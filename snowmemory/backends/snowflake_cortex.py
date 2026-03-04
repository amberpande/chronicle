"""
SnowMemory — Snowflake + Cortex Backend
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All AI operations run as native Snowflake SQL functions.
Nothing leaves the warehouse for embedding, search, or graph extraction.

┌─────────────────────────────────────────────────────────────────┐
│  What runs INSIDE Snowflake SQL (not in Python):                │
│                                                                 │
│  SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', content)         │
│    → generates 768-dim VECTOR from text                         │
│                                                                 │
│  VECTOR_COSINE_SIMILARITY(embedding, query_vec) * decay_weight  │
│    → server-side ANN — only top-k rows cross the wire           │
│                                                                 │
│  SNOWFLAKE.CORTEX.COMPLETE('mistral-7b', prompt)                │
│    → LLM graph extraction as a SQL function                     │
│                                                                 │
│  SNOWFLAKE.CORTEX.CLASSIFY_TEXT(content, labels)               │
│    → optional memory-type classification                        │
└─────────────────────────────────────────────────────────────────┘

vs. old approach (ARRAY + client-side cosine):
  Old: SELECT * → full table to Python → cosine on every row → slow
  New: SQL computes similarity → only top-k rows returned → fast

Supported Cortex embedding models:
  e5-base-v2                (768d)  ← default, cost-effective
  snowflake-arctic-embed-m  (768d)  ← Snowflake native
  snowflake-arctic-embed-l  (1024d) ← higher quality
  multilingual-e5-large     (1024d) ← multilingual
  voyage-multilingual-2     (1024d) ← highest quality

Supported Cortex LLMs (COMPLETE):
  mistral-7b | mixtral-8x7b | llama3-8b | llama3-70b
  llama3.1-8b | llama3.1-70b | snowflake-arctic
  reka-flash | reka-core | jamba-instruct

Requirements:
  pip install snowflake-connector-python
  Snowflake Enterprise+ account with Cortex AI enabled
"""
from __future__ import annotations
import json, math, uuid, re
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import MemoryBackend
from ..core.models import (
    AuditRecord, GraphPayload, GraphRelation,
    IntegrityReport, Memory, MemoryStatus, MemoryType, OperationType,
)
from ..config.schema import SnowflakeBackendConfig, CortexConfig


# ─────────────────────────────────────────────────────────────────────────────
# DDL  — native VECTOR column sized to match the chosen embedding model
# ─────────────────────────────────────────────────────────────────────────────

_DDL = """
CREATE DATABASE IF NOT EXISTS {db};
CREATE SCHEMA   IF NOT EXISTS {s};

CREATE TABLE IF NOT EXISTS {s}.agent_memories (
    memory_id        VARCHAR(64)   NOT NULL PRIMARY KEY,
    agent_id         VARCHAR(256)  NOT NULL,
    session_id       VARCHAR(256),
    memory_type      VARCHAR(32)   NOT NULL,
    content          TEXT          NOT NULL,
    embedding        VECTOR(FLOAT, {dim}),
    entities         ARRAY,
    domain           VARCHAR(128)  DEFAULT 'general',
    surprise_score   FLOAT         DEFAULT 0,
    novelty_score    FLOAT         DEFAULT 0,
    orphan_score     FLOAT         DEFAULT 0,
    bridge_score     FLOAT         DEFAULT 0,
    confidence       FLOAT         DEFAULT 1,
    decay_weight     FLOAT         DEFAULT 1,
    access_count     INTEGER       DEFAULT 0,
    status           VARCHAR(32)   DEFAULT 'ACTIVE',
    version          INTEGER       DEFAULT 1,
    created_at       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    last_accessed_at TIMESTAMP_NTZ,
    expires_at       TIMESTAMP_NTZ,
    metadata         VARIANT
);

CREATE TABLE IF NOT EXISTS {s}.memory_relations (
    relation_id   VARCHAR(64)  NOT NULL PRIMARY KEY,
    from_entity   VARCHAR(512) NOT NULL,
    relation_type VARCHAR(128) NOT NULL,
    to_entity     VARCHAR(512) NOT NULL,
    confidence    FLOAT        DEFAULT 1,
    memory_id     VARCHAR(64),
    agent_id      VARCHAR(256),
    created_at    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS {s}.domain_stats (
    domain     VARCHAR(128) NOT NULL PRIMARY KEY,
    mean       FLOAT        DEFAULT 0.5,
    std        FLOAT        DEFAULT 0.2,
    m2         FLOAT        DEFAULT 0,
    count      FLOAT        DEFAULT 0,
    updated_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Immutable audit ledger — stores hash only, never content
CREATE TABLE IF NOT EXISTS {s}.audit_log (
    audit_id       VARCHAR(64)  NOT NULL PRIMARY KEY,
    operation      VARCHAR(32)  NOT NULL,
    memory_id      VARCHAR(64)  NOT NULL,
    agent_id       VARCHAR(256) NOT NULL,
    content_hash   VARCHAR(64)  NOT NULL,
    timestamp      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    salience_score FLOAT        DEFAULT 0,
    decay_weight   FLOAT        DEFAULT 1,
    session_id     VARCHAR(256),
    notes          TEXT
);
"""


def _embed_fn(model: str, dim: int) -> str:
    """Returns SNOWFLAKE.CORTEX.EMBED_TEXT_{dim}(model, {text}) template."""
    return f"SNOWFLAKE.CORTEX.EMBED_TEXT_{dim}('{model}', {{text}})"


# ─────────────────────────────────────────────────────────────────────────────
# Graph extraction prompt for CORTEX.COMPLETE
# ─────────────────────────────────────────────────────────────────────────────

_GRAPH_PROMPT = """Extract entities and relations from this text.
Return ONLY valid JSON (no explanation, no markdown fences):
{{"entities":["entity1","entity2"],"relations":[{{"from":"A","type":"RELATION","to":"B","confidence":0.9}}]}}

Text: {content}

JSON:"""


class SnowflakeCortexBackend(MemoryBackend):
    """
    Production Snowflake backend with full Cortex AI integration.
    Drop-in replacement for InMemoryBackend — same interface, Snowflake storage.
    """

    def __init__(self, sf: SnowflakeBackendConfig, cortex: CortexConfig):
        self.sf     = sf
        self.cortex = cortex
        self._conn  = None
        self._dim   = cortex.embedding_dim
        self._emodel = cortex.embedding_model
        self._llm   = cortex.complete_model
        self._s     = f"{sf.database}.{sf.schema_name}"
        self._connect()
        self._setup()

    # ── Connection ──────────────────────────────────────────────────────────

    def _connect(self):
        try:
            import snowflake.connector as sf_conn
        except ImportError:
            raise ImportError("pip install snowflake-connector-python")

        kwargs: Dict[str, Any] = dict(
            account   = self.sf.account,
            user      = self.sf.user,
            warehouse = self.sf.warehouse,
            database  = self.sf.database,
            schema    = self.sf.schema_name,
        )
        if self.sf.role:
            kwargs["role"] = self.sf.role
        if self.sf.authenticator:
            kwargs["authenticator"] = self.sf.authenticator
        elif self.sf.private_key_path:
            kwargs["private_key"] = self._load_pkey()
        else:
            kwargs["password"] = self.sf.password

        self._conn = sf_conn.connect(**kwargs)

    def _load_pkey(self) -> bytes:
        from cryptography.hazmat.primitives.serialization import (
            load_pem_private_key, Encoding, PrivateFormat, NoEncryption
        )
        with open(self.sf.private_key_path, "rb") as f:
            k = load_pem_private_key(f.read(), password=None)
        return k.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())

    def _setup(self):
        ddl = _DDL.format(db=self.sf.database, s=self._s, dim=self._dim)
        cur = self._conn.cursor()
        for stmt in ddl.split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    cur.execute(stmt)
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"[CortexBackend DDL warn] {e}")

    def _cur(self):
        try:
            self._conn.cursor().execute("SELECT 1")
        except Exception:
            self._connect()
        return self._conn.cursor()

    # ── Cortex: Embedding ──────────────────────────────────────────────────

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding inside Snowflake via CORTEX.EMBED_TEXT.
        Used by the salience engine when cortex embedder mode is active.
        """
        fn  = _embed_fn(self._emodel, self._dim).format(text="%s")
        cur = self._cur()
        cur.execute(f"SELECT {fn}::ARRAY", (text,))
        row = cur.fetchone()
        if row and row[0]:
            v = row[0]
            if isinstance(v, str):
                v = json.loads(v)
            return [float(x) for x in v]
        return []

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Batch embed — one round-trip for up to N texts via VALUES table."""
        if not texts:
            return []
        fn   = _embed_fn(self._emodel, self._dim).format(text="t.v")
        vals = ", ".join("(%s)" for _ in texts)
        cur  = self._cur()
        cur.execute(f"SELECT {fn}::ARRAY FROM (VALUES {vals}) t(v)", texts)
        out = []
        for row in cur.fetchall():
            v = row[0] or []
            if isinstance(v, str):
                v = json.loads(v)
            out.append([float(x) for x in v])
        return out

    # ── Cortex: LLM graph extraction ───────────────────────────────────────

    def extract_graph_cortex(self, content: str, memory_id: str = "") -> GraphPayload:
        """
        Run entity/relation extraction using CORTEX.COMPLETE inside Snowflake.
        The LLM call never leaves the warehouse.
        Falls back to empty payload on error.
        """
        prompt = _GRAPH_PROMPT.format(content=content[:1500])
        cur    = self._cur()
        try:
            cur.execute(
                f"SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s)",
                (self._llm, prompt)
            )
            raw = (cur.fetchone() or ["{}"])[0]
            # Strip markdown fences if model wraps output
            raw = re.sub(r"```(?:json)?|```", "", raw).strip()
            data      = json.loads(raw)
            entities  = [str(e) for e in data.get("entities", [])]
            relations = [
                GraphRelation(
                    from_entity=str(r.get("from", "")),
                    relation_type=str(r.get("type", "RELATED_TO")).upper(),
                    to_entity=str(r.get("to", "")),
                    confidence=float(r.get("confidence", 0.8)),
                    memory_id=memory_id,
                )
                for r in data.get("relations", [])
                if r.get("from") and r.get("to")
            ]
            return GraphPayload(entities=entities, relations=relations)
        except Exception as e:
            print(f"[CortexBackend] graph extraction failed: {e}")
            return GraphPayload()

    # ── Core CRUD ───────────────────────────────────────────────────────────

    def write(self, memory: Memory) -> bool:
        """
        Write memory. If use_cortex_embed=True, Snowflake generates the
        embedding inline in the INSERT — no embedding passed from Python.
        """
        cur = self._cur()
        if self.cortex.use_cortex_embed and self.cortex.use_vector_column:
            fn = _embed_fn(self._emodel, self._dim).format(text="%s")
            cur.execute(f"""
                INSERT INTO {self._s}.agent_memories
                  (memory_id,agent_id,session_id,memory_type,content,embedding,
                   entities,domain,surprise_score,novelty_score,orphan_score,
                   bridge_score,confidence,decay_weight,access_count,status,
                   version,expires_at,metadata)
                SELECT
                  %s,%s,%s,%s,%s,
                  {fn}::VECTOR(FLOAT,{self._dim}),
                  PARSE_JSON(%s),%s,
                  %s,%s,%s,%s,
                  %s,%s,%s,%s,
                  %s,%s,PARSE_JSON(%s)
            """, (
                memory.memory_id, memory.agent_id, memory.session_id,
                memory.memory_type.value, memory.content,
                memory.content,                    # ← passed to embed_fn
                json.dumps(memory.entities), memory.domain,
                memory.surprise_score, memory.novelty_score,
                memory.orphan_score, memory.bridge_score,
                memory.confidence, memory.decay_weight,
                memory.access_count, memory.status.value,
                memory.version,
                memory.expires_at.isoformat() if memory.expires_at else None,
                json.dumps(memory.metadata),
            ))
        else:
            # Pre-computed or null embedding (legacy / no-cortex mode)
            cur.execute(f"""
                INSERT INTO {self._s}.agent_memories
                  (memory_id,agent_id,session_id,memory_type,content,
                   entities,domain,surprise_score,novelty_score,orphan_score,
                   bridge_score,confidence,decay_weight,access_count,status,
                   version,expires_at,metadata)
                VALUES (%s,%s,%s,%s,%s,PARSE_JSON(%s),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,PARSE_JSON(%s))
            """, (
                memory.memory_id, memory.agent_id, memory.session_id,
                memory.memory_type.value, memory.content,
                json.dumps(memory.entities), memory.domain,
                memory.surprise_score, memory.novelty_score,
                memory.orphan_score, memory.bridge_score,
                memory.confidence, memory.decay_weight,
                memory.access_count, memory.status.value,
                memory.version,
                memory.expires_at.isoformat() if memory.expires_at else None,
                json.dumps(memory.metadata),
            ))
        return True

    def get(self, memory_id: str) -> Optional[Memory]:
        cur = self._cur()
        cur.execute(
            f"SELECT * EXCLUDE embedding FROM {self._s}.agent_memories WHERE memory_id=%s",
            (memory_id,)
        )
        row = cur.fetchone()
        return self._row(row, cur.description) if row else None

    def delete(self, memory_id: str) -> bool:
        self._cur().execute(
            f"DELETE FROM {self._s}.agent_memories WHERE memory_id=%s", (memory_id,)
        )
        return True

    def update_decay(self, memory_id: str, new_weight: float) -> bool:
        self._cur().execute(
            f"UPDATE {self._s}.agent_memories SET decay_weight=%s WHERE memory_id=%s",
            (max(0.0, min(1.0, new_weight)), memory_id)
        )
        return True

    def update_access(self, memory_id: str) -> bool:
        self._cur().execute(f"""
            UPDATE {self._s}.agent_memories
            SET access_count=access_count+1,
                last_accessed_at=CURRENT_TIMESTAMP()
            WHERE memory_id=%s
        """, (memory_id,))
        return True

    # ── Vector Search — runs entirely in Snowflake SQL ─────────────────────

    def query_by_text(
        self,
        query_text: str,
        agent_id:   str,
        top_k:      int = 10,
        memory_types: Optional[List[MemoryType]] = None,
        min_decay:  float = 0.1,
    ) -> List[Memory]:
        """
        Preferred Cortex query path.
        Pass raw text — Snowflake embeds it AND computes similarity in one SQL:

            VECTOR_COSINE_SIMILARITY(
                embedding,
                SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', :query)
            ) * decay_weight   AS ranked_score

        Only top_k rows are returned. Full-table scan never happens.
        """
        fn     = _embed_fn(self._emodel, self._dim).format(text="%s")
        where  = ["agent_id=%s", "embedding IS NOT NULL", "decay_weight>=%s"]
        params: List[Any] = [agent_id, min_decay]

        if memory_types:
            placeholders = ",".join(["%s"] * len(memory_types))
            where.append(f"memory_type IN ({placeholders})")
            params.extend(mt.value for mt in memory_types)

        # expires_at filter
        where.append("(expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP())")

        where_sql = " AND ".join(where)
        cur = self._cur()
        cur.execute(f"""
            SELECT * EXCLUDE embedding,
                   VECTOR_COSINE_SIMILARITY(
                       embedding,
                       {fn}::VECTOR(FLOAT,{self._dim})
                   ) AS _sim,
                   VECTOR_COSINE_SIMILARITY(
                       embedding,
                       {fn}::VECTOR(FLOAT,{self._dim})
                   ) * decay_weight AS _ranked
            FROM {self._s}.agent_memories
            WHERE {where_sql}
            ORDER BY _ranked DESC
            LIMIT {top_k}
        """, [*params, query_text, query_text])  # query_text passed twice for both embed_fn calls
        rows = cur.fetchall()
        return [self._row(r, cur.description) for r in rows]

    def get_neighbors(
        self,
        embedding:   List[float],
        k:           int = 5,
        memory_type: Optional[MemoryType] = None,
        domain:      Optional[str] = None,
        agent_id:    Optional[str] = None,
    ) -> List[Memory]:
        """
        Salience engine calls this with a pre-computed embedding vector.
        Converts the Python list to a Snowflake VECTOR literal inline in SQL.
        """
        where  = ["embedding IS NOT NULL"]
        params: List[Any] = []

        if memory_type:
            where.append("memory_type=%s"); params.append(memory_type.value)
        if domain:
            where.append("domain=%s");      params.append(domain)
        if agent_id:
            where.append("agent_id=%s");    params.append(agent_id)

        where_sql = " AND ".join(where)
        # Build inline VECTOR literal from Python list
        vec_literal = "[" + ",".join(str(x) for x in embedding) + "]"

        cur = self._cur()
        cur.execute(f"""
            SELECT * EXCLUDE embedding,
                   VECTOR_COSINE_SIMILARITY(
                       embedding,
                       {vec_literal}::VECTOR(FLOAT,{self._dim})
                   ) AS _sim
            FROM {self._s}.agent_memories
            WHERE {where_sql}
            ORDER BY _sim DESC
            LIMIT {k}
        """, params)
        rows = cur.fetchall()
        return [self._row(r, cur.description) for r in rows]

    def query(
        self,
        embedding: List[float],
        agent_id:  str,
        top_k:     int = 10,
        memory_types: Optional[List[MemoryType]] = None,
        min_decay: float = 0.1,
    ) -> List[Memory]:
        """Standard interface — uses inline VECTOR literal for the query vec."""
        where  = ["agent_id=%s", "embedding IS NOT NULL", "decay_weight>=%s"]
        params: List[Any] = [agent_id, min_decay]

        if memory_types:
            ph = ",".join(["%s"] * len(memory_types))
            where.append(f"memory_type IN ({ph})")
            params.extend(mt.value for mt in memory_types)

        where.append("(expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP())")
        where_sql = " AND ".join(where)
        vec_literal = "[" + ",".join(str(x) for x in embedding) + "]"

        cur = self._cur()
        cur.execute(f"""
            SELECT * EXCLUDE embedding,
                   VECTOR_COSINE_SIMILARITY(
                       embedding,
                       {vec_literal}::VECTOR(FLOAT,{self._dim})
                   ) * decay_weight AS _ranked
            FROM {self._s}.agent_memories
            WHERE {where_sql}
            ORDER BY _ranked DESC
            LIMIT {top_k}
        """, params)
        rows = cur.fetchall()
        return [self._row(r, cur.description) for r in rows]

    # ── Cortex Search Service (optional managed semantic search) ───────────

    def cortex_search(
        self,
        query_text: str,
        agent_id:   str,
        top_k:      int = 10,
    ) -> List[Memory]:
        """
        Use Cortex Search Service if configured — highest quality semantic search.
        Requires a pre-created CORTEX SEARCH SERVICE in Snowflake.

        CREATE OR REPLACE CORTEX SEARCH SERVICE MEMORY_SEARCH_SVC
          ON content
          WAREHOUSE = MEMORY_WH
          TARGET_LAG = '1 minute'
          AS (
            SELECT memory_id, agent_id, content, domain, memory_type, decay_weight
            FROM SNOWMEMORY_DB.AGENT_MEMORY.agent_memories
            WHERE status = 'ACTIVE'
          );
        """
        if not self.cortex.use_cortex_search or not self.cortex.cortex_search_service:
            return self.query_by_text(query_text, agent_id, top_k)

        svc = self.cortex.cortex_search_service
        cur = self._cur()
        cur.execute(f"""
            SELECT memory_id FROM TABLE(
                {svc}!SEARCH(
                    query => %s,
                    columns => ['content'],
                    filter => OBJECT_CONSTRUCT('agent_id', %s),
                    limit => {top_k}
                )
            )
        """, (query_text, agent_id))
        ids      = [row[0] for row in cur.fetchall()]
        memories = [self.get(mid) for mid in ids]
        return [m for m in memories if m]

    # ── Graph ───────────────────────────────────────────────────────────────

    def write_relations(self, relations: List[GraphRelation]) -> bool:
        cur = self._cur()
        for r in relations:
            cur.execute(f"""
                INSERT INTO {self._s}.memory_relations
                  (relation_id,from_entity,relation_type,to_entity,confidence,memory_id,agent_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (
                str(uuid.uuid4()), r.from_entity, r.relation_type,
                r.to_entity, r.confidence, r.memory_id, None
            ))
        return True

    def get_graph_neighbors(
        self, entity: str, depth: int = 2, agent_id: Optional[str] = None
    ) -> List[Dict]:
        cur = self._cur()
        # Recursive CTE — max_depth=2 is safe for production
        cur.execute(f"""
            WITH RECURSIVE g AS (
                SELECT from_entity, to_entity, relation_type, 1 AS d, memory_id
                FROM {self._s}.memory_relations
                WHERE LOWER(from_entity) = LOWER(%s)
                UNION ALL
                SELECT r.from_entity, r.to_entity, r.relation_type, g.d+1, r.memory_id
                FROM {self._s}.memory_relations r
                JOIN g ON LOWER(r.from_entity) = LOWER(g.to_entity)
                WHERE g.d < %s
            )
            SELECT g.from_entity, g.relation_type, g.to_entity, g.d, m.content
            FROM g
            LEFT JOIN {self._s}.agent_memories m ON m.memory_id = g.memory_id
            LIMIT 200
        """, (entity, depth))
        return [
            {"from_entity": r[0], "relation_type": r[1],
             "to_entity": r[2], "depth": r[3], "content": r[4]}
            for r in cur.fetchall()
        ]

    # ── Domain Stats ─────────────────────────────────────────────────────────

    def get_domain_stats(self, domain: str) -> Dict:
        cur = self._cur()
        cur.execute(
            f"SELECT mean,std,m2,count FROM {self._s}.domain_stats WHERE domain=%s",
            (domain,)
        )
        row = cur.fetchone()
        if row:
            return {"mean": row[0], "std": row[1], "m2": row[2], "count": row[3]}
        return {"mean": 0.5, "std": 0.2, "m2": 0.0, "count": 0}

    def update_domain_stats(self, domain: str, novelty: float) -> None:
        stats = self.get_domain_stats(domain)
        n     = stats["count"] + 1
        mean  = stats["mean"] + (novelty - stats["mean"]) / n
        m2    = stats.get("m2", 0.0) + (novelty - stats["mean"]) * (novelty - mean)
        std   = math.sqrt(m2 / n) if n > 1 else 0.2
        self._cur().execute(f"""
            MERGE INTO {self._s}.domain_stats t
            USING (SELECT %s AS domain) s ON t.domain = s.domain
            WHEN MATCHED     THEN UPDATE SET mean=%s,std=%s,m2=%s,count=%s,updated_at=CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN INSERT (domain,mean,std,m2,count) VALUES (%s,%s,%s,%s,%s)
        """, (domain, mean, max(std, 1e-6), m2, n,
              domain, mean, max(std, 1e-6), m2, n))

    # ── Audit ────────────────────────────────────────────────────────────────

    def write_audit(self, record: AuditRecord) -> bool:
        self._cur().execute(f"""
            INSERT INTO {self._s}.audit_log
              (audit_id,operation,memory_id,agent_id,content_hash,
               timestamp,salience_score,decay_weight,session_id,notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            str(uuid.uuid4()), record.operation.value, record.memory_id,
            record.agent_id, record.content_hash,
            record.timestamp.isoformat(), record.salience_score,
            record.decay_weight, record.session_id, record.notes,
        ))
        return True

    def get_audit_trail(self, memory_id: str) -> List[AuditRecord]:
        cur = self._cur()
        cur.execute(f"""
            SELECT operation,memory_id,agent_id,content_hash,
                   timestamp,salience_score,decay_weight,session_id,notes
            FROM {self._s}.audit_log
            WHERE memory_id=%s
            ORDER BY timestamp ASC
        """, (memory_id,))
        records = []
        for row in cur.fetchall():
            records.append(AuditRecord(
                operation=OperationType(row[0]),
                memory_id=row[1],
                agent_id=row[2],
                content_hash=row[3],
                timestamp=row[4] if isinstance(row[4], datetime) else datetime.fromisoformat(str(row[4])),
                salience_score=row[5] or 0.0,
                decay_weight=row[6] or 1.0,
                session_id=row[7],
                notes=row[8] or "",
            ))
        return records

    def verify_integrity(self, memory_id: str) -> IntegrityReport:
        memory = self.get(memory_id)
        if not memory:
            return IntegrityReport(
                memory_id=memory_id, content_hash_matches=False,
                original_write_timestamp=datetime.utcnow(),
                operation_count=0, current_hash="", stored_hash=""
            )
        cur = self._cur()
        cur.execute(f"""
            SELECT content_hash, timestamp, COUNT(*) OVER() AS total
            FROM {self._s}.audit_log
            WHERE memory_id=%s AND operation='WRITE'
            ORDER BY timestamp ASC LIMIT 1
        """, (memory_id,))
        row          = cur.fetchone()
        stored_hash  = row[0] if row else ""
        write_ts     = row[1] if row else datetime.utcnow()
        op_count     = row[2] if row else 0
        current_hash = memory.content_hash()
        return IntegrityReport(
            memory_id=memory_id,
            content_hash_matches=(current_hash == stored_hash),
            original_write_timestamp=write_ts if isinstance(write_ts, datetime) else datetime.fromisoformat(str(write_ts)),
            operation_count=op_count,
            current_hash=current_hash,
            stored_hash=stored_hash,
        )

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def expire_old(self, agent_id: str, memory_type: MemoryType) -> int:
        cur = self._cur()
        cur.execute(f"""
            DELETE FROM {self._s}.agent_memories
            WHERE agent_id=%s AND memory_type=%s
              AND expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP()
        """, (agent_id, memory_type.value))
        return cur.rowcount

    def get_all(self, agent_id: str, memory_type: Optional[MemoryType] = None) -> List[Memory]:
        where  = ["agent_id=%s"]
        params: List[Any] = [agent_id]
        if memory_type:
            where.append("memory_type=%s"); params.append(memory_type.value)
        cur = self._cur()
        cur.execute(
            f"SELECT * EXCLUDE embedding FROM {self._s}.agent_memories WHERE {' AND '.join(where)}",
            params
        )
        return [self._row(r, cur.description) for r in cur.fetchall()]

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _row(self, row, description) -> Memory:
        cols = {d[0].lower(): i for i, d in enumerate(description)}
        def v(c): return row[cols[c]] if c in cols else None

        entities = v("entities") or []
        if isinstance(entities, str):
            entities = json.loads(entities)

        return Memory(
            memory_id     = v("memory_id"),
            content       = v("content"),
            agent_id      = v("agent_id"),
            memory_type   = MemoryType(v("memory_type")),
            session_id    = v("session_id"),
            embedding     = None,              # excluded from SELECT for perf
            entities      = entities,
            domain        = v("domain") or "general",
            surprise_score= float(v("surprise_score") or 0),
            novelty_score = float(v("novelty_score")  or 0),
            orphan_score  = float(v("orphan_score")   or 0),
            bridge_score  = float(v("bridge_score")   or 0),
            confidence    = float(v("confidence")     or 1),
            decay_weight  = float(v("decay_weight")   or 1),
            access_count  = int(v("access_count")     or 0),
            status        = MemoryStatus(v("status") or "ACTIVE"),
            version       = int(v("version") or 1),
        )

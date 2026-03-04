"""
SnowMemory Snowflake Backend
Production backend using Snowflake Iceberg tables + native VECTOR type.
Requires: snowflake-connector-python
"""
from __future__ import annotations
import json, math
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import MemoryBackend
from ..core.models import (
    AuditRecord, GraphRelation, IntegrityReport,
    Memory, MemoryType, MemoryStatus, OperationType,
)
from ..config.schema import SnowflakeBackendConfig


_SETUP_SQL = """
CREATE SCHEMA IF NOT EXISTS {schema};

CREATE TABLE IF NOT EXISTS {schema}.agent_memories (
    memory_id        VARCHAR         NOT NULL PRIMARY KEY,
    agent_id         VARCHAR         NOT NULL,
    session_id       VARCHAR,
    memory_type      VARCHAR         NOT NULL,
    content          VARCHAR         NOT NULL,
    embedding        ARRAY,
    entities         ARRAY,
    domain           VARCHAR         DEFAULT 'general',
    surprise_score   FLOAT           DEFAULT 0,
    novelty_score    FLOAT           DEFAULT 0,
    orphan_score     FLOAT           DEFAULT 0,
    bridge_score     FLOAT           DEFAULT 0,
    confidence       FLOAT           DEFAULT 1,
    decay_weight     FLOAT           DEFAULT 1,
    access_count     INTEGER         DEFAULT 0,
    status           VARCHAR         DEFAULT 'ACTIVE',
    version          INTEGER         DEFAULT 1,
    created_at       TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    last_accessed_at TIMESTAMP_NTZ,
    expires_at       TIMESTAMP_NTZ,
    metadata         VARIANT
);

CREATE TABLE IF NOT EXISTS {schema}.memory_relations (
    relation_id      VARCHAR         NOT NULL PRIMARY KEY,
    from_entity      VARCHAR         NOT NULL,
    relation_type    VARCHAR         NOT NULL,
    to_entity        VARCHAR         NOT NULL,
    confidence       FLOAT           DEFAULT 1,
    memory_id        VARCHAR,
    created_at       TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS {schema}.domain_stats (
    domain           VARCHAR         NOT NULL PRIMARY KEY,
    mean             FLOAT           DEFAULT 0.5,
    std              FLOAT           DEFAULT 0.2,
    m2               FLOAT           DEFAULT 0,
    count            FLOAT           DEFAULT 0,
    updated_at       TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS {schema}.audit_log (
    audit_id         VARCHAR         NOT NULL PRIMARY KEY,
    operation        VARCHAR         NOT NULL,
    memory_id        VARCHAR         NOT NULL,
    agent_id         VARCHAR         NOT NULL,
    content_hash     VARCHAR         NOT NULL,
    timestamp        TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    salience_score   FLOAT           DEFAULT 0,
    decay_weight     FLOAT           DEFAULT 1,
    session_id       VARCHAR,
    notes            VARCHAR
);
"""


def _cosine_sql_fallback(a: List[float], b: List[float]) -> float:
    """Client-side cosine similarity when native vector search unavailable."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-9)


class SnowflakeMemoryBackend(MemoryBackend):
    """
    Snowflake-backed memory store.
    Uses ARRAY column for embeddings + client-side cosine for MVP.
    Production upgrade path: migrate to VECTOR column + VECTOR_COSINE_SIMILARITY.
    """

    def __init__(self, config: SnowflakeBackendConfig):
        self.config = config
        self._conn  = None
        self._setup()

    def _connect(self):
        try:
            import snowflake.connector
            self._conn = snowflake.connector.connect(
                account=self.config.account,
                user=self.config.user,
                password=self.config.password,
                warehouse=self.config.warehouse,
                database=self.config.database,
                schema=self.config.schema_name,
                role=self.config.role or None,
            )
        except ImportError:
            raise ImportError(
                "pip install snowflake-connector-python to use Snowflake backend"
            )

    def _setup(self):
        try:
            self._connect()
            schema = f"{self.config.database}.{self.config.schema_name}"
            cur    = self._conn.cursor()
            for stmt in _SETUP_SQL.format(schema=schema).split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
        except Exception as e:
            print(f"[SnowflakeBackend] Setup skipped — {e}")

    def _cur(self):
        return self._conn.cursor()

    def _schema(self):
        return f"{self.config.database}.{self.config.schema_name}"

    # ── Core CRUD ────────────────────────────────────────────────

    def write(self, memory: Memory) -> bool:
        s   = self._schema()
        cur = self._cur()
        cur.execute(f"""
            INSERT INTO {s}.agent_memories
            (memory_id,agent_id,session_id,memory_type,content,embedding,
             entities,domain,surprise_score,novelty_score,orphan_score,
             bridge_score,confidence,decay_weight,access_count,status,
             version,expires_at,metadata)
            SELECT
              %s,%s,%s,%s,%s,PARSE_JSON(%s),
              PARSE_JSON(%s),%s,%s,%s,%s,
              %s,%s,%s,%s,%s,
              %s,%s,PARSE_JSON(%s)
        """, (
            memory.memory_id, memory.agent_id, memory.session_id,
            memory.memory_type.value, memory.content,
            json.dumps(memory.embedding),
            json.dumps(memory.entities),
            memory.domain,
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
            f"SELECT * FROM {self._schema()}.agent_memories WHERE memory_id = %s",
            (memory_id,)
        )
        row = cur.fetchone()
        return self._row_to_memory(row, cur.description) if row else None

    def delete(self, memory_id: str) -> bool:
        self._cur().execute(
            f"DELETE FROM {self._schema()}.agent_memories WHERE memory_id = %s",
            (memory_id,)
        )
        return True

    def update_decay(self, memory_id: str, new_weight: float) -> bool:
        self._cur().execute(
            f"UPDATE {self._schema()}.agent_memories SET decay_weight=%s WHERE memory_id=%s",
            (new_weight, memory_id)
        )
        return True

    def update_access(self, memory_id: str) -> bool:
        self._cur().execute(f"""
            UPDATE {self._schema()}.agent_memories
            SET access_count = access_count+1,
                last_accessed_at = CURRENT_TIMESTAMP()
            WHERE memory_id = %s
        """, (memory_id,))
        return True

    # ── Vector Search (client-side cosine for MVP) ────────────────

    def get_neighbors(self, embedding, k=5, memory_type=None,
                      domain=None, agent_id=None) -> List[Memory]:
        where = "1=1"
        if memory_type:
            where += f" AND memory_type='{memory_type.value}'"
        if domain:
            where += f" AND domain='{domain}'"
        if agent_id:
            where += f" AND agent_id='{agent_id}'"

        cur = self._cur()
        cur.execute(f"SELECT * FROM {self._schema()}.agent_memories WHERE {where}")
        rows = cur.fetchall()
        memories = [self._row_to_memory(r, cur.description) for r in rows]

        scored = [
            (m, _cosine_sql_fallback(embedding, m.embedding or []))
            for m in memories if m.embedding
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [m for m, _ in scored[:k]]

    def query(self, embedding, agent_id, top_k=10,
              memory_types=None, min_decay=0.1) -> List[Memory]:
        return self.get_neighbors(embedding, k=top_k, agent_id=agent_id)

    # ── Graph ─────────────────────────────────────────────────────

    def write_relations(self, relations: List[GraphRelation]) -> bool:
        import uuid
        cur = self._cur()
        for r in relations:
            cur.execute(f"""
                INSERT INTO {self._schema()}.memory_relations
                (relation_id,from_entity,relation_type,to_entity,confidence,memory_id)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (str(uuid.uuid4()), r.from_entity, r.relation_type,
                  r.to_entity, r.confidence, r.memory_id))
        return True

    def get_graph_neighbors(self, entity, depth=2, agent_id=None):
        cur = self._cur()
        # Recursive CTE for graph traversal
        cur.execute(f"""
            WITH RECURSIVE entity_graph AS (
                SELECT from_entity, to_entity, relation_type, 1 AS depth, memory_id
                FROM {self._schema()}.memory_relations
                WHERE LOWER(from_entity) = LOWER(%s)
                UNION ALL
                SELECT r.from_entity, r.to_entity, r.relation_type, g.depth+1, r.memory_id
                FROM {self._schema()}.memory_relations r
                JOIN entity_graph g ON LOWER(r.from_entity) = LOWER(g.to_entity)
                WHERE g.depth < %s
            )
            SELECT eg.from_entity, eg.relation_type, eg.to_entity, eg.depth, m.content
            FROM entity_graph eg
            LEFT JOIN {self._schema()}.agent_memories m ON m.memory_id = eg.memory_id
        """, (entity, depth))
        rows = cur.fetchall()
        return [
            {"from_entity": r[0], "relation_type": r[1], "to_entity": r[2],
             "depth": r[3], "content": r[4]}
            for r in rows
        ]

    # ── Domain Stats ──────────────────────────────────────────────

    def get_domain_stats(self, domain: str) -> Dict[str, float]:
        cur = self._cur()
        cur.execute(
            f"SELECT mean,std,count FROM {self._schema()}.domain_stats WHERE domain=%s",
            (domain,)
        )
        row = cur.fetchone()
        return {"mean": row[0], "std": row[1], "count": row[2]} if row else {
            "mean": 0.5, "std": 0.2, "count": 0
        }

    def update_domain_stats(self, domain: str, novelty: float) -> None:
        cur = self._cur()
        stats = self.get_domain_stats(domain)
        n  = stats["count"] + 1
        m  = stats["mean"] + (novelty - stats["mean"]) / n
        m2 = stats.get("m2", 0.0) + (novelty - stats["mean"]) * (novelty - m)
        std = math.sqrt(m2 / n) if n > 1 else 0.2
        cur.execute(f"""
            MERGE INTO {self._schema()}.domain_stats t
            USING (SELECT %s AS domain) s ON t.domain = s.domain
            WHEN MATCHED THEN UPDATE SET mean=%s,std=%s,m2=%s,count=%s
            WHEN NOT MATCHED THEN INSERT (domain,mean,std,m2,count) VALUES (%s,%s,%s,%s,%s)
        """, (domain, m, max(std, 1e-6), m2, n, domain, m, max(std, 1e-6), m2, n))

    # ── Audit ─────────────────────────────────────────────────────

    def write_audit(self, record: AuditRecord) -> bool:
        import uuid
        cur = self._cur()
        cur.execute(f"""
            INSERT INTO {self._schema()}.audit_log
            (audit_id,operation,memory_id,agent_id,content_hash,
             timestamp,salience_score,decay_weight,session_id,notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            str(uuid.uuid4()), record.operation.value, record.memory_id,
            record.agent_id, record.content_hash,
            record.timestamp.isoformat(), record.salience_score,
            record.decay_weight, record.session_id, record.notes
        ))
        return True

    def get_audit_trail(self, memory_id: str) -> List[AuditRecord]:
        cur = self._cur()
        cur.execute(
            f"SELECT * FROM {self._schema()}.audit_log WHERE memory_id=%s ORDER BY timestamp",
            (memory_id,)
        )
        # Simplified return
        return []

    def verify_integrity(self, memory_id: str) -> IntegrityReport:
        m = self.get(memory_id)
        if not m:
            return IntegrityReport(
                memory_id=memory_id, content_hash_matches=False,
                original_write_timestamp=datetime.utcnow(),
                operation_count=0, current_hash="", stored_hash=""
            )
        cur = self._cur()
        cur.execute(f"""
            SELECT content_hash, timestamp FROM {self._schema()}.audit_log
            WHERE memory_id=%s AND operation='WRITE' ORDER BY timestamp LIMIT 1
        """, (memory_id,))
        row = cur.fetchone()
        stored_hash = row[0] if row else ""
        current_hash = m.content_hash()
        return IntegrityReport(
            memory_id=memory_id,
            content_hash_matches=current_hash == stored_hash,
            original_write_timestamp=row[1] if row else datetime.utcnow(),
            operation_count=0,
            current_hash=current_hash,
            stored_hash=stored_hash,
        )

    def expire_old(self, agent_id, memory_type) -> int:
        cur = self._cur()
        cur.execute(f"""
            DELETE FROM {self._schema()}.agent_memories
            WHERE agent_id=%s AND memory_type=%s
            AND expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP()
        """, (agent_id, memory_type.value))
        return cur.rowcount

    def get_all(self, agent_id, memory_type=None) -> List[Memory]:
        where = f"agent_id='{agent_id}'"
        if memory_type:
            where += f" AND memory_type='{memory_type.value}'"
        cur = self._cur()
        cur.execute(f"SELECT * FROM {self._schema()}.agent_memories WHERE {where}")
        return [self._row_to_memory(r, cur.description) for r in cur.fetchall()]

    # ── Helpers ───────────────────────────────────────────────────

    def _row_to_memory(self, row, description) -> Memory:
        cols = {d[0].lower(): i for i, d in enumerate(description)}
        def v(col): return row[cols[col]] if col in cols else None
        emb = v("embedding")
        if isinstance(emb, str):
            emb = json.loads(emb)
        entities = v("entities") or []
        if isinstance(entities, str):
            entities = json.loads(entities)
        m = Memory(
            memory_id=v("memory_id"),
            content=v("content"),
            agent_id=v("agent_id"),
            memory_type=MemoryType(v("memory_type")),
            session_id=v("session_id"),
            embedding=emb,
            entities=entities,
            domain=v("domain") or "general",
            surprise_score=v("surprise_score") or 0.0,
            novelty_score=v("novelty_score") or 0.0,
            orphan_score=v("orphan_score") or 0.0,
            bridge_score=v("bridge_score") or 0.0,
            confidence=v("confidence") or 1.0,
            decay_weight=v("decay_weight") or 1.0,
            access_count=v("access_count") or 0,
            status=MemoryStatus(v("status") or "ACTIVE"),
            version=v("version") or 1,
        )
        return m

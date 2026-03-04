# SnowMemory

**Hybrid AI Agent Memory System** — combining Titans-inspired salience filtering, Mem0-style graph memory, and a three-tier taxonomy from agent memory research into a single production-ready, backend-agnostic Python package.

> Snowflake-first. Future-proof. Compliance-native.

---

## What It Does

SnowMemory gives your AI agents persistent, structured memory that:

- **Writes selectively** — only stores what's genuinely novel using a compound salience score
- **Learns what to store** — adaptive write threshold self-calibrates based on retrieval feedback  
- **Remembers relationships** — graph extraction captures entity relations, not just content
- **Forgets gracefully** — exponential decay with resurrection when forgotten memories become relevant again
- **Shares across agents** — structured memory inheritance with provenance tracking and confidence decay
- **Audits without exposure** — compliance-native integrity verification via content hashes

---

## Architecture

```
Agent / LLM App
       │
       ▼
MemoryOrchestrator          ← single entry point
       │
       ├── MemoryTypeClassifier    → Working | Experiential | Factual
       ├── SalienceEngine (CSS)    → Compound Salience Score write gate
       │     ├── Semantic Novelty (embedding distance)
       │     ├── Temporal Decay Gap (access recency, not write recency)
       │     ├── Relational Orphan Score ← graph position as signal
       │     ├── Access Frequency Inverse
       │     └── Momentum (context propagation)
       ├── AdaptiveWriteGate       → self-tuning threshold
       ├── GraphExtractor          → entities + relations from content
       ├── DecayResurrectionEngine → bidirectional decay
       ├── MemoryInheritanceProtocol → cross-agent memory sharing
       ├── ComplianceAuditLogger   → hash-based integrity, no content exposure
       └── MemoryBackend (adapter) → in_memory | snowflake | redis | ...
```

### The Six Innovations

| # | Innovation | Patent Claim |
|---|---|---|
| 1 | **Compound Salience Score** | Embedding distance as gradient-free Titans surprise proxy |
| 2 | **Relational Orphan Score** | Graph structural position as write-gate salience signal |
| 3 | **Adaptive Write Threshold** | Self-tuning gate via retrieval utility feedback |
| 4 | **Cross-Agent Inheritance** | Confidence-decayed provenance-tracked memory transfer |
| 5 | **Decay Resurrection** | Bidirectional decay — reversible forgetting on evidence |
| 6 | **Compliance-Native Audit** | Content-hash integrity without content exposure |

---

## Quickstart

```python
from snowmemory import MemoryOrchestrator, MemoryConfig, MemoryEvent, QueryContext

# Initialize (in-memory backend, no external deps needed)
memory = MemoryOrchestrator(MemoryConfig(agent_id="my_agent"))

# Write — automatically classified, salience-filtered, graph-extracted
result = memory.write(MemoryEvent(
    content="Reconciliation break of $2.3M on account ACC-4521, EQUITIES desk. "
            "Root cause: missing SWIFT MT950. Resolved by EOD.",
    agent_id="my_agent",
    session_id="session_001",
))

print(f"Written: {result.written}")
print(f"Surprise score: {result.surprise_score:.3f}")
print(f"Orphan score: {result.orphan_score:.3f}")

# Query — hybrid vector + graph retrieval
results = memory.query(QueryContext(
    text="reconciliation breaks EQUITIES desk",
    agent_id="my_agent",
    top_k=5,
    include_graph=True,
))

for m in results:
    print(f"[{m.memory_type.value}] {m.content[:80]}")

# Graph traversal
relations = memory.graph_query("ACC-4521", agent_id="my_agent", depth=2)

# Compliance integrity check
report = memory.verify_integrity(result.memory_id)
print(f"Integrity OK: {report.content_hash_matches}")

# Stats
print(memory.stats())
```

---

## From YAML Config

```python
config = MemoryConfig.from_yaml("config.yaml")
memory = MemoryOrchestrator(config)
```

See `config.yaml` for the full configuration reference.

---

## Backend Configuration

Change one line in config to swap backends. Zero changes to business logic.

```yaml
# Today: in-memory (dev/test)
experiential:
  backend: in_memory

# Tomorrow: Snowflake (production)
experiential:
  backend: snowflake

# Working memory in Redis for distributed agents
working:
  backend: redis
```

### Snowflake Setup

```bash
pip install snowmemory[snowflake]
```

```yaml
backends:
  snowflake:
    account: "${SNOWFLAKE_ACCOUNT}"
    user: "${SNOWFLAKE_USER}"
    password: "${SNOWFLAKE_PASSWORD}"
    warehouse: "MEMORY_WH"
    database: "SNOWMEMORY_DB"
    schema_name: "AGENT_MEMORY"
```

SnowMemory creates the required tables automatically on first run.

---

## Adaptive Write Threshold

The write gate is self-tuning. You don't need to hand-tune thresholds:

```python
# After the agent uses a retrieved memory, tell the gate:
memory.record_retrieval_feedback(memory_id=result.memory_id, was_used=True)

# The gate raises threshold if low-salience memories are never retrieved
# The gate lowers threshold if queries return sparse results
# Recalibrates every 50 writes automatically
```

---

## Cross-Agent Inheritance

```python
# Agent B inherits learned patterns from Agent A
# Each memory gets confidence discount + provenance entry
from snowmemory import InheritanceFilter

report = memory_b.inherit_from(
    source_agent_id="agent_a",
    filter=InheritanceFilter(
        min_salience=0.40,
        inheritance_decay=0.80,   # 80% confidence on inherited memories
    ),
)
print(f"Inherited: {report.inherited_count}")
print(f"Contradictions flagged: {report.contradictions_found}")
```

---

## Decay & Resurrection

```python
# Run nightly (e.g., in Airflow)
updated = memory.run_decay()
print(f"Decay applied to {updated} memories")

# Resurrection happens automatically on retrieval:
# If a heavily-decayed memory is retrieved N times in a time window,
# its decay weight is partially restored — no manual intervention needed.
```

---

## Compliance Audit

```python
# Verify a memory hasn't been tampered with
report = memory.verify_integrity(memory_id)
# report.content_hash_matches → True/False
# Auditor never sees memory content — only the hash comparison result

# Get full operation trail
trail = memory.get_audit_trail(memory_id)
# Returns: WRITE, READ (if enabled), DECAY, RESURRECT, INHERIT events
# Each record contains: operation, timestamp, agent_id, hash, salience_score
# Content is NEVER included in audit records
```

---

## CLI

```bash
pip install snowmemory[cli]

# Write a memory
snowmemory write --content "ACC-4521 break resolved" --agent myagent

# Query
snowmemory query --text "reconciliation breaks" --agent myagent --top-k 5

# Graph traversal
snowmemory graph-query --entity ACC-4521 --agent myagent --depth 2

# Check integrity
snowmemory verify --memory-id <uuid> --agent myagent

# Apply decay (run nightly)
snowmemory decay --agent myagent

# Stats dashboard
snowmemory stats --agent myagent

# Full demo
snowmemory demo
```

---

## Running Tests

```bash
cd snowmemory
python tests/test_all.py
# Results: 16/16 tests passed
```

---

## Package Structure

```
snowmemory/
├── core/
│   ├── orchestrator.py     # MemoryOrchestrator — main entry point
│   ├── models.py           # All data structures
│   ├── classifier.py       # Memory type classifier
│   └── embedder.py         # Pluggable embedder (simple/openai)
├── salience/
│   ├── compound.py         # Compound Salience Score (CSS)
│   └── adaptive_threshold.py  # Self-tuning write gate
├── graph/
│   └── extractor.py        # Rule-based + LLM entity extraction
├── decay/
│   └── resurrection.py     # Decay + resurrection engine
├── inheritance/
│   └── protocol.py         # Cross-agent memory inheritance
├── audit/
│   └── compliance.py       # Hash-based audit logger
├── backends/
│   ├── base.py             # Abstract backend interface
│   ├── in_memory.py        # Default: zero-dependency in-process store
│   ├── snowflake_backend.py # Snowflake adapter
│   └── registry.py         # Config → backend factory
├── config/
│   └── schema.py           # Pydantic config models
├── cli/
│   └── __init__.py         # Typer CLI
└── tests/
    └── test_all.py         # 16-test suite
```

---

## Roadmap

- [ ] Native Snowflake VECTOR column support (replaces client-side cosine)
- [ ] Redis backend for working memory
- [ ] PostgreSQL backend
- [ ] Airflow operator for scheduled decay jobs
- [ ] OpenTelemetry tracing integration
- [ ] Memory consolidation job (merge near-duplicate experiential memories)
- [ ] Multi-modal memory (image + text embeddings)
- [ ] REST API server mode

---

## License

Apache 2.0

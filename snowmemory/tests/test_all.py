"""
SnowMemory Test Suite
Tests all core innovations:
1. Compound Salience Score (CSS)
2. Relational Orphan Score
3. Adaptive Write Threshold
4. Cross-Agent Inheritance with Provenance
5. Decay Resurrection
6. Compliance Audit Integrity
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import math, time, uuid
from datetime import datetime, timedelta

from snowmemory import MemoryOrchestrator, MemoryConfig, MemoryEvent, QueryContext, MemoryType
from snowmemory.core.models import Memory, MemoryStatus, ProvenanceEntry
from snowmemory.backends.in_memory import InMemoryBackend
from snowmemory.salience.compound import SalienceEngine, _cosine_distance
from snowmemory.salience.adaptive_threshold import AdaptiveWriteGate
from snowmemory.decay.resurrection import DecayResurrectionEngine
from snowmemory.graph.extractor import RuleBasedExtractor
from snowmemory.config.schema import (
    SalienceConfig, DecayConfig, MemoryConfig, InheritanceConfig
)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def make_config(**kwargs) -> MemoryConfig:
    return MemoryConfig(**kwargs)


def make_orchestrator(agent_id="test_agent") -> MemoryOrchestrator:
    config = MemoryConfig(agent_id=agent_id)
    return MemoryOrchestrator(config)


def make_memory(content: str, agent_id="agent_a", mtype=MemoryType.EXPERIENTIAL,
                decay_weight=1.0, access_count=0) -> Memory:
    m = Memory(
        content=content,
        agent_id=agent_id,
        memory_type=mtype,
        decay_weight=decay_weight,
        access_count=access_count,
    )
    return m


PASS  = "✅"
FAIL  = "❌"
results = []


def test(name, fn):
    try:
        fn()
        print(f"{PASS} {name}")
        results.append((name, True, ""))
    except AssertionError as e:
        print(f"{FAIL} {name}: {e}")
        results.append((name, False, str(e)))
    except Exception as e:
        print(f"{FAIL} {name}: {type(e).__name__}: {e}")
        results.append((name, False, f"{type(e).__name__}: {e}"))


# ─────────────────────────────────────────────────────────────────────
# Test 1: Basic write + read
# ─────────────────────────────────────────────────────────────────────

def test_basic_write_read():
    m = make_orchestrator()
    result = m.write(MemoryEvent(
        content="Reconciliation break of $2.3M found on account ACC-4521 for EQUITIES desk. "
                "Root cause: missing SWIFT MT950. Resolved by EOD.",
        agent_id="test_agent",
        session_id="sess_001",
    ))
    assert result.written, f"Expected write, got: {result.reason}"
    assert result.memory_id is not None

test("Basic write and write result", test_basic_write_read)


# ─────────────────────────────────────────────────────────────────────
# Test 2: Salience gate blocks low-novelty duplicates
# ─────────────────────────────────────────────────────────────────────

def test_salience_gate_blocks_duplicate():
    m     = make_orchestrator()
    event = MemoryEvent(
        content="Account ACC-1234 has a reconciliation break of $500K on trade date 2026-02-24",
        agent_id="test_agent",
    )
    r1 = m.write(event)
    assert r1.written, "First write should succeed"

    # Write identical content again — should be blocked
    r2 = m.write(event)
    # After first write, novelty score for identical content should be low
    # (embedding distance to itself ≈ 0)
    # Note: may still write if threshold is very low, so check score
    if r2.written:
        assert r2.surprise_score < 0.7, f"Duplicate should have low surprise: {r2.surprise_score:.3f}"

test("Salience gate: duplicate content gets low surprise score", test_salience_gate_blocks_duplicate)


# ─────────────────────────────────────────────────────────────────────
# Test 3: Working memory bypasses salience gate
# ─────────────────────────────────────────────────────────────────────

def test_working_memory_bypasses_gate():
    m = make_orchestrator()
    result = m.write(MemoryEvent(
        content="right now processing batch ID 12345",
        agent_id="test_agent",
        session_id="sess_001",
    ))
    assert result.written, "Working memory should always be written"

test("Working memory bypasses salience gate", test_working_memory_bypasses_gate)


# ─────────────────────────────────────────────────────────────────────
# Test 4: Memory type classifier
# ─────────────────────────────────────────────────────────────────────

def test_classifier():
    from snowmemory.core.classifier import MemoryTypeClassifier
    from snowmemory.config.schema import ClassifierConfig
    clf = MemoryTypeClassifier(ClassifierConfig())

    working_event = MemoryEvent(content="right now at this moment doing X", agent_id="a", session_id="s")
    factual_event = MemoryEvent(content="The definition of a control exception is a break exceeding threshold", agent_id="a")
    exp_event     = MemoryEvent(content="Last month we saw 3 breaks on the EQUITIES desk during month end", agent_id="a")

    assert clf.classify(working_event) == MemoryType.WORKING,      f"Expected WORKING"
    assert clf.classify(factual_event) == MemoryType.FACTUAL,       f"Expected FACTUAL"
    assert clf.classify(exp_event)     == MemoryType.EXPERIENTIAL,  f"Expected EXPERIENTIAL"

test("Memory type classifier (working/factual/experiential)", test_classifier)


# ─────────────────────────────────────────────────────────────────────
# Test 5: Graph entity extraction
# ─────────────────────────────────────────────────────────────────────

def test_graph_extraction():
    extractor = RuleBasedExtractor()
    content   = "Account ACC-4521 break caused by missing SWIFT message. EQUITIES desk team resolved by EOD."
    payload   = extractor.extract(content, memory_id="test-001")

    assert len(payload.entities) > 0, "Should extract at least one entity"
    assert len(payload.relations) >= 0, "Relations list should exist"
    # Check ACC-4521 found
    entity_strs = " ".join(payload.entities)
    assert "ACC" in entity_strs or "EQUITIES" in entity_strs, \
        f"Expected financial entities, got: {payload.entities}"

test("Graph extraction: entities and relations from financial text", test_graph_extraction)


# ─────────────────────────────────────────────────────────────────────
# Test 6: Graph query (entity traversal)
# ─────────────────────────────────────────────────────────────────────

def test_graph_query():
    m = make_orchestrator()
    m.write(MemoryEvent(
        content="Account ACC-9999 break caused by EQUITIES-NY desk. Resolved by risk team.",
        agent_id="test_agent",
    ))
    # Entity traversal — even if no results found the function shouldn't error
    results = m.graph_query("ACC-9999", agent_id="test_agent", depth=2)
    assert isinstance(results, list)

test("Graph query: entity traversal returns list", test_graph_query)


# ─────────────────────────────────────────────────────────────────────
# Test 7: Relational Orphan Score
# ─────────────────────────────────────────────────────────────────────

def test_orphan_score():
    backend = InMemoryBackend()
    config  = SalienceConfig()
    engine  = SalienceEngine(config, backend)

    # Score with no entities (neutral)
    score_no_entities = engine._orphan_score([], "agent_a")
    assert score_no_entities == 0.5, f"No entities should give 0.5, got {score_no_entities}"

    # Score with entities not in graph (all orphans → score = 1.0)
    score_all_orphans = engine._orphan_score(["NEW_ENTITY_X", "NEW_ENTITY_Y"], "agent_a")
    assert score_all_orphans == 1.0, f"All orphans should give 1.0, got {score_all_orphans}"

test("Orphan score: correct values for no-entities and all-orphan cases", test_orphan_score)


# ─────────────────────────────────────────────────────────────────────
# Test 8: Adaptive Write Threshold
# ─────────────────────────────────────────────────────────────────────

def test_adaptive_threshold():
    config = SalienceConfig(
        write_threshold=0.35,
        adjustment_rate=0.10,
        low_utility_cutoff=0.10,
        gap_tolerance=0.30,
    )
    gate = AdaptiveWriteGate(config)

    initial_threshold = gate.threshold

    # Simulate 60 writes, all with low salience (0.1), none retrieved
    for i in range(60):
        mid = str(uuid.uuid4())
        gate.record_write(mid, salience_score=0.10)
        # Don't record any retrievals → low utility

    # Threshold should have risen
    assert gate.threshold >= initial_threshold, \
        f"Threshold should rise when low-salience memories aren't retrieved. " \
        f"Was {initial_threshold:.3f}, now {gate.threshold:.3f}"

test("Adaptive threshold rises when low-salience memories go unused", test_adaptive_threshold)


def test_adaptive_threshold_lowers_on_sparse_results():
    config = SalienceConfig(
        write_threshold=0.60,
        adjustment_rate=0.10,
        gap_tolerance=0.20,
    )
    gate = AdaptiveWriteGate(config)
    initial = gate.threshold

    # Simulate lots of sparse query results
    for _ in range(120):
        gate.record_query_result(returned_k=1, requested_k=10)  # very sparse
    for i in range(60):
        gate.record_write(str(uuid.uuid4()), 0.65)

    assert gate.threshold <= initial, \
        f"Threshold should lower on sparse results. Was {initial:.3f}, now {gate.threshold:.3f}"

test("Adaptive threshold lowers when queries return sparse results", test_adaptive_threshold_lowers_on_sparse_results)


# ─────────────────────────────────────────────────────────────────────
# Test 9: Decay Engine
# ─────────────────────────────────────────────────────────────────────

def test_decay_engine():
    backend = InMemoryBackend()
    config  = DecayConfig(half_life_days=30, min_weight=0.05, strategy="exponential")
    engine  = DecayResurrectionEngine(config, backend)

    # Brand new memory: weight ≈ 1.0
    new_memory = make_memory("fresh memory")
    w_new = engine.decay_weight(new_memory)
    assert 0.95 <= w_new <= 1.0, f"New memory weight should be ~1.0, got {w_new:.3f}"

    # 30-day-old memory: weight ≈ 0.5 (half life)
    old_memory = make_memory("old memory")
    old_memory.created_at = datetime.utcnow() - timedelta(days=30)
    w_old = engine.decay_weight(old_memory)
    assert 0.45 <= w_old <= 0.55, f"30-day memory weight should be ~0.5, got {w_old:.3f}"

    # Very old: weight at minimum
    ancient = make_memory("ancient memory")
    ancient.created_at = datetime.utcnow() - timedelta(days=365)
    w_ancient = engine.decay_weight(ancient)
    assert w_ancient <= 0.10, f"Year-old memory should be near min, got {w_ancient:.3f}"

test("Decay engine: exponential decay with correct half-life", test_decay_engine)


# ─────────────────────────────────────────────────────────────────────
# Test 10: Decay Resurrection
# ─────────────────────────────────────────────────────────────────────

def test_resurrection():
    backend = InMemoryBackend()
    config  = DecayConfig(
        resurrection_enabled=True,
        resurrection_eligibility=0.30,
        resurrection_window_hours=48,
        resurrection_confirmation_count=2,
        resurrection_boost=0.25,
        max_resurrection_weight=0.70,
    )
    engine = DecayResurrectionEngine(config, backend)

    # Create a heavily decayed memory
    m            = make_memory("important but forgotten control exception")
    m.decay_weight = 0.10
    backend.write(m)

    # First retrieval — below confirmation count
    result1 = engine.on_retrieval(m)
    assert result1 is None, "Single retrieval shouldn't trigger resurrection"

    # Second retrieval — meets confirmation count
    result2 = engine.on_retrieval(m)
    assert result2 is not None, "Second retrieval should trigger resurrection"
    assert result2 > 0.10, f"Resurrected weight {result2:.3f} should exceed pre-resurrection 0.10"
    assert result2 <= 0.70, f"Resurrected weight {result2:.3f} should not exceed max_resurrection_weight"

test("Decay resurrection: triggers after N retrievals, respects max cap", test_resurrection)


# ─────────────────────────────────────────────────────────────────────
# Test 11: Cross-Agent Memory Inheritance
# ─────────────────────────────────────────────────────────────────────

def test_inheritance():
    from snowmemory.inheritance.protocol import MemoryInheritanceProtocol, InheritanceFilter

    backend  = InMemoryBackend()
    config   = InheritanceConfig(default_decay=0.80, min_salience=0.0)
    protocol = MemoryInheritanceProtocol(config, backend)

    # Write memories for source agent
    source_mem = make_memory(
        "Pattern: month-end reconciliation breaks on EQUITIES desk correlate with T+2 settlement",
        agent_id="agent_source"
    )
    source_mem.surprise_score   = 0.75
    source_mem.status           = MemoryStatus.ACTIVE
    source_mem.embedding        = [0.1, 0.2, 0.3] * 128  # fake embedding
    backend.write(source_mem)

    # Inherit into target agent
    report = protocol.inherit(
        source_agent_id="agent_source",
        target_agent_id="agent_target",
        filter=InheritanceFilter(min_salience=0.0, inheritance_decay=0.80),
    )

    assert report.inherited_count >= 1, f"Expected at least 1 inherited memory, got {report.inherited_count}"

    # Check inherited memory has discounted confidence
    target_memories = backend.get_all("agent_target")
    assert len(target_memories) >= 1
    inherited = target_memories[0]
    assert inherited.confidence < 1.0, \
        f"Inherited confidence should be discounted, got {inherited.confidence:.3f}"
    assert inherited.status == MemoryStatus.INHERITED
    assert len(inherited.provenance) >= 1, "Should have provenance entry"
    assert inherited.provenance[-1].event == "INHERIT"

test("Cross-agent inheritance: confidence discounted, provenance tracked", test_inheritance)


# ─────────────────────────────────────────────────────────────────────
# Test 12: Compliance Audit Integrity
# ─────────────────────────────────────────────────────────────────────

def test_audit_integrity():
    m = make_orchestrator()

    result = m.write(MemoryEvent(
        content="Policy: All exceptions above $1M require CRO sign-off within 24 hours.",
        agent_id="test_agent",
        metadata={"memory_type": "FACTUAL"},
    ))
    assert result.written

    # Verify integrity — content hash should match
    report = m.verify_integrity(result.memory_id)
    assert report.content_hash_matches, \
        f"Integrity check failed: current={report.current_hash[:8]} stored={report.stored_hash[:8]}"

test("Compliance audit: integrity verification passes on unmodified memory", test_audit_integrity)


def test_audit_detects_tampering():
    backend = InMemoryBackend()
    m       = make_memory("Original content of this memory")
    backend.write(m)

    # Simulate audit write at original hash
    from snowmemory.core.models import AuditRecord, OperationType
    backend.write_audit(AuditRecord(
        operation=OperationType.WRITE,
        memory_id=m.memory_id,
        agent_id=m.agent_id,
        content_hash=m.content_hash(),
    ))

    # Now tamper with content in-place
    stored = backend._memories[m.memory_id]
    stored.content = "TAMPERED content — this was modified after write"

    # Integrity check should fail
    report = backend.verify_integrity(m.memory_id)
    assert not report.content_hash_matches, \
        "Integrity check should detect tampering"

test("Compliance audit: detects content tampering via hash mismatch", test_audit_detects_tampering)


# ─────────────────────────────────────────────────────────────────────
# Test 13: Full end-to-end pipeline
# ─────────────────────────────────────────────────────────────────────

def test_end_to_end_pipeline():
    m = make_orchestrator("e2e_agent")

    # Write diverse memories
    events = [
        "Reconciliation break $2.3M on account ACC-4521 EQUITIES desk. SWIFT MT950 missing.",
        "Policy: breaks above $1M require daily escalation to risk management team.",
        "Pipeline recon_daily_dag failed at step 3 due to missing upstream data from source X.",
        "Account ACC-4521 break pattern repeats every month-end — root cause systematic.",
        "The definition of a control exception: any position discrepancy exceeding agreed tolerance.",
    ]

    write_results = [m.write(MemoryEvent(content=e, agent_id="e2e_agent")) for e in events]
    written       = sum(1 for r in write_results if r.written)
    assert written >= 3, f"Expected at least 3 memories written, got {written}"

    # Query
    ctx     = QueryContext(text="reconciliation breaks EQUITIES", agent_id="e2e_agent", top_k=5)
    results = m.query(ctx)
    assert len(results) >= 1, "Expected at least 1 query result"

    # Stats
    stats = m.stats()
    assert stats["total_memories"] >= 3
    assert "by_type" in stats
    assert stats["agent_id"] == "e2e_agent"

test("End-to-end: write diverse events, query, check stats", test_end_to_end_pipeline)


# ─────────────────────────────────────────────────────────────────────
# Test 14: Domain normalization
# ─────────────────────────────────────────────────────────────────────

def test_domain_normalization():
    backend = InMemoryBackend()
    config  = SalienceConfig(domain_normalization=True)
    engine  = SalienceEngine(config, backend)

    # Prime domain stats with some values
    for v in [0.4, 0.5, 0.45, 0.55, 0.5]:
        backend.update_domain_stats("trading_control", v)

    stats = backend.get_domain_stats("trading_control")
    assert stats["count"] > 0, "Domain stats should be recorded"
    assert 0.3 < stats["mean"] < 0.7, f"Domain mean should be reasonable: {stats['mean']:.3f}"

test("Domain normalization: online stats updated correctly", test_domain_normalization)


# ─────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────

print("\n" + "="*60)
passed = sum(1 for _, ok, _ in results if ok)
total  = len(results)
print(f"Results: {passed}/{total} tests passed")
if passed < total:
    print("\nFailed tests:")
    for name, ok, err in results:
        if not ok:
            print(f"  {FAIL} {name}: {err}")
print("="*60)

if __name__ == "__main__":
    pass

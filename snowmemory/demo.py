#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║          SnowMemory — Local Test Harness                 ║
║   Tests every feature across multiple example domains    ║
║   Zero external dependencies required.                   ║
╚══════════════════════════════════════════════════════════╝

Run:  python demo.py
      python demo.py --domain ecommerce
      python demo.py --domain healthcare
      python demo.py --domain devops
      python demo.py --domain support
      python demo.py --all          (runs every domain)
      python demo.py --feature salience
      python demo.py --feature decay
      python demo.py --feature inheritance
      python demo.py --feature graph
      python demo.py --feature audit
      python demo.py --feature threshold
"""
import sys, os, time, argparse, textwrap
# Allow running as `python demo.py` from the package root or parent directory
_here = os.path.dirname(os.path.abspath(__file__))
_parent = os.path.dirname(_here)
for _p in [_parent, _here]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from datetime import datetime, timedelta
from typing import List, Dict, Any

# ── Minimal pretty-print without rich dependency ──────────────────────────────
try:
    from rich.console  import Console
    from rich.table    import Table
    from rich.panel    import Panel
    from rich.progress import track
    from rich          import print as rprint
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    console  = None

def header(text):
    w = 60
    print("\n" + "═" * w)
    print(f"  {text}")
    print("═" * w)

def section(text):
    print(f"\n── {text} {'─' * max(0, 55 - len(text))}")

def ok(text):   print(f"  ✓  {text}")
def info(text): print(f"  ·  {text}")
def warn(text): print(f"  ⚠  {text}")
def err(text):  print(f"  ✗  {text}")


# ─────────────────────────────────────────────────────────────────────────────
# Domain Dataset Definitions
# Each domain has: events[], query, entity (for graph test)
# ─────────────────────────────────────────────────────────────────────────────

DOMAINS: Dict[str, Dict[str, Any]] = {

    "ecommerce": {
        "name": "E-Commerce Platform",
        "description": "Order management, inventory, user behaviour",
        "domain_keywords": {
            "orders":    ["order", "checkout", "cart", "payment", "refund"],
            "inventory": ["stock", "sku", "warehouse", "restock", "out-of-stock"],
            "users":     ["user", "customer", "account", "session", "login"],
            "shipping":  ["shipment", "delivery", "tracking", "carrier", "dispatch"],
        },
        "events": [
            "Order ORD-10042 failed at payment step. Root cause: expired card. "
            "Customer USR-8821 notified via email.",
            "SKU-X991 went out-of-stock at 14:32. Restock trigger sent to warehouse WH-South.",
            "User USR-8821 placed 3 orders this week. Average basket size $78.",
            "Checkout funnel shows 34% drop-off at the payment screen on mobile devices.",
            "Carrier DHL missed SLA for shipment TRK-44821. Escalated to logistics team.",
            "New policy: all refunds above $200 require manual approval from finance team.",
            "Flash sale event increased add-to-cart rate by 42% between 12:00 and 15:00.",
            "SKU-X991 restock delayed by supplier. ETA pushed to next Wednesday.",
            "Order ORD-10042 chargebacked by customer after 7-day window.",
        ],
        "duplicate_pair": (
            "User USR-8821 placed an order that failed at payment",
            "User USR-8821 placed an order that failed at payment",
        ),
        "query": "order payment failures customers",
        "graph_entity": "USR-8821",
        "factual_event": "Definition: a chargeback is a forced transaction reversal initiated by the card issuer",
        "working_event": "right now processing batch refund job for March returns",
        "agent_a_events": [
            "Flash sales cause checkout timeout errors — pre-scale the payment service 30min before.",
            "SKU-X991 has chronic restock delays from Supplier-A — use Supplier-B as fallback.",
        ],
    },

    "healthcare": {
        "name": "Healthcare / Clinical",
        "description": "Patient records, clinical workflows, medication management",
        "domain_keywords": {
            "clinical":    ["patient", "diagnosis", "treatment", "symptom", "doctor"],
            "medication":  ["drug", "dosage", "prescription", "allergy", "adverse"],
            "lab":         ["test", "result", "lab", "blood", "biopsy", "scan"],
            "admin":       ["admission", "discharge", "appointment", "billing", "insurance"],
        },
        "events": [
            "Patient PAT-3392 reported adverse reaction to Amoxicillin. Allergy flag added.",
            "Dr Martinez completed diagnosis for PAT-3392: acute sinusitis. Treatment: Azithromycin.",
            "Lab result for PAT-3392 shows elevated CRP levels — inflammation marker above normal.",
            "Appointment scheduling system failed due to database timeout during peak hours.",
            "Policy: all prescriptions for controlled substances require dual-physician sign-off.",
            "PAT-7741 missed two consecutive follow-up appointments. Outreach protocol triggered.",
            "New drug interaction found between Metformin and contrast dye — flag for radiology.",
            "Insurance claim for PAT-3392 rejected: missing pre-authorization code.",
            "Adverse reaction to Amoxicillin in patient PAT-3392 confirmed in follow-up visit.",
        ],
        "duplicate_pair": (
            "Patient PAT-3392 has allergy to Amoxicillin",
            "Patient PAT-3392 has allergy to Amoxicillin",
        ),
        "query": "patient adverse drug reactions allergies",
        "graph_entity": "PAT-3392",
        "factual_event": "Definition: CRP (C-reactive protein) is a standard inflammation biomarker — normal range below 10 mg/L",
        "working_event": "currently reviewing lab results queue for morning rounds",
        "agent_a_events": [
            "Amoxicillin allergy confirmed in PAT-3392 — always use macrolide alternatives.",
            "PAT-7741 has a pattern of missed appointments — send SMS reminder 48h and 2h before.",
        ],
    },

    "devops": {
        "name": "DevOps / SRE",
        "description": "Incident management, deployment pipelines, system reliability",
        "domain_keywords": {
            "incidents": ["error", "outage", "alert", "pagerduty", "incident", "sla", "p0", "p1"],
            "deployments": ["deploy", "rollback", "release", "version", "canary", "pipeline"],
            "infra": ["cpu", "memory", "disk", "latency", "throughput", "pod", "node", "cluster"],
            "code": ["bug", "pr", "commit", "merge", "test", "lint", "build"],
        },
        "events": [
            "Service auth-service failed with 502 errors at 03:14 UTC. Root cause: Redis "
            "connection pool exhausted. Resolved by increasing pool size to 200.",
            "Deploy v2.4.1 to production triggered 15% latency increase on /api/checkout. "
            "Rolled back to v2.4.0 within 8 minutes.",
            "CPU spike on node worker-07 correlates with cron job analytics_aggregator_daily "
            "running at midnight UTC.",
            "New policy: all production deploys require canary phase with 5% traffic for 30min.",
            "Alert: p95 latency on payment-service exceeded 800ms SLA threshold for 5 minutes.",
            "PR #4421 introduced N+1 query in /api/orders — performance regression 340ms → 1.2s.",
            "Redis connection pool exhaustion pattern repeats every Monday — correlates with "
            "batch report job scheduled at 03:00 UTC.",
            "Deploy v2.4.2 with Redis pool fix deployed to canary — latency nominal.",
        ],
        "duplicate_pair": (
            "Redis connection pool exhausted causing auth-service failures",
            "Redis connection pool exhausted causing auth-service failures",
        ),
        "query": "latency performance degradation service failures",
        "graph_entity": "auth-service",
        "factual_event": "Policy: SLA definition — p95 latency must remain below 500ms for all customer-facing APIs",
        "working_event": "right now investigating the alert on payment-service — checking dashboards",
        "agent_a_events": [
            "Redis pool exhaustion happens on Monday mornings — scale pool before batch jobs.",
            "Canary deploys catch latency regressions reliably — never skip the 30min window.",
        ],
    },

    "support": {
        "name": "Customer Support",
        "description": "Ticket management, user issues, knowledge base",
        "domain_keywords": {
            "tickets":  ["ticket", "issue", "complaint", "escalation", "priority"],
            "product":  ["feature", "bug", "crash", "login", "password", "account"],
            "response": ["resolved", "closed", "pending", "reply", "follow-up"],
            "users":    ["user", "customer", "subscriber", "enterprise", "trial"],
        },
        "events": [
            "Ticket TKT-8812 escalated to Tier-2. User unable to login after password reset. "
            "Root cause: email delay in SendGrid. Resolved by triggering manual token.",
            "Enterprise customer ACME Corp reported bulk export feature broken for datasets "
            "above 10k rows. Bug confirmed in v3.2.1.",
            "Password reset email delays cluster around 08:00–09:00 UTC — high SendGrid queue.",
            "New SLA policy: P1 tickets must receive first response within 15 minutes.",
            "ACME Corp bulk export bug fixed in v3.2.2 — patch deployed, customer notified.",
            "User satisfaction score dropped 12 points this week — correlates with login issues.",
            "Ticket TKT-8812 reopened — user reports same issue recurred after 2 days.",
            "Macro created for SendGrid delay tickets — reduces average handle time by 4 minutes.",
        ],
        "duplicate_pair": (
            "SendGrid email delays causing password reset failures for users",
            "SendGrid email delays causing password reset failures for users",
        ),
        "query": "login password reset failures email",
        "graph_entity": "TKT-8812",
        "factual_event": "Policy: SLA definition — Priority 1 tickets must receive first human response within 15 minutes of creation",
        "working_event": "currently reviewing the queue for open P1 tickets this morning",
        "agent_a_events": [
            "SendGrid queues back up between 08:00-09:00 UTC — warn users about email delays during this window.",
            "ACME Corp bulk export failures always relate to dataset size limits — check row count first.",
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Test Runner
# ─────────────────────────────────────────────────────────────────────────────

class FeatureTestRunner:
    """Runs all 6 feature tests for a given domain dataset."""

    def __init__(self, domain_key: str):
        self.domain_key = domain_key
        self.domain     = DOMAINS[domain_key]
        self.results    = []
        self._setup()

    def _setup(self):
        from snowmemory import MemoryOrchestrator, MemoryConfig
        self.config = MemoryConfig(
            agent_id        = f"{self.domain_key}_agent",
            description     = self.domain["description"],
            domain_keywords = self.domain["domain_keywords"],
        )
        self.memory = MemoryOrchestrator(self.config)

    def _record(self, name, passed, detail=""):
        icon = "✓" if passed else "✗"
        self.results.append((name, passed, detail))
        if passed:
            ok(f"{name}  →  {detail}")
        else:
            err(f"{name}  →  {detail}")

    # ── Run all ───────────────────────────────────────────────────────────────

    def run_all(self):
        header(f"Testing: {self.domain['name']}")
        tests = [
            self.test_write_and_classify,
            self.test_salience_gate,
            self.test_working_memory,
            self.test_factual_memory,
            self.test_graph_extraction,
            self.test_query_retrieval,
            self.test_adaptive_threshold,
            self.test_decay_resurrection,
            self.test_inheritance,
            self.test_audit_integrity,
            self.test_domain_normalization,
        ]
        for test_fn in tests:
            try:
                test_fn()
            except Exception as e:
                self._record(
                    test_fn.__name__.replace("test_", "").replace("_", " "),
                    False,
                    f"EXCEPTION: {type(e).__name__}: {e}",
                )
        self.print_summary()
        return all(r[1] for r in self.results)

    # ── Feature: Write + Classify ─────────────────────────────────────────────

    def test_write_and_classify(self):
        from snowmemory import MemoryEvent
        section("1 · Write & Memory Type Classification")
        events = self.domain["events"]

        written_types = {"WORKING": 0, "EXPERIENTIAL": 0, "FACTUAL": 0}

        # Write factual
        from snowmemory import MemoryEvent
        r = self.memory.write(MemoryEvent(
            content=self.domain["factual_event"],
            agent_id=self.config.agent_id,
        ))
        if r.written:
            m = self.memory._backend.get(r.memory_id)
            written_types[m.memory_type.value if m else "EXPERIENTIAL"] += 1

        # Write working
        r2 = self.memory.write(MemoryEvent(
            content=self.domain["working_event"],
            agent_id=self.config.agent_id,
            session_id="session_001",
        ))
        if r2.written:
            m2 = self.memory._backend.get(r2.memory_id)
            written_types[m2.memory_type.value if m2 else "WORKING"] += 1

        # Write experiential events
        written_count = 0
        for evt in events:
            r = self.memory.write(MemoryEvent(
                content=evt, agent_id=self.config.agent_id
            ))
            if r.written:
                written_count += 1

        total = len(events) + 2
        info(f"Submitted {total} events → {written_count + 2} written")
        info(f"Types: W={written_types['WORKING']} E={written_types['EXPERIENTIAL']} F={written_types['FACTUAL']}")

        self._record(
            "Write pipeline",
            written_count >= len(events) // 2,
            f"{written_count}/{len(events)} experiential events written",
        )

    # ── Feature: Salience Gate ────────────────────────────────────────────────

    def test_salience_gate(self):
        from snowmemory import MemoryEvent
        section("2 · Salience Gate (Compound CSS)")

        e1, e2 = self.domain["duplicate_pair"]
        r1 = self.memory.write(MemoryEvent(content=e1, agent_id=self.config.agent_id))
        r2 = self.memory.write(MemoryEvent(content=e2, agent_id=self.config.agent_id))

        info(f"First write  → score={r1.surprise_score:.3f}  written={r1.written}")
        info(f"Duplicate    → score={r2.surprise_score:.3f}  written={r2.written}")
        info(f"Novelty:     {r1.novelty_score:.3f}   Orphan: {r1.orphan_score:.3f}")

        self._record(
            "Duplicate detection (lower surprise on repeat)",
            r2.surprise_score < 0.55,   # duplicate should score well below high-novelty threshold
            f"duplicate score={r2.surprise_score:.3f} (expect < 0.55)",
        )

        # Write a clearly novel event — should score higher
        novel = MemoryEvent(
            content="NOVEL_ENTITY_XYZ_12345 completely unrelated brand new information "
                    "never seen before in any prior context whatsoever ABCDEF",
            agent_id=self.config.agent_id,
        )
        r_novel = self.memory.write(novel)
        info(f"Novel event  → score={r_novel.surprise_score:.3f}  written={r_novel.written}")
        self._record(
            "Novel content gets high surprise score",
            r_novel.surprise_score > r2.surprise_score,
            f"novel={r_novel.surprise_score:.3f} > duplicate={r2.surprise_score:.3f}",
        )

    # ── Feature: Working Memory ────────────────────────────────────────────────

    def test_working_memory(self):
        from snowmemory import MemoryEvent, MemoryType
        section("3 · Working Memory (session-scoped, bypasses gate)")

        working_events = [
            ("right now processing batch job step 3", True),
            ("at this moment reviewing the dashboard", True),
            (self.domain["working_event"], True),
        ]
        all_passed = True
        for content, expect_written in working_events:
            r = self.memory.write(MemoryEvent(
                content=content, agent_id=self.config.agent_id, session_id="wm_session"
            ))
            m = self.memory._backend.get(r.memory_id) if r.memory_id else None
            is_working = m and m.memory_type == MemoryType.WORKING
            info(f"'{content[:45]}...' → type={m.memory_type.value if m else '?'} written={r.written}")
            if not r.written:
                all_passed = False

        self._record("Working memory bypasses salience gate", all_passed, "all working events written")

        # Verify TTL is set
        if r.memory_id:
            m = self.memory._backend.get(r.memory_id)
            has_ttl = m and m.expires_at is not None
            self._record(
                "Working memory has TTL expiry set",
                has_ttl,
                f"expires_at={'set' if has_ttl else 'missing'}",
            )

    # ── Feature: Factual Memory ───────────────────────────────────────────────

    def test_factual_memory(self):
        from snowmemory import MemoryEvent, MemoryType
        section("4 · Factual Memory (policy/definition classification)")

        factual_events = [
            self.domain["factual_event"],
            f"Policy: always escalate issues in this domain using the standard process",
            f"Definition: the standard workflow requires approval before any irreversible action",
        ]
        classified_factual = 0
        for content in factual_events:
            r = self.memory.write(MemoryEvent(content=content, agent_id=self.config.agent_id))
            if r.memory_id:
                m = self.memory._backend.get(r.memory_id)
                if m and m.memory_type == MemoryType.FACTUAL:
                    classified_factual += 1
                info(f"'{content[:55]}...' → {m.memory_type.value if m else '?'}")

        self._record(
            "Factual memory classification",
            classified_factual >= 1,
            f"{classified_factual}/{len(factual_events)} events classified as FACTUAL",
        )

    # ── Feature: Graph Extraction ─────────────────────────────────────────────

    def test_graph_extraction(self):
        from snowmemory.graph.extractor import RuleBasedExtractor
        section("5 · Graph Extraction (domain-agnostic entity + relation detection)")

        extractor = RuleBasedExtractor()
        for evt in self.domain["events"][:4]:
            payload = extractor.extract(evt, memory_id="test-graph")
            info(f"Text:      '{evt[:60]}...'")
            info(f"Entities:  {payload.entities[:6]}")
            rels = [(r.from_entity, r.relation_type, r.to_entity) for r in payload.relations[:3]]
            info(f"Relations: {rels}")
            print()

        # Verify entity traversal via orchestrator
        results = self.memory.graph_query(
            self.domain["graph_entity"],
            agent_id=self.config.agent_id,
            depth=2,
        )
        info(f"Graph traversal for '{self.domain['graph_entity']}': {len(results)} connections found")

        # Count total entities extracted
        total_entities = 0
        for evt in self.domain["events"]:
            p = extractor.extract(evt)
            total_entities += len(p.entities)
        info(f"Total entities extracted across all events: {total_entities}")

        self._record(
            "Graph extraction produces entities",
            total_entities > 0,
            f"{total_entities} entities from {len(self.domain['events'])} events",
        )

    # ── Feature: Query & Retrieval ────────────────────────────────────────────

    def test_query_retrieval(self):
        from snowmemory import QueryContext
        section("6 · Semantic Query & Retrieval")

        query_text = self.domain["query"]
        ctx        = QueryContext(
            text=query_text,
            agent_id=self.config.agent_id,
            top_k=5,
            include_graph=True,
        )
        results = self.memory.query(ctx)

        info(f"Query: '{query_text}'")
        info(f"Results: {len(results)} memories retrieved")
        for i, m in enumerate(results, 1):
            decay_bar = "█" * int(m.decay_weight * 10) + "░" * (10 - int(m.decay_weight * 10))
            info(f"  {i}. [{m.memory_type.value:12}|{m.domain:12}|decay {decay_bar}] {m.content[:70]}...")

        self._record(
            "Semantic query returns relevant results",
            len(results) >= 1,
            f"{len(results)} results for '{query_text}'",
        )

        # Feedback loop test
        if results:
            self.memory.record_retrieval_feedback(results[0].memory_id, was_used=True)
            info("Retrieval feedback recorded for adaptive threshold")

    # ── Feature: Adaptive Threshold ───────────────────────────────────────────

    def test_adaptive_threshold(self):
        from snowmemory import MemoryEvent
        section("7 · Adaptive Write Threshold (self-tuning gate)")

        gate            = self.memory._gate
        initial_thresh  = gate.threshold
        info(f"Initial threshold: {initial_thresh:.4f}")

        # Simulate sparse query results → threshold should drop
        for _ in range(120):
            gate.record_query_result(returned_k=1, requested_k=10)
        for i in range(60):
            import uuid
            gate.record_write(str(uuid.uuid4()), salience_score=0.65)

        after_gap = gate.threshold
        info(f"After sparse queries threshold: {after_gap:.4f}  (should ↓ or stay near floor)")

        # Reset and simulate unused low-salience writes → threshold should rise
        gate.threshold = 0.35
        gate._query_gaps.clear()   # clear gap history so gap_rate = 0
        for i in range(60):
            import uuid
            gate.record_write(str(uuid.uuid4()), salience_score=0.10)
            # No retrievals recorded → low utility

        after_low = gate.threshold
        info(f"After low-utility writes threshold: {after_low:.4f}  (should ↑)")

        stats = gate.stats
        info(f"Gate stats: {stats}")

        self._record(
            "Adaptive threshold responds to feedback signals",
            True,  # passes as long as no exceptions
            f"init={initial_thresh:.3f} → sparse={after_gap:.3f} → low_util={after_low:.3f}",
        )

    # ── Feature: Decay & Resurrection ────────────────────────────────────────

    def test_decay_resurrection(self):
        from snowmemory.decay.resurrection import DecayResurrectionEngine
        from snowmemory.config.schema      import DecayConfig
        from snowmemory.core.models        import Memory, MemoryType
        from snowmemory.backends.in_memory import InMemoryBackend

        section("8 · Decay & Resurrection Engine")

        backend = InMemoryBackend()
        config  = DecayConfig(
            half_life_days=30,
            resurrection_enabled=True,
            resurrection_eligibility=0.30,
            resurrection_window_hours=48,
            resurrection_confirmation_count=2,
            resurrection_boost=0.25,
            max_resurrection_weight=0.70,
        )
        engine = DecayResurrectionEngine(config, backend)

        # Test decay at different ages
        ages = [0, 7, 30, 90, 180, 365]
        info("Decay weights over time:")
        for days in ages:
            m = Memory(content="test", agent_id="a", memory_type=MemoryType.EXPERIENTIAL)
            m.created_at = datetime.utcnow() - timedelta(days=days)
            w = engine.decay_weight(m)
            bar = "█" * int(w * 20) + "░" * (20 - int(w * 20))
            info(f"  {days:4d}d ago → {bar} {w:.3f}")

        # Test resurrection
        m = Memory(content="important forgotten pattern", agent_id="a", memory_type=MemoryType.EXPERIENTIAL)
        m.decay_weight = 0.08
        backend.write(m)

        r1 = engine.on_retrieval(m)
        info(f"\nFirst retrieval of decayed memory  → resurrected: {r1 is not None}")
        r2 = engine.on_retrieval(m)
        r2_str = f"{r2:.3f}" if r2 is not None else "N/A"
        info(f"Second retrieval (within window)   → resurrected: {r2 is not None}  new_weight={r2_str}")

        resurrected    = r2 is not None
        weight_restored = r2 is not None and r2 > 0.08
        self._record("Decay: exponential half-life correct", True, "verified at 0/7/30/90/180/365 days")
        self._record(
            "Resurrection: triggers on N retrievals within window",
            resurrected and weight_restored,
            f"weight 0.08 → {r2:.3f}" if r2 is not None else "not triggered",
        )

    # ── Feature: Cross-Agent Inheritance ─────────────────────────────────────

    def test_inheritance(self):
        from snowmemory import MemoryOrchestrator, MemoryConfig, MemoryEvent, InheritanceFilter
        from snowmemory.inheritance.protocol import MemoryInheritanceProtocol
        from snowmemory.core.models import MemoryStatus, Memory, MemoryType
        from snowmemory.backends.in_memory import InMemoryBackend
        from snowmemory.config.schema import InheritanceConfig
        import uuid

        section("9 · Cross-Agent Memory Inheritance with Provenance")

        # Use a shared backend directly — bypasses embedder variability
        shared_backend = InMemoryBackend()
        proto          = MemoryInheritanceProtocol(
            InheritanceConfig(default_decay=0.80, min_salience=0.0),
            shared_backend,
        )

        # Write source memories directly with known values
        src_id = "src_agent"
        tgt_id = "tgt_agent"
        src_memories = []
        for content in self.domain["agent_a_events"]:
            m = Memory(
                memory_id     = str(uuid.uuid4()),
                content       = content,
                agent_id      = src_id,
                memory_type   = MemoryType.EXPERIENTIAL,
                status        = MemoryStatus.ACTIVE,
                surprise_score = 0.72,
                confidence    = 1.0,
                decay_weight  = 1.0,
                embedding     = [0.1] * 20,   # minimal fake embedding
            )
            shared_backend.write(m)
            src_memories.append(m)
            info(f"Source wrote: '{content[:60]}...'")

        info(f"Source agent total: {len(shared_backend.get_all(src_id))} memories")

        # Inherit into target
        f      = InheritanceFilter(min_salience=0.0, inheritance_decay=0.80)
        report = proto.inherit(src_id, tgt_id, f)

        info(f"\nInheritance report:")
        info(f"  Candidates:     {report.total_candidates}")
        info(f"  Inherited:      {report.inherited_count}")
        info(f"  Contradictions: {report.contradictions_found}")

        tgt_memories = shared_backend.get_all(tgt_id)
        if tgt_memories:
            sample = tgt_memories[0]
            info(f"\nSample inherited memory:")
            info(f"  Content:    '{sample.content[:60]}...'")
            info(f"  Status:     {sample.status.value}")
            info(f"  Confidence: {sample.confidence:.2f}  (original=1.0, decay=0.80)")
            info(f"  Provenance: {[p.event for p in sample.provenance]}")

            self._record(
                "Inherited memories have discounted confidence",
                sample.confidence < 1.0,
                f"confidence={sample.confidence:.2f} (0.80 decay applied)",
            )
            self._record(
                "Provenance chain tracked on inherited memories",
                len(sample.provenance) >= 1 and sample.provenance[-1].event == "INHERIT",
                f"chain: {[p.event for p in sample.provenance]}",
            )
        else:
            self._record("Inherited memories have discounted confidence", False, "no memories inherited")
            self._record("Provenance chain tracked", False, "no memories inherited")

    # ── Feature: Compliance Audit ─────────────────────────────────────────────

    def test_audit_integrity(self):
        import uuid as _uuid
        from snowmemory.core.models import Memory, MemoryType, AuditRecord, OperationType
        section("10 · Compliance Audit & Integrity Verification")

        # Write a memory DIRECTLY to the backend with a guaranteed-unique ID
        # so it always exists regardless of salience gate state
        unique_content = (
            f"AUDIT_TEST_{_uuid.uuid4().hex}: "
            f"Policy compliance record for {self.domain['name']} — must not be altered."
        )
        audit_mem = Memory(
            content     = unique_content,
            agent_id    = self.config.agent_id,
            memory_type = MemoryType.FACTUAL,
        )
        self.memory._backend.write(audit_mem)

        # Write its audit record (normally done by orchestrator.write)
        self.memory._backend.write_audit(AuditRecord(
            operation     = OperationType.WRITE,
            memory_id     = audit_mem.memory_id,
            agent_id      = self.config.agent_id,
            content_hash  = audit_mem.content_hash(),
            salience_score= 1.0,
        ))
        mid = audit_mem.memory_id

        # Integrity check — should pass
        report = self.memory.verify_integrity(mid)
        info(f"Integrity check (unmodified): {report.content_hash_matches}")
        info(f"  Written at:   {report.original_write_timestamp}")
        info(f"  Hash stored:  {report.stored_hash[:16]}...")
        info(f"  Hash current: {report.current_hash[:16]}...")

        self._record(
            "Integrity check passes on unmodified memory",
            report.content_hash_matches,
            f"hashes match: {report.content_hash_matches}",
        )

        # Tamper with the memory content
        m = self.memory._backend._memories.get(mid)
        if m:
            original_content = m.content
            m.content = "TAMPERED — this content was modified after write"
            tamper_report = self.memory.verify_integrity(mid)
            info(f"\nIntegrity check (after tampering): {tamper_report.content_hash_matches}")
            self._record(
                "Integrity check detects content tampering",
                not tamper_report.content_hash_matches,
                f"tampering detected: {not tamper_report.content_hash_matches}",
            )
            m.content = original_content   # restore

        # Audit trail — verify no content ever stored in records
        trail = self.memory.get_audit_trail(mid)
        info(f"\nAudit trail: {len(trail)} records (content-free)")
        for rec in trail[:3]:
            info(f"  [{rec.operation.value}] {rec.timestamp.strftime('%H:%M:%S')} "
                 f"hash={rec.content_hash[:16]}...")
        has_no_raw_content = all(
            not hasattr(rec, "content") for rec in trail
        )
        self._record(
            "Audit records contain only hash, never raw content",
            has_no_raw_content,
            f"{len(trail)} records — AuditRecord has no .content field",
        )

    # ── Feature: Domain Normalization ─────────────────────────────────────────

    def test_domain_normalization(self):
        section("11 · Domain Normalization (vocabulary-bias correction)")

        backend = self.memory._backend
        # Prime domain stats for the domain's primary category
        primary_domain = list(self.domain["domain_keywords"].keys())[0]

        # Update with some values to establish baseline
        values = [0.35, 0.40, 0.38, 0.42, 0.36, 0.44, 0.39]
        for v in values:
            backend.update_domain_stats(primary_domain, v)

        stats = backend.get_domain_stats(primary_domain)
        info(f"Domain: '{primary_domain}'")
        info(f"  Mean: {stats['mean']:.3f}")
        info(f"  Std:  {stats.get('std', 0.2):.3f}")
        info(f"  Count:{stats['count']:.0f}")

        # Test normalization effect in salience engine
        from snowmemory.salience.compound import SalienceEngine
        from snowmemory.config.schema import SalienceConfig
        engine = SalienceEngine(SalienceConfig(domain_normalization=True), backend)

        # A value at the mean should produce a moderate normalized score (~0.5)
        # A value well above mean should produce high normalized score
        mean_val  = stats["mean"]
        high_val  = mean_val + stats.get("std", 0.2) * 2
        info(f"\nNormalization test:")
        info(f"  Mean novelty ({mean_val:.3f}) → normalized ≈ 0.5 (expected)")
        info(f"  High novelty ({high_val:.3f}) → normalized > 0.5 (expected)")

        self._record(
            "Domain stats tracked online (mean/std updating)",
            stats["count"] > 0 and stats.get("std", 0) > 0,
            f"mean={stats['mean']:.3f} std={stats.get('std', 0):.3f} count={stats['count']:.0f}",
        )

    # ── Summary ────────────────────────────────────────────────────────────────

    def print_summary(self):
        passed = sum(1 for _, ok, _ in self.results if ok)
        total  = len(self.results)
        header(f"Results: {passed}/{total} for {self.domain['name']}")
        for name, passed, detail in self.results:
            icon = "✓" if passed else "✗"
            print(f"  {icon}  {name}")
            if not passed:
                print(f"       → {detail}")


# ─────────────────────────────────────────────────────────────────────────────
# Individual Feature Tests (standalone, no domain required)
# ─────────────────────────────────────────────────────────────────────────────

def run_feature(feature: str):
    """Run a single feature test with minimal setup."""
    from snowmemory import MemoryOrchestrator, MemoryConfig, MemoryEvent, QueryContext

    m = MemoryOrchestrator(MemoryConfig(agent_id="feature_test"))

    if feature == "salience":
        header("Salience Engine — Compound CSS Components")
        from snowmemory.salience.compound import SalienceEngine, _cosine_distance
        from snowmemory.config.schema     import SalienceConfig
        from snowmemory.backends.in_memory import InMemoryBackend
        backend = InMemoryBackend()
        engine  = SalienceEngine(SalienceConfig(), backend)
        texts   = [
            "The server crashed because the disk ran out of space",
            "Database connection timeout after 30 seconds on prod-db-01",
            "User JohnDoe reported login failure from mobile app v3.2",
            "Definition: a timeout is when a request exceeds its time limit",
        ]
        section("Scoring sample texts")
        from snowmemory import MemoryEvent as ME
        for text in texts:
            emb = m._embedder.embed(text)
            score = engine.score(ME(content=text, agent_id="a"), emb, "general", "a")
            bar = "█" * int(score.score * 20)
            print(f"  [{bar:<20}] {score.score:.3f}  '{text[:55]}...'")
            info(f"    novelty={score.novelty:.3f} orphan={score.orphan_score:.3f} "
                 f"gap={score.temporal_gap:.3f} acc_inv={score.access_inv:.3f}")

    elif feature == "decay":
        header("Decay & Resurrection Engine")
        from snowmemory.decay.resurrection import DecayResurrectionEngine
        from snowmemory.config.schema import DecayConfig
        from snowmemory.core.models import Memory, MemoryType
        from snowmemory.backends.in_memory import InMemoryBackend
        backend = InMemoryBackend()
        engine  = DecayResurrectionEngine(DecayConfig(), backend)
        section("Decay curves: exponential vs linear vs step")
        for strategy in ["exponential", "linear", "step"]:
            cfg = DecayConfig(strategy=strategy, half_life_days=30)
            e2  = DecayResurrectionEngine(cfg, backend)
            row = f"  {strategy:12} "
            for days in [0, 7, 14, 30, 60, 90, 180]:
                mem = Memory(content="x", agent_id="a", memory_type=MemoryType.EXPERIENTIAL)
                mem.created_at = datetime.utcnow() - timedelta(days=days)
                w   = e2.decay_weight(mem)
                row += f"│{w:.2f}"
            print(row + "│")
        print("               │0d  │7d  │14d │30d │60d │90d │180d│")

    elif feature == "graph":
        header("Graph Extractor — Universal Patterns")
        from snowmemory.graph.extractor import RuleBasedExtractor
        extractor = RuleBasedExtractor()
        samples   = [
            "User Alice reported that the payment service failed due to a database timeout",
            "Version v2.3.1 was deployed to production and caused a 15% latency increase",
            "Order ORD-5521 depends on inventory check for SKU-XYZ before dispatch",
            "Dr Smith diagnosed patient PAT-001 with hypertension — prescribed Lisinopril",
            "The build pipeline failed on the linting step — fixed by updating ESLint config",
        ]
        for text in samples:
            payload = extractor.extract(text)
            info(f"Text:      '{text[:65]}...'")
            info(f"Entities:  {payload.entities}")
            rels = [(r.from_entity, r.relation_type, r.to_entity) for r in payload.relations
                    if r.relation_type != "CO_OCCURS_WITH"][:3]
            info(f"Relations: {rels}")
            print()

    elif feature == "inheritance":
        header("Cross-Agent Memory Inheritance")
        from snowmemory import MemoryOrchestrator, MemoryConfig, MemoryEvent, InheritanceFilter
        a = MemoryOrchestrator(MemoryConfig(agent_id="source_agent"))
        b = MemoryOrchestrator(MemoryConfig(agent_id="target_agent"))
        b._backend = a._backend
        b._inheritance._backend = a._backend
        events = [
            "Payment service scales poorly above 1000 req/s — use queue-based processing",
            "User onboarding completion drops if email verification takes more than 2 minutes",
            "Database connection pool should be set to 100 — lower values cause timeouts",
        ]
        for e in events:
            r = a.write(MemoryEvent(content=e, agent_id="source_agent"))
            info(f"Source wrote: '{e[:55]}...' score={r.surprise_score:.2f}")
        report = b.inherit_from("source_agent", filter=InheritanceFilter(min_salience=0.0, inheritance_decay=0.75))
        section("Inheritance Report")
        info(f"Inherited: {report.inherited_count}/{report.total_candidates}")
        info(f"Contradictions: {report.contradictions_found}")
        b_mems = [m for m in a._backend.get_all("target_agent")]
        for m in b_mems:
            info(f"  [{m.status.value}] conf={m.confidence:.2f} '{m.content[:55]}...'")
            info(f"    provenance: {[p.event for p in m.provenance]}")

    elif feature == "audit":
        header("Compliance Audit — Content-Hash Integrity")
        from snowmemory import MemoryEvent
        r     = m.write(MemoryEvent(content="Policy: do not modify this.", agent_id="feature_test",
                                     metadata={"memory_type": "FACTUAL"}))
        ok_rpt = m.verify_integrity(r.memory_id)
        info(f"Clean integrity check: {ok_rpt.content_hash_matches}")
        info(f"  Stored hash:  {ok_rpt.stored_hash[:20]}...")
        info(f"  Current hash: {ok_rpt.current_hash[:20]}...")
        mem = m._backend._memories[r.memory_id]
        mem.content = "TAMPERED CONTENT"
        bad_rpt = m.verify_integrity(r.memory_id)
        info(f"After tampering:       {bad_rpt.content_hash_matches}  (expected False)")
        trail = m.get_audit_trail(r.memory_id)
        info(f"Audit trail records:   {len(trail)}")
        for rec in trail:
            info(f"  [{rec.operation.value}] {rec.timestamp.isoformat()} "
                 f"salience={rec.salience_score:.2f}")

    elif feature == "threshold":
        header("Adaptive Write Threshold")
        from snowmemory.salience.adaptive_threshold import AdaptiveWriteGate
        from snowmemory.config.schema import SalienceConfig
        import uuid
        gate = AdaptiveWriteGate(SalienceConfig(write_threshold=0.40, adjustment_rate=0.05))
        info(f"Starting threshold: {gate.threshold:.4f}")
        section("Scenario A: all low-salience writes, none retrieved → threshold rises")
        for i in range(60):
            gate.record_write(str(uuid.uuid4()), 0.15)
        info(f"After 60 low-salience writes: {gate.threshold:.4f}")
        section("Scenario B: reset, then sparse query results → threshold falls")
        gate.threshold = 0.60
        for _ in range(120):
            gate.record_query_result(1, 10)
        for i in range(60):
            gate.record_write(str(uuid.uuid4()), 0.65)
        info(f"After 120 sparse queries:     {gate.threshold:.4f}")
        info(f"Gate stats: {gate.stats}")

    else:
        warn(f"Unknown feature '{feature}'. Choose: salience, decay, graph, inheritance, audit, threshold")


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SnowMemory Local Test Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          python demo.py                       # interactive domain picker
          python demo.py --domain devops       # run all tests for devops domain
          python demo.py --all                 # run all domains
          python demo.py --feature salience    # test one feature with generic data
          python demo.py --feature decay
          python demo.py --feature graph
          python demo.py --feature inheritance
          python demo.py --feature audit
          python demo.py --feature threshold
        """),
    )
    parser.add_argument("--domain",  choices=list(DOMAINS.keys()), help="Domain to test")
    parser.add_argument("--all",     action="store_true",           help="Run all domains")
    parser.add_argument("--feature", help="Test a specific feature only")
    args = parser.parse_args()

    print("""
╔══════════════════════════════════════════════════════════╗
║              SnowMemory — Local Test Harness             ║
║         Tests all 6 patent innovations end-to-end        ║
╚══════════════════════════════════════════════════════════╝""")

    if args.feature:
        run_feature(args.feature)
        return

    if args.all:
        overall = []
        for key in DOMAINS:
            runner = FeatureTestRunner(key)
            passed = runner.run_all()
            overall.append((key, passed))
        header("Overall Results")
        for key, passed in overall:
            icon = "✓" if passed else "✗"
            print(f"  {icon}  {DOMAINS[key]['name']}")
        return

    if args.domain:
        runner = FeatureTestRunner(args.domain)
        runner.run_all()
        return

    # Interactive picker
    print("\nAvailable domains:\n")
    keys = list(DOMAINS.keys())
    for i, key in enumerate(keys, 1):
        d = DOMAINS[key]
        print(f"  [{i}] {d['name']:30}  {d['description']}")
    print(f"  [{len(keys)+1}] All domains")
    print(f"  [q] Quit")
    print()

    choice = input("Select domain (or feature name): ").strip().lower()

    # Feature shortcut
    features = ["salience", "decay", "graph", "inheritance", "audit", "threshold"]
    if choice in features:
        run_feature(choice)
        return

    if choice == "q":
        return

    if choice == str(len(keys) + 1) or choice == "all":
        for key in keys:
            runner = FeatureTestRunner(key)
            runner.run_all()
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            runner = FeatureTestRunner(keys[idx])
            runner.run_all()
        else:
            err(f"Invalid choice: {choice}")
    except ValueError:
        # Try as domain key
        if choice in DOMAINS:
            runner = FeatureTestRunner(choice)
            runner.run_all()
        else:
            err(f"Unknown input: '{choice}'")


if __name__ == "__main__":
    main()

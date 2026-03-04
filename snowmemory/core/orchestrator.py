"""
SnowMemory Orchestrator
The single entry point for all memory operations.
Wires together: salience engine, adaptive threshold, classifier,
graph extractor, decay/resurrection, inheritance, compliance audit.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .models     import (
    Memory, MemoryEvent, MemoryType, MemoryStatus,
    QueryContext, WriteResult, SalienceScore,
    AuditRecord, OperationType,
)
from .classifier  import MemoryTypeClassifier
from .embedder    import build_embedder
from ..config.schema          import MemoryConfig
from ..backends.registry      import build_backend
from ..backends.base          import MemoryBackend
from ..salience.compound      import SalienceEngine
from ..salience.adaptive_threshold import AdaptiveWriteGate
from ..graph.extractor        import build_extractor
from ..decay.resurrection     import DecayResurrectionEngine
from ..audit.compliance       import ComplianceAuditLogger
from ..inheritance.protocol   import MemoryInheritanceProtocol, InheritanceFilter


class MemoryOrchestrator:
    """
    Hybrid memory system combining:
    - Titans-inspired CSS salience engine (write gate)
    - Adaptive write threshold (self-tuning via retrieval feedback)
    - Mem0-style graph extraction and storage
    - Three-tier taxonomy (Working / Experiential / Factual)
    - Decay + Resurrection engine
    - Cross-agent memory inheritance with provenance
    - Compliance-native audit (content hash, not content)
    - Pluggable backend adapter (Snowflake today, anything tomorrow)
    """

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.config = config or MemoryConfig()

        # Build backends (one shared backend routes all tiers in MVP)
        # In production you can have separate backends per tier
        self._backend: MemoryBackend = build_backend(
            self.config.experiential.backend, self.config
        )

        # Core components
        self._embedder    = build_embedder(self.config.embedder)
        self._classifier  = MemoryTypeClassifier(self.config.classifier)
        self._salience    = SalienceEngine(self.config.salience, self._backend)
        self._gate        = AdaptiveWriteGate(self.config.salience)
        self._extractor   = build_extractor(self.config.graph) if self.config.graph.enabled else None
        self._decay       = DecayResurrectionEngine(self.config.decay, self._backend)
        self._audit       = ComplianceAuditLogger(self.config.audit, self._backend)
        self._inheritance = MemoryInheritanceProtocol(self.config.inheritance, self._backend)

    # ─────────────────────────────────────────────────────────────
    # Write Pipeline
    # ─────────────────────────────────────────────────────────────

    def write(self, event: MemoryEvent) -> WriteResult:
        """
        Full write pipeline:
        1. Classify memory type
        2. Embed content
        3. Score salience (CSS)
        4. Gate check (adaptive threshold)
        5. Extract graph entities/relations
        6. Persist memory + graph + audit record
        """
        # Step 1: classify
        memory_type = self._classifier.classify(event)

        # Working memory skips the salience gate (always written, TTL-bounded)
        if memory_type == MemoryType.WORKING:
            return self._write_working(event)

        # Step 2: embed
        embedding = self._embedder.embed(event.content)
        domain    = event.domain or self._infer_domain(event.content)

        # Step 3: score salience
        sal_score = self._salience.score(
            event=event,
            embedding=embedding,
            domain=domain,
            agent_id=event.agent_id,
        )

        # Step 4: adaptive gate
        if not self._gate.should_write(sal_score.score):
            return WriteResult(
                written=False,
                reason=f"below_threshold (score={sal_score.score:.3f} < {self._gate.threshold:.3f})",
                surprise_score=sal_score.score,
                novelty_score=sal_score.novelty,
                orphan_score=sal_score.orphan_score,
                threshold_used=self._gate.threshold,
            )

        # Step 5: build Memory object
        memory = self._build_memory(event, embedding, memory_type, domain, sal_score)

        # Step 6: persist
        self._backend.write(memory)
        self._audit.log_write(memory, sal_score.score)
        self._gate.record_write(memory.memory_id, sal_score.score)

        # Step 7: graph extraction
        if self._extractor and self.config.graph.enabled:
            graph = self._extractor.extract(event.content, memory.memory_id)
            memory.entities = graph.entities
            self._backend.write_relations(graph.relations)

        return WriteResult(
            written=True,
            memory_id=memory.memory_id,
            reason="written",
            surprise_score=sal_score.score,
            novelty_score=sal_score.novelty,
            orphan_score=sal_score.orphan_score,
            threshold_used=self._gate.threshold,
        )

    def _write_working(self, event: MemoryEvent) -> WriteResult:
        """Working memory bypasses salience gate — always written, auto-expires."""
        embedding = self._embedder.embed(event.content)
        memory    = Memory(
            content=event.content,
            agent_id=event.agent_id,
            memory_type=MemoryType.WORKING,
            session_id=event.session_id,
            embedding=embedding,
            domain=event.domain or "general",
            expires_at=datetime.utcnow() + timedelta(seconds=self.config.working.ttl_seconds),
            metadata=event.metadata,
        )
        self._backend.write(memory)
        return WriteResult(written=True, memory_id=memory.memory_id, reason="working_memory")

    # ─────────────────────────────────────────────────────────────
    # Query Pipeline
    # ─────────────────────────────────────────────────────────────

    def query(self, ctx: QueryContext) -> List[Memory]:
        """
        Hybrid retrieval across all tiers:
        Vector similarity × decay weight × recency, + graph expansion.
        """
        embedding = self._embedder.embed(ctx.text)
        memories  = self._backend.query(
            embedding=embedding,
            agent_id=ctx.agent_id,
            top_k=ctx.top_k,
            memory_types=ctx.memory_types,
            min_decay=ctx.min_decay,
        )

        # Update access counts + check resurrection
        for m in memories:
            self._backend.update_access(m.memory_id)
            if self.config.audit.log_reads:
                self._audit.log_read(m.memory_id, ctx.agent_id, m)
            # Resurrection check
            new_weight = self._decay.on_retrieval(m)
            if new_weight:
                m.decay_weight = new_weight

        # Graph expansion
        if ctx.include_graph and self.config.graph.enabled:
            graph_mems = self._expand_via_graph(memories, ctx)
            # Merge deduplicated
            seen = {m.memory_id for m in memories}
            for m in graph_mems:
                if m.memory_id not in seen:
                    memories.append(m)
                    seen.add(m.memory_id)

        # Record query gap for adaptive threshold
        self._gate.record_query_result(len(memories), ctx.top_k)

        return memories[:ctx.top_k]

    def _expand_via_graph(
        self, memories: List[Memory], ctx: QueryContext
    ) -> List[Memory]:
        """Expand results via graph traversal on extracted entities."""
        extra = []
        seen_entities = set()
        for m in memories[:3]:   # expand top-3 results only
            for entity in m.entities:
                if entity in seen_entities:
                    continue
                seen_entities.add(entity)
                relations = self._backend.get_graph_neighbors(
                    entity, depth=ctx.graph_depth, agent_id=ctx.agent_id
                )
                for rel in relations:
                    mid = rel.get("memory_id")
                    if mid:
                        candidate = self._backend.get(mid)
                        if candidate:
                            extra.append(candidate)
        return extra

    # ─────────────────────────────────────────────────────────────
    # Graph Query
    # ─────────────────────────────────────────────────────────────

    def graph_query(
        self,
        entity: str,
        agent_id: str,
        depth: int = 2,
    ) -> List[Dict]:
        """Direct graph traversal — returns relation dicts with memory content."""
        return self._backend.get_graph_neighbors(entity, depth=depth, agent_id=agent_id)

    # ─────────────────────────────────────────────────────────────
    # Agent Inheritance
    # ─────────────────────────────────────────────────────────────

    def inherit_from(
        self,
        source_agent_id: str,
        filter: Optional[InheritanceFilter] = None,
    ) -> Any:
        """Transfer memories from another agent with provenance tracking."""
        return self._inheritance.inherit(
            source_agent_id=source_agent_id,
            target_agent_id=self.config.agent_id,
            filter=filter,
        )

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    def run_decay(self) -> int:
        """Apply decay to all experiential memories. Run nightly."""
        return self._decay.apply_decay_all(self.config.agent_id)

    def expire_working_memory(self) -> int:
        """Remove expired working memory entries."""
        return self._backend.expire_old(self.config.agent_id, MemoryType.WORKING)

    # ─────────────────────────────────────────────────────────────
    # Compliance / Audit
    # ─────────────────────────────────────────────────────────────

    def verify_integrity(self, memory_id: str):
        """Verify memory content hasn't been tampered with."""
        return self._audit.verify(memory_id)

    def get_audit_trail(self, memory_id: str):
        """Get full operation history for a memory (no content exposed)."""
        return self._audit.get_trail(memory_id)

    def record_retrieval_feedback(self, memory_id: str, was_used: bool = True):
        """
        Tell the adaptive gate whether a retrieved memory was actually useful.
        Call this from your agent after consuming a memory.
        This closes the feedback loop for threshold calibration.
        """
        self._gate.record_retrieval(memory_id, was_used)

    # ─────────────────────────────────────────────────────────────
    # Stats / Debug
    # ─────────────────────────────────────────────────────────────

    def stats(self) -> Dict:
        all_memories = self._backend.get_all(self.config.agent_id)
        by_type = {}
        for mt in MemoryType:
            by_type[mt.value] = sum(1 for m in all_memories if m.memory_type == mt)
        return {
            "agent_id":          self.config.agent_id,
            "total_memories":    len(all_memories),
            "by_type":           by_type,
            "write_threshold":   self._gate.threshold,
            "gate_stats":        self._gate.stats,
            "backend":           self.config.experiential.backend,
        }

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    def _build_memory(
        self,
        event: MemoryEvent,
        embedding: List[float],
        memory_type: MemoryType,
        domain: str,
        sal: SalienceScore,
    ) -> Memory:
        ttl = None
        if memory_type == MemoryType.EXPERIENTIAL and self.config.experiential.ttl_days:
            ttl = datetime.utcnow() + timedelta(days=self.config.experiential.ttl_days)

        return Memory(
            content=event.content,
            agent_id=event.agent_id,
            memory_type=memory_type,
            session_id=event.session_id,
            embedding=embedding,
            domain=domain,
            surprise_score=sal.score,
            novelty_score=sal.novelty,
            orphan_score=sal.orphan_score,
            bridge_score=sal.bridge_score,
            expires_at=ttl,
            metadata=event.metadata,
        )

    def _infer_domain(self, text: str) -> str:
        """
        Domain inference via configurable keyword map (domain_keywords in config).
        Fully domain-agnostic — no hardcoded vocabulary.
        Falls back to 'general' when no keywords match.
        """
        text_l     = text.lower()
        domain_map = getattr(self.config, "domain_keywords", None) or {}
        for domain, keywords in domain_map.items():
            if any(kw.lower() in text_l for kw in keywords):
                return domain
        return "general"

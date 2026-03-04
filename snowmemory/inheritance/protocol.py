"""
SnowMemory Cross-Agent Memory Inheritance Protocol
Patent-novel: structured memory sharing between agents with provenance
tracking and confidence decay.

Key innovations:
1. Inherited memories receive confidence discount (not full trust)
2. Full provenance chain preserved — you know exactly where memory came from
3. Contradiction detection between inherited and directly-experienced memories
4. Re-experience → confidence restoration
"""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from ..core.models import (
    Memory, MemoryType, MemoryStatus, OperationType,
    AuditRecord, ProvenanceEntry,
)
from ..config.schema import InheritanceConfig
from ..backends.base import MemoryBackend
from ..core.embedder import SimpleEmbedder


def _cosine(a: List[float], b: List[float]) -> float:
    import math
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-9)


@dataclass
class InheritanceFilter:
    min_salience:      float       = 0.40
    memory_types:      List[MemoryType] = field(default_factory=lambda: [MemoryType.EXPERIENTIAL])
    inheritance_decay: float       = 0.80   # confidence multiplier on inherited memories
    max_memories:      int         = 100


@dataclass
class InheritanceReport:
    source_agent:          str
    target_agent:          str
    total_candidates:      int
    inherited_count:       int
    contradictions_found:  int
    skipped_low_salience:  int
    timestamp:             datetime = field(default_factory=datetime.utcnow)


class MemoryInheritanceProtocol:
    """
    Transfers curated memory from one agent to another with:
    - Confidence discounting (inherited memories are less trusted)
    - Provenance chain (full lineage preserved)
    - Contradiction flagging (conflicts with target's own memories)
    """

    CONTRADICTION_THRESHOLD = 0.85  # cosine similarity to existing for contradiction check

    def __init__(self, config: InheritanceConfig, backend: MemoryBackend):
        self.config  = config
        self.backend = backend

    def inherit(
        self,
        source_agent_id: str,
        target_agent_id: str,
        filter: Optional[InheritanceFilter] = None,
    ) -> InheritanceReport:
        """
        Transfer experiential memories from source → target agent.
        Each inherited memory gets discounted confidence and a provenance entry.
        """
        f = filter or InheritanceFilter(
            min_salience=self.config.min_salience,
            inheritance_decay=self.config.default_decay,
        )

        # Get candidate memories from source
        candidates = self.backend.get_all(source_agent_id)
        candidates = [
            m for m in candidates
            if m.memory_type in f.memory_types
            and m.surprise_score >= f.min_salience
            and m.status == MemoryStatus.ACTIVE
        ][:f.max_memories]

        inherited       = 0
        contradictions  = 0
        skipped         = 0

        for memory in candidates:
            # Build inherited copy
            inherited_memory = self._build_inherited(
                memory, target_agent_id, f.inheritance_decay
            )

            # Check for contradiction with target's existing memories
            if self.config.contradiction_check and memory.embedding:
                conflict = self._find_contradiction(
                    inherited_memory, target_agent_id
                )
                if conflict:
                    inherited_memory.status          = MemoryStatus.FLAGGED_CONTRADICTION
                    inherited_memory.contradiction_ref = conflict.memory_id
                    contradictions += 1

            self.backend.write(inherited_memory)
            self.backend.write_audit(AuditRecord(
                operation=OperationType.INHERIT,
                memory_id=inherited_memory.memory_id,
                agent_id=target_agent_id,
                content_hash=inherited_memory.content_hash(),
                salience_score=inherited_memory.surprise_score,
                decay_weight=inherited_memory.confidence,
                notes=(
                    f"inherited from {source_agent_id} "
                    f"with decay={f.inheritance_decay}"
                ),
            ))
            inherited += 1

        return InheritanceReport(
            source_agent=source_agent_id,
            target_agent=target_agent_id,
            total_candidates=len(candidates),
            inherited_count=inherited,
            contradictions_found=contradictions,
            skipped_low_salience=skipped,
        )

    def _build_inherited(
        self,
        source: Memory,
        target_agent_id: str,
        decay: float,
    ) -> Memory:
        """Clone a memory for the target agent with provenance tracking."""
        prov_entry = ProvenanceEntry(
            event="INHERIT",
            agent_id=source.agent_id,
            confidence_at=source.confidence,
            decay_applied=1.0 - decay,
            notes=f"inherited from agent {source.agent_id}",
        )
        inherited_memory = Memory(
            memory_id=str(uuid.uuid4()),
            content=source.content,
            agent_id=target_agent_id,
            memory_type=source.memory_type,
            session_id=None,
            embedding=source.embedding,
            entities=source.entities,
            domain=source.domain,
            surprise_score=source.surprise_score,
            novelty_score=source.novelty_score,
            orphan_score=source.orphan_score,
            confidence=source.confidence * decay,   # ← discounted
            decay_weight=source.decay_weight,
            status=MemoryStatus.INHERITED,
            provenance=source.provenance + [prov_entry],
            metadata={**source.metadata, "inherited_from": source.agent_id},
        )
        return inherited_memory

    def _find_contradiction(
        self, candidate: Memory, target_agent_id: str
    ) -> Optional[Memory]:
        """
        Find an existing memory in target that is highly similar (same topic)
        but whose content may conflict.
        Uses high cosine similarity as a proxy for 'same topic'.
        """
        if not candidate.embedding:
            return None
        neighbors = self.backend.get_neighbors(
            candidate.embedding, k=3, agent_id=target_agent_id
        )
        for n in neighbors:
            if not n.embedding:
                continue
            sim = _cosine(candidate.embedding, n.embedding)
            if sim > self.CONTRADICTION_THRESHOLD:
                # High similarity = same topic = potential contradiction
                # (a more sophisticated check would do semantic entailment,
                #  but cosine threshold is the MVP approach)
                if n.status == MemoryStatus.ACTIVE:
                    return n
        return None

    def confirm_experience(
        self, memory_id: str, agent_id: str
    ) -> Optional[Memory]:
        """
        When an inherited memory is directly re-experienced by the target
        agent, restore confidence to 1.0 (direct experience trumps inheritance).
        """
        memory = self.backend.get(memory_id)
        if not memory or memory.agent_id != agent_id:
            return None
        if memory.status != MemoryStatus.INHERITED:
            return None

        memory.confidence = 1.0
        memory.status     = MemoryStatus.ACTIVE
        memory.provenance.append(ProvenanceEntry(
            event="CONFIRM_EXPERIENCE",
            agent_id=agent_id,
            confidence_at=1.0,
            notes="confidence restored via direct re-experience",
        ))
        self.backend.write(memory)
        return memory

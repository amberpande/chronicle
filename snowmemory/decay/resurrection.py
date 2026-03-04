"""
SnowMemory Decay & Resurrection Engine
Patent-novel: makes forgetting reversible.

Standard systems: decay is one-directional (memories only fade).
This system: memories that are retrieved repeatedly after heavy decay
are RESURRECTED — their decay weight is partially restored.

Analogy: forgotten memories strengthened by re-exposure (human cognition).
No prior art in Titans, Mem0, or any RAG system.
"""
from __future__ import annotations
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from ..core.models import (
    Memory, MemoryType, MemoryStatus, OperationType, AuditRecord, ProvenanceEntry
)
from ..config.schema import DecayConfig
from ..backends.base import MemoryBackend


class DecayResurrectionEngine:
    """
    Two responsibilities:
    1. Periodically decay experiential memories (exponential by default)
    2. Detect resurrection candidates and restore their decay weight
    """

    def __init__(self, config: DecayConfig, backend: MemoryBackend):
        self.config  = config
        self.backend = backend
        # memory_id → deque of retrieval timestamps
        self._retrieval_log: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=20)
        )

    # ─────────────────────────────────────────────────────────────
    # Decay
    # ─────────────────────────────────────────────────────────────

    def decay_weight(self, memory: Memory, as_of: Optional[datetime] = None) -> float:
        """
        Compute the current decay weight for a memory.
        Does NOT update the backend — call apply_decay() for that.
        """
        now        = as_of or datetime.utcnow()
        age_days   = (now - memory.created_at).total_seconds() / 86400
        cfg        = self.config

        if cfg.strategy == "exponential":
            # w(t) = e^(-λt), λ = ln(2) / half_life
            lam    = math.log(2) / cfg.half_life_days
            weight = math.exp(-lam * age_days)
        elif cfg.strategy == "linear":
            weight = max(0.0, 1.0 - age_days / (cfg.half_life_days * 2))
        elif cfg.strategy == "step":
            steps  = age_days // cfg.half_life_days
            weight = 0.5 ** steps
        else:
            weight = 1.0

        return max(cfg.min_weight, weight)

    def apply_decay_all(self, agent_id: str) -> int:
        """
        Apply decay to all experiential memories for an agent.
        Run this periodically (e.g., nightly Airflow task).
        Returns count of memories updated.
        """
        memories = self.backend.get_all(agent_id, MemoryType.EXPERIENTIAL)
        updated  = 0
        for m in memories:
            if m.status in (MemoryStatus.EXPIRED, MemoryStatus.DELETED if hasattr(MemoryStatus, 'DELETED') else None):
                continue
            new_weight = self.decay_weight(m)
            if abs(new_weight - m.decay_weight) > 0.01:
                self.backend.update_decay(m.memory_id, new_weight)
                self.backend.write_audit(AuditRecord(
                    operation=OperationType.DECAY,
                    memory_id=m.memory_id,
                    agent_id=agent_id,
                    content_hash=m.content_hash(),
                    decay_weight=new_weight,
                    notes=f"decay from {m.decay_weight:.3f} → {new_weight:.3f}",
                ))
                updated += 1
        return updated

    # ─────────────────────────────────────────────────────────────
    # Resurrection
    # ─────────────────────────────────────────────────────────────

    def on_retrieval(self, memory: Memory) -> Optional[float]:
        """
        Call every time a memory is retrieved.
        Returns new decay weight if resurrected, else None.

        Resurrection triggers when:
        - memory is heavily decayed (below eligibility threshold)
        - it has been retrieved N+ times within the time window
        """
        if not self.config.resurrection_enabled:
            return None
        if memory.decay_weight >= self.config.resurrection_eligibility:
            return None  # not decayed enough to be eligible

        # Log retrieval
        now = datetime.utcnow()
        self._retrieval_log[memory.memory_id].append(now)

        # Count recent retrievals within the window
        window_start  = now - timedelta(hours=self.config.resurrection_window_hours)
        recent_count  = sum(
            1 for t in self._retrieval_log[memory.memory_id]
            if t >= window_start
        )

        if recent_count >= self.config.resurrection_confirmation_count:
            return self._resurrect(memory)
        return None

    def _resurrect(self, memory: Memory) -> float:
        """
        Partially restore decay weight. Never fully restores —
        max cap prevents resurrection from fully overriding natural decay.
        """
        cfg             = self.config
        pre_weight      = memory.decay_weight
        restored_weight = min(
            pre_weight + cfg.resurrection_boost,
            cfg.max_resurrection_weight,
        )

        self.backend.update_decay(memory.memory_id, restored_weight)

        # Write provenance entry
        prov = ProvenanceEntry(
            event="RESURRECT",
            agent_id=memory.agent_id,
            confidence_at=restored_weight,
            notes=(
                f"resurrected from {pre_weight:.3f} → {restored_weight:.3f} "
                f"after {self.config.resurrection_confirmation_count} retrievals "
                f"within {self.config.resurrection_window_hours}h"
            ),
        )

        self.backend.write_audit(AuditRecord(
            operation=OperationType.RESURRECT,
            memory_id=memory.memory_id,
            agent_id=memory.agent_id,
            content_hash=memory.content_hash(),
            decay_weight=restored_weight,
            notes=prov.notes,
        ))

        print(
            f"[Resurrection] {memory.memory_id[:8]}… "
            f"{pre_weight:.3f} → {restored_weight:.3f}"
        )
        return restored_weight

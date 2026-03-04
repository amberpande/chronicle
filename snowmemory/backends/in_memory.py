"""
SnowMemory In-Memory Backend
Full-featured backend that works with zero external dependencies.
Perfect for: testing, development, single-process agents.
All data lives in Python dicts — lost on process exit.
"""
from __future__ import annotations
import math, hashlib
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .base import MemoryBackend
from ..core.models import (
    AuditRecord, GraphRelation, IntegrityReport,
    Memory, MemoryType, OperationType,
)


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot  = sum(x * y for x, y in zip(a, b))
    na   = math.sqrt(sum(x * x for x in a))
    nb   = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-9)


def _cosine_distance(a: List[float], b: List[float]) -> float:
    return 1.0 - _cosine(a, b)


class InMemoryBackend(MemoryBackend):
    """
    Thread-unsafe in-process store. Sufficient for MVP and testing.
    Replace with SnowflakeBackend for production multi-process agents.
    """

    def __init__(self):
        # memory_id → Memory
        self._memories:     Dict[str, Memory]              = {}
        # memory_id → list[AuditRecord]
        self._audit:        Dict[str, List[AuditRecord]]   = defaultdict(list)
        # (from_entity, to_entity) → GraphRelation
        self._relations:    Dict[Tuple, GraphRelation]     = {}
        # entity → set(memory_ids)
        self._entity_index: Dict[str, set]                 = defaultdict(set)
        # domain → {mean, variance, count}
        self._domain_stats: Dict[str, Dict[str, float]]   = {}
        # memory_id → content_hash at write time (for integrity)
        self._write_hashes: Dict[str, str]                 = {}

    # ── Core CRUD ────────────────────────────────────────────────

    def write(self, memory: Memory) -> bool:
        self._memories[memory.memory_id] = memory
        self._write_hashes[memory.memory_id] = memory.content_hash()
        for entity in memory.entities:
            self._entity_index[entity.lower()].add(memory.memory_id)
        return True

    def get(self, memory_id: str) -> Optional[Memory]:
        return self._memories.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        if memory_id in self._memories:
            del self._memories[memory_id]
            return True
        return False

    def update_decay(self, memory_id: str, new_weight: float) -> bool:
        if memory_id in self._memories:
            self._memories[memory_id].decay_weight = max(0.0, min(1.0, new_weight))
            return True
        return False

    def update_access(self, memory_id: str) -> bool:
        if memory_id in self._memories:
            m = self._memories[memory_id]
            m.access_count   += 1
            m.last_accessed_at = datetime.utcnow()
            return True
        return False

    # ── Vector Search ─────────────────────────────────────────────

    def get_neighbors(
        self,
        embedding: List[float],
        k: int = 5,
        memory_type: Optional[MemoryType] = None,
        domain: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> List[Memory]:
        candidates = [
            m for m in self._memories.values()
            if m.embedding is not None
            and (memory_type is None or m.memory_type == memory_type)
            and (domain is None or m.domain == domain)
            and (agent_id is None or m.agent_id == agent_id)
        ]
        scored = [
            (m, _cosine(embedding, m.embedding))
            for m in candidates
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [m for m, _ in scored[:k]]

    # ── Query ─────────────────────────────────────────────────────

    def query(
        self,
        embedding: List[float],
        agent_id: str,
        top_k: int = 10,
        memory_types: Optional[List[MemoryType]] = None,
        min_decay: float = 0.1,
    ) -> List[Memory]:
        candidates = [
            m for m in self._memories.values()
            if m.agent_id == agent_id
            and m.embedding is not None
            and m.decay_weight >= min_decay
            and (memory_types is None or m.memory_type in memory_types)
        ]
        scored = [
            (m, _cosine(embedding, m.embedding) * m.effective_weight())
            for m in candidates
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [m for m, _ in scored[:top_k]]

    # ── Graph ─────────────────────────────────────────────────────

    def write_relations(self, relations: List[GraphRelation]) -> bool:
        for r in relations:
            key = (r.from_entity.lower(), r.to_entity.lower(), r.relation_type)
            self._relations[key] = r
        return True

    def get_graph_neighbors(
        self, entity: str, depth: int = 2, agent_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        visited  = set()
        frontier = {entity.lower()}
        results  = []

        for d in range(depth):
            next_frontier = set()
            for ent in frontier:
                if ent in visited:
                    continue
                visited.add(ent)
                # Find all relations touching this entity
                for (fe, te, rt), rel in self._relations.items():
                    if fe == ent or te == ent:
                        neighbor = te if fe == ent else fe
                        next_frontier.add(neighbor)
                        # Get memories mentioning this entity
                        mem_ids = self._entity_index.get(neighbor, set())
                        for mid in mem_ids:
                            m = self._memories.get(mid)
                            if m and (agent_id is None or m.agent_id == agent_id):
                                results.append({
                                    "from_entity":   rel.from_entity,
                                    "relation_type": rel.relation_type,
                                    "to_entity":     rel.to_entity,
                                    "memory_id":     mid,
                                    "content":       m.content,
                                    "depth":         d + 1,
                                })
            frontier = next_frontier - visited

        return results

    # ── Domain Stats ──────────────────────────────────────────────

    def get_domain_stats(self, domain: str) -> Dict[str, float]:
        return self._domain_stats.get(domain, {"mean": 0.5, "std": 0.2, "count": 0})

    def update_domain_stats(self, domain: str, novelty: float) -> None:
        stats = self._domain_stats.get(domain, {"mean": 0.5, "std": 0.2, "count": 0.0})
        n     = stats["count"] + 1
        mean  = stats["mean"] + (novelty - stats["mean"]) / n
        # Welford online variance
        if n > 1:
            m2 = stats.get("m2", 0.0) + (novelty - stats["mean"]) * (novelty - mean)
            std = math.sqrt(m2 / n) if n > 1 else 0.2
        else:
            m2  = 0.0
            std = 0.2
        self._domain_stats[domain] = {"mean": mean, "std": max(std, 1e-6), "count": n, "m2": m2}

    # ── Audit ─────────────────────────────────────────────────────

    def write_audit(self, record: AuditRecord) -> bool:
        self._audit[record.memory_id].append(record)
        return True

    def get_audit_trail(self, memory_id: str) -> List[AuditRecord]:
        return self._audit.get(memory_id, [])

    def verify_integrity(self, memory_id: str) -> IntegrityReport:
        memory    = self._memories.get(memory_id)
        records   = self._audit.get(memory_id, [])
        write_rec = next((r for r in records if r.operation == OperationType.WRITE), None)
        if not memory or not write_rec:
            return IntegrityReport(
                memory_id=memory_id,
                content_hash_matches=False,
                original_write_timestamp=datetime.utcnow(),
                operation_count=len(records),
                current_hash="",
                stored_hash=write_rec.content_hash if write_rec else "",
            )
        current_hash = memory.content_hash()
        return IntegrityReport(
            memory_id=memory_id,
            content_hash_matches=(current_hash == write_rec.content_hash),
            original_write_timestamp=write_rec.timestamp,
            operation_count=len(records),
            current_hash=current_hash,
            stored_hash=write_rec.content_hash,
        )

    # ── Lifecycle ─────────────────────────────────────────────────

    def expire_old(self, agent_id: str, memory_type: MemoryType) -> int:
        now  = datetime.utcnow()
        keys = [
            mid for mid, m in self._memories.items()
            if m.agent_id == agent_id
            and m.memory_type == memory_type
            and m.expires_at is not None
            and m.expires_at < now
        ]
        for k in keys:
            del self._memories[k]
        return len(keys)

    def get_all(
        self, agent_id: str, memory_type: Optional[MemoryType] = None
    ) -> List[Memory]:
        return [
            m for m in self._memories.values()
            if m.agent_id == agent_id
            and (memory_type is None or m.memory_type == memory_type)
        ]

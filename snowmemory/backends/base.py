"""
SnowMemory Backend Abstract Interface
All storage backends implement this contract.
Swap backends by changing config — zero changes to business logic.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from ..core.models import Memory, MemoryType, GraphRelation, AuditRecord, IntegrityReport


class MemoryBackend(ABC):
    """Abstract interface every backend must implement."""

    # ── Core CRUD ────────────────────────────────────────────────
    @abstractmethod
    def write(self, memory: Memory) -> bool: ...

    @abstractmethod
    def get(self, memory_id: str) -> Optional[Memory]: ...

    @abstractmethod
    def delete(self, memory_id: str) -> bool: ...

    @abstractmethod
    def update_decay(self, memory_id: str, new_weight: float) -> bool: ...

    @abstractmethod
    def update_access(self, memory_id: str) -> bool: ...

    # ── Vector Search ─────────────────────────────────────────────
    @abstractmethod
    def get_neighbors(
        self,
        embedding: List[float],
        k: int = 5,
        memory_type: Optional[MemoryType] = None,
        domain: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> List[Memory]: ...

    # ── Query ─────────────────────────────────────────────────────
    @abstractmethod
    def query(
        self,
        embedding: List[float],
        agent_id: str,
        top_k: int = 10,
        memory_types: Optional[List[MemoryType]] = None,
        min_decay: float = 0.1,
    ) -> List[Memory]: ...

    # ── Graph ─────────────────────────────────────────────────────
    @abstractmethod
    def write_relations(self, relations: List[GraphRelation]) -> bool: ...

    @abstractmethod
    def get_graph_neighbors(
        self, entity: str, depth: int = 2, agent_id: Optional[str] = None
    ) -> List[Dict[str, Any]]: ...

    # ── Domain stats (for normalization) ──────────────────────────
    @abstractmethod
    def get_domain_stats(self, domain: str) -> Dict[str, float]: ...

    @abstractmethod
    def update_domain_stats(self, domain: str, novelty: float) -> None: ...

    # ── Audit ─────────────────────────────────────────────────────
    @abstractmethod
    def write_audit(self, record: AuditRecord) -> bool: ...

    @abstractmethod
    def get_audit_trail(self, memory_id: str) -> List[AuditRecord]: ...

    @abstractmethod
    def verify_integrity(self, memory_id: str) -> IntegrityReport: ...

    # ── Lifecycle ─────────────────────────────────────────────────
    @abstractmethod
    def expire_old(self, agent_id: str, memory_type: MemoryType) -> int: ...

    @abstractmethod
    def get_all(
        self, agent_id: str, memory_type: Optional[MemoryType] = None
    ) -> List[Memory]: ...

"""
SnowMemory Compliance-Native Audit Architecture
Patent-novel: architecturally separated content store and audit ledger.
The audit ledger never stores memory content — only its hash.
Allows compliance verification without content exposure.

Architecture:
  Stream 1 — CONTENT STORE: what was remembered (mutable, decayable)
  Stream 2 — AUDIT LEDGER:  that an operation occurred (immutable)
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..core.models import AuditRecord, IntegrityReport, Memory, OperationType
from ..config.schema import AuditConfig
from ..backends.base import MemoryBackend


class ComplianceAuditLogger:
    """
    Wraps any backend to add a tamper-evident audit trail.
    The audit stream is WRITE-ONLY from the memory system's perspective.
    Content hashes enable integrity verification without content access.
    """

    def __init__(self, config: AuditConfig, backend: MemoryBackend):
        self.config  = config
        self.backend = backend
        # For file-mode: append-only JSONL
        self._log_file: Optional[Path] = None
        if config.backend == "file":
            self._log_file = Path(config.log_file)
            self._log_file.parent.mkdir(parents=True, exist_ok=True)

    def log_write(self, memory: Memory, salience_score: float = 0.0) -> None:
        if not self.config.enabled:
            return
        record = AuditRecord(
            operation=OperationType.WRITE,
            memory_id=memory.memory_id,
            agent_id=memory.agent_id,
            content_hash=memory.content_hash(),   # hash only, never content
            salience_score=salience_score,
            decay_weight=memory.decay_weight,
            session_id=memory.session_id,
            notes=f"type={memory.memory_type.value} domain={memory.domain}",
        )
        self._emit(record)

    def log_read(self, memory_id: str, agent_id: str, memory: Memory) -> None:
        if not self.config.enabled or not self.config.log_reads:
            return
        record = AuditRecord(
            operation=OperationType.READ,
            memory_id=memory_id,
            agent_id=agent_id,
            content_hash=memory.content_hash(),
            decay_weight=memory.decay_weight,
        )
        self._emit(record)

    def log_decay(self, memory: Memory, new_weight: float) -> None:
        if not self.config.enabled:
            return
        record = AuditRecord(
            operation=OperationType.DECAY,
            memory_id=memory.memory_id,
            agent_id=memory.agent_id,
            content_hash=memory.content_hash(),
            decay_weight=new_weight,
            notes=f"decay {memory.decay_weight:.3f}→{new_weight:.3f}",
        )
        self._emit(record)

    def log_resurrect(self, memory: Memory, new_weight: float) -> None:
        if not self.config.enabled:
            return
        record = AuditRecord(
            operation=OperationType.RESURRECT,
            memory_id=memory.memory_id,
            agent_id=memory.agent_id,
            content_hash=memory.content_hash(),
            decay_weight=new_weight,
        )
        self._emit(record)

    def log_inherit(self, memory: Memory, source_agent: str) -> None:
        if not self.config.enabled:
            return
        record = AuditRecord(
            operation=OperationType.INHERIT,
            memory_id=memory.memory_id,
            agent_id=memory.agent_id,
            content_hash=memory.content_hash(),
            notes=f"inherited from {source_agent}",
        )
        self._emit(record)

    # ─────────────────────────────────────────────────────────────
    # Integrity Verification
    # (allows compliance officer to verify without seeing content)
    # ─────────────────────────────────────────────────────────────

    def verify(self, memory_id: str) -> IntegrityReport:
        """
        Verify that memory content has not been altered since write.
        Returns True/False without exposing content to the auditor.
        """
        return self.backend.verify_integrity(memory_id)

    def get_trail(self, memory_id: str) -> List[AuditRecord]:
        return self.backend.get_audit_trail(memory_id)

    def audit_summary(self, agent_id: Optional[str] = None) -> Dict:
        """Return statistics about audit log — no content exposed."""
        memories = self.backend.get_all(agent_id or "", None) if agent_id else []
        total = len(memories)
        return {
            "total_memories": total,
            "audit_enabled": self.config.enabled,
            "reads_logged": self.config.log_reads,
            "backend": self.config.backend,
        }

    # ─────────────────────────────────────────────────────────────
    # Emission
    # ─────────────────────────────────────────────────────────────

    def _emit(self, record: AuditRecord) -> None:
        # Write to backend store
        self.backend.write_audit(record)
        # Also write to file if configured (append-only JSONL)
        if self._log_file:
            with self._log_file.open("a") as f:
                f.write(json.dumps(record.to_dict()) + "\n")

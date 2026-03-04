"""
SnowMemory Core Models
All data structures used across the system.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


# ─────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────

class MemoryType(str, Enum):
    WORKING      = "WORKING"       # ephemeral, session-scoped
    EXPERIENTIAL = "EXPERIENTIAL"  # learned from past runs, decays
    FACTUAL      = "FACTUAL"       # stable world knowledge, versioned


class OperationType(str, Enum):
    WRITE     = "WRITE"
    READ      = "READ"
    DECAY     = "DECAY"
    RESURRECT = "RESURRECT"
    INHERIT   = "INHERIT"
    DELETE    = "DELETE"
    EXPIRE    = "EXPIRE"


class MemoryStatus(str, Enum):
    ACTIVE               = "ACTIVE"
    DECAYED              = "DECAYED"
    EXPIRED              = "EXPIRED"
    FLAGGED_CONTRADICTION = "FLAGGED_CONTRADICTION"
    INHERITED            = "INHERITED"
    RESURRECTED          = "RESURRECTED"


# ─────────────────────────────────────────────
# Provenance
# ─────────────────────────────────────────────

@dataclass
class ProvenanceEntry:
    event:           str                       # WRITE | INHERIT | RESURRECT | DECAY
    agent_id:        str
    timestamp:       datetime = field(default_factory=datetime.utcnow)
    confidence_at:   float    = 1.0
    decay_applied:   float    = 0.0
    notes:           str      = ""


# ─────────────────────────────────────────────
# Core Memory Object
# ─────────────────────────────────────────────

@dataclass
class Memory:
    content:          str
    agent_id:         str
    memory_type:      MemoryType

    memory_id:        str                    = field(default_factory=lambda: str(uuid.uuid4()))
    session_id:       Optional[str]          = None
    embedding:        Optional[List[float]]  = None
    entities:         List[str]              = field(default_factory=list)
    domain:           str                    = "general"

    # Salience tracking
    surprise_score:   float                  = 0.0
    novelty_score:    float                  = 0.0
    orphan_score:     float                  = 0.0
    bridge_score:     float                  = 0.0

    # Lifecycle
    confidence:       float                  = 1.0
    decay_weight:     float                  = 1.0
    access_count:     int                    = 0
    status:           MemoryStatus           = MemoryStatus.ACTIVE
    version:          int                    = 1

    # Timestamps
    created_at:       datetime               = field(default_factory=datetime.utcnow)
    last_accessed_at: Optional[datetime]     = None
    expires_at:       Optional[datetime]     = None

    # Provenance chain (cross-agent inheritance)
    provenance:       List[ProvenanceEntry]  = field(default_factory=list)

    # Contradiction tracking
    contradiction_ref: Optional[str]         = None

    # Flexible metadata
    metadata:         Dict[str, Any]         = field(default_factory=dict)

    def effective_weight(self) -> float:
        """Combined score for retrieval ranking."""
        return self.decay_weight * self.confidence

    def content_hash(self) -> str:
        """SHA-256 hash of content for compliance integrity checks."""
        import hashlib
        return hashlib.sha256(self.content.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id":        self.memory_id,
            "content":          self.content,
            "agent_id":         self.agent_id,
            "memory_type":      self.memory_type.value,
            "session_id":       self.session_id,
            "entities":         self.entities,
            "domain":           self.domain,
            "surprise_score":   self.surprise_score,
            "novelty_score":    self.novelty_score,
            "orphan_score":     self.orphan_score,
            "bridge_score":     self.bridge_score,
            "confidence":       self.confidence,
            "decay_weight":     self.decay_weight,
            "access_count":     self.access_count,
            "status":           self.status.value,
            "version":          self.version,
            "created_at":       self.created_at.isoformat(),
            "last_accessed_at": self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            "expires_at":       self.expires_at.isoformat() if self.expires_at else None,
            "metadata":         self.metadata,
        }


# ─────────────────────────────────────────────
# Input / Output Types
# ─────────────────────────────────────────────

@dataclass
class MemoryEvent:
    """Raw event submitted by an agent for potential storage."""
    content:    str
    agent_id:   str
    session_id: Optional[str]      = None
    domain:     Optional[str]      = None
    metadata:   Dict[str, Any]     = field(default_factory=dict)
    timestamp:  datetime           = field(default_factory=datetime.utcnow)


@dataclass
class QueryContext:
    text:          str
    agent_id:      str
    session_id:    Optional[str]      = None
    top_k:         int                = 10
    memory_types:  Optional[List[MemoryType]] = None
    include_graph: bool               = True
    graph_depth:   int                = 2
    min_decay:     float              = 0.1   # exclude nearly-fully-decayed
    metadata:      Dict[str, Any]     = field(default_factory=dict)


@dataclass
class WriteResult:
    written:         bool
    memory_id:       Optional[str]  = None
    reason:          str            = ""
    surprise_score:  float          = 0.0
    novelty_score:   float          = 0.0
    orphan_score:    float          = 0.0
    threshold_used:  float          = 0.0


@dataclass
class SalienceScore:
    score:              float
    novelty:            float          = 0.0
    temporal_gap:       float          = 0.0
    orphan_score:       float          = 0.0
    access_inv:         float          = 0.0
    momentum:           float          = 0.0
    domain:             str            = "general"
    nearest_ids:        List[str]      = field(default_factory=list)
    bridge_score:       float          = 0.0


@dataclass
class GraphRelation:
    from_entity:   str
    relation_type: str
    to_entity:     str
    confidence:    float          = 1.0
    memory_id:     Optional[str]  = None


@dataclass
class GraphPayload:
    entities:  List[str]           = field(default_factory=list)
    relations: List[GraphRelation] = field(default_factory=list)


# ─────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────

@dataclass
class AuditRecord:
    operation:      OperationType
    memory_id:      str
    agent_id:       str
    content_hash:   str
    timestamp:      datetime       = field(default_factory=datetime.utcnow)
    salience_score: float          = 0.0
    decay_weight:   float          = 1.0
    session_id:     Optional[str]  = None
    notes:          str            = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation":      self.operation.value,
            "memory_id":      self.memory_id,
            "agent_id":       self.agent_id,
            "content_hash":   self.content_hash,
            "timestamp":      self.timestamp.isoformat(),
            "salience_score": self.salience_score,
            "decay_weight":   self.decay_weight,
            "session_id":     self.session_id,
            "notes":          self.notes,
        }


@dataclass
class IntegrityReport:
    memory_id:               str
    content_hash_matches:    bool
    original_write_timestamp: datetime
    operation_count:         int
    current_hash:            str
    stored_hash:             str

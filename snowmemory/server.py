"""
SnowMemory API Server
FastAPI wrapper around the SnowMemory Python backend.
Serves the React playground UI and all memory API endpoints.

Run: python server.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from snowmemory import (
    MemoryOrchestrator, MemoryConfig, MemoryEvent,
    QueryContext, MemoryType,
)
from snowmemory.core.models import Memory, MemoryStatus
from snowmemory.inheritance.protocol import InheritanceFilter

# ─────────────────────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────────────────────
app = FastAPI(title="SnowMemory API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global orchestrators (keyed by agent_id)
_orchestrators: Dict[str, MemoryOrchestrator] = {}

def get_orchestrator(agent_id: str) -> MemoryOrchestrator:
    if agent_id not in _orchestrators:
        config = MemoryConfig(agent_id=agent_id)
        _orchestrators[agent_id] = MemoryOrchestrator(config)
    return _orchestrators[agent_id]

# ─────────────────────────────────────────────────────────────
# Pydantic request/response models
# ─────────────────────────────────────────────────────────────

class WriteRequest(BaseModel):
    content:    str
    agent_id:   str = "demo_agent"
    session_id: Optional[str] = None
    domain:     Optional[str] = None
    metadata:   Dict[str, Any] = {}

class QueryRequest(BaseModel):
    text:          str
    agent_id:      str = "demo_agent"
    top_k:         int = 10
    memory_types:  Optional[List[str]] = None
    include_graph: bool = True
    graph_depth:   int  = 2
    min_decay:     float = 0.05

class DecayRequest(BaseModel):
    agent_id: str = "demo_agent"

class InheritRequest(BaseModel):
    source_agent_id: str
    target_agent_id: str
    inheritance_decay: float = 0.80
    min_salience: float = 0.0

class FeedbackRequest(BaseModel):
    memory_id: str
    agent_id:  str = "demo_agent"
    was_used:  bool = True

class GraphQueryRequest(BaseModel):
    entity:   str
    agent_id: str = "demo_agent"
    depth:    int = 2

class ThresholdRequest(BaseModel):
    agent_id:  str = "demo_agent"
    threshold: float

# ─────────────────────────────────────────────────────────────
# Helper: serialize Memory to dict
# ─────────────────────────────────────────────────────────────

def serialize_memory(m: Memory) -> Dict[str, Any]:
    return {
        "id":            m.memory_id,
        "content":       m.content,
        "agent_id":      m.agent_id,
        "memory_type":   m.memory_type.value,
        "session_id":    m.session_id,
        "domain":        m.domain,
        "entities":      m.entities,
        "surprise_score": m.surprise_score,
        "novelty_score": m.novelty_score,
        "orphan_score":  m.orphan_score,
        "bridge_score":  m.bridge_score,
        "confidence":    m.confidence,
        "decay_weight":  m.decay_weight,
        "access_count":  m.access_count,
        "status":        m.status.value,
        "version":       m.version,
        "created_at":    m.created_at.isoformat(),
        "last_accessed_at": m.last_accessed_at.isoformat() if m.last_accessed_at else None,
        "expires_at":    m.expires_at.isoformat() if m.expires_at else None,
        "metadata":      m.metadata,
        "provenance":    [
            {"event": p.event, "agent_id": p.agent_id,
             "confidence_at": p.confidence_at, "notes": p.notes}
            for p in m.provenance
        ],
    }

def serialize_audit(r) -> Dict[str, Any]:
    return {
        "operation":      r.operation.value,
        "memory_id":      r.memory_id,
        "agent_id":       r.agent_id,
        "content_hash":   r.content_hash[:16] + "…",
        "timestamp":      r.timestamp.isoformat(),
        "salience_score": r.salience_score,
        "decay_weight":   r.decay_weight,
        "session_id":     r.session_id,
        "notes":          r.notes,
    }

# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/write")
def write_memory(req: WriteRequest):
    """Write a memory event through the full CSS salience pipeline."""
    m      = get_orchestrator(req.agent_id)
    event  = MemoryEvent(
        content=req.content,
        agent_id=req.agent_id,
        session_id=req.session_id,
        domain=req.domain,
        metadata=req.metadata,
    )
    result = m.write(event)
    return {
        "written":        result.written,
        "memory_id":      result.memory_id,
        "reason":         result.reason,
        "surprise_score": result.surprise_score,
        "novelty_score":  result.novelty_score,
        "orphan_score":   result.orphan_score,
        "threshold_used": result.threshold_used,
    }


@app.post("/query")
def query_memories(req: QueryRequest):
    """Query memories by semantic similarity with hybrid graph expansion."""
    m = get_orchestrator(req.agent_id)
    types = [MemoryType(t) for t in req.memory_types] if req.memory_types else None
    ctx   = QueryContext(
        text=req.text,
        agent_id=req.agent_id,
        top_k=req.top_k,
        memory_types=types,
        include_graph=req.include_graph,
        graph_depth=req.graph_depth,
        min_decay=req.min_decay,
    )
    results = m.query(ctx)
    return {"results": [serialize_memory(mem) for mem in results], "count": len(results)}


@app.get("/memories/{agent_id}")
def get_memories(agent_id: str, memory_type: Optional[str] = None):
    """Get all memories for an agent, optionally filtered by type."""
    m       = get_orchestrator(agent_id)
    backend = m._backend
    mtype   = MemoryType(memory_type) if memory_type else None
    mems    = backend.get_all(agent_id, mtype)
    return {"memories": [serialize_memory(mem) for mem in mems], "count": len(mems)}


@app.get("/memory/{agent_id}/{memory_id}")
def get_memory(agent_id: str, memory_id: str):
    """Get a single memory by ID."""
    m      = get_orchestrator(agent_id)
    mem    = m._backend.get(memory_id)
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    return serialize_memory(mem)


@app.post("/decay")
def apply_decay(req: DecayRequest):
    """Apply decay to all experiential memories."""
    m       = get_orchestrator(req.agent_id)
    updated = m.run_decay()
    return {"updated": updated, "agent_id": req.agent_id}


@app.post("/feedback")
def record_feedback(req: FeedbackRequest):
    """Record retrieval feedback for adaptive threshold calibration."""
    m = get_orchestrator(req.agent_id)
    m.record_retrieval_feedback(req.memory_id, req.was_used)
    return {"ok": True}


@app.post("/graph/query")
def graph_query(req: GraphQueryRequest):
    """Traverse the knowledge graph for an entity."""
    m       = get_orchestrator(req.agent_id)
    results = m.graph_query(req.entity, req.agent_id, req.depth)
    return {"relations": results, "count": len(results)}


@app.get("/graph/all/{agent_id}")
def get_all_relations(agent_id: str):
    """Get all graph relations for an agent."""
    m      = get_orchestrator(agent_id)
    rels   = m._backend._relations  # in-memory backend exposes this directly
    result = [
        {"from": r.from_entity, "type": r.relation_type,
         "to": r.to_entity, "confidence": r.confidence, "memId": r.memory_id}
        for r in rels.values()
    ]
    return {"relations": result, "count": len(result)}


@app.post("/inherit")
def inherit_memories(req: InheritRequest):
    """Transfer memories between agents with provenance tracking."""
    target = get_orchestrator(req.target_agent_id)
    # Ensure source orchestrator exists
    get_orchestrator(req.source_agent_id)
    # Share backend between them for inheritance
    from snowmemory.inheritance.protocol import MemoryInheritanceProtocol, InheritanceFilter
    from snowmemory.config.schema import InheritanceConfig
    protocol = MemoryInheritanceProtocol(
        InheritanceConfig(default_decay=req.inheritance_decay, min_salience=req.min_salience),
        target._backend,
    )
    f = InheritanceFilter(
        min_salience=req.min_salience,
        inheritance_decay=req.inheritance_decay,
    )
    report = protocol.inherit(
        source_agent_id=req.source_agent_id,
        target_agent_id=req.target_agent_id,
        filter=f,
    )
    return {
        "inherited_count":      report.inherited_count,
        "contradictions_found": report.contradictions_found,
        "total_candidates":     report.total_candidates,
    }


@app.post("/verify/{memory_id}")
def verify_integrity(memory_id: str, agent_id: str = "demo_agent"):
    """Verify memory content integrity via hash comparison."""
    m      = get_orchestrator(agent_id)
    report = m.verify_integrity(memory_id)
    return {
        "memory_id":               report.memory_id,
        "content_hash_matches":    report.content_hash_matches,
        "original_write_timestamp": report.original_write_timestamp.isoformat(),
        "operation_count":         report.operation_count,
        "current_hash":            report.current_hash[:16] + "…",
        "stored_hash":             report.stored_hash[:16] + "…",
    }


@app.get("/audit/{agent_id}")
def get_audit_log(agent_id: str, limit: int = 100):
    """Get audit trail for all memories of an agent."""
    m       = get_orchestrator(agent_id)
    backend = m._backend
    records = []
    for mid, recs in backend._audit.items():
        for r in recs:
            records.append(serialize_audit(r))
    records.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"records": records[:limit], "count": len(records)}


@app.get("/stats/{agent_id}")
def get_stats(agent_id: str):
    """Get memory statistics for an agent."""
    m = get_orchestrator(agent_id)
    s = m.stats()
    return s


@app.post("/threshold")
def set_threshold(req: ThresholdRequest):
    """Manually override the adaptive write threshold."""
    m = get_orchestrator(req.agent_id)
    m._gate.threshold = max(0.05, min(0.80, req.threshold))
    return {"threshold": m._gate.threshold}


@app.get("/threshold/{agent_id}")
def get_threshold(agent_id: str):
    m = get_orchestrator(agent_id)
    return {"threshold": m._gate.threshold, "stats": m._gate.stats}


@app.delete("/memories/{agent_id}")
def clear_memories(agent_id: str):
    """Clear all memories for an agent (playground reset)."""
    if agent_id in _orchestrators:
        del _orchestrators[agent_id]
    return {"ok": True, "agent_id": agent_id}


@app.get("/agents")
def list_agents():
    """List all active agent IDs."""
    return {"agents": list(_orchestrators.keys())}


# ─────────────────────────────────────────────────────────────
# Serve the React UI (index.html in /ui directory)
# ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    ui_path = os.path.join(os.path.dirname(__file__), "ui", "index.html")
    if os.path.exists(ui_path):
        with open(ui_path) as f:
            return f.read()
    return HTMLResponse("<h1>UI not built. Run: cd ui && npm install && npm run build</h1>")


if __name__ == "__main__":
    import uvicorn
    print("🧠 SnowMemory API starting on http://localhost:8000")
    print("📖 API docs at http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)

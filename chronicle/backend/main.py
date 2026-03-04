"""
Chronicle Backend — FastAPI wrapper around SnowMemory
Run: uvicorn main:app --reload --port 8000
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os

from snowmemory import MemoryOrchestrator, MemoryConfig, MemoryEvent, QueryContext

app = FastAPI(title="Chronicle API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store of orchestrators per user (persisted via DuckDB in prod)
_orchestrators: dict = {}

def get_memory(user_id: str) -> MemoryOrchestrator:
    if user_id not in _orchestrators:
        _orchestrators[user_id] = MemoryOrchestrator(
            MemoryConfig(agent_id=user_id)
        )
    return _orchestrators[user_id]


# ── Request Models ────────────────────────────────────────────────────────────

class IngestTextRequest(BaseModel):
    content: str
    source: Optional[str] = "paste"   # paste | notion | obsidian | file

class QueryRequest(BaseModel):
    text: str
    top_k: Optional[int] = 5


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "Chronicle API running", "version": "1.0.0"}

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest/text/{user_id}")
def ingest_text(user_id: str, req: IngestTextRequest):
    """Ingest plain text or pasted content."""
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")
    
    memory = get_memory(user_id)
    result = memory.write(MemoryEvent(
        content=req.content,
        agent_id=user_id,
        metadata={"source": req.source}
    ))
    return {
        "written": result.written,
        "surprise_score": round(result.surprise_score, 3),
        "novelty_score": round(result.novelty_score, 3),
        "memory_id": result.memory_id,
        "message": "Stored" if result.written else "Skipped (low novelty — similar memory already exists)"
    }


@app.post("/ingest/file/{user_id}")
async def ingest_file(user_id: str, file: UploadFile = File(...)):
    """Ingest uploaded file (txt, md, pdf)."""
    allowed = [".txt", ".md", ".markdown", ".pdf"]
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {allowed}"
        )
    
    content_bytes = await file.read()
    
    # Basic PDF text extraction (no external dep needed for MVP)
    if ext == ".pdf":
        try:
            import pdfplumber
            import io
            with pdfplumber.open(io.BytesIO(content_bytes)) as pdf:
                content = "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                )
        except ImportError:
            # Fallback: treat as text
            content = content_bytes.decode("utf-8", errors="ignore")
    else:
        content = content_bytes.decode("utf-8", errors="ignore")

    if not content.strip():
        raise HTTPException(status_code=400, detail="File appears to be empty or unreadable")

    # Split large files into chunks (2000 chars each) for better salience scoring
    chunks = _chunk_text(content, chunk_size=2000, overlap=200)
    
    memory   = get_memory(user_id)
    written  = 0
    skipped  = 0
    
    for chunk in chunks:
        result = memory.write(MemoryEvent(
            content=chunk,
            agent_id=user_id,
            metadata={"source": "file", "filename": file.filename}
        ))
        if result.written:
            written += 1
        else:
            skipped += 1

    return {
        "filename": file.filename,
        "chunks_total": len(chunks),
        "chunks_written": written,
        "chunks_skipped": skipped,
        "message": f"Processed {file.filename}: {written} new memories stored, {skipped} skipped as duplicates"
    }


@app.post("/query/{user_id}")
def query(user_id: str, req: QueryRequest):
    """Query memory — returns most relevant past notes for current context."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Query text cannot be empty")
    
    memory  = get_memory(user_id)
    results = memory.query(QueryContext(
        text=req.text,
        agent_id=user_id,
        top_k=req.top_k,
    ))
    
    return {
        "query": req.text,
        "results": [
            {
                "content":       r.content,
                "score":         round(r.surprise_score, 3),
                "decay_weight":  round(r.decay_weight, 3),
                "domain":        r.domain,
                "memory_type":   r.memory_type.value,
                "memory_id":     r.memory_id,
            }
            for r in results
        ],
        "count": len(results)
    }


@app.get("/stats/{user_id}")
def stats(user_id: str):
    """Get memory stats for a user."""
    memory   = get_memory(user_id)
    all_mems = memory._backend.get_all(user_id)
    
    from collections import Counter
    type_counts   = Counter(m.memory_type.value  for m in all_mems)
    domain_counts = Counter(m.domain             for m in all_mems)
    
    return {
        "user_id":      user_id,
        "total":        len(all_mems),
        "by_type":      dict(type_counts),
        "by_domain":    dict(domain_counts),
        "free_limit":   50,
        "is_pro":       False,   # wire to Stripe in production
    }


@app.delete("/memory/{user_id}/{memory_id}")
def delete_memory(user_id: str, memory_id: str):
    """Delete a specific memory."""
    memory = get_memory(user_id)
    ok     = memory._backend.delete(memory_id)
    return {"deleted": ok, "memory_id": memory_id}


@app.delete("/reset/{user_id}")
def reset_user(user_id: str):
    """Clear all memories for a user (dev/testing use)."""
    if user_id in _orchestrators:
        del _orchestrators[user_id]
    return {"reset": True, "user_id": user_id}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> list:
    """Split text into overlapping chunks for better memory granularity."""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start  = 0
    while start < len(text):
        end   = start + chunk_size
        chunk = text[start:end]
        # Try to break at paragraph boundary
        last_para = chunk.rfind("\n\n")
        if last_para > chunk_size // 2:
            chunk = chunk[:last_para]
            end   = start + last_para
        chunks.append(chunk.strip())
        start = end - overlap
    
    return [c for c in chunks if len(c.strip()) > 50]

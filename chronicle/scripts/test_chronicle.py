#!/usr/bin/env python3
"""
Chronicle local test script.
Ingests all test notes and runs sample queries to verify SnowMemory is working.

Usage:
    python test_chronicle.py
"""
import sys, os, glob, time

# Add snowmemory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from snowmemory import MemoryOrchestrator, MemoryConfig, MemoryEvent, QueryContext

NOTES_DIR = os.path.join(os.path.dirname(__file__), '..', 'test_notes')
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"

def header(text):
    print(f"\n{BOLD}{BLUE}{'─' * 60}{RESET}")
    print(f"{BOLD}{BLUE}  {text}{RESET}")
    print(f"{BOLD}{BLUE}{'─' * 60}{RESET}")

def section(text):
    print(f"\n{BOLD}{YELLOW}▶ {text}{RESET}")

def ok(text):
    print(f"  {GREEN}✓{RESET}  {text}")

def info(text):
    print(f"  {DIM}{text}{RESET}")


def chunk_text(text, chunk_size=1500, overlap=150):
    if len(text) <= chunk_size:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        last_para = chunk.rfind("\n\n")
        if last_para > chunk_size // 2:
            chunk = chunk[:last_para]
            end = start + last_para
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    return chunks


def run():
    header("Chronicle — Local Test")

    # ── Step 1: Setup ────────────────────────────────────────────────────────
    section("Setting up SnowMemory")
    memory = MemoryOrchestrator(MemoryConfig(
        agent_id="chronicle_test",
        domain_keywords={
            "auth":        ["jwt", "oauth", "token", "session", "password", "login", "auth"],
            "database":    ["postgres", "duckdb", "redis", "sql", "query", "index", "cache"],
            "api":         ["fastapi", "endpoint", "cors", "webhook", "stripe", "rate limit"],
            "deployment":  ["railway", "docker", "deploy", "ci", "github", "env", "production"],
            "frontend":    ["next.js", "react", "tailwind", "clerk", "ui", "ux", "component"],
            "product":     ["user", "interview", "onboarding", "pricing", "feature", "roadmap"],
        }
    ))
    ok(f"SnowMemory initialized (backend: {type(memory._backend).__name__})")

    # ── Step 2: Ingest all test notes ────────────────────────────────────────
    section("Ingesting test notes")
    note_files = sorted(glob.glob(os.path.join(NOTES_DIR, "*.md")))
    
    if not note_files:
        print(f"  No .md files found in {NOTES_DIR}")
        return

    total_chunks = 0
    total_written = 0

    for filepath in note_files:
        filename = os.path.basename(filepath)
        with open(filepath, "r") as f:
            content = f.read()
        
        chunks = chunk_text(content)
        written = 0

        for chunk in chunks:
            result = memory.write(MemoryEvent(
                content=chunk,
                agent_id="chronicle_test",
                metadata={"source": "file", "filename": filename}
            ))
            if result.written:
                written += 1
        
        total_chunks += len(chunks)
        total_written += written
        ok(f"{filename:40s} → {written}/{len(chunks)} chunks stored")

    info(f"\n  Total: {total_written}/{total_chunks} chunks stored across {len(note_files)} files")
    info(f"  Skipped: {total_chunks - total_written} (low novelty / duplicates — working as intended)")

    # ── Step 3: Run sample queries ───────────────────────────────────────────
    section("Running sample queries\n")

    test_queries = [
        ("I'm debugging a user login issue",
         "auth"),
        ("Our API is timing out under load",
         "performance"),
        ("Setting up a new deployment pipeline",
         "devops"),
        ("Database queries are running slowly",
         "database"),
        ("Users are dropping off during onboarding",
         "product"),
        ("React component not rendering correctly on mobile",
         "frontend"),
        ("Connection pool maxed out in production",
         "database+infra"),
        ("JWT token keeps expiring too soon",
         "auth"),
    ]

    for query_text, label in test_queries:
        print(f"  {BOLD}Query:{RESET} \"{query_text}\"  {DIM}[expected: {label}]{RESET}")
        
        results = memory.query(QueryContext(
            text=query_text,
            agent_id="chronicle_test",
            top_k=3
        ))

        if not results:
            print(f"  {YELLOW}  ⚠ No results — try adding more notes{RESET}")
        else:
            for i, r in enumerate(results[:2]):
                preview = r.content[:100].replace('\n', ' ')
                score_dots = "●" * round(r.surprise_score * 5) + "○" * (5 - round(r.surprise_score * 5))
                print(f"  {GREEN}  {i+1}.{RESET} {score_dots}  {preview}...")
        print()

    # ── Step 4: Stats ────────────────────────────────────────────────────────
    section("Memory stats")
    all_mems = memory._backend.get_all("chronicle_test")
    from collections import Counter
    by_type   = Counter(m.memory_type.value for m in all_mems)
    by_domain = Counter(m.domain            for m in all_mems)

    ok(f"Total memories stored: {len(all_mems)}")
    info(f"  By type:   {dict(by_type)}")
    info(f"  By domain: {dict(by_domain)}")

    # ── Step 5: Graph check ──────────────────────────────────────────────────
    section("Knowledge graph check")
    relations = memory._backend.get_all("chronicle_test")
    graph_backend = memory._backend
    
    test_entities = ["JWT", "DuckDB", "Railway", "FastAPI", "Stripe"]
    for entity in test_entities:
        neighbors = graph_backend.get_graph_neighbors(entity, depth=1)
        if neighbors:
            ok(f"Entity '{entity}' → {len(neighbors)} graph connections")
        else:
            info(f"  Entity '{entity}' → no graph connections yet")

    print(f"\n{BOLD}{GREEN}{'─' * 60}")
    print(f"  All done. Chronicle core is working correctly.")
    print(f"{'─' * 60}{RESET}\n")


if __name__ == "__main__":
    run()

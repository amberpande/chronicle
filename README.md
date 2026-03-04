# Chronicle + SnowMemory

> Your second brain, but with actual memory.

Chronicle surfaces relevant past notes automatically — no searching, no prompting.
Built on SnowMemory: a patent-pending AI agent memory engine with compound salience scoring,
decay resurrection, and cross-agent knowledge inheritance.

---

## Quick Start (Mac Silicon)

```bash
# 1. Run setup once — installs everything
bash setup.sh

# 2. Every new terminal session:
source activate.sh

# 3. Start both servers
cd chronicle && npm run dev

# 4. Open in browser
# Frontend:  http://localhost:3000
# API docs:  http://localhost:8000/docs
```

That's it. The setup script handles Python venv, all pip packages, Node packages, and Next.js.

---

## Project Structure

```
chronicle_project/
│
├── setup.sh              ← Run this first (once)
├── activate.sh           ← Run this every new terminal session
├── requirements.txt      ← Python dependencies
│
├── snowmemory/           ← The AI memory engine (already built)
│   ├── core/             ← Orchestrator, models, salience engine
│   ├── backends/         ← InMemory, Snowflake, Cortex backends
│   ├── graph/            ← Entity + relation extraction
│   ├── salience/         ← Compound Salience Score + adaptive threshold
│   ├── decay/            ← Decay engine + resurrection
│   ├── inheritance/      ← Cross-agent memory inheritance
│   ├── audit/            ← Compliance-native hash audit
│   ├── config/           ← YAML config schema
│   └── demo.py           ← 68-test suite across 4 domains
│
└── chronicle/            ← The product
    ├── backend/
    │   └── main.py       ← FastAPI server (7 endpoints)
    ├── frontend/         ← Next.js app (created by setup.sh)
    ├── test_notes/       ← 8 developer note files for testing
    │   ├── 01_auth_notes.md
    │   ├── 02_database_notes.md
    │   ├── 03_api_notes.md
    │   ├── 04_devops_notes.md
    │   ├── 05_frontend_notes.md
    │   ├── 06_product_notes.md
    │   ├── 07_bugs_incidents.md
    │   └── 08_architecture_notes.md
    ├── scripts/
    │   └── test_chronicle.py   ← Test runner
    ├── .env.example            ← Backend env template
    └── .env.local.example      ← Frontend env template
```

---

## API Endpoints

Once the backend is running at `http://localhost:8000`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/health` | Health check |
| `POST` | `/ingest/text/{user_id}` | Ingest text or pasted content |
| `POST` | `/ingest/file/{user_id}` | Upload .md, .txt, or .pdf file |
| `POST` | `/query/{user_id}` | Query — surface relevant memories |
| `GET`  | `/stats/{user_id}` | Memory stats for a user |
| `DELETE` | `/memory/{user_id}/{memory_id}` | Delete a specific memory |
| `DELETE` | `/reset/{user_id}` | Clear all memories (dev use) |

Full interactive docs at: `http://localhost:8000/docs`

---

## Test the Memory Engine

```bash
# After running setup.sh and source activate.sh:
python3 chronicle/scripts/test_chronicle.py
```

This ingests all 8 test note files and runs 8 sample queries.
You should see the JWT query surface the JWT bug note as result #1 — that's the magic moment.

---

## Useful Commands

```bash
# Activate environment (every new terminal)
source activate.sh

# Run SnowMemory full test suite (68 tests)
cd snowmemory && python3 demo.py --all

# Run Chronicle memory test
python3 chronicle/scripts/test_chronicle.py

# Start API only
cd chronicle/backend && uvicorn main:app --reload --port 8000

# Start frontend only
cd chronicle/frontend && npm run dev

# Start both together
cd chronicle && npm run dev

# Quick API test
curl http://localhost:8000/health
curl -X POST http://localhost:8000/ingest/text/me \
  -H "Content-Type: application/json" \
  -d '{"content": "Your note here"}'
curl -X POST http://localhost:8000/query/me \
  -H "Content-Type: application/json" \
  -d '{"text": "what you are working on"}'
```

---

## Environment Setup

**Backend** — copy and fill in:
```bash
cp chronicle/.env.example chronicle/.env
```

**Frontend** — copy and fill in:
```bash
cp chronicle/.env.local.example chronicle/frontend/.env.local
```

Get free Clerk keys at [clerk.com](https://clerk.com) (needed for auth).
Get free Stripe keys at [stripe.com](https://stripe.com) (needed for payments).

---

## Next Steps After Setup

1. Run `python3 chronicle/scripts/test_chronicle.py` — verify memory works
2. Feed your own notes into it via the API
3. Build the Chronicle UI in `chronicle/frontend/`
4. Get Clerk keys and wire up auth
5. Launch 🚀

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Memory engine | SnowMemory (Python, patent-pending) |
| Backend API | FastAPI + uvicorn |
| Local storage | DuckDB (zero infra, persists to disk) |
| Frontend | Next.js 14 + Tailwind CSS |
| Auth | Clerk |
| Payments | Stripe |
| Production deploy | Railway (backend) + Vercel (frontend) |
| Enterprise backend | Snowflake + Cortex AI (optional upgrade) |

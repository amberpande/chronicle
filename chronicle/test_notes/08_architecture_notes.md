# Architecture Decisions & Future Plans

## Why DuckDB Not SQLite for Local Storage — 2024-06-22
Both are embedded, zero-server databases. DuckDB wins for our use case.
Reason 1: DuckDB handles ARRAY columns natively — needed for embeddings.
Reason 2: DuckDB has VECTOR type support via extensions — upgrade path to native ANN.
Reason 3: Analytical query performance is 10-100x faster for aggregations.
SQLite is better for: OLTP, mobile, very simple key-value storage.
DuckDB is better for: analytical queries, vector data, columnar storage.
Migration path: DuckDB → Snowflake when user base grows. Zero code change needed.

## Monorepo vs Separate Repos Decision — 2024-07-03
Chose monorepo: `frontend/` and `backend/` in same repository.
Reason: solo developer — context switching between repos is friction.
Tooling: single `package.json` at root for scripts. `npm run dev` starts both.
`concurrently` package runs Next.js and FastAPI in parallel.
When to split: when you have separate teams or deployment pipelines diverge significantly.

## The Memory Persistence Hierarchy — 2024-07-30
Designed three-tier storage approach for scale:
Tier 1: In-process dict — fastest, lost on restart. Fine for development.
Tier 2: DuckDB on disk — fast, persistent, single-node. Good for up to 100k users.
Tier 3: Snowflake with Cortex — petabyte scale, multi-region, enterprise.
Current: Tier 1 in dev, Tier 2 in production.
Upgrade trigger: when DuckDB file exceeds 10GB or we need multi-instance deployment.
Zero code changes needed to upgrade — just swap backend in config.

## Multi-Tenancy Architecture — 2024-08-18
Each user's memories are fully isolated via `agent_id = user_id`.
No cross-contamination possible at query level.
Future team feature: shared `agent_id` for team workspace + personal `agent_id`.
Cross-agent inheritance: team inherits from members with confidence decay.
This is already built in SnowMemory — just needs a team management UI.

## AI Model Strategy — 2024-09-25
Current: local sentence-transformers (all-MiniLM-L6-v2, 384 dims).
Free, private, runs on CPU, 80MB model file.
Quality: good enough for English content. Struggles with code and multilingual.
Upgrade path:
- Better quality: OpenAI text-embedding-3-small ($0.02/1M tokens)
- Enterprise: Snowflake Cortex EMBED_TEXT (runs inside warehouse, data never leaves)
- Multilingual: multilingual-e5-large (local, 560MB, 100+ languages)
Decision: keep local model until users request better quality or multilingual support.

## Roadmap Q1 2025 — 2024-10-28
P0 (must have):
- Notion integration (API-based sync, not file export)
- Obsidian plugin (reads vault directly, real-time sync)
- Better onboarding flow (guided first-upload experience)

P1 (should have):
- Team workspaces (shared memory + personal memory)
- Mobile app (React Native, read-only v1)
- VS Code extension (sidebar with context-aware surfacing)

P2 (nice to have):
- Slack integration (capture notes from messages)
- Browser extension (capture from any webpage)
- Snowflake backend (enterprise tier at $99/month)

Not doing:
- Chat interface (that's what ChatGPT is for)
- Note editor (that's what Notion/Obsidian is for)
- Document summarisation (not our core value prop)

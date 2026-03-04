# Database & Performance Notes

## Postgres Connection Pool Exhaustion — 2024-07-11
Production went down for 8 minutes. Root cause: connection pool maxed out at 10.
Every API request was opening a new connection and not closing it properly.
Fix: Set `max_connections=50` in `db/config.py`, added connection pooling via `pgbouncer`.
Also added `finally` block in all DB query functions to ensure connections close.
Lesson: always use context managers for DB connections. Never open manually.

## Slow Query on Memory Search — 2024-08-03
`/query` endpoint timing out for users with 500+ memories. P95 latency was 4200ms.
Root cause: full table scan on `agent_memories` — no index on `agent_id`.
Fix: Added composite index on `(agent_id, decay_weight)`.
Result: P95 dropped to 180ms. 23x improvement.
SQL: `CREATE INDEX idx_memories_agent ON agent_memories (agent_id, decay_weight);`

## DuckDB File Lock Issue on Restart — 2024-08-19
App crashing on restart with `Database is locked` error.
Root cause: DuckDB file not being released cleanly on SIGTERM.
Fix: Added graceful shutdown handler in `main.py`.
```python
import signal
def shutdown(sig, frame):
    for orch in _orchestrators.values():
        orch._backend._conn.close()
    sys.exit(0)
signal.signal(signal.SIGTERM, shutdown)
```

## N+1 Query Problem in Stats Endpoint — 2024-09-07
`/stats/:userId` was firing one SQL query per memory to get type counts.
For users with 200 memories, this was 201 queries per request.
Fix: Replaced with single aggregation query using GROUP BY.
Before: 1800ms average. After: 12ms average.
Rule: never query inside a loop. Always aggregate at DB layer.

## Redis Cache Stampede on Cold Start — 2024-10-14
After deployment, first 30 seconds had 10x normal DB load.
Root cause: all cache keys expired simultaneously (same TTL set on deploy).
Fix: Added jitter to TTL — `ttl = base_ttl + random.randint(0, 300)`.
Also added cache warming step in deployment script.
Monitor cache hit rate — should be above 85% during normal operation.

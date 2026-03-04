# Bug Reports & Incident Log

## INCIDENT: Complete Outage 45 Minutes — 2024-08-30
Timeline:
- 14:23 UTC: Spike in error rate, PagerDuty fires
- 14:25 UTC: Investigated — Railway instance OOM (out of memory) killed
- 14:31 UTC: Root cause found: memory leak in SnowMemory orchestrator dict
- 14:47 UTC: Hotfix deployed, service restored
- 15:08 UTC: Post-mortem written

Root cause: orchestrators dict grew unboundedly — one entry per user_id, never evicted.
With 800 users each having in-memory embeddings, RAM hit 512MB limit.
Fix: Added LRU cache with max 200 entries. Evict oldest on overflow.
Prevention: added memory usage metric to Railway dashboard. Alert at 400MB.

## BUG: Emoji in Notes Breaking DuckDB Insert — 2024-09-03
Users with emoji in their notes (common in Japanese users) getting 500 errors.
Root cause: DuckDB VARCHAR column not handling 4-byte UTF-8 sequences correctly.
Fix: Sanitize content before insert — strip or replace 4-byte chars.
```python
content = content.encode('utf-16', 'surrogatepass').decode('utf-16')
```
Better fix: switch to TEXT column type which handles full Unicode range.
Filed PR #87. Merged same day.

## BUG: File Upload Hangs on Safari — 2024-09-19
Safari users reporting file upload spinner never stopping.
Root cause: Safari handles FormData differently — adds extra Content-Type boundary.
Fix: Don't manually set Content-Type header when sending FormData.
`fetch(url, { method: 'POST', body: formData })` — let browser set headers.
Note: this is a classic Safari bug. Always test on Safari before shipping file upload.

## BUG: Query Returns Empty for New Users — 2024-10-02
New users getting zero results even after uploading files successfully.
Root cause: user_id from Clerk includes `user_` prefix. Inconsistency between
ingest endpoint (stripping prefix) and query endpoint (keeping prefix).
Fix: normalise user_id in every endpoint — always strip `user_` prefix.
Added helper function `normalise_user_id(user_id: str) -> str`.
Added test to catch this class of bug in future.

## BUG: Decay Weight Going Negative — 2024-10-11
Some memories showing decay_weight of -0.12 in stats endpoint.
Root cause: decay calculation didn't clamp to minimum of 0.
Fix: `decay_weight = max(0.0, calculated_weight)` in decay engine.
SnowMemory core updated. Also added assertion in Memory model validator.
Negative decay caused those memories to be ranked below zero in search — effectively invisible.

## PERFORMANCE: Slow Cold Start on Railway — 2024-10-25
First request after inactivity taking 8-12 seconds.
Root cause: sentence-transformers model loading on first request.
Fix: Pre-load the model at startup, not on first request.
```python
@app.on_event("startup")
async def startup():
    # Pre-warm the embedder
    get_memory("warmup_user")
```
Result: cold start reduced to 3 seconds. Hot requests unchanged at <200ms.
Consider: keep-alive ping every 10 minutes to prevent cold starts entirely.

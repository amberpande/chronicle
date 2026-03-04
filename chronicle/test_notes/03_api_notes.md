# API Design & Backend Notes

## Why We Chose FastAPI Over Express — 2024-06-15
Decision: use FastAPI (Python) instead of Node/Express for backend.
Reason 1: SnowMemory core is Python — avoid language context switching.
Reason 2: FastAPI auto-generates OpenAPI docs at /docs — useful for frontend team.
Reason 3: Pydantic validation is cleaner than Zod on the backend.
Tradeoff: slightly more complex deployment (Python runtime vs Node).
Revisit if we hire Node engineers or need Edge deployment.

## File Upload Size Limit — 2024-07-28
Set max file upload to 10MB in both FastAPI and Railway config.
Most markdown files are under 500KB. PDFs can be large — warn users above 5MB.
Added client-side size check before upload to fail fast.
Railway default limit is 100MB but we enforce lower for cost reasons.
Config: `app.add_middleware(LimitUploadSize, max_upload_size=10_000_000)`

## Chunking Strategy for Large Files — 2024-08-22
Problem: feeding a 50-page document as one memory gives bad salience scores.
Solution: chunk at 2000 characters with 200 character overlap.
Overlap prevents losing context at chunk boundaries.
Break points: prefer paragraph boundaries over character count.
Tested with 100-page technical PDF — 47 chunks, 31 stored after salience gate.
Quality assessment: chunks stored were genuinely the most novel/informative sections.

## Webhook Retry Logic for Stripe — 2024-09-11
Stripe webhooks fail silently if endpoint returns non-200 within 30 seconds.
Added idempotency key check to prevent double-processing retried events.
Webhook events stored in `stripe_events` table with processed flag.
Dead letter queue: events failing 3 times go to manual review queue.
Test with Stripe CLI: `stripe listen --forward-to localhost:8000/webhook/stripe`

## CORS Headache with Clerk Auth Headers — 2024-10-01
Frontend getting blocked by CORS on requests with Clerk auth headers.
Root cause: `Authorization` header not in CORS allowed headers list.
Fix: Added `Authorization` to `allow_headers` in FastAPI CORS middleware.
Also needed `allow_credentials=True` — took 2 hours to debug this.
Note for next project: always set CORS headers explicitly, never use wildcard in prod.

## Background Task Queue Decision — 2024-10-30
For large file ingestion, processing should be async not blocking the request.
Options evaluated: Celery + Redis, FastAPI BackgroundTasks, RQ, ARQ.
Chose FastAPI BackgroundTasks for MVP — zero extra infrastructure.
Will migrate to ARQ (async Redis queue) when processing time exceeds 10 seconds regularly.
Current P95 ingestion time: 2.3 seconds. Fine for now.

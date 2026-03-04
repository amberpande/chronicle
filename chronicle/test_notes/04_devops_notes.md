# Deployment & DevOps Notes

## Railway vs Render vs Fly.io Decision — 2024-06-20
Evaluated three platforms for FastAPI deployment.
Railway: $5/month starter, persistent disk, easy env vars, good Python support. WINNER.
Render: free tier sleeps after 15 min inactivity — kills our use case.
Fly.io: better for multi-region but overkill for MVP. Revisit at 10k users.
Railway deploy command: push to main branch, auto-deploys via GitHub integration.
Add `Procfile`: `web: uvicorn main:app --host 0.0.0.0 --port $PORT`

## Environment Variables Checklist — 2024-07-05
Never commit .env files. Always use .env.example with placeholder values.
Required vars for production:
- DATABASE_URL (Railway auto-injects this)
- CLERK_SECRET_KEY
- NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
- STRIPE_SECRET_KEY
- STRIPE_WEBHOOK_SECRET
- NEXT_PUBLIC_API_URL (Railway backend URL)
- SNOWFLAKE_ACCOUNT (when upgrading from DuckDB)
Missing any of these = silent failures. Add startup check that validates all vars exist.

## Zero Downtime Deploys on Railway — 2024-08-08
Default Railway deploy has ~3 second downtime during restart.
Fix: Added health check endpoint `/health` returning 200.
Set Railway health check to `/health` with 10 second timeout.
Railway waits for health check before routing traffic to new instance.
Result: zero visible downtime on deploys.

## Persistent Disk Setup for DuckDB — 2024-08-25
DuckDB files lost on Railway restart if using ephemeral storage.
Fix: Mount persistent volume at `/data` in Railway dashboard.
Set `DUCKDB_PATH=/data/chronicle.db` in environment variables.
Cost: $0.25/GB/month. At 1000 users with 1MB each = $0.25/month. Negligible.
Backup: Railway doesn't auto-backup volumes. Set up daily pg_dump to S3.

## Docker Setup for Local Dev — 2024-09-14
Created docker-compose.yml for one-command local setup.
Services: fastapi backend + redis (for future queue).
Volume mount: `./backend:/app` for hot reload during development.
Command: `docker-compose up --build`
Note: DuckDB doesn't work well in Docker on Apple Silicon — use local Python instead on M1/M2 Macs.

## GitHub Actions CI Pipeline — 2024-10-08
Set up CI to run tests on every PR before merge.
Pipeline: lint (ruff) → type check (mypy) → unit tests (pytest) → build check.
Total CI time: 2 min 40 sec. Acceptable.
Added status badge to README.
Secrets: store all env vars in GitHub Secrets, not hardcoded in workflow file.
Branch protection: require CI pass before merge to main.

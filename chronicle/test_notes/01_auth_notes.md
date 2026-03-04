# Auth & Security Notes

## JWT Token Expiry Bug — 2024-08-14
Fixed a critical bug where JWT tokens were expiring after 1 hour causing users to be logged out mid-session.
Root cause: `JWT_EXPIRY` env var was set to `3600` (seconds) but the library expected milliseconds.
Fix: Changed to `3600000` in `.env.production`. Also updated `auth/middleware.ts` line 47.
Also added a silent refresh mechanism — token refreshes automatically when 15 min remain.
Filed as JIRA-1204.

## OAuth Google Login Redirect Issue — 2024-09-02
Google OAuth was redirecting to `localhost` in production after login.
Root cause: `NEXTAUTH_URL` was not set in Railway environment variables.
Fix: Set `NEXTAUTH_URL=https://app.getchronicle.io` in Railway dashboard.
Note: This silently fails without error — just wrong redirect. Easy to miss.

## Password Reset Email Delay — 2024-09-18
Users reporting password reset emails arriving 10–15 minutes late.
Investigated: SendGrid queue backing up between 08:00–10:00 UTC.
Temporary fix: Added retry logic with 3 attempts, 30 second intervals.
Permanent fix: Switch to Resend for transactional email — faster + cheaper.
Action: migrate email to Resend by end of sprint.

## Session Token Leak in Console — 2024-10-05
Discovered session tokens were being logged to browser console in development mode.
Root cause: Debug logging in `lib/auth.ts` was accidentally left enabled.
Fix: Wrapped all auth logging in `if (process.env.NODE_ENV === 'development')` guard.
Security audit recommended — check all console.log calls before next release.

## Rate Limiting on Login Endpoint — 2024-10-22
Added rate limiting to `/api/auth/login` after detecting credential stuffing attempts.
Implementation: `express-rate-limit` — 5 attempts per 15 minutes per IP.
Added CAPTCHA trigger after 3 failed attempts.
Blocked 4,200 malicious requests in first 24 hours after deploy.
Monitor: set up alert if rate limit triggers > 100 times/hour.

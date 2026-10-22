# 03 — Hosting on Vercel, next to Cardcore

LogiDx runs as a **second Vercel project** from the same GitHub repository as Cardcore, with its own URL
(for example `logidx-<team>.vercel.app`). The two projects share nothing at runtime: separate database,
separate environment variables, separate deployments.

| Piece | How it runs on Vercel |
|---|---|
| Dashboard and API | One Python function (`api/index.py`) serving the whole FastAPI app |
| Database | Neon Postgres from the Vercel Marketplace (a **new** database, not Cardcore's) |
| Schedule | Vercel Cron calls `/cron/run?slot=20:00` with `Authorization: Bearer $CRON_SECRET` |
| First login | Created on the first request from `LOGIDX_ADMIN_EMAIL` / `LOGIDX_ADMIN_PASSWORD` |

What has been verified (2026-10-22): `vercel build` succeeds with Vercel CLI 65 and the `@vercel/python` builder.
The built function was then run against PostgreSQL 16 with Vercel-style environment variables. That run covered:
nine simultaneous cold starts on an empty database (one migration, one first user, no errors); login; Run now;
every page; and cron authentication and once-per-day idempotency. **It has not yet been deployed to a live Vercel
project.**

## One-time setup (about 10 minutes)

1. **New project.** In Vercel, go to **Add New → Project** and import `wtfcartel/TCG-Valuation` again. This is the
   same repository as Cardcore; Vercel allows several projects per repository.
   - **Project Name:** `logidx` (this becomes the URL)
   - **Root Directory:** `logidx` ← important
   - **Framework Preset:** Other
2. **Database.** In the new project, go to **Storage → Create → Neon (Postgres)** and connect it. This sets
   `DATABASE_URL`. Prefer the pooled connection string if offered.
3. **Environment variables** (Settings → Environment Variables, Production and Preview):

   | Name | Value |
   |---|---|
   | `LOGIDX_SECRET_KEY` | Long random string (`openssl rand -hex 32`). **Required** — the app refuses to start without it |
   | `CRON_SECRET` | Another random string of 16+ characters. Vercel sends it to the cron route automatically |
   | `LOGIDX_ADMIN_EMAIL` | Your login email |
   | `LOGIDX_ADMIN_PASSWORD` | A temporary password (12+ characters). **Delete this variable after first login** |
   | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Optional: free key from developer.adzuna.com (the main searchable source) |
   | `XAI_API_KEY` | Optional: turns on Grok assessments |
   | `SMTP_HOST`, `SMTP_FROM`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `LOGIDX_REPORT_RECIPIENT` | Optional: daily report email |

   Do not set `LOGIDX_COOKIE_SECURE=false`: Vercel serves HTTPS.
4. **Deploy.** The first request migrates the database and creates your login. Open the project URL and sign in.
5. **Remove `LOGIDX_ADMIN_PASSWORD`** and redeploy. Change your password locally with
   `LOGIDX_DATABASE_URL='<Neon URL>' logidx create-user you@example.com` if you want a different one.

## Plan limits and what they mean here

| Limit | Effect on LogiDx |
|---|---|
| **Cron frequency.** Hobby allows once per day, and Hobby crons may fire at any point within the scheduled hour | One run a day (`0 9 * * *` UTC = 20:00 AEDT in summer, 19:00 AEST in winter), which also sends the daily report. For the 06:00 and 14:00 runs, upgrade to Pro and add two crons to `vercel.json`: `{"path": "/cron/run?slot=06:00", "schedule": "0 19 * * *"}` and `{"path": "/cron/run?slot=14:00", "schedule": "0 3 * * *"}` (UTC; these shift by an hour when daylight saving changes). The Run now button works at any time |
| **Function duration.** `vercel.json` asks for 300 s | Each run stops starting new searches after `LOGIDX_RUN_TIME_BUDGET` seconds (240 by default on Vercel) and records the rest as NOT SEARCHED, with the reason. If Vercel rejects 300 s on your plan, set `maxDuration` to 60 and `LOGIDX_RUN_TIME_BUDGET=45` |
| **Hobby is personal, non-commercial use only** | Fine for a private job search |
| **No writable disk** (only `/tmp`) | The uploaded CV's *text* is stored in the database; the original file in `/tmp` is temporary |
| **Many short-lived instances** | Migrations and seeding are serialised with a Postgres advisory lock; runs use the database run lock; login rate limiting is per instance |

## Isolation from Cardcore

- `logidx/vercel.json` has `"ignoreCommand": "git diff --quiet HEAD^ HEAD -- ."`, so the LogiDx project only
  rebuilds when something under `logidx/` changes. Cardcore's own project (repository root) is unaffected by LogiDx,
  apart from rebuilding when any file in the repository changes, as it already does.
- Use a separate Neon database. Never point LogiDx at Cardcore's `DATABASE_URL`.

## Troubleshooting

- A plain-text page saying **"LogiDx could not start"** gives the reason (secrets are redacted). It is usually a
  missing `LOGIDX_SECRET_KEY` or database variable.
- **Function logs**: Vercel → project → Logs. Runs, failures and coverage are also in the dashboard under Runs and
  Search coverage.

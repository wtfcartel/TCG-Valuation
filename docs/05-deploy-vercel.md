# 05 — Deploying to Vercel

Cardcore runs on Vercel as:
- **Static PWA** (`apps/web/dist`), served from Vercel's CDN.
- **One Vercel Function** (`api/index.js`) running the whole Fastify API. It is pre-bundled by `npm run build:vercel`.
- **Neon Postgres** from the Vercel Marketplace.
- **Private Vercel Blob** for owner photographs. They are never publicly addressable and are streamed only through the authenticated `/api/photos/:id` route.
- **Vercel Cron** at 16:30 UTC daily, importing ECB exchange rates via `/api/cron/ecb`.

Everything is configured in [`vercel.json`](../vercel.json). The build was verified locally with `vercel build`, and the built function was exercised against PostgreSQL. It has not yet been deployed to a live Vercel project.

## Important plan limits

| Limit | Hobby (free) | What Cardcore does |
|---|---|---|
| **Use** | **Personal, non-commercial only.** Charging users or operating it as a business requires Pro ($20/month) | Treat Hobby as a private pilot |
| Request body | 4.5 MB | The browser shrinks photos (≤2400 px JPEG) and strips scripts/styles from saved eBay pages before upload |
| Function duration | Up to 60 s (set in `vercel.json`) | Reconciling very large schedules or slow PokeTrace Free-plan imports may need Pro's longer limit |
| Cron | Once per day | ECB publishes once per business day, so daily is enough |
| Blob | 1 GB storage, 10 GB transfer/month | Enough for a pilot |
| Instances | Many short-lived instances | Migrations are lock-protected. Login rate limits are per instance (weaker than on a single server) |

## One-time setup

1. **Import the repository.** In Vercel, go to **Add New → Project** and import `wtfcartel/TCG-Valuation`. Leave **Framework Preset** as *Other* and **Root Directory** as the repository root; `vercel.json` supplies the install/build commands and output directory.
2. **Add the database.** Go to Project → **Storage → Create → Neon (Postgres)** and connect it to the project. This sets `DATABASE_URL`. Prefer the **pooled** connection string if Neon offers both.
3. **Add photo storage.** Go to Project → **Storage → Create → Blob**, choose **Private** access, and connect it. The SDK authenticates automatically on Vercel.
4. **Environment variables** (Project → Settings → Environment Variables, Production and Preview):

   | Name | Value |
   |---|---|
   | `JWT_SECRET` | A long random string, e.g. the output of `openssl rand -hex 32` |
   | `CRON_SECRET` | Another random string of 16+ characters |
   | `POKETRACE_API_KEY` | Optional: your PokeTrace key |
   | `POKETRACE_COMMERCIAL_LICENCE` | `false` until your PokeTrace plan's terms allow commercial use |

   `NODE_ENV=production` and `VERCEL=1` are set by Vercel. The synthetic demo source stays off in production.
5. **Deploy.** The first request migrates the database automatically.
6. **Create your admin account.** Register in the deployed app. Then, on your own computer with the production `DATABASE_URL`:
   ```bash
   DATABASE_URL='postgres://…neon…' npm run create-admin -w @cardcore/api -- you@example.com
   ```
7. **Load exchange rates now** rather than waiting for the nightly cron: sign in as admin, go to **Settings → Exchange rates → ECB 90 days**.

## Preview deployments

Each pull request gets a preview URL. If the Neon integration creates a database branch per preview, previews are isolated from production. Otherwise they share the production database, and migrations would run against it. Check this in the Neon integration settings before opening PRs that change migrations.

## Moving off Vercel later

Nothing is Vercel-specific apart from `api/index.js`, `vercel.json`, the Blob photo store and the cron route. The same code runs as a normal server with `docker compose up`, which uses local photo storage and an in-process ECB timer.

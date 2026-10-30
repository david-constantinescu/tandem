# Deployment

## Option A — Docker Compose on a VPS (recommended)

```bash
cp .env.example .env
# set APP_ENV=production, SECRET_KEY, ENCRYPTION_KEY, SESSION_COOKIE_SECURE=true,
# FRONTEND_URL/BACKEND_URL to your public https URL, POSTGRES_PASSWORD, OSM_CONTACT_EMAIL, provider keys
docker compose up -d --build
docker compose exec web flask seed-demo --password '<demo password>'   # optional shared demo account
```

Services: `db` (PostgreSQL 16, volume `pgdata`), `redis` (rate-limit storage), `migrate`
(`flask db upgrade`, runs once), `web` (gunicorn, 3 workers × 4 threads, serves API + SPA on port
8000, health check `/api/v1/health`), `worker` (`flask worker`: jobs + periodic checks every
`SCHEDULED_CHECK_MINUTES`). Put a TLS-terminating reverse proxy (Caddy, nginx, Traefik) in front, forward `X-Forwarded-For`, and
set `TRUSTED_PROXIES=1` so rate limits and audit logs see real client IPs (otherwise every user shares
the proxy's IP). For events where many people share one network, raise `DEMO_RATE_LIMIT`.

Scale workers with `docker compose up -d --scale worker=3` — the queue uses `SKIP LOCKED`, so several
workers are safe. Uploaded files live in the `storage` volume; for multiple hosts use
`STORAGE_TYPE=s3`.

> This Compose stack and the Dockerfile were written for this build but could not be executed on the
> development machine (no Docker available). The same commands were verified directly on the host.

## Option B — Frontend on Vercel, API elsewhere

Build the SPA (`npm run build`) and deploy `frontend/dist` to Vercel with a rewrite of `/api/*` to the
Flask host so cookies stay first-party:

```json
{ "rewrites": [{ "source": "/api/:path*", "destination": "https://api.example.com/api/:path*" },
               { "source": "/(.*)", "destination": "/index.html" }] }
```

Run the Flask app and the worker on a Python host (VPS, Fly.io, Render, Railway…) with PostgreSQL.
Do not run Flask or the worker as serverless functions: the worker is long-running.

## Production checklist

- `APP_ENV=production` (startup refuses weak `SECRET_KEY`, missing `ENCRYPTION_KEY`, insecure cookies).
- `RATELIMIT_STORAGE_URI=redis://…` when running more than one web process.
- `OSM_CONTACT_EMAIL` set (OSM usage policy). For heavier use, self-host Nominatim/Overpass or use a
  commercial geocoder behind the same interface.
- Gmail: verify the OAuth app with Google (gmail.readonly is a restricted scope) and set
  `GOOGLE_REDIRECT_URI` to `https://<host>/api/v1/integrations/gmail/callback`.
- Run `flask check-providers` after configuring AI keys.

## Backups

- PostgreSQL: nightly `pg_dump -Fc` (or managed backups) with point-in-time recovery where available;
  test restores regularly.
- Files: back up the storage volume / bucket (objects are encrypted with `ENCRYPTION_KEY`).
- **Back up `ENCRYPTION_KEY` separately**; without it stored documents, tokens and extracted text
  cannot be decrypted. Rotate by prepending a new key (`ENCRYPTION_KEY=new,old`).

## Operations

- Logs go to stdout (no document contents, prompts or secrets).
- `GET /api/v1/health` reports database and queue depth.
- `flask run-jobs` processes due jobs once; `flask periodic` runs scheduled checks once.
- Error reporting: attach Sentry or similar at the WSGI level if desired (not bundled).

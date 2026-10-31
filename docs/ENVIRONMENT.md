# Environment & API keys

Tandem runs with **zero third-party keys**. Without them it reads documents with its own parser and OCR, the assistant
answers from your trip data in an offline mode, and activities come from OpenStreetMap plus the simulated demo
provider. Every key below switches on something extra; nothing is faked when a key is missing.

Check what your environment unlocks at any time (prints no secret values):

```bash
cd backend && .venv/bin/flask --app app env-status
```

## 1. Generated secrets (you make these yourself)

| Variable | Needed | How to create it |
|---|---|---|
| `SECRET_KEY` | Always (required in production) | `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `ENCRYPTION_KEY` | Always | `python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` — encrypts stored files, OAuth tokens and extracted data. Comma-separate old keys to rotate. **Losing it makes stored files unreadable.** |
| `CRON_SECRET` | On Vercel | Any long random string. Vercel Cron sends it to `/api/v1/internal/cron`. |
| `DEMO_ACCOUNT_PASSWORD` | Optional | Only for the shared `flask seed-demo` account. The "Explore the demo" button doesn't need it. |

## 2. Database

| Variable | Where to get it |
|---|---|
| `DATABASE_URL` | Local: `scripts/dev-db.sh start` prints it (PostgreSQL 16 on port 5433). Hosted: any PostgreSQL 14+; the Vercel deployment uses [Neon](https://neon.tech) (free tier). `postgres://` URLs are normalised automatically. |

Run migrations after pointing at a new database: `cd backend && .venv/bin/flask --app app db upgrade`.

## 3. AI providers (optional, all have free tiers)

| Variable | Unlocks | Where to get it |
|---|---|---|
| `GEMINI_API_KEY` | The main extractor: reads PDFs, screenshots and photos directly; powers the assistant. **The one key worth getting first.** | [Google AI Studio → API keys](https://aistudio.google.com/apikey). Free tier, no card. |
| `ZAI_API_KEY` | Second provider: text extraction, the vision model for images, assistant fallback. | [Z.ai platform → API keys](https://z.ai/manage-apikey/apikey-list). The `-flash` models are free. |
| `GROQ_API_KEY` | Very fast text-only tasks (classification, short answers). Groq **never** receives files — enforced in code. | [GroqCloud console → API keys](https://console.groq.com/keys). Free tier. |

Model names are pre-filled in `.env.example` with models verified as free. Paid models are never used unless you set
`AI_ALLOW_PAID_MODELS=true`. After adding keys, `flask check-providers` makes one tiny call to each provider and
`flask smoke-ai` runs a real extraction end to end. Each user still chooses Off / Text only / Files and text in
Settings → AI & privacy. More detail: [AI_PROVIDER_CONFIGURATION.md](AI_PROVIDER_CONFIGURATION.md).

## 4. Gmail import (optional)

| Variable | Value |
|---|---|
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials) → *Create OAuth client ID* → *Web application*. |
| `GOOGLE_REDIRECT_URI` | `<BACKEND_URL>/api/v1/integrations/gmail/callback` — add the exact same URL under *Authorised redirect URIs*. On Vercel: `https://<your-domain>/api/v1/integrations/gmail/callback`. |

Also: enable the [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com), configure the OAuth
consent screen (External, *Testing*), add yourself as a test user. Tandem only asks for `gmail.readonly`. That is a
*restricted* scope: fine for you and up to 100 test users; opening it to the public needs Google's verification.

## 5. Activities & travel providers (optional, partner approval needed)

These are real partner programmes. Tandem has working clients for them but they stay "not configured" until you have
credentials — they are never simulated.

| Variable(s) | Programme | Notes |
|---|---|---|
| `VIATOR_API_KEY`, `VIATOR_ENV` | [Viator Partner API](https://partnerresources.viator.com/) | Affiliate access gives search + availability; booking needs a merchant agreement. Start with `sandbox`. |
| `GETYOURGUIDE_ACCESS_TOKEN` | [GetYourGuide Partner](https://partner.getyourguide.com/) | API access is granted to approved partners. |
| `BOOKING_COM_AFFILIATE_ID`, `BOOKING_COM_API_TOKEN` | [Booking.com Demand API](https://developers.booking.com/demand/) | Affiliate Partner Programme approval. |
| `EXPEDIA_API_KEY`, `EXPEDIA_SHARED_SECRET` | [Expedia Rapid](https://developers.expediagroup.com/rapid) | Partner agreement; keep `EXPEDIA_ACTIVITIES_ENABLED=false` until activities access is granted. |

No key needed: `OSM_PLACES_ENABLED=true` searches museums, galleries and sights from OpenStreetMap (search only, no booking).

## 6. Maps & travel times (optional)

| Variable | Unlocks | Where to get it |
|---|---|---|
| `LOCATION_PROVIDER=nominatim` + `OSM_CONTACT_EMAIL` | Geocoding addresses so events appear on the map | No key. OSM's [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/) asks for a contact email in the User-Agent and max 1 request/second (Tandem respects both). `offline` uses the built-in city list only. |
| `ROUTING_OSRM_URL` | Real travel times between places in conflict checks | Run [OSRM](https://project-osrm.org/) yourself. Without it Tandem says travel time is unknown instead of guessing. |

## 6b. Live trip context

| Variable | Unlocks | Where to get it |
|---|---|---|
| `WEATHER_ENABLED` (default `true`) | Per-day forecast on trips, weather-aware activity ranking, the assistant's `get_weather` tool | No key: [Open-Meteo](https://open-meteo.com/en/docs), free for non-commercial use, 10,000 calls/day. Cached 3 hours. |
| `NEWS_ENABLED` (default `true`) | Strikes, protests, closures and alerts for the destination, the assistant's `check_local_news` tool | No key: Google News RSS, with the [GDELT DOC API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) as fallback. Cached 1 hour. |
| `TAVILY_API_KEY` | General web search for the assistant (`web_search`) | [app.tavily.com](https://app.tavily.com): 1,000 free searches/month. Without it, `web_search` searches Google News. |

## 7. Infrastructure (optional)

| Variable(s) | When you need it |
|---|---|
| `STORAGE_TYPE=s3`, `STORAGE_BUCKET`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`, `STORAGE_ENDPOINT`, `STORAGE_REGION` | Large volumes of files. Any S3-compatible store works (AWS S3, Cloudflare R2, MinIO). Defaults: `local` on a server, `database` (encrypted, in PostgreSQL) on Vercel. |
| `REDIS_URL` | Several web processes sharing rate limits (e.g. [Upstash](https://upstash.com) free tier). |
| `BROWSER_WORKER_ENABLED=true` | A long-running worker with Playwright + Chromium (`Dockerfile.browser`). Not possible on Vercel. |
| `BROWSER_ASSIST_SITES` | Real booking sites you allow the agent to *search* after you have reviewed their terms. Empty = link-only everywhere. |
| `BROWSER_CDP_URL` | A Chromium you run elsewhere with remote debugging, instead of a local headless browser. |

## Local setup (what is already done)

`backend/.env` exists with generated `SECRET_KEY` and `ENCRYPTION_KEY`, the local database URL, the worker job runner and
the browser worker enabled. Add any keys from sections 3–7 to that file and restart the backend and worker.

```bash
scripts/dev-db.sh start
cd backend && .venv/bin/flask --app app run --port 5050     # API
cd backend && .venv/bin/flask --app app worker              # background jobs + browser agent
npm --prefix frontend run dev                               # http://localhost:5173
```

## Vercel (production)

Production already has `SECRET_KEY`, `ENCRYPTION_KEY`, `DATABASE_URL` (Neon), `CRON_SECRET`, `APP_ENV=production`
and the demo settings. To add the keys you collect:

1. Put them in `.env.production.local` at the repo root, one `KEY=value` per line (the file is gitignored). Starting
   from a copy of `.env.example` is fine.
2. Check what would change: `scripts/vercel-env-push.sh --dry-run` (prints key names only).
3. Apply: `scripts/vercel-env-push.sh` — values go to Vercel over stdin and are never printed. It skips empty values,
   unchanged defaults, anything pointing at localhost, and the core settings production already has (secrets,
   database, URLs) unless you pass `--include-core`.
4. Redeploy: `vercel deploy --prod`.

If you add Gmail on Vercel, set `GOOGLE_REDIRECT_URI` to the production URL and register the same URL in Google Cloud.

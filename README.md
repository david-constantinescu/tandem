# Tandem

Tandem is a personal travel manager. You give it booking confirmations — PDFs, screenshots, photos,
emails, pasted text or links — and it extracts the details with sources and confidence, groups them
into trips, keeps a timezone-correct itinerary, detects conflicts, and runs an assistant that works
from your real data. It can find activities that fit your free time and prepare bookings, which only
execute after you approve the exact proposal and the provider's response is verified.

- **Backend:** Python 3.11, Flask, SQLAlchemy 2, Alembic, Pydantic, PostgreSQL 16
- **Jobs:** PostgreSQL-backed queue (`SELECT … FOR UPDATE SKIP LOCKED`) with a separate worker process
- **AI:** Gemini (primary, files/vision), Z.ai GLM (text + free vision model), Groq (text only — never files)
- **Frontend:** React 19, TypeScript, Vite 7, Tailwind CSS 4, TanStack Query, React Router, Radix UI, Leaflet

See [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) for what works today, what is
tested, and which features wait on partner credentials.

## Quick start (local development)

Prerequisites: Python 3.11, Node 20+, Tesseract OCR (`brew install tesseract` / `apt install tesseract-ocr`).
PostgreSQL is provided locally by the `pgserver` pip package's bundled binaries; any PostgreSQL 14+ works.

```bash
# 1. Backend environment
python3.11 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt pgserver

# 2. Local PostgreSQL on port 5433 (creates databases `tandem` and `tandem_test`)
scripts/dev-db.sh start

# 3. Configuration
cp .env.example backend/.env      # then set SECRET_KEY and ENCRYPTION_KEY (commands are in the file)

# 4. Database schema and the shared demo account
cd backend
.venv/bin/flask --app app db upgrade
.venv/bin/flask --app app seed-demo --password "choose-a-demo-password"

# 5. Run the API, the worker and the frontend (three terminals)
.venv/bin/flask --app app run --port 5050
.venv/bin/flask --app app worker
npm --prefix ../frontend install && npm --prefix ../frontend run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` to the Flask API on port 5050.

**Live:** https://tandem-travel-roan.vercel.app — click *Explore the demo*.

## The demo

Click **Explore the demo** on the sign-in page. Each visitor gets an isolated, expiring workspace with
a fictional Rome long weekend (flights, hotel with an applied update, museum ticket, walking tour,
dinner, free time, a suggestion, one deliberate conflict, documents and an assistant conversation).
Bookings use a simulated provider — nothing real is booked or charged. On **Websites**, the browser agent
can complete a full (simulated) purchase on Tandem's demo rail, bus, airline and museum sites after you approve it;
real booking sites (42 listed) are link-only by default — see [docs/BROWSER_AGENT.md](docs/BROWSER_AGENT.md). The shared account
`demo@tandem.travel` is created by `flask seed-demo`. Details: [docs/DEMO_ENVIRONMENT.md](docs/DEMO_ENVIRONMENT.md).

## Configuring AI providers

Everything works without API keys: documents are read by Tandem's on-server parser and OCR, and the
assistant runs in a clearly labelled offline mode. Add keys to enable AI:

| Key | Unlocks |
|---|---|
| `GEMINI_API_KEY` | Extraction from original PDFs/images (Files API for large PDFs), the full assistant with tool calling, conflict explanations |
| `ZAI_API_KEY` | Text extraction/reasoning (GLM-4.7-Flash), screenshots via the free GLM-4.6V-Flash vision model, assistant fallback |
| `GROQ_API_KEY` | Fast text-only tasks (summaries, conflict explanations); never receives files |

Users also choose, per account, whether external AI may see nothing, only extracted text, or files.
After adding keys, run `flask --app app check-providers` to verify the configured model IDs, then
`flask --app app smoke-ai` for a live end-to-end check (fictional demo PDF and screenshot through
Gemini/Z.ai with the extraction schema, a Groq text task, and a multi-tool assistant turn).
See [docs/AI_PROVIDER_CONFIGURATION.md](docs/AI_PROVIDER_CONFIGURATION.md) and [docs/AI_PRIVACY.md](docs/AI_PRIVACY.md).

## Integrations

| Integration | Needs | Status without it |
|---|---|---|
| Gmail (read-only) | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (OAuth app; restricted scope needs Google verification for production) | Hidden as "not configured" |
| Booking.com Attractions | Affiliate ID + token, early-access pilot approval | `awaiting_partner_approval` |
| Expedia Rapid Activities | Beta partner access | `awaiting_partner_approval` |
| Viator | Affiliate API key | `awaiting_partner_approval` |
| GetYourGuide | Partner token | `awaiting_partner_approval` |
| OpenStreetMap places | none (`OSM_CONTACT_EMAIL` recommended) | Search-only discovery, no prices or availability |

See [docs/PROVIDER_INTEGRATIONS.md](docs/PROVIDER_INTEGRATIONS.md).

## Tests

```bash
cd backend && .venv/bin/python -m pytest          # 103 tests on PostgreSQL (tandem_test); no API keys needed
# Playwright tests need: .venv/bin/pip install playwright && .venv/bin/python -m playwright install chromium
cd frontend && npx vitest run && npx tsc -b --noEmit
```

`TEST_DATABASE_URL` overrides the test database. External providers are mocked (respx / fakes).

## Deployment

`docker compose up -d --build` runs PostgreSQL, Redis (rate limits), a one-shot migration, the web
app (gunicorn serving API + built SPA on one origin) and the worker. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Documentation

[Product overview](docs/PRODUCT_OVERVIEW.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Database schema](docs/DATABASE_SCHEMA.md) · [API reference](docs/API_REFERENCE.md) ·
[AI providers](docs/AI_PROVIDER_CONFIGURATION.md) · [AI privacy](docs/AI_PRIVACY.md) ·
[Document ingestion](docs/DOCUMENT_INGESTION.md) · [Agent](docs/AGENT_ARCHITECTURE.md) ·
[Approvals](docs/APPROVAL_SYSTEM.md) · [Provider integrations](docs/PROVIDER_INTEGRATIONS.md) ·
[Booking.com](docs/BOOKING_COM_INTEGRATION.md) · [Expedia](docs/EXPEDIA_INTEGRATION.md) ·
[Airlines](docs/AIRLINE_INTEGRATIONS.md) · [Demo](docs/DEMO_ENVIRONMENT.md) ·
[Browser agent](docs/BROWSER_AGENT.md) · [Deployment](docs/DEPLOYMENT.md) · [Security](docs/SECURITY.md) ·
[Status](docs/IMPLEMENTATION_STATUS.md)

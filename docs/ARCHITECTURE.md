# Architecture

```
frontend/ (React SPA)  ──/api/v1──▶  backend/app (Flask, gunicorn)  ──▶ PostgreSQL
                                           │  enqueue                     ▲
                                           ▼                              │
                                     processing_jobs  ◀── flask worker ───┘
                                           │
                     AI router ─▶ Gemini / Z.ai / Groq      Travel adapters ─▶ Simulator (demo) / OSM / partners
                     Storage   ─▶ local (encrypted) / S3    Geo ─▶ airportsdata, curated cities, Nominatim, OSRM
```

## Backend layout

```
backend/app/
  __init__.py          app factory: config validation, extensions, blueprints, security headers, SPA serving
  config.py            environment configuration and startup validation
  api/                 versioned REST blueprints (/api/v1/...), _core.py = envelope, auth, CSRF, OpenAPI metadata
  models/              SQLAlchemy models (user, trip/reservation/itinerary, document/extraction, assistant, system)
  schemas/serializers  JSON serialisation (times returned in UTC and in each event's local zone)
  services/
    ai/                base types, model registry, Gemini/Z.ai/Groq providers, router
    ingestion/         validation, local extractors (PDF/OCR/DOCX/HTML/EML), local parser, normalisation, pipeline, SSRF-safe fetch
    trips/             grouping, reservations, itinerary sync, change detection
    itinerary/         event editing, deterministic conflict engine
    agent/             tools, orchestrator, offline assistant, approvals/execution
    providers/         adapter interface, simulator, OSM, partner adapters, registry, activity search
    integrations/      Gmail (read-only OAuth)
    geo/, demo/, notifications/, storage.py, cache.py, audit.py, users.py
  tasks/               queue, job handlers, periodic checks
  security/            encryption (Fernet) and encrypted column types
  cli.py               worker, run-jobs, periodic, seed-demo, check-providers, openapi
```

## Request lifecycle

1. `load_session` resolves the `tandem_session` cookie (random token; only its HMAC is stored).
2. `login_required` enforces authentication and, for non-GET requests, the `X-CSRF-Token` header.
3. Handlers validate bodies with Pydantic, load resources through `get_owned` (404 for other users' data),
   call services, and return `{"data": ...}` or `{"error": {"code", "message", "details"}}`.

## Decision log

| Decision | Choice | Why |
|---|---|---|
| Job queue | PostgreSQL table + `FOR UPDATE SKIP LOCKED`, separate `flask worker` | Durable, transactional with app data, no extra infrastructure; multiple workers safe. Redis is optional (rate-limit storage). |
| Auth | Server-side sessions in DB + HttpOnly SameSite=Lax cookie + CSRF header | Revocable sessions (password change signs out everywhere), no tokens in JS storage. |
| AI routing | Model registry with per-model free-tier and capability data; router enforces consent, capability, paid policy and Groq restriction | Free-tier status and modalities differ per model, not per provider. Unknown IDs are treated as paid. |
| Structured output | Provider-native mode (Gemini response schema, Groq strict json_schema, Z.ai json_object) → Pydantic validation → one repair retry → fail over | Normalises different provider guarantees into one validated contract. |
| Anti-hallucination | Values verified against text Tandem extracted itself (PDF text / OCR) | Concrete check behind "never invent reservation numbers". |
| No-key operation | Local rules parser + offline assistant over the same tools | The core workflow works and is honest without any AI provider. |
| Timezones | UTC instants + IANA zone per event; local wall-clock strings sent to clients | Correct display across zones and DST without browser conversion. |
| Locations | airportsdata + curated major cities offline; Nominatim when enabled; ambiguous names unresolved | Avoids silent wrong guesses (Rome, Georgia). |
| Travel time | Physical lower bound for impossibility; routed time only with OSRM configured | Never invent durations. |
| Demo isolation | Per-visitor tenant; registry gives demo users only the simulator and real users never the simulator | Enforced in one place in code. |
| Single origin | Flask serves the built SPA when `frontend/dist` exists | Simplifies cookies/CSRF; Vercel + API split is also possible (see DEPLOYMENT). |

## Frontend

`src/lib` (API client with CSRF, types, formatting that renders each event's own local time, query
hooks, auth context, i18n), `src/components` (UI primitives, layout shell, trips/inbox/activities
components), `src/pages` (route-level, lazily loaded). Polling is used where background work
progresses (inbox processing, in-progress actions).

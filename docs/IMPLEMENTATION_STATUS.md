# Implementation status

Last updated: 2026-10-30. Legend: ✅ implemented and tested · 🟡 implemented, not exercised against the
live third-party service · 📐 designed / scaffolded only · ⛔ not started.

## Verification summary

- **Live deployment:** https://tandem-travel-roan.vercel.app (Vercel, region fra1, Neon Postgres). The full demo
  workflow was run on the live URL: sample upload → inline processing → review → conflict → assistant →
  proposal → approval → verified simulated booking in the itinerary.
- Backend: **109 pytest tests pass** on PostgreSQL 16 (`backend/tests`), no API keys required; external
  providers mocked with fakes and `respx`.
- Frontend: type-check (`tsc -b`) and production build pass; unit tests (vitest) pass.
- Manual end-to-end run in a browser against the real stack (Flask API + separate worker + Vite):
  demo login → home → itinerary → upload sample → worker processing → review with evidence → accept →
  new conflict → assistant activity search → live quote → approval → worker execution → verified
  simulated booking → itinerary updated. Mobile layout (375 px) checked for overflow on all pages.
- Fresh-account run in the browser (new registration, no profile): flight PDF (2 segments) + hotel PDF
  uploaded through the file input, accepted with the default suggestions → exactly one trip
  ("Rome · Nov 2026", destinations ["Rome"], 3 reservations). Also covered by `tests/test_fresh_account.py`.
- Live AI check available but not run here (no keys): `flask --app app smoke-ai`.
- Not verified on this machine: Docker images/Compose (Docker not installed), live AI provider calls
  (no API keys available), live partner APIs, Gmail OAuth against Google (mocked in tests).

## Phases

| Phase | Status | Notes |
|---|---|---|
| 0 Audit & architecture | ✅ | Empty repository; architecture and decision log in ARCHITECTURE.md |
| 1 Foundation | ✅ | Flask factory, blueprints, SQLAlchemy 2, Alembic, Pydantic, sessions + CSRF, settings, OpenAPI |
| 2 Demo environment | ✅ | Per-visitor isolated workspaces, shared demo account CLI, Rome scenario, live samples, simulator |
| 3 Universal Inbox | ✅ | Upload/paste/URL, validation, encrypted storage, duplicates, statuses, preview, retry/ignore/delete |
| 4 Gemini | 🟡 | Provider, structured output, function calling with thought-signature echo, Files API lifecycle, error mapping — unit-tested with SDK fakes; no live key here |
| 5 Z.ai | 🟡 | OpenAI-compatible client, json_object mode, vision (free 4.6V-Flash), paid-only file input gated — tested with respx |
| 6 Groq | ✅/🟡 | Text-only enforcement at router and provider (tested); live calls not exercised |
| 7 Trips & reservations | ✅ | Automatic grouping with reasons, multi-destination, manual moves, change detection with history |
| 8 Itinerary engine | ✅ | UTC + IANA zones, DST gap/fold notes, editing, 12 deterministic conflict rules, notifications |
| 9 Agent | ✅ | Typed tools with permission levels, bounded loop, approvals, prompt-injection tests, offline assistant |
| 10 Activity discovery | ✅ | Provider framework, itinerary fit, saved activities, proposals; OSM search (live network, not in tests) |
| 11 Booking.com | 🟡 | Attractions search/details + redirect booking per docs; awaiting partner access |
| 12 Expedia | 📐 | Capability reporting and signature helper; Rapid Activities beta endpoints not yet public |
| 13 Specialist providers | 🟡/📐 | Viator and GetYourGuide search + link-out (untested live); Tiqets, Klook, Headout registered as partner-only (awaiting approval); Eventbrite public search retired |
| 14 Gmail | ✅/🟡 | Read-only OAuth, candidate search, selective import, dedupe, encrypted tokens, disconnect + delete — tested with mocked Google; production needs Google verification |
| 15 Airlines | ✅ (import) / ⛔ (search, booking) | Flight import incl. multi-segment and timezones; link-outs only; see AIRLINE_INTEGRATIONS.md |
| 10b Browser agent | ✅ (simulated + guards) / 🟡 (real sites) | Full agentic purchase on Tandem's simulated rail/bus/air/museum sites (works on Vercel); Playwright engine + AI navigator for allow-listed real sites, tested with real Chromium against a fixture site; 42 real sites registered link-only by default. See BROWSER_AGENT.md |
| 16 Production hardening | 🟡 | Security headers, rate limits, encryption, SSRF, privacy controls, backups doc, Docker/Compose (unverified here) |

## Definition of done (§29)

| Step | Status |
|---|---|
| 1–6 Account, inbox, upload, validation/storage, analysis by a suitable provider, structured extraction | ✅ (local parser and AI path both tested; AI path with mocked providers) |
| 7 Review and correct | ✅ |
| 8–11 Trip identification/proposal, reservation, itinerary, conflicts | ✅ |
| 12–13 Assistant answers from actual data | ✅ (AI loop tested with scripted model; offline assistant tested live) |
| 14–15 Activity search and itinerary-fit recommendation | ✅ (simulator in demo; OSM for real accounts) |
| 16–17 Booking proposal, approve/reject | ✅ |
| 18–20 Supported integration executes, response verified, reservation/itinerary updated | ✅ via simulator; real providers await partner access |
| 21 History of what happened and when | ✅ approvals history, change history, audit log, notifications |

## Known issues and limitations

- Live AI quality is unmeasured here; prompts are versioned (`extract-v1`, `agent-v1`) for evaluation once keys
  are added. Run `flask smoke-ai` first: it exercises Gemini PDF/image extraction with the full schema
  (`response_json_schema`), Z.ai vision, Groq text and a multi-tool Gemini agent turn (parallel function
  responses are sent in one turn with their call ids, unit-tested but not yet confirmed live).
- Z.ai free model IDs (`glm-4.7-flash`, `glm-4.6v-flash`) are inferred from the pricing page names;
  confirm with `flask check-providers`. Z.ai base64 image format (data URL vs raw) is configurable
  (`ZAI_IMAGE_DATA_URL`) pending a live check.
- The local parser handles common labelled layouts; unusual layouts may need AI or manual correction.
- `timezonefinder`'s compact dataset reports merged zones (e.g. Rome → Europe/Paris) for points not
  near a curated destination; offsets are correct.
- Travel times are only available with a configured OSRM server; otherwise conflicts use a physical
  lower bound and say travel time is unknown.
- Browser agent on real websites is link-only by default (terms not reviewed); assisted search needs an operator
  allow-list, a browser worker and an AI provider, and has only been tested against a local fixture site.
  Tandem never enters traveller or payment details on real sites; payment there is always done by the user.
- Audio ingestion is not supported.
- Romanian translation covers navigation only; the i18n layer is ready for full translation.
- Outbound email notifications are not implemented (in-app notifications only).
- Frontend end-to-end tests are manual (browser run); backend has API-level end-to-end tests.

## Credentials needed to unlock more

| Credential | Unlocks |
|---|---|
| `GEMINI_API_KEY` (AI Studio, ideally a non-billed project) | AI extraction from files, full assistant, explanations |
| `ZAI_API_KEY` | GLM text/vision fallback |
| `GROQ_API_KEY` | fast text-only tasks |
| `GOOGLE_CLIENT_ID/SECRET` + verified OAuth app | Gmail import |
| Booking.com affiliate + Attractions pilot | Booking.com attraction search (redirect booking) |
| Viator affiliate key | Viator search + link-out |
| Expedia Rapid Activities beta | Expedia activities (then implement booking flow) |
| `OSM_CONTACT_EMAIL` | policy-compliant OSM geocoding and place search |
| `ROUTING_OSRM_URL` | routed travel times in conflict checks |

# Tandem

**Your travel, in tandem.** Drop in every confirmation, ticket and screenshot. Tandem reads them, builds one calm
itinerary, tells you what clashes, and only books things when you say yes.

**Try it:** https://tandem-travel-roan.vercel.app → *Explore the demo* (works best on a phone).

---

## The story

Trips don't arrive in one piece. The flight is a PDF in one inbox, the hotel is an email in another, the museum
ticket is a screenshot, and the dinner reservation lives in a group chat. Somewhere between them there's a
problem you won't notice until you're standing at the wrong door: a walking tour that runs into dinner, a check-in
that starts three hours after you land, a train that leaves before the museum closes.

Tandem is the friend who reads all of it for you.

- **You throw things at it.** PDFs, photos of a printout, screenshots, forwarded emails, pasted text, a link, or
  read-only access to Gmail.
- **It reads them carefully.** Every detail it pulls out comes with the line it found it on, so you can check it in
  a second. If it's not sure, it says so and asks you instead of guessing.
- **It builds the trip.** Bookings land in the right trip, in the right order, in the right *local* time (a flight
  from London to Rome shows both clocks).
- **It spots trouble.** Overlaps, impossible connections, missing hotels, unconfirmed bookings, cancellation
  deadlines.
- **It fills the gaps.** Ask what to do on Saturday afternoon and it looks at the hours you actually have free.
- **It lives in your calendar too.** One private link puts every trip in Apple, Google or Outlook calendar and keeps
  it updated when plans change. Booking references and names stay in Tandem.
- **It works without signal.** Add it to your home screen and it behaves like an app: your trips and itinerary open
  in airplane mode, and it says plainly when something needs a connection.
- **It never spends your money on its own.** It can prepare a booking or drive a booking website, but nothing is
  bought until you approve that exact thing. If the price changes, it asks again.

And a few things it deliberately won't do: pretend an integration is live when it isn't, solve CAPTCHAs or sneak past
a website's rules, or send your files to an AI company unless you've said that's OK.

### What to try in the demo

The demo is a fictional long weekend in Rome. Each visitor gets their own private copy that expires after a day.

1. **Home** shows the next trip as a boarding pass, plus the clash Tandem already found.
2. **Inbox → Try a sample document** sends a fictional Colosseum ticket through the real reading pipeline. Accept it
   and watch a new conflict appear.
3. **Assistant** answers from your actual plans ("what's still unconfirmed?").
4. **The trip page** shows the real Open-Meteo forecast for each day and real local headlines about strikes, protests
   and closures (from Google News, in Italian). Wet days are marked, and outdoor activities sink to the bottom.
5. **Explore → Tickets → Get there** opens Google Maps and Google Flights with the route filled in, and lists the
   official operators for that route (Trenitalia, Italo, ITA Airways…), which open on their own sites.
6. **Explore → Tickets → Practice runs** lets the browser agent search a simulated rail site, pick a train that fits,
   and stop for your approval. Approve it and the confirmation is read back into your trip. No real money moves.

---

## The technical story

### Shape of the system

```
React SPA (Vite) ──/api/v1──▶ Flask API ──▶ PostgreSQL ◀── worker (flask worker)
                                 │            ▲  jobs table (FOR UPDATE SKIP LOCKED)
                                 │            │  encrypted file blobs (on Vercel)
                                 ▼            │
                     AI router: Gemini · Z.ai · Groq      browser agent: HTTP engine · Playwright
```

One Flask app serves the API (and the built SPA in production). Long work runs in a worker that pulls jobs from a
PostgreSQL table with `SELECT … FOR UPDATE SKIP LOCKED`, so there's no Redis or Celery to run. On Vercel the same
jobs run inline and a cron hits a protected endpoint for scheduled checks.

### From a file to an itinerary

1. **Upload** → the original is encrypted (Fernet) and stored (local disk, S3, or PostgreSQL on Vercel). Duplicates
   are caught by content hash.
2. **Extract text** → PDF text layer, Tesseract OCR for images and scans, MIME parsing for `.eml`, DOCX and HTML.
3. **Understand** → depending on the user's AI setting (off / text only / files and text), the AI router sends the
   original file to Gemini, images to Z.ai's free vision model, or text to whichever provider is up. With AI off,
   a local rules-based parser does the job.
4. **Verify** → every extracted value is searched for in the source text. Each field ends up as *found in document*,
   *derived* (e.g. end time from a stated duration) or *not found*, and that's what the review screen shows.
5. **Group** → records are matched to trips by dates, places and booking references, or a new trip is proposed.
   Updates to an existing booking (new check-in time, cancellation) are detected and applied as changes.
6. **Check** → deterministic conflict rules run over the timezone-aware itinerary: overlaps, impossible sequences,
   arrival-to-check-in gaps, missing transport or accommodation, unconfirmed items, cancellation deadlines. No model
   decides whether two events overlap.

### The assistant

A tool-using agent with about twenty tools (read trips and itinerary, find free time, search activities, propose
bookings, start a website task…). It works from database state, not from chat memory. Anything with side effects
becomes an **action** that a person must approve. The approval is bound to a hash of the exact proposal, and the
provider's response is verified before anything is marked booked. Without AI keys an offline assistant answers common
questions straight from the data and says that it's offline.

It is one assistant, not several: the activity search, the browser agent, live context and the planner are all its
tools. When you ask for something ("add dinner at 8"), it goes straight into the plan. When the idea is the
assistant's own, it goes in as a suggestion you can accept. Bookings and payments always wait for your approval.

### Live context

| What | Source | Key |
|---|---|---|
| Forecast per trip day (16 days ahead): rain chance, wet hours, "better indoors" | [Open-Meteo](https://open-meteo.com) | none |
| Strikes, protests, closures, weather alerts, searched in the local language | [Google News RSS](https://news.google.com), [GDELT](https://www.gdeltproject.org) as fallback | none |
| General web search for the assistant | [Tavily](https://tavily.com) (1,000 free searches/month), else Google News | `TAVILY_API_KEY`, optional |
| Ways to get from A to B | Google Maps, Google Flights, and official operators' sites | none |

The assistant gets these as tools (`get_weather`, `check_local_news`, `web_search`, `plan_journey`) with the whole trip
in view, so "what should we do Saturday?" accounts for Saturday's rain, and "can we take the bus?" checks for a
transport strike. Headlines are links, not verified fact. The assistant says where it read them, and Tandem drops
headlines about dates that have passed.

### AI providers

| Provider | Used for | Rule |
|---|---|---|
| Gemini | Reading PDFs and images, the main assistant | Primary |
| Z.ai (GLM) | Text, a free vision model, fallback | Additional |
| Groq | Fast text-only tasks | **Never receives files.** Enforced in the router *and* the provider client, with tests |

Only free-tier models are used unless `AI_ALLOW_PAID_MODELS=true`. Everything degrades gracefully: no keys means the
local parser plus the offline assistant, never a fake answer.

### The browser agent

42 real airline, rail, bus, museum and gallery sites are listed. By default they're **link-only**: Tandem doesn't
automate sites whose terms haven't been reviewed (Ryanair, which forbids it, is permanently link-only). An operator
can allow assisted *search* per site; the agent then checks robots.txt, stays on the site's own domain, refuses to
type into password or payment fields, stops at CAPTCHAs and logins, and hands off before personal details. On
Tandem's own simulated sites it completes the whole flow after approval, which is what the demo shows.

### Frontend

React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, Radix primitives, Leaflet and [Motion](https://motion.dev)
for the springy bits (sliding tab pills, staggered lists, the route line that draws itself). On phones it follows
Apple's conventions: safe-area insets, a floating tab bar, 44pt touch targets, UISwitch-sized toggles, 16px inputs so
iOS doesn't zoom, bottom sheets instead of modals, and reduced-motion support.

### Installable app (PWA)

Tandem is a Progressive Web App: a web manifest with PNG and maskable icons, and a Workbox service worker
(`vite-plugin-pwa`) that precaches the app shell and every page, so it starts with no connection. API responses are
never cached by the service worker. Instead, trips, itineraries, reservations and conflicts are kept on the device
for up to a week through TanStack Query's `dehydrate`/`hydrate` (`frontend/src/lib/offline.ts`). That copy belongs to
one user and is wiped on sign-out or when someone else signs in. Without a connection the app opens with that copy and
an offline strip; pages that need the server say so with a retry button instead of looking empty. New versions are
offered with a "Reload" prompt rather than swapped in mid-task. Chrome and Android get a native Install button; iPhone
users get the Share → Add to Home Screen steps.

### Calendar sync

`/api/v1/calendar` serves RFC 5545 files: times in UTC so any calendar shows them correctly, lines folded at 75 octets,
stable UIDs so edits update events instead of duplicating them. The subscription link carries a random token that is
stored encrypted (so Settings can show it again) and looked up by its HMAC; resetting it revokes the old link.

### Security & privacy, briefly

Server-side sessions with CSRF headers, encrypted files/tokens/extractions at rest, per-user AI consent enforced on
the server, rate limits on auth and demo creation, SSRF-safe link import, and prompt-injection-aware extraction
(documents are data, never instructions). More in [docs/SECURITY.md](docs/SECURITY.md) and
[docs/AI_PRIVACY.md](docs/AI_PRIVACY.md).

---

## Running it

Prerequisites: Python 3.11, Node 20+, Tesseract (`brew install tesseract`). PostgreSQL comes from the `pgserver`
package's bundled binaries, or bring any PostgreSQL 14+.

```bash
python3.11 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt pgserver
scripts/dev-db.sh start                           # PostgreSQL 16 on :5433
cp .env.example backend/.env                      # set SECRET_KEY and ENCRYPTION_KEY (commands inside)

cd backend
.venv/bin/flask --app app db upgrade
.venv/bin/flask --app app run --port 5050         # terminal 1: API
.venv/bin/flask --app app worker                  # terminal 2: jobs + browser agent
npm --prefix ../frontend install
npm --prefix ../frontend run dev                  # terminal 3: http://localhost:5173
```

### Keys

None are required. The short version:

| Get this | To unlock |
|---|---|
| `GEMINI_API_KEY` ([AI Studio](https://aistudio.google.com/apikey), free) | Reading PDFs/photos with AI, the full assistant |
| `ZAI_API_KEY` ([Z.ai](https://z.ai/manage-apikey/apikey-list), free models) | Second provider + free vision model |
| `GROQ_API_KEY` ([GroqCloud](https://console.groq.com/keys), free) | Fast text tasks |
| `TAVILY_API_KEY` ([Tavily](https://app.tavily.com), 1,000 free searches/month) | General web search for the assistant |
| Google OAuth client | Read-only Gmail import |
| Viator / GetYourGuide / Booking.com / Expedia partner credentials | Live activities and bookings |

Weather (Open-Meteo), local news (Google News, GDELT), places (OpenStreetMap) and journey links need no keys.
The full list, with where to get each key and what it switches on, is in
[docs/ENVIRONMENT.md](docs/ENVIRONMENT.md). `flask --app app env-status` shows what your environment has (without
printing secrets), and `scripts/vercel-env-push.sh` copies keys to Vercel without echoing them.

### Tests

```bash
cd backend && .venv/bin/python -m pytest      # 109 tests on a real PostgreSQL; providers are mocked
cd frontend && npx vitest run && npx tsc -b --noEmit
```

### Deploying

- **Docker:** `docker compose up -d --build` runs PostgreSQL, Redis, migrations, the web app, the job worker and a
  Playwright browser worker.
- **Vercel:** `api/index.py` is the serverless entry, the SPA is served statically, jobs run inline, files are
  stored encrypted in PostgreSQL (Neon), and a cron runs the scheduled checks.

Details in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Docs

[Product overview](docs/PRODUCT_OVERVIEW.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Environment & keys](docs/ENVIRONMENT.md) · [Database schema](docs/DATABASE_SCHEMA.md) ·
[API reference](docs/API_REFERENCE.md) · [AI providers](docs/AI_PROVIDER_CONFIGURATION.md) ·
[AI privacy](docs/AI_PRIVACY.md) · [Document ingestion](docs/DOCUMENT_INGESTION.md) ·
[Agent](docs/AGENT_ARCHITECTURE.md) · [Approvals](docs/APPROVAL_SYSTEM.md) ·
[Browser agent](docs/BROWSER_AGENT.md) · [Provider integrations](docs/PROVIDER_INTEGRATIONS.md) ·
[Booking.com](docs/BOOKING_COM_INTEGRATION.md) · [Expedia](docs/EXPEDIA_INTEGRATION.md) ·
[Airlines](docs/AIRLINE_INTEGRATIONS.md) · [Demo](docs/DEMO_ENVIRONMENT.md) · [Security](docs/SECURITY.md) ·
[Status](docs/IMPLEMENTATION_STATUS.md)

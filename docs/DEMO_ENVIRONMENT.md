# Demo environment

The demo uses the same frontend, API, pipeline, conflict engine, assistant and approval system as
production. Only the booking provider is simulated.

## Access

- **Explore the demo** (sign-in page) → `POST /api/v1/auth/demo` creates an isolated workspace
  (its own `demo_tenant`) for that visitor, valid for `DEMO_SESSION_HOURS` (24 h). Expired workspaces,
  their users and stored files are deleted by the worker's periodic job.
- **Shared account** `demo@tandem.travel` for presentations: `flask --app app seed-demo [--password …]`
  (password from `DEMO_ACCOUNT_PASSWORD` or generated and printed once). Re-running resets it.
- `DEMO_MODE=true` disables registration for a demo-only deployment.

## Seeded scenario — "Rome long weekend" from Craiova, 12–16 November

Dates are anchored to the next 12 November so the trip is always upcoming (12–16 Nov 2026 now).

The names are real (Craiova airport, Wizz Air, Rome Fiumicino, Hotel Santa Maria, the Vatican Museums, Da Enzo al 29) and
the bookings are not: references, prices and flight numbers are made up, and every generated document says so on the
page. Tandem does not forge a real company's confirmation. The route and times are a sample too: check Wizz Air's own
timetable (or the Google Flights link in the app) for what actually flies.

| Item | Details |
|---|---|
| Flights | Wizz Air CRA → FCO Thu 06:30 Craiova (EET) → 07:35 Rome (CET); FCO → CRA Mon 17:20 → 20:25; booking WZ7QRM (sample) |
| Hotel | Hotel Santa Maria, Trastevere, 4 nights, HSM-58213; **updated reservation** (early check-in 13:00 instead of 15:00) applied with history |
| Museum | Vatican Museums timed entry Fri 09:30–12:30, VM-20931 |
| Walking tour | Trastevere Twilight Walking Tour Sat 17:30–19:30, PLT-4471 (from a screenshot) |
| Restaurant | Da Enzo al 29 Sat 19:00, DE-1906 (from an email) — **conflict** with the tour |
| Free time | Sunday 14:00–18:00 |
| Suggestion | Borghese Gallery timed entry Sunday 10:00 (suggested) |
| Documents | 2 PDFs for the hotel, flight e-ticket PDF, museum ticket PDF, tour screenshot PNG, restaurant EML |
| Conversation | "What's on Saturday?" answered by the offline assistant from the seeded data |

All documents are generated (`services/demo/documents.py`) and stamped "DEMO DOCUMENT – fictional
booking". Names, references, the airline, hotel, operators and restaurant are fictional.

## Live samples (Inbox → "Try a sample document")

| Sample | Shows |
|---|---|
| Colosseum tour e-ticket (PDF) | extraction → joins the Rome trip → new overlap with the Vatican visit |
| Osteria booking screenshot (PNG) | OCR / vision extraction of an image; fits the free Sunday |
| Lisbon hotel confirmation (EML) | grouping proposes a **new trip** |

Samples go through the real pipeline (download them to try drag & drop).

## Full demo script (≈ 5 minutes)

1. Explore the demo → Home shows the trip, alerts and suggestion.
2. Trip → itinerary (cross-timezone flight labels, conflict markers, suggestion), Reservations
   (verification badges, applied hotel update), Map, Alerts → *Suggest fixes*.
3. Inbox → upload the Colosseum sample → review evidence badges and the grouping reason → accept →
   the new conflict appears.
4. Assistant → "Find a workshop on Sunday that fits my plans" → *Prepare booking* → live quote →
   approval card → *Approve & book* → in progress → **completed and verified** (simulated) → the
   workshop appears in the itinerary.
5. Approvals → history; Settings → AI & privacy, API usage, Connected accounts (honest provider states).

## Safety guarantees (tested in `tests/test_agent_approvals.py::test_demo_isolation`)

- Demo users can only reach the simulator; real users cannot reach the simulator.
- Gmail cannot be connected from a demo workspace; no email is ever sent.
- No real payment details are collected anywhere; simulated bookings say "nothing was charged".
- Each visitor's workspace is separate; demo data never mixes with real accounts.
- External AI in the demo (if configured) processes only the fictional documents and is capped at
  `DEMO_DAILY_AI_REQUESTS` per workspace per day.

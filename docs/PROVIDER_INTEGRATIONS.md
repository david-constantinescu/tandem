# Travel provider integrations

All providers implement `TravelProviderAdapter` (`services/providers/base.py`): `capabilities`,
`health_check`, `search`, `get_details`, `check_availability`, `create_booking`, `get_booking`,
`modify_booking`, `cancel_booking`. Unsupported operations raise explicit capability errors.

Capability states shown in the UI: not configured · configuration required · **awaiting partner
approval** · sandbox only · search only · search and availability · redirect only · booking enabled ·
management enabled · temporarily unavailable · disabled · simulated (demo).

The registry (`providers/registry.py`) is the only place adapters are created: demo users get only
the simulator; real users never get the simulator.

## Status (researched 2026-10-30)

| Provider | Access model | Implemented | State without credentials |
|---|---|---|---|
| **Simulator** (demo) | built in | search, details, availability, idempotent booking, read-back, cancel | simulated (demo only) |
| **OpenStreetMap places** (Overpass) | public, keyless; usage policy applies | search near a location by category; cached 24 h; no prices/availability; "listed hours (unverified)" | search only |
| **Booking.com Demand API — Attractions** | Affiliate partner; Attractions is an early-access pilot granted by an account manager | city lookup, `/attractions/search`, `/attractions/details`; redirect booking with affiliate id | awaiting partner approval |
| **Expedia Rapid Activities** | Early-access beta (Q3 2026), GA planned 2027; OAuth 2.0; booking needs Payments API token | capability reporting, EAN signature helper; search intentionally disabled until endpoints are issued | awaiting partner approval |
| **Viator Partner API v2** | Affiliate API key (self-serve basic access); merchant access for API booking | free-text product search, link-out to Viator | awaiting partner approval |
| **GetYourGuide Partner API** | Approved partners | tour search, link-out | awaiting partner approval |
| Tiqets, Klook, Headout | Partner programmes | not yet implemented (Phase 3, one at a time) | — |
| Eventbrite | Public event search API was retired; only organiser-scoped APIs remain | not planned | — |
| Google Places | Paid; place listings are not ticket availability | not used | — |

Untested parts are labelled in code and here: Booking.com, Viator and GetYourGuide request shapes follow
their documentation but have not been exercised with live credentials (Viator's endpoint paths must be
confirmed with a sandbox key — its OpenAPI spec could not be retrieved during research).

## Activity search (`providers/activities.py`)

Searches every operational adapter, reports per-provider counts and errors, and — when a trip is
given — computes **free windows** for the day (08:30–22:00, 30-minute buffers around non-cancelled
events) and marks each result as *fits your free time* (with fitting slots), *no slot fits*, or
*availability unknown*. Distance from the trip's hotel is included. Results are ranked fit-first.

## Booking flow

Select result → live quote (`check_availability`) → proposal awaiting approval → user approves the
exact payload → re-quote → `create_booking` with idempotency key → `get_booking` verification →
reservation + itinerary + conflict re-check → notification. Redirect-only providers produce a
link-out action instead. See APPROVAL_SYSTEM.md.

## Adding a provider

1. Subclass `TravelProviderAdapter`, implement `state()`/`capabilities()` honestly and only the
   operations the provider documents for your access level.
2. Register it in `REAL_ADAPTERS`.
3. Add credentials to `.env.example` and a section here; add adapter tests with mocked HTTP.

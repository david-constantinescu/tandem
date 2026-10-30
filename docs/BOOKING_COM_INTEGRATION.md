# Booking.com integration

Adapter: `BookingComAdapter` in `backend/app/services/providers/partners.py`.

## What the official documentation says (checked 2026-10-30)

- Demand API base: `https://demandapi.booking.com/{version}` (production) and
  `https://demandapi-sandbox.booking.com/{version}` (sandbox). 3.1 is in maintenance mode; 3.3 is the
  latest stable; Attractions appeared as 3.2 Beta.
- Authentication: Bearer token plus `X-Affiliate-Id` header on every request.
- Access is **partner-dependent**: an ordinary Booking.com account does not provide API access.
- **Attractions** ([quick guide](https://developers.booking.com/demand/docs/attractions/attractions-quick-guide)):
  early-access pilot for selected partners; contact your Booking.com account manager.
  - `POST /attractions/search` — one criterion (cities, countries, points of interest or IDs), dates
    within the 180-day window and ≤ 90 days range; returns price total/currency, free-cancellation flag
    and Booking.com web/app URLs.
  - `POST /attractions/details` — up to 100 IDs; name, description, categories, duration, photos,
    locations, ratings. No price/availability.
  - `POST /attractions/points-of-interest`.
  - **No booking endpoint**: travellers are redirected to the Booking.com attraction URL (with `aid`).
- Accommodation, car rentals and orders exist in the Demand API but are outside Tandem's initial
  booking scope (activities only).

## What Tandem implements

- State: `awaiting_partner_approval` without `BOOKING_COM_API_TOKEN` + `BOOKING_COM_AFFILIATE_ID`;
  `sandbox_only` (sandbox env) or `redirect_only` (production) with them.
- City resolution via `POST /common/locations/cities` (cached 30 days) → `attractions/search` →
  `attractions/details` merge → results with price, free-cancellation note and Booking.com URL.
- Booking stays **redirect-only** (`link_out` action), matching the documented flow.
- Not yet exercised against live credentials.

## Configuration

```
BOOKING_COM_AFFILIATE_ID=
BOOKING_COM_API_TOKEN=
BOOKING_COM_ENV=sandbox
BOOKING_COM_API_VERSION=3.3      # use 3.2 for the Beta path if your pilot access is on 3.2/Beta
```

## Next steps once access is granted

1. Run searches in sandbox, confirm response fields against the adapter mapping, add recorded
   fixtures to tests.
2. Add `health_check` call (e.g. languages endpoint) and surface it in Settings.
3. If Booking.com later documents an attractions orders flow, add `check_availability`/`create_booking`
   behind the existing approval system.

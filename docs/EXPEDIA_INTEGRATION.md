# Expedia integration

Adapter: `ExpediaAdapter` in `backend/app/services/providers/partners.py`.

## Findings (checked 2026-10-30)

- Rapid offers Lodging, Cars, Flights and **Activities** APIs ([Rapid](https://developers.expediagroup.com/rapid/)).
- **Rapid Activities** ([overview](https://developers.expediagroup.com/rapid/activities)) is an
  early-access preview for selected partners: beta programmes from Q3 2026, general availability in
  2027. Contact an account manager to join.
- Documented flow: discover inventory by region (`GET /v2/regions/{region_id}/activity-groups`,
  `GET /v2/regions/{region_id}/activities`, `GET /experiences/activities/content`) → availability and
  prices → pre-booking price check returning a booking token → create booking with the token and a
  `payment_token` from the Payments API → retrieve, cancel, vouchers.
- The full endpoint reference is to be added to the API Explorer after the pilot stage.
- Activities uses **OAuth 2.0**; lodging/common Rapid APIs use the EAN `APIKey`/`Signature`/`timestamp`
  header (SHA-512 of key + secret + timestamp).
- A `test` HTTP header triggers simulated responses (`standard`, `bad_link`, `invalid_input`,
  `price_mismatch`, `sold_out`, `internal_server_error`, `service_unavailable`).

## What Tandem implements

- State: `awaiting_partner_approval` unless `EXPEDIA_API_KEY`, `EXPEDIA_SHARED_SECRET` **and**
  `EXPEDIA_ACTIVITIES_ENABLED=true` are set.
- EAN signature helper (`signature()`), capability notes in the UI.
- Activity search deliberately raises "beta access pending" even when enabled, because the endpoint
  reference is not public yet. Nothing is faked.

## Next steps once beta access is granted

1. Implement OAuth client-credentials token retrieval (token URL from onboarding material).
2. Map region discovery via the Geography API, then availability and price check into
   `check_availability`.
3. Implement `create_booking` with the Payments API token flow behind the approval system; use the
   `test` header values for adapter tests (`price_mismatch` → re-approval, `sold_out` → failed).

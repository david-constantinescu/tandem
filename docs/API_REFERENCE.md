# API reference

The machine-readable OpenAPI 3.1 document is served at `GET /api/v1/openapi.json` and exported to
[`docs/openapi.json`](openapi.json) (`flask --app app openapi ../docs/openapi.json`). 75 paths.

## Conventions

- Base path `/api/v1`. JSON in and out.
- Success: `{"data": ..., "meta": {...}?}`. Errors: `{"error": {"code": "...", "message": "...", "details": ...}}`
  with 400/401/403/404/409/413/422/429/5xx.
- Auth: session cookie `tandem_session` (HttpOnly, SameSite=Lax, Secure in production) set by
  `/auth/login`, `/auth/register` or `/auth/demo`. Every non-GET request needs `X-CSRF-Token`
  (returned by those endpoints and `/auth/me`).
- Resources owned by other users return 404.
- Event and reservation times are returned as UTC (`start_at`) and as local time in their own zone
  (`start_local`, `start_tz`).

## Endpoints by area

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/demo`, `POST /auth/logout`, `GET /auth/me` |
| Trips | `GET/POST /trips`, `GET/PATCH/DELETE /trips/{id}`, `POST /trips/{id}/destinations`, `DELETE /trips/{id}/destinations/{dest}`, `POST /trips/{id}/travellers`, `GET /trips/{id}/reservations`, `GET /trips/{id}/itinerary`, `GET /trips/{id}/documents`, `GET /trips/{id}/conflicts`, `POST /trips/{id}/conflicts/explain`, `GET /trips/{id}/map` |
| Inbox | `GET /inbox`, `POST /inbox/upload` (multipart `files`, optional `trip_id`), `POST /inbox/paste`, `POST /inbox/url`, `GET /inbox/{id}`, `POST /inbox/{id}/review`, `POST /inbox/{id}/ignore`, `POST /inbox/{id}/retry`, `DELETE /inbox/{id}`, `GET /inbox/email-candidates`, `POST /inbox/email-candidates/import` |
| Documents | `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/download`, `GET /documents/{id}/preview`, `DELETE /documents/{id}` |
| Reservations | `GET/POST /reservations`, `GET/PATCH/DELETE /reservations/{id}`, `POST /reservations/{id}/move`, `GET /reservations/{id}/changes`, `POST /reservations/changes/{id}/apply`, `POST /reservations/changes/{id}/dismiss` |
| Itinerary | `POST /itinerary/events`, `PATCH/DELETE /itinerary/events/{id}` |
| Activities | `GET /activities/providers`, `POST /activities/search`, `GET /activities/{provider}/{id}`, `POST /activities/{provider}/{id}/availability`, `POST /activities/proposals`, `GET/POST /activities/saved`, `DELETE /activities/saved/{id}` |
| Assistant | `GET/POST /assistant/conversations`, `GET/DELETE /assistant/conversations/{id}`, `GET/POST /assistant/conversations/{id}/messages` |
| Approvals | `GET /approvals`, `GET /approvals/{id}`, `POST /approvals/{id}/approve` (`{payload_hash}`), `POST /approvals/{id}/reject` |
| Integrations | `GET /integrations`, `POST /integrations/gmail/connect`, `GET /integrations/gmail/callback`, `POST /integrations/gmail/sync`, `POST /integrations/gmail/disconnect` |
| Notifications | `GET /notifications`, `POST /notifications/{id}/read`, `POST /notifications/read-all` |
| Settings | `GET /settings`, `PATCH /settings/profile`, `PATCH /settings/preferences`, `GET/PUT /settings/ai`, `GET /settings/usage`, `GET /settings/providers`, `GET /settings/sessions`, `DELETE /settings/sessions/{id}`, `POST /settings/password`, `GET /settings/export`, `POST /settings/delete-account` |
| Demo | `GET /demo/samples`, `GET /demo/samples/{key}`, `POST /demo/samples/{key}/upload` (demo users only) |
| Health | `GET /health` |

## Review payload example

```json
POST /api/v1/inbox/{document_id}/review
{"decisions": [
  {"record_id": "…", "decision": "accept", "corrections": {"seat": "15A", "start_local": "2026-11-12T08:15"},
   "trip_id": "…"},
  {"record_id": "…", "decision": "accept", "new_trip_name": "Lisbon · Feb 2027"},
  {"record_id": "…", "decision": "reject"}
]}
```

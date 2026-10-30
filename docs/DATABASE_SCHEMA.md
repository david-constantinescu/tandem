# Database schema

PostgreSQL, managed by Alembic (`backend/migrations`). UUID primary keys, `timestamptz` everywhere,
JSONB for flexible attributes. Every user-owned table has `user_id` with `ON DELETE CASCADE`; services
filter by owner and the API returns 404 for other users' rows. Sessions run with `timezone=utc`.

| Table | Purpose | Notes |
|---|---|---|
| `users` | Accounts | `is_demo`, `demo_tenant_id`, home city/airport, locale, timezone |
| `user_sessions` | Server-side sessions | stores HMAC of the token, CSRF token, expiry, revocation |
| `user_preferences` | Interests, pace, budget, accessibility, notification prefs, storage settings, auto-organise | |
| `user_ai_settings` | AI mode (`off`/`text_only`/`full`), allowed providers, preference, consent time | enforced by the router |
| `demo_tenants` | Isolated demo workspaces with expiry | cleanup deletes users and files |
| `trips` | Trips | `created_via` (user/auto/demo), `grouping` reasons, `known_conflicts` keys for notifications |
| `trip_destinations` | Ordered destinations with coordinates and timezone | multi-destination trips |
| `travellers` | Trip travellers | |
| `reservations` | Bookings | UTC `start_at`/`end_at` + `start_tz`/`end_tz`, price, policy, `details` JSONB (flight number, seat, history…), `verification`, `source_document_id` |
| `reservation_changes` | Detected updates | `changes` = field → {old,new}; pending/applied/dismissed; history preserved |
| `itinerary_events` | Timeline | linked to a reservation (role main/start/end) or standalone; type, status, both locations for transport |
| `documents` | Inbox items and stored originals | checksum, storage key, status, encrypted extracted text, extraction method, parent (email attachments), duplicate link |
| `processing_jobs` | Job queue | status, attempts, run_after, lock owner; claimed with SKIP LOCKED |
| `extracted_records` | Candidate records per document | normalised `data`, confidence, notes, grouping proposal, matched reservation |
| `extracted_fields` | Field-level provenance | value, encrypted evidence quote, page, verification state |
| `provider_files` | Temporary AI-provider copies (Gemini Files API) | provider file id/uri, expiry, deletion status |
| `conversations`, `messages` | Assistant | messages store tool-call summaries, references, linked action ids, provider/model |
| `agent_actions` | Proposals and executions | payload + `payload_hash`, cost, consequences, expiry, idempotency key, result/error |
| `approvals` | Decisions bound to a payload hash | |
| `provider_bookings` | Provider-side booking records | verified_at, simulated flag |
| `saved_activities` | Saved discovery results | |
| `notifications` | In-app notifications | de-duplicated by `(user_id, dedupe_key)` |
| `audit_logs` | Security-relevant events | no document contents or secrets |
| `ai_usage_records` | Per-attempt AI usage | written on an independent connection so failures are counted |
| `provider_status` | Provider health / quota cooldowns | |
| `cache_entries` | AI responses, geocoding, routes, OSM searches, simulator store | namespaced, with expiry |
| `integration_connections` | Gmail connection | encrypted tokens, history id, last sync |
| `email_candidates` | Travel-looking Gmail messages | unique per (user, message id) |
| `browser_tasks` | State model for user-guided website workflows | design scaffold only (see AGENT_ARCHITECTURE) |

Encrypted columns (`EncryptedText`, `EncryptedJSON`) use Fernet with `ENCRYPTION_KEY`; migrations store
them as `text`/`bytea`.

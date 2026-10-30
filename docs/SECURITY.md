# Security

## Authentication and sessions

- Passwords hashed with Werkzeug scrypt; constant-time behaviour for unknown emails; minimum 10 chars.
- Sessions are random 256-bit tokens in an HttpOnly, SameSite=Lax cookie (Secure in production).
  Only an HMAC of the token is stored; sessions expire (14 days default), can be revoked individually,
  and all are revoked on password change.
- CSRF: every state-changing request requires `X-CSRF-Token` matching the session; plus SameSite.
- Rate limits (Flask-Limiter, per client IP): register 10/h, login 20/15 min, demo workspaces
  `DEMO_RATE_LIMIT` (120/h default), uploads 60/h, assistant 60/h, approvals 30/h, URL import 30/h.
  Behind a proxy set `TRUSTED_PROXIES` (Werkzeug ProxyFix); raw `X-Forwarded-For` is never trusted.

## Authorisation

- All user data is scoped by `user_id`; `get_owned` returns 404 for other users' resources. Tests
  cover cross-user access to trips, documents, downloads and uploads into others' trips.
- Agent tools re-check ownership on every call; there is no generic data or SQL tool.
- Demo isolation is enforced in the provider registry and integration guards.

## Data protection

- Fernet encryption (`ENCRYPTION_KEY`, rotatable) for stored files, extracted text, evidence quotes
  and OAuth tokens. S3 objects are additionally stored with server-side encryption.
- Private storage only; downloads stream through an authenticated endpoint with
  `Content-Disposition: attachment`, `nosniff` and a sandbox CSP (inline view only for PDF/images).
- Uploaded HTML is never rendered raw: previews are sanitised with `nh3` (no scripts, styles, event
  handlers, images or non-https links).
- Logs exclude bodies, prompts, documents, tokens and passwords. Audit log records security events.

## Input handling

- Upload validation: extension allow-list, MIME consistency, magic-byte signatures, size and count
  limits, filename sanitisation, duplicate detection. Files are never executed.
- URL import is SSRF-hardened (public addresses only, re-checked on each redirect, ports 80/443, size
  and time caps). **Residual risk:** DNS rebinding between the address check and the connection;
  mitigate in production with an egress proxy that enforces the same rules.
- Request bodies validated with Pydantic; SQLAlchemy parameterisation throughout.

## AI-specific controls

- Untrusted content (documents, emails, pages) is passed as data with explicit instructions; it can't
  change permissions because every effect is enforced in backend code.
- Groq can never receive files (router + provider checks). Paid/unknown models are blocked by default.
- AI-generated booking status is never trusted: completion requires provider read-back verification.
- AI-extracted URLs are displayed as information only and never fetched automatically.

## Headers

API: `Content-Security-Policy: default-src 'none'`, `Cache-Control: no-store`, `X-Frame-Options: DENY`,
`X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, HSTS when secure cookies
are enabled. SPA (when served by Flask): restrictive CSP allowing self, Google Fonts and OSM tiles.

## Dependency scanning

Run `pip-audit -r backend/requirements.txt` and `npm audit --omit=dev` in CI. Pinned Python
dependencies; npm lockfile committed.

## Reporting

Please report vulnerabilities privately to the maintainers rather than opening a public issue.

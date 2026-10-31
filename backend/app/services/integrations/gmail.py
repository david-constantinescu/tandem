"""gmail (doar citire, oauth oficial google). emailurile de calatorie se importa singure"""
from __future__ import annotations

import base64
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from flask import current_app

from app.i18n import T, locale_of, tr
from app.extensions import db
from app.models import Document, EmailCandidate, IntegrationConnection, User
from app.services.audit import audit
from app.services.notifications.service import notify
from app.tasks.queue import RetryableJobError
from app.utils.errors import APIError, Forbidden, ValidationFailed
from app.utils.timeutil import utcnow

log = logging.getLogger("tandem.gmail")

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
TRAVEL_QUERY = (
    '(subject:(booking OR reservation OR confirmation OR itinerary OR "e-ticket" OR ticket OR "check-in" OR '
    '"boarding pass" OR "your trip" OR "schedule change" OR cancelled OR voucher) OR '
    'from:(booking.com OR expedia OR airbnb OR ryanair OR wizzair OR lufthansa OR britishairways OR klm OR '
    'airfrance OR aa.com OR trenitalia OR italotreno OR sncf OR eurostar OR flixbus OR viator OR getyourguide OR '
    'tiqets OR klook OR headout OR opentable OR thefork)) -category:promotions'
)


def configured() -> bool:
    cfg = current_app.config
    return bool(cfg.get("GOOGLE_CLIENT_ID") and cfg.get("GOOGLE_CLIENT_SECRET"))


def _guard(user: User) -> None:
    if user.is_demo:
        raise Forbidden("Gmail cannot be connected from the demo workspace", code="demo_restricted")
    if not configured():
        raise APIError("Gmail integration is not configured on this server (GOOGLE_CLIENT_ID/SECRET)",
                       code="integration_not_configured", status=503)


def start_connect(user: User) -> str:
    _guard(user)
    conn = db.session.execute(db.select(IntegrationConnection).where(
        IntegrationConnection.user_id == user.id, IntegrationConnection.provider == "gmail")).scalar_one_or_none()
    if conn is None:
        conn = IntegrationConnection(user_id=user.id, provider="gmail", status="pending")
        db.session.add(conn)
    conn.oauth_state = secrets.token_urlsafe(32)
    db.session.flush()
    cfg = current_app.config
    params = {"client_id": cfg["GOOGLE_CLIENT_ID"], "redirect_uri": cfg["GOOGLE_REDIRECT_URI"],
              "response_type": "code", "scope": SCOPE, "access_type": "offline", "prompt": "consent",
              "include_granted_scopes": "false", "state": conn.oauth_state}
    return f"{AUTH_URL}?{urlencode(params)}"


def finish_connect(user: User, code: str, state: str) -> IntegrationConnection:
    _guard(user)
    conn = db.session.execute(db.select(IntegrationConnection).where(
        IntegrationConnection.user_id == user.id, IntegrationConnection.provider == "gmail")).scalar_one_or_none()
    if conn is None or not conn.oauth_state or not secrets.compare_digest(conn.oauth_state, state or ""):
        raise ValidationFailed("OAuth state mismatch; please try connecting again", code="oauth_state")
    cfg = current_app.config
    resp = httpx.post(TOKEN_URL, data={"code": code, "client_id": cfg["GOOGLE_CLIENT_ID"],
                                       "client_secret": cfg["GOOGLE_CLIENT_SECRET"],
                                       "redirect_uri": cfg["GOOGLE_REDIRECT_URI"], "grant_type": "authorization_code"},
                      timeout=15)
    if resp.status_code != 200:
        conn.status = "error"
        conn.error = f"Token exchange failed ({resp.status_code})"
        raise ValidationFailed("Google did not accept the authorisation", code="oauth_failed")
    tokens = resp.json()
    granted = set((tokens.get("scope") or "").split())
    if SCOPE not in granted:
        conn.status = "error"
        conn.error = "Read-only Gmail access was not granted"
        raise ValidationFailed("Gmail read-only access was not granted", code="scope_missing")
    conn.tokens = {"access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token"),
                   "expires_at": (utcnow() + timedelta(seconds=int(tokens.get("expires_in", 3600)) - 60)).isoformat()}
    conn.scopes = sorted(granted)
    conn.oauth_state = None
    profile = _api(conn, "GET", "/profile")
    conn.account_email = profile.get("emailAddress")
    conn.history_id = str(profile.get("historyId") or "")
    conn.status = "connected"
    conn.error = None
    audit(user.id, "integration.connected", resource_type="integration", resource_id=conn.id, provider="gmail")
    return conn


def _access_token(conn: IntegrationConnection) -> str:
    tokens = conn.tokens or {}
    expires = datetime.fromisoformat(tokens["expires_at"]) if tokens.get("expires_at") else None
    if tokens.get("access_token") and expires and expires > utcnow():
        return tokens["access_token"]
    if not tokens.get("refresh_token"):
        conn.status = "error"
        conn.error = "Authorisation expired; reconnect Gmail"
        raise ValidationFailed(conn.error, code="reauth_required")
    cfg = current_app.config
    resp = httpx.post(TOKEN_URL, data={"client_id": cfg["GOOGLE_CLIENT_ID"], "client_secret": cfg["GOOGLE_CLIENT_SECRET"],
                                       "refresh_token": tokens["refresh_token"], "grant_type": "refresh_token"}, timeout=15)
    if resp.status_code != 200:
        conn.status = "error"
        conn.error = tr("Could not refresh Gmail access; reconnect Gmail", locale_of(conn.user_id))
        notify(conn.user_id, "integration_failure", T("Gmail needs to be reconnected"), conn.error,
               link="/settings/connections", severity="warning", dedupe_key=f"gmail_reauth:{conn.id}:{utcnow().date()}")
        raise ValidationFailed(conn.error, code="reauth_required")
    data = resp.json()
    conn.tokens = {**tokens, "access_token": data["access_token"],
                   "expires_at": (utcnow() + timedelta(seconds=int(data.get("expires_in", 3600)) - 60)).isoformat()}
    return data["access_token"]


def _api(conn: IntegrationConnection, method: str, path: str, **kwargs) -> dict:
    try:
        resp = httpx.request(method, f"{API}{path}", headers={"Authorization": f"Bearer {_access_token(conn)}"},
                             timeout=20, **kwargs)
    except httpx.HTTPError as exc:
        raise RetryableJobError(f"Gmail unreachable: {type(exc).__name__}", delay_seconds=120) from exc
    if resp.status_code == 429 or resp.status_code >= 500:
        raise RetryableJobError(f"Gmail temporarily unavailable ({resp.status_code})", delay_seconds=300)
    if resp.status_code == 401:
        conn.tokens = {**(conn.tokens or {}), "expires_at": None}
        raise ValidationFailed("Gmail authorisation was rejected", code="reauth_required")
    if resp.status_code >= 400:
        raise ValidationFailed(f"Gmail API error {resp.status_code}", code="gmail_error")
    return resp.json()


def sync_candidates(user_id: uuid.UUID, *, full: bool = False) -> int:
    conn = db.session.execute(db.select(IntegrationConnection).where(
        IntegrationConnection.user_id == user_id, IntegrationConnection.provider == "gmail",
        IntegrationConnection.status == "connected")).scalar_one_or_none()
    if conn is None:
        return 0
    query = TRAVEL_QUERY
    if conn.last_sync_at and not full:
        query += f" after:{int(conn.last_sync_at.timestamp()) - 3600}"
    else:
        query += " newer_than:365d"
    listing = _api(conn, "GET", "/messages", params={"q": query, "maxResults": 50})
    added = 0
    for item in listing.get("messages", []):
        mid = item["id"]
        exists = db.session.execute(db.select(EmailCandidate.id).where(
            EmailCandidate.user_id == user_id, EmailCandidate.message_id == mid)).first()
        if exists:
            continue
        meta = _api(conn, "GET", f"/messages/{mid}", params=[("format", "metadata"), ("metadataHeaders", "Subject"),
                                                              ("metadataHeaders", "From"), ("metadataHeaders", "Date")])
        headers = {h["name"].lower(): h["value"] for h in (meta.get("payload") or {}).get("headers", [])}
        received = datetime.fromtimestamp(int(meta.get("internalDate", "0")) / 1000, tz=timezone.utc)
        parts = (meta.get("payload") or {}).get("parts") or []
        db.session.add(EmailCandidate(
            user_id=user_id, connection_id=conn.id, message_id=mid, thread_id=meta.get("threadId"),
            subject=headers.get("subject", "")[:500], sender=headers.get("from", "")[:320], received_at=received,
            snippet=(meta.get("snippet") or "")[:500], has_attachments=any(p.get("filename") for p in parts)))
        added += 1
    conn.last_sync_at = utcnow()
    db.session.commit()
    if added:
        # no separate review step: travel emails go straight through the reading pipeline, and the assistant says
        # what it found in the chat (anything uncertain still waits for the user's check there)
        pending = db.session.execute(db.select(EmailCandidate).where(
            EmailCandidate.user_id == user_id, EmailCandidate.status == "candidate")).scalars().all()
        imported = import_messages(user_id, [str(c.id) for c in pending])
        if imported:
            from app.services.agent import feed

            user = db.session.get(User, user_id)
            loc = locale_of(user)
            docs = [c for c in pending if c.document_id]
            lines = "\n".join(f"- {c.subject or c.sender}" for c in docs[:8])
            feed.post(user, f"gmail:{conn.last_sync_at.isoformat()}",
                      tr("I brought in {n} travel emails from Gmail:", loc, n=imported) + "\n" + lines + "\n\n"
                      + tr("Bookings I could read are in your trips; anything I wasn't sure about is waiting for you in the Inbox.", loc),
                      references=[{"type": "document", "id": str(c.document_id), "label": c.subject[:60]} for c in docs[:8]],
                      notify_title=T("Imported from Gmail: {n}", n=imported))
            db.session.commit()
    return added


def import_messages(user_id: uuid.UUID, candidate_ids: list[str]) -> int:
    from app.services.ingestion.pipeline import _store_and_queue

    user = db.session.get(User, user_id)
    conn = db.session.execute(db.select(IntegrationConnection).where(
        IntegrationConnection.user_id == user_id, IntegrationConnection.provider == "gmail")).scalar_one_or_none()
    if conn is None or user is None:
        return 0
    count = 0
    created = []
    for cid in candidate_ids:
        cand = db.session.get(EmailCandidate, uuid.UUID(cid))
        if cand is None or cand.user_id != user_id or cand.status == "imported":
            continue
        raw = _api(conn, "GET", f"/messages/{cand.message_id}", params={"format": "raw"})
        data = base64.urlsafe_b64decode(raw["raw"] + "=" * (-len(raw["raw"]) % 4))
        if len(data) > current_app.config["MAX_UPLOAD_BYTES"]:
            cand.status = "skipped"
            continue
        doc = _store_and_queue(user, filename=(cand.subject[:80] or "email") + ".eml", mime_type="message/rfc822",
                               data=data, source="email", email_message_id=cand.message_id)
        cand.status = "imported"
        cand.document_id = doc.id
        created.append(doc)
        count += 1
    db.session.commit()
    from app.services.ingestion.pipeline import queue_after_commit

    queue_after_commit(created)
    return count


def disconnect(user: User, *, delete_imported: bool) -> None:
    from app.services.ingestion.pipeline import delete_document

    conn = db.session.execute(db.select(IntegrationConnection).where(
        IntegrationConnection.user_id == user.id, IntegrationConnection.provider == "gmail")).scalar_one_or_none()
    if conn is None:
        return
    token = (conn.tokens or {}).get("refresh_token") or (conn.tokens or {}).get("access_token")
    if token:
        try:
            httpx.post(REVOKE_URL, params={"token": token}, timeout=10)
        except httpx.HTTPError:
            log.warning("token revocation request failed")
    if delete_imported:
        for doc in db.session.execute(db.select(Document).where(Document.user_id == user.id,
                                                                Document.source == "email",
                                                                Document.parent_document_id.is_(None))).scalars():
            delete_document(user, doc)
    db.session.delete(conn)
    audit(user.id, "integration.disconnected", resource_type="integration", provider="gmail",
          deleted_imported=delete_imported)

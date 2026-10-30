from __future__ import annotations

from flask import Blueprint, current_app, redirect, request
from pydantic import BaseModel

from app.api._core import current_user, doc, login_required, ok, parse_body
from app.extensions import db
from app.models import IntegrationConnection
from app.services.integrations import gmail
from app.services.providers.registry import adapters_for
from app.tasks.queue import enqueue, run_inline_if_configured
from app.utils.errors import APIError, NotFound

bp = Blueprint("integrations", __name__, url_prefix="/api/v1/integrations")


class DisconnectBody(BaseModel):
    delete_imported: bool = False


def _gmail_conn():
    return db.session.execute(db.select(IntegrationConnection).where(
        IntegrationConnection.user_id == current_user().id, IntegrationConnection.provider == "gmail")).scalar_one_or_none()


@bp.get("")
@login_required
@doc("Connected accounts and travel provider states", tag="Integrations")
def list_integrations():
    u = current_user()
    conn = _gmail_conn()
    return ok({
        "gmail": {
            "available": gmail.configured() and not u.is_demo,
            "reason": "Not available in the demo workspace" if u.is_demo else (
                None if gmail.configured() else "Server is not configured with Google OAuth credentials"),
            "status": conn.status if conn else "disconnected", "account_email": conn.account_email if conn else None,
            "scopes": conn.scopes if conn else [], "last_sync_at": conn.last_sync_at.isoformat() if conn and conn.last_sync_at else None,
            "error": conn.error if conn else None,
        },
        "travel_providers": [a.capabilities() for a in adapters_for(u)],
    })


@bp.post("/gmail/connect")
@login_required
@doc("Start Gmail read-only OAuth; returns the Google consent URL", tag="Integrations")
def gmail_connect():
    url = gmail.start_connect(current_user())
    db.session.commit()
    return ok({"authorization_url": url})


@bp.get("/gmail/callback")
@doc("OAuth redirect target (browser navigation)", tag="Integrations")
def gmail_callback():
    front = current_app.config["FRONTEND_URL"].rstrip("/")
    from flask import g

    if g.get("user") is None:
        return redirect(f"{front}/login?next=/settings/connections")
    if request.args.get("error"):
        return redirect(f"{front}/settings/connections?gmail=denied")
    try:
        gmail.finish_connect(g.user, request.args.get("code", ""), request.args.get("state", ""))
        job = enqueue("gmail_sync", {"full": True}, user_id=g.user.id)
        db.session.commit()
        run_inline_if_configured(job)
    except APIError as exc:
        db.session.commit()
        return redirect(f"{front}/settings/connections?gmail=error&code={exc.code}")
    return redirect(f"{front}/settings/connections?gmail=connected")


@bp.post("/gmail/sync")
@login_required
@doc("Search Gmail for new travel emails", tag="Integrations")
def gmail_sync():
    if _gmail_conn() is None:
        raise NotFound("Gmail is not connected")
    job = enqueue("gmail_sync", {"full": False}, user_id=current_user().id)
    db.session.commit()
    run_inline_if_configured(job)
    return ok({"queued": True}, 202)


@bp.post("/gmail/disconnect")
@login_required
@doc("Disconnect Gmail, revoke tokens, optionally delete imported emails", body=DisconnectBody, tag="Integrations")
def gmail_disconnect():
    body = parse_body(DisconnectBody)
    gmail.disconnect(current_user(), delete_imported=body.delete_imported)
    db.session.commit()
    return ok({"disconnected": True})

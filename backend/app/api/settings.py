from __future__ import annotations

import io
import json
import zipfile
from datetime import timedelta

from flask import Blueprint, current_app, g, make_response, send_file
from pydantic import BaseModel, Field

from app.api._core import current_user, doc, login_required, ok, parse_body
from app.extensions import db
from app.models import (
    AgentAction, AIUsageRecord, Conversation, Document, ItineraryEvent, Message, Reservation, Trip, UserSession,
)
from app.models.user import AI_MODES
from app.schemas.serializers import (
    action_dict, conversation_dict, document_dict, event_dict, message_dict, reservation_dict, trip_dict, user_dict,
)
from app.services import users as user_service
from app.services.ai.router import provider_overview
from app.services.audit import audit
from app.services.ingestion.pipeline import delete_document
from app.services.providers.registry import adapters_for
from app.utils.errors import ValidationFailed
from app.utils.timeutil import is_valid_tz, utcnow

bp = Blueprint("settings", __name__, url_prefix="/api/v1/settings")


class ProfileBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    home_city: str | None = Field(default=None, max_length=120)
    home_airport: str | None = Field(default=None, max_length=8)
    timezone: str | None = None
    locale: str | None = Field(default=None, pattern="^(en|ro)$")


class PreferencesBody(BaseModel):
    interests: list[str] | None = None
    pace: str | None = Field(default=None, pattern="^(relaxed|balanced|packed)$")
    budget: str | None = Field(default=None, pattern="^(budget|moderate|premium)$")
    accessibility_needs: str | None = Field(default=None, max_length=500)
    default_currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    notification_prefs: dict[str, bool] | None = None
    retain_original_documents: bool | None = None
    auto_organize: bool | None = None


class AISettingsBody(BaseModel):
    mode: str
    allowed_providers: dict[str, bool] | None = None
    preferred_provider: str | None = None
    acknowledge_privacy: bool = False


class PasswordBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


class DeleteAccountBody(BaseModel):
    password: str
    confirm: str


def _prefs_dict(p) -> dict:
    return {"interests": p.interests, "pace": p.pace, "budget": p.budget, "accessibility_needs": p.accessibility_needs,
            "default_currency": p.default_currency, "notification_prefs": p.notification_prefs,
            "retain_original_documents": p.retain_original_documents, "auto_organize": p.auto_organize}


def _ai_dict(s) -> dict:
    return {"mode": s.mode, "allowed_providers": s.allowed_providers, "preferred_provider": s.preferred_provider,
            "consent_recorded_at": s.consent_recorded_at.isoformat() if s.consent_recorded_at else None}


@bp.get("")
@login_required
@doc("All settings for the current user", tag="Settings")
def get_settings():
    u = current_user()
    return ok({"profile": user_dict(u), "preferences": _prefs_dict(u.preferences), "ai": _ai_dict(u.ai_settings),
               "limits": {"max_upload_mb": current_app.config["MAX_UPLOAD_BYTES"] // (1024 * 1024),
                          "max_files_per_upload": current_app.config["MAX_FILES_PER_UPLOAD"]}})


@bp.patch("/profile")
@login_required
@doc("Update profile", body=ProfileBody, tag="Settings")
def update_profile():
    body = parse_body(ProfileBody)
    u = current_user()
    if body.timezone is not None and not is_valid_tz(body.timezone):
        raise ValidationFailed("Unknown timezone", code="invalid_timezone")
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(u, key, value.upper() if key == "home_airport" else value)
    db.session.commit()
    return ok(user_dict(u))


@bp.patch("/preferences")
@login_required
@doc("Update travel and notification preferences", body=PreferencesBody, tag="Settings")
def update_preferences():
    body = parse_body(PreferencesBody)
    p = current_user().preferences
    for key, value in body.model_dump(exclude_none=True).items():
        if key == "notification_prefs":
            value = {**p.notification_prefs, **value}
        setattr(p, key, value)
    db.session.commit()
    return ok(_prefs_dict(p))


@bp.get("/ai")
@login_required
@doc("AI privacy settings and provider capabilities", tag="Settings")
def get_ai():
    u = current_user()
    return ok({"settings": _ai_dict(u.ai_settings), "providers": provider_overview(),
               "paid_models_allowed": bool(current_app.config["AI_ALLOW_PAID_MODELS"]),
               "demo_external_ai": bool(u.is_demo and current_app.config["DEMO_ALLOW_EXTERNAL_AI"])})


@bp.put("/ai")
@login_required
@doc("Update AI privacy settings (consent is recorded)", body=AISettingsBody, tag="Settings")
def update_ai():
    body = parse_body(AISettingsBody)
    u = current_user()
    if body.mode not in AI_MODES:
        raise ValidationFailed("Unknown AI mode", code="invalid_mode")
    s = u.ai_settings
    rank = {"off": 0, "text_only": 1, "full": 2}
    if rank[body.mode] > rank.get(s.mode, 0) and not body.acknowledge_privacy:
        raise ValidationFailed("Please confirm you have read how external AI providers handle your data",
                               code="privacy_ack_required")
    s.mode = body.mode
    if body.allowed_providers is not None:
        s.allowed_providers = {k: bool(v) for k, v in body.allowed_providers.items() if k in ("gemini", "zai", "groq")}
    if body.preferred_provider in (None, "", "gemini", "zai", "groq"):
        s.preferred_provider = body.preferred_provider or None
    if body.mode != "off":
        s.consent_recorded_at = utcnow()
    audit(u.id, "settings.ai_updated", mode=body.mode, providers=s.allowed_providers)
    db.session.commit()
    return ok(_ai_dict(s))


@bp.get("/usage")
@login_required
@doc("AI usage over the last 30 days", tag="Settings")
def usage():
    u = current_user()
    since = utcnow() - timedelta(days=30)
    rows = db.session.execute(db.select(
        AIUsageRecord.provider, AIUsageRecord.model, AIUsageRecord.status,
        db.func.count(AIUsageRecord.id), db.func.coalesce(db.func.sum(AIUsageRecord.input_tokens), 0),
        db.func.coalesce(db.func.sum(AIUsageRecord.output_tokens), 0),
        db.func.coalesce(db.func.sum(AIUsageRecord.estimated_cost), 0),
    ).where(AIUsageRecord.user_id == u.id, AIUsageRecord.created_at >= since)
        .group_by(AIUsageRecord.provider, AIUsageRecord.model, AIUsageRecord.status)).all()
    recent = db.session.execute(db.select(AIUsageRecord).where(AIUsageRecord.user_id == u.id)
                                .order_by(AIUsageRecord.created_at.desc()).limit(25)).scalars().all()
    return ok({
        "summary": [{"provider": r[0], "model": r[1], "status": r[2], "requests": r[3], "input_tokens": int(r[4]),
                     "output_tokens": int(r[5]), "estimated_cost_usd": float(r[6])} for r in rows],
        "recent": [{"provider": r.provider, "model": r.model, "task": r.task, "status": r.status,
                    "input_tokens": r.input_tokens, "output_tokens": r.output_tokens, "latency_ms": r.latency_ms,
                    "error_code": r.error_code, "created_at": r.created_at.isoformat()} for r in recent],
        "paid_models_allowed": bool(current_app.config["AI_ALLOW_PAID_MODELS"]),
    })


@bp.get("/providers")
@login_required
@doc("Travel provider integration states", tag="Settings")
def travel_providers():
    return ok([a.capabilities() for a in adapters_for(current_user())])


@bp.get("/sessions")
@login_required
@doc("Active sign-in sessions", tag="Settings")
def sessions():
    u = current_user()
    rows = db.session.execute(db.select(UserSession).where(
        UserSession.user_id == u.id, UserSession.revoked_at.is_(None), UserSession.expires_at > utcnow())
        .order_by(UserSession.last_seen_at.desc())).scalars().all()
    return ok([{"id": str(s.id), "user_agent": s.user_agent, "created_at": s.created_at.isoformat(),
                "last_seen_at": s.last_seen_at.isoformat(), "current": s.id == g.session.id} for s in rows])


@bp.delete("/sessions/<session_id>")
@login_required
@doc("Sign out another session", tag="Settings")
def revoke_session(session_id):
    from app.api._core import get_owned

    sess = get_owned(UserSession, session_id, "session")
    sess.revoked_at = utcnow()
    db.session.commit()
    return ok({"revoked": True})


@bp.post("/password")
@login_required
@doc("Change password (signs out all sessions)", body=PasswordBody, tag="Settings")
def change_password():
    body = parse_body(PasswordBody)
    user_service.change_password(current_user(), body.current_password, body.new_password)
    audit(current_user().id, "auth.password_changed")
    db.session.commit()
    return ok({"changed": True})


@bp.get("/export")
@login_required
@doc("Export all of your data as a ZIP of JSON files", tag="Settings")
def export_data():
    u = current_user()
    trips = db.session.execute(db.select(Trip).where(Trip.user_id == u.id)).scalars().all()
    data = {
        "profile.json": user_dict(u),
        "trips.json": [trip_dict(t) for t in trips],
        "reservations.json": [reservation_dict(r) for r in db.session.execute(
            db.select(Reservation).where(Reservation.user_id == u.id)).scalars()],
        "itinerary.json": [event_dict(e) for e in db.session.execute(
            db.select(ItineraryEvent).where(ItineraryEvent.user_id == u.id)).scalars()],
        "documents.json": [document_dict(d, include_records=True) for d in db.session.execute(
            db.select(Document).where(Document.user_id == u.id)).scalars()],
        "actions.json": [action_dict(a) for a in db.session.execute(
            db.select(AgentAction).where(AgentAction.user_id == u.id)).scalars()],
    }
    convs = db.session.execute(db.select(Conversation).where(Conversation.user_id == u.id)).scalars().all()
    data["conversations.json"] = [{**conversation_dict(c), "messages": [message_dict(m) for m in db.session.execute(
        db.select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at)).scalars()]} for c in convs]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, payload in data.items():
            z.writestr(name, json.dumps(payload, indent=2, default=str))
        z.writestr("README.txt", "Tandem data export. Original documents can be downloaded individually from the Inbox.")
    buf.seek(0)
    audit(u.id, "data.exported")
    db.session.commit()
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"tandem-export-{utcnow():%Y%m%d}.zip")


@bp.post("/delete-account")
@login_required
@doc("Permanently delete the account and all data", body=DeleteAccountBody, tag="Settings")
def delete_account():
    body = parse_body(DeleteAccountBody)
    u = current_user()
    if body.confirm != "DELETE":
        raise ValidationFailed("Type DELETE to confirm", code="confirmation_required")
    user_service.authenticate(u.email, body.password)
    from app.services.integrations import gmail

    try:
        gmail.disconnect(u, delete_imported=False)
    except Exception:  # noqa: BLE001 - deletion must proceed even if revocation fails
        pass
    for d in db.session.execute(db.select(Document).where(Document.user_id == u.id,
                                                          Document.parent_document_id.is_(None))).scalars():
        delete_document(u, d)
    db.session.delete(u)
    db.session.commit()
    resp = make_response(*ok({"deleted": True}))
    resp.delete_cookie(current_app.config["SESSION_COOKIE_NAME"], path="/")
    return resp

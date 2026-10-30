from __future__ import annotations

from flask import Blueprint, current_app, g, make_response, request
from pydantic import BaseModel, EmailStr, Field

from app.api._core import client_ip, doc, login_required, ok, parse_body
from app.extensions import db, limiter
from app.schemas.serializers import user_dict
from app.services import users as user_service
from app.services.audit import audit
from app.utils.errors import Forbidden

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    display_name: str = Field(default="", max_length=120)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


def _with_session_cookie(payload: dict, token: str, status: int = 200, hours: int | None = None):
    resp, code = ok(payload, status)
    resp = make_response(resp, code)
    cfg = current_app.config
    resp.set_cookie(
        cfg["SESSION_COOKIE_NAME"], token, httponly=True, secure=cfg["SESSION_COOKIE_SECURE"], samesite="Lax",
        max_age=(hours or cfg["SESSION_TTL_HOURS"]) * 3600, path="/",
    )
    return resp


def _session_payload(user, sess) -> dict:
    return {"user": user_dict(user), "csrf_token": sess.csrf_token}


@bp.post("/register")
@limiter.limit("10 per hour")
@doc("Create an account", body=RegisterBody, tag="Auth", auth=False)
def register():
    if current_app.config["DEMO_MODE"]:
        raise Forbidden("Registration is disabled on this demo deployment", code="demo_mode")
    body = parse_body(RegisterBody)
    user = user_service.create_user(body.email, body.password, body.display_name)
    token, sess = user_service.start_session(user, request.user_agent.string)
    audit(user.id, "auth.register")
    db.session.commit()
    return _with_session_cookie(_session_payload(user, sess), token, 201)


@bp.post("/login")
@limiter.limit("20 per 15 minutes")
@doc("Sign in with email and password", body=LoginBody, tag="Auth", auth=False)
def login():
    body = parse_body(LoginBody)
    user = user_service.authenticate(body.email, body.password)
    token, sess = user_service.start_session(user, request.user_agent.string)
    audit(user.id, "auth.login", ip=client_ip())
    db.session.commit()
    return _with_session_cookie(_session_payload(user, sess), token)


@bp.post("/demo")
@limiter.limit(lambda: current_app.config["DEMO_RATE_LIMIT"])
@doc("Start an isolated demo workspace (fictional data, simulated providers)", tag="Auth", auth=False)
def demo():
    from app.services.demo.seed import create_demo_workspace

    if not current_app.config["DEMO_ACCOUNT_ENABLED"]:
        raise Forbidden("The demo is disabled on this deployment", code="demo_disabled")
    user = create_demo_workspace()
    hours = current_app.config["DEMO_SESSION_HOURS"]
    token, sess = user_service.start_session(user, request.user_agent.string, hours=hours)
    audit(user.id, "auth.demo_start")
    db.session.commit()
    return _with_session_cookie(_session_payload(user, sess), token, 201, hours=hours)


@bp.post("/logout")
@login_required
@doc("Sign out of this session", tag="Auth")
def logout():
    user_service.revoke_session(g.session)
    db.session.commit()
    resp, code = ok({"signed_out": True})
    resp = make_response(resp, code)
    resp.delete_cookie(current_app.config["SESSION_COOKIE_NAME"], path="/")
    return resp


@bp.get("/me")
@doc("Current user and CSRF token", tag="Auth")
def me():
    if g.get("user") is None:
        return ok({"user": None, "csrf_token": None})
    return ok(_session_payload(g.user, g.session))

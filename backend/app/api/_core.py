"""Shared API plumbing: response envelope, authentication, CSRF, request validation, OpenAPI metadata."""
from __future__ import annotations

import functools
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TypeVar

from flask import Response, current_app, g, jsonify, request
from pydantic import BaseModel, ValidationError

from app.extensions import db
from app.models import User, UserSession
from app.security.encryption import hash_token
from app.utils.errors import APIError, Forbidden, NotFound, Unauthorized, ValidationFailed

M = TypeVar("M", bound=BaseModel)

# OpenAPI metadata registry: view function qualified name -> metadata
OPENAPI_REGISTRY: dict[str, dict] = {}

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def ok(data: Any = None, status: int = 200, meta: dict | None = None) -> tuple[Response, int]:
    body: dict[str, Any] = {"data": data}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), status


def error_response(err: APIError) -> tuple[Response, int]:
    body: dict[str, Any] = {"error": {"code": err.code, "message": err.message}}
    if err.details is not None:
        body["error"]["details"] = err.details
    return jsonify(body), err.status


def doc(summary: str, *, body: type[BaseModel] | None = None, query: type[BaseModel] | None = None,
        tag: str | None = None, auth: bool = True):
    """Attach OpenAPI metadata to a view function."""

    def decorator(fn: Callable) -> Callable:
        OPENAPI_REGISTRY[f"{fn.__module__}.{fn.__name__}"] = {
            "summary": summary, "body": body, "query": query, "tag": tag, "auth": auth,
        }
        return fn

    return decorator


def parse_body(model: type[M], *, partial_ok: bool = False) -> M:
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValidationFailed("Request body must be a JSON object")
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ValidationFailed("Invalid request body", details=_pydantic_errors(exc)) from exc


def parse_query(model: type[M]) -> M:
    try:
        return model.model_validate(request.args.to_dict())
    except ValidationError as exc:
        raise ValidationFailed("Invalid query parameters", details=_pydantic_errors(exc)) from exc


def _pydantic_errors(exc: ValidationError) -> list[dict]:
    return [
        {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
        for e in exc.errors(include_url=False, include_input=False)
    ]


def parse_uuid(value: str, label: str = "resource") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise NotFound(f"{label.capitalize()} not found") from exc


def load_session() -> None:
    """Resolve the session cookie into g.user / g.session (called before every request)."""
    g.user = None
    g.session = None
    token = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
    if not token:
        return
    sess = db.session.execute(
        db.select(UserSession).where(UserSession.token_hash == hash_token(token))
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not sess or sess.revoked_at is not None or sess.expires_at <= now:
        return
    user = db.session.get(User, sess.user_id)
    if not user:
        return
    if (now - sess.last_seen_at) > timedelta(minutes=5):
        sess.last_seen_at = now
        db.session.commit()
    g.user = user
    g.session = sess


def login_required(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if g.get("user") is None:
            raise Unauthorized("Sign in to continue")
        if request.method not in SAFE_METHODS:
            sent = request.headers.get("X-CSRF-Token", "")
            if not sent or sent != g.session.csrf_token:
                raise Forbidden("Missing or invalid CSRF token", code="csrf_failed")
        return fn(*args, **kwargs)

    return wrapper


def current_user() -> User:
    user = g.get("user")
    if user is None:
        raise Unauthorized("Sign in to continue")
    return user


def get_owned(model, obj_id, label: str | None = None):
    """Fetch a row by id that belongs to the current user, or 404 (never 403, to avoid leaking existence)."""
    label = label or model.__name__.lower()
    oid = parse_uuid(obj_id, label)
    obj = db.session.get(model, oid)
    if obj is None or getattr(obj, "user_id", None) != current_user().id:
        raise NotFound(f"{label.capitalize()} not found")
    return obj


def client_ip() -> str:
    # remote_addr already reflects trusted X-Forwarded-For hops when TRUSTED_PROXIES is set (ProxyFix);
    # the raw header is never trusted directly because clients can forge it.
    return request.remote_addr or ""

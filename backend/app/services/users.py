from __future__ import annotations

import secrets
from datetime import timedelta

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import User, UserAISettings, UserPreference, UserSession
from app.security.encryption import generate_token, hash_token
from app.utils.errors import Conflict, Unauthorized
from app.utils.timeutil import utcnow

# used to equalise timing for unknown emails
_DUMMY_HASH = generate_password_hash("tandem-timing-equaliser")


def normalise_email(email: str) -> str:
    return email.strip().lower()


def create_user(email: str, password: str, display_name: str = "", *, is_demo: bool = False,
                demo_tenant_id=None, ai_mode: str | None = None, locale: str = "ro") -> User:
    email = normalise_email(email)
    if db.session.execute(db.select(User.id).where(User.email == email)).first():
        raise Conflict("An account with this email already exists", code="email_taken")
    user = User(email=email, password_hash=generate_password_hash(password), display_name=display_name.strip(),
                is_demo=is_demo, demo_tenant_id=demo_tenant_id, locale=locale if locale in ("ro", "en") else "ro")
    user.preferences = UserPreference()
    user.ai_settings = UserAISettings()
    if ai_mode:
        user.ai_settings.mode = ai_mode
        user.ai_settings.consent_recorded_at = utcnow()
    db.session.add(user)
    db.session.flush()
    return user


def authenticate(email: str, password: str) -> User:
    user = db.session.execute(db.select(User).where(User.email == normalise_email(email))).scalar_one_or_none()
    if user is None:
        check_password_hash(_DUMMY_HASH, password)
        raise Unauthorized("Incorrect email or password", code="invalid_credentials")
    if not check_password_hash(user.password_hash, password):
        raise Unauthorized("Incorrect email or password", code="invalid_credentials")
    return user


def start_session(user: User, user_agent: str = "", hours: int | None = None) -> tuple[str, UserSession]:
    token = generate_token(32)
    ttl = hours or current_app.config["SESSION_TTL_HOURS"]
    sess = UserSession(user_id=user.id, token_hash=hash_token(token), csrf_token=secrets.token_urlsafe(24),
                       expires_at=utcnow() + timedelta(hours=ttl), user_agent=user_agent[:255])
    user.last_login_at = utcnow()
    db.session.add(sess)
    db.session.flush()
    return token, sess


def revoke_session(sess: UserSession) -> None:
    sess.revoked_at = utcnow()


def change_password(user: User, current: str, new: str) -> None:
    if not check_password_hash(user.password_hash, current):
        raise Unauthorized("Current password is incorrect", code="invalid_credentials")
    user.password_hash = generate_password_hash(new)
    for sess in db.session.execute(db.select(UserSession).where(UserSession.user_id == user.id)).scalars():
        sess.revoked_at = sess.revoked_at or utcnow()

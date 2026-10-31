from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.i18n import T, locale_of, render
from app.models import Notification, UserPreference


def notify(user_id: uuid.UUID, type_: str, title: T | str, body: T | str | None = "", *, link: str | None = None,
           severity: str = "info", dedupe_key: str | None = None) -> Notification | None:
    """Create an in-app notification, honouring preferences and de-duplicating by key.

    Notifications are stored text, so translatable parts are rendered now, in the recipient's language."""
    prefs = db.session.get(UserPreference, user_id)
    if prefs and prefs.notification_prefs.get(type_) is False:
        return None
    if dedupe_key:
        existing = db.session.execute(
            db.select(Notification).where(Notification.user_id == user_id, Notification.dedupe_key == dedupe_key)
        ).scalar_one_or_none()
        if existing:
            return None
    locale = locale_of(user_id)
    title, body = render(title, locale), render(body, locale) or ""
    note = Notification(user_id=user_id, type=type_, title=title[:200], body=body, link=link,
                        severity=severity, dedupe_key=dedupe_key)
    try:
        with db.session.begin_nested():
            db.session.add(note)
    except IntegrityError:
        return None
    return note

from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import CacheEntry
from app.utils.timeutil import utcnow


def cache_key(raw: str | dict | list) -> str:
    if not isinstance(raw, str):
        raw = json.dumps(raw, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_get(namespace: str, raw_key):
    entry = db.session.get(CacheEntry, (namespace, cache_key(raw_key)))
    if entry is None:
        return None
    if entry.expires_at and entry.expires_at < utcnow():
        return None
    return entry.value


def cache_set(namespace: str, raw_key, value, ttl_hours: int | None = 24) -> None:
    key = cache_key(raw_key)
    expires = utcnow() + timedelta(hours=ttl_hours) if ttl_hours else None
    try:
        with db.session.begin_nested():
            entry = db.session.get(CacheEntry, (namespace, key))
            if entry is None:
                db.session.add(CacheEntry(namespace=namespace, key=key, value=value, expires_at=expires))
            else:
                entry.value = value
                entry.expires_at = expires
    except SQLAlchemyError:
        pass

"""Limite care tin pe toate instantele, nu doar pe una.

Pe Vercel fiecare cerere poate ajunge pe alt proces, deci limiter-ul din memorie e usor de ocolit (o instanta noua =
contor de la zero). Pentru lucrurile care conteaza (login, cont nou, demo, chat) tinem contorul in baza de date.
Fereastra se prelungeste la fiecare incercare, deci cine insista asteapta mai mult, nu mai putin.
"""
from __future__ import annotations

import hashlib
from datetime import timedelta

from sqlalchemy import insert

from app.extensions import db
from app.models import CacheEntry
from app.utils.errors import APIError
from app.utils.timeutil import utcnow


class TooManyRequests(APIError):
    status = 429
    code = "rate_limited"


def _key(bucket: str, who: str) -> str:
    return hashlib.sha256(f"{bucket}:{who}".encode()).hexdigest()


def _count(bucket: str, who: str) -> int:
    row = db.session.get(CacheEntry, ("throttle", _key(bucket, who)))
    if row is None or (row.expires_at and row.expires_at < utcnow()):
        return 0
    return int((row.value or {}).get("n", 0))


def hit(bucket: str, who: str, *, window_minutes: float) -> int:
    """count one attempt and return the new total"""
    if not who or not enabled():
        return 0
    n = _count(bucket, who) + 1
    table = CacheEntry.__table__
    with db.engine.begin() as conn:
        conn.execute(table.delete().where(table.c.namespace == "throttle", table.c.key == _key(bucket, who)))
        conn.execute(insert(table).values(namespace="throttle", key=_key(bucket, who), value={"n": n},
                                          expires_at=utcnow() + timedelta(minutes=window_minutes), created_at=utcnow()))
    db.session.expire_all()
    return n


def enabled() -> bool:
    from flask import current_app

    return bool(current_app.config.get("THROTTLE_ENABLED", True))


def guard(bucket: str, who: str, *, limit: int, window_minutes: float, count: bool = True) -> None:
    """refuse when `who` already used up `limit` attempts in the window; otherwise (optionally) count this one"""
    if not who or not enabled():
        return
    if _count(bucket, who) >= limit:
        raise TooManyRequests("Too many attempts. Wait a few minutes and try again.")
    if count:
        hit(bucket, who, window_minutes=window_minutes)


def clear(bucket: str, who: str) -> None:
    if not enabled():
        return
    table = CacheEntry.__table__
    with db.engine.begin() as conn:
        conn.execute(table.delete().where(table.c.namespace == "throttle", table.c.key == _key(bucket, who)))

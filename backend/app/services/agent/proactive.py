"""tandem scrie primul: se uita la calatoriile urmatoare si zice cand ceva cere o decizie (ploaie, greva, suprapunere)"""
from __future__ import annotations

import logging
from datetime import timedelta

from app.extensions import db
from app.i18n import locale_of, render, tr
from app.models import ItineraryEvent, Trip, User
from app.services.agent import feed
from app.services.cache import cache_get, cache_set
from app.utils.timeutil import iso_local, local_date

log = logging.getLogger("tandem.proactive")

LOOKAHEAD_DAYS = 16  # cat de departe ajunge prognoza
MAX_PER_RUN = 3
OUTDOOR = ("outdoor", "park", "garden", "walk", "tour", "day trip", "viewpoint", "beach", "hike", "bike", "boat",
           "picnic", "sunset", "plimbare", "parc", "grădin", "gradin", "aer liber", "pe jos", "apus", "tur ")
OUTDOOR_TYPES = ("tour", "activity", "free_time", "outdoor", "custom")


def _trips(user: User) -> list[Trip]:
    from app.services.agent.tools import today_for

    today = today_for(user)
    rows = db.session.execute(db.select(Trip).where(Trip.user_id == user.id, Trip.is_cancelled.is_(False))).scalars()
    return [t for t in rows if t.start_date and t.start_date <= today + timedelta(days=LOOKAHEAD_DAYS)
            and (t.end_date or t.start_date) >= today]


def _is_outdoor(e: ItineraryEvent) -> bool:
    text = f" {e.title} {e.location_name or ''} ".lower()
    return e.type in OUTDOOR_TYPES and any(w in text for w in OUTDOOR)


def _weather(user: User, trip: Trip, loc: str) -> list[tuple[str, str, list[str]]]:
    from app.services.context import weather

    try:
        data = weather.for_trip(trip)
    except Exception:  # noqa: BLE001 - a check that can't run just doesn't post
        log.warning("proactive: weather failed", exc_info=True)
        return []
    if not data.get("available"):
        return []
    wet = {d["date"]: d for d in data["days"] if not d["outdoor_ok"]}
    out = []
    events = db.session.execute(db.select(ItineraryEvent).where(
        ItineraryEvent.trip_id == trip.id, ItineraryEvent.status.notin_(["cancelled", "completed"]))).scalars()
    for e in events:
        day = local_date(e.start_at, e.start_tz).isoformat()
        if day not in wet or not _is_outdoor(e):
            continue
        w = wet[day]
        from app.i18n import long_date

        hours = ", ".join(w.get("wet_hours") or [])[:40]
        text = tr("I know you planned {title} on {day} at {time}, but the forecast has rain that day ({p}% chance{hours}). "
                  "Would you like to move it, or swap it for something indoors?", loc, title=e.title,
                  day=long_date(local_date(e.start_at, e.start_tz), loc), time=iso_local(e.start_at, e.start_tz)[11:16],
                  p=w.get("precip_probability") or 0,
                  hours=(", " + tr("wettest around {hours}", loc, hours=hours)) if hours else "")
        out.append((f"weather:{e.id}:{day}", text, [tr("Move it to a drier time", loc), tr("Find something indoors", loc),
                                                     tr("Keep it as it is", loc)]))
    return out


def _news(user: User, trip: Trip, loc: str) -> list[tuple[str, str, list[str]]]:
    from app.services.context import news

    try:
        data = news.for_trip(trip)
    except Exception:  # noqa: BLE001
        log.warning("proactive: news failed", exc_info=True)
        return []
    out = []
    for item in data.get("items", []):
        if item["kind"] not in ("strike", "protest") or not item["mentions_dates"]:
            continue
        what = tr("a strike", loc) if item["kind"] == "strike" else tr("a protest or march", loc)
        text = tr("Heads up: {source} reports {what} on {dates}, during your trip: “{headline}”. Buses, metro or trains "
                  "may not run normally. Do you want me to plan around it?", loc, source=item["source"] or "the news",
                  what=what, dates=", ".join(item["mentions_dates"]), headline=item["title"][:160])
        out.append((f"news:{item['url'][-120:]}", text, [tr("Plan around it", loc), tr("What exactly is affected?", loc),
                                                         tr("It's fine, thanks", loc)]))
    return out


def _clashes(user: User, trip: Trip, loc: str) -> list[tuple[str, str, list[str]]]:
    from app.services.itinerary import conflicts

    out = []
    for c in conflicts.detect(trip):
        if c.severity == "info":
            continue
        text = tr("{title}. {detail} Shall I sort it out?", loc, title=render(c.title, loc), detail=render(c.detail, loc))
        out.append((f"clash:{trip.id}:{c.key}", text, [tr("Yes, move one of them", loc), tr("Show me both", loc),
                                                       tr("Leave it", loc)]))
    return out


def check_user(user: User, *, force: bool = False) -> int:
    """post what's new for this user"""
    throttle = {"u": str(user.id)}
    if not force and cache_get("proactive_run", throttle):
        return 0
    cache_set("proactive_run", throttle, True, ttl_hours=3)
    loc = locale_of(user)
    posted = 0
    for trip in _trips(user):
        for check in (_weather, _news, _clashes):
            for key, text, options in check(user, trip, loc):
                if posted >= MAX_PER_RUN:
                    break
                if feed.post(user, key, text, trip=trip, options=options) is not None:
                    posted += 1
    db.session.commit()
    return posted


def run_all(limit: int = 200) -> int:
    """daily: everyone with a trip coming up soon"""
    users = db.session.execute(db.select(User).join(Trip, Trip.user_id == User.id).distinct().limit(limit)).scalars().all()
    total = 0
    for u in users:
        try:
            total += check_user(u, force=True)
        except Exception:  # noqa: BLE001 - one user's failure must not stop the rest
            db.session.rollback()
            log.exception("proactive check failed for a user")
    return total

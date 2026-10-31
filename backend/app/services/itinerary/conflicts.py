"""Deterministic itinerary conflict detection.

All rules here are plain code over stored data. AI may later *explain* a conflict, but never decides
whether one exists. Travel-time checks use a physical lower bound (straight-line distance at a
generous maximum speed) to flag impossible sequences; routed durations are used only when a routing
provider is configured, and otherwise the result says travel time is unknown.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from flask import current_app

from app.extensions import db
from app.i18n import T, When, render
from app.models import ItineraryEvent, Reservation, ReservationChange, Trip, User
from app.services import geo
from app.services.notifications.service import notify
from app.utils.timeutil import local_date, to_local, utcnow

TRANSPORT_EVENTS = {"flight", "train", "bus", "ferry", "transfer"}
NON_BLOCKING = {"free_time", "travel_time", "reminder", "hotel_checkin", "hotel_checkout", "car_rental"}
LONG_HAUL_KMH = 900.0  # faster than any surface mode; anything needing more is physically impossible
SURFACE_KMH = 110.0


@dataclass
class ConflictItem:
    type: str
    severity: str  # critical | warning | info
    title: T | str  # rendered in the reader's language (see as_dicts / notify)
    detail: T | str
    event_ids: list[str] = field(default_factory=list)
    reservation_ids: list[str] = field(default_factory=list)
    key: str = ""

    def finalise(self) -> "ConflictItem":
        ids = sorted(self.event_ids + self.reservation_ids)
        self.key = f"{self.type}:{'|'.join(ids)}"
        return self


def _fmt(dt: datetime, tz: str) -> When:
    return When(to_local(dt, tz))


def _end(e: ItineraryEvent) -> datetime:
    return e.end_at or e.start_at


def _loc_start(e: ItineraryEvent):
    return (e.lat, e.lon, e.city)


def _loc_end(e: ItineraryEvent):
    if e.type in TRANSPORT_EVENTS:
        return (e.end_lat, e.end_lon, e.end_city or e.end_location_name)
    return (e.lat, e.lon, e.city)


def _same_city(a: str | None, b: str | None) -> bool:
    return bool(a and b and a.strip().lower() == b.strip().lower())


def detect(trip: Trip, *, now: datetime | None = None) -> list[ConflictItem]:
    now = now or utcnow()
    cfg = current_app.config
    events = db.session.execute(db.select(ItineraryEvent).where(
        ItineraryEvent.trip_id == trip.id, ItineraryEvent.status.notin_(["cancelled"])
    ).order_by(ItineraryEvent.start_at)).scalars().all()
    reservations = db.session.execute(db.select(Reservation).where(
        Reservation.trip_id == trip.id, Reservation.status != "cancelled")).scalars().all()
    out: list[ConflictItem] = []

    # 1. Overlapping events (intervals only; check-in/out and free time do not block)
    timed = [e for e in events if e.end_at and e.type not in NON_BLOCKING]
    for i, a in enumerate(timed):
        for b in timed[i + 1:]:
            if b.start_at >= a.end_at:
                break
            overlap = min(a.end_at, b.end_at) - b.start_at
            if overlap <= timedelta(0):
                continue
            minutes = int(overlap.total_seconds() // 60)
            suggestion = "suggested" in (a.status, b.status)
            out.append(ConflictItem(
                "overlap", "warning" if suggestion else "critical",
                T("{a} overlaps {b}", a=a.title, b=b.title),
                T("They overlap by {minutes} min ({start} – {end}). One of them is only a suggestion." if suggestion
                  else "They overlap by {minutes} min ({start} – {end}).", minutes=minutes,
                  start=_fmt(b.start_at, b.start_tz), end=_fmt(min(a.end_at, b.end_at), a.end_tz or a.start_tz)),
                [str(a.id), str(b.id)]))

    # 2/3. Sequence checks between consecutive located events
    blocking = [e for e in events if e.type not in ("reminder", "free_time", "travel_time")]
    blocking.sort(key=lambda e: e.start_at)
    for a, b in zip(blocking, blocking[1:]):
        gap_min = (b.start_at - _end(a)).total_seconds() / 60
        if gap_min < 0:
            continue  # overlaps handled above
        lat1, lon1, city1 = _loc_end(a)
        lat2, lon2, city2 = _loc_start(b)
        if a.type in TRANSPORT_EVENTS and a.end_at and b.type not in TRANSPORT_EVENTS \
                and b.type not in ("hotel_checkout",) and gap_min < cfg["AIRPORT_EXIT_BUFFER_MINUTES"] \
                and (city2 is None or _same_city(city1, city2)):
            out.append(ConflictItem(
                "tight_after_arrival", "warning", T("Little time after {a}", a=a.title),
                T("{b} starts {gap} min after you arrive. Allow at least {buffer} min to leave the station or airport.",
                  b=b.title, gap=int(gap_min), buffer=cfg["AIRPORT_EXIT_BUFFER_MINUTES"]),
                [str(a.id), str(b.id)]))
            continue
        if None in (lat1, lon1, lat2, lon2):
            continue
        km = geo.haversine_km(lat1, lon1, lat2, lon2)
        if km < 1:
            continue
        lower_bound = km / (LONG_HAUL_KMH if km > 150 else SURFACE_KMH) * 60
        transported = b.type in TRANSPORT_EVENTS and _same_city(city1, b.city)
        if not transported and gap_min < lower_bound:
            out.append(ConflictItem(
                "impossible_sequence", "critical", T("Can't get from {a} to {b} in time", a=a.title, b=b.title),
                T("The places are {km} km apart but only {gap} min separate them.", km=round(km), gap=int(gap_min)),
                [str(a.id), str(b.id)]))
            continue
        routed = geo.travel_time_minutes(lat1, lon1, lat2, lon2)
        if routed is not None and gap_min < routed + 10:
            out.append(ConflictItem(
                "insufficient_transfer", "warning", T("Tight transfer to {b}", b=b.title),
                T("Travel time is about {routed} min; you have {gap} min.", routed=int(routed), gap=int(gap_min)),
                [str(a.id), str(b.id)]))
        elif routed is None and km >= 2 and gap_min < cfg["MIN_TRANSFER_BUFFER_MINUTES"] and not transported:
            out.append(ConflictItem(
                "possible_tight_transfer", "info", T("Check travel time to {b}", b=b.title),
                T("{b} is {km} km away and starts {gap} min later. Travel time is unknown (no routing provider configured).",
                  b=b.title, km=round(km, 1), gap=int(gap_min)), [str(a.id), str(b.id)]))

    # 4. Activities after leaving a city / missing travel segments
    transports = [e for e in events if e.type in TRANSPORT_EVENTS and e.end_city and e.city
                  and not _same_city(e.city, e.end_city)]
    for t in transports:
        later_arrival_back = min((x.start_at for x in transports if x.start_at > t.start_at and _same_city(x.end_city, t.city)),
                                 default=None)
        for e in events:
            if e.type in TRANSPORT_EVENTS or e.type in ("hotel_checkout", "reminder") or not _same_city(e.city, t.city):
                continue
            if e.start_at >= t.start_at and (later_arrival_back is None or e.start_at < later_arrival_back):
                out.append(ConflictItem(
                    "after_departure", "critical", T("{e} is after you leave {city}", e=e.title, city=t.city),
                    T("{t} departs {when}, before {e} at {at}.", t=t.title, when=_fmt(t.start_at, t.start_tz),
                      e=e.title, at=_fmt(e.start_at, e.start_tz)),
                    [str(t.id), str(e.id)]))
    located = [e for e in events if e.city and e.type not in TRANSPORT_EVENTS and e.type != "reminder"]
    for a, b in zip(located, located[1:]):
        if _same_city(a.city, b.city):
            continue
        between = [t for t in transports if _end(a) <= t.start_at <= b.start_at]
        if not between:
            out.append(ConflictItem(
                "missing_transport", "warning", T("No transport from {a} to {b}", a=a.city, b=b.city),
                T("You're in {a_city} for {a} and in {b_city} for {b}, but no journey between them is in the itinerary.",
                  a_city=a.city, a=a.title, b_city=b.city, b=b.title), [str(a.id), str(b.id)]))

    # 5. Hotel coverage, check-out after departure, missing check-in details
    hotels = [r for r in reservations if r.type == "hotel" and r.start_at and r.end_at]
    if trip.start_date and trip.end_date and (trip.end_date - trip.start_date).days >= 1:
        night = trip.start_date
        uncovered = []
        while night < trip.end_date:
            covered = any(local_date(h.start_at, h.start_tz) <= night < local_date(h.end_at, h.end_tz or h.start_tz)
                          for h in hotels)
            overnight = any(e.type in TRANSPORT_EVENTS and e.end_at and local_date(e.start_at, e.start_tz) <= night
                            < local_date(e.end_at, e.end_tz or e.start_tz) for e in events)
            if not covered and not overnight:
                uncovered.append(night)
            night += timedelta(days=1)
        if uncovered:
            out.append(ConflictItem(
                "missing_accommodation", "info",
                T("No accommodation for 1 night") if len(uncovered) == 1 else T("No accommodation for {n} nights", n=len(uncovered)),
                T("Nights without a stay: {nights}.", nights=[When(n, with_time=False) for n in uncovered[:7]]),
                [], []))
    for h in hotels:
        departures = [t for t in transports if _same_city(t.city, h.city)
                      and local_date(t.start_at, t.start_tz) == local_date(h.end_at, h.end_tz or h.start_tz)]
        for t in departures:
            if h.end_at > t.start_at:
                out.append(ConflictItem(
                    "checkout_after_departure", "critical", T("Check-out at {h} is after {t} departs", h=h.title, t=t.title),
                    T("Check-out {out}, departure {dep}.", out=_fmt(h.end_at, h.end_tz or h.start_tz), dep=_fmt(t.start_at, t.start_tz)),
                    [str(t.id)], [str(h.id)]))
        if not (h.details or {}).get("check_in_from") or not h.address:
            no_time, no_address = not (h.details or {}).get("check_in_from"), not h.address
            title = (T("Missing check-in time and address for {h}", h=h.title) if no_time and no_address
                     else T("Missing check-in time for {h}", h=h.title) if no_time else T("Missing address for {h}", h=h.title))
            out.append(ConflictItem("missing_checkin_info", "info", title,
                                    T("Add it from the confirmation so arrival planning is accurate."), [], [str(h.id)]))

    # 6. Reservation status and deadlines
    for r in reservations:
        if r.status in ("pending", "unknown"):
            out.append(ConflictItem(
                "unconfirmed", "info", T("{r} is not confirmed", r=r.title),
                T("The source document does not show this booking as confirmed.") if r.status == "unknown"
                else T("This booking is pending with the provider."), [], [str(r.id)]))
        if r.cancellation_deadline and now < r.cancellation_deadline <= now + timedelta(hours=72):
            hours = int((r.cancellation_deadline - now).total_seconds() // 3600)
            out.append(ConflictItem(
                "cancellation_deadline", "warning", T("Free cancellation for {r} ends soon", r=r.title),
                T("Deadline in about {hours} h ({when}).", hours=hours, when=_fmt(r.cancellation_deadline, r.start_tz or "UTC")),
                [], [str(r.id)]))
    pending_changes = db.session.execute(db.select(ReservationChange).where(
        ReservationChange.status == "pending",
        ReservationChange.reservation_id.in_([r.id for r in reservations] or [None]))).scalars().all()
    for c in pending_changes:
        out.append(ConflictItem("pending_change", "warning", T("Booking update waiting for review"), c.summary,
                                [], [str(c.reservation_id)]))

    # 7. Verified opening hours (only when a provider supplied verified hours)
    for e in events:
        hours = (e.details or {}).get("opening_hours")
        if not (isinstance(hours, dict) and hours.get("verified")):
            continue
        local = to_local(e.start_at, e.start_tz)
        if hours.get("open") and local.strftime("%H:%M") < hours["open"] or \
                hours.get("close") and local.strftime("%H:%M") >= hours["close"]:
            out.append(ConflictItem("outside_opening_hours", "warning", T("{e} is outside opening hours", e=e.title),
                                    T("Verified hours: {open}–{close}.", open=hours.get("open"), close=hours.get("close")), [str(e.id)]))

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    items = [c.finalise() for c in out]
    unique = {c.key: c for c in items}
    return sorted(unique.values(), key=lambda c: (severity_rank[c.severity], c.type))


def as_dicts(items: list[ConflictItem], locale: str | None = None) -> list[dict]:
    """Plain dicts with title and detail rendered in the reader's language."""
    out = []
    for c in items:
        d = asdict(c)
        d["title"], d["detail"] = render(c.title, locale), render(c.detail, locale)
        out.append(d)
    return out


def check_and_notify(trip: Trip, user: User) -> list[ConflictItem]:
    items = detect(trip)
    known = set(trip.known_conflicts or [])
    for c in items:
        if c.severity in ("critical", "warning") and c.key not in known:
            notify(user.id, "conflict_detected", c.title, c.detail, link=f"/trips/{trip.id}",
                   severity="critical" if c.severity == "critical" else "warning",
                   dedupe_key=f"conflict:{trip.id}:{c.key}")
    trip.known_conflicts = [c.key for c in items]
    return items

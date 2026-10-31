"""iCalendar (RFC 5545) export of itinerary events, for "Add to Calendar" and the private subscription feed.

Times are written in UTC (``…Z``), so no VTIMEZONE blocks are needed and calendar apps show them in the
viewer's own time zone; the description repeats the local time at the destination. Calendar feeds are fetched
by third-party servers (iCloud, Google), so events carry only what, when, where and a link back to Tandem:
no booking references, traveller names, prices or notes.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from app.models import ItineraryEvent
from app.models.trip import RESERVATION_TYPES
from app.utils.timeutil import local_date, to_local

PRODID = "-//Tandem//Travel itinerary//EN"
EXPORTED_STATUSES = ("confirmed", "pending", "unbooked", "completed")  # suggestions stay in Tandem

TYPE_LABELS = {
    "flight": "Flight", "train": "Train", "bus": "Bus", "ferry": "Ferry", "car_rental": "Car hire",
    "transfer": "Transfer", "hotel": "Stay", "hotel_checkin": "Hotel check-in", "hotel_checkout": "Hotel check-out",
    "museum": "Museum", "tour": "Tour", "activity": "Activity", "restaurant": "Restaurant", "event": "Event",
    "meeting": "Meeting", "free_time": "Free time", "travel_time": "Travel time", "reminder": "Reminder",
}


def escape(text: str) -> str:
    """Escape a TEXT value: backslash, semicolon, comma and line breaks."""
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n"))


def fold(line: str) -> str:
    """Fold a content line at 75 octets without splitting a UTF-8 character."""
    if len(line.encode()) <= 75:
        return line
    parts: list[str] = []
    chunk, size, limit = [], 0, 75
    for ch in line:
        n = len(ch.encode())
        if size + n > limit:
            parts.append("".join(chunk))
            chunk, size, limit = [], 0, 74  # continuation lines begin with a space
        chunk.append(ch)
        size += n
    parts.append("".join(chunk))
    return "\r\n ".join(parts)


def _utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _local_label(dt: datetime, tz: str | None) -> str:
    local = to_local(dt, tz)
    return f"{local:%a %d %b, %H:%M} ({tz or 'UTC'})" if local else ""


def _location(e: ItineraryEvent) -> str:
    if e.end_location_name or e.end_city:
        start = e.location_name or e.city or ""
        end = e.end_location_name or e.end_city or ""
        return f"{start} → {end}".strip(" →")
    place, where = e.location_name, e.address or e.city
    if place and where and where.lower().startswith(place.lower()):
        place = None  # the address already starts with the venue name
    return ", ".join(p for p in (place, where) if p)


def _description(e: ItineraryEvent, link: str) -> str:
    lines = [TYPE_LABELS.get(e.type, e.type.replace("_", " ").capitalize())]
    if e.status == "pending":
        lines[0] += " · not confirmed yet"
    elif e.status == "unbooked" and e.type in RESERVATION_TYPES:
        lines[0] += " · not booked yet"
    if not e.all_day:
        lines.append(f"Local time: {_local_label(e.start_at, e.start_tz)}")
        if e.end_at and (e.end_tz or e.start_tz) != e.start_tz:
            lines.append(f"Arrives: {_local_label(e.end_at, e.end_tz)}")
    lines.append(f"Open in Tandem: {link}")
    return "\n".join(lines)


def _vevent(e: ItineraryEvent, app_url: str) -> list[str]:
    link = f"{app_url}/trips/{e.trip_id}"
    stamp = _utc(e.updated_at or e.created_at)
    out = ["BEGIN:VEVENT", f"UID:{e.id}@tandem", f"DTSTAMP:{stamp}", f"LAST-MODIFIED:{stamp}"]
    if e.all_day:
        start = local_date(e.start_at, e.start_tz)
        last = local_date(e.end_at, e.end_tz or e.start_tz) if e.end_at else start
        out += [f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
                f"DTEND;VALUE=DATE:{max(last, start) + timedelta(days=1):%Y%m%d}"]  # DTEND is exclusive
    else:
        out.append(f"DTSTART:{_utc(e.start_at)}")
        if e.end_at and e.end_at > e.start_at:
            out.append(f"DTEND:{_utc(e.end_at)}")
    summary = e.title + (" (unconfirmed)" if e.status == "pending" else "")
    out.append(f"SUMMARY:{escape(summary)}")
    if loc := _location(e):
        out.append(f"LOCATION:{escape(loc)}")
    if e.lat is not None and e.lon is not None and not (e.end_location_name or e.end_city):
        out.append(f"GEO:{e.lat:.6f};{e.lon:.6f}")
    out += [f"DESCRIPTION:{escape(_description(e, link))}", f"URL:{link}",
            f"STATUS:{'TENTATIVE' if e.status == 'pending' else 'CONFIRMED'}", "END:VEVENT"]
    return out


def build_calendar(events: Iterable[ItineraryEvent], *, name: str, app_url: str) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{escape(name)}", "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H"]
    for e in events:
        lines += _vevent(e, app_url.rstrip("/"))
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"

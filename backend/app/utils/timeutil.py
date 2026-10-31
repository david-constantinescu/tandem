"""helperi pt timp. in baza totul e utc, fiecare eveniment isi tine fusul orar"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def zone(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def is_valid_tz(tz_name: str | None) -> bool:
    if not tz_name:
        return False
    try:
        ZoneInfo(tz_name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def localize(naive: datetime, tz_name: str) -> tuple[datetime, list[str]]:
    """attach a zone to a naive local wall-clock time, flagging DST gaps and folds"""
    notes: list[str] = []
    tz = zone(tz_name)
    first = naive.replace(tzinfo=tz, fold=0)
    second = naive.replace(tzinfo=tz, fold=1)
    if first.utcoffset() != second.utcoffset():
        # either a fold (ambiguous) or a gap (non-existent). Round-trip tells which.
        roundtrip = first.astimezone(UTC).astimezone(tz).replace(tzinfo=None)
        if roundtrip != naive:
            notes.append(f"{naive:%Y-%m-%d %H:%M} does not exist in {tz_name} (DST change); shifted forward")
            return second.astimezone(UTC), notes
        notes.append(f"{naive:%Y-%m-%d %H:%M} occurs twice in {tz_name} (DST change); assumed first occurrence")
    return first.astimezone(UTC), notes


def to_local(dt: datetime | None, tz_name: str | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(zone(tz_name))


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def iso_local(dt: datetime | None, tz_name: str | None) -> str | None:
    local = to_local(dt, tz_name)
    return local.isoformat() if local else None


def local_date(dt: datetime, tz_name: str | None) -> date:
    return to_local(dt, tz_name).date()  # type: ignore[union-attr]


def combine_local(d: date, t: time | None, tz_name: str) -> tuple[datetime, list[str]]:
    return localize(datetime.combine(d, t or time(0, 0)), tz_name)


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt


def minutes_between(a: datetime, b: datetime) -> float:
    return (b - a) / timedelta(minutes=1)

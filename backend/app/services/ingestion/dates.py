"""recunoaste date si ore in documentele de calatorie"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    # Italian / Romanian / French / Spanish short forms commonly seen on tickets
    "gen": 1, "ian": 1, "gennaio": 1, "ianuarie": 1, "febbraio": 2, "februarie": 2, "marzo": 3, "martie": 3,
    "aprile": 4, "aprilie": 4, "mag": 5, "maggio": 5, "mai": 5, "giu": 6, "giugno": 6, "iunie": 6, "lug": 7,
    "luglio": 7, "iulie": 7, "ago": 8, "agosto": 8, "set": 9, "settembre": 9, "septembrie": 9, "ott": 10,
    "ottobre": 10, "octombrie": 10, "noiembrie": 11, "novembre": 11, "dic": 12, "dicembre": 12,
    "decembrie": 12,
}
_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))
_WEEKDAY = r"(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*\.?,?\s+"

RE_ISO = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
RE_DMY_TEXT = re.compile(rf"\b(?:{_WEEKDAY})?(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_ALT})\.?,?\s+(20\d{{2}})\b", re.I)
RE_MDY_TEXT = re.compile(rf"\b(?:{_WEEKDAY})?({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d{{2}})\b", re.I)
RE_NUMERIC = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](20\d{2})\b")
RE_TIME_24 = re.compile(r"\b([01]?\d|2[0-3])[:h]([0-5]\d)\b(?!\s*(?:am|pm|a\.m\.|p\.m\.))", re.I)
RE_TIME_12 = re.compile(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(am|pm|a\.m\.|p\.m\.)", re.I)


@dataclass
class DateHit:
    value: date
    start: int
    end: int
    text: str
    ambiguous: str | None = None


@dataclass
class TimeHit:
    value: time
    start: int
    end: int
    text: str


def find_dates(text: str) -> list[DateHit]:
    hits: list[DateHit] = []
    taken: list[tuple[int, int]] = []

    def add(d: date | None, m: re.Match, ambiguous: str | None = None):
        if d is None:
            return
        if any(not (m.end() <= a or m.start() >= b) for a, b in taken):
            return
        taken.append((m.start(), m.end()))
        hits.append(DateHit(d, m.start(), m.end(), m.group(0), ambiguous))

    for m in RE_ISO.finditer(text):
        add(_safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3))), m)
    for m in RE_DMY_TEXT.finditer(text):
        add(_safe_date(int(m.group(3)), MONTHS[m.group(2).lower().rstrip(".")], int(m.group(1))), m)
    for m in RE_MDY_TEXT.finditer(text):
        add(_safe_date(int(m.group(3)), MONTHS[m.group(1).lower().rstrip(".")], int(m.group(2))), m)
    for m in RE_NUMERIC.finditer(text):
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12 and b <= 12:
            add(_safe_date(y, b, a), m)
        elif b > 12 and a <= 12:
            add(_safe_date(y, a, b), m)
        elif a == b:
            add(_safe_date(y, b, a), m)
        else:
            # day-first (European) reading by default, flagged as ambiguous
            add(_safe_date(y, b, a), m,
                ambiguous=f"'{m.group(0)}' could be {a} {_month_name(b)} or {b} {_month_name(a)}; read as day/month")
    hits.sort(key=lambda h: h.start)
    return hits


def find_times(text: str) -> list[TimeHit]:
    hits: list[TimeHit] = []
    for m in RE_TIME_12.finditer(text):
        hour = int(m.group(1)) % 12
        if m.group(3).lower().startswith("p"):
            hour += 12
        hits.append(TimeHit(time(hour, int(m.group(2) or 0)), m.start(), m.end(), m.group(0)))
    for m in RE_TIME_24.finditer(text):
        if any(h.start <= m.start() < h.end for h in hits):
            continue
        # avoid matching parts of dates like 2026-11-12 or ratios
        before = text[max(0, m.start() - 1):m.start()]
        if before in ("-", "/", "."):
            continue
        hits.append(TimeHit(time(int(m.group(1)), int(m.group(2))), m.start(), m.end(), m.group(0)))
    hits.sort(key=lambda h: h.start)
    return hits


def first_datetime(text: str) -> tuple[datetime | None, str | None, str | None]:
    """first date in text combined with the nearest following time on the same line"""
    dates = find_dates(text)
    if not dates:
        return None, None, None
    d = dates[0]
    line_end = text.find("\n", d.end)
    line_end = len(text) if line_end == -1 else line_end
    line_start = text.rfind("\n", 0, d.start) + 1
    times = [t for t in find_times(text[line_start:line_end])]
    chosen = None
    for t in times:
        if line_start + t.start >= d.end:
            chosen = t
            break
    if chosen is None and times:
        chosen = times[0]
    if chosen is None:
        return datetime.combine(d.value, time(0, 0)), d.ambiguous, None
    return datetime.combine(d.value, chosen.value), d.ambiguous, chosen.text


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _month_name(m: int) -> str:
    return ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
            "November", "December"][m - 1] if 1 <= m <= 12 else str(m)


def date_variants(d: date) -> list[str]:
    """textual forms a date may take in a source document (used to verify AI-extracted dates)"""
    months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
              "november", "december"]
    full = months[d.month - 1]
    return [
        d.isoformat(), f"{d.day} {full}", f"{d.day} {full[:3]}", f"{full} {d.day}", f"{full[:3]} {d.day}",
        f"{d.day:02d}/{d.month:02d}/{d.year}", f"{d.day}/{d.month}/{d.year}", f"{d.month:02d}/{d.day:02d}/{d.year}",
        f"{d.day:02d}.{d.month:02d}.{d.year}", f"{d.day}.{d.month}.{d.year}",
    ]


def time_variants(t: time) -> list[str]:
    h12 = t.hour % 12 or 12
    suffix = "pm" if t.hour >= 12 else "am"
    return [f"{t.hour:02d}:{t.minute:02d}", f"{t.hour}:{t.minute:02d}", f"{t.hour:02d}h{t.minute:02d}",
            f"{h12}:{t.minute:02d} {suffix}", f"{h12}:{t.minute:02d}{suffix}",
            *( [f"{h12} {suffix}", f"{h12}{suffix}"] if t.minute == 0 else [] )]

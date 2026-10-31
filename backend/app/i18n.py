"""Server-side localisation of text users see: errors, itinerary checks, notifications, the offline assistant
and the demo trip. Romanian is the default; English is the alternative.

English templates are the keys (``T("Processed {name}", name=...)``) and ``locale_ro.RO`` maps them to Romanian.
A ``T`` is lazy: an API response renders it in the request's language (the ``X-Tandem-Locale`` header the app
sends, else the signed-in user's), and a stored notification renders it in the recipient's language.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from flask import g, has_request_context, request

LOCALES = ("ro", "en")
DEFAULT_LOCALE = "ro"

_RO_DAYS = ("lun.", "mar.", "mie.", "joi", "vin.", "sâm.", "dum.")
_RO_MONTHS = ("ian.", "feb.", "mar.", "apr.", "mai", "iun.", "iul.", "aug.", "sept.", "oct.", "nov.", "dec.")


def normalise(locale: str | None) -> str | None:
    return locale if locale in LOCALES else None


def request_locale() -> str:
    """The language of the current request: the app's header, then the signed-in user's, then Romanian."""
    if has_request_context():
        header = normalise(request.headers.get("X-Tandem-Locale"))
        if header:
            return header
        user = g.get("user")
        if user is not None and normalise(user.locale):
            return user.locale
    return DEFAULT_LOCALE


def locale_of(who: Any) -> str:
    """Language for stored text addressed to someone: a User, a user id, or a locale string."""
    if isinstance(who, str) and normalise(who):
        return who
    locale = getattr(who, "locale", None)
    if normalise(locale):
        return locale
    if who is not None and not isinstance(who, str):
        from app.extensions import db
        from app.models import User
        user = db.session.get(User, who)
        if user is not None and normalise(user.locale):
            return user.locale
    return request_locale()


class T:
    """A translatable template with its values, rendered when the language is known."""

    __slots__ = ("text", "kw")

    def __init__(self, text: str, **kw: Any):
        self.text = text
        self.kw = kw

    def render(self, locale: str | None = None) -> str:
        loc = normalise(locale) or request_locale()
        from app.locale_ro import RO
        template = RO.get(self.text, self.text) if loc == "ro" else self.text
        values = {k: (", ".join(x) if isinstance(x := render(v, loc), list) else x) for k, v in self.kw.items()}
        return template.format(**values) if values else template

    def __str__(self) -> str:
        return self.render()

    def __repr__(self) -> str:
        return f"T({self.text!r})"


class When:
    """A local date-time shown as e.g. "Sat 14 Nov 17:30" / "sâm. 14 nov. 17:30"."""

    __slots__ = ("value", "with_time")

    def __init__(self, value: datetime | date, with_time: bool = True):
        self.value = value
        self.with_time = with_time

    def render(self, locale: str | None = None) -> str:
        loc = normalise(locale) or request_locale()
        v = self.value
        if loc == "ro":
            text = f"{_RO_DAYS[v.weekday()]} {v.day} {_RO_MONTHS[v.month - 1]}"
        else:
            text = v.strftime("%a %d %b").replace(" 0", " ")
        if self.with_time and isinstance(v, datetime):
            text += f" {v:%H:%M}"
        return text


_RO_LONG_DAYS = ("luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică")
_RO_LONG_MONTHS = ("ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august", "septembrie",
                   "octombrie", "noiembrie", "decembrie")


def long_date(d: date, locale: str | None = None) -> str:
    """e.g. "Saturday 14 November" / "sâmbătă, 14 noiembrie"."""
    loc = normalise(locale) or request_locale()
    if loc == "ro":
        return f"{_RO_LONG_DAYS[d.weekday()]}, {d.day} {_RO_LONG_MONTHS[d.month - 1]}"
    return f"{d:%A} {d.day} {d:%B}"


def weekday_name(d: date, locale: str | None = None) -> str:
    loc = normalise(locale) or request_locale()
    return _RO_LONG_DAYS[d.weekday()] if loc == "ro" else f"{d:%A}"


def month_year(d: date, locale: str | None = None) -> str:
    """e.g. "Nov 2026" / "nov. 2026"."""
    loc = normalise(locale) or request_locale()
    return f"{_RO_MONTHS[d.month - 1]} {d.year}" if loc == "ro" else d.strftime("%b %Y")


def render(value: Any, locale: str | None = None) -> Any:
    """Render a T/When (or a list of them); anything else passes through."""
    if isinstance(value, (T, When)):
        return value.render(locale)
    if isinstance(value, list):
        return [render(v, locale) for v in value]
    return value


def tr(text: str, locale: str | None = None, **kw: Any) -> str:
    return T(text, **kw).render(locale)

"""Local news that can affect a trip: transport strikes, protests and marches, closures, weather alerts.

Sources need no key: Google News RSS (searched in the destination's own language, where local outlets and the city
council publish strike notices first) and the GDELT 2.0 DOC API as a fallback. Results are headlines with links;
the assistant reads them and says what they mean for the plans, and the app never treats them as verified fact.
"""
from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx
from flask import current_app

from app.services.cache import cache_get, cache_set

GOOGLE_NEWS = "https://news.google.com/rss/search"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
UA = "Mozilla/5.0 (compatible; Tandem travel assistant)"

# Destination country → (news language, words that signal a disruption in that language).
LANGUAGES: dict[str, tuple[str, list[str]]] = {
    "IT": ("it", ["sciopero", "manifestazione", "corteo", "chiusura", "chiuso", "allerta meteo", "disagi"]),
    "FR": ("fr", ["grève", "manifestation", "fermeture", "perturbations", "vigilance"]),
    "ES": ("es", ["huelga", "manifestación", "cierre", "cortes de tráfico", "alerta"]),
    "DE": ("de", ["Streik", "Demonstration", "Sperrung", "Unwetterwarnung"]),
    "AT": ("de", ["Streik", "Demonstration", "Sperrung", "Unwetterwarnung"]),
    "PT": ("pt", ["greve", "manifestação", "encerramento", "aviso meteorológico"]),
    "RO": ("ro", ["grevă", "protest", "manifestație", "închis", "cod meteo"]),
    "NL": ("nl", ["staking", "demonstratie", "afgesloten", "weeralarm"]),
    "GR": ("el", ["απεργία", "διαδήλωση", "κλειστό"]),
}
ENGLISH = ("en", ["strike", "protest", "march", "closure", "closed", "disruption", "weather warning"])
COUNTRY_NAMES = {"italy": "IT", "italia": "IT", "france": "FR", "spain": "ES", "españa": "ES", "germany": "DE",
                 "deutschland": "DE", "austria": "AT", "portugal": "PT", "romania": "RO", "românia": "RO",
                 "netherlands": "NL", "greece": "GR", "united kingdom": "GB", "uk": "GB", "ireland": "IE",
                 "united states": "US", "usa": "US"}
CITY_COUNTRY = {"rome": "IT", "roma": "IT", "milan": "IT", "florence": "IT", "venice": "IT", "naples": "IT",
                "firenze": "IT", "florenta": "IT", "milano": "IT", "venezia": "IT", "napoli": "IT", "veneția": "IT",
                "florența": "IT", "paris": "FR", "parigi": "FR", "lyon": "FR", "madrid": "ES", "barcelona": "ES", "seville": "ES", "berlin": "DE",
                "munich": "DE", "vienna": "AT", "lisbon": "PT", "porto": "PT", "bucharest": "RO", "bucurești": "RO",
                "cluj-napoca": "RO", "craiova": "RO", "brasov": "RO", "brașov": "RO", "sibiu": "RO", "timisoara": "RO", "timișoara": "RO", "iasi": "RO", "iași": "RO", "constanta": "RO", "constanța": "RO", "amsterdam": "NL", "athens": "GR", "london": "GB", "londra": "GB", "dublin": "IE", "bucuresti": "RO", "lisabona": "PT", "viena": "AT"}
# Local spellings, so local outlets are found ("Roma", not "Rome").
LOCAL_NAMES = {"rome": "Roma", "florence": "Firenze", "milan": "Milano", "venice": "Venezia", "naples": "Napoli",
               "turin": "Torino", "munich": "München", "cologne": "Köln", "vienna": "Wien", "lisbon": "Lisboa",
               "seville": "Sevilla", "bucharest": "București", "athens": "Αθήνα", "prague": "Praha", "the hague": "Den Haag"}
KINDS = [  # first match wins; words without diacritics, lower case
    ("strike", ["sciopero", "strike", "greve", "huelga", "streik", "greva", "staking", "apergia", "walkout"]),
    ("protest", ["manifest", "corteo", "protest", "march", "demonstr", "rally", "diadilosi"]),
    ("weather", ["allerta", "alert", "vigilance", "unwetter", "cod ", "weeralarm", "aviso", "warning", "storm"]),
    ("closure", ["chius", "closed", "closure", "fermeture", "cierre", "sperrung", "encerra", "inchis", "afgesloten"]),
]
MONTHS = {
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
           "novembre", "dicembre"],
    "fr": ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre", "novembre",
           "decembre"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre"],
    "de": ["januar", "februar", "marz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november",
           "dezember"],
    "pt": ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
           "novembro", "dezembro"],
    "ro": ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august", "septembrie", "octombrie",
           "noiembrie", "decembrie"],
    "en": ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december"],
}


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: str | None
    kind: str  # strike | protest | weather | closure | news
    mentions_dates: list[str] = field(default_factory=list)  # trip dates named in the headline


def country_for(city: str | None, country: str | None = None) -> str | None:
    if country:
        c = country.strip()
        if len(c) == 2:
            return c.upper()
        if c.lower() in COUNTRY_NAMES:
            return COUNTRY_NAMES[c.lower()]
    return CITY_COUNTRY.get((city or "").strip().lower())


def _kind(title: str) -> str:
    t = _plain(title)
    for kind, words in KINDS:
        if any(w in t for w in words):
            return kind
    return "news"


def _dates_in(title: str, days: list[date], lang: str) -> list[str]:
    t = _plain(title)
    hits = []
    for d in days:
        for lng in {lang, "en"}:
            month = MONTHS.get(lng, MONTHS["en"])[d.month - 1]
            if re.search(rf"\b{d.day}\s+{month}\b", t) or re.search(rf"\b{month}\s+{d.day}\b", t):
                hits.append(d.isoformat())
                break
    return hits


def _named_dates(title: str, lang: str, published: str | None) -> list[date]:
    """Every "30 ottobre" / "October 30" in a headline, placed in the year around when it was published."""
    t = _plain(title)
    ref = datetime.fromisoformat(published).date() if published else date.today()
    out = []
    for lng in {lang, "en"}:
        for m, month in enumerate(MONTHS.get(lng, MONTHS["en"]), start=1):
            for hit in re.finditer(rf"\b(\d{{1,2}})\s+{month}\b|\b{month}\s+(\d{{1,2}})\b", t):
                day = int(hit.group(1) or hit.group(2))
                for year in (ref.year, ref.year + 1, ref.year - 1):
                    try:
                        d = date(year, m, day)
                    except ValueError:
                        break
                    if abs((d - ref).days) <= 200:
                        out.append(d)
                        break
    return out


def _google_news(query: str, lang: str, country: str) -> list[dict]:
    params = {"q": query, "hl": lang, "gl": country, "ceid": f"{country}:{lang}"}
    resp = httpx.get(GOOGLE_NEWS, params=params, timeout=12, headers={"User-Agent": UA}, follow_redirects=True)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    out = []
    for item in root.findall("./channel/item")[:40]:
        title, source = item.findtext("title") or "", item.findtext("source") or ""
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "").astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            published = None
        out.append({"title": title.strip(), "url": item.findtext("link") or "", "source": source, "published": published})
    return out


def _gdelt(query: str) -> list[dict]:
    params = {"query": query, "mode": "artlist", "format": "json", "maxrecords": 30, "timespan": "7d", "sort": "datedesc"}
    resp = httpx.get(GDELT, params=params, timeout=15, headers={"User-Agent": UA})
    resp.raise_for_status()
    try:
        arts = resp.json().get("articles", [])
    except ValueError:  # GDELT answers rate limits in plain text
        return []
    out = []
    for a in arts:
        try:
            published = datetime.strptime(a.get("seendate", ""), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            published = None
        out.append({"title": a.get("title", ""), "url": a.get("url", ""), "source": a.get("domain", ""), "published": published})
    return out


def disruptions(city: str | None, *, country: str | None = None, days: list[date] | None = None,
                topic: str | None = None, max_items: int = 10) -> dict:
    """Recent headlines about strikes, protests, closures and alerts in a city, newest first; those naming one of
    `days` come first."""
    if not current_app.config.get("NEWS_ENABLED"):
        return {"available": False, "reason": "disabled", "items": []}
    if not city:
        return {"available": False, "reason": "no_location", "items": []}
    code = country_for(city, country) or "US"
    lang, words = LANGUAGES.get(code, ENGLISH)
    terms = [topic] if topic else words
    local = LOCAL_NAMES.get(city.strip().lower())
    place = f'("{city}" OR "{local}")' if local and local.lower() != city.strip().lower() else f'"{city}"'
    query = f'{place} ({" OR ".join(terms)}) when:10d'
    key = {"q": query, "c": code}
    raw = cache_get("news", key)
    source = "Google News"
    if raw is None:
        try:
            raw = _google_news(query, lang, code if code != "US" else "US")
        except (httpx.HTTPError, ET.ParseError) as exc:
            current_app.logger.warning("news: google news failed: %s", exc)
            raw = []
        if not raw:
            source = "GDELT"
            try:
                raw = _gdelt(f'{place} ({" OR ".join(t if " " not in t else f"{chr(34)}{t}{chr(34)}" for t in terms)})')
            except httpx.HTTPError as exc:
                current_app.logger.warning("news: gdelt failed: %s", exc)
                raw = []
        cache_set("news", key, raw, ttl_hours=1)
    days = days or []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    items, seen, today = [], set(), date.today()
    for r in raw:
        norm = _plain(r["title"])[:80]
        if not r["title"] or norm in seen or (r["published"] and r["published"] < cutoff):
            continue
        seen.add(norm)
        named = _named_dates(r["title"], lang, r["published"])
        if named and max(named) < today:  # about something that has already happened
            continue
        items.append(NewsItem(title=r["title"], url=r["url"], source=r["source"], published=r["published"],
                              kind=_kind(r["title"]),
                              mentions_dates=_dates_in(r["title"], days, lang)))
    relevant = [i for i in items if i.kind != "news" or topic]
    relevant.sort(key=lambda i: (not i.mentions_dates, -(datetime.fromisoformat(i.published).timestamp() if i.published else 0)))
    return {"available": True, "source": source, "language": lang, "query": query,
            "items": [asdict(i) for i in relevant[:max_items]]}


def for_trip(trip, topic: str | None = None, day: date | None = None) -> dict:
    from app.services.context.weather import trip_point

    _, _, _, name = trip_point(trip)
    dest = (trip.destinations or [None])[0]
    city = name or trip.primary_destination
    days: list[date] = []
    if day:
        days = [day]
    elif trip.start_date and trip.end_date:
        days = [trip.start_date + timedelta(days=i) for i in range((trip.end_date - trip.start_date).days + 1)]
    out = disruptions(city, country=getattr(dest, "country", None), days=days, topic=topic)
    out["place"] = city
    return out

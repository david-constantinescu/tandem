"""chestii de locatie: aeroporturi, fusuri orare, geocodare, distante"""
from __future__ import annotations

import logging
import math
import re
import threading
import time
from dataclasses import asdict, dataclass
from functools import lru_cache

import httpx
from flask import current_app

from app.services.cache import cache_get, cache_set

log = logging.getLogger("tandem.geo")


@dataclass
class Place:
    name: str
    city: str | None = None
    country: str | None = None
    lat: float | None = None
    lon: float | None = None
    tz: str | None = None
    iata: str | None = None
    source: str = "unknown"  # airport_db | city_db | nominatim

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def _airports() -> dict[str, dict]:
    import airportsdata

    return airportsdata.load("IATA")


@lru_cache(maxsize=1)
def _city_index() -> dict[str, list[dict]]:
    """city name (lower) -> airports in cities of that name (possibly several countries)"""
    index: dict[str, list[dict]] = {}
    for a in _airports().values():
        name = (a.get("city") or "").strip().lower()
        if name:
            index.setdefault(name, []).append(a)
    return index


@lru_cache(maxsize=1)
def _tzfinder():
    from timezonefinder import TimezoneFinder

    return TimezoneFinder()


def airport(code: str | None) -> Place | None:
    if not code:
        return None
    a = _airports().get(code.strip().upper())
    if not a:
        return None
    return Place(name=a["name"], city=a.get("city"), country=a.get("country"), lat=a.get("lat"), lon=a.get("lon"),
                 tz=a.get("tz"), iata=a.get("iata"), source="airport_db")


def city(name: str | None, country: str | None = None) -> Place | None:
    """resolve a city name offline"""
    from app.services.geo.cities import ALIASES, MAJOR_CITIES

    if not name:
        return None
    key = name.strip().lower()
    key = ALIASES.get(key, key)
    major = MAJOR_CITIES.get(key)
    if major and (country is None or major[3] == country):
        lat, lon, tz, cc = major
        return Place(name=name.strip().title() if name.islower() else name.strip(), city=key.title(), country=cc,
                     lat=lat, lon=lon, tz=tz, source="city_db")
    candidates = _city_index().get(key, [])
    if country:
        candidates = [a for a in candidates if a.get("country") == country]
    countries = {(a.get("country"), a.get("subd")) for a in candidates}
    if not candidates or len(countries) > 1:
        return None  # unknown or ambiguous (e.g. several towns of that name): don't guess
    a = candidates[0]
    return Place(name=a.get("city") or name, city=a.get("city"), country=a.get("country"), lat=a.get("lat"),
                 lon=a.get("lon"), tz=a.get("tz"), source="city_db")


def tz_for_point(lat: float | None, lon: float | None) -> str | None:
    from app.services.geo.cities import MAJOR_CITIES

    if lat is None or lon is None:
        return None
    for clat, clon, tz, _cc in MAJOR_CITIES.values():
        if abs(clat - lat) < 1 and abs(clon - lon) < 1 and haversine_km(lat, lon, clat, clon) < 60:
            return tz
    try:
        return _tzfinder().timezone_at(lat=lat, lng=lon)
    except ImportError:  # optional dependency, omitted from slim serverless builds
        return None
    except Exception:  # noqa: BLE001
        return None


_IATA_IN_PARENS = re.compile(r"\(([A-Z]{3})\)")


def find_airport_code(text: str | None) -> str | None:
    if not text:
        return None
    m = _IATA_IN_PARENS.search(text)
    if m and m.group(1) in _airports():
        return m.group(1)
    stripped = text.strip()
    if re.fullmatch(r"[A-Z]{3}", stripped) and stripped in _airports():
        return stripped
    return None


def resolve_place(text: str | None, *, allow_network: bool = True) -> Place | None:
    """best-effort resolution of an airport, city or address string"""
    from app.services.geo.cities import COUNTRY_NAMES

    if not text or not text.strip():
        return None
    code = find_airport_code(text)
    if code:
        return airport(code)
    # address parts, most specific last ("Via Roma 1, 00153 Rome, Italy"); country names give a hint
    parts = [re.sub(r"\b\d{3,6}(-\d{3})?\b", "", p).strip(" .") for p in text.split(",")]
    country = next((COUNTRY_NAMES[p.lower()] for p in parts if p.lower() in COUNTRY_NAMES), None)
    candidates = [text.strip()] + [p for p in reversed(parts) if p and p.lower() not in COUNTRY_NAMES]
    for part in candidates:
        place = city(part, country)
        if place:
            if part.lower() != text.strip().lower():
                place.name = text.strip()
            return place
    if allow_network:
        return geocode(text)
    return None


_nominatim_lock = threading.Lock()
_nominatim_last = [0.0]


def user_agent() -> str:
    contact = current_app.config.get("OSM_CONTACT_EMAIL") or "contact-not-configured"
    return f"Tandem-Travel/1.0 ({contact})"


def geocode(query: str) -> Place | None:
    cfg = current_app.config
    if cfg.get("LOCATION_PROVIDER") != "nominatim" or cfg.get("TESTING"):
        return None
    key_src = query.strip().lower()
    cached = cache_get("geocode", key_src)
    if cached is not None:
        return Place(**cached) if cached else None
    with _nominatim_lock:
        wait = 1.05 - (time.monotonic() - _nominatim_last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            resp = httpx.get(
                f"{cfg['NOMINATIM_URL']}/search",
                params={"q": query, "format": "jsonv2", "limit": 1, "addressdetails": 1},
                headers={"User-Agent": user_agent(), "Accept-Language": "en"}, timeout=10,
            )
            _nominatim_last[0] = time.monotonic()
            resp.raise_for_status()
            rows = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("geocoding failed: %s", type(exc).__name__)
            return None
    if not rows:
        cache_set("geocode", key_src, {}, ttl_hours=24 * 7)
        return None
    row = rows[0]
    addr = row.get("address") or {}
    lat, lon = float(row["lat"]), float(row["lon"])
    place = Place(
        name=query.strip(), city=addr.get("city") or addr.get("town") or addr.get("village"),
        country=addr.get("country"), lat=lat, lon=lon, tz=tz_for_point(lat, lon), source="nominatim",
    )
    cache_set("geocode", key_src, place.to_dict(), ttl_hours=24 * 30)
    return place


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def travel_time_minutes(lat1: float, lon1: float, lat2: float, lon2: float, mode: str = "driving") -> float | None:
    """routed travel time from a configured OSRM server, or None when no routing provider is available"""
    base = current_app.config.get("ROUTING_OSRM_URL")
    if not base or current_app.config.get("TESTING"):
        return None
    profile = {"walking": "foot", "driving": "driving"}.get(mode, "driving")
    key = f"{profile}:{lat1:.4f},{lon1:.4f}:{lat2:.4f},{lon2:.4f}"
    cached = cache_get("route", key)
    if cached is not None:
        return cached.get("minutes")
    try:
        resp = httpx.get(f"{base}/route/v1/{profile}/{lon1},{lat1};{lon2},{lat2}", params={"overview": "false"},
                         headers={"User-Agent": user_agent()}, timeout=10)
        resp.raise_for_status()
        routes = resp.json().get("routes") or []
    except (httpx.HTTPError, ValueError):
        return None
    minutes = routes[0]["duration"] / 60 if routes else None
    cache_set("route", key, {"minutes": minutes}, ttl_hours=24 * 7)
    return minutes

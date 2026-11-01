"""vremea pe zilele calatoriei, de la open-meteo (gratis, fara cheie)"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

import httpx
from flask import current_app

from app.services.cache import cache_get, cache_set
from app.utils.timeutil import utcnow

FORECAST_DAYS = 16
WET_PROBABILITY = 50  # % chance of rain from which a day (or hour) counts as wet


def condition(code: int | None) -> str:
    """WMO weather code -> clear | cloudy | fog | drizzle | rain | snow | storm"""
    if code is None:
        return "unknown"
    if code == 0:
        return "clear"
    if code <= 3:
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 57:
        return "drizzle"
    if 61 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if code >= 95:
        return "storm"
    return "cloudy"


@dataclass
class DayWeather:
    date: str
    condition: str
    temp_max: float | None
    temp_min: float | None
    precip_probability: int | None
    precip_mm: float | None
    wind_kmh: float | None
    wet_hours: list[str] = field(default_factory=list)  # local hours with a high chance of rain
    outdoor_ok: bool = True


def _fetch(lat: float, lon: float, tz: str, start: date, end: date) -> dict | None:
    params = {
        "latitude": round(lat, 3), "longitude": round(lon, 3), "timezone": tz or "auto",
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,"
                 "wind_speed_10m_max",
        "hourly": "precipitation_probability",
    }
    key = {"p": params}
    cached = cache_get("weather", key)
    if cached is not None:
        return cached
    try:
        resp = httpx.get(current_app.config["OPEN_METEO_URL"], params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        current_app.logger.warning("weather: %s", exc)
        return None
    cache_set("weather", key, data, ttl_hours=3)
    return data


def forecast(lat: float | None, lon: float | None, tz: str | None, start: date, end: date) -> dict:
    """daily weather between two dates (inclusive), clipped to what's forecast today"""
    if not current_app.config.get("WEATHER_ENABLED"):
        return {"available": False, "reason": "disabled", "days": []}
    if lat is None or lon is None:
        return {"available": False, "reason": "no_location", "days": []}
    today = utcnow().date()
    last = today + timedelta(days=FORECAST_DAYS - 1)
    lo, hi = max(start, today), min(end, last)
    if lo > hi:
        return {"available": False, "reason": "too_far_ahead" if start > last else "past",
                "forecast_from": (start - timedelta(days=FORECAST_DAYS - 1)).isoformat(), "days": []}
    data = _fetch(lat, lon, tz or "auto", lo, hi)
    if not data or "daily" not in data:
        return {"available": False, "reason": "unavailable", "days": []}
    d, h = data["daily"], data.get("hourly") or {}
    wet_by_day: dict[str, list[str]] = {}
    for t, p in zip(h.get("time", []), h.get("precipitation_probability", [])):
        if p is not None and p >= WET_PROBABILITY and "08:00" <= t[11:16] <= "22:00":
            wet_by_day.setdefault(t[:10], []).append(t[11:16])
    days = []
    for i, day in enumerate(d["time"]):
        cond = condition(d["weather_code"][i])
        prob = d["precipitation_probability_max"][i]
        wet = cond in ("rain", "storm", "snow") or (prob is not None and prob >= 70)
        days.append(asdict(DayWeather(
            date=day, condition=cond, temp_max=d["temperature_2m_max"][i], temp_min=d["temperature_2m_min"][i],
            precip_probability=prob, precip_mm=d["precipitation_sum"][i], wind_kmh=d["wind_speed_10m_max"][i],
            wet_hours=wet_by_day.get(day, []), outdoor_ok=not wet)))
    return {"available": True, "source": "Open-Meteo", "timezone": data.get("timezone"), "days": days,
            "covers_until": hi.isoformat()}


def trip_point(trip) -> tuple[float | None, float | None, str | None, str | None]:
    """where to read the weather for a trip: its first located destination"""
    for d in trip.destinations or []:
        if d.lat is not None and d.lon is not None:
            return d.lat, d.lon, d.timezone, d.name
    return getattr(trip, "lat", None), getattr(trip, "lon", None), None, trip.primary_destination


def for_trip(trip, day: date | None = None) -> dict:
    from app.extensions import db
    from app.models import User

    owner = db.session.get(User, trip.user_id)
    if owner is not None and owner.is_demo:  # spatiile demo nu au vreme: datele sunt fictive
        return {"available": False, "reason": "demo", "days": []}
    lat, lon, tz, name = trip_point(trip)
    start = day or trip.start_date or utcnow().date()
    end = day or trip.end_date or start
    out = forecast(lat, lon, tz, start, end)
    out["place"] = name
    return out

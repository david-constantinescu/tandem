"""Normalise extracted records: resolve places and timezones, convert to UTC, verify evidence.

Verification is the concrete guard against hallucination: booking references, flight numbers, dates,
times and prices claimed by any extractor must appear in the text Tandem itself extracted from the
document (embedded PDF text or local OCR). Values that cannot be found are marked unverified,
lower the record's confidence, and are highlighted for review.
"""
from __future__ import annotations

import re
from datetime import datetime

from app.services import geo
from app.services.ingestion.dates import find_dates, find_times, time_variants
from app.services.ingestion.schema import ExtractedTravelRecord
from app.utils.timeutil import is_valid_tz, iso, localize

TRANSPORT = {"flight", "train", "bus", "ferry", "transfer"}
VERIFIED_FIELDS = ("booking_reference", "flight_number", "train_number", "start_local", "end_local", "price")


def _squash(s: str) -> str:
    return re.sub(r"[\s\-_/.]", "", s).lower()


def _resolve(text: str | None, code: str | None, allow_network: bool) -> geo.Place | None:
    if code:
        place = geo.airport(code)
        if place:
            return place
    if text:
        return geo.resolve_place(text, allow_network=allow_network)
    return None


def normalise_record(rec: ExtractedTravelRecord, *, source_text: str | None, fallback_tz: str,
                     allow_network: bool = True) -> tuple[dict, list[dict], list[str], float]:
    """Return (data, field_rows, notes, confidence)."""
    notes = list(rec.uncertainty_notes)
    if rec.date_ambiguity:
        notes.append(rec.date_ambiguity)
    details = {k: v for k, v in rec.details.model_dump().items() if v not in (None, "", [])}

    start_place = end_place = None
    if rec.record_type in TRANSPORT:
        start_place = _resolve(rec.origin, rec.origin_code, allow_network)
        end_place = _resolve(rec.destination, rec.destination_code, allow_network)
    else:
        query = rec.address or ", ".join(x for x in (rec.location_name, rec.city, rec.country) if x) or None
        start_place = _resolve(rec.city, None, False) if rec.city else None
        if (start_place is None or rec.address) and query:
            precise = geo.resolve_place(query, allow_network=allow_network)
            start_place = precise or start_place
        end_place = start_place

    assumed: set[str] = set()

    def pick_tz(stated: str | None, place: geo.Place | None, label: str) -> str:
        place_tz = place.tz if place else None
        if stated and is_valid_tz(stated):
            if place_tz and place_tz != stated:
                notes.append(f"{label} timezone {stated} differs from location timezone {place_tz}; using {place_tz}")
                return place_tz
            return stated
        if place_tz:
            return place_tz
        notes.append(f"{label} timezone unknown; assumed {fallback_tz}")
        assumed.add(label.lower())
        return fallback_tz

    start_tz = pick_tz(rec.start_timezone, start_place, "Start")
    end_tz = pick_tz(rec.end_timezone, end_place, "End") if rec.end_local else start_tz

    def to_utc(local: str | None, tz: str) -> str | None:
        if not local:
            return None
        try:
            naive = datetime.fromisoformat(local[:16])
        except ValueError:
            notes.append(f"Unreadable date/time '{local}'")
            return None
        aware, dst_notes = localize(naive, tz)
        notes.extend(dst_notes)
        return iso(aware)

    start_at = to_utc(rec.start_local, start_tz)
    end_at = to_utc(rec.end_local, end_tz)
    if start_at and end_at and end_at < start_at:
        notes.append("End is before start; please check the dates")
    deadline_at = to_utc(rec.cancellation_deadline_local, start_tz)

    city = rec.city or (start_place.city if start_place else None)
    data = {
        "type": rec.record_type,
        "title": (rec.title or _default_title(rec, details))[:300],
        "provider_name": rec.provider_name,
        "booking_reference": rec.booking_reference.strip() if rec.booking_reference else None,
        "status": rec.confirmation_status,
        "description": rec.description,
        "origin": rec.origin, "origin_code": rec.origin_code,
        "destination": rec.destination, "destination_code": rec.destination_code,
        "start_local": rec.start_local, "start_tz": start_tz, "start_at": start_at,
        "end_local": rec.end_local, "end_tz": end_tz, "end_at": end_at,
        "location_name": rec.location_name or (rec.provider_name if rec.record_type in ("hotel", "restaurant") else None),
        "address": rec.address, "city": city, "country": rec.country or (start_place.country if start_place else None),
        "lat": start_place.lat if start_place else None, "lon": start_place.lon if start_place else None,
        "end_city": end_place.city if end_place and rec.record_type in TRANSPORT else None,
        "end_lat": end_place.lat if end_place and rec.record_type in TRANSPORT else None,
        "end_lon": end_place.lon if end_place and rec.record_type in TRANSPORT else None,
        "place_source": start_place.source if start_place else None,
        "price": rec.price, "currency": rec.currency,
        "travellers": rec.traveller_names,
        "details": details,
        "cancellation_deadline": deadline_at, "cancellation_policy": rec.cancellation_policy,
        "website": rec.website, "contact": rec.contact,
        "is_change_notice": rec.is_change_notice, "is_cancellation_notice": rec.is_cancellation_notice,
        "start_tz_assumed": "start" in assumed, "end_tz_assumed": "end" in assumed and bool(rec.end_local),
    }
    if rec.is_cancellation_notice:
        data["status"] = "cancelled"

    fields, unverified = _field_rows(rec, data, details, source_text)
    if "end_local" in unverified and _end_matches_stated_duration(rec, source_text):
        unverified.remove("end_local")
        for f in fields:
            if f["field_name"] == "end_local":
                f["verification"] = "derived"
    confidence = rec.confidence
    if unverified:
        notes.append("Not found in the document text: " + ", ".join(unverified))
        confidence = round(confidence * 0.7, 2)
    if not start_at:
        confidence = round(min(confidence, 0.4), 2)
    return data, fields, _dedupe(notes), confidence


_DURATION = re.compile(r"(\d+(?:[.,]\d+)?)\s*(hours?|hrs?|h|minutes?|mins?)\b", re.I)


def _end_matches_stated_duration(rec: ExtractedTravelRecord, source_text: str | None) -> bool:
    """True when the end time equals start + a duration printed in the document (a derived, not invented, value)."""
    if not (source_text and rec.start_local and rec.end_local):
        return False
    try:
        minutes = (datetime.fromisoformat(rec.end_local[:16]) - datetime.fromisoformat(rec.start_local[:16])).total_seconds() / 60
    except ValueError:
        return False
    for m in _DURATION.finditer(source_text):
        amount = float(m.group(1).replace(",", "."))
        stated = amount * 60 if m.group(2).lower().startswith("h") else amount
        if abs(stated - minutes) < 1:
            return True
    return False


def _default_title(rec: ExtractedTravelRecord, details: dict) -> str:
    if rec.record_type == "flight":
        return f"Flight {details.get('flight_number', '')} {rec.origin_code or rec.origin or ''} → " \
               f"{rec.destination_code or rec.destination or ''}".strip()
    return rec.provider_name or rec.location_name or rec.record_type.replace("_", " ").title()


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def verify_value(field: str, value, source_text: str | None) -> str:
    if value in (None, "", []):
        return "no_value"
    if not source_text or not source_text.strip():
        return "no_source_text"
    text = source_text
    if field in ("booking_reference", "flight_number", "train_number"):
        return "evidence_found" if _squash(str(value)) in _squash(text) else "not_found_in_source"
    if field in ("start_local", "end_local"):
        try:
            dt = datetime.fromisoformat(str(value)[:16])
        except ValueError:
            return "not_found_in_source"
        dates = {h.value for h in find_dates(text)}
        if dt.date() not in dates:
            return "not_found_in_source"
        if dt.hour == 0 and dt.minute == 0:
            return "evidence_found"
        times = {(t.value.hour, t.value.minute) for t in find_times(text)}
        if (dt.hour, dt.minute) in times or any(v.lower() in text.lower() for v in time_variants(dt.time())):
            return "evidence_found"
        return "not_found_in_source"
    if field == "price":
        amount = float(value)
        candidates = {f"{amount:.2f}", f"{amount:.2f}".replace(".", ","), f"{amount:g}", f"{int(amount)}"}
        flat = text.replace(" ", " ")
        return "evidence_found" if any(c in flat for c in candidates) else "not_found_in_source"
    return "not_checked"


def _field_rows(rec: ExtractedTravelRecord, data: dict, details: dict, source_text: str | None):
    evidence: dict[str, tuple[str, int | None]] = {}
    for ev in rec.evidence:
        key = ev.field.split(".")[-1]
        evidence.setdefault(key, (ev.quote[:500], ev.page))
    rows: list[dict] = []
    unverified: list[str] = []
    flat = {
        "title": data["title"], "provider_name": data["provider_name"], "booking_reference": data["booking_reference"],
        "status": data["status"], "origin": data["origin"], "destination": data["destination"],
        "origin_code": data["origin_code"], "destination_code": data["destination_code"],
        "start_local": data["start_local"], "end_local": data["end_local"], "start_tz": data["start_tz"],
        "address": data["address"], "city": data["city"], "price": data["price"], "currency": data["currency"],
        "travellers": data["travellers"] or None, "cancellation_policy": data["cancellation_policy"],
        **{k: v for k, v in details.items()},
    }
    for name, value in flat.items():
        if value in (None, "", []):
            continue
        quote, page = evidence.get(name, (None, None))
        verification = verify_value(name, value, source_text) if name in VERIFIED_FIELDS else (
            "evidence_found" if quote and source_text and _squash(quote)[:40] in _squash(source_text) else
            ("no_source_text" if not source_text else "not_checked"))
        if verification == "not_found_in_source":
            unverified.append(name)
        rows.append({"field_name": name, "value": value, "evidence": quote, "source_page": page,
                     "verification": verification})
    return rows, unverified

"""Simulated activity provider — available ONLY to demo workspaces.

It behaves like a real booking API (search, live-looking availability, quotes, idempotent booking,
retrieval for verification, cancellation) over a fictional catalogue, so the full approval workflow
can be demonstrated without real bookings, payments or third-party calls. Its "provider-side"
booking store is separate from Tandem's own tables, so verification is a genuine read-back.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import date as date_cls
from datetime import datetime, timedelta

from app.services import geo
from app.services.cache import cache_get, cache_set
from app.services.providers.base import (
    SIMULATED, ActivityResult, ActivitySearchRequest, AvailabilityQuote, BookingResult, ProviderRequestError,
    TravelProviderAdapter,
)
from app.utils.timeutil import utcnow

ROME_CATALOGUE = [
    ("sim-rome-001", "Colosseum & Roman Forum Guided Visit", "tours", 180, 49.0, 41.8902, 12.4922,
     "Piazza del Colosseo, 00184 Rome", ["09:00", "11:30", "14:00", "16:00"], True,
     "Small-group visit of the arena floor and the Forum with a licensed guide."),
    ("sim-rome-002", "Trastevere Food Walk", "food", 210, 65.0, 41.8896, 12.4695,
     "Piazza di Santa Maria in Trastevere, Rome", ["11:00", "17:30"], False,
     "Tastings at five family-run spots across Trastevere's lanes."),
    ("sim-rome-003", "Borghese Gallery Timed Entry", "museums", 120, 27.0, 41.9142, 12.4922,
     "Piazzale Scipione Borghese 5, Rome", ["09:00", "11:00", "13:00", "15:00", "17:00"], True,
     "Two-hour timed entry to the gallery's sculpture and painting collection."),
    ("sim-rome-004", "Pasta-Making Workshop near Campo de' Fiori", "workshops", 150, 59.0, 41.8956, 12.4722,
     "Via dei Cappellari 30, Rome", ["10:00", "15:00", "18:30"], True,
     "Make fettuccine and ravioli by hand, then eat what you made."),
    ("sim-rome-005", "Appian Way E-Bike Ride", "outdoor", 240, 75.0, 41.8569, 12.5160,
     "Via Appia Antica 58, Rome", ["09:30", "14:30"], False,
     "Guided e-bike ride past aqueducts, catacombs and Roman tombs."),
    ("sim-rome-006", "Vatican Gardens Small-Group Tour", "tours", 120, 45.0, 41.9040, 12.4500,
     "Viale Vaticano, Rome", ["08:30", "10:30", "13:30"], True,
     "A walk through the Vatican Gardens with a historian guide."),
    ("sim-rome-007", "Twilight Rooftop Aperitivo Walk", "entertainment", 120, 39.0, 41.8986, 12.4768,
     "Piazza Navona, Rome", ["18:00", "19:00"], False,
     "Golden-hour walk ending with an aperitivo on a rooftop terrace."),
    ("sim-rome-008", "Day Trip to Tivoli Villas", "day trips", 480, 95.0, 41.9636, 12.7960,
     "Departure: Piazza della Repubblica, Rome", ["08:00"], False,
     "Hadrian's Villa and Villa d'Este with coach transport."),
    ("sim-rome-009", "Capitoline Museums Highlights", "museums", 150, 32.0, 41.8930, 12.4828,
     "Piazza del Campidoglio 1, Rome", ["09:30", "12:00", "15:30"], True,
     "Guided highlights of the world's oldest public museums."),
    ("sim-rome-010", "Ostia Antica Half-Day Tour", "historical", 300, 69.0, 41.7556, 12.2915,
     "Meeting point: Piramide metro station, Rome", ["09:00", "13:30"], False,
     "Explore the excavated port city of ancient Rome."),
]
TIMEZONE_ROME = "Europe/Rome"
CANCELLATION = "Free cancellation up to 24 hours before the start time (simulated policy)."


def _catalogue_for(req: ActivitySearchRequest) -> tuple[list[tuple], str]:
    loc = (req.location or "").lower()
    near_rome = req.lat is not None and geo.haversine_km(req.lat, req.lon, 41.9028, 12.4964) < 60
    if "rome" in loc or "roma" in loc or near_rome:
        return ROME_CATALOGUE, TIMEZONE_ROME
    place = geo.resolve_place(req.location, allow_network=False) if req.location else None
    if place is None and req.lat is None:
        return [], "UTC"
    lat = place.lat if place else req.lat
    lon = place.lon if place else req.lon
    city = (place.city if place else None) or (req.location or "City").title()
    slug = "".join(ch for ch in city.lower() if ch.isalnum())[:12]
    generic = [
        (f"sim-{slug}-001", f"{city} Old Town Walking Tour", "tours", 150, 29.0, lat, lon, f"Main square, {city}",
         ["10:00", "15:00"], True, f"A simulated introduction to {city}'s historic centre."),
        (f"sim-{slug}-002", f"{city} Food Tasting Evening", "food", 180, 55.0, lat + 0.004, lon + 0.003,
         f"Central market, {city}", ["18:30"], False, "Simulated tasting tour."),
        (f"sim-{slug}-003", f"{city} City Museum Entry", "museums", 120, 18.0, lat - 0.003, lon + 0.002,
         f"Museum district, {city}", ["09:00", "11:00", "14:00"], True, "Simulated timed entry ticket."),
    ]
    tz = (place.tz if place else None) or geo.tz_for_point(lat, lon) or "UTC"
    return generic, tz


def _remaining(item_id: str, day: str, time: str) -> int:
    h = int(hashlib.sha256(f"{item_id}|{day}|{time}".encode()).hexdigest(), 16)
    return h % 9  # 0 means sold out


class SimulatorAdapter(TravelProviderAdapter):
    key = "simulator"
    name = "Tandem Demo Provider"
    simulated = True

    def state(self) -> str:
        return SIMULATED

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps.update(search=True, details=True, availability=True, booking=True, cancellation=True, redirect=False,
                    environment="simulated",
                    notes=["Demo only: fictional catalogue, simulated availability and bookings. "
                           "No real reservations, payments or external calls."])
        return caps

    def _items(self, req: ActivitySearchRequest):
        catalogue, tz = _catalogue_for(req)
        return [(row, tz) for row in catalogue]

    def _to_result(self, row, tz, req: ActivitySearchRequest | None = None) -> ActivityResult:
        item_id, title, category, duration, price, lat, lon, address, times, accessible, desc = row
        slots = []
        if req and req.date_from:
            day = req.date_from
            last = req.date_to or req.date_from
            while day <= last and len(slots) < 12:
                for t in times:
                    slots.append({"date": day.isoformat(), "time": t, "remaining": _remaining(item_id, day.isoformat(), t),
                                  "timezone": tz})
                day += timedelta(days=1)
        return ActivityResult(
            provider=self.key, provider_item_id=item_id, title=title, description=desc, location_name=title,
            address=address, city=address.split(",")[-1].strip() if "," in address else None, lat=lat, lon=lon,
            price=price, currency="EUR", price_basis="per_person", duration_minutes=duration, categories=[category],
            rating=4.4 + (int(item_id[-1]) % 5) / 10, review_count=120 + int(item_id[-2:]) * 37,
            cancellation_policy=CANCELLATION, availability_checked=bool(slots), available_slots=slots,
            bookable_via_api=True, accessible=accessible, source_label="Simulated provider (demo only)",
            simulated=True,
        )

    def search(self, req: ActivitySearchRequest) -> list[ActivityResult]:
        results = []
        for row, tz in self._items(req):
            res = self._to_result(row, tz, req)
            if req.categories and not set(c.lower() for c in req.categories) & set(res.categories):
                continue
            if req.query and req.query.lower() not in (res.title + " " + res.description).lower():
                continue
            if req.max_price is not None and res.price is not None and res.price > req.max_price:
                continue
            if req.accessible_only and not res.accessible:
                continue
            if req.max_duration_minutes and res.duration_minutes and res.duration_minutes > req.max_duration_minutes:
                continue
            results.append(res)
        return results[: req.limit]

    def _find(self, item_id: str):
        for row in ROME_CATALOGUE:
            if row[0] == item_id:
                return row, TIMEZONE_ROME
        slug = item_id.split("-")[1] if item_id.count("-") >= 2 else ""
        for row, tz in self._items(ActivitySearchRequest(location=slug)):
            if row[0] == item_id:
                return row, tz
        raise ProviderRequestError("Activity not found in the simulated catalogue", code="not_found")

    def get_details(self, item_id: str) -> ActivityResult:
        row, tz = self._find(item_id)
        return self._to_result(row, tz)

    def check_availability(self, item_id: str, day: str, time: str | None, participants: int) -> AvailabilityQuote:
        row, tz = self._find(item_id)
        times = row[8]
        chosen = time or times[0]
        if chosen not in times:
            return AvailabilityQuote(self.key, item_id, row[1], day, chosen, participants, False, row[4], None, "EUR",
                                     CANCELLATION, row[3], tz, checked_at=utcnow().isoformat(),
                                     detail={"reason": f"No departure at {chosen}", "times": times})
        remaining = _remaining(item_id, day, chosen)
        available = remaining >= participants
        return AvailabilityQuote(
            provider=self.key, provider_item_id=item_id, title=row[1], date=day, time=chosen, participants=participants,
            available=available, unit_price=row[4], total_price=round(row[4] * participants, 2), currency="EUR",
            cancellation_policy=CANCELLATION, duration_minutes=row[3], timezone=tz,
            quote_ref=f"SIMQ-{hashlib.sha1(f'{item_id}{day}{chosen}{participants}'.encode()).hexdigest()[:10].upper()}",
            checked_at=utcnow().isoformat(),
            detail={"remaining": remaining, "address": row[7], "lat": row[5], "lon": row[6], "simulated": True},
        )

    def create_booking(self, quote: dict, traveller: dict, idempotency_key: str) -> BookingResult:
        existing_id = cache_get("simulator_idem", idempotency_key)
        if existing_id:
            return self.get_booking(existing_id["booking_id"])
        live = self.check_availability(quote["provider_item_id"], quote["date"], quote["time"], quote["participants"])
        if not live.available:
            raise ProviderRequestError("The simulated slot is sold out", code="sold_out")
        if live.total_price != quote.get("total_price"):
            raise ProviderRequestError("The simulated price changed", code="price_changed")
        booking_id = f"SIM-{secrets.token_hex(3).upper()}"
        record = {"booking_id": booking_id, "status": "confirmed", "item_id": live.provider_item_id,
                  "title": live.title, "date": live.date, "time": live.time, "participants": live.participants,
                  "total_price": live.total_price, "currency": live.currency, "lead_traveller": traveller.get("name"),
                  "created_at": utcnow().isoformat(), "simulated": True}
        cache_set("simulator_bookings", booking_id, record, ttl_hours=24 * 60)
        cache_set("simulator_idem", idempotency_key, {"booking_id": booking_id}, ttl_hours=24 * 60)
        return BookingResult(booking_id, "confirmed", simulated=True, summary=record)

    def get_booking(self, booking_id: str) -> BookingResult:
        record = cache_get("simulator_bookings", booking_id)
        if not record:
            raise ProviderRequestError("Simulated booking not found", code="not_found")
        return BookingResult(booking_id, record["status"], simulated=True, summary=record)

    def cancel_booking(self, booking_id: str) -> BookingResult:
        record = cache_get("simulator_bookings", booking_id)
        if not record:
            raise ProviderRequestError("Simulated booking not found", code="not_found")
        record["status"] = "cancelled"
        cache_set("simulator_bookings", booking_id, record, ttl_hours=24 * 60)
        return BookingResult(booking_id, "cancelled", simulated=True, summary=record)


def parse_day(value: str) -> date_cls:
    return datetime.fromisoformat(value).date()

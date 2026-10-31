"""Demo workspaces: isolated, fictional, and wired to the simulated provider only.

`create_demo_workspace` gives each visitor their own tenant (expires after DEMO_SESSION_HOURS) so
visitors never see each other's actions. `seed_demo_account` maintains the shared demo@tandem.travel
account for presentations. Both use the same seeding function and the real application code paths.
"""
from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta

from flask import current_app

from app.extensions import db
from app.i18n import locale_of, tr, weekday_name
from app.models import Conversation, DemoTenant, Document, User
from app.models.user import AI_MODE_FULL, AI_MODE_OFF
from app.security.encryption import sha256_hex
from app.services import users as user_service
from app.services.demo import documents as demo_docs
from app.services.ingestion import extractors
from app.services.itinerary.conflicts import check_and_notify
from app.services.itinerary.service import create_event
from app.services.storage import storage
from app.services.trips import service as trips
from app.utils.timeutil import iso, localize, utcnow

ROME_TZ = "Europe/Rome"
HOME_TZ = "Europe/Bucharest"  # Craiova


def demo_start_date(today: date | None = None) -> date:
    """Next occurrence of 12 November that keeps the 12–16 Nov trip in the future (or ongoing)."""
    today = today or utcnow().date()
    start = date(today.year, 11, 12)
    if today > start + timedelta(days=4):
        start = date(today.year + 1, 11, 12)
    return start


def _at(day: date, hhmm: str, tz: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    aware, _ = localize(datetime(day.year, day.month, day.day, h, m), tz)
    return iso(aware)


def _store_doc(user: User, trip_id, filename: str, mime: str, data: bytes) -> Document:
    content = extractors.extract(data, mime)
    d = Document(user_id=user.id, trip_id=trip_id, source="demo", filename=filename, mime_type=mime,
                 size_bytes=len(data), sha256=sha256_hex(data), status="processed", classification="travel",
                 status_detail=tr("Demo document (fictional)", locale_of(user)), extracted_text=content.text, page_count=content.page_count,
                 extraction_method={"path": "demo_seed", "provider": "demo"}, processed_at=utcnow())
    db.session.add(d)
    db.session.flush()
    d.storage_key = f"documents/{user.id}/{d.id}"
    storage().put(d.storage_key, data, mime)
    return d


def create_demo_workspace(locale: str = "ro") -> User:
    cfg = current_app.config
    tenant = DemoTenant(label="visitor", expires_at=utcnow() + timedelta(hours=cfg["DEMO_SESSION_HOURS"]))
    db.session.add(tenant)
    db.session.flush()
    user = user_service.create_user(
        f"demo+{secrets.token_hex(4)}@demo.tandem.travel", secrets.token_urlsafe(24), demo_docs.TRAVELLERS[0], is_demo=True,
        demo_tenant_id=tenant.id, ai_mode=AI_MODE_FULL if cfg["DEMO_ALLOW_EXTERNAL_AI"] else AI_MODE_OFF, locale=locale)
    _profile(user)
    seed_rome_trip(user)
    from app.services.agent import proactive

    proactive.check_user(user, force=True)  # Tandem writes first: the demo opens with its own heads-up
    return user


def seed_demo_account(password: str | None = None) -> tuple[User, str | None]:
    """Create or reset the shared demo account. Returns (user, generated_password_or_None)."""
    cfg = current_app.config
    email = cfg["DEMO_ACCOUNT_EMAIL"]
    existing = db.session.execute(db.select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        for d in db.session.execute(db.select(Document).where(Document.user_id == existing.id)).scalars():
            if d.storage_key:
                storage().delete(d.storage_key)
        db.session.delete(existing)
        db.session.flush()
    generated = None
    if not password:
        password = cfg.get("DEMO_ACCOUNT_PASSWORD") or None
    if not password:
        password = generated = secrets.token_urlsafe(12)
    tenant = DemoTenant(label="shared demo account", expires_at=None)
    db.session.add(tenant)
    db.session.flush()
    user = user_service.create_user(email, password, demo_docs.TRAVELLERS[0], is_demo=True, demo_tenant_id=tenant.id,
                                    ai_mode=AI_MODE_FULL if cfg["DEMO_ALLOW_EXTERNAL_AI"] else AI_MODE_OFF)
    _profile(user)
    seed_rome_trip(user)
    db.session.commit()
    return user, generated


def _profile(user: User) -> None:
    user.home_city = "Craiova"
    user.home_airport = "CRA"
    user.timezone = HOME_TZ
    user.preferences.interests = ["history", "food", "architecture", "walking"]
    user.preferences.pace = "balanced"


def seed_rome_trip(user: User) -> None:
    # The demo is seeded in the visitor's language; names of places and providers stay as they are.
    loc = locale_of(user)
    start = demo_start_date()
    end = start + timedelta(days=4)
    d1, d2, d3 = (start + timedelta(days=i) for i in range(1, 4))
    trip = trips.create_trip(user, tr("Rome long weekend", loc), start_date=start, end_date=end, destination="Rome",  # place names are data: they must match the bookings' cities
                             created_via="demo", lat=41.9028, lon=12.4964)
    trip.notes = tr("Demo trip: real places, airports and operators, but sample bookings with made-up references. Try the sample documents in the Inbox and ask the assistant about Saturday.", loc)
    from app.models import Traveller

    db.session.add(Traveller(trip_id=trip.id, full_name=demo_docs.TRAVELLERS[1]))

    flight_doc = _store_doc(user, trip.id, "Wizz Air sample e-ticket WZ7QRM.pdf", "application/pdf",
                            demo_docs.flight_confirmation(start))
    hotel_doc = _store_doc(user, trip.id, "Hotel Santa Maria sample confirmation.pdf", "application/pdf",
                           demo_docs.hotel_confirmation(start))
    hotel_update_doc = _store_doc(user, trip.id, "Hotel Santa Maria sample - updated booking.pdf", "application/pdf",
                                  demo_docs.hotel_update(start))
    museum_doc = _store_doc(user, trip.id, "Vatican Museums ticket VM-20931.pdf", "application/pdf",
                            demo_docs.museum_ticket(start))
    tour_doc = _store_doc(user, trip.id, "Trastevere walking tour sample screenshot.png", "image/png",
                          demo_docs.walking_tour_screenshot(start))
    dinner_doc = _store_doc(user, trip.id, "Da Enzo al 29 sample confirmation.eml", "message/rfc822",
                            demo_docs.restaurant_email(start, user.email))

    travellers = list(demo_docs.TRAVELLERS)
    common = {"status": "confirmed", "travellers": travellers}
    seeds = [
        (flight_doc, {"type": "flight", "title": tr("Flight {number} {route}", loc, number="W6 3501", route="CRA → FCO"), "provider_name": "Wizz Air",
                      "booking_reference": "WZ7QRM", "origin": "Craiova International Airport (CRA)", "destination": "Rome Fiumicino (FCO)",
                      "start_at": _at(start, "06:30", HOME_TZ), "start_tz": HOME_TZ,
                      "end_at": _at(start, "07:35", ROME_TZ), "end_tz": ROME_TZ, "city": "Craiova",
                      "lat": 44.3181, "lon": 23.8886, "end_city": "Rome", "end_lat": 41.8003, "end_lon": 12.2389,
                      "details": {"flight_number": "W6 3501", "airline": "Wizz Air", "seat": "14A, 14B",
                                  "terminal": "3", "origin_code": "CRA", "destination_code": "FCO",
                                  "baggage": "1 x 10kg cabin bag per passenger", "arrival_city": "Rome",
                                  "arrival_lat": 41.8003, "arrival_lon": 12.2389},
                      "price": 214.80, "currency": "EUR"}),
        (flight_doc, {"type": "flight", "title": tr("Flight {number} {route}", loc, number="W6 3502", route="FCO → CRA"), "provider_name": "Wizz Air",
                      "booking_reference": "WZ7QRM", "origin": "Rome Fiumicino (FCO)", "destination": "Craiova International Airport (CRA)",
                      "start_at": _at(end, "17:20", ROME_TZ), "start_tz": ROME_TZ,
                      "end_at": _at(end, "20:25", HOME_TZ), "end_tz": HOME_TZ, "city": "Rome",
                      "lat": 41.8003, "lon": 12.2389,
                      "details": {"flight_number": "W6 3502", "airline": "Wizz Air", "seat": "21C, 21D",
                                  "terminal": "3", "origin_code": "FCO", "destination_code": "CRA",
                                  "arrival_city": "Craiova", "arrival_lat": 44.3181, "arrival_lon": 23.8886}}),
        (hotel_doc, {"type": "hotel", "title": demo_docs.HOTEL, "provider_name": demo_docs.HOTEL,
                     "booking_reference": "HSM-58213", "start_at": _at(start, "15:00", ROME_TZ), "start_tz": ROME_TZ,
                     "end_at": _at(end, "11:00", ROME_TZ), "end_tz": ROME_TZ, "location_name": demo_docs.HOTEL,
                     "address": demo_docs.HOTEL_ADDRESS, "city": "Rome", "lat": 41.8896, "lon": 12.4690,
                     "price": 612.00, "currency": "EUR",
                     "cancellation_deadline": _at(start - timedelta(days=2), "23:59", ROME_TZ),
                     "cancellation_policy": tr("Free cancellation until 2 days before arrival, 23:59.", loc),
                     "details": {"room_type": "Superior Double, courtyard view", "guests": 2, "nights": 4,
                                 "check_in_from": "15:00", "check_out_until": "11:00"}}),
        (museum_doc, {"type": "museum", "title": tr("Vatican Museums & Sistine Chapel", loc), "provider_name": "Vatican Museums",
                      "booking_reference": "VM-20931", "start_at": _at(d1, "09:30", ROME_TZ), "start_tz": ROME_TZ,
                      "end_at": _at(d1, "12:30", ROME_TZ), "end_tz": ROME_TZ, "location_name": "Vatican Museums",
                      "address": "Viale Vaticano, 00165 Rome", "city": "Rome", "lat": 41.9065, "lon": 12.4536,
                      "price": 54.00, "currency": "EUR", "cancellation_policy": tr("Non-refundable.", loc),
                      "details": {"party_size": 2}}),
        (tour_doc, {"type": "tour", "title": tr("Trastevere Twilight Walking Tour", loc), "provider_name": "Local guide",
                    "booking_reference": "PLT-4471", "start_at": _at(d2, "17:30", ROME_TZ), "start_tz": ROME_TZ,
                    "end_at": _at(d2, "19:30", ROME_TZ), "end_tz": ROME_TZ, "location_name": "Piazza di Santa Maria in Trastevere",
                    "address": "Piazza di Santa Maria in Trastevere, Rome", "city": "Rome", "lat": 41.8896, "lon": 12.4695,
                    "price": 70.00, "currency": "EUR",
                    "cancellation_policy": tr("Free cancellation up to 24 hours before the tour", loc),
                    "cancellation_deadline": _at(d2 - timedelta(days=1), "17:30", ROME_TZ),
                    "details": {"party_size": 2, "meeting_point": "Piazza di Santa Maria in Trastevere"}}),
        (dinner_doc, {"type": "restaurant", "title": tr("Dinner at {place}", loc, place=demo_docs.RESTAURANT), "provider_name": demo_docs.RESTAURANT,
                      "booking_reference": "DE-1906", "start_at": _at(d2, "19:00", ROME_TZ), "start_tz": ROME_TZ,
                      "end_at": _at(d2, "21:00", ROME_TZ), "end_tz": ROME_TZ, "location_name": demo_docs.RESTAURANT,
                      "address": demo_docs.RESTAURANT_ADDRESS, "city": "Rome", "lat": 41.8879, "lon": 12.4748,
                      "details": {"party_size": 2}}),
    ]
    reservations = {}
    for doc, data in seeds:
        res = trips.reservation_from_data(user, {**common, **data}, trip=trip, source_document_id=doc.id,
                                          confidence=0.95, verification="user_confirmed", created_via="demo")
        trips.sync_events(res)
        reservations[data["booking_reference"] + data["title"][:10]] = res
        doc.trip_id = trip.id

    # An updated reservation, already applied, with its change history preserved.
    hotel = next(r for r in reservations.values() if r.type == "hotel")
    from app.models import ExtractedRecord, ReservationChange

    rec = ExtractedRecord(document_id=hotel_update_doc.id, user_id=user.id, index=0, record_type="hotel",
                          data={"type": "hotel", "booking_reference": "HSM-58213"}, confidence=0.9, status="accepted",
                          extractor={"provider": "demo", "path": "demo_seed"}, reservation_id=hotel.id,
                          matched_reservation_id=hotel.id, reviewed_at=utcnow())
    db.session.add(rec)
    db.session.flush()
    new_checkin = _at(start, "13:00", ROME_TZ)
    change = ReservationChange(
        reservation_id=hotel.id, user_id=user.id, source_document_id=hotel_update_doc.id, extracted_record_id=rec.id,
        changes={"start_at": {"old": hotel.start_at.isoformat(), "new": new_checkin},
                 "details.check_in_from": {"old": "15:00", "new": "13:00"}},
        summary=tr("{hotel}: early check-in from 13:00 (was 15:00)", loc, hotel=demo_docs.HOTEL), status="pending")
    db.session.add(change)
    db.session.flush()
    trips.apply_change(user, change, actor="user")

    # Free time and a pending suggestion.
    create_event(user, trip, {"title": tr("Free afternoon", loc), "type": "free_time", "status": "unbooked",
                              "start_local": f"{d3.isoformat()}T14:00", "end_local": f"{d3.isoformat()}T18:00",
                              "start_tz": ROME_TZ}, source="manual")
    create_event(user, trip, {"title": tr("Borghese Gallery Timed Entry", loc), "type": "museum", "status": "suggested",
                              "start_local": f"{d3.isoformat()}T10:00", "end_local": f"{d3.isoformat()}T12:00",
                              "start_tz": ROME_TZ, "location_name": "Galleria Borghese",
                              "address": "Piazzale Scipione Borghese 5, Rome", "lat": 41.9142, "lon": 12.4922,
                              "city": "Rome", "notes": tr("Suggested by Tandem: fits your free Sunday morning.", loc),
                              "details": {"suggested_activity": {"provider": "simulator",
                                                                 "provider_item_id": "sim-rome-003"}}},
                 source="assistant")
    trips.refresh_trip(trip, user)
    db.session.flush()
    check_and_notify(trip, user)

    # A realistic conversation produced by the offline assistant over the real seeded data.
    from app.services.agent import local_assistant
    from app.services.agent.tools import ToolContext
    from app.models import Message

    conv = Conversation(user_id=user.id, trip_id=trip.id, title=tr("What's on Saturday?", loc))
    db.session.add(conv)
    db.session.flush()
    question = tr("What do I have booked on {day}?", loc, day=weekday_name(d2, loc))
    ctx = ToolContext(user=user, conversation_id=conv.id, default_trip_id=trip.id)
    log: list = []
    answer = local_assistant.answer(user, ctx, question, log, reason="Demo conversation generated offline")
    db.session.add(Message(conversation_id=conv.id, role="user", content=question))
    db.session.add(Message(conversation_id=conv.id, role="assistant", content=answer, tool_calls=log,
                           provider="local", model="tandem-offline-v1",
                           created_at=utcnow() + timedelta(seconds=1)))
    db.session.flush()

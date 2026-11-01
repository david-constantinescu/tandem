"""Trip grouping, change detection, timezone handling and deterministic conflict detection."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.extensions import db
from app.models import Trip
from app.services import users as user_service
from app.services.demo import documents as D
from app.services.demo.seed import demo_start_date
from app.services.itinerary.conflicts import detect
from app.services.trips import grouping
from app.services.trips import service as trips
from app.utils.timeutil import iso, localize
from tests.conftest import upload


def _user():
    u = user_service.create_user("g@example.com", "password12345", "G", locale="en")
    u.home_city = "London"
    u.timezone = "Europe/London"
    db.session.flush()
    return u


def _data(type_, city, day, hhmm="10:00", tz="Europe/Rome", hours=2, ref=None, lat=None, lon=None, **extra):
    start, _ = localize(datetime.combine(day, datetime.strptime(hhmm, "%H:%M").time()), tz)
    return {"type": type_, "title": f"{type_} in {city}", "city": city, "start_at": iso(start), "start_tz": tz,
            "end_at": iso(start + timedelta(hours=hours)), "end_tz": tz, "booking_reference": ref,
            "status": "confirmed", "lat": lat, "lon": lon, **extra}


def _add(u, trip, data):
    r = trips.reservation_from_data(u, data, trip=trip)
    trips.sync_events(r)
    return r


def test_grouping_same_destination_and_dates(app):
    u = _user()
    day = date(2026, 11, 12)
    trip = trips.create_trip(u, "Rome", start_date=day, end_date=day + timedelta(days=4), destination="Rome")
    p = grouping.propose(u, _data("museum", "Rome", day + timedelta(days=1), lat=41.9, lon=12.45))
    assert p["action"] == "join" and p["trip_id"] == str(trip.id)


def test_similar_dates_but_different_city_creates_new_trip(app):
    u = _user()
    day = date(2026, 11, 12)
    trips.create_trip(u, "Rome", start_date=day, end_date=day + timedelta(days=4), destination="Rome")
    p = grouping.propose(u, _data("hotel", "Oslo", day + timedelta(days=1), tz="Europe/Oslo", lat=59.91, lon=10.75))
    assert p["action"] == "create" and p["new_trip"]["destination"] == "Oslo"
    assert "No destination match" in " ".join(p["reasons"])


def test_shared_booking_reference_joins_even_outside_dates(app):
    u = _user()
    day = date(2026, 11, 12)
    trip = trips.create_trip(u, "Rome", start_date=day, end_date=day + timedelta(days=4), destination="Rome")
    _add(u, trip, _data("flight", "London", day, ref="ABC123"))
    p = grouping.propose(u, _data("flight", "Milan", day + timedelta(days=20), ref="ABC123"))
    assert p["action"] == "join"


def test_return_flight_home_groups_by_departure_city(app):
    u = _user()
    day = date(2026, 11, 12)
    trip = trips.create_trip(u, "Rome", start_date=day, end_date=day + timedelta(days=4), destination="Rome")
    ret = _data("flight", "Rome", day + timedelta(days=4), "17:20", end_city="London")
    assert grouping.propose(u, ret)["trip_id"] == str(trip.id)


def test_multi_destination_trip(user_api):
    t = user_api.post("/api/v1/trips", json={"name": "Grand tour", "primary_destination": "London"}).get_json()["data"]
    for city in ("Paris", "Amsterdam"):
        t = user_api.post(f"/api/v1/trips/{t['id']}/destinations", json={"name": city}).get_json()["data"]
    assert [d["name"] for d in t["destinations"]] == ["London", "Paris", "Amsterdam"]


def test_manual_move_between_trips_is_reversible(user_api):
    a = user_api.post("/api/v1/trips", json={"name": "A"}).get_json()["data"]
    b = user_api.post("/api/v1/trips", json={"name": "B"}).get_json()["data"]
    r = user_api.post("/api/v1/reservations", json={"type": "museum", "title": "Louvre", "trip_id": a["id"],
                                                    "start_local": "2026-12-01T10:00", "start_tz": "Europe/Paris"}).get_json()["data"]
    user_api.post(f"/api/v1/reservations/{r['id']}/move", json={"trip_id": b["id"]})
    assert user_api.get(f"/api/v1/trips/{b['id']}/itinerary").get_json()["data"][0]["title"] == "Louvre"
    assert user_api.get(f"/api/v1/trips/{a['id']}/itinerary").get_json()["data"] == []
    user_api.post(f"/api/v1/reservations/{r['id']}/move", json={"trip_id": a["id"]})
    assert len(user_api.get(f"/api/v1/trips/{a['id']}/itinerary").get_json()["data"]) == 1


def test_updated_confirmation_detected_and_applied(user_api):
    start = demo_start_date()
    doc = upload(user_api, "hotel.pdf", D.hotel_confirmation(start), "application/pdf").get_json()["data"]["documents"][0]
    rec = user_api.get(f"/api/v1/inbox/{doc['id']}").get_json()["data"]["records"][0]
    accepted = user_api.post(f"/api/v1/inbox/{doc['id']}/review",
                             json={"decisions": [{"record_id": rec["id"], "decision": "accept"}]}).get_json()["data"]
    res_id = accepted["results"][0]["reservation_id"]
    upd = upload(user_api, "update.pdf", D.hotel_update(start), "application/pdf").get_json()["data"]["documents"][0]
    item = user_api.get(f"/api/v1/inbox/{upd['id']}").get_json()["data"]
    assert item["records"][0]["status"] == "change_detected"
    assert item["records"][0]["matched_reservation_id"] == res_id
    changes = user_api.get(f"/api/v1/reservations/{res_id}/changes").get_json()["data"]
    assert changes[0]["status"] == "pending" and "start_at" in changes[0]["changes"]
    before = user_api.get(f"/api/v1/reservations/{res_id}").get_json()["data"]["start_local"]
    assert before.startswith(f"{start.isoformat()}T15:00")
    user_api.post(f"/api/v1/reservations/changes/{changes[0]['id']}/apply")
    after = user_api.get(f"/api/v1/reservations/{res_id}").get_json()["data"]
    assert after["start_local"].startswith(f"{start.isoformat()}T13:00")
    assert after["details"]["check_in_from"] == "13:00"
    assert after["details"]["history"][0]["changes"]["start_at"]["old"].startswith(start.isoformat())
    assert user_api.get(f"/api/v1/inbox/{upd['id']}").get_json()["data"]["status"] == "processed"


def test_reupload_identical_reservation_is_not_a_change(user_api):
    start = demo_start_date()
    doc = upload(user_api, "t.pdf", D.museum_ticket(start), "application/pdf").get_json()["data"]["documents"][0]
    rec = user_api.get(f"/api/v1/inbox/{doc['id']}").get_json()["data"]["records"][0]
    user_api.post(f"/api/v1/inbox/{doc['id']}/review", json={"decisions": [{"record_id": rec["id"], "decision": "accept"}]})
    # Same content, different bytes (re-rendered) -> no duplicate file match, but nothing changed.
    text = "Admission ticket\nReservation code: VM-20931\nVisit date: " + (start + timedelta(days=1)).strftime("%d %B %Y") + \
           "\nEntry time: 09:30\nDuration: 3 hours\nMuseum: Vatican Museums & Sistine Chapel - timed entry\nTotal paid: EUR 54.00"
    d = user_api.post("/api/v1/inbox/paste", json={"text": text}).get_json()["data"]
    item = user_api.get(f"/api/v1/inbox/{d['id']}").get_json()["data"]
    assert item["status"] == "processed" and item["records"][0]["status"] == "rejected"


# --- Timezones ---------------------------------------------------------------------------
def test_dst_gap_and_fold():
    from app.utils.timeutil import localize as loc

    gap, notes = loc(datetime(2026, 3, 29, 2, 30), "Europe/Rome")  # clocks jump 02:00 -> 03:00
    assert notes and "does not exist" in notes[0]
    fold, notes = loc(datetime(2026, 10, 25, 2, 30), "Europe/Rome")  # 02:00-03:00 happens twice
    assert notes and "occurs twice" in notes[0]
    assert fold.isoformat() == "2026-10-25T00:30:00+00:00"
    normal, notes = loc(datetime(2026, 11, 12, 8, 5), "Europe/London")
    assert not notes and normal.isoformat() == "2026-11-12T08:05:00+00:00"


def test_flight_across_timezones_and_overnight(app):
    u = _user()
    day = date(2026, 11, 20)
    trip = trips.create_trip(u, "Tokyo", start_date=day, end_date=day + timedelta(days=5), destination="Tokyo")
    dep, _ = localize(datetime(2026, 11, 20, 21, 0), "Europe/London")
    arr, _ = localize(datetime(2026, 11, 21, 17, 0), "Asia/Tokyo")
    r = _add(u, trip, {"type": "flight", "title": "LHR-HND", "start_at": iso(dep), "start_tz": "Europe/London",
                       "end_at": iso(arr), "end_tz": "Asia/Tokyo", "city": "London", "end_city": "Tokyo",
                       "status": "confirmed"})
    assert (r.end_at - r.start_at) == timedelta(hours=11)
    from app.schemas.serializers import reservation_dict

    d = reservation_dict(r)
    assert d["start_local"].startswith("2026-11-20T21:00") and d["end_local"].startswith("2026-11-21T17:00")
    # The overnight flight covers the night of the 20th; no "missing accommodation" for it.
    hotel_start, _ = localize(datetime(2026, 11, 21, 18, 0), "Asia/Tokyo")
    _add(u, trip, {"type": "hotel", "title": "Hotel", "city": "Tokyo", "start_at": iso(hotel_start),
                   "start_tz": "Asia/Tokyo", "end_at": iso(hotel_start + timedelta(days=4, hours=-7)),
                   "end_tz": "Asia/Tokyo", "status": "confirmed", "address": "x",
                   "details": {"check_in_from": "15:00"}})
    trips.refresh_trip(trip, u)
    kinds = {c.type for c in detect(trip)}
    assert "missing_accommodation" not in kinds


# --- Conflicts ---------------------------------------------------------------------------
def test_overlap_and_tight_arrival_and_after_departure(app):
    u = _user()
    day = date(2026, 11, 12)
    trip = trips.create_trip(u, "Rome", start_date=day, end_date=day + timedelta(days=1), destination="Rome")
    arr, _ = localize(datetime(2026, 11, 12, 11, 40), "Europe/Rome")
    _add(u, trip, {"type": "flight", "title": "Inbound", "start_at": iso(arr - timedelta(hours=2, minutes=35)),
                   "start_tz": "Europe/London", "end_at": iso(arr), "end_tz": "Europe/Rome", "city": "London",
                   "end_city": "Rome", "status": "confirmed", "details": {"arrival_city": "Rome"}})
    _add(u, trip, _data("tour", "Rome", day, "12:00", hours=2))  # 20 min after landing
    _add(u, trip, _data("museum", "Rome", day, "13:30", hours=2))  # overlaps the tour
    dep, _ = localize(datetime(2026, 11, 13, 10, 0), "Europe/Rome")
    _add(u, trip, {"type": "flight", "title": "Outbound", "start_at": iso(dep), "start_tz": "Europe/Rome",
                   "end_at": iso(dep + timedelta(hours=2)), "end_tz": "Europe/London", "city": "Rome",
                   "end_city": "London", "status": "confirmed", "details": {"arrival_city": "London"}})
    _add(u, trip, _data("restaurant", "Rome", day + timedelta(days=1), "13:00"))  # after leaving Rome
    kinds = {c.type: c for c in detect(trip)}
    assert kinds["overlap"].severity == "critical"
    assert "tight_after_arrival" in kinds
    assert kinds["after_departure"].severity == "critical"


def test_impossible_sequence_uses_physical_lower_bound(app):
    u = _user()
    day = date(2026, 11, 12)
    trip = trips.create_trip(u, "Italy", start_date=day, end_date=day, destination="Rome")
    _add(u, trip, _data("museum", "Rome", day, "10:00", hours=1, lat=41.9, lon=12.5))
    _add(u, trip, _data("tour", "Milan", day, "11:30", hours=1, lat=45.46, lon=9.19))  # ~480 km in 30 min
    kinds = {c.type for c in detect(trip)}
    assert "impossible_sequence" in kinds and "missing_transport" in kinds


def test_suggestion_overlap_is_warning_and_unconfirmed_flagged(app):
    u = _user()
    day = date(2026, 11, 12)
    trip = trips.create_trip(u, "Rome", start_date=day, end_date=day, destination="Rome")
    _add(u, trip, _data("museum", "Rome", day, "10:00"))
    from app.services.itinerary.service import create_event

    create_event(u, trip, {"title": "Idea", "type": "activity", "status": "suggested", "start_local": "2026-11-12T11:00",
                           "end_local": "2026-11-12T12:30", "start_tz": "Europe/Rome"}, source="assistant")
    pending = _add(u, trip, {**_data("restaurant", "Rome", day, "20:00"), "status": "pending"})
    items = detect(trip)
    overlap = next(c for c in items if c.type == "overlap")
    assert overlap.severity == "warning"
    assert any(c.type == "unconfirmed" and str(pending.id) in c.reservation_ids for c in items)


def test_cancellation_deadline_warning(app):
    u = _user()
    day = date.today() + timedelta(days=5)
    trip = trips.create_trip(u, "Soon", start_date=day, end_date=day, destination="Rome")
    r = _add(u, trip, _data("tour", "Rome", day))
    from app.utils.timeutil import utcnow

    r.cancellation_deadline = utcnow() + timedelta(hours=20)
    assert any(c.type == "cancellation_deadline" for c in detect(trip))


def test_trip_bounds_follow_events(app):
    u = _user()
    trip = trips.create_trip(u, "Auto", destination="Rome")
    trip.created_via = "auto"
    _add(u, trip, _data("museum", "Rome", date(2026, 11, 13)))
    _add(u, trip, _data("tour", "Rome", date(2026, 11, 15)))
    trips.refresh_trip(trip, u)
    assert (trip.start_date, trip.end_date) == (date(2026, 11, 13), date(2026, 11, 15))
    assert db.session.get(Trip, trip.id).primary_destination == "Rome"

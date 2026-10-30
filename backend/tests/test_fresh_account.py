"""A brand-new account with no profile, going through the inbox exactly as the UI does."""
from __future__ import annotations

from app.services.demo import documents as D
from app.services.demo.seed import demo_start_date
from tests.conftest import upload


def _accept_one_by_one(api, doc_id):
    item = api.get(f"/api/v1/inbox/{doc_id}").get_json()["data"]
    for rec in item["records"]:
        # The UI sends no trip choice when the user keeps Tandem's suggestion.
        r = api.post(f"/api/v1/inbox/{doc_id}/review", json={"decisions": [{"record_id": rec["id"], "decision": "accept"}]})
        assert r.status_code == 200, r.get_json()


def test_fresh_account_builds_one_trip(user_api):
    api = user_api
    start = demo_start_date()
    flight = upload(api, "flight.pdf", D.flight_confirmation(start), "application/pdf").get_json()["data"]["documents"][0]
    hotel = upload(api, "hotel.pdf", D.hotel_confirmation(start), "application/pdf").get_json()["data"]["documents"][0]
    # Both were analysed before any trip existed, so both initially propose a new trip.
    assert api.get(f"/api/v1/inbox/{hotel['id']}").get_json()["data"]["records"][0]["grouping"]["action"] == "create"
    _accept_one_by_one(api, flight["id"])
    # After the first acceptance, pending sibling proposals are refreshed to join the new trip.
    hotel_rec = api.get(f"/api/v1/inbox/{hotel['id']}").get_json()["data"]["records"][0]
    assert hotel_rec["grouping"]["action"] == "join"
    _accept_one_by_one(api, hotel["id"])
    trips = api.get("/api/v1/trips").get_json()["data"]
    assert len(trips) == 1, [t["name"] for t in trips]
    assert [d["name"] for d in trips[0]["destinations"]] == ["Rome"]
    assert trips[0]["stats"]["reservations"] == 3


def test_explicit_new_trip_still_creates_one(user_api):
    api = user_api
    doc = upload(api, "museum.pdf", D.museum_ticket(demo_start_date()), "application/pdf").get_json()["data"]["documents"][0]
    rec = api.get(f"/api/v1/inbox/{doc['id']}").get_json()["data"]["records"][0]
    api.post(f"/api/v1/inbox/{doc['id']}/review", json={"decisions": [
        {"record_id": rec["id"], "decision": "accept", "new_trip_name": "Art week"}]})
    assert [t["name"] for t in api.get("/api/v1/trips").get_json()["data"]] == ["Art week"]

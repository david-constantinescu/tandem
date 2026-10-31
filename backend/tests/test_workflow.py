"""End-to-end workflow (spec §29) through the HTTP API: document → extraction → review → reservation →
trip → itinerary → conflicts → assistant → activity search → proposal → approval → verified result."""
from __future__ import annotations

from app.services.demo import documents as D
from app.services.demo.seed import demo_start_date
from tests.conftest import upload


def test_full_workflow_with_local_parser(user_api):
    api = user_api
    start = demo_start_date()
    api.patch("/api/v1/settings/profile", json={"home_city": "Craiova", "timezone": "Europe/Bucharest"})

    # 1-6. Upload a flight confirmation; AI is off by default so the local parser runs.
    r = upload(api, "flight.pdf", D.flight_confirmation(start), "application/pdf")
    assert r.status_code == 201, r.get_json()
    doc_id = r.get_json()["data"]["documents"][0]["id"]
    item = api.get(f"/api/v1/inbox/{doc_id}").get_json()["data"]
    assert item["status"] == "awaiting_review"
    assert item["extraction_method"]["path"] == "local_parser"
    records = item["records"]
    assert len(records) == 2
    out = records[0]
    assert out["data"]["booking_reference"] == "WZ7QRM"
    assert out["data"]["start_tz"] == "Europe/Bucharest" and out["data"]["end_tz"] == "Europe/Rome"
    fields = {f["field"]: f for f in out["fields"]}
    assert fields["booking_reference"]["verification"] == "evidence_found"
    assert fields["start_local"]["verification"] == "evidence_found"
    assert out["grouping"]["action"] == "create"

    # 7-10. Review (with a correction) and accept both segments → trip + reservations + itinerary.
    r = api.post(f"/api/v1/inbox/{doc_id}/review", json={"decisions": [
        {"record_id": records[0]["id"], "decision": "accept", "corrections": {"seat": "15A"}},
        {"record_id": records[1]["id"], "decision": "accept"},
    ]})
    assert r.status_code == 200, r.get_json()
    results = r.get_json()["data"]["results"]
    trip_id = results[0]["trip_id"]
    assert trip_id and results[1]["trip_id"] == trip_id, "return flight should join the same trip"
    trip = api.get(f"/api/v1/trips/{trip_id}").get_json()["data"]
    assert trip["start_date"] == start.isoformat()
    assert any(d["name"] == "Rome" for d in trip["destinations"])
    res = api.get(f"/api/v1/trips/{trip_id}/reservations").get_json()["data"]
    assert {x["details"].get("flight_number") for x in res} == {"W6 3501", "W6 3502"}
    assert next(x for x in res if x["details"]["flight_number"] == "W6 3501")["details"]["seat"] == "15A"

    # Hotel joins the same trip automatically by destination + dates.
    r = upload(api, "hotel.pdf", D.hotel_confirmation(start), "application/pdf")
    hotel_doc = r.get_json()["data"]["documents"][0]["id"]
    rec = api.get(f"/api/v1/inbox/{hotel_doc}").get_json()["data"]["records"][0]
    assert rec["grouping"]["action"] == "join" and rec["grouping"]["trip_id"] == trip_id
    api.post(f"/api/v1/inbox/{hotel_doc}/review", json={"decisions": [{"record_id": rec["id"], "decision": "accept"}]})

    # Museum + overlapping tour → deterministic conflict.
    for name, data, mime in (("museum.pdf", D.museum_ticket(start), "application/pdf"),
                             ("colosseum.pdf", D.sample_colosseum_ticket(start), "application/pdf")):
        d = upload(api, name, data, mime).get_json()["data"]["documents"][0]["id"]
        rec = api.get(f"/api/v1/inbox/{d}").get_json()["data"]["records"][0]
        api.post(f"/api/v1/inbox/{d}/review", json={"decisions": [{"record_id": rec["id"], "decision": "accept"}]})
    itinerary = api.get(f"/api/v1/trips/{trip_id}/itinerary").get_json()["data"]
    assert len(itinerary) == 6  # 2 flights, check-in, check-out, museum, tour
    conflicts = api.get(f"/api/v1/trips/{trip_id}/conflicts").get_json()["data"]
    overlap = [c for c in conflicts if c["type"] == "overlap"]
    assert overlap and overlap[0]["severity"] == "critical"
    notes = api.get("/api/v1/notifications").get_json()["data"]
    assert any(n["type"] == "conflict_detected" for n in notes)

    # 12-13. Assistant (offline mode, since AI is off) answers from real data.
    conv = api.post("/api/v1/assistant/conversations", json={"trip_id": trip_id}).get_json()["data"]
    day = (start.replace(day=start.day + 1)).strftime("%d %B %Y")
    reply = api.post(f"/api/v1/assistant/conversations/{conv['id']}/messages",
                     json={"content": f"What do I have booked on {day}?"}).get_json()["data"]["reply"]
    assert reply["provider"] == "local"
    assert "Vatican Museums" in reply["content"] and "Colosseum" in reply["content"]
    conflicts_reply = api.post(f"/api/v1/assistant/conversations/{conv['id']}/messages",
                               json={"content": "Are there any conflicts?"}).get_json()["data"]["reply"]
    assert "overlaps" in conflicts_reply["content"]

    # 14. Non-demo accounts never see the simulator; partner providers report honest states.
    providers = api.get("/api/v1/activities/providers").get_json()["data"]
    keys = {p["key"]: p["state"] for p in providers}
    assert "simulator" not in keys
    assert keys["booking_com"] == "awaiting_partner_approval"
    assert keys["expedia"] == "awaiting_partner_approval"


def test_full_booking_workflow_in_demo(api):
    api.demo()
    trips = api.get("/api/v1/trips").get_json()["data"]
    assert len(trips) == 1
    trip = trips[0]
    start = trip["start_date"]
    # Search simulated activities with itinerary fit on the free Sunday.
    from datetime import date, timedelta

    sunday = (date.fromisoformat(start) + timedelta(days=3)).isoformat()
    r = api.post("/api/v1/activities/search", json={"trip_id": trip["id"], "date_from": sunday, "date_to": sunday,
                                                    "categories": ["workshops"]})
    data = r.get_json()["data"]
    assert "simulator" in [p["provider"] for p in data["providers"]]
    workshop = data["results"][0]
    assert workshop["simulated"] is True and workshop["availability_checked"] is True
    fitting = workshop["fits"]["slots"]
    assert fitting, "pasta workshop should fit the free afternoon"
    slot = next(s for s in fitting if s["remaining"] >= 2)

    # 16. Proposal (live quote) — nothing booked yet.
    r = api.post("/api/v1/activities/proposals", json={"provider": "simulator", "provider_item_id": workshop["provider_item_id"],
                                                      "date": slot["date"], "time": slot["time"], "participants": 2,
                                                      "trip_id": trip["id"]})
    assert r.status_code == 201, r.get_json()
    action = r.get_json()["data"]
    assert action["status"] == "awaiting_approval" and action["external"] is True
    assert action["cost"] == workshop["price"] * 2

    # Approval is bound to the exact payload.
    bad = api.post(f"/api/v1/approvals/{action['id']}/approve", json={"payload_hash": "0" * 64})
    assert bad.status_code == 409
    # 17-20. Approve → executed via provider, verified by read-back, reservation + itinerary updated.
    r = api.post(f"/api/v1/approvals/{action['id']}/approve", json={"payload_hash": action["payload_hash"]})
    assert r.status_code == 200, r.get_json()
    done = r.get_json()["data"]
    assert done["status"] == "completed", done
    assert done["result"]["provider_booking_id"].startswith("SIM-")
    assert done["result"]["simulated"] is True and done["result"]["verified_at"]
    res = api.get(f"/api/v1/trips/{trip['id']}/reservations").get_json()["data"]
    booked = next(x for x in res if x["booking_reference"] == done["result"]["provider_booking_id"])
    assert booked["status"] == "confirmed" and booked["verification"] == "verified"
    itinerary = api.get(f"/api/v1/trips/{trip['id']}/itinerary").get_json()["data"]
    assert any(e["reservation_id"] == booked["id"] for e in itinerary)
    # Approving again is refused (no double booking).
    again = api.post(f"/api/v1/approvals/{action['id']}/approve", json={"payload_hash": action["payload_hash"]})
    assert again.status_code == 409
    # 21. History is visible.
    detail = api.get(f"/api/v1/approvals/{action['id']}").get_json()["data"]
    assert [d["decision"] for d in detail["decisions"]] == ["approved"]

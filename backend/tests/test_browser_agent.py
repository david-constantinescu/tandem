"""Browser agent: site policy, guards, and the full simulated purchase through Tandem's demo websites."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import AgentAction, BrowserTask
from app.services.browser.policy import (
    detect_challenge,
    detect_payment_page,
    host_allowed,
    is_sensitive_field,
)
from app.services.browser.sites import ALL_SITES, get_site, policy_for


def _trip(api):
    return api.get("/api/v1/trips").get_json()["data"][0]


def test_registry_defaults_are_link_only(app):
    real = [s for s in ALL_SITES.values() if not s.simulated]
    assert len(real) >= 35
    assert {s.category for s in real} >= {"train", "bus", "flight", "museum", "gallery", "attraction"}
    assert all(policy_for(s) == "link_only" for s in real)
    assert policy_for(get_site("demo_rail")) == "simulated"


def test_operator_allow_list_but_never_forbidden_sites(app, monkeypatch):
    monkeypatch.setitem(app.config, "BROWSER_ASSIST_SITES", "flixbus,ryanair")
    assert policy_for(get_site("flixbus")) == "assisted"
    assert policy_for(get_site("ryanair")) == "link_only"  # site terms prohibit automation


def test_guards():
    rail = get_site("trenitalia")
    assert host_allowed(rail, "https://www.trenitalia.com/en/search")
    assert not host_allowed(rail, "https://evil.example.com/trenitalia.com")
    assert not host_allowed(rail, "http://www.trenitalia.com/")  # https only
    assert is_sensitive_field({"type": "password"})
    assert is_sensitive_field({"autocomplete": "cc-number"})
    assert is_sensitive_field({"name": "cvc"}) and is_sensitive_field({"label": "Passport number"})
    assert not is_sensitive_field({"name": "origin", "label": "From"})
    assert detect_challenge('<iframe src="https://www.google.com/recaptcha/api2/anchor">') == "recaptcha"
    assert detect_challenge("<div class='cf-turnstile'></div>") == "turnstile"
    assert detect_challenge("Pardon Our Interruption") == "akamai"
    assert detect_challenge("Book trains across Italy") is None
    assert detect_payment_page([{"autocomplete": "cc-number", "name": "card"}])


def test_link_only_site_hands_off_without_automation(api):
    api.demo()
    r = api.post("/api/v1/browser/tasks", json={"site": "ryanair", "origin": "STN", "destination": "CIA",
                                                "date": "2026-11-20"})
    t = r.get_json()["data"]
    assert t["state"] == "requires_manual" and t["engine"] == "none"
    assert t["handoff_url"] == "https://www.ryanair.com/" and "prohibit" in t["stop_reason"]
    t2 = api.post("/api/v1/browser/tasks", json={"site": "flixbus", "origin": "Rome", "destination": "Naples",
                                                 "date": "2026-11-20"}).get_json()["data"]
    assert t2["state"] == "requires_manual" and "link-only" in t2["stop_reason"]


def test_full_simulated_purchase_by_the_agent(api):
    api.demo()
    trip = _trip(api)
    day = (date.fromisoformat(trip["start_date"]) + timedelta(days=3)).isoformat()  # Sunday, free afternoon
    r = api.post("/api/v1/browser/tasks", json={"site": "demo_rail", "origin": "Rome", "destination": "Florence",
                                                "date": day, "time": "14:00", "adults": 2, "trip_id": trip["id"]})
    assert r.status_code == 201, r.get_json()
    task = r.get_json()["data"]
    assert task["state"] == "awaiting_approval", task
    assert [s["action"] for s in task["log"]][:3] == ["open", "search", "select"]
    assert task["result"]["selected"]["depart"] >= "14:00"
    action = api.get(f"/api/v1/approvals/{task['action_id']}").get_json()["data"]
    assert action["action_type"] == "browser_checkout" and action["status"] == "awaiting_approval"
    assert action["payload"]["travellers"] == ["Andrei Popescu", "Ioana Marinescu"]
    # Nothing typed into the site yet: the approval comes first.
    assert not any(s["action"] == "details" for s in task["log"])
    first = api.post(f"/api/v1/approvals/{action['id']}/approve", json={"payload_hash": action["payload_hash"]}).get_json()["data"]
    assert first["status"] == "completed" and first["result"]["stage"] == "details_entered", first
    # Names are in, but it stopped on the payment page and asks again before paying.
    task = api.get(f"/api/v1/browser/tasks/{task['id']}").get_json()["data"]
    assert task["state"] == "awaiting_approval" and [s["action"] for s in task["log"]][-2:] == ["details", "awaiting_payment"]
    assert not any(s["action"] == "pay" for s in task["log"])
    pay = api.get(f"/api/v1/approvals/{task['action_id']}").get_json()["data"]
    assert pay["action_type"] == "browser_payment" and float(pay["cost"]) == float(action["cost"])
    done = api.post(f"/api/v1/approvals/{pay['id']}/approve", json={"payload_hash": pay["payload_hash"]}).get_json()["data"]
    assert done["status"] == "completed", done
    assert done["result"]["provider_booking_id"].startswith("FD-")
    task = api.get(f"/api/v1/browser/tasks/{task['id']}").get_json()["data"]
    assert task["state"] == "completed"
    assert [s["action"] for s in task["log"]][-3:] == ["resume", "pay", "done"]
    res = api.get(f"/api/v1/trips/{trip['id']}/reservations").get_json()["data"]
    booked = next(x for x in res if x["booking_reference"] == done["result"]["provider_booking_id"])
    assert booked["type"] == "train" and booked["verification"] == "verified" and booked["start_tz"] == "Europe/Rome"
    assert booked["travellers"] == ["Andrei Popescu", "Ioana Marinescu"]
    assert booked["start_local"].startswith(f"{day}T{task['result']['selected']['depart']}")


def test_museum_purchase_and_price_change_protection(app, api):
    api.demo()
    trip = _trip(api)
    day = (date.fromisoformat(trip["start_date"]) + timedelta(days=3)).isoformat()
    task = api.post("/api/v1/browser/tasks", json={"site": "demo_museum", "venue": "Galleria Demo", "date": day,
                                                   "adults": 1, "trip_id": trip["id"]}).get_json()["data"]
    assert task["state"] == "awaiting_approval", task
    action = api.get(f"/api/v1/approvals/{task['action_id']}").get_json()["data"]
    assert "Galleria Demo d'Arte Moderna" in action["title"]
    # The approved amount no longer matches what the site charges -> the agent stops before paying.
    row = db.session.get(AgentAction, __import__("uuid").UUID(action["id"]))
    payload = dict(row.payload)
    payload["total"] = payload["total"] + 1
    from app.services.agent.approvals import payload_hash

    row.payload, row.payload_hash = payload, payload_hash(payload)
    db.session.commit()
    done = api.post(f"/api/v1/approvals/{action['id']}/approve", json={"payload_hash": row.payload_hash}).get_json()["data"]
    assert done["status"] == "failed" and "Nothing was paid" in done["error"]
    bt = db.session.get(BrowserTask, __import__("uuid").UUID(task["id"]))
    assert bt.state == "failed" and not any(s["action"] == "pay" for s in bt.log)


def test_sensitive_fields_are_never_filled(app):
    from app.services.browser.engines import HttpEngine
    from app.services.browser.policy import PolicyViolation

    eng = HttpEngine(get_site("demo_rail"))
    snap = eng.goto("/demo-sites/rail/")
    snap.elements.append({"id": "x1", "tag": "input", "type": "password", "name": "pw", "form": 0, "sensitive": True})
    with pytest.raises(PolicyViolation):
        eng.fill("x1", "secret")
    with pytest.raises(PolicyViolation):
        eng.goto("/demo-sites/coach/")  # another site's pages are off the allow-list
    eng.close()


def test_sites_endpoint_and_cancel(api):
    api.demo()
    sites = api.get("/api/v1/browser/sites").get_json()
    assert sites["meta"]["browser_worker"] is False
    by_key = {s["key"]: s for s in sites["data"]}
    assert by_key["demo_rail"]["agent_can"]["enter_traveller_details"] is True
    assert by_key["louvre"]["policy"] == "link_only" and by_key["louvre"]["agent_can"]["payment"] == "user_completes_on_site"
    trip = _trip(api)
    day = (date.fromisoformat(trip["start_date"]) + timedelta(days=1)).isoformat()
    t = api.post("/api/v1/browser/tasks", json={"site": "demo_coach", "origin": "Rome", "destination": "Naples",
                                                "date": day, "adults": 1}).get_json()["data"]
    assert t["state"] == "awaiting_approval"
    c = api.post(f"/api/v1/browser/tasks/{t['id']}/cancel").get_json()["data"]
    assert c["state"] == "cancelled"
    assert api.get(f"/api/v1/approvals/{t['action_id']}").get_json()["data"]["status"] == "cancelled"


def test_offline_assistant_plans_real_journeys(api):
    api.demo()
    trip = _trip(api)
    conv = api.post("/api/v1/assistant/conversations", json={"trip_id": trip["id"]}).get_json()["data"]
    reply = api.post(f"/api/v1/assistant/conversations/{conv['id']}/messages",
                     json={"content": "Book a train from Rome to Florence on Sunday"}).get_json()["data"]
    msg = reply["reply"]
    # Real websites, route filled in where possible; nothing is bought and no simulated task starts.
    assert "google.com/maps/dir" in msg["content"] and "trenitalia.com" in msg["content"]
    assert not msg["action_ids"]


def test_offline_assistant_books_via_simulated_site(api):
    api.demo()
    trip = _trip(api)
    conv = api.post("/api/v1/assistant/conversations", json={"trip_id": trip["id"]}).get_json()["data"]
    reply = api.post(f"/api/v1/assistant/conversations/{conv['id']}/messages",
                     json={"content": "Practice run: book a train from Rome to Florence on Sunday for 2 people"}).get_json()["data"]
    msg = reply["reply"]
    assert msg["provider"] == "local" and "approve" in msg["content"].lower()
    assert msg["action_ids"], msg
    action = reply["actions"][msg["action_ids"][0]]
    assert action["action_type"] == "browser_checkout" and action["status"] == "awaiting_approval"
    assert [t["name"] for t in msg["tool_calls"]][-1] == "start_website_task"


def test_country_domain_matching_is_strict():
    af = get_site("airfrance")
    assert host_allowed(af, "https://wwws.airfrance.ro/")
    assert host_allowed(af, "https://www.airfrance.co.uk/")
    assert not host_allowed(af, "https://airfrance.evil.com/")
    assert not host_allowed(af, "https://notairfrance.ro/")
    assert host_allowed(get_site("megabus"), "https://www.megabus.co.uk/")


def test_buying_a_wizz_air_flight_hands_off_and_the_practice_airline_goes_to_payment(api):
    api.demo()
    trip = _trip(api)
    day = trip["start_date"]
    real = api.post("/api/v1/browser/tasks", json={"site": "Wizz Air", "origin": "Craiova", "destination": "Roma",
                                                   "date": day, "adults": 2, "trip_id": trip["id"]}).get_json()["data"]
    assert real["state"] == "requires_manual"
    assert real["handoff_url"] == f"https://wizzair.com/en-gb/booking/select-flight/CRA/FCO/{day}/null/2/0/0/null"
    assert not real.get("action_id")  # nothing to approve: a real site is never driven by the agent

    task = api.post("/api/v1/browser/tasks", json={"site": "demo_air", "origin": "Craiova", "destination": "Roma",
                                                   "date": day, "adults": 2, "trip_id": trip["id"]}).get_json()["data"]
    assert task["state"] == "awaiting_approval", task
    details = api.get(f"/api/v1/approvals/{task['action_id']}").get_json()["data"]
    assert details["action_type"] == "browser_checkout"
    first = api.post(f"/api/v1/approvals/{details['id']}/approve", json={"payload_hash": details["payload_hash"]}).get_json()["data"]
    pay = api.get(f"/api/v1/approvals/{first['result']['payment_action_id']}").get_json()["data"]
    assert pay["action_type"] == "browser_payment" and pay["status"] == "awaiting_approval"
    # Declining the payment leaves nothing booked.
    rejected = api.post(f"/api/v1/approvals/{pay['id']}/reject", json={}).get_json()["data"]
    assert rejected["status"] in ("rejected", "declined", "cancelled")
    bt = api.get(f"/api/v1/browser/tasks/{task['id']}").get_json()["data"]
    assert not any(s["action"] == "pay" for s in bt["log"])

    again = api.post("/api/v1/browser/tasks", json={"site": "demo_air", "origin": "Craiova", "destination": "Roma",
                                                    "date": day, "adults": 2, "trip_id": trip["id"]}).get_json()["data"]
    d = api.get(f"/api/v1/approvals/{again['action_id']}").get_json()["data"]
    first = api.post(f"/api/v1/approvals/{d['id']}/approve", json={"payload_hash": d["payload_hash"]}).get_json()["data"]
    pay = api.get(f"/api/v1/approvals/{first['result']['payment_action_id']}").get_json()["data"]
    done = api.post(f"/api/v1/approvals/{pay['id']}/approve", json={"payload_hash": pay["payload_hash"]}).get_json()["data"]
    assert done["status"] == "completed", done
    res = api.get(f"/api/v1/trips/{trip['id']}/reservations").get_json()["data"]
    booked = next(x for x in res if x["booking_reference"] == done["result"]["provider_booking_id"])
    assert booked["type"] == "flight" and booked["travellers"] == ["Andrei Popescu", "Ioana Marinescu"]

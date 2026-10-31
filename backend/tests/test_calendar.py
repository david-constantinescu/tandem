"""Calendar export: RFC 5545 formatting, the per-trip download and the private subscription feed."""
from __future__ import annotations

from app.services.calendar_ics import escape, fold


def _physical_lines(body: str) -> list[str]:
    assert body.endswith("\r\n")
    return body[:-2].split("\r\n")


def _unfold(body: str) -> str:
    return body.replace("\r\n ", "")


def _first_trip(api) -> dict:
    trips = api.get("/api/v1/trips").get_json()["data"]
    return next(t for t in trips if t["stats"]["reservations"])


def test_escape_and_fold():
    assert escape("a,b;c\\d\nnext") == "a\\,b\\;c\\\\d\\nnext"
    line = "SUMMARY:" + "Café, Colosseo → Fontana di Trevi; " * 6
    folded = fold(line)
    assert all(len(part.encode()) <= 75 for part in folded.split("\r\n"))
    assert all(part.startswith(" ") for part in folded.split("\r\n")[1:])
    assert folded.replace("\r\n ", "") == line
    assert fold("SHORT:line") == "SHORT:line"


def test_trip_download_is_valid_and_private(api):
    api.demo()
    trip = _first_trip(api)
    r = api.get(f"/api/v1/calendar/trips/{trip['id']}.ics")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("text/calendar")
    body = r.get_data(as_text=True)
    lines = _physical_lines(body)
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-1] == "END:VCALENDAR"
    assert "VERSION:2.0" in lines and any(x.startswith("PRODID:") for x in lines)
    assert all(len(x.encode()) <= 75 for x in lines)
    text = _unfold(body)
    assert text.count("BEGIN:VEVENT") == text.count("END:VEVENT") > 0
    assert all(x.endswith("Z") for x in text.split("\r\n") if x.startswith(("DTSTART:", "DTEND:", "DTSTAMP:")))
    # Booking references and traveller names never leave Tandem in calendar files.
    reservations = api.get(f"/api/v1/trips/{trip['id']}/reservations").get_json()["data"]
    refs = [x["booking_reference"] for x in reservations if x.get("booking_reference")]
    assert refs
    for ref in refs:
        assert ref not in text
    me = api.get("/api/v1/auth/me").get_json()["data"]["user"]
    assert me["display_name"] not in text


def test_trip_download_requires_owner(api, other_api, app):
    api.demo()
    trip = _first_trip(api)
    anonymous = app.test_client()
    assert anonymous.get(f"/api/v1/calendar/trips/{trip['id']}.ics").status_code == 401
    other_api.register(email="someone@example.com")
    assert other_api.get(f"/api/v1/calendar/trips/{trip['id']}.ics").status_code == 404


def test_subscription_lifecycle(api, app):
    api.demo()
    assert api.get("/api/v1/calendar/subscription").get_json()["data"]["active"] is False
    sub = api.post("/api/v1/calendar/subscription").get_json()["data"]
    assert sub["active"] and sub["webcal_url"].startswith("webcal://")
    path = sub["url"].split("://", 1)[1].split("/", 1)[1]
    anonymous = app.test_client()
    feed = anonymous.get(f"/{path}")
    assert feed.status_code == 200 and "BEGIN:VEVENT" in feed.get_data(as_text=True)
    # The link survives a page reload, and resetting it revokes the old one.
    assert api.get("/api/v1/calendar/subscription").get_json()["data"]["url"] == sub["url"]
    new = api.post("/api/v1/calendar/subscription").get_json()["data"]
    new_path = new["url"].split("://", 1)[1].split("/", 1)[1]
    assert anonymous.get(f"/{path}").status_code == 404
    assert anonymous.get(f"/{new_path}").status_code == 200
    assert api.delete("/api/v1/calendar/subscription").get_json()["data"]["active"] is False
    assert anonymous.get(f"/{new_path}").status_code == 404
    assert anonymous.get("/api/v1/calendar/feed/not-a-real-token.ics").status_code == 404


def test_subscription_changes_need_csrf(api, app):
    api.demo()
    api.csrf = None
    assert api.post("/api/v1/calendar/subscription").status_code in (400, 403)


def test_feed_only_contains_the_owners_trips(api, other_api, app):
    api.demo()
    other_api.register(email="other@example.com")
    t = other_api.post("/api/v1/trips", json={"name": "Private trip"}).get_json()["data"]
    r = other_api.post("/api/v1/itinerary/events", json={
        "trip_id": t["id"], "title": "Only mine dinner", "type": "restaurant", "start_local": "2030-05-01T20:00",
        "start_tz": "Europe/Paris", "city": "Paris"})
    assert r.status_code == 201, r.get_json()
    other_feed = other_api.post("/api/v1/calendar/subscription").get_json()["data"]["url"]
    mine = api.post("/api/v1/calendar/subscription").get_json()["data"]["url"]
    anonymous = app.test_client()
    mine_body = anonymous.get("/" + mine.split("://", 1)[1].split("/", 1)[1]).get_data(as_text=True)
    theirs_body = anonymous.get("/" + other_feed.split("://", 1)[1].split("/", 1)[1]).get_data(as_text=True)
    assert "Only mine dinner" not in _unfold(mine_body)
    assert "Only mine dinner" in _unfold(theirs_body)
    assert "Europe/Paris" in _unfold(theirs_body)  # the local time at the destination is spelled out

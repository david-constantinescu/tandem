"""Tandem writes first (rain on an outdoor plan, a strike on a travel day, a clash), uploads land in the chat, and
travel emails come in from Gmail on their own."""
from __future__ import annotations

from datetime import date, timedelta

from app.extensions import db
from app.models import Conversation, Message, Trip, User
from app.services.agent import proactive
from app.services.demo import documents as D
from tests.conftest import upload


def _demo(api):
    api.demo()
    user = db.session.execute(db.select(User).where(User.is_demo.is_(True)).order_by(User.created_at.desc())).scalars().first()
    trip = db.session.execute(db.select(Trip).where(Trip.user_id == user.id)).scalars().first()
    return user, trip


def _updates(user):
    conv = db.session.execute(db.select(Conversation).where(Conversation.user_id == user.id, Conversation.kind == "updates")).scalar_one()
    return conv, db.session.execute(db.select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)).scalars().all()


def test_a_new_demo_opens_with_tandem_pointing_out_the_clash(api):
    user, trip = _demo(api)
    conv, msgs = _updates(user)
    assert conv.trip_id == trip.id and msgs and msgs[0].role == "assistant"
    clash = msgs[0]
    assert "Trastevere" in clash.content
    assert [r["options"] for r in clash.references if r["type"] == "choices"][0][0]
    listed = api.get("/api/v1/assistant/conversations").get_json()["data"]
    assert listed[0]["kind"] == "updates"  # the newest thing to read


def test_rain_on_an_outdoor_plan_prompts_a_message_once(api, monkeypatch):
    from app.services.context import weather

    user, trip = _demo(api)
    saturday = (trip.start_date + timedelta(days=2)).isoformat()
    monkeypatch.setattr(weather, "for_trip", lambda t, day=None: {"available": True, "days": [
        {"date": saturday, "condition": "rain", "temp_max": 14, "temp_min": 9, "precip_probability": 85, "precip_mm": 9,
         "wind_kmh": 12, "wet_hours": ["17:00", "18:00"], "outdoor_ok": False}]})
    assert proactive.check_user(user, force=True) >= 1
    _, msgs = _updates(user)
    rain = [m for m in msgs if "85%" in m.content]
    assert len(rain) == 1 and "17:00" in rain[0].content
    assert proactive.check_user(user, force=True) == 0  # never the same news twice
    assert proactive.check_user(user) == 0  # and not more often than every few hours


def test_a_strike_on_a_travel_day_prompts_a_message(api, monkeypatch):
    from app.services.context import news

    user, trip = _demo(api)
    first = trip.start_date.isoformat()
    monkeypatch.setattr(news, "for_trip", lambda t, topic=None, day=None: {"available": True, "items": [
        {"title": "Sciopero dei trasporti a Roma", "url": "https://www.romatoday.it/sciopero", "source": "RomaToday",
         "published": None, "kind": "strike", "mentions_dates": [first]},
        {"title": "Old news", "url": "https://example.org/x", "source": "X", "published": None, "kind": "strike", "mentions_dates": []}]})
    proactive.check_user(user, force=True)
    _, msgs = _updates(user)
    assert any("RomaToday" in m.content and first in m.content for m in msgs)
    assert not any("Old news" in m.content for m in msgs)


def test_check_in_endpoint(api):
    api.demo()
    r = api.post("/api/v1/assistant/check-in", json={}).get_json()["data"]
    assert r["updates_conversation_id"]


def test_uploads_land_in_the_chat_with_what_was_read(api):
    user, trip = _demo(api)
    conv = api.post("/api/v1/assistant/conversations", json={"trip_id": str(trip.id)}).get_json()["data"]
    r = upload(api, "colosseum.pdf", D.sample_colosseum_ticket(trip.start_date), "application/pdf")
    doc_id = r.get_json()["data"]["documents"][0]["id"]
    payload = api.post(f"/api/v1/assistant/conversations/{conv['id']}/attachments", json={"document_ids": [doc_id]}).get_json()["data"]
    user_msg, reply = payload["messages"][-2], payload["messages"][-1]
    assert user_msg["role"] == "user" and "colosseum.pdf" in user_msg["content"]
    assert reply["role"] == "assistant" and "Colosseum" in reply["content"]
    assert any(x["type"] == "document" and x["id"] == doc_id for x in reply["references"])
    other = api.post(f"/api/v1/assistant/conversations/{conv['id']}/attachments", json={"document_ids": ["00000000-0000-0000-0000-000000000000"]})
    assert other.status_code == 404


def test_gmail_travel_emails_are_imported_and_announced_without_a_review_step(app, user_api, monkeypatch):
    import base64
    from datetime import datetime, timezone

    from app.models import IntegrationConnection
    from app.services.integrations import gmail

    me = db.session.execute(db.select(User).order_by(User.created_at.desc())).scalars().first()
    conn = IntegrationConnection(user_id=me.id, provider="gmail", status="connected", account_email="me@example.com")
    db.session.add(conn)
    db.session.commit()
    eml = D.restaurant_email(date.today() + timedelta(days=10), "me@example.com")

    def fake_api(c, method, path, **kw):
        if path == "/messages":
            return {"messages": [{"id": "m1"}]}
        if kw.get("params") == {"format": "raw"}:
            return {"raw": base64.urlsafe_b64encode(eml).decode()}
        return {"threadId": "t1", "internalDate": str(int(datetime.now(timezone.utc).timestamp() * 1000)), "snippet": "",
                "payload": {"headers": [{"name": "Subject", "value": "Your table at Da Enzo al 29"}, {"name": "From", "value": "x@y"}]}}

    monkeypatch.setattr(gmail, "_api", fake_api)
    assert gmail.sync_candidates(me.id) == 1
    conv, msgs = _updates(me)
    assert "Da Enzo al 29" in msgs[-1].content and any(r["type"] == "document" for r in msgs[-1].references)

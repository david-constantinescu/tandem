"""Live trip context: weather (Open-Meteo), local news (Google News RSS), journeys, and the assistant acting on them."""
from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest

from app.services.context import news, weather


class _Resp:
    def __init__(self, *, json_data=None, text=""):
        self._json, self.text = json_data, text

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


@pytest.fixture
def live(app, monkeypatch):
    """Weather and news switched on, with the HTTP calls answered by fixed, realistic payloads."""
    app.config.update(WEATHER_ENABLED=True, NEWS_ENABLED=True)

    def fake_get(url, params=None, **kw):
        if "open-meteo" in url:
            start = date.fromisoformat(params["start_date"])
            days = [(start + timedelta(days=i)).isoformat()
                    for i in range((date.fromisoformat(params["end_date"]) - start).days + 1)]
            wet = days[0]  # the first day of any request is rainy
            return _Resp(json_data={"timezone": "Europe/Rome", "daily": {
                "time": days, "weather_code": [63 if d == wet else 1 for d in days],
                "temperature_2m_max": [16.0] * len(days), "temperature_2m_min": [9.0] * len(days),
                "precipitation_probability_max": [90 if d == wet else 10 for d in days],
                "precipitation_sum": [12.0 if d == wet else 0 for d in days], "wind_speed_10m_max": [12.0] * len(days)},
                "hourly": {"time": [f"{wet}T15:00"], "precipitation_probability": [85]}})
        if "news.google.com" in url:
            day, past = date.today() + timedelta(days=13), date.today() - timedelta(days=1)
            months = news.MONTHS["it"]
            return _Resp(text=f"""<rss><channel>
              <item><title>Sciopero ATAC il {day.day} {months[day.month - 1]}: a rischio bus e metro - RomaToday</title>
                <link>https://www.romatoday.it/sciopero</link><pubDate>{_rfc822()}</pubDate><source>RomaToday</source></item>
              <item><title>Corteo in centro, chiusa via del Corso - Roma Capitale</title>
                <link>https://www.comune.roma.it/corteo</link><pubDate>{_rfc822()}</pubDate><source>Roma Capitale</source></item>
              <item><title>Sciopero generale il {past.day} {months[past.month - 1]}, città bloccata - RomaToday</title>
                <link>https://www.romatoday.it/sciopero-passato</link><pubDate>{_rfc822()}</pubDate><source>RomaToday</source></item>
              <item><title>Nuova pizzeria apre a Trastevere - Food blog</title>
                <link>https://example.org/pizza</link><pubDate>{_rfc822()}</pubDate><source>Food blog</source></item>
            </channel></rss>""")
        raise httpx.ConnectError("unexpected url " + url)

    monkeypatch.setattr(weather.httpx, "get", fake_get)
    monkeypatch.setattr(news.httpx, "get", fake_get)
    return fake_get


def _rfc822() -> str:
    from datetime import datetime, timezone
    from email.utils import format_datetime
    return format_datetime(datetime.now(timezone.utc))


def _trip(api) -> dict:
    return api.get("/api/v1/trips").get_json()["data"][0]


def test_trip_context_has_weather_and_disruptions(api, live):
    api.demo()
    t = _trip(api)
    data = api.get(f"/api/v1/trips/{t['id']}/context").get_json()["data"]
    w = data["weather"]
    assert w["available"] and w["days"][0]["condition"] == "rain" and w["days"][0]["outdoor_ok"] is False
    assert w["days"][0]["wet_hours"] == ["15:00"]
    items = data["news"]["items"]
    kinds = [i["kind"] for i in items]
    assert kinds[:2] == ["strike", "protest"] or set(kinds) == {"strike", "protest"}
    assert "Nuova pizzeria" not in " ".join(i["title"] for i in items)  # not a disruption
    assert all("passato" not in i["url"] for i in items)  # yesterday's strike is over
    strike = next(i for i in items if i["kind"] == "strike")
    assert strike["source"] == "RomaToday" and not strike["title"].endswith("RomaToday")


def test_forecast_only_covers_sixteen_days(app, live):
    with app.app_context():
        far = date.today() + timedelta(days=40)
        out = weather.forecast(41.9, 12.5, "Europe/Rome", far, far + timedelta(days=3))
    assert out["available"] is False and out["reason"] == "too_far_ahead"


def test_offline_assistant_answers_weather_and_news(api, live):
    api.demo()
    t = _trip(api)
    conv = api.post("/api/v1/assistant/conversations", json={"trip_id": t["id"]}).get_json()["data"]
    weather_reply = api.post(f"/api/v1/assistant/conversations/{conv['id']}/messages",
                             json={"content": "What's the weather like?"}).get_json()["data"]["reply"]["content"]
    assert "Open-Meteo" in weather_reply and "better indoors" in weather_reply
    news_reply = api.post(f"/api/v1/assistant/conversations/{conv['id']}/messages",
                          json={"content": "Are there any strikes? Can I take the bus?"}).get_json()["data"]["reply"]
    assert "romatoday.it" in news_reply["content"] and "Strike" in news_reply["content"]
    assert any(r.get("type") == "link" for r in news_reply["references"])


def test_journeys_are_real_links(api):
    api.register()
    r = api.get("/api/v1/journeys?origin=Rome&destination=Florence&date=2026-11-15&mode=train").get_json()["data"]
    names = [link["name"] for link in r["links"]]
    assert names[0] == "Google Maps" and "Trenitalia" in names and "Italo" in names
    assert "Eurostar" not in names  # doesn't serve Italy
    assert all(link["url"].startswith("https://") for link in r["links"])


def test_assistant_adds_what_the_user_asked_for_directly(api, app):
    from app.extensions import db
    from app.models import User
    from app.services.agent.tools import ToolContext, run_tool

    api.demo()
    t = _trip(api)
    with app.app_context():
        user = db.session.execute(db.select(User).where(User.is_demo.is_(True)).order_by(User.created_at.desc())).scalars().first()
        ctx = ToolContext(user=user, conversation_id=None, default_trip_id=t["id"])
        day = t["start_date"]
        status, asked = run_tool(ctx, "create_itinerary_event", {"title": "Gelato at Giolitti", "type": "restaurant",
                                                                 "start_local": f"{day}T16:00", "requested_by_user": True})
        assert status == "ok" and asked["created"]["status"] == "unbooked"
        status, idea = run_tool(ctx, "create_itinerary_event", {"title": "Sunset at the Pincio", "type": "activity",
                                                                "start_local": f"{day}T17:00"})
        assert status == "ok" and idea["created"]["status"] == "suggested"


def test_journeys_abroad_skip_domestic_buses(api):
    api.register()
    r = api.get("/api/v1/journeys?origin=London&destination=Rome").get_json()["data"]
    names = [link["name"] for link in r["links"]]
    assert "Google Flights" in names and "ITA Airways" in names and "British Airways" in names
    assert "National Express" not in names and "Trenitalia" not in names


@pytest.mark.parametrize("question, locale, expect", [
    ("How do I get from Rome to Florence on Sunday?", "en", "Trenitalia"),
    ("Cum ajung de la Roma la Florența cu trenul pe 14 noiembrie?", "ro", "Trenitalia"),
])
def test_offline_assistant_answers_route_questions(api, live, question, locale, expect):
    api.demo()
    t = _trip(api)
    conv = api.post("/api/v1/assistant/conversations", json={"trip_id": t["id"]}).get_json()["data"]
    reply = api.post(f"/api/v1/assistant/conversations/{conv['id']}/messages", json={"content": question},
                     headers={"X-Tandem-Locale": locale}).get_json()["data"]["reply"]["content"]
    assert expect in reply and "Florenta Cu" not in reply


def test_offline_news_answer_says_whether_trip_dates_are_hit(api, live):
    api.demo()
    t = _trip(api)
    conv = api.post("/api/v1/assistant/conversations", json={"trip_id": t["id"]}).get_json()["data"]
    reply = api.post(f"/api/v1/assistant/conversations/{conv['id']}/messages",
                     json={"content": "Is there a strike?"}).get_json()["data"]["reply"]["content"]
    assert "mention your trip dates" in reply


@pytest.mark.parametrize("question, locale, title", [
    ("Add dinner at Roscioli on Saturday at 8pm", "en", "Dinner at Roscioli"),
    ("Adaugă cină la Roscioli sâmbătă la 19:15", "ro", "Cină la Roscioli"),
])
def test_offline_assistant_adds_what_you_ask_for(api, live, question, locale, title):
    api.demo()
    t = _trip(api)
    conv = api.post("/api/v1/assistant/conversations", json={"trip_id": t["id"]}).get_json()["data"]
    reply = api.post(f"/api/v1/assistant/conversations/{conv['id']}/messages", json={"content": question},
                     headers={"X-Tandem-Locale": locale}).get_json()["data"]["reply"]["content"]
    assert title in reply
    events = api.get(f"/api/v1/trips/{t['id']}/itinerary").get_json()["data"]
    added = next(e for e in events if e["title"] == title)
    assert added["status"] == "unbooked"  # asked for, so in the plan, not a suggestion
    if locale == "ro":  # 19:15 lands on the demo's 19:00 dinner
        assert "se suprapune cu Cină la Roscioli" in reply

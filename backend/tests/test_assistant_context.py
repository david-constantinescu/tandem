"""The assistant knows the whole trip up front, asks tappable clarifying questions, and survives provider limits."""
from __future__ import annotations

import time
from datetime import timedelta

import pytest

from app.extensions import db
from app.models import ItineraryEvent
from app.services.agent import orchestrator
from app.services.agent.brief import trip_brief
from app.services.ai.base import AIRequest, ChatMessage, ProviderUnavailable, QuotaExceeded, TextPart, ToolCall
from tests.test_agent_approvals import _demo_user, scripted  # noqa: F401


def _conversation(user, trip):
    conv = orchestrator.Conversation(user_id=user.id, trip_id=trip.id, title="New conversation")
    db.session.add(conv)
    db.session.commit()
    return conv


def test_brief_has_travellers_bookings_plan_and_conflicts(app):
    user, trip = _demo_user()
    text = trip_brief(user, trip)
    assert trip.name in text and "Travellers:" in text and "Bookings:" in text
    assert "Known clashes" in text
    assert "Preferences:" in text
    assert len(text) <= 5300


def test_system_prompt_carries_the_brief_so_no_tool_round_is_needed(app, scripted):  # noqa: F811
    user, trip = _demo_user()
    user.ai_settings.mode = "full"
    db.session.commit()
    p = scripted(["Saturday you have the walking tour at 17:30 and dinner at 19:00."])
    orchestrator.respond(user, _conversation(user, trip), "What's on Saturday?")
    assert len(p.seen) == 1  # answered in one model call
    assert trip.name in p.seen[0].system and "Travellers:" in p.seen[0].system


def test_ask_user_ends_the_turn_with_tappable_options(app, scripted):  # noqa: F811
    user, trip = _demo_user()
    user.ai_settings.mode = "full"
    db.session.commit()
    p = scripted([[ToolCall("1", "ask_user", {"question": "What kind of culture?", "options": ["Museum", "Guided tour", "Live music"]})],
                  "SHOULD NOT BE REACHED"])
    msg = orchestrator.respond(user, _conversation(user, trip), "Something cultural")
    assert msg.content == "What kind of culture?"
    choices = [r for r in msg.references if r["type"] == "choices"]
    assert choices and choices[0]["options"] == ["Museum", "Guided tour", "Live music"]
    assert len(p.seen) == 1  # it stopped for the answer instead of carrying on


def test_ask_user_needs_two_real_options(app):
    from app.services.agent.tools import ToolContext, run_tool

    user, trip = _demo_user()
    status, _ = run_tool(ToolContext(user=user, default_trip_id=trip.id), "ask_user", {"question": "Which?", "options": ["Only", " "]})
    assert status == "error"


def test_prompt_tells_the_model_not_to_ask_what_the_trip_already_says(app):
    user, trip = _demo_user()
    prompt = orchestrator.system_prompt(user, trip, trip_brief(user, trip))
    assert "Don't ask which" in prompt and "ask_user" in prompt


def test_prompt_makes_clash_questions_get_a_direct_answer(app):
    user, trip = _demo_user()
    prompt = orchestrator.system_prompt(user, trip, trip_brief(user, trip))
    assert "answered, never asked back" in prompt and "Never call ask_user" in prompt


def test_added_event_gets_a_length_and_reports_its_clash(app):
    from app.services.agent.tools import ToolContext, run_tool

    user, trip = _demo_user()
    sat = (trip.start_date + timedelta(days=2)).isoformat()
    status, out = run_tool(ToolContext(user=user, default_trip_id=trip.id), "create_itinerary_event",
                           {"title": "Cena la Roscioli", "type": "restaurant", "start_local": f"{sat}T19:30",
                            "requested_by_user": True})
    assert status == "ok" and out["created"]["end_local"]
    assert out["conflicts"] and "Roscioli" in out["conflicts"][0]["title"]
    e = db.session.execute(db.select(ItineraryEvent).where(ItineraryEvent.title == "Cena la Roscioli")).scalar_one()
    assert e.status == "unbooked" and e.end_at is not None


def test_gemini_falls_back_across_models_when_one_is_out_of_quota(app, monkeypatch):
    from app.services.ai.base import AIResponse
    from app.services.ai.gemini import GeminiProvider

    cfg = {"GEMINI_API_KEY": "x", "AI_REQUEST_TIMEOUT": 20, "GEMINI_FALLBACK_MODELS": "flash-lite, other"}
    provider = GeminiProvider(cfg)
    tried = []

    def fake(self, request, model):
        tried.append(model)
        if model == "main":
            raise QuotaExceeded("quota", provider="gemini")
        if model == "flash-lite":
            raise ProviderUnavailable("503", provider="gemini")
        return AIResponse(provider="gemini", model=model, text="ok")

    monkeypatch.setattr(GeminiProvider, "_generate_one", fake)
    req = AIRequest(task="agent", system="", messages=[ChatMessage(role="user", parts=[TextPart("hi")])])
    assert provider.generate(req, "main").model == "other"
    assert tried == ["main", "flash-lite", "other"]


def test_gemini_gives_up_when_every_model_fails_and_keeps_the_last_error(app, monkeypatch):
    from app.services.ai.gemini import GeminiProvider

    monkeypatch.setattr(GeminiProvider, "_generate_one", lambda self, r, m: (_ for _ in ()).throw(QuotaExceeded("q", provider="gemini")))
    provider = GeminiProvider({"GEMINI_API_KEY": "x", "AI_REQUEST_TIMEOUT": 20, "GEMINI_FALLBACK_MODELS": "b"})
    with pytest.raises(QuotaExceeded):
        provider.generate(AIRequest(task="agent", system="", messages=[]), "a")


def test_no_fallback_once_the_turn_is_nearly_out_of_time(app, monkeypatch):
    from app.services.ai.gemini import GeminiProvider

    tried = []

    def fake(self, request, model):
        tried.append(model)
        raise ProviderUnavailable("503", provider="gemini")

    monkeypatch.setattr(GeminiProvider, "_generate_one", fake)
    provider = GeminiProvider({"GEMINI_API_KEY": "x", "AI_REQUEST_TIMEOUT": 20, "GEMINI_FALLBACK_MODELS": "b,c"})
    with pytest.raises(ProviderUnavailable):
        provider.generate(AIRequest(task="agent", system="", messages=[], deadline=time.monotonic() + 2), "a")
    assert tried == ["a"]


def test_a_conversation_that_runs_past_its_deadline_stops_with_a_reply(app, scripted, monkeypatch):  # noqa: F811
    user, trip = _demo_user()
    user.ai_settings.mode = "full"
    db.session.commit()
    monkeypatch.setattr(orchestrator, "MAX_SECONDS", -1)
    scripted(["never used"])
    msg = orchestrator.respond(user, _conversation(user, trip), "Hello")
    assert "ran out of time" in msg.content


def test_a_model_that_stops_after_the_tools_is_asked_once_for_the_answer(app, scripted):  # noqa: F811
    user, trip = _demo_user()
    user.ai_settings.mode = "full"
    db.session.commit()
    p = scripted([[ToolCall("1", "get_trip", {})], "", "Weekendul din Roma e 12-16 noiembrie."])
    msg = orchestrator.respond(user, _conversation(user, trip), "Când plec?")
    assert msg.content.startswith("Weekendul") and len(p.seen) == 3
    assert "Now answer my last message" in p.seen[2].messages[-1].parts[0].text


def test_an_assistant_that_never_answers_says_so_in_the_users_language(app, scripted):  # noqa: F811
    user, trip = _demo_user()
    user.ai_settings.mode = "full"
    user.locale = "ro"
    db.session.commit()
    scripted([[ToolCall("1", "get_trip", {})], "", ""])
    msg = orchestrator.respond(user, _conversation(user, trip), "Când plec?")
    assert "Nu am reușit" in msg.content


def test_a_fallback_model_gets_earlier_tool_results_as_text_not_as_function_calls():
    from app.services.ai.gemini import flatten_tool_turns

    msgs = [ChatMessage(role="user", parts=[TextPart("Cum e vremea?")]),
            ChatMessage(role="assistant", parts=[], tool_calls=[ToolCall("c1", "get_weather", {"date": "2026-11-14"})], provider_state=object()),
            ChatMessage(role="tool", parts=[TextPart('{"condition":"fog"}')], tool_call_id="c1", tool_name="get_weather")]
    out = flatten_tool_turns(msgs)
    assert [m.role for m in out] == ["user"] and not any(m.tool_calls or m.provider_state for m in out)
    assert "get_weather returned" in out[0].parts[-1].text and "fog" in out[0].parts[-1].text
    assert flatten_tool_turns(msgs[:1]) is msgs[:1] or flatten_tool_turns(msgs[:1]) == msgs[:1]


def test_a_model_that_just_ran_out_of_quota_is_skipped_by_the_next_request(app, monkeypatch):
    from app.services.ai.base import AIResponse
    from app.services.ai.gemini import GeminiProvider

    tried = []

    def fake(self, request, model):
        tried.append(model)
        if model == "main":
            raise QuotaExceeded("quota", provider="gemini")
        return AIResponse(provider="gemini", model=model, text="ok")

    monkeypatch.setattr(GeminiProvider, "_generate_one", fake)
    provider = GeminiProvider({"GEMINI_API_KEY": "x", "AI_REQUEST_TIMEOUT": 20, "GEMINI_FALLBACK_MODELS": "backup"})
    req = AIRequest(task="agent", system="", messages=[ChatMessage(role="user", parts=[TextPart("hi")])])
    assert provider.generate(req, "main").model == "backup"
    assert provider.generate(req, "main").model == "backup"
    assert tried == ["main", "backup", "backup"]  # the second request didn't ask "main" again


class _R:
    def __init__(self, status, payload=None):
        self.status_code, self._p = status, payload or {}

    def json(self):
        return self._p


def test_overpass_tries_a_mirror_quickly_and_remembers_the_answer(app, monkeypatch):
    import httpx

    from app.services.providers import osm

    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw["timeout"]))
        if "overpass-api.de" in url:
            raise httpx.ReadTimeout("slow")
        return _R(200, {"elements": [{"type": "node", "id": 1, "lat": 41.9, "lon": 12.5, "tags": {"name": "Museo", "tourism": "museum"}}]})

    monkeypatch.setattr(osm.httpx, "post", fake_post)
    adapter = osm.OSMPlacesAdapter(app.config)
    first = adapter._query(41.9, 12.5, 2000, ["museums"])
    again = adapter._query(41.9, 12.5, 2000, ["museums"])
    assert first == again and first[0]["id"] == 1
    assert all(t <= 8 for _, t in calls) and len(calls) == 2  # one timeout, one mirror; the repeat came from the cache


def test_when_every_overpass_server_fails_the_next_question_does_not_wait_again(app, monkeypatch):
    import httpx

    from app.services.providers import osm
    from app.services.providers.base import ProviderRequestError

    calls = []
    monkeypatch.setattr(osm.httpx, "post", lambda url, **kw: (calls.append(url), (_ for _ in ()).throw(httpx.ConnectError("down")))[1])
    adapter = osm.OSMPlacesAdapter(app.config)
    with pytest.raises(ProviderRequestError):
        adapter._query(41.9, 12.5, 2500, ["historical"])
    n = len(calls)
    with pytest.raises(ProviderRequestError):
        adapter._query(41.9, 12.5, 3000, ["outdoor"])
    assert len(calls) == n  # no new network attempts during the rest period


def test_every_ai_request_in_a_web_request_gets_a_deadline(app, monkeypatch):
    from app.services.ai.base import AIResponse
    from app.services.ai.router import AIRouter

    seen = {}

    class P:
        name = "gemini"
        supports_original_file_processing = True

        def configured(self): return True
        def model_for(self, role): return "gemini-2.5-flash"
        def generate(self, request, model):
            seen["deadline"] = request.deadline
            return AIResponse(provider="gemini", model=model, text="ok")

    app.config["AI_TURN_SECONDS"] = 30
    try:
        user, _ = _demo_user()
        user.ai_settings.mode = "full"
        db.session.commit()
        app.config["DEMO_ALLOW_EXTERNAL_AI"] = True
        req = AIRequest(task="agent", system="", messages=[ChatMessage(role="user", parts=[TextPart("hi")])])
        AIRouter(providers={"gemini": P()}).run(req, user=user)
        assert seen["deadline"] is not None and 0 < seen["deadline"] - time.monotonic() <= 30
    finally:
        app.config["AI_TURN_SECONDS"] = 0
        app.config["DEMO_ALLOW_EXTERNAL_AI"] = False


def test_gemini_moves_to_the_next_model_when_one_answers_with_an_error(app, monkeypatch):
    from app.services.ai.base import AIResponse, ProviderError
    from app.services.ai.gemini import GeminiProvider

    def fake(self, request, model):
        if model == "main":
            raise ProviderError("Gemini returned no content", provider="gemini")
        return AIResponse(provider="gemini", model=model, text="ok")

    monkeypatch.setattr(GeminiProvider, "_generate_one", fake)
    provider = GeminiProvider({"GEMINI_API_KEY": "x", "AI_REQUEST_TIMEOUT": 20, "GEMINI_FALLBACK_MODELS": "backup"})
    req = AIRequest(task="agent", system="", messages=[ChatMessage(role="user", parts=[TextPart("hi")])])
    assert provider.generate(req, "main").model == "backup"


def test_a_question_written_as_prose_is_asked_again_through_the_tool(app, scripted):  # noqa: F811
    user, trip = _demo_user()
    user.ai_settings.mode = "full"
    db.session.commit()
    p = scripted(["Ce fel de activitate te interesează?",
                  [ToolCall("1", "ask_user", {"question": "Ce fel de activitate te interesează?", "options": ["Muzeu", "Tur"]})],
                  "unused"])
    msg = orchestrator.respond(user, _conversation(user, trip), "Ceva cultural")
    assert [r["options"] for r in msg.references if r["type"] == "choices"] == [["Muzeu", "Tur"]]
    sent = " ".join(getattr(part, "text", "") or "" for m in p.seen[-1].messages for part in m.parts)
    assert "by calling ask_user" in sent and len(p.seen) == 2


def test_only_one_purchase_starts_per_reply(app, scripted):  # noqa: F811
    from app.models import AgentAction

    user, trip = _demo_user()
    user.ai_settings.mode = "full"
    db.session.commit()
    day = trip.start_date.isoformat()
    args = {"site": "demo_rail", "origin": "Roma", "destination": "Firenze", "date": day, "adults": 2}
    scripted([[ToolCall("1", "start_website_task", args), ToolCall("2", "start_website_task", args)], "Card mai jos."])
    msg = orchestrator.respond(user, _conversation(user, trip), "cumpara trenul pe site-ul de exercitii")
    assert [c["status"] for c in msg.tool_calls] == ["ok", "error"]
    waiting = db.session.execute(db.select(AgentAction).where(AgentAction.user_id == user.id,
                                                               AgentAction.status == "awaiting_approval")).scalars().all()
    assert len(waiting) == 1


def test_deciding_an_approval_clears_its_notification(app, api):
    from app.models import Notification

    api.demo()
    t = api.get("/api/v1/trips").get_json()["data"][0]
    task = api.post("/api/v1/browser/tasks", json={"site": "demo_rail", "origin": "Roma", "destination": "Firenze",
                                                   "date": t["start_date"], "adults": 1, "trip_id": t["id"]}).get_json()["data"]
    note = db.session.execute(db.select(Notification).where(Notification.dedupe_key == f"approval:{task['action_id']}")).scalar_one()
    assert note.read_at is None
    api.post(f"/api/v1/approvals/{task['action_id']}/reject", json={})
    db.session.refresh(note)
    assert note.read_at is not None

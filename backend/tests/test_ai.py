"""AI provider layer: routing rules, Groq file restriction, paid-model blocking, fallback, validation, HTTP mapping."""
from __future__ import annotations

import httpx
import pytest
import respx
from pydantic import BaseModel

from app.extensions import db
from app.models import AIUsageRecord
from app.services import users as user_service
from app.services.ai.base import (
    TASK_AGENT, TASK_DOCUMENT_EXTRACTION, TASK_DOCUMENT_TEXT_EXTRACTION, TASK_SUMMARY, TASK_TEXT_EXTRACTION, AIProvider,
    AIRequest, AIResponse, CapabilityError, ChatMessage, ConsentRequired, FilePart, ImagePart, InvalidOutput,
    NoProviderAvailable, ProviderTimeout, QuotaExceeded, TextPart,
)
from app.services.ai.groq import GroqProvider
from app.services.ai.router import AIRouter
from app.services.ai.zai import ZaiProvider


class Out(BaseModel):
    answer: str


class FakeProvider(AIProvider):
    def __init__(self, name, model_ids, responses=None, files=False):
        self.name = name
        self.models = model_ids
        self.responses = list(responses or [])
        self.calls: list[AIRequest] = []
        self.supports_original_file_processing = files

    def configured(self):
        return True

    def model_for(self, role):
        return self.models.get(role)

    def capabilities(self):
        return {}

    def generate(self, request, model):
        self.calls.append(request)
        nxt = self.responses.pop(0) if self.responses else '{"answer": "ok"}'
        if isinstance(nxt, Exception):
            raise nxt
        return AIResponse(provider=self.name, model=model, text=nxt, input_tokens=10, output_tokens=5)


GEMINI_MODELS = {r: "gemini-3.8-flash" for r in ("extraction", "document", "vision", "reasoning", "fast")}
ZAI_MODELS = {"extraction": "glm-4.7-flash", "reasoning": "glm-4.7-flash", "fast": "glm-4.5-flash",
              "vision": "glm-4.6v-flash", "document": "glm-5.3-flash"}
GROQ_MODELS = {"extraction": "openai/gpt-oss-20b", "reasoning": "openai/gpt-oss-20b", "fast": "openai/gpt-oss-20b"}


@pytest.fixture
def user(app):
    u = user_service.create_user("ai@example.com", "password12345", "AI")
    u.ai_settings.mode = "full"
    db.session.commit()
    return u


def router(app, **providers):
    cfg = dict(app.config)
    return AIRouter(providers=providers, cfg=cfg), cfg


def text_req(task=TASK_SUMMARY, schema=Out):
    return AIRequest(task=task, system="s", messages=[ChatMessage.user("hello")], schema=schema, role="fast")


def file_req(part):
    return AIRequest(task=TASK_DOCUMENT_EXTRACTION, system="s", schema=Out,
                     messages=[ChatMessage(role="user", parts=[part, TextPart("extract")])], role="extraction")


PDF = FilePart(b"%PDF-1.4 test", "application/pdf", "a.pdf")
PNG = ImagePart(b"\x89PNG....", "image/png")


def test_groq_never_receives_files_via_router(app, user):
    groq = FakeProvider("groq", GROQ_MODELS)
    r, _ = router(app, groq=groq)
    for part in (PDF, PNG):
        with pytest.raises(NoProviderAvailable) as exc:
            r.run(file_req(part), user=user)
        assert "groq_file_restriction" in str(exc.value)
    assert groq.calls == []


def test_groq_rejected_for_document_text_task(app, user):
    groq = FakeProvider("groq", GROQ_MODELS)
    r, _ = router(app, groq=groq)
    req = AIRequest(task=TASK_DOCUMENT_TEXT_EXTRACTION, system="s", messages=[ChatMessage.user("text from a pdf")],
                    schema=Out)
    with pytest.raises(NoProviderAvailable):
        r.run(req, user=user)
    assert groq.calls == []


def test_groq_provider_refuses_non_text_parts_even_without_router(app):
    groq = GroqProvider({**app.config, "GROQ_API_KEY": "x"})
    for part in (PNG, PDF):
        req = AIRequest(task=TASK_SUMMARY, system="", messages=[ChatMessage(role="user", parts=[part])])
        with pytest.raises(CapabilityError):
            groq.generate(req, "openai/gpt-oss-20b")
    sneaky = AIRequest(task=TASK_SUMMARY, system="", messages=[ChatMessage.user(
        "data:image/png;base64," + "A" * 200)])
    with pytest.raises(CapabilityError):
        groq.generate(sneaky, "openai/gpt-oss-20b")


def test_groq_allowed_for_text_summary(app, user):
    groq = FakeProvider("groq", GROQ_MODELS)
    r, _ = router(app, groq=groq)
    resp = r.run(text_req(), user=user)
    assert resp.provider == "groq" and resp.data == {"answer": "ok"}


def test_failed_pdf_falls_back_to_zai_only_when_paid_allowed_never_groq(app, user):
    gemini = FakeProvider("gemini", GEMINI_MODELS, [QuotaExceeded("q", retry_after=30)], files=True)
    zai = FakeProvider("zai", ZAI_MODELS)
    groq = FakeProvider("groq", GROQ_MODELS)
    r, cfg = router(app, gemini=gemini, zai=zai, groq=groq)
    with pytest.raises(NoProviderAvailable):
        r.run(file_req(PDF), user=user)
    assert len(gemini.calls) == 1 and zai.calls == [] and groq.calls == []


def test_paid_models_blocked_by_default(app, user):
    zai = FakeProvider("zai", {**ZAI_MODELS, "fast": "glm-5.3"})  # paid text model
    r, _ = router(app, zai=zai)
    with pytest.raises(NoProviderAvailable) as exc:
        r.run(text_req(), user=user)
    assert "paid_model_blocked" in str(exc.value)
    unknown = FakeProvider("gemini", {**GEMINI_MODELS, "fast": "gemini-99-ultra"})
    r2, _ = router(app, gemini=unknown)
    with pytest.raises(NoProviderAvailable) as exc:
        r2.run(text_req(), user=user)
    assert "unknown_model_blocked" in str(exc.value)


def test_consent_modes_enforced(app, user):
    gemini = FakeProvider("gemini", GEMINI_MODELS, files=True)
    r, _ = router(app, gemini=gemini)
    user.ai_settings.mode = "off"
    with pytest.raises(ConsentRequired):
        r.run(text_req(), user=user)
    user.ai_settings.mode = "text_only"
    with pytest.raises(ConsentRequired):
        r.run(file_req(PDF), user=user)
    assert r.run(text_req(TASK_TEXT_EXTRACTION), user=user).provider == "gemini"
    user.ai_settings.allowed_providers = {"gemini": False}
    with pytest.raises(NoProviderAvailable):
        r.run(text_req(TASK_TEXT_EXTRACTION), user=user)


def test_quota_exhaustion_falls_back_and_cools_down(app, user):
    gemini = FakeProvider("gemini", GEMINI_MODELS, [QuotaExceeded("limit", retry_after=120)])
    zai = FakeProvider("zai", ZAI_MODELS)
    r, _ = router(app, gemini=gemini, zai=zai)
    resp = r.run(text_req(TASK_TEXT_EXTRACTION), user=user)
    assert resp.provider == "zai"
    # Gemini is now cooling down and is skipped without being called.
    r.run(text_req(TASK_TEXT_EXTRACTION), user=user)
    assert len(gemini.calls) == 1
    statuses = [u.status for u in db.session.execute(db.select(AIUsageRecord)).scalars()]
    assert "rate_limited" in statuses and statuses.count("ok") == 2


def test_timeout_retries_then_falls_back(app, user):
    gemini = FakeProvider("gemini", GEMINI_MODELS, [ProviderTimeout("t"), ProviderTimeout("t"), ProviderTimeout("t")])
    zai = FakeProvider("zai", ZAI_MODELS)
    r, _ = router(app, gemini=gemini, zai=zai)
    assert r.run(text_req(TASK_TEXT_EXTRACTION), user=user).provider == "zai"
    assert len(gemini.calls) == 3  # 1 + AI_MAX_RETRIES(2)


def test_invalid_structured_output_gets_one_repair_then_fails_over(app, user):
    gemini = FakeProvider("gemini", GEMINI_MODELS, ["not json", '{"wrong": 1}'])
    zai = FakeProvider("zai", ZAI_MODELS, ['```json\n{"answer": "fixed"}\n```'])
    r, _ = router(app, gemini=gemini, zai=zai)
    resp = r.run(text_req(TASK_TEXT_EXTRACTION), user=user)
    assert len(gemini.calls) == 2 and resp.provider == "zai" and resp.data == {"answer": "fixed"}
    with pytest.raises(InvalidOutput):
        from app.services.ai.schema_utils import validate_against

        validate_against(Out, {"wrong": 1})


def test_zai_vision_used_for_images_when_gemini_unavailable(app, user):
    zai = FakeProvider("zai", ZAI_MODELS)
    r, _ = router(app, zai=zai)
    resp = r.run(file_req(PNG), user=user)
    assert resp.provider == "zai" and resp.model == "glm-4.6v-flash"


def test_agent_requires_tool_capable_model(app, user):
    gemini = FakeProvider("gemini", GEMINI_MODELS, ["plain answer"])
    r, _ = router(app, gemini=gemini)
    from app.services.ai.base import ToolSpec

    req = AIRequest(task=TASK_AGENT, system="s", messages=[ChatMessage.user("hi")],
                    tools=[ToolSpec("t", "d", {"type": "object", "properties": {}})])
    assert r.run(req, user=user).text == "plain answer"


# --- HTTP-level provider tests (mocked with respx) ---------------------------------------
@respx.mock
def test_zai_http_success_and_reasoning_discarded(app):
    route = respx.post("https://api.z.ai/api/paas/v4/chat/completions").mock(return_value=httpx.Response(200, json={
        "choices": [{"message": {"content": '{"answer": "hi"}', "reasoning_content": "secret thoughts"},
                     "finish_reason": "stop"}], "usage": {"prompt_tokens": 12, "completion_tokens": 4}}))
    p = ZaiProvider({**app.config, "ZAI_API_KEY": "k"})
    resp = p.generate(text_req(TASK_TEXT_EXTRACTION), "glm-4.7-flash")
    assert resp.text == '{"answer": "hi"}' and "secret" not in resp.text and resp.input_tokens == 12
    body = route.calls[0].request.read().decode()
    assert '"response_format": {"type": "json_object"}' in body.replace(":{", ": {").replace(',"', ', "') or \
           "json_object" in body


@respx.mock
def test_zai_quota_and_timeout_mapping(app):
    p = ZaiProvider({**app.config, "ZAI_API_KEY": "k"})
    respx.post("https://api.z.ai/api/paas/v4/chat/completions").mock(
        return_value=httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"code": "1302", "message": "rate"}}))
    with pytest.raises(QuotaExceeded) as exc:
        p.generate(text_req(), "glm-4.7-flash")
    assert exc.value.retry_after == 7
    respx.post("https://api.z.ai/api/paas/v4/chat/completions").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderTimeout):
        p.generate(text_req(), "glm-4.7-flash")


def test_zai_unsupported_capabilities(app):
    p = ZaiProvider({**app.config, "ZAI_API_KEY": "k", "AI_ALLOW_PAID_MODELS": False})
    with pytest.raises(CapabilityError):
        p.generate(file_req(PDF), "glm-5.3-flash")
    with pytest.raises(CapabilityError):
        p.generate(file_req(ImagePart(b"RIFF....WEBP", "image/webp")), "glm-4.6v-flash")


@respx.mock
def test_groq_http_strict_schema(app):
    route = respx.post("https://api.groq.com/openai/v1/chat/completions").mock(return_value=httpx.Response(200, json={
        "choices": [{"message": {"content": '{"answer": "x"}'}, "finish_reason": "stop"}], "usage": {}}))
    p = GroqProvider({**app.config, "GROQ_API_KEY": "k"})
    p.generate(text_req(), "openai/gpt-oss-20b")
    sent = route.calls[0].request.read().decode()
    assert '"json_schema"' in sent and '"strict":true' in sent.replace(" ", "")


def test_gemini_maps_sdk_errors(app, monkeypatch):
    from google.genai import errors

    from app.services.ai.gemini import GeminiProvider

    p = GeminiProvider({**app.config, "GEMINI_API_KEY": "k"})

    class Models:
        def __init__(self, exc):
            self.exc = exc

        def generate_content(self, **kw):
            raise self.exc

    class Client:
        def __init__(self, exc):
            self.models = Models(exc)

    p._client = Client(errors.ClientError(429, {"error": {"message": "Resource exhausted"}}))
    with pytest.raises(QuotaExceeded):
        p.generate(text_req(), "gemini-3.8-flash")
    p._client = Client(errors.ServerError(503, {"error": {"message": "overloaded"}}))
    from app.services.ai.base import ProviderUnavailable

    with pytest.raises(ProviderUnavailable):
        p.generate(text_req(), "gemini-3.8-flash")


def test_gemini_success_parses_text_usage_and_tool_calls(app):
    from types import SimpleNamespace as NS

    from app.services.ai.gemini import GeminiProvider

    captured = {}

    class Models:
        def generate_content(self, model, contents, config):
            captured["config"] = config
            part = NS(text='{"answer": "g"}', thought=False)
            fc = NS(id="c1", name="get_trip", args={"trip_id": None})
            return NS(candidates=[NS(content=NS(parts=[part]), finish_reason="STOP")], function_calls=[fc],
                      usage_metadata=NS(prompt_token_count=100, candidates_token_count=20, thoughts_token_count=5),
                      prompt_feedback=None)

    p = GeminiProvider({**app.config, "GEMINI_API_KEY": "k"})
    p._client = NS(models=Models())
    resp = p.generate(text_req(), "gemini-3.8-flash")
    assert resp.text == '{"answer": "g"}' and resp.input_tokens == 100 and resp.output_tokens == 25
    assert resp.tool_calls[0].name == "get_trip"
    assert captured["config"].response_mime_type == "application/json"
    assert str(captured["config"].thinking_config.thinking_level).lower().endswith("low")


def test_usage_endpoint_reports_no_paid_usage(user_api):
    data = user_api.get("/api/v1/settings/usage").get_json()["data"]
    assert data["paid_models_allowed"] is False
    ai = user_api.get("/api/v1/settings/ai").get_json()["data"]
    groq = next(p for p in ai["providers"] if p["provider"] == "groq")
    assert groq["original_file_processing"] is False
    gemini = next(p for p in ai["providers"] if p["provider"] == "gemini")
    assert gemini["roles"]["extraction"]["free_tier"] is True


def test_ai_settings_require_privacy_acknowledgement(user_api):
    r = user_api.put("/api/v1/settings/ai", json={"mode": "full"})
    assert r.status_code == 422
    r = user_api.put("/api/v1/settings/ai", json={"mode": "full", "acknowledge_privacy": True})
    assert r.status_code == 200 and r.get_json()["data"]["consent_recorded_at"]




def test_gemini_groups_parallel_tool_results_with_ids(app):
    from app.services.ai.base import ToolCall
    from app.services.ai.gemini import GeminiProvider

    p = GeminiProvider({**app.config, "GEMINI_API_KEY": "k"})
    msgs = [ChatMessage.user("plan my day"),
            ChatMessage(role="assistant", tool_calls=[ToolCall("c1", "get_trip", {}), ToolCall("c2", "detect_conflicts", {})]),
            ChatMessage(role="tool", parts=[TextPart('{"a":1}')], tool_call_id="c1", tool_name="get_trip"),
            ChatMessage(role="tool", parts=[TextPart('{"b":2}')], tool_call_id="c2", tool_name="detect_conflicts")]
    contents = p._contents(msgs, [])
    assert [c.role for c in contents] == ["user", "model", "user"]
    responses = [part.function_response for part in contents[2].parts]
    assert [(r.id, r.name) for r in responses] == [("c1", "get_trip"), ("c2", "detect_conflicts")]


def test_gemini_models_are_picked_from_googles_list_newest_flash_first(app, monkeypatch):
    import httpx

    from app.services.ai import gemini_models, registry

    listing = {"models": [{"name": f"models/{n}", "supportedGenerationMethods": ["generateContent"]} for n in (
        "gemini-2.5-flash", "gemini-3.7-flash", "gemini-3.8-flash-tts", "gemini-3-flash-preview", "gemini-3.5-flash-lite",
        "gemini-3.1-pro-preview", "gemini-flash-latest", "gemini-3.6-flash", "gemini-2.5-flash-lite")]}

    class R:
        def raise_for_status(self): pass
        def json(self): return listing

    monkeypatch.setattr(httpx, "get", lambda *a, **k: R())
    cfg = {"GEMINI_API_KEY": "k"}
    assert gemini_models.available(cfg)[:3] == ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
    assert gemini_models.chain(cfg, "reasoning")[:3] == ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-2.5-flash"]
    assert gemini_models.chain(cfg, "fast")[0] == "gemini-3.5-flash-lite"
    assert all("tts" not in m and "preview" not in m and "pro" not in m for m in gemini_models.available(cfg))
    info = registry.lookup("gemini", "gemini-3.7-flash")
    assert info and info.free_tier and info.tools
    assert registry.lookup("gemini", "gemini-3.1-pro-preview").free_tier is False  # Pro stays blocked


def test_gemini_models_fall_back_when_google_cannot_be_asked(app, monkeypatch):
    import httpx

    from app.services.ai import gemini_models

    def down(*a, **k):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", down)
    assert gemini_models.available({"GEMINI_API_KEY": "k"}) == ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
    assert gemini_models.available({}) == ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

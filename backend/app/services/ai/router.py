"""routerul ai: alege providerul, respecta setarile omului, trece la urmatorul daca unul pica"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta

from flask import current_app
from sqlalchemy import insert

from app.extensions import db
from app.models import AIUsageRecord, ProviderStatus, User, UserAISettings
from app.models.user import AI_MODE_FULL, AI_MODE_OFF
from app.services.ai import registry
from app.services.ai.base import (
    TASK_AGENT, TASK_CLASSIFICATION, TASK_DOCUMENT_EXTRACTION, TASK_DOCUMENT_TEXT_EXTRACTION, TASK_EXPLANATION,
    TASK_SUMMARY, TASK_TEXT_EXTRACTION, AIError, AIProvider, AIRequest, AIResponse, CapabilityError, ChatMessage,
    ConsentRequired, FilePart, ImagePart, InvalidOutput, NoProviderAvailable, NotConfigured, PaidModelBlocked,
    QuotaExceeded, TextPart,
)
from app.services.ai.gemini import GeminiProvider
from app.services.ai.groq import GroqProvider
from app.services.ai.schema_utils import parse_json_text, validate_against
from app.services.ai.zai import ZaiProvider
from app.services.cache import cache_get, cache_set
from app.utils.timeutil import utcnow

log = logging.getLogger("tandem.ai.router")

DEFAULT_ORDER = {
    TASK_DOCUMENT_EXTRACTION: ["gemini", "zai"],
    TASK_DOCUMENT_TEXT_EXTRACTION: ["gemini", "zai"],
    TASK_TEXT_EXTRACTION: ["gemini", "zai", "groq"],
    TASK_CLASSIFICATION: ["groq", "gemini", "zai"],
    TASK_SUMMARY: ["groq", "gemini", "zai"],
    TASK_EXPLANATION: ["groq", "gemini", "zai"],
    TASK_AGENT: ["gemini", "groq", "zai"],  # groq e rapid si sigur; z.ai e des aglomerat
}
GROQ_FORBIDDEN_TASKS = {TASK_DOCUMENT_EXTRACTION, TASK_DOCUMENT_TEXT_EXTRACTION}
FILE_DERIVED_TASKS = {TASK_DOCUMENT_TEXT_EXTRACTION}


@dataclass
class Candidate:
    provider: AIProvider
    model: str


@dataclass
class RoutePlan:
    candidates: list[Candidate]
    skipped: list[dict]


def build_providers(cfg) -> dict[str, AIProvider]:
    return {"gemini": GeminiProvider(cfg), "zai": ZaiProvider(cfg), "groq": GroqProvider(cfg)}


class AIRouter:
    def __init__(self, providers: dict[str, AIProvider] | None = None, cfg=None):
        self.cfg = cfg or current_app.config
        self.providers = providers or build_providers(self.cfg)

    # ---------------------------------------------------------------------------------
    def plan(self, request: AIRequest, settings: UserAISettings | None, *, is_demo: bool = False) -> RoutePlan:
        skipped: list[dict] = []
        mode = settings.mode if settings else AI_MODE_OFF
        if is_demo and not self.cfg.get("DEMO_ALLOW_EXTERNAL_AI"):
            mode = AI_MODE_OFF
        if mode == AI_MODE_OFF:
            return RoutePlan([], [{"provider": "*", "reason": "external_ai_disabled"}])
        if request.contains_original_file and mode != AI_MODE_FULL:
            return RoutePlan([], [{"provider": "*", "reason": "file_upload_not_permitted"}])

        order = list(DEFAULT_ORDER.get(request.task, ["gemini", "zai", "groq"]))
        # verificam toti providerii, ca restrictiile sa fie aplicate (si raportate) clar, nu doar
        # pentru ca un provider lipseste din ordine
        order += [name for name in self.providers if name not in order]
        preferred = (settings.preferred_provider if settings else None) or self.cfg.get("AI_DEFAULT_PROVIDER")
        if preferred in order:
            order.remove(preferred)
            order.insert(0, preferred)
        allowed = (settings.allowed_providers if settings else None) or {}

        candidates: list[Candidate] = []
        for name in order:
            provider = self.providers.get(name)
            reason = self._ineligible(provider, name, request, allowed)
            if reason:
                skipped.append({"provider": name, "reason": reason})
                continue
            candidates.append(Candidate(provider, self._model(provider, request)))
        if not self.cfg.get("AI_ENABLE_FALLBACK", True):
            candidates = candidates[:1]
        return RoutePlan(candidates, skipped)

    def _model(self, provider: AIProvider, request: AIRequest) -> str | None:
        if request.has_files:
            return provider.model_for("document")
        if request.has_images:
            return provider.model_for("vision")
        return provider.model_for(request.role)

    def _ineligible(self, provider: AIProvider | None, name: str, request: AIRequest, allowed: dict) -> str | None:
        if provider is None:
            return "unknown_provider"
        if allowed.get(name) is False:
            return "disabled_by_user"
        if not provider.configured():
            return "not_configured"
        if name == "groq":
            if request.contains_original_file:
                return "groq_file_restriction"
            if request.task in GROQ_FORBIDDEN_TASKS:
                return "groq_document_task_restriction"
        if request.has_files and not provider.supports_original_file_processing:
            return "no_document_support"
        model = self._model(provider, request)
        if not model:
            return "no_model_for_modality"
        info = registry.lookup(name, model)
        allow_paid = bool(self.cfg.get("AI_ALLOW_PAID_MODELS"))
        if info is None and not allow_paid:
            return "unknown_model_blocked"
        if info is not None and not info.free_tier and not allow_paid:
            return "paid_model_blocked"
        if info is not None:
            needed = self._needed_inputs(request)
            if not needed.issubset(info.inputs):
                return f"model_lacks_inputs:{','.join(sorted(needed - info.inputs))}"
            if request.tools and not info.tools:
                return "model_lacks_tools"
        if self._cooling_down(name):
            return "quota_cooldown"
        return None

    @staticmethod
    def _needed_inputs(request: AIRequest) -> set[str]:
        needed = {"text"}
        for mime in request.file_mime_types:
            if mime.startswith("image/"):
                needed.add("image")
            elif mime == "application/pdf":
                needed.add("pdf")
            else:
                needed.add("office_docs")
        return needed

    def _cooling_down(self, name: str) -> bool:
        status = db.session.get(ProviderStatus, f"ai:{name}")
        return bool(status and status.cooldown_until and status.cooldown_until > utcnow())

    # ---------------------------------------------------------------------------------
    def run(self, request: AIRequest, *, user: User | None = None) -> AIResponse:
        settings = user.ai_settings if user else None
        is_demo = bool(user and user.is_demo)
        if is_demo:
            self._enforce_demo_budget(user)
        if request.deadline is None and self.cfg.get("AI_TURN_SECONDS"):
            request.deadline = time.monotonic() + float(self.cfg["AI_TURN_SECONDS"])
        plan = self.plan(request, settings, is_demo=is_demo)
        if not plan.candidates:
            reasons = {s["reason"] for s in plan.skipped}
            if reasons & {"external_ai_disabled", "file_upload_not_permitted"}:
                raise ConsentRequired("External AI processing is not permitted by your privacy settings")
            raise NoProviderAvailable("No AI provider is available for this request: "
                                      + ", ".join(f"{s['provider']}={s['reason']}" for s in plan.skipped))

        cache_key = self._cache_key(request) if request.cacheable else None
        if cache_key:
            cached = cache_get("ai", cache_key)
            if cached:
                self._record(user, cached["provider"], cached["model"], request.task, "cached", 0, 0, 0)
                return AIResponse(provider=cached["provider"], model=cached["model"], text=cached.get("text", ""),
                                  data=cached.get("data"))

        errors: list[str] = []
        for cand in plan.candidates:
            if request.remaining is not None and request.remaining < 4:
                errors.append(f"{cand.provider.name}: out_of_time")
                break
            try:
                response = self._attempt(cand, request, user)
            except AIError as exc:
                errors.append(f"{cand.provider.name}: {exc.code}")
                log.info("provider %s failed (%s); trying next", cand.provider.name, exc.code)
                continue
            if cache_key:
                cache_set("ai", cache_key, {"provider": response.provider, "model": response.model,
                                            "text": response.text, "data": response.data},
                          ttl_hours=self.cfg.get("AI_CACHE_TTL_HOURS", 168))
            return response
        raise NoProviderAvailable("All eligible AI providers failed: " + "; ".join(errors))

    def _attempt(self, cand: Candidate, request: AIRequest, user: User | None) -> AIResponse:
        provider, model = cand.provider, cand.model
        retries = int(self.cfg.get("AI_MAX_RETRIES", 2))
        repaired = False
        attempt = 0
        while True:
            started = time.monotonic()
            try:
                response = provider.generate(request, model)
                if request.schema is not None and not request.tools:
                    try:
                        response.data = validate_against(request.schema, parse_json_text(response.text))
                    except InvalidOutput:
                        self._record(user, provider.name, model, request.task, "invalid_output",
                                     response.input_tokens, response.output_tokens, _ms(started))
                        if repaired:
                            raise
                        repaired = True
                        request = _with_repair_hint(request, response.text)
                        continue
                self._record(user, provider.name, model, request.task, "ok", response.input_tokens,
                             response.output_tokens, _ms(started))
                return response
            except QuotaExceeded as exc:
                self._record(user, provider.name, model, request.task, "rate_limited", 0, 0, _ms(started), exc.code)
                self._cooldown(provider.name, exc.retry_after or 60, str(exc))
                raise
            except (CapabilityError, NotConfigured, PaidModelBlocked) as exc:
                self._record(user, provider.name, model, request.task, "rejected", 0, 0, _ms(started), exc.code)
                raise
            except AIError as exc:
                self._record(user, provider.name, model, request.task, "error", 0, 0, _ms(started), exc.code)
                # daca cineva asteapta raspunsul nu dormim si reincercam, trecem la urmatorul provider
                if exc.retryable and attempt < retries and request.deadline is None:
                    attempt += 1
                    time.sleep(min(2 ** attempt, 8) if not current_app.config.get("TESTING") else 0)
                    continue
                raise

    # ---------------------------------------------------------------------------------
    def _enforce_demo_budget(self, user: User) -> None:
        since = utcnow() - timedelta(days=1)
        count = db.session.execute(
            db.select(db.func.count(AIUsageRecord.id)).where(
                AIUsageRecord.user_id == user.id, AIUsageRecord.created_at >= since,
                AIUsageRecord.status.in_(["ok", "error", "invalid_output"]))
        ).scalar_one()
        if count >= int(self.cfg.get("DEMO_DAILY_AI_REQUESTS", 60)):
            raise QuotaExceeded("The demo workspace has used its daily AI allowance", provider="demo")

    def _record(self, user, provider, model, task, status, tin, tout, ms, error_code=None) -> None:
        values = {
            "id": uuid.uuid4(), "user_id": user.id if user else None, "provider": provider, "model": model or "",
            "task": task, "status": status, "input_tokens": tin, "output_tokens": tout, "latency_ms": ms,
            "estimated_cost": registry.estimate_cost(provider, model, tin, tout) if model else None,
            "error_code": error_code, "created_at": utcnow(),
        }
        try:
            with db.engine.begin() as conn:
                conn.execute(insert(AIUsageRecord.__table__).values(**values))
        except Exception:  # noqa: BLE001 - usage tracking must never break a request
            log.exception("could not record AI usage")

    def _cooldown(self, provider: str, seconds: float, detail: str) -> None:
        until = utcnow() + timedelta(seconds=min(max(seconds, 15), 3600))
        table = ProviderStatus.__table__
        try:
            with db.engine.begin() as conn:
                conn.execute(table.delete().where(table.c.provider == f"ai:{provider}"))
                conn.execute(insert(table).values(provider=f"ai:{provider}", kind="ai", state="quota_exhausted",
                                                  detail={"message": detail[:300]}, cooldown_until=until,
                                                  checked_at=utcnow()))
        except Exception:  # noqa: BLE001
            log.exception("could not record provider cooldown")

    @staticmethod
    def _cache_key(request: AIRequest) -> str:
        # pe user, ca sa nu se amestece raspunsurile intre conturi
        h = hashlib.sha256()
        h.update(str(request.user_id).encode())
        h.update(request.task.encode())
        h.update(request.system.encode())
        h.update((request.schema.__name__ if request.schema else "").encode())
        for m in request.messages:
            for p in m.parts:
                if isinstance(p, TextPart):
                    h.update(p.text.encode())
                elif isinstance(p, (ImagePart, FilePart)):
                    h.update(hashlib.sha256(p.data).digest())
        return h.hexdigest()


def _with_repair_hint(request: AIRequest, bad_output: str) -> AIRequest:
    hint = ("Your previous reply was not valid JSON for the required schema. Reply again with only the "
            "corrected JSON object.")
    messages = list(request.messages) + [
        ChatMessage(role="assistant", parts=[TextPart(bad_output[:4000] or "(empty)")]),
        ChatMessage.user(hint),
    ]
    return AIRequest(**{**request.__dict__, "messages": messages})


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def ai_router() -> AIRouter:
    return AIRouter()


def provider_overview(cfg=None) -> list[dict]:
    """configuration and capability summary for the Settings page (no network calls)"""
    cfg = cfg or current_app.config
    out = []
    for name, provider in build_providers(cfg).items():
        roles = {}
        for role in ("extraction", "vision", "reasoning", "fast", "document"):
            model = provider.model_for(role)
            if not model:
                continue
            info = registry.lookup(name, model)
            roles[role] = {
                "model": model,
                "known": info is not None,
                "free_tier": bool(info and info.free_tier),
                "id_verified": bool(info and info.id_verified),
                "usable": bool(info and (info.free_tier or cfg.get("AI_ALLOW_PAID_MODELS"))) or
                          (info is None and bool(cfg.get("AI_ALLOW_PAID_MODELS"))),
                "inputs": sorted(info.inputs) if info else [],
                "notes": list(info.notes) if info else ["Not in Tandem's verified model registry"],
            }
        status = db.session.get(ProviderStatus, f"ai:{name}")
        out.append({
            "provider": name, "configured": provider.configured(), "capabilities": provider.capabilities(),
            "original_file_processing": bool(provider.supports_original_file_processing),
            "roles": roles,
            "status": {"state": status.state, "detail": status.detail,
                       "cooldown_until": status.cooldown_until.isoformat() if status.cooldown_until else None,
                       "checked_at": status.checked_at.isoformat()} if status else None,
        })
    return out


def json_dumps_compact(value) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)

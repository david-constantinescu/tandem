"""Gemini provider (official google-genai SDK). Primary provider for documents and images."""
from __future__ import annotations

import io
import logging
import time

from flask import current_app

from app.services.ai.base import (
    AIProvider, AIRequest, AIResponse, CapabilityError, ChatMessage, FilePart, ImagePart, NotConfigured,
    ProviderError, ProviderTimeout, ProviderUnavailable, QuotaExceeded, TextPart, ToolCall,
)
from app.services.ai.schema_utils import inline_schema

log = logging.getLogger("tandem.ai.gemini")

# PDFs above this size go through the Files API instead of inline bytes.
INLINE_PDF_LIMIT = 15 * 1024 * 1024


def flatten_tool_turns(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Rewrite earlier tool calls and their results as plain text on the last user message.

    Gemini 3.x refuses a replayed function call that lacks the thought signature of the model that made it, so when
    a different model takes over mid-conversation it is given what the tools returned as text instead.
    """
    from dataclasses import replace

    if not any(m.tool_calls or m.role == "tool" for m in messages):
        return messages
    lines: list[str] = []
    kept: list[ChatMessage] = []
    for m in messages:
        if m.role == "tool":
            body = "".join(p.text for p in m.parts if isinstance(p, TextPart))
            lines.append(f"- {m.tool_name} returned: {body[:3500]}")
        elif m.tool_calls:
            if any(isinstance(p, TextPart) and p.text for p in m.parts):
                kept.append(replace(m, tool_calls=[], provider_state=None))
        else:
            kept.append(replace(m, provider_state=None) if m.provider_state else m)
    note = TextPart("(Tools I already ran for this request, with what they returned:\n" + "\n".join(lines) + "\n)")
    for idx in range(len(kept) - 1, -1, -1):
        if kept[idx].role == "user":
            kept[idx] = replace(kept[idx], parts=[*kept[idx].parts, note])
            return kept
    return [*kept, ChatMessage(role="user", parts=[note])]


class GeminiProvider(AIProvider):
    name = "gemini"
    supports_original_file_processing = True

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._client = None

    def configured(self) -> bool:
        return bool(self.cfg.get("GEMINI_API_KEY"))

    @property
    def client(self):
        if not self.configured():
            raise NotConfigured("GEMINI_API_KEY is not set", provider=self.name)
        if self._client is None:
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=self.cfg["GEMINI_API_KEY"],
                http_options=types.HttpOptions(timeout=int(self.cfg["AI_REQUEST_TIMEOUT"]) * 1000),
            )
        return self._client

    def model_for(self, role):
        return {
            "extraction": self.cfg.get("GEMINI_EXTRACTION_MODEL"),
            "document": self.cfg.get("GEMINI_EXTRACTION_MODEL"),
            "vision": self.cfg.get("GEMINI_VISION_MODEL"),
            "reasoning": self.cfg.get("GEMINI_REASONING_MODEL"),
            "fast": self.cfg.get("GEMINI_FAST_MODEL"),
        }.get(role)

    def capabilities(self) -> dict:
        return {
            "text": True, "image_input": True, "pdf_input": True, "structured_output": True, "tools": True,
            "temporary_files": True, "original_file_processing": True, "audio_input": False,
        }

    # ------------------------------------------------------------------------------------
    def generate(self, request: AIRequest, model: str) -> AIResponse:
        """Try `model`, then the cheaper fallbacks when it is out of quota, at capacity or too slow.

        Free-tier limits are per model, and the 3.x previews are often at capacity (HTTP 503), so a chain of
        models keeps the assistant answering. Only text requests fall back: files stay on the requested model.
        """
        chain = [model]
        if not request.has_files and not request.has_images:
            chain += [m for m in str(self.cfg.get("GEMINI_FALLBACK_MODELS") or "").split(",")
                      if m.strip() and m.strip() != model]
        last: Exception | None = None
        for i, name in enumerate(chain):
            name = name.strip()
            if i and (request.remaining is not None and request.remaining < 6):
                break
            req = request
            if i:  # reasoning state (thought signatures) from another model can't be replayed to this one
                from dataclasses import replace

                req = replace(request, messages=flatten_tool_turns(request.messages))
            try:
                return self._generate_one(req, name)
            except (QuotaExceeded, ProviderUnavailable, ProviderTimeout) as exc:
                last = exc
                log.info("gemini %s unavailable (%s)%s", name, exc.code, "; trying the next model" if i + 1 < len(chain) else "")
        assert last is not None
        raise last

    def _generate_one(self, request: AIRequest, model: str) -> AIResponse:
        from google.genai import errors, types

        uploaded: list[str] = []
        try:
            contents = self._contents(request.messages, uploaded)
            config_kwargs: dict = {
                "system_instruction": request.system or None,
                "temperature": request.temperature,
                "max_output_tokens": request.max_output_tokens,
                "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
            }
            if request.remaining is not None:  # never wait past the turn's deadline
                config_kwargs["http_options"] = types.HttpOptions(
                    timeout=int(max(3.0, min(float(self.cfg["AI_REQUEST_TIMEOUT"]), request.remaining)) * 1000))
            if model.startswith("gemini-3"):
                # Gemini 3.x: 'minimal' thinking is rejected by 3.8-flash, so use 'low' for latency.
                config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="low")
            if request.schema is not None and not request.tools:
                config_kwargs["response_mime_type"] = "application/json"
                config_kwargs["response_json_schema"] = inline_schema(request.schema)
            if request.tools:
                config_kwargs["tools"] = [types.Tool(function_declarations=[
                    types.FunctionDeclaration(name=t.name, description=t.description,
                                              parameters_json_schema=t.parameters)
                    for t in request.tools
                ])]
            started = time.monotonic()
            resp = self.client.models.generate_content(
                model=model, contents=contents, config=types.GenerateContentConfig(**config_kwargs)
            )
            log.debug("gemini %s took %.1fs", model, time.monotonic() - started)
        except errors.ClientError as exc:
            raise self._map_client_error(exc) from exc
        except errors.ServerError as exc:
            raise ProviderUnavailable(f"Gemini server error {exc.code}", provider=self.name) from exc
        except errors.APIError as exc:
            raise ProviderError(f"Gemini API error {getattr(exc, 'code', '')}", provider=self.name) from exc
        except Exception as exc:  # noqa: BLE001 - httpx timeouts surface as various types
            if "timeout" in type(exc).__name__.lower() or "timed out" in str(exc).lower():
                raise ProviderTimeout("Gemini request timed out", provider=self.name) from exc
            if isinstance(exc, (CapabilityError, NotConfigured)):
                raise
            raise ProviderUnavailable(f"Gemini request failed: {type(exc).__name__}", provider=self.name) from exc
        finally:
            for name in uploaded:
                self.delete_temporary_file(name)

        candidate = (resp.candidates or [None])[0]
        if candidate is None or candidate.content is None:
            reason = getattr(getattr(resp, "prompt_feedback", None), "block_reason", None)
            raise ProviderError(f"Gemini returned no content{f' (blocked: {reason})' if reason else ''}",
                                provider=self.name)
        calls = [
            ToolCall(id=fc.id or f"call_{i}", name=fc.name, arguments=dict(fc.args or {}))
            for i, fc in enumerate(resp.function_calls or [])
        ]
        text = "".join(p.text for p in (candidate.content.parts or []) if getattr(p, "text", None)
                       and not getattr(p, "thought", False))
        usage = resp.usage_metadata
        return AIResponse(
            provider=self.name, model=model, text=text, tool_calls=calls,
            input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
            output_tokens=int((getattr(usage, "candidates_token_count", 0) or 0)
                              + (getattr(usage, "thoughts_token_count", 0) or 0)),
            finish_reason=str(candidate.finish_reason) if candidate.finish_reason else None,
            provider_state=candidate.content,  # echoed back verbatim to preserve thought signatures
        )

    def _contents(self, messages: list[ChatMessage], uploaded: list[str]) -> list:
        """Build Gemini contents. All function responses answering one model turn go in a single user
        Content, each carrying the call id it answers."""
        from google.genai import types

        out: list = []
        pending_tool_parts: list = []
        for msg in messages:
            if msg.role == "tool":
                text = "".join(p.text for p in msg.parts if isinstance(p, TextPart))
                pending_tool_parts.append(types.Part(function_response=types.FunctionResponse(
                    id=msg.tool_call_id, name=msg.tool_name or "tool", response={"result": text})))
                continue
            if pending_tool_parts:
                out.append(types.Content(role="user", parts=pending_tool_parts))
                pending_tool_parts = []
            out.append(self._content(msg, uploaded))
        if pending_tool_parts:
            out.append(types.Content(role="user", parts=pending_tool_parts))
        return out

    def _content(self, msg: ChatMessage, uploaded: list[str]):
        from google.genai import types

        if msg.role == "assistant" and msg.provider_state is not None and msg.provider_state.__class__.__name__ == "Content":
            return msg.provider_state
        if msg.role == "tool":
            text = "".join(p.text for p in msg.parts if isinstance(p, TextPart))
            return types.Content(role="user", parts=[types.Part.from_function_response(
                name=msg.tool_name or "tool", response={"result": text})])
        if msg.role == "assistant":
            parts = [types.Part.from_text(text=p.text) for p in msg.parts if isinstance(p, TextPart)]
            for tc in msg.tool_calls:
                parts.append(types.Part.from_function_call(name=tc.name, args=tc.arguments))
            return types.Content(role="model", parts=parts or [types.Part.from_text(text="")])
        parts = []
        for p in msg.parts:
            if isinstance(p, TextPart):
                parts.append(types.Part.from_text(text=p.text))
            elif isinstance(p, ImagePart):
                parts.append(types.Part.from_bytes(data=p.data, mime_type=p.mime_type))
            elif isinstance(p, FilePart):
                if p.mime_type == "application/pdf" and len(p.data) <= INLINE_PDF_LIMIT:
                    parts.append(types.Part.from_bytes(data=p.data, mime_type=p.mime_type))
                else:
                    info = self.upload_temporary_file(p)
                    uploaded.append(info["name"])
                    parts.append(types.Part.from_uri(file_uri=info["uri"], mime_type=p.mime_type))
        return types.Content(role="user", parts=parts)

    def _map_client_error(self, exc):
        code = getattr(exc, "code", None)
        message = str(getattr(exc, "message", "") or exc)[:300]
        if code == 429:
            return QuotaExceeded(f"Gemini quota or rate limit reached: {message}", provider=self.name, retry_after=60)
        if code in (401, 403):
            return NotConfigured(f"Gemini rejected the API key ({code})", provider=self.name)
        if code == 404:
            return ProviderError(f"Gemini model not found: {message}", provider=self.name)
        return ProviderError(f"Gemini request rejected ({code}): {message}", provider=self.name)

    # Files API ----------------------------------------------------------------------------
    def upload_temporary_file(self, part: FilePart) -> dict:
        from google.genai import types

        from app.extensions import db
        from app.models import ProviderFile
        from app.utils.timeutil import utcnow

        f = self.client.files.upload(
            file=io.BytesIO(part.data),
            config=types.UploadFileConfig(mime_type=part.mime_type, display_name=part.filename[:100]),
        )
        deadline = time.monotonic() + 60
        while getattr(f, "state", None) is not None and str(f.state).endswith("PROCESSING") and time.monotonic() < deadline:
            time.sleep(1.5)
            f = self.client.files.get(name=f.name)
        if part.document_id:
            db.session.add(ProviderFile(
                document_id=part.document_id, provider=self.name, provider_file_id=f.name, provider_uri=f.uri,
                uploaded_at=utcnow(), expires_at=getattr(f, "expiration_time", None),
            ))
            db.session.flush()
        return {"name": f.name, "uri": f.uri}

    def delete_temporary_file(self, file_id: str) -> bool:
        from app.extensions import db
        from app.models import ProviderFile
        from app.utils.timeutil import utcnow

        try:
            self.client.files.delete(name=file_id)
            ok = True
        except Exception as exc:  # noqa: BLE001
            log.warning("could not delete Gemini file %s: %s", file_id, type(exc).__name__)
            ok = False
        row = db.session.execute(
            db.select(ProviderFile).where(ProviderFile.provider == self.name, ProviderFile.provider_file_id == file_id)
        ).scalar_one_or_none()
        if row:
            row.status = "deleted" if ok else "delete_failed"
            row.deleted_at = utcnow() if ok else None
            row.detail = "" if ok else "Deletion failed; Gemini removes files automatically after 48 hours"
        return ok

    def health_check(self) -> dict:
        if not self.configured():
            return {"state": "not_configured"}
        try:
            available = {m.name.removeprefix("models/") for m in self.client.models.list()}
        except Exception as exc:  # noqa: BLE001
            return {"state": "error", "detail": f"{type(exc).__name__}: {str(exc)[:200]}"}
        roles = {r: self.model_for(r) for r in ("extraction", "vision", "reasoning", "fast")}
        models = {r: {"id": m, "available": m in available} for r, m in roles.items() if m}
        state = "ok" if all(v["available"] for v in models.values()) else "model_missing"
        return {"state": state, "models": models}


def gemini_provider() -> GeminiProvider:
    return GeminiProvider(current_app.config)

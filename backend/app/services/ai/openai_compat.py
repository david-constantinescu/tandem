"""helperi comuni pt api-urile compatibile openai (z.ai, groq)"""
from __future__ import annotations

import base64
import json
import time

import httpx

from app.services.ai.base import (
    AIError, AIRequest, AIResponse, ChatMessage, FilePart, ImagePart, NotConfigured, ProviderError, ProviderTimeout,
    ProviderUnavailable, QuotaExceeded, TextPart, ToolCall,
)


def tools_payload(request: AIRequest) -> list[dict] | None:
    if not request.tools:
        return None
    return [
        {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
        for t in request.tools
    ]


def convert_messages(request: AIRequest, *, part_converter, system_suffix: str = "") -> list[dict]:
    out: list[dict] = []
    system = request.system + (("\n\n" + system_suffix) if system_suffix else "")
    if system.strip():
        out.append({"role": "system", "content": system})
    for msg in request.messages:
        out.extend(_convert_one(msg, part_converter))
    return out


def _convert_one(msg: ChatMessage, part_converter) -> list[dict]:
    if msg.role == "tool":
        text = "".join(p.text for p in msg.parts if isinstance(p, TextPart))
        return [{"role": "tool", "tool_call_id": msg.tool_call_id, "content": text}]
    if msg.role == "assistant":
        entry: dict = {"role": "assistant",
                       "content": "".join(p.text for p in msg.parts if isinstance(p, TextPart)) or None}
        if msg.tool_calls:
            entry["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                for tc in msg.tool_calls
            ]
        return [entry]
    parts = [part_converter(p) for p in msg.parts]
    if all(isinstance(p, TextPart) for p in msg.parts):
        return [{"role": "user", "content": "\n\n".join(p.text for p in msg.parts)}]
    return [{"role": "user", "content": parts}]


def image_data_url(part: ImagePart | FilePart, *, prefix: bool = True) -> str:
    encoded = base64.b64encode(part.data).decode()
    return f"data:{part.mime_type};base64,{encoded}" if prefix else encoded


def post_chat(provider: str, url: str, api_key: str, body: dict, timeout: float) -> tuple[dict, httpx.Response]:
    if not api_key:
        raise NotConfigured(f"{provider} API key is not configured", provider=provider)
    try:
        resp = httpx.post(url, json=body, timeout=timeout,
                          headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    except httpx.TimeoutException as exc:
        raise ProviderTimeout(f"{provider} request timed out", provider=provider) from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"{provider} is unreachable: {type(exc).__name__}", provider=provider) from exc
    if resp.status_code == 200:
        try:
            return resp.json(), resp
        except ValueError as exc:
            raise ProviderError(f"{provider} returned a non-JSON response", provider=provider) from exc
    raise map_http_error(provider, resp)


def map_http_error(provider: str, resp: httpx.Response) -> AIError:
    detail = ""
    code = None
    try:
        payload = resp.json()
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict):
            detail = str(err.get("message", ""))[:300]
            code = err.get("code")
        elif isinstance(err, str):
            detail = err[:300]
    except ValueError:
        detail = resp.text[:200]
    status = resp.status_code
    retry_after = None
    if "retry-after" in resp.headers:
        try:
            retry_after = float(resp.headers["retry-after"])
        except ValueError:
            retry_after = None
    label = f"{provider} HTTP {status}" + (f" ({code})" if code else "") + (f": {detail}" if detail else "")
    if status == 429:
        return QuotaExceeded(label, provider=provider, retry_after=retry_after or 60)
    if status in (401, 403):
        return NotConfigured(f"{provider} rejected the API key ({status})", provider=provider)
    if status >= 500:
        return ProviderUnavailable(label, provider=provider, retry_after=retry_after)
    return ProviderError(label, provider=provider)


def parse_chat_response(provider: str, model: str, payload: dict) -> AIResponse:
    choices = payload.get("choices") or []
    if not choices:
        raise ProviderError(f"{provider} returned no choices", provider=provider)
    choice = choices[0]
    message = choice.get("message") or {}
    calls = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {"__invalid_json__": fn.get("arguments")}
        calls.append(ToolCall(id=tc.get("id") or f"call_{len(calls)}", name=fn.get("name", ""), arguments=args))
    usage = payload.get("usage") or {}
    # reasoning_content (thinking traces) is deliberately discarded and never shown to users
    return AIResponse(
        provider=provider, model=model, text=message.get("content") or "", tool_calls=calls,
        input_tokens=int(usage.get("prompt_tokens") or 0), output_tokens=int(usage.get("completion_tokens") or 0),
        finish_reason=choice.get("finish_reason"),
    )


def health_ping(provider: str, url: str, api_key: str, model: str, timeout: float = 20) -> dict:
    started = time.monotonic()
    body = {"model": model, "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
            "max_tokens": 16}
    try:
        payload, _ = post_chat(provider, url, api_key, body, timeout)
        parse_chat_response(provider, model, payload)
        return {"model": model, "ok": True, "latency_ms": int((time.monotonic() - started) * 1000)}
    except AIError as exc:
        return {"model": model, "ok": False, "error": exc.code, "detail": str(exc)[:300]}

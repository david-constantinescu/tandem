"""Groq provider — strictly NON-FILE tasks.

Tandem never sends uploaded files (PDFs, screenshots, photos, audio) to Groq. This is enforced
twice: the router rejects any request that carries an original file or ingests a document, and
this provider refuses every message part that is not plain text, including text that embeds a
base64 data URL. A router bug therefore cannot leak a file to Groq.
"""
from __future__ import annotations

import re

from app.services.ai import registry
from app.services.ai.base import AIProvider, AIRequest, AIResponse, CapabilityError, TextPart
from app.services.ai.openai_compat import (
    convert_messages, health_ping, parse_chat_response, post_chat, tools_payload,
)
from app.services.ai.schema_utils import schema_prompt, strict_schema

_EMBEDDED_BINARY = re.compile(r"data:[\w.+-]+/[\w.+-]+;base64,[A-Za-z0-9+/=]{64,}")
FILE_TASKS = {"document_extraction", "document_text_extraction"}


class GroqProvider(AIProvider):
    name = "groq"
    supports_original_file_processing = False

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def configured(self) -> bool:
        return bool(self.cfg.get("GROQ_API_KEY"))

    def model_for(self, role):
        if role in ("vision", "document"):
            return None
        if role == "reasoning":
            return self.cfg.get("GROQ_REASONING_MODEL") or self.cfg.get("GROQ_TEXT_MODEL")
        return self.cfg.get("GROQ_TEXT_MODEL")

    def capabilities(self) -> dict:
        return {"text": True, "image_input": False, "pdf_input": False, "structured_output": "json_schema",
                "tools": True, "temporary_files": False, "original_file_processing": False}

    def assert_text_only(self, request: AIRequest) -> None:
        if request.task in FILE_TASKS:
            raise CapabilityError("Groq is restricted to non-file tasks", provider=self.name)
        for msg in request.messages:
            for part in msg.parts:
                if not isinstance(part, TextPart):
                    raise CapabilityError("Groq accepts plain text only; files and images are refused",
                                          provider=self.name)
                if _EMBEDDED_BINARY.search(part.text):
                    raise CapabilityError("Groq request contained embedded binary data", provider=self.name)

    def generate(self, request: AIRequest, model: str) -> AIResponse:
        self.assert_text_only(request)
        info = registry.lookup(self.name, model)
        body: dict = {"model": model, "temperature": request.temperature,
                      "max_completion_tokens": request.max_output_tokens}
        suffix = ""
        tools = tools_payload(request)
        if request.schema is not None and not tools:
            if info and info.structured == "json_schema":
                body["response_format"] = {"type": "json_schema", "json_schema": {
                    "name": request.schema.__name__, "strict": True, "schema": strict_schema(request.schema)}}
            else:
                body["response_format"] = {"type": "json_object"}
                suffix = schema_prompt(request.schema)
        body["messages"] = convert_messages(request, part_converter=lambda p: {"type": "text", "text": p.text},
                                            system_suffix=suffix)
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        payload, _ = post_chat(self.name, f"{self.cfg['GROQ_BASE_URL'].rstrip('/')}/chat/completions",
                               self.cfg.get("GROQ_API_KEY", ""), body, float(self.cfg["AI_REQUEST_TIMEOUT"]))
        return parse_chat_response(self.name, model, payload)

    def health_check(self) -> dict:
        if not self.configured():
            return {"state": "not_configured"}
        url = f"{self.cfg['GROQ_BASE_URL'].rstrip('/')}/chat/completions"
        result = health_ping(self.name, url, self.cfg["GROQ_API_KEY"], self.model_for("fast"))
        return {"state": "ok" if result["ok"] else "error", "models": {"text": result}}

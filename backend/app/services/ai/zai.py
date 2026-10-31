from __future__ import annotations
from app.services.ai import registry
from app.services.ai.base import (
    AIProvider, AIRequest, AIResponse, CapabilityError, FilePart, ImagePart, TextPart,
)
from app.services.ai.openai_compat import (
    convert_messages, health_ping, image_data_url, parse_chat_response, post_chat, tools_payload,
)
from app.services.ai.schema_utils import schema_prompt

ZAI_IMAGE_MIME = {"image/jpeg", "image/png", "image/jpg"}
ZAI_IMAGE_MAX_BYTES = 5 * 1024 * 1024


class ZaiProvider(AIProvider):
    name = "zai"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    @property
    def supports_original_file_processing(self) -> bool:  # type: ignore[override]
        return bool(self.cfg.get("AI_ALLOW_PAID_MODELS"))

    def configured(self) -> bool:
        return bool(self.cfg.get("ZAI_API_KEY"))

    def model_for(self, role):
        return {
            "extraction": self.cfg.get("ZAI_TEXT_MODEL"),
            "reasoning": self.cfg.get("ZAI_REASONING_MODEL"),
            "fast": self.cfg.get("ZAI_FAST_MODEL"),
            "vision": self.cfg.get("ZAI_VISION_MODEL"),
            "document": self.cfg.get("ZAI_DOCUMENT_MODEL"),
        }.get(role)

    def capabilities(self) -> dict:
        return {
            "text": True, "image_input": True, "pdf_input": self.supports_original_file_processing,
            "structured_output": "json_object (text models only)", "tools": True, "temporary_files": False,
            "original_file_processing": self.supports_original_file_processing,
        }

    def generate(self, request: AIRequest, model: str) -> AIResponse:
        info = registry.lookup(self.name, model)
        vision_request = request.has_images or request.has_files
        suffix = ""
        body: dict = {"model": model, "temperature": max(0.0, min(1.0, request.temperature)),
                      "max_tokens": request.max_output_tokens}
        if request.schema is not None and not request.tools:
            suffix = schema_prompt(request.schema)
            if not vision_request and info and info.structured == "json_object":
                body["response_format"] = {"type": "json_object"}
        body["messages"] = convert_messages(request, part_converter=self._part, system_suffix=suffix)
        tools = tools_payload(request)
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"  # nu accepta nimic altceva decat auto idk
        payload, _ = post_chat(self.name, f"{self.cfg['ZAI_BASE_URL'].rstrip('/')}/chat/completions",
                               self.cfg.get("ZAI_API_KEY", ""), body,
                               max(3.0, min(float(self.cfg["AI_REQUEST_TIMEOUT"]), request.remaining if request.remaining is not None else 1e9)))
        return parse_chat_response(self.name, model, payload)

    def _part(self, part):
        if isinstance(part, TextPart):
            return {"type": "text", "text": part.text}
        if isinstance(part, ImagePart):
            if part.mime_type not in ZAI_IMAGE_MIME:
                raise CapabilityError(f"Z.ai vision accepts jpg/png only, not {part.mime_type}", provider=self.name)
            if len(part.data) > ZAI_IMAGE_MAX_BYTES:
                raise CapabilityError("Image exceeds Z.ai's 5 MB limit", provider=self.name)
            return {"type": "image_url",
                    "image_url": {"url": image_data_url(part, prefix=bool(self.cfg.get("ZAI_IMAGE_DATA_URL", True)))}}
        if isinstance(part, FilePart):
            if not self.supports_original_file_processing:
                raise CapabilityError("Z.ai file input requires a paid model; paid models are disabled",
                                      provider=self.name)
            return {"type": "file", "file": {"file_data": image_data_url(part, prefix=True)}}
        raise CapabilityError("Unsupported message part", provider=self.name)

    def health_check(self) -> dict:
        if not self.configured():
            return {"state": "not_configured"}
        url = f"{self.cfg['ZAI_BASE_URL'].rstrip('/')}/chat/completions"
        result = health_ping(self.name, url, self.cfg["ZAI_API_KEY"], self.model_for("extraction"))
        return {"state": "ok" if result["ok"] else "error", "models": {"text": result}}

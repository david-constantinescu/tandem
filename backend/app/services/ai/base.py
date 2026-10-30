"""Provider-neutral AI request/response types and the AIProvider interface."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

# Tasks the router understands. Groq is never eligible for tasks that carry or ingest documents.
TASK_DOCUMENT_EXTRACTION = "document_extraction"  # original file (PDF/image) sent to a provider
TASK_DOCUMENT_TEXT_EXTRACTION = "document_text_extraction"  # text we extracted locally from a file
TASK_TEXT_EXTRACTION = "text_extraction"  # user-pasted text (not from a file)
TASK_CLASSIFICATION = "classification"
TASK_SUMMARY = "summary"
TASK_EXPLANATION = "explanation"
TASK_AGENT = "agent"
TASKS = (
    TASK_DOCUMENT_EXTRACTION, TASK_DOCUMENT_TEXT_EXTRACTION, TASK_TEXT_EXTRACTION, TASK_CLASSIFICATION,
    TASK_SUMMARY, TASK_EXPLANATION, TASK_AGENT,
)

ModelRole = Literal["extraction", "reasoning", "vision", "fast", "document"]


@dataclass
class TextPart:
    text: str


@dataclass
class ImagePart:
    data: bytes
    mime_type: str
    label: str = ""


@dataclass
class FilePart:
    """An original uploaded file (e.g. PDF). Only providers with official document support may receive it."""

    data: bytes
    mime_type: str
    filename: str
    document_id: uuid.UUID | None = None


Part = TextPart | ImagePart | FilePart


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatMessage:
    role: Literal["user", "assistant", "tool"]
    parts: list[Part] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None
    # Opaque provider-specific data that must be echoed back (e.g. Gemini thought signatures)
    provider_state: Any = None

    @staticmethod
    def user(text: str) -> "ChatMessage":
        return ChatMessage(role="user", parts=[TextPart(text)])


@dataclass
class AIRequest:
    task: str
    system: str
    messages: list[ChatMessage]
    schema: type[BaseModel] | None = None
    tools: list[ToolSpec] | None = None
    role: ModelRole = "reasoning"
    temperature: float = 0.1
    max_output_tokens: int = 4096
    user_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    cacheable: bool = False

    @property
    def has_images(self) -> bool:
        return any(isinstance(p, ImagePart) for m in self.messages for p in m.parts)

    @property
    def has_files(self) -> bool:
        return any(isinstance(p, FilePart) for m in self.messages for p in m.parts)

    @property
    def contains_original_file(self) -> bool:
        return self.has_images or self.has_files

    @property
    def file_mime_types(self) -> set[str]:
        return {p.mime_type for m in self.messages for p in m.parts if isinstance(p, (ImagePart, FilePart))}


@dataclass
class AIResponse:
    provider: str
    model: str
    text: str = ""
    data: dict | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str | None = None
    provider_state: Any = None


class AIError(Exception):
    code = "ai_error"
    retryable = False

    def __init__(self, message: str, *, provider: str | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.provider = provider
        self.retry_after = retry_after


class CapabilityError(AIError):
    code = "capability_unsupported"


class NotConfigured(AIError):
    code = "not_configured"


class ConsentRequired(AIError):
    code = "consent_required"


class PaidModelBlocked(AIError):
    code = "paid_model_blocked"


class QuotaExceeded(AIError):
    code = "quota_exceeded"
    retryable = True


class ProviderTimeout(AIError):
    code = "timeout"
    retryable = True


class ProviderUnavailable(AIError):
    code = "provider_unavailable"
    retryable = True


class ProviderError(AIError):
    code = "provider_error"


class InvalidOutput(AIError):
    code = "invalid_output"


class NoProviderAvailable(AIError):
    code = "no_provider_available"


class AIProvider:
    """Common interface. Providers implement `generate`; the convenience methods enforce capabilities."""

    name: str = "base"
    # Hard architectural flag checked by the router *and* by the provider itself.
    supports_original_file_processing: bool = False

    def configured(self) -> bool:
        raise NotImplementedError

    def model_for(self, role: ModelRole) -> str | None:
        raise NotImplementedError

    def capabilities(self) -> dict:
        raise NotImplementedError

    def generate(self, request: AIRequest, model: str) -> AIResponse:
        raise NotImplementedError

    # Convenience wrappers mirroring the specification's interface -------------------------
    def generate_text(self, request: AIRequest) -> AIResponse:
        return self.generate(request, self._require_model(request.role))

    def generate_structured(self, request: AIRequest, schema: type[BaseModel]) -> AIResponse:
        request.schema = schema
        return self.generate(request, self._require_model(request.role))

    def analyze_image(self, request: AIRequest) -> AIResponse:
        if not self.capabilities().get("image_input"):
            raise CapabilityError(f"{self.name} does not accept image input", provider=self.name)
        return self.generate(request, self._require_model("vision"))

    def analyze_document(self, request: AIRequest) -> AIResponse:
        if not self.supports_original_file_processing:
            raise CapabilityError(f"{self.name} does not process original documents", provider=self.name)
        return self.generate(request, self._require_model("document"))

    def transcribe_audio(self, request: AIRequest) -> AIResponse:
        raise CapabilityError(f"Audio transcription is not enabled for {self.name}", provider=self.name)

    def call_tools(self, request: AIRequest, tools: list[ToolSpec]) -> AIResponse:
        request.tools = tools
        return self.generate(request, self._require_model(request.role))

    def upload_temporary_file(self, part: FilePart) -> dict:
        raise CapabilityError(f"{self.name} has no temporary file storage", provider=self.name)

    def delete_temporary_file(self, file_id: str) -> bool:
        raise CapabilityError(f"{self.name} has no temporary file storage", provider=self.name)

    def health_check(self) -> dict:
        raise NotImplementedError

    def _require_model(self, role: ModelRole) -> str:
        model = self.model_for(role)
        if not model:
            raise CapabilityError(f"{self.name} has no model configured for role '{role}'", provider=self.name)
        return model

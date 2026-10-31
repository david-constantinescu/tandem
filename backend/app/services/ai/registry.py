"""ce stie fiecare model si daca e gratis. modelele necunoscute sunt blocate (pot fi platite)"""
from __future__ import annotations

from dataclasses import dataclass, field

VERIFIED_ON = "2026-10-30"

GEMINI_MODELS_URL = "https://ai.google.dev/gemini-api/docs/models"
GEMINI_PRICING_URL = "https://ai.google.dev/gemini-api/docs/pricing"
ZAI_PRICING_URL = "https://docs.z.ai/guides/overview/pricing"
ZAI_CHAT_URL = "https://docs.z.ai/api-reference/llm/chat-completion"
GROQ_MODELS_URL = "https://console.groq.com/docs/models"
GROQ_STRUCTURED_URL = "https://console.groq.com/docs/structured-outputs"


@dataclass(frozen=True)
class ModelInfo:
    provider: str
    id: str
    free_tier: bool
    inputs: frozenset[str]  # text | image | pdf | audio | video | office_docs
    structured: str | None  # response_schema | json_schema | json_object | None
    tools: bool
    structured_with_tools: bool
    context_tokens: int | None
    source: str
    id_verified: bool = True  # the exact API identifier appeared in official docs
    notes: tuple[str, ...] = field(default_factory=tuple)
    # USD per 1M tokens on the paid tier (for estimates); None when free-only or unknown
    input_price: float | None = None
    output_price: float | None = None


_ALL_MEDIA = frozenset({"text", "image", "pdf", "audio", "video"})

MODELS: dict[tuple[str, str], ModelInfo] = {}


def _add(info: ModelInfo) -> None:
    MODELS[(info.provider, info.id)] = info


# --- Gemini (Google AI) ---------------------------------------------------------------
for _mid, _note in (
    ("gemini-3.8-flash", "Newest Flash. Thinking levels low/medium/high; 'minimal' is rejected."),
    ("gemini-3.6-flash", "Previous-generation Flash, still supported for production."),
    ("gemini-3.5-flash", "Flash from the 3.5 generation; answers in ~2 s and has its own free-tier quota."),
    ("gemini-3.5-flash-lite", "Lowest-cost Flash-Lite; used for quick classification."),
):
    _add(ModelInfo(
        provider="gemini", id=_mid, free_tier=True, inputs=_ALL_MEDIA, structured="response_schema", tools=True,
        structured_with_tools=False, context_tokens=1_048_576, source=GEMINI_MODELS_URL,
        notes=(_note, "Free-tier prompts and responses may be used by Google to improve its products."),
    ))
for _mid, _note in (
    ("gemini-2.5-flash", "Stable Flash with a free tier; the default for the assistant because the 3.x previews are "
                         "often at capacity (HTTP 503). Verified with a live key on 2026-10-31."),
    ("gemini-2.5-flash-lite", "Stable Flash-Lite with a free tier, for quick classification."),
):
    _add(ModelInfo(
        provider="gemini", id=_mid, free_tier=True, inputs=_ALL_MEDIA, structured="response_schema", tools=True,
        structured_with_tools=False, context_tokens=1_048_576, source=GEMINI_PRICING_URL,
        notes=(_note, "Free-tier prompts and responses may be used by Google to improve its products."),
    ))
_add(ModelInfo(
    provider="gemini", id="gemini-3.1-flash-lite", free_tier=True, inputs=_ALL_MEDIA, structured="response_schema",
    tools=True, structured_with_tools=False, context_tokens=None, source=GEMINI_PRICING_URL,
    notes=("Free tier listed on pricing page; capabilities assumed from the Flash-Lite family.",),
))
_add(ModelInfo(
    provider="gemini", id="gemini-3.1-pro-preview", free_tier=False, inputs=_ALL_MEDIA, structured="response_schema",
    tools=True, structured_with_tools=False, context_tokens=None, source=GEMINI_PRICING_URL,
    notes=("No free tier.",),
))
_add(ModelInfo(
    provider="gemini", id="gemini-embedding-001", free_tier=True, inputs=frozenset({"text"}), structured=None,
    tools=False, structured_with_tools=False, context_tokens=None, source=GEMINI_PRICING_URL,
))

# --- Z.ai (GLM) -----------------------------------------------------------------------
_add(ModelInfo(
    provider="zai", id="glm-4.7-flash", free_tier=True, inputs=frozenset({"text"}), structured="json_object",
    tools=True, structured_with_tools=False, context_tokens=None, source=ZAI_PRICING_URL, id_verified=False,
    notes=("Listed as free on the pricing page; the lowercase API id is inferred and checked by the health check.",
           "GLM-4.7 always produces reasoning_content, which Tandem discards."),
))
_add(ModelInfo(
    provider="zai", id="glm-4.5-flash", free_tier=True, inputs=frozenset({"text"}), structured="json_object",
    tools=True, structured_with_tools=False, context_tokens=None, source=ZAI_PRICING_URL, id_verified=False,
))
_add(ModelInfo(
    provider="zai", id="glm-4.6v-flash", free_tier=True, inputs=frozenset({"text", "image"}), structured=None,
    tools=True, structured_with_tools=False, context_tokens=None, source=ZAI_PRICING_URL, id_verified=False,
    notes=("Free vision model. Images up to 5 MB, jpg/png only. No response_format on vision requests, "
           "so JSON is requested in the prompt and validated.",),
))
_add(ModelInfo(
    provider="zai", id="glm-5.3-flash", free_tier=False, inputs=frozenset({"text", "image", "pdf", "office_docs"}),
    structured=None, tools=True, structured_with_tools=False, context_tokens=None, source=ZAI_CHAT_URL,
    notes=("Paid. The only documented Z.ai family accepting file inputs (pdf, txt, word...) via file_data.",),
    input_price=0.15, output_price=0.50,
))
_add(ModelInfo(
    provider="zai", id="glm-5.3", free_tier=False, inputs=frozenset({"text"}), structured="json_object", tools=True,
    structured_with_tools=False, context_tokens=None, source=ZAI_CHAT_URL, input_price=1.4, output_price=4.4,
))
_add(ModelInfo(
    provider="zai", id="glm-4.6v", free_tier=False, inputs=frozenset({"text", "image"}), structured=None, tools=True,
    structured_with_tools=False, context_tokens=None, source=ZAI_PRICING_URL, input_price=0.3, output_price=0.9,
))

# --- Groq (text only in Tandem) -------------------------------------------------------
for _mid in ("openai/gpt-oss-20b", "openai/gpt-oss-120b"):
    _add(ModelInfo(
        provider="groq", id=_mid, free_tier=True, inputs=frozenset({"text"}), structured="json_schema", tools=True,
        structured_with_tools=False, context_tokens=131_072, source=GROQ_STRUCTURED_URL,
        notes=("Strict json_schema supported; not combinable with tools or streaming.",
               "Developer-plan base limit ~8K tokens/minute: suited to short text tasks only."),
    ))
for _mid in ("llama-3.1-8b-instant", "llama-3.3-70b-versatile"):
    _add(ModelInfo(
        provider="groq", id=_mid, free_tier=True, inputs=frozenset({"text"}), structured="json_object", tools=True,
        structured_with_tools=False, context_tokens=131_072, source=GROQ_MODELS_URL,
    ))


def lookup(provider: str, model_id: str | None) -> ModelInfo | None:
    if not model_id:
        return None
    info = MODELS.get((provider, model_id))
    if info is None and provider == "gemini":
        # modelele Flash/Flash-Lite noi apar des si toate au tier gratuit, citesc text/poze/PDF si stiu tools
        # le acceptam dupa nume ca sa nu actualizam registrul la fiecare lansare Google
        from app.services.ai.gemini_models import PATTERN

        if PATTERN.match(model_id):
            info = ModelInfo(provider="gemini", id=model_id, free_tier=True, inputs=_ALL_MEDIA, structured="response_schema",
                             tools=True, structured_with_tools=False, context_tokens=1_048_576, source=GEMINI_MODELS_URL,
                             id_verified=False, notes=("Picked automatically from Google's model list.",))
    return info


def is_free(provider: str, model_id: str) -> bool:
    info = lookup(provider, model_id)
    return bool(info and info.free_tier)


def estimate_cost(provider: str, model_id: str, input_tokens: int, output_tokens: int) -> float | None:
    info = lookup(provider, model_id)
    if info is None:
        return None
    if info.free_tier:
        return 0.0
    if info.input_price is None or info.output_price is None:
        return None
    return round(input_tokens / 1e6 * info.input_price + output_tokens / 1e6 * info.output_price, 6)

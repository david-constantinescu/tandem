# AI provider configuration

Model information was verified against official documentation on **2026-10-30** and is encoded in
`backend/app/services/ai/registry.py` (provider, ID, free tier, input modalities, structured-output
mode, tool support, source URL). Re-verify and update the registry when providers change catalogues.

## Verified catalogue (2026-10-30)

### Gemini — primary for files and multimodal ([models](https://ai.google.dev/gemini-api/docs/models), [pricing](https://ai.google.dev/gemini-api/docs/pricing))

| Model | Free tier | Inputs | Structured output | Function calling | Context |
|---|---|---|---|---|---|
| `gemini-3.8-flash` (default extraction/vision/reasoning) | Yes | text, image, video, audio, PDF | Yes | Yes | 1,048,576 |
| `gemini-3.6-flash` | Yes | same | Yes | Yes | 1,048,576 |
| `gemini-3.5-flash-lite` (default fast) | Yes | same | Yes | Yes | 1,048,576 |
| `gemini-3.1-pro-preview` | **No** | — | — | — | blocked unless paid enabled |

- Gemini 3.x uses `thinking_level`; `gemini-3.8-flash` rejects `minimal`, so Tandem sends `low`.
- Free-tier rate limits are not published per model; they are shown in AI Studio. A 429 puts the
  provider into a cooldown (recorded in `provider_status`) and the router fails over.
- Files API: 2 GB per file, 20 GB per project, files kept 48 h; PDFs over 50 MB need the Files API.
  Tandem sends PDFs ≤ 15 MB inline and larger ones via the Files API, records each temporary file in
  `provider_files`, and deletes it right after the request.
- **Free-tier data may be used by Google to improve its products** (see AI_PRIVACY.md).

### Z.ai (GLM) ([pricing](https://docs.z.ai/guides/overview/pricing), [chat API](https://docs.z.ai/api-reference/llm/chat-completion))

| Model | Free | Use in Tandem |
|---|---|---|
| `glm-4.7-flash` | Yes | text extraction, reasoning, assistant fallback |
| `glm-4.5-flash` | Yes | fast text |
| `glm-4.6v-flash` | Yes | images (jpg/png ≤ 5 MB) |
| `glm-5.3-flash` | **No** | the only documented family with file input (PDF/Word via `file_data`); used for PDFs only when `AI_ALLOW_PAID_MODELS=true` |

- The free model names come from the pricing page; their lowercase API identifiers are not listed in
  the API reference enum, so they are marked "ID checked at runtime". Run `flask check-providers`.
- `response_format` supports only `json_object` and only on text models; `tool_choice` only `auto`.
  GLM-4.7 always produces `reasoning_content`, which Tandem discards.

### Groq — text only ([models](https://console.groq.com/docs/models), [structured outputs](https://console.groq.com/docs/structured-outputs))

| Model | Use |
|---|---|
| `openai/gpt-oss-20b` (default) | summaries, explanations, classification, pasted-text extraction, assistant last resort |
| `openai/gpt-oss-120b` | reasoning role |

- Strict `json_schema` is supported but not together with tools or streaming.
- Developer-plan base limit for gpt-oss models is ~8K tokens/minute, so Groq is ordered last for the agent.
- **Never used for files.** See below.

## Routing rules (enforced in `router.py`)

1. User consent mode: `off` → no external AI; `text_only` → no request containing an original file;
   `full` → files allowed to providers that support them. Per-provider toggles are honoured.
2. Model must be in the registry and free, unless `AI_ALLOW_PAID_MODELS=true`. Unknown IDs are blocked.
3. Model must support the request's modalities (image / PDF / office docs) and tools if requested.
4. **Groq restriction:** rejected for any request containing an image or file part and for the
   `document_extraction` / `document_text_extraction` tasks. `GroqProvider` itself also refuses any
   non-text part and any text embedding a base64 data URL.
5. Providers in quota cooldown are skipped. Retryable errors (timeouts, 5xx) are retried
   `AI_MAX_RETRIES` times with backoff; invalid JSON gets one repair attempt; then the next eligible
   provider is tried (`AI_ENABLE_FALLBACK`).
6. Every attempt is written to `ai_usage_records` (tokens, latency, status, estimated cost).

Default order by task: document extraction → Gemini, Z.ai; pasted text → Gemini, Z.ai, Groq;
summaries/explanations → Groq, Gemini, Z.ai; agent → Gemini, Z.ai, Groq. A user's preferred provider
(or `AI_DEFAULT_PROVIDER`) is tried first when eligible.

## Document fallback chain

1. Original PDF/image → Gemini (or Z.ai vision for images).
2. Scanned PDF → rendered page images → vision-capable provider.
3. Locally extracted text (PyMuPDF / Tesseract) → Gemini or Z.ai text models (never Groq).
4. Local rules parser (no network).

## Environment variables

See `.env.example`. Model IDs are configurable per role (`GEMINI_EXTRACTION_MODEL`,
`GEMINI_VISION_MODEL`, `GEMINI_REASONING_MODEL`, `GEMINI_FAST_MODEL`, `ZAI_*_MODEL`, `GROQ_*_MODEL`).

## Health check

`flask --app app check-providers` lists Gemini models via `models.list()` (marking each configured
ID present/missing) and sends a tiny request to Z.ai and Groq. Results are stored in `provider_status`
and shown in Settings → AI & privacy.

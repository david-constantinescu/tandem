# AI privacy

Travel documents contain personal data (names, booking references, addresses, sometimes ticket
numbers). Tandem gives each user control over what leaves Tandem, and enforces it in the router.

## User modes (Settings → AI & privacy)

| Mode | What can be sent | Default |
|---|---|---|
| **Off — local only** | Nothing. Documents are read by Tandem's parser and Tesseract OCR on the server. The assistant runs in offline mode. | Yes, for new accounts |
| **Text only** | Text Tandem extracted on its own servers. Original files never leave Tandem. | |
| **Files and text** | Original PDFs/images to providers that officially support them (Gemini; Z.ai vision for images). Never to Groq. | |

Enabling text or file processing requires ticking an acknowledgement; the consent time is stored.
Demo workspaces (fictional data) use files-and-text when `DEMO_ALLOW_EXTERNAL_AI=true`.

## What users are told before enabling

- On the **Gemini free tier, prompts and files may be used by Google to improve its products** and may
  be seen by human reviewers (pricing page: "Used to improve our products: Yes" for free models).
- **Gemini Files API** keeps uploaded files for up to 48 hours. Tandem deletes its temporary copies
  right after processing; if deletion fails it is recorded and the file expires on Google's side.
- **Z.ai and Groq** process requests under their own terms and retention policies. Tandem does not
  claim they delete data beyond what their documentation states.
- Tandem uses free-tier models only (unless the administrator enables paid models). If the API key
  belongs to a Google Cloud project with billing enabled, Google may bill that usage — Tandem cannot
  detect this; administrators should use a non-billed project for the free tier.

## Tandem's own retention

- Originals are stored privately, encrypted with the application key, and are only downloadable by
  their owner through an authenticated endpoint. Users can turn off "Keep original documents" to have
  originals deleted after extraction.
- Extracted text and evidence quotes are encrypted at rest.
- Deleting a document deletes its stored file; deleting the account deletes all data and revokes
  connected accounts. Export is available as a ZIP of JSON.

## Caching

AI outputs for documents are **not cached** (per-user checksum de-duplication already prevents
re-analysis). The AI response cache, when used for other tasks, is keyed by user and never shared
across accounts. Geocoding and OpenStreetMap caches hold public place data only.

## Minimisation

- Only the document being processed is sent; the assistant receives trip data through tool results
  scoped to the user, and document excerpts are marked as untrusted data.
- Logs never contain document contents, prompts, tokens or passwords.
- Email bodies imported from Gmail are not logged and are not used for unrelated AI tasks.

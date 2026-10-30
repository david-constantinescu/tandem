# Document ingestion

## Supported inputs (implemented and tested)

PDF (text and scanned), JPG/JPEG, PNG, WEBP (screenshots and photos), TXT, HTML, EML (with
attachments processed as child documents), DOCX, pasted text, URLs (HTML, text, PDF, images), and
Gmail messages imported as EML. Audio is **not** supported in this version.

## Pipeline

**Intake (request):** authenticate → ownership of target trip → sanitise filename → extension
allow-list → declared MIME consistent with extension → magic-byte signature (`filetype`; DOCX must be
a ZIP with Word parts; text files must not contain binary) → size limit (`MAX_UPLOAD_BYTES`, default
20 MB; ≤ 10 files per upload) → SHA-256 → duplicate check per user (duplicates are recorded and not
reprocessed) → encrypted private storage → `documents` row → `process_document` job.

**Processing (worker):**
1. `processing` — local extraction: PyMuPDF text per page; pages with < 40 characters are rendered at
   200 dpi and OCR'd with Tesseract; images are EXIF-rotated, bounded to 3072 px and OCR'd; DOCX
   paragraphs/tables; HTML → text (scripts/styles removed); EML headers + body, attachments queued.
2. `analysing` — extraction via the AI router (see AI_PROVIDER_CONFIGURATION) with the structured
   schema in `ingestion/schema.py`, falling back to the local rules parser.
3. Normalisation (`normalize.py`): resolve places (airport codes, curated cities, Nominatim when
   enabled), choose IANA zones (stated zone cross-checked against location), convert local wall-clock
   times to UTC with DST gap/fold notes, compute cancellation deadlines.
4. **Evidence verification:** booking reference, flight/train number, start/end date+time and price
   must appear in the text Tandem extracted. Missing values are marked `not_found_in_source`, listed in
   the notes and reduce confidence by 30 %. End times computed from a printed duration are `derived`.
5. Change detection: a record with the same booking reference and type as an existing reservation is
   diffed. Differences create a pending `reservation_change`; identical records are marked as already
   known. If the update doesn't state a location, its times are read in the existing booking's zone.
6. Grouping proposal for new records (see below), notifications, status `awaiting_review` or `processed`.
7. Originals are deleted afterwards if the user disabled retention.

Failures retry with backoff (3 attempts) and then mark the document `failed` with a notification.

## Structured schema

`ExtractionResult { is_travel_related, document_summary, records[] }`; each `ExtractedTravelRecord`
has type, title, provider, booking reference, confirmation status, origin/destination (+codes),
`start_local`/`end_local` as printed (no offset), optional stated zones, date-ambiguity note, location,
address, city, travellers, price/currency, website/contact, cancellation deadline/policy, change and
cancellation flags, details (airline, flight number, seat, terminal, gate, baggage, ticket number,
room, guests, party size, meeting point, check-in/out times…), confidence, uncertainty notes and
`evidence[] {field, quote, page}`. Prompt version: `extract-v1`.

## Local rules parser

`local_parser.py` classifies the document by keyword signals and reads labelled fields
("Booking reference:", "Check-in:", "Departure:", …) including label-on-one-line/value-on-next
layouts produced by PDFs. It supports multi-segment flights (one record per flight number with its
own airports, times and seat), hotels, trains, restaurants, museums, tours and generic tickets, and
dates in ISO, "12 Nov 2026", "November 12, 2026" and numeric forms (ambiguous day/month flagged).
Confidence is capped at 0.75 and every record says it was read without AI.

## Review and correction

Users see each field with its verification badge and source quote, can correct any field (local times
are re-converted with the chosen zone), choose the trip (suggested, another, new, none) or dismiss
the record. Accepted records become reservations and itinerary events; trips' dates and destinations
are recomputed and conflicts re-checked. Optional **auto-organise** accepts only records with
confidence ≥ 0.85, no notes and verified key fields.

## Trip grouping

`trips/grouping.py` scores each trip: shared booking reference (+0.6, sufficient alone), dates within
the trip ±1 day (+0.35) or ±4 days (+0.15), same destination city or within 60 km (+0.4/+0.35), same
traveller (+0.05). Dates alone never group (capped at 0.3). Join threshold 0.6; otherwise a new trip
is proposed from the record's destination (arrival city for outbound transport; departure city when
arriving home) and dates. Reasons are stored and shown; records can be moved later.

Grouping is re-evaluated when a record is accepted (unless the user explicitly picks a trip or "New
trip"), and every other pending record's proposal is refreshed afterwards. So a flight and hotel
uploaded together into an empty account produce **one** trip: the first acceptance creates it and the
rest then propose joining it. The trip's starting city (first journey's departure) is never added as
a destination.

## URL import

SSRF protections: http/https only, ports 80/443, no embedded credentials, every hop (including
redirects, max 3) must resolve only to public addresses, 10 s timeout, 5 MB cap, allowed content types
only. Links found inside documents are never fetched automatically.

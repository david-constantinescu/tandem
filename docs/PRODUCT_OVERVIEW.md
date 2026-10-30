# Product overview

Tandem turns scattered travel information into one organised, continuously updated travel workspace.
It is exclusively a travel product.

## Core workflow

Document → verified extracted information → reservation → trip → itinerary → conflict detection →
assistant → activity discovery → booking proposal → user approval → supported external action →
verified result.

## Areas

| Area | What it does |
|---|---|
| **Home** | Next trip with countdown, next events, alerts, suggestions, pending approvals, inbox activity, quick actions |
| **Trips** | Current, upcoming and past trips; each with itinerary timeline, reservations, alerts, map, documents and notes |
| **Inbox** | Upload (drag & drop, multiple files), paste text, import a link, Gmail candidates; processing status; review with evidence and corrections |
| **Discover** | Activity search across available providers, itinerary-aware fit, saved activities, booking proposals |
| **Assistant** | Conversations with trip context; visible tool use; activity cards and approval cards inline |
| **Approvals** | Proposals awaiting a decision and the history of executed, failed and rejected actions |
| **Settings** | Profile and preferences, AI & privacy, API usage, connected accounts and provider states, notifications, storage, sessions/password, export and account deletion |

## Principles in practice

- **Accuracy over apparent intelligence.** Every extracted value keeps the quote it came from; booking
  references, flight numbers, dates, times and prices are checked against the document text and
  flagged when absent. Records are reviewed before they become reservations (optional
  auto-organise only for fully verified, high-confidence records).
- **Real functionality.** Providers show their true capability state (e.g. "awaiting partner
  approval"); there are no fake results. Without partner credentials, discovery uses
  OpenStreetMap place listings labelled "availability unknown"; the demo uses a clearly labelled simulator.
- **User autonomy.** Routine organisation is automatic (extraction, grouping proposals, conflict
  checks, suggestions). Booking, money, changes to confirmed plans and sharing data with providers
  require explicit approval bound to the exact payload.
- **Clear action reporting.** Actions move through suggested → prepared → awaiting approval → in
  progress → completed / failed / requires manual intervention, and are only "completed" after the
  provider's own record is read back and matches.

## Status vocabulary

Itinerary events: confirmed, pending, suggested, not booked, cancelled, completed.
Inbox items: uploaded, validating, queued, processing, analysing, awaiting review, processed, failed,
duplicate, ignored.

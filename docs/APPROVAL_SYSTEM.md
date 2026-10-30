# Approval system

Implemented in `services/agent/approvals.py`; API in `api/approvals.py`; UI: approval cards in the
assistant, Discover, Home and the Approvals page.

## Action types

| Type | Created by | External | Executes |
|---|---|---|---|
| `book_activity` | Discover "Prepare booking" or assistant `create_booking_proposal` | yes | provider booking via adapter |
| `itinerary_update` / `itinerary_delete` / `itinerary_create` | assistant, for confirmed plans | no | Tandem itinerary only |
| `apply_reservation_change` | reserved for assistant-proposed updates | no | applies a detected change |
| `link_out` | when a provider is redirect-only | no | nothing — shows the provider link (`requires_manual`) |

## Statuses

suggested · prepared · **awaiting_approval** · **in_progress** · **completed** · **failed** ·
**requires_manual** · rejected · expired · cancelled.

## Proposal contents

Action type, provider, title, description, exact payload (item, date, local time + zone,
participants, unit/total price, currency, quote reference and time, address, lead traveller name),
cost, cancellation policy, user-visible consequences (what is booked, what is charged — "simulated"
in the demo — and that the lead traveller's name is shared), expiry (30 min for quotes), idempotency key.

## Rules

1. **Approval is bound to the payload.** The client must send the `payload_hash` it displayed; a
   mismatch returns 409. Approvals record the hash they approved.
2. Only `awaiting_approval`, unexpired actions can be approved. Rejected/expired/completed actions
   cannot be re-approved (no double booking).
3. **Re-quote at execution.** If availability, time, price or currency changed, the payload and hash are
   updated, the action returns to `awaiting_approval`, and the user is notified to approve again.
   Execution checks for an approval matching the *current* hash.
4. **Idempotent submission:** the provider receives the action's idempotency key.
5. **Verification:** the booking is read back from the provider (`get_booking`); it must be confirmed
   and match item, date, time and participants. Only then is the action `completed`, a
   `provider_booking` recorded (`verified_at`), a confirmed reservation created
   (`verification = verified`) and the itinerary/conflicts updated. A replaced suggestion is removed.
6. **Uncertainty is never success:** a retryable failure after submission (timeout) or a read-back
   mismatch → `requires_manual` with instructions to check with the provider. A provider decline →
   `failed`, nothing recorded.
7. The model cannot approve or execute; there is no such tool. Chat replies like "sounds good" have no
   effect on actions.
8. External actions run in the worker (`execute_action` job); internal ones run in the request.
   Everything is audited.

All of the above is covered by tests (`tests/test_workflow.py`, `tests/test_agent_approvals.py`).

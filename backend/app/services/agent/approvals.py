"""Action proposals, approvals and verified execution.

Rules enforced here (never by prompts):
  * consequential actions start as `awaiting_approval` and run only after the user approves the exact
    payload (the approval is bound to the payload hash);
  * external bookings are re-quoted at execution time; any change in price, time or availability sends
    the action back for a fresh approval;
  * a booking is `completed` only after the provider's own record is read back and matches;
  * an uncertain outcome (e.g. timeout after submission) becomes `requires_manual`, never `completed`;
  * the AI model can create proposals and read their status, but cannot approve or execute them.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import AgentAction, Approval, ItineraryEvent, ProviderBooking, ReservationChange, Trip, User
from app.services.audit import audit
from app.services.notifications.service import notify
from app.services.providers.base import ProviderCapabilityError, ProviderRequestError
from app.services.providers.registry import get_adapter
from app.services.trips import service as trips
from app.tasks.queue import enqueue, run_inline_if_configured
from app.utils.errors import Conflict, ValidationFailed
from app.utils.timeutil import iso, localize, utcnow

log = logging.getLogger("tandem.approvals")
APPROVAL_TTL = timedelta(minutes=30)
CATEGORY_TO_TYPE = {"museums": "museum", "tours": "tour", "food": "activity", "workshops": "activity",
                    "outdoor": "activity", "entertainment": "event", "day trips": "tour", "historical": "tour"}


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _new_action(user: User, **kwargs) -> AgentAction:
    payload = kwargs.pop("payload")
    action = AgentAction(user_id=user.id, payload=payload, payload_hash=payload_hash(payload),
                         idempotency_key=secrets.token_hex(16), **kwargs)
    db.session.add(action)
    db.session.flush()
    return action


# ---------------------------------------------------------------------------------------
# Proposals
def propose_booking(user: User, *, provider: str, item_id: str, day: str, time: str | None, participants: int,
                    trip: Trip | None, conversation_id=None, created_by: str = "user",
                    replaces_event_id: str | None = None) -> AgentAction:
    if participants < 1 or participants > 20:
        raise ValidationFailed("Participants must be between 1 and 20", code="invalid_participants")
    adapter = get_adapter(user, provider)
    caps = adapter.capabilities()
    details = None
    try:
        details = adapter.get_details(item_id) if caps.get("details") else None
    except (ProviderRequestError, ProviderCapabilityError):
        details = None
    if not caps.get("booking"):
        url = details.booking_url if details else None
        return _new_action(
            user, trip_id=trip.id if trip else None, conversation_id=conversation_id, action_type="link_out",
            provider=provider, status="requires_manual", title=f"Book {details.title if details else item_id} on {adapter.name}",
            description=f"{adapter.name} does not allow booking through Tandem ({caps['state'].replace('_', ' ')}). "
                        "Open the provider's page to book, then forward the confirmation to your Tandem inbox.",
            payload={"provider": provider, "provider_item_id": item_id, "booking_url": url, "date": day, "time": time},
            external=False, created_by=created_by, consequences=["Nothing is booked by Tandem."])
    quote = adapter.check_availability(item_id, day, time, participants)
    if not quote.available:
        raise Conflict(f"{quote.title} is not available on {day} at {quote.time} for {participants}",
                       code="not_available", details=quote.detail)
    payload = {
        "provider": provider, "provider_name": adapter.name, "provider_item_id": item_id, "title": quote.title,
        "date": quote.date, "time": quote.time, "timezone": quote.timezone, "participants": participants,
        "unit_price": quote.unit_price, "total_price": quote.total_price, "currency": quote.currency,
        "duration_minutes": quote.duration_minutes, "cancellation_policy": quote.cancellation_policy,
        "quote_ref": quote.quote_ref, "quoted_at": quote.checked_at, "address": quote.detail.get("address"),
        "lat": quote.detail.get("lat"), "lon": quote.detail.get("lon"),
        "category": (details.categories[0] if details and details.categories else None),
        "lead_traveller": user.display_name or user.email, "trip_id": str(trip.id) if trip else None,
        "replaces_event_id": replaces_event_id, "simulated": adapter.simulated,
    }
    consequences = [
        f"Books {participants} place{'s' if participants > 1 else ''} for {quote.title} on {quote.date} at {quote.time}"
        f" ({quote.timezone}).",
        f"Total {quote.total_price:.2f} {quote.currency}" + (" — simulated, no money is charged." if adapter.simulated
                                                            else " charged by the provider."),
        "Shares your name with the provider as lead traveller.",
    ]
    action = _new_action(
        user, trip_id=trip.id if trip else None, conversation_id=conversation_id, action_type="book_activity",
        provider=provider, status="awaiting_approval", title=f"Book {quote.title}",
        description=f"{quote.date} at {quote.time} · {participants} × {quote.unit_price:.2f} {quote.currency}",
        payload=payload, cost=Decimal(str(quote.total_price)), currency=quote.currency, consequences=consequences,
        cancellation_policy=quote.cancellation_policy, external=True, created_by=created_by,
        expires_at=utcnow() + APPROVAL_TTL)
    notify(user.id, "approval_required", f"Approval needed: {action.title}", action.description,
           link="/approvals", dedupe_key=f"approval:{action.id}")
    audit(user.id, "action.proposed", actor=created_by, resource_type="agent_action", resource_id=action.id,
          action_type="book_activity", provider=provider)
    return action


def propose_itinerary_change(user: User, *, trip: Trip, kind: str, event: ItineraryEvent | None, changes: dict,
                             reason: str, conversation_id=None, created_by: str = "assistant") -> AgentAction:
    if kind not in ("update", "delete", "create"):
        raise ValidationFailed("Unknown itinerary change", code="invalid_change")
    payload = {"trip_id": str(trip.id), "kind": kind, "event_id": str(event.id) if event else None,
               "changes": changes, "before": _event_snapshot(event) if event else None}
    title = {"update": f"Change {event.title if event else 'event'}", "delete": f"Remove {event.title if event else 'event'}",
             "create": f"Add {changes.get('title', 'event')}"}[kind]
    action = _new_action(
        user, trip_id=trip.id, conversation_id=conversation_id, action_type=f"itinerary_{kind}", provider=None,
        status="awaiting_approval", title=title, description=reason[:1000], payload=payload, external=False,
        created_by=created_by, consequences=["Changes your Tandem itinerary only. No provider is contacted."],
        expires_at=utcnow() + timedelta(days=2))
    notify(user.id, "approval_required", f"Review proposed change: {title}", reason[:300], link="/approvals",
           dedupe_key=f"approval:{action.id}")
    return action


def _event_snapshot(e: ItineraryEvent) -> dict:
    return {"title": e.title, "start_at": iso(e.start_at), "end_at": iso(e.end_at), "start_tz": e.start_tz,
            "status": e.status, "location_name": e.location_name}


# ---------------------------------------------------------------------------------------
# Decisions
def approve(user: User, action: AgentAction, presented_hash: str) -> AgentAction:
    if action.status != "awaiting_approval":
        raise Conflict(f"This action is {action.status.replace('_', ' ')}, not awaiting approval", code="not_awaiting")
    if action.expires_at and action.expires_at < utcnow():
        action.status = "expired"
        db.session.commit()
        raise Conflict("This proposal expired. Ask for a fresh quote.", code="expired")
    if presented_hash != action.payload_hash:
        raise Conflict("The proposal changed since you reviewed it. Please review it again.", code="payload_changed")
    db.session.add(Approval(action_id=action.id, user_id=user.id, decision="approved", payload_hash=action.payload_hash))
    action.status = "in_progress"
    audit(user.id, "action.approved", resource_type="agent_action", resource_id=action.id,
          payload_hash=action.payload_hash)
    db.session.commit()
    if action.external:
        job = enqueue("execute_action", {"action_id": str(action.id)}, user_id=user.id, max_attempts=1)
        db.session.commit()
        run_inline_if_configured(job)
    else:
        execute_action(str(action.id))
    db.session.refresh(action)
    return action


def reject(user: User, action: AgentAction, note: str = "") -> AgentAction:
    if action.status not in ("awaiting_approval", "requires_manual", "suggested", "prepared"):
        raise Conflict(f"This action is {action.status.replace('_', ' ')} and can't be rejected", code="not_rejectable")
    db.session.add(Approval(action_id=action.id, user_id=user.id, decision="rejected",
                            payload_hash=action.payload_hash, note=note[:500]))
    action.status = "rejected" if action.status == "awaiting_approval" else "cancelled"
    audit(user.id, "action.rejected", resource_type="agent_action", resource_id=action.id)
    return action


# ---------------------------------------------------------------------------------------
# Execution
def execute_action(action_id: str) -> None:
    action = db.session.get(AgentAction, uuid.UUID(str(action_id)))
    if action is None or action.status != "in_progress":
        return
    approval = db.session.execute(db.select(Approval).where(
        Approval.action_id == action.id, Approval.decision == "approved",
        Approval.payload_hash == action.payload_hash).order_by(Approval.decided_at.desc())).scalars().first()
    if approval is None:
        action.status = "failed"
        action.error = "No matching approval for this exact payload"
        db.session.commit()
        return
    user = db.session.get(User, action.user_id)
    try:
        if action.action_type == "book_activity":
            _execute_booking(user, action)
        elif action.action_type.startswith("itinerary_"):
            _execute_itinerary(user, action)
        elif action.action_type == "browser_checkout":
            from app.services.browser.agent import complete_checkout

            complete_checkout(user, action)
        elif action.action_type == "apply_reservation_change":
            change = db.session.get(ReservationChange, uuid.UUID(action.payload["change_id"]))
            trips.apply_change(user, change, actor="assistant")
            _complete(action, {"reservation_id": str(change.reservation_id)})
        else:
            raise ValidationFailed(f"Unsupported action type {action.action_type}")
    except (ValidationFailed, Conflict) as exc:
        db.session.rollback()
        action = db.session.get(AgentAction, action.id)
        action.status = "failed"
        action.error = exc.message
    db.session.commit()


def _complete(action: AgentAction, result: dict) -> None:
    action.status = "completed"
    action.result = {**(action.result or {}), **result}
    action.executed_at = utcnow()


def _execute_itinerary(user: User, action: AgentAction) -> None:
    from app.services.itinerary.service import apply_event_changes, create_event, delete_event

    p = action.payload
    trip = db.session.get(Trip, uuid.UUID(p["trip_id"]))
    if p["kind"] == "create":
        event = create_event(user, trip, p["changes"], source="assistant")
        _complete(action, {"event_id": str(event.id)})
        return
    event = db.session.get(ItineraryEvent, uuid.UUID(p["event_id"]))
    if event is None or event.user_id != user.id:
        raise Conflict("The event no longer exists")
    if p.get("before") and iso(event.start_at) != p["before"]["start_at"]:
        raise Conflict("The event changed after this proposal was made; nothing was applied")
    if p["kind"] == "delete":
        delete_event(user, event)
        _complete(action, {"deleted_event_id": p["event_id"]})
    else:
        apply_event_changes(user, event, p["changes"], allow_confirmed=True)
        _complete(action, {"event_id": p["event_id"]})


def _execute_booking(user: User, action: AgentAction) -> None:
    p = dict(action.payload)
    adapter = get_adapter(user, p["provider"])
    # 1. Re-quote: price, time and availability must be unchanged.
    try:
        quote = adapter.check_availability(p["provider_item_id"], p["date"], p["time"], p["participants"])
    except (ProviderRequestError, ProviderCapabilityError) as exc:
        action.status = "failed"
        action.error = f"Could not re-check availability: {exc}"
        _notify_result(user, action, False)
        return
    if not quote.available or quote.total_price != p["total_price"] or quote.currency != p["currency"] \
            or quote.time != p["time"]:
        new_payload = {**p, "unit_price": quote.unit_price, "total_price": quote.total_price,
                       "currency": quote.currency, "quote_ref": quote.quote_ref, "quoted_at": quote.checked_at}
        if not quote.available:
            action.status = "failed"
            action.error = "No longer available at the approved time. Nothing was booked."
            _notify_result(user, action, False)
            return
        action.payload = new_payload
        action.payload_hash = payload_hash(new_payload)
        action.cost = Decimal(str(quote.total_price))
        action.status = "awaiting_approval"
        action.expires_at = utcnow() + APPROVAL_TTL
        action.result = {"requote": f"Price changed from {p['total_price']} to {quote.total_price} {quote.currency}"}
        notify(user.id, "approval_required", f"Price changed: {action.title}",
               "The provider's price changed, so the booking needs your approval again.", link="/approvals",
               severity="warning", dedupe_key=f"requote:{action.id}:{action.payload_hash}")
        return
    # 2. Submit with an idempotency key so retries can't double-book.
    try:
        booking = adapter.create_booking(quote.to_dict(), {"name": p.get("lead_traveller")}, action.idempotency_key)
    except ProviderRequestError as exc:
        if exc.retryable:
            action.status = "requires_manual"
            action.error = (f"The provider did not confirm the outcome ({exc}). Check your account with "
                            f"{adapter.name} before trying again.")
        else:
            action.status = "failed"
            action.error = f"{adapter.name} declined the booking: {exc}"
        _notify_result(user, action, False)
        return
    # 3. Verify by reading the booking back from the provider.
    try:
        check = adapter.get_booking(booking.provider_booking_id)
    except (ProviderRequestError, ProviderCapabilityError) as exc:
        action.status = "requires_manual"
        action.error = f"Booking {booking.provider_booking_id} was submitted but could not be verified: {exc}"
        _notify_result(user, action, False)
        return
    s = check.summary or {}
    matches = (check.status == "confirmed" and s.get("item_id", p["provider_item_id"]) == p["provider_item_id"]
               and s.get("date", p["date"]) == p["date"] and s.get("time", p["time"]) == p["time"]
               and int(s.get("participants", p["participants"])) == int(p["participants"]))
    pb = ProviderBooking(user_id=user.id, action_id=action.id, provider=p["provider"],
                         provider_booking_id=booking.provider_booking_id, status=check.status,
                         simulated=booking.simulated, verified_at=utcnow() if matches else None,
                         response_summary={k: v for k, v in s.items() if k not in ("lead_traveller",)})
    db.session.add(pb)
    if not matches:
        action.status = "requires_manual"
        action.error = f"The provider reports status '{check.status}' or different details; please check with {adapter.name}."
        _notify_result(user, action, False)
        return
    # 4. Record the reservation and update the itinerary.
    trip = db.session.get(Trip, uuid.UUID(p["trip_id"])) if p.get("trip_id") else None
    start_naive = datetime.fromisoformat(f"{p['date']}T{p['time']}")
    start, _ = localize(start_naive, p.get("timezone") or user.timezone or "UTC")
    end = start + timedelta(minutes=p.get("duration_minutes") or 60)
    res = trips.reservation_from_data(user, {
        "type": CATEGORY_TO_TYPE.get(p.get("category") or "", "activity"), "status": "confirmed",
        "title": p["title"], "provider_name": p.get("provider_name"),
        "booking_reference": booking.provider_booking_id, "start_at": iso(start), "start_tz": p.get("timezone"),
        "end_at": iso(end), "end_tz": p.get("timezone"), "location_name": p["title"], "address": p.get("address"),
        "lat": p.get("lat"), "lon": p.get("lon"), "price": p["total_price"], "currency": p["currency"],
        "cancellation_policy": p.get("cancellation_policy"),
        "details": {"party_size": p["participants"], "provider_booking_id": booking.provider_booking_id,
                    "simulated": booking.simulated},
        "city": trip.primary_destination if trip else None,
    }, trip=trip, confidence=1.0, verification="verified", created_via="booking")
    pb.reservation_id = res.id
    trips.sync_events(res)
    if p.get("replaces_event_id"):
        old = db.session.get(ItineraryEvent, uuid.UUID(p["replaces_event_id"]))
        if old and old.user_id == user.id and old.status in ("suggested", "unbooked"):
            db.session.delete(old)
    _complete(action, {"provider_booking_id": booking.provider_booking_id, "reservation_id": str(res.id),
                       "verified_at": utcnow().isoformat(), "simulated": booking.simulated})
    audit(user.id, "booking.completed", actor="system", resource_type="reservation", resource_id=res.id,
          provider=p["provider"], simulated=booking.simulated)
    if trip:
        trips.refresh_trip(trip, user)
        db.session.flush()
        from app.services.itinerary.conflicts import check_and_notify

        check_and_notify(trip, user)
    _notify_result(user, action, True)


def _notify_result(user: User, action: AgentAction, ok: bool) -> None:
    if ok:
        sim = " (simulated)" if action.result.get("simulated") else ""
        notify(user.id, "booking_result", f"Booked{sim}: {action.payload.get('title')}",
               f"Confirmation {action.result.get('provider_booking_id')}, verified with the provider.",
               link=f"/trips/{action.trip_id}" if action.trip_id else "/approvals", severity="success",
               dedupe_key=f"booking_ok:{action.id}")
    else:
        notify(user.id, "booking_result", f"Not booked: {action.payload.get('title', action.title)}",
               action.error or "", link="/approvals", severity="warning", dedupe_key=f"booking_fail:{action.id}")

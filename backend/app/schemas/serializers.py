"""transforma modelele in json pt api. datele sunt iso 8601, orele evenimentelor sunt si locale"""
from __future__ import annotations

from decimal import Decimal

from app.models import (
    AgentAction, Conversation, Document, ExtractedField, ExtractedRecord, ItineraryEvent, Message, Notification,
    Reservation, ReservationChange, Trip, User,
)
from app.utils.timeutil import iso, iso_local


def _num(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _id(value) -> str | None:
    return str(value) if value is not None else None


def user_dict(u: User) -> dict:
    return {
        "id": str(u.id), "email": u.email, "display_name": u.display_name, "home_city": u.home_city,
        "home_airport": u.home_airport, "locale": u.locale, "timezone": u.timezone, "is_demo": u.is_demo,
        "created_at": iso(u.created_at),
    }


def trip_dict(t: Trip, *, stats: dict | None = None) -> dict:
    return {
        "id": str(t.id), "name": t.name, "start_date": t.start_date.isoformat() if t.start_date else None,
        "end_date": t.end_date.isoformat() if t.end_date else None, "primary_destination": t.primary_destination,
        "notes": t.notes, "is_cancelled": t.is_cancelled, "created_via": t.created_via,
        "grouping": t.grouping or {},
        "destinations": [
            {"id": str(d.id), "name": d.name, "country": d.country, "lat": d.lat, "lon": d.lon, "timezone": d.timezone,
             "arrive_date": d.arrive_date.isoformat() if d.arrive_date else None,
             "depart_date": d.depart_date.isoformat() if d.depart_date else None, "position": d.position}
            for d in t.destinations
        ],
        "travellers": [{"id": str(x.id), "full_name": x.full_name, "is_primary": x.is_primary} for x in t.travellers],
        "stats": stats or {},
        "created_at": iso(t.created_at), "updated_at": iso(t.updated_at),
    }


def reservation_dict(r: Reservation) -> dict:
    return {
        "id": str(r.id), "trip_id": _id(r.trip_id), "type": r.type, "status": r.status, "title": r.title,
        "provider_name": r.provider_name, "booking_reference": r.booking_reference, "description": r.description,
        "origin": r.origin, "destination": r.destination,
        "start_at": iso(r.start_at), "start_tz": r.start_tz, "start_local": iso_local(r.start_at, r.start_tz),
        "end_at": iso(r.end_at), "end_tz": r.end_tz, "end_local": iso_local(r.end_at, r.end_tz or r.start_tz),
        "location_name": r.location_name, "address": r.address, "city": r.city, "lat": r.lat, "lon": r.lon,
        "price": _num(r.price), "currency": r.currency, "travellers": r.travellers or [], "details": r.details or {},
        "cancellation_deadline": iso(r.cancellation_deadline), "cancellation_policy": r.cancellation_policy,
        "website": r.website, "contact": r.contact, "source_document_id": _id(r.source_document_id),
        "confidence": r.confidence, "verification": r.verification, "created_via": r.created_via,
        "created_at": iso(r.created_at), "updated_at": iso(r.updated_at),
    }


def change_dict(c: ReservationChange) -> dict:
    return {
        "id": str(c.id), "reservation_id": str(c.reservation_id), "source_document_id": _id(c.source_document_id),
        "changes": c.changes, "status": c.status, "summary": c.summary, "detected_at": iso(c.detected_at),
        "resolved_at": iso(c.resolved_at),
    }


def event_dict(e: ItineraryEvent) -> dict:
    return {
        "id": str(e.id), "trip_id": str(e.trip_id), "reservation_id": _id(e.reservation_id), "type": e.type,
        "status": e.status, "title": e.title, "notes": e.notes,
        "start_at": iso(e.start_at), "start_tz": e.start_tz, "start_local": iso_local(e.start_at, e.start_tz),
        "end_at": iso(e.end_at), "end_tz": e.end_tz or e.start_tz,
        "end_local": iso_local(e.end_at, e.end_tz or e.start_tz), "all_day": e.all_day,
        "location_name": e.location_name, "address": e.address, "city": e.city, "lat": e.lat, "lon": e.lon,
        "end_location_name": e.end_location_name, "end_city": e.end_city, "end_lat": e.end_lat, "end_lon": e.end_lon,
        "source": e.source, "details": e.details or {}, "updated_at": iso(e.updated_at),
    }


def field_dict(f: ExtractedField) -> dict:
    return {
        "field": f.field_name, "value": f.value, "evidence": f.evidence, "confidence": f.confidence,
        "source_page": f.source_page, "verification": f.verification,
    }


def record_dict(r: ExtractedRecord) -> dict:
    return {
        "id": str(r.id), "document_id": str(r.document_id), "index": r.index, "record_type": r.record_type,
        "data": r.data, "confidence": r.confidence, "uncertainty_notes": r.uncertainty_notes or [],
        "status": r.status, "extractor": r.extractor or {}, "proposed_trip_id": _id(r.proposed_trip_id),
        "grouping": r.grouping or {}, "matched_reservation_id": _id(r.matched_reservation_id),
        "reservation_id": _id(r.reservation_id), "fields": [field_dict(f) for f in r.fields],
        "created_at": iso(r.created_at), "reviewed_at": iso(r.reviewed_at),
    }


def document_dict(d: Document, *, include_records: bool = False, include_text: bool = False) -> dict:
    out = {
        "id": str(d.id), "trip_id": _id(d.trip_id), "parent_document_id": _id(d.parent_document_id),
        "duplicate_of_id": _id(d.duplicate_of_id), "source": d.source, "filename": d.filename,
        "mime_type": d.mime_type, "size_bytes": d.size_bytes, "status": d.status, "status_detail": d.status_detail,
        "classification": d.classification, "page_count": d.page_count, "source_url": d.source_url,
        "extraction_method": d.extraction_method or {}, "has_original": bool(d.storage_key) and not d.original_deleted_at,
        "created_at": iso(d.created_at), "processed_at": iso(d.processed_at),
        "record_count": len(d.records),
        "pending_review_count": sum(1 for r in d.records if r.status in ("pending_review", "change_detected")),
    }
    if include_records:
        out["records"] = [record_dict(r) for r in d.records]
    if include_text:
        out["extracted_text"] = d.extracted_text
    return out


def action_dict(a: AgentAction) -> dict:
    return {
        "id": str(a.id), "trip_id": _id(a.trip_id), "conversation_id": _id(a.conversation_id),
        "action_type": a.action_type, "provider": a.provider, "status": a.status, "title": a.title,
        "description": a.description, "payload": a.payload, "payload_hash": a.payload_hash, "cost": _num(a.cost),
        "currency": a.currency, "consequences": a.consequences or [], "cancellation_policy": a.cancellation_policy,
        "external": a.external, "created_by": a.created_by, "expires_at": iso(a.expires_at), "result": a.result or {},
        "error": a.error, "executed_at": iso(a.executed_at), "created_at": iso(a.created_at),
        "updated_at": iso(a.updated_at),
    }


def conversation_dict(c: Conversation) -> dict:
    return {"id": str(c.id), "trip_id": _id(c.trip_id), "title": c.title, "kind": c.kind or "chat",
            "created_at": iso(c.created_at), "updated_at": iso(c.updated_at)}


def message_dict(m: Message) -> dict:
    return {
        "id": str(m.id), "role": m.role, "content": m.content, "tool_calls": m.tool_calls or [],
        "references": m.references or [], "action_ids": m.action_ids or [], "provider": m.provider,
        "model": m.model, "error": m.error, "created_at": iso(m.created_at),
    }


def notification_dict(n: Notification) -> dict:
    return {"id": str(n.id), "type": n.type, "severity": n.severity, "title": n.title, "body": n.body,
            "link": n.link, "read": n.read_at is not None, "created_at": iso(n.created_at)}

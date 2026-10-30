from __future__ import annotations

from flask import Blueprint, current_app, request
from pydantic import BaseModel, Field

from app.api._core import current_user, doc, get_owned, login_required, ok, parse_body, parse_uuid
from app.extensions import db, limiter
from app.models import Document, EmailCandidate, ExtractedRecord, ProcessingJob
from app.schemas.serializers import document_dict
from app.services.audit import audit
from app.services.ingestion import pipeline
from app.services.trips import service as trips
from app.tasks.queue import run_inline_if_configured
from app.utils.errors import APIError, NotFound, ValidationFailed

bp = Blueprint("inbox", __name__, url_prefix="/api/v1/inbox")


class PasteBody(BaseModel):
    text: str = Field(min_length=1, max_length=60000)
    title: str | None = Field(default=None, max_length=120)


class UrlBody(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class RecordDecision(BaseModel):
    record_id: str
    decision: str = Field(pattern="^(accept|reject)$")
    corrections: dict = Field(default_factory=dict)
    trip_id: str | None = None
    new_trip_name: str | None = Field(default=None, max_length=200)
    no_trip: bool = False


class ReviewBody(BaseModel):
    decisions: list[RecordDecision] = Field(min_length=1, max_length=20)


class ImportBody(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=25)


@bp.get("")
@login_required
@doc("Inbox items (top-level documents), newest first. Filter with ?status=", tag="Inbox")
def list_inbox():
    u = current_user()
    q = db.select(Document).where(Document.user_id == u.id, Document.parent_document_id.is_(None))
    if request.args.get("status"):
        q = q.where(Document.status.in_(request.args["status"].split(",")))
    rows = db.session.execute(q.order_by(Document.created_at.desc()).limit(200)).scalars().all()
    children = db.session.execute(db.select(Document).where(
        Document.parent_document_id.in_([d.id for d in rows] or [None]))).scalars().all()
    by_parent: dict = {}
    for c in children:
        by_parent.setdefault(str(c.parent_document_id), []).append(document_dict(c))
    counts = dict(db.session.execute(db.select(Document.status, db.func.count(Document.id)).where(
        Document.user_id == u.id).group_by(Document.status)).all())
    return ok([{**document_dict(d), "attachments": by_parent.get(str(d.id), [])} for d in rows],
              meta={"counts": counts})


@bp.post("/upload")
@login_required
@limiter.limit("60 per hour")
@doc("Upload one or more files (multipart field 'files')", tag="Inbox")
def upload():
    u = current_user()
    files = request.files.getlist("files")
    if not files:
        raise ValidationFailed("No files received", code="no_files")
    if len(files) > current_app.config["MAX_FILES_PER_UPLOAD"]:
        raise ValidationFailed(f"Upload at most {current_app.config['MAX_FILES_PER_UPLOAD']} files at once",
                               code="too_many_files")
    trip_id = request.form.get("trip_id")
    if trip_id:
        from app.models import Trip

        t = db.session.get(Trip, parse_uuid(trip_id, "trip"))
        if t is None or t.user_id != u.id:
            raise NotFound("Trip not found")
    created, errors = [], []
    max_bytes = current_app.config["MAX_UPLOAD_BYTES"]
    for f in files:
        data = f.stream.read(max_bytes + 1)
        try:
            created.append(pipeline.ingest_file(u, f.filename or "upload", data, f.mimetype,
                                                trip_id=parse_uuid(trip_id) if trip_id else None))
        except APIError as exc:
            errors.append({"filename": f.filename, "code": exc.code, "message": exc.message})
    db.session.commit()
    pipeline.queue_after_commit(created)
    status = 201 if created else 422
    return ok({"documents": [document_dict(d) for d in created], "errors": errors}, status)


@bp.post("/paste")
@login_required
@limiter.limit("60 per hour")
@doc("Import pasted text (e.g. a confirmation email body)", body=PasteBody, tag="Inbox")
def paste():
    body = parse_body(PasteBody)
    d = pipeline.ingest_text(current_user(), body.text, title=body.title)
    db.session.commit()
    pipeline.queue_after_commit([d])
    return ok(document_dict(d), 201)


@bp.post("/url")
@login_required
@limiter.limit("30 per hour")
@doc("Import a web page or file by URL (SSRF-protected)", body=UrlBody, tag="Inbox")
def from_url():
    body = parse_body(UrlBody)
    d = pipeline.ingest_url(current_user(), body.url)
    db.session.commit()
    pipeline.queue_after_commit([d])
    return ok(document_dict(d), 201)


@bp.get("/<doc_id>")
@login_required
@doc("Inbox item with extracted records, fields and evidence", tag="Inbox")
def get_item(doc_id):
    d = get_owned(Document, doc_id, "document")
    job = db.session.execute(db.select(ProcessingJob).where(ProcessingJob.document_id == d.id)
                             .order_by(ProcessingJob.created_at.desc()).limit(1)).scalar()
    children = db.session.execute(db.select(Document).where(Document.parent_document_id == d.id)).scalars().all()
    return ok({**document_dict(d, include_records=True, include_text=True),
               "attachments": [document_dict(c, include_records=True) for c in children],
               "job": {"status": job.status, "attempts": job.attempts, "last_error": None if job.status != "failed"
                       else "Processing failed", "progress": job.progress} if job else None})


@bp.post("/<doc_id>/review")
@login_required
@doc("Accept (with corrections and trip choice) or reject extracted records", body=ReviewBody, tag="Inbox")
def review(doc_id):
    d = get_owned(Document, doc_id, "document")
    body = parse_body(ReviewBody)
    u = current_user()
    results = []
    for dec in body.decisions:
        rec = db.session.get(ExtractedRecord, parse_uuid(dec.record_id, "record"))
        if rec is None or rec.user_id != u.id:
            raise NotFound("Record not found")
        if rec.document_id != d.id and rec.document.parent_document_id != d.id:
            raise ValidationFailed("Record does not belong to this document", code="record_mismatch")
        if dec.decision == "reject":
            trips.reject_record(u, rec)
            results.append({"record_id": str(rec.id), "status": "rejected"})
            continue
        choice = {"trip_id": dec.trip_id} if dec.trip_id else (
            {"new_trip": {"name": dec.new_trip_name}} if dec.new_trip_name else ({"no_trip": True} if dec.no_trip else None))
        res = trips.accept_record(u, rec, corrections=dec.corrections, trip_choice=choice)
        results.append({"record_id": str(rec.id), "status": "accepted", "reservation_id": str(res.id),
                        "trip_id": str(res.trip_id) if res.trip_id else None})
    db.session.commit()
    return ok({"results": results, "document": document_dict(d, include_records=True)})


@bp.post("/<doc_id>/ignore")
@login_required
@doc("Mark an item as not relevant", tag="Inbox")
def ignore(doc_id):
    d = get_owned(Document, doc_id, "document")
    d.status = "ignored"
    for r in d.records:
        if r.status in ("pending_review",):
            r.status = "rejected"
    audit(current_user().id, "document.ignored", resource_type="document", resource_id=d.id)
    db.session.commit()
    return ok(document_dict(d))


@bp.post("/<doc_id>/retry")
@login_required
@doc("Re-process a document", tag="Inbox")
def retry(doc_id):
    d = get_owned(Document, doc_id, "document")
    if d.status in ("processing", "analysing", "queued"):
        raise ValidationFailed("This document is already being processed", code="in_progress")
    job = pipeline.retry_document(current_user(), d)
    db.session.commit()
    run_inline_if_configured(job)
    return ok(document_dict(d))


@bp.delete("/<doc_id>")
@login_required
@doc("Delete a document, its stored original and its pending records", tag="Inbox")
def delete(doc_id):
    d = get_owned(Document, doc_id, "document")
    pipeline.delete_document(current_user(), d)
    db.session.commit()
    return ok({"deleted": True})


@bp.get("/email-candidates")
@login_required
@doc("Travel-looking Gmail messages found by the last sync", tag="Inbox")
def email_candidates():
    rows = db.session.execute(db.select(EmailCandidate).where(EmailCandidate.user_id == current_user().id)
                              .order_by(EmailCandidate.received_at.desc()).limit(100)).scalars().all()
    return ok([{"id": str(c.id), "subject": c.subject, "sender": c.sender,
                "received_at": c.received_at.isoformat() if c.received_at else None, "snippet": c.snippet,
                "has_attachments": c.has_attachments, "status": c.status,
                "document_id": str(c.document_id) if c.document_id else None} for c in rows])


@bp.post("/email-candidates/import")
@login_required
@doc("Import selected Gmail messages into the inbox", body=ImportBody, tag="Inbox")
def import_emails():
    from app.tasks.queue import enqueue

    body = parse_body(ImportBody)
    u = current_user()
    job = enqueue("gmail_import", {"candidate_ids": body.candidate_ids}, user_id=u.id)
    db.session.commit()
    run_inline_if_configured(job)
    return ok({"queued": len(body.candidate_ids)}, 202)

from __future__ import annotations

import io

from flask import Blueprint, request, send_file

from app.api._core import current_user, doc, get_owned, login_required, ok
from app.extensions import db
from app.models import Document
from app.schemas.serializers import document_dict
from app.services.audit import audit
from app.services.ingestion.extractors import html_to_text, sanitize_html
from app.services.ingestion.pipeline import delete_document
from app.services.storage import storage
from app.utils.errors import NotFound

bp = Blueprint("documents", __name__, url_prefix="/api/v1/documents")

INLINE_SAFE = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


@bp.get("")
@login_required
@doc("All documents (filter trip_id)", tag="Documents")
def list_documents():
    u = current_user()
    q = db.select(Document).where(Document.user_id == u.id)
    if request.args.get("trip_id"):
        from app.api._core import parse_uuid

        q = q.where(Document.trip_id == parse_uuid(request.args["trip_id"], "trip"))
    rows = db.session.execute(q.order_by(Document.created_at.desc())).scalars().all()
    return ok([document_dict(d) for d in rows])


@bp.get("/<doc_id>")
@login_required
@doc("Document metadata", tag="Documents")
def get_document(doc_id):
    return ok(document_dict(get_owned(Document, doc_id, "document"), include_records=True))


@bp.get("/<doc_id>/download")
@login_required
@doc("Download the original file (authenticated; never a public URL)", tag="Documents")
def download(doc_id):
    d = get_owned(Document, doc_id, "document")
    if not d.storage_key or d.original_deleted_at:
        raise NotFound("The original file is no longer stored", code="original_deleted")
    data = storage().get(d.storage_key)
    inline = request.args.get("inline") == "1" and d.mime_type in INLINE_SAFE
    audit(current_user().id, "document.downloaded", resource_type="document", resource_id=d.id)
    db.session.commit()
    resp = send_file(io.BytesIO(data), mimetype=d.mime_type if inline else "application/octet-stream",
                     as_attachment=not inline, download_name=d.filename)
    resp.headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self' data:; plugin-types application/pdf; sandbox"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.get("/<doc_id>/preview")
@login_required
@doc("Safe text preview (HTML is sanitised; scripts and remote content removed)", tag="Documents")
def preview(doc_id):
    d = get_owned(Document, doc_id, "document")
    if d.mime_type == "text/html" and d.storage_key and not d.original_deleted_at:
        html = storage().get(d.storage_key).decode("utf-8", errors="replace")
        return ok({"kind": "html", "html": sanitize_html(html), "text": html_to_text(html)[:20000]})
    return ok({"kind": "text", "text": (d.extracted_text or "")[:20000]})


@bp.delete("/<doc_id>")
@login_required
@doc("Delete a document", tag="Documents")
def delete(doc_id):
    d = get_owned(Document, doc_id, "document")
    delete_document(current_user(), d)
    db.session.commit()
    return ok({"deleted": True})

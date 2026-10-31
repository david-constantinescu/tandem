from __future__ import annotations

import io

from flask import Blueprint, send_file

from app.api._core import current_user, doc, login_required, ok
from app.i18n import tr
from app.extensions import db
from app.schemas.serializers import document_dict
from app.services.demo import documents as demo_docs
from app.services.demo.seed import demo_start_date
from app.services.ingestion import pipeline
from app.utils.errors import Forbidden, NotFound

bp = Blueprint("demo", __name__, url_prefix="/api/v1/demo")


def _demo_user():
    u = current_user()
    if not u.is_demo:
        raise Forbidden("Sample documents are only available in the demo workspace", code="demo_only")
    return u


@bp.get("/samples")
@login_required
@doc("Sample documents for the demo's live upload flow", tag="Demo")
def samples():
    _demo_user()
    return ok([{"key": k, "filename": v[0], "mime_type": v[1], "description": tr(v[2])} for k, v in demo_docs.SAMPLES.items()])


@bp.get("/samples/<key>")
@login_required
@doc("Download a sample document to try drag-and-drop", tag="Demo")
def download_sample(key):
    u = _demo_user()
    if key not in demo_docs.SAMPLES:
        raise NotFound("Unknown sample")
    filename, mime, data = demo_docs.build_sample(key, demo_start_date(), u.email)
    return send_file(io.BytesIO(data), mimetype=mime, as_attachment=True, download_name=filename)


@bp.post("/samples/<key>/upload")
@login_required
@doc("Send a sample document into the inbox through the real ingestion pipeline", tag="Demo")
def upload_sample(key):
    u = _demo_user()
    if key not in demo_docs.SAMPLES:
        raise NotFound("Unknown sample")
    filename, mime, data = demo_docs.build_sample(key, demo_start_date(), u.email)
    d = pipeline.ingest_file(u, filename, data, mime)
    db.session.commit()
    pipeline.queue_after_commit([d])
    return ok(document_dict(d), 201)

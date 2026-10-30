from __future__ import annotations

from flask import Blueprint, current_app
from sqlalchemy import text

from app.api._core import doc, ok
from app.extensions import db
from app.models import ProcessingJob
from app.utils.timeutil import utcnow

bp = Blueprint("health", __name__, url_prefix="/api/v1/health")


@bp.get("")
@doc("Liveness and dependency status", tag="Health", auth=False)
def health():
    db_ok = True
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    queued = running = None
    if db_ok:
        queued = db.session.execute(db.select(db.func.count(ProcessingJob.id)).where(
            ProcessingJob.status == "queued")).scalar()
        running = db.session.execute(db.select(db.func.count(ProcessingJob.id)).where(
            ProcessingJob.status == "running")).scalar()
    status = 200 if db_ok else 503
    return ok({"status": "ok" if db_ok else "degraded", "database": db_ok, "jobs": {"queued": queued, "running": running},
               "job_runner": current_app.config["JOB_RUNNER"], "demo_mode": current_app.config["DEMO_MODE"],
               "time": utcnow().isoformat()}, status)

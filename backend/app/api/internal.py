"""Scheduled maintenance endpoint for hosts without a long-running worker (e.g. Vercel Cron)."""
from __future__ import annotations

import hmac

from flask import Blueprint, current_app, request

from app.api._core import doc, ok
from app.utils.errors import Forbidden

bp = Blueprint("internal", __name__, url_prefix="/api/v1/internal")


@bp.get("/cron")
@doc("Run periodic checks and due jobs (requires Authorization: Bearer CRON_SECRET)", tag="Internal", auth=False)
def cron():
    secret = current_app.config.get("CRON_SECRET") or ""
    sent = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not secret or not hmac.compare_digest(sent, secret):
        raise Forbidden("Not allowed", code="cron_forbidden")
    from app.tasks.periodic import run_periodic
    from app.tasks.queue import run_pending

    run_periodic()
    processed = run_pending(limit=50)
    return ok({"periodic": "done", "jobs_processed": processed})

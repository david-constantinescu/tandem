"""PostgreSQL-backed job queue.

Jobs are rows in `processing_jobs`. Workers claim them with `SELECT ... FOR UPDATE SKIP LOCKED`,
so several worker processes can run safely without Redis. See docs/ARCHITECTURE.md (decision log).
"""
from __future__ import annotations

import logging
import os
import socket
import time
import traceback
import uuid
from datetime import timedelta
from typing import Callable

from flask import current_app

from app.extensions import db
from app.models import ProcessingJob
from app.utils.timeutil import utcnow

log = logging.getLogger("tandem.jobs")

HANDLERS: dict[str, Callable[[ProcessingJob], None]] = {}
STALE_LOCK = timedelta(minutes=15)


class RetryableJobError(Exception):
    """Raise from a handler to retry later (e.g. provider rate limit)."""

    def __init__(self, message: str, delay_seconds: int = 60):
        super().__init__(message)
        self.delay_seconds = delay_seconds


def handler(kind: str):
    def register(fn: Callable[[ProcessingJob], None]):
        HANDLERS[kind] = fn
        return fn

    return register


def enqueue(kind: str, payload: dict | None = None, *, user_id: uuid.UUID | None = None,
            document_id: uuid.UUID | None = None, delay_seconds: int = 0, max_attempts: int = 3) -> ProcessingJob:
    job = ProcessingJob(kind=kind, payload=payload or {}, user_id=user_id, document_id=document_id,
                        run_after=utcnow() + timedelta(seconds=delay_seconds), max_attempts=max_attempts)
    db.session.add(job)
    db.session.flush()
    return job


def run_inline_if_configured(job: ProcessingJob) -> None:
    """In JOB_RUNNER=inline mode (tests, single-process demos) run the job immediately after commit."""
    if current_app.config.get("JOB_RUNNER") == "inline":
        db.session.commit()
        execute(job.id)


def claim_next(worker_id: str) -> uuid.UUID | None:
    now = utcnow()
    stmt = (
        db.select(ProcessingJob)
        .where(
            ((ProcessingJob.status == "queued") & (ProcessingJob.run_after <= now))
            | ((ProcessingJob.status == "running") & (ProcessingJob.locked_at < now - STALE_LOCK))
        )
        .order_by(ProcessingJob.run_after)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = db.session.execute(stmt).scalar_one_or_none()
    if job is None:
        db.session.rollback()
        return None
    job.status = "running"
    job.locked_at = now
    job.locked_by = worker_id
    job.attempts += 1
    db.session.commit()
    return job.id


def execute(job_id: uuid.UUID) -> None:
    job = db.session.get(ProcessingJob, job_id)
    if job is None:
        return
    fn = HANDLERS.get(job.kind)
    if fn is None:
        job.status = "failed"
        job.last_error = f"No handler for job kind {job.kind}"
        job.finished_at = utcnow()
        db.session.commit()
        return
    if job.status != "running":
        job.status = "running"
        job.attempts += 1
        job.locked_at = utcnow()
        db.session.commit()
    try:
        fn(job)
        db.session.commit()
        job = db.session.get(ProcessingJob, job_id)
        job.status = "succeeded"
        job.finished_at = utcnow()
        db.session.commit()
    except RetryableJobError as exc:
        db.session.rollback()
        job = db.session.get(ProcessingJob, job_id)
        _retry_or_fail(job, str(exc), exc.delay_seconds)
    except Exception as exc:  # noqa: BLE001 - jobs must never crash the worker
        db.session.rollback()
        log.error("job %s (%s) failed: %s", job_id, job.kind, traceback.format_exc(limit=5))
        job = db.session.get(ProcessingJob, job_id)
        _retry_or_fail(job, f"{type(exc).__name__}: {exc}"[:2000], 30 * job.attempts)


def _retry_or_fail(job: ProcessingJob, message: str, delay: int) -> None:
    job.last_error = message
    job.locked_at = None
    job.locked_by = None
    if job.attempts < job.max_attempts:
        job.status = "queued"
        job.run_after = utcnow() + timedelta(seconds=delay)
    else:
        job.status = "failed"
        job.finished_at = utcnow()
        on_fail = FAILURE_HOOKS.get(job.kind)
        if on_fail:
            try:
                on_fail(job, message)
            except Exception:  # noqa: BLE001
                log.exception("failure hook for %s raised", job.kind)
    db.session.commit()


FAILURE_HOOKS: dict[str, Callable[[ProcessingJob, str], None]] = {}


def on_failure(kind: str):
    def register(fn):
        FAILURE_HOOKS[kind] = fn
        return fn

    return register


def run_pending(limit: int = 100) -> int:
    """Process all currently due jobs synchronously (used by tests and the CLI)."""
    worker_id = f"sync-{os.getpid()}"
    count = 0
    while count < limit:
        job_id = claim_next(worker_id)
        if job_id is None:
            break
        execute(job_id)
        count += 1
    return count


def worker_loop(app, *, once: bool = False) -> None:
    from app.tasks import periodic

    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    poll = app.config["WORKER_POLL_SECONDS"]
    interval = app.config["SCHEDULED_CHECK_MINUTES"] * 60
    last_periodic = 0.0
    log.info("worker %s started", worker_id)
    while True:
        with app.app_context():
            if time.monotonic() - last_periodic > interval:
                try:
                    periodic.run_periodic()
                except Exception:  # noqa: BLE001
                    log.exception("periodic tasks failed")
                    db.session.rollback()
                last_periodic = time.monotonic()
            job_id = claim_next(worker_id)
            if job_id:
                execute(job_id)
            db.session.remove()
        if once:
            return
        if not job_id:
            time.sleep(poll)

"""Job handler registrations (imported by the app factory so workers know every job kind)."""
from __future__ import annotations

from app.models import ProcessingJob
from app.tasks.queue import handler, on_failure


@handler("process_document")
def _process_document(job: ProcessingJob) -> None:
    from app.services.ingestion.pipeline import process_document

    process_document(job)


@on_failure("process_document")
def _process_document_failed(job: ProcessingJob, message: str) -> None:
    from app.services.ingestion.pipeline import on_process_failure

    on_process_failure(job, message)


@handler("gmail_sync")
def _gmail_sync(job: ProcessingJob) -> None:
    from app.services.integrations.gmail import sync_candidates

    sync_candidates(job.user_id, full=bool(job.payload.get("full")))


@handler("gmail_import")
def _gmail_import(job: ProcessingJob) -> None:
    from app.services.integrations.gmail import import_messages

    import_messages(job.user_id, job.payload.get("candidate_ids", []))


@handler("browser_task")
def _browser_task(job: ProcessingJob) -> None:
    from app.services.browser.agent import run_task

    run_task(job.payload["task_id"])


@handler("execute_action")
def _execute_action(job: ProcessingJob) -> None:
    from app.services.agent.approvals import execute_action

    execute_action(job.payload["action_id"])

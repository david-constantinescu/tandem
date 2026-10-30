from __future__ import annotations

import io

from flask import Blueprint, request, send_file
from pydantic import BaseModel, Field

from app.api._core import current_user, doc, get_owned, login_required, ok, parse_body, parse_uuid
from app.extensions import db, limiter
from app.models import BrowserTask, Trip
from app.services.browser import agent
from app.services.browser.engines import playwright_available
from app.services.browser.sites import CATEGORIES, sites_for
from app.services.storage import storage
from app.utils.errors import Conflict, NotFound

bp = Blueprint("browser", __name__, url_prefix="/api/v1/browser")


class TaskBody(BaseModel):
    site: str
    origin: str | None = Field(default=None, max_length=120)
    destination: str | None = Field(default=None, max_length=120)
    venue: str | None = Field(default=None, max_length=200)
    date: str | None = None
    time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    adults: int = Field(default=1, ge=1, le=9)
    travellers: list[str] = Field(default_factory=list, max_length=9)
    trip_id: str | None = None
    goal: str = Field(default="book", pattern="^(book|search)$")


@bp.get("/sites")
@login_required
@doc("Booking websites the browser agent knows, with each site's automation policy", tag="Browser agent")
def list_sites():
    cat = request.args.get("category")
    sites = [s.to_dict() for s in sites_for(current_user().is_demo) if not cat or s.category == cat]
    return ok(sites, meta={"categories": list(CATEGORIES), "browser_worker": playwright_available()})


@bp.get("/tasks")
@login_required
@doc("Recent browser-agent tasks", tag="Browser agent")
def list_tasks():
    rows = db.session.execute(db.select(BrowserTask).where(BrowserTask.user_id == current_user().id)
                              .order_by(BrowserTask.created_at.desc()).limit(30)).scalars().all()
    return ok([agent.task_dict(t) for t in rows])


@bp.post("/tasks")
@login_required
@limiter.limit("60 per hour")
@doc("Start a website task: search a site and, on simulated sites, prepare a purchase for approval", body=TaskBody,
     tag="Browser agent")
def create_task():
    body = parse_body(TaskBody)
    u = current_user()
    trip = None
    if body.trip_id:
        trip = db.session.get(Trip, parse_uuid(body.trip_id, "trip"))
        if trip is None or trip.user_id != u.id:
            raise NotFound("Trip not found")
    task = agent.create_task(u, body.site, body.model_dump(exclude={"site", "trip_id", "goal"}), trip=trip, goal=body.goal)
    db.session.commit()
    job = getattr(task, "_job", None)
    if job is not None:
        from app.tasks.queue import run_inline_if_configured

        run_inline_if_configured(job)
        db.session.refresh(task)
    return ok(agent.task_dict(task), 201)


@bp.get("/tasks/<task_id>")
@login_required
@doc("A browser-agent task with its step log", tag="Browser agent")
def get_task(task_id):
    return ok(agent.task_dict(get_owned(BrowserTask, task_id, "task")))


@bp.post("/tasks/<task_id>/cancel")
@login_required
@doc("Cancel a browser-agent task that hasn't completed", tag="Browser agent")
def cancel_task(task_id):
    t = get_owned(BrowserTask, task_id, "task")
    if t.state in ("completed", "cancelled"):
        raise Conflict("This task already finished", code="task_finished")
    t.state = "cancelled"
    t.stop_reason = "Cancelled by you"
    if t.action_id:
        from app.models import AgentAction

        a = db.session.get(AgentAction, t.action_id)
        if a and a.status == "awaiting_approval":
            a.status = "cancelled"
    db.session.commit()
    return ok(agent.task_dict(t))


@bp.get("/tasks/<task_id>/steps/<int:step>/screenshot")
@login_required
@doc("Screenshot captured at a step (sensitive fields are masked)", tag="Browser agent")
def screenshot(task_id, step):
    t = get_owned(BrowserTask, task_id, "task")
    entry = next((e for e in (t.log or []) if e.get("step") == step and e.get("screenshot")), None)
    if entry is None:
        raise NotFound("No screenshot for this step")
    return send_file(io.BytesIO(storage().get(entry["screenshot"])), mimetype="image/jpeg")

from __future__ import annotations

from flask import Blueprint, request
from pydantic import BaseModel, Field

from app.api._core import current_user, doc, get_owned, login_required, ok, parse_body
from app.extensions import db, limiter
from app.models import AgentAction, Approval
from app.schemas.serializers import action_dict
from app.services.agent import approvals as approval_service

bp = Blueprint("approvals", __name__, url_prefix="/api/v1/approvals")


class ApproveBody(BaseModel):
    payload_hash: str = Field(min_length=64, max_length=64, description="Hash of the exact proposal shown to the user")


class RejectBody(BaseModel):
    note: str = Field(default="", max_length=500)


@bp.get("")
@login_required
@doc("Actions and proposals (filter ?status=awaiting_approval,in_progress...)", tag="Approvals")
def list_actions():
    q = db.select(AgentAction).where(AgentAction.user_id == current_user().id)
    if request.args.get("status"):
        q = q.where(AgentAction.status.in_(request.args["status"].split(",")))
    if request.args.get("trip_id"):
        from app.api._core import parse_uuid

        q = q.where(AgentAction.trip_id == parse_uuid(request.args["trip_id"], "trip"))
    rows = db.session.execute(q.order_by(AgentAction.created_at.desc()).limit(100)).scalars().all()
    return ok([action_dict(a) for a in rows])


@bp.get("/<action_id>")
@login_required
@doc("One action with its approval history", tag="Approvals")
def get_action(action_id):
    a = get_owned(AgentAction, action_id, "action")
    history = db.session.execute(db.select(Approval).where(Approval.action_id == a.id)
                                 .order_by(Approval.decided_at)).scalars().all()
    return ok({**action_dict(a), "decisions": [{"decision": h.decision, "payload_hash": h.payload_hash,
                                               "note": h.note, "decided_at": h.decided_at.isoformat()} for h in history]})


@bp.post("/<action_id>/approve")
@login_required
@limiter.limit("30 per hour")
@doc("Approve the exact proposal identified by its payload hash", body=ApproveBody, tag="Approvals")
def approve(action_id):
    a = get_owned(AgentAction, action_id, "action")
    body = parse_body(ApproveBody)
    a = approval_service.approve(current_user(), a, body.payload_hash)
    return ok(action_dict(a))


@bp.post("/<action_id>/reject")
@login_required
@doc("Reject a proposal", body=RejectBody, tag="Approvals")
def reject(action_id):
    a = get_owned(AgentAction, action_id, "action")
    body = parse_body(RejectBody)
    approval_service.reject(current_user(), a, body.note)
    db.session.commit()
    return ok(action_dict(a))

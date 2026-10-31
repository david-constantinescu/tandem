from __future__ import annotations

import uuid

from app.extensions import db
from app.models import AuditLog


def audit(user_id: uuid.UUID | None, action: str, *, actor: str = "user", resource_type: str | None = None,
          resource_id=None, **details) -> None:
    """record an audit event. Never pass secrets, document contents or tokens in details."""
    db.session.add(AuditLog(
        user_id=user_id, actor=actor, action=action, resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None, details=details,
    ))

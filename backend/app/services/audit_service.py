import json
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from ..models import AuditLog, User


def log_audit(
    db: Session,
    action: str,
    entity_type: str,
    actor_username: str,
    actor_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """
    Creates an immutable audit log entry.
    """
    details_str = json.dumps(details or {}) if details else None
    audit_entry = AuditLog(
        actor_id=actor_id,
        actor_username=actor_username,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details_json=details_str,
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry

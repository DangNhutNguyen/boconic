from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.jobs import AuditLog

SENSITIVE_KEYS = {"password", "password_hash", "token", "session_token", "secret", "api_key"}

def mask_sensitive_dict(d: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not d:
        return d
    cleaned = {}
    for k, v in d.items():
        if any(s in k.lower() for s in SENSITIVE_KEYS):
            cleaned[k] = "[REDACTED]"
        elif isinstance(v, dict):
            cleaned[k] = mask_sensitive_dict(v)
        else:
            cleaned[k] = v
    return cleaned

class AuditService:
    @staticmethod
    async def log_action(
        db: AsyncSession,
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_type: str = "admin",
        diff_before: Optional[Dict[str, Any]] = None,
        diff_after: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> AuditLog:
        if diff_after is None and details is not None:
            diff_after = details
        entry = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            actor_type=actor_type,
            diff_before=mask_sensitive_dict(diff_before),
            diff_after=mask_sensitive_dict(diff_after),
            reason=reason,
            ip_address=ip_address,
            correlation_id=correlation_id,
        )
        db.add(entry)
        await db.flush()
        return entry

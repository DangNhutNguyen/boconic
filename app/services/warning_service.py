"""
Service for managing user warnings, moderation notices, and appeals.
Ensures transparent conduct feedback and rights review alerts without arbitrary bans.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BoconicException, ErrorCode
from app.db.models.community import UserWarning


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WarningService:
    VALID_CATEGORIES = {
        "validation",
        "rights_review",
        "transaction_reminder",
        "conduct_warning",
        "copyright_concern",
        "incorrect_metadata",
    }
    VALID_SEVERITIES = {"info", "warning", "critical"}

    @classmethod
    async def issue_warning(
        cls,
        db: AsyncSession,
        subject_user_id: str,
        category: str,
        severity: str,
        message: str,
        reason: str,
        issued_by: str,
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> UserWarning:
        """Issue a tracked warning to a user."""
        if category not in cls.VALID_CATEGORIES:
            category = "conduct_warning"
        if severity not in cls.VALID_SEVERITIES:
            severity = "warning"

        warning = UserWarning(
            subject_user_id=subject_user_id,
            category=category,
            severity=severity,
            message=message.strip(),
            reason=reason.strip(),
            issued_by=issued_by,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            appeal_status="none",
            expires_at=expires_at,
        )
        db.add(warning)
        await db.flush()
        return warning

    @classmethod
    async def acknowledge_warning(
        cls,
        db: AsyncSession,
        warning_id: str,
        user_id: str,
    ) -> UserWarning:
        """User marks a warning as acknowledged. Does not forfeit right of appeal."""
        warning = await db.get(UserWarning, warning_id)
        if not warning:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy cảnh báo.", status_code=404)
        if warning.subject_user_id != user_id:
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không phải người nhận cảnh báo này.", status_code=403)

        warning.acknowledged_at = utc_now()
        await db.flush()
        return warning

    @classmethod
    async def submit_appeal(
        cls,
        db: AsyncSession,
        warning_id: str,
        user_id: str,
        appeal_note: str,
    ) -> UserWarning:
        """User submits an appeal for a warning."""
        warning = await db.get(UserWarning, warning_id)
        if not warning:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy cảnh báo.", status_code=404)
        if warning.subject_user_id != user_id:
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không có quyền khiếu nại cảnh báo này.", status_code=403)

        if warning.appeal_status in ("pending", "accepted"):
            raise BoconicException(code=ErrorCode.INVALID_STATE, message="Khiếu nại đang chờ xét duyệt hoặc đã được chấp thuận.", status_code=409)

        warning.appeal_status = "pending"
        warning.appeal_note = appeal_note.strip()
        await db.flush()
        return warning

    @classmethod
    async def review_appeal(
        cls,
        db: AsyncSession,
        warning_id: str,
        moderator_id: str,
        decision: str,  # 'accepted' or 'rejected'
        notes: Optional[str] = None,
    ) -> UserWarning:
        """Moderator reviews an appeal."""
        warning = await db.get(UserWarning, warning_id)
        if not warning:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy cảnh báo.", status_code=404)

        if decision not in ("accepted", "rejected"):
            raise BoconicException(code=ErrorCode.BAD_REQUEST, message="Quyết định khiếu nại không hợp lệ.", status_code=400)

        warning.appeal_status = decision
        if decision == "accepted":
            # If accepted, expire immediately
            warning.expires_at = utc_now()
        if notes:
            warning.reason = f"{warning.reason} | Appeal review: {notes}"
        await db.flush()
        return warning

    @classmethod
    async def get_user_warnings(
        cls,
        db: AsyncSession,
        user_id: str,
        include_expired: bool = False,
    ) -> List[UserWarning]:
        """Fetch all warnings for a user."""
        stmt = select(UserWarning).where(UserWarning.subject_user_id == user_id)
        if not include_expired:
            now = utc_now()
            stmt = stmt.where(
                (UserWarning.expires_at == None) | (UserWarning.expires_at > now)  # noqa: E711
            )
        stmt = stmt.order_by(UserWarning.created_at.desc())
        res = await db.execute(stmt)
        return list(res.scalars().all())

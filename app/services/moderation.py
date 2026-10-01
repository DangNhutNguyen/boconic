from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BoconicException, ErrorCode
from app.db.models.community import Report, UserBlock

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class ModerationService:
    @classmethod
    async def block_user(
        cls, db: AsyncSession, blocker_id: str, blocked_id: str, reason: Optional[str] = None
    ) -> UserBlock:
        if blocker_id == blocked_id:
            raise BoconicException(code=ErrorCode.VALIDATION_ERROR, message="Bạn không thể tự chặn chính mình.")

        existing = await db.execute(
            select(UserBlock).where(
                UserBlock.blocker_id == blocker_id,
                UserBlock.blocked_id == blocked_id,
            )
        )
        block = existing.scalar_one_or_none()
        if not block:
            block = UserBlock(blocker_id=blocker_id, blocked_id=blocked_id, reason=reason)
            db.add(block)
            await db.flush()
        return block

    @classmethod
    async def unblock_user(cls, db: AsyncSession, blocker_id: str, blocked_id: str) -> bool:
        existing = await db.execute(
            select(UserBlock).where(
                UserBlock.blocker_id == blocker_id,
                UserBlock.blocked_id == blocked_id,
            )
        )
        block = existing.scalar_one_or_none()
        if block:
            await db.delete(block)
            await db.flush()
            return True
        return False

    @classmethod
    async def file_report(
        cls,
        db: AsyncSession,
        reporter_id: str,
        target_entity_type: str,
        target_entity_id: str,
        category: str,
        description: str,
        evidence_media_ids: Optional[List[str]] = None,
    ) -> Report:
        report = Report(
            reporter_id=reporter_id,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            category=category,
            description=description.strip(),
            evidence_media_ids=evidence_media_ids or [],
            status="open",
        )
        db.add(report)
        await db.flush()
        return report

    @classmethod
    async def resolve_report(
        cls,
        db: AsyncSession,
        report_id: str,
        resolved_by: str,
        resolution_status: str, # "resolved" or "rejected"
        resolution_note: str,
    ) -> Report:
        report = await db.get(Report, report_id)
        if not report:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy báo cáo vi phạm.", status_code=404)

        report.status = resolution_status
        report.resolved_by = resolved_by
        report.resolution_note = resolution_note.strip()
        report.resolved_at = utc_now()
        await db.flush()
        return report

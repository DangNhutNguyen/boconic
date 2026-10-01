import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import BoconicException, ErrorCode
from app.db.models.catalog import (
    Book, Chapter, ChapterProposal, ChapterResource, ChapterWatch, UserChapterProgress
)
from app.db.models.community import CommunityRequest, SupportOffer
from app.db.models.jobs import OutboxEvent

logger = logging.getLogger(__name__)

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class ChapterService:
    @classmethod
    async def get_book_chapters(
        cls,
        db: AsyncSession,
        book_id: str,
        include_archived: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve structured catalog chapters for a specific Book edition.
        Sorts by order_index, then chapter_number.
        """
        query = select(Chapter).where(Chapter.book_id == book_id)
        if not include_archived:
            query = query.where(Chapter.is_archived == False)
        
        query = query.order_index(Chapter.order_index, Chapter.chapter_number) if hasattr(query, 'order_index') else query.order_by(Chapter.order_index, Chapter.chapter_number)
        
        res = await db.execute(query)
        chapters = list(res.scalars().all())

        results = []
        for ch in chapters:
            results.append({
                "id": ch.id,
                "book_id": ch.book_id,
                "chapter_number": ch.chapter_number,
                "chapter_code": ch.chapter_code or str(ch.chapter_number),
                "order_index": ch.order_index,
                "parent_id": ch.parent_id,
                "title": ch.title,
                "page_start": ch.page_start,
                "page_end": ch.page_end,
                "pagination_basis": ch.pagination_basis,
                "topics": ch.topics or [],
                "source": ch.source,
                "verification_status": ch.verification_status,
                "version": ch.version,
                "is_archived": ch.is_archived,
            })
        return results

    @classmethod
    async def create_chapter_proposal(
        cls,
        db: AsyncSession,
        user_id: str,
        book_id: str,
        action: str,
        proposed_data: Dict[str, Any],
        reason: str,
        source_evidence: Optional[str] = None,
        chapter_id: Optional[str] = None,
        base_version: int = 1,
    ) -> ChapterProposal:
        """
        Create a proposal to add or modify chapters.
        Validates:
        - action in ("create", "update", "delete", "reorder")
        - base_version matches chapter version (detects concurrency conflicts)
        - page_start <= page_end if provided
        - no cyclic parent_id and max hierarchy depth <= 3
        """
        valid_actions = ("create", "update", "delete", "reorder")
        if action not in valid_actions:
            raise BoconicException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Hành động không hợp lệ: {action}. Chấp nhận: {valid_actions}",
                status_code=400,
            )

        book = await db.get(Book, book_id)
        if not book:
            raise BoconicException(
                code=ErrorCode.NOT_FOUND,
                message="Không tìm thấy thông tin sách.",
                status_code=404,
            )

        current_data: Dict[str, Any] = {}
        target_chapter: Optional[Chapter] = None

        if chapter_id:
            target_chapter = await db.get(Chapter, chapter_id)
            if not target_chapter or target_chapter.book_id != book_id:
                raise BoconicException(
                    code=ErrorCode.NOT_FOUND,
                    message="Không tìm thấy chương thuộc sách đã chọn.",
                    status_code=404,
                )

            # Concurrency conflict detection: base_version check
            if target_chapter.version != base_version:
                raise BoconicException(
                    code=ErrorCode.CONFLICT,
                    message=(
                        f"Xung đột phiên bản: Chương đang ở phiên bản {target_chapter.version}, "
                        f"nhưng đề xuất dựa trên phiên bản {base_version}. "
                        "Vui lòng tải lại dữ liệu mới nhất trước khi chỉnh sửa."
                    ),
                    status_code=409,
                )

            current_data = {
                "chapter_number": target_chapter.chapter_number,
                "chapter_code": target_chapter.chapter_code,
                "order_index": target_chapter.order_index,
                "parent_id": target_chapter.parent_id,
                "title": target_chapter.title,
                "page_start": target_chapter.page_start,
                "page_end": target_chapter.page_end,
                "pagination_basis": target_chapter.pagination_basis,
                "topics": target_chapter.topics or [],
            }

        # Validate proposed page range
        page_start = proposed_data.get("page_start")
        page_end = proposed_data.get("page_end")
        if page_start is not None and page_end is not None:
            if page_start < 1 or page_start > page_end:
                raise BoconicException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"Khoảng trang không hợp lệ: {page_start} đến {page_end}. page_start phải >= 1 và <= page_end.",
                    status_code=400,
                )

        # Validate hierarchy and prevent cycles
        parent_id = proposed_data.get("parent_id")
        if parent_id:
            if chapter_id and parent_id == chapter_id:
                raise BoconicException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="Chương không thể là cha của chính mình.",
                    status_code=400,
                )
            parent = await db.get(Chapter, parent_id)
            if not parent or parent.book_id != book_id:
                raise BoconicException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="Chương cha không tồn tại trong cùng ấn bản sách.",
                    status_code=400,
                )
            
            # Check hierarchy depth (max 3)
            depth = 1
            curr_parent_id = parent.parent_id
            while curr_parent_id and depth < 5:
                depth += 1
                if chapter_id and curr_parent_id == chapter_id:
                    raise BoconicException(
                        code=ErrorCode.VALIDATION_ERROR,
                        message="Phát hiện chu trình phân cấp chương.",
                        status_code=400,
                    )
                p = await db.get(Chapter, curr_parent_id)
                curr_parent_id = p.parent_id if p else None
            
            if depth >= 3:
                raise BoconicException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="Cấu trúc chương chỉ hỗ trợ tối đa 3 cấp phân cấp (Chương -> Mục -> Tiểu mục).",
                    status_code=400,
                )

        proposal = ChapterProposal(
            book_id=book_id,
            chapter_id=chapter_id,
            proposer_id=user_id,
            action=action,
            base_version=base_version,
            proposed_data=proposed_data,
            current_data=current_data,
            source_evidence=source_evidence,
            reason=reason.strip(),
            status="pending",
        )
        db.add(proposal)
        await db.flush()

        outbox = OutboxEvent(
            event_type="CHAPTER_PROPOSAL_CREATED",
            aggregate_type="chapter_proposal",
            aggregate_id=proposal.id,
            payload={
                "proposal_id": proposal.id,
                "book_id": book_id,
                "action": action,
                "proposer_id": user_id,
            },
        )
        db.add(outbox)
        await db.flush()

        return proposal

    @classmethod
    async def review_chapter_proposal(
        cls,
        db: AsyncSession,
        proposal_id: str,
        reviewer_id: str,
        approved: bool,
        review_notes: Optional[str] = None,
    ) -> ChapterProposal:
        """
        Admin/Moderator reviews a chapter proposal.
        If approved:
        - Applies modifications into catalog transactionally.
        - Increments version.
        - If page range was changed: flags affected CommunityRequests and SupportOffers with revalidation_required=True.
        - Emits outbox audit event.
        """
        proposal = await db.get(ChapterProposal, proposal_id)
        if not proposal:
            raise BoconicException(
                code=ErrorCode.NOT_FOUND,
                message="Không tìm thấy đề xuất chương.",
                status_code=404,
            )

        if proposal.status != "pending":
            raise BoconicException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Đề xuất đã ở trạng thái {proposal.status}, không thể duyệt lại.",
                status_code=400,
            )

        now = utc_now()
        proposal.reviewed_by = reviewer_id
        proposal.reviewed_at = now
        proposal.review_notes = review_notes

        if not approved:
            proposal.status = "rejected"
            await db.flush()
            db.add(
                OutboxEvent(
                    event_type="CHAPTER_PROPOSAL_REJECTED",
                    aggregate_type="chapter_proposal",
                    aggregate_id=proposal.id,
                    payload={"proposal_id": proposal.id, "reason": review_notes},
                )
            )
            await db.flush()
            return proposal

        proposal.status = "approved"
        data = proposal.proposed_data or {}
        action = proposal.action

        if action == "create":
            # Determine order_index and chapter_number
            existing_count_res = await db.execute(
                select(Chapter).where(Chapter.book_id == proposal.book_id)
            )
            existing_count = len(existing_count_res.scalars().all())

            new_chapter = Chapter(
                book_id=proposal.book_id,
                chapter_number=data.get("chapter_number", existing_count + 1),
                chapter_code=data.get("chapter_code") or str(data.get("chapter_number", existing_count + 1)),
                order_index=data.get("order_index", existing_count + 1),
                parent_id=data.get("parent_id"),
                title=data.get("title", f"Chương {existing_count + 1}"),
                page_start=data.get("page_start"),
                page_end=data.get("page_end"),
                pagination_basis=data.get("pagination_basis", "edition_page_numbers"),
                topics=data.get("topics", []),
                source=f"proposal:{proposal.id}",
                verification_status="verified",
                version=1,
            )
            db.add(new_chapter)
            await db.flush()
            proposal.chapter_id = new_chapter.id

        elif action in ("update", "reorder"):
            if not proposal.chapter_id:
                raise BoconicException(ErrorCode.VALIDATION_ERROR, "Thiếu chapter_id cho cập nhật.")
            chapter = await db.get(Chapter, proposal.chapter_id)
            if not chapter:
                raise BoconicException(ErrorCode.NOT_FOUND, "Không tìm thấy chương mục tiêu.")

            old_range = (chapter.page_start, chapter.page_end)
            new_start = data.get("page_start", chapter.page_start)
            new_end = data.get("page_end", chapter.page_end)
            range_changed = (old_range != (new_start, new_end))

            if "title" in data:
                chapter.title = data["title"]
            if "chapter_code" in data:
                chapter.chapter_code = data["chapter_code"]
            if "chapter_number" in data:
                chapter.chapter_number = data["chapter_number"]
            if "order_index" in data:
                chapter.order_index = data["order_index"]
            if "parent_id" in data:
                chapter.parent_id = data["parent_id"]
            if "pagination_basis" in data:
                chapter.pagination_basis = data["pagination_basis"]
            if "topics" in data:
                chapter.topics = data["topics"]

            chapter.page_start = new_start
            chapter.page_end = new_end
            chapter.verification_status = "verified"
            chapter.version += 1
            await db.flush()

            # If page range changed: flag affected open Needs and SupportOffers for revalidation!
            if range_changed:
                await cls._flag_affected_needs_and_offers_for_revalidation(
                    db, chapter.book_id, chapter.id, old_range, (new_start, new_end)
                )

        elif action == "delete":
            if not proposal.chapter_id:
                raise BoconicException(ErrorCode.VALIDATION_ERROR, "Thiếu chapter_id cho lưu trữ.")
            chapter = await db.get(Chapter, proposal.chapter_id)
            if chapter:
                chapter.is_archived = True
                chapter.version += 1
                await db.flush()

        db.add(
            OutboxEvent(
                event_type="CHAPTER_PROPOSAL_APPROVED",
                aggregate_type="chapter_proposal",
                aggregate_id=proposal.id,
                payload={
                    "proposal_id": proposal.id,
                    "book_id": proposal.book_id,
                    "chapter_id": proposal.chapter_id,
                    "action": action,
                },
            )
        )
        await db.flush()
        return proposal

    @classmethod
    async def _flag_affected_needs_and_offers_for_revalidation(
        cls,
        db: AsyncSession,
        book_id: str,
        chapter_id: str,
        old_range: Tuple[Optional[int], Optional[int]],
        new_range: Tuple[Optional[int], Optional[int]],
    ) -> None:
        """
        Flags any active CommunityRequest and SupportOffer targeting this book/chapter
        as revalidation_required=True, recording event snapshot.
        """
        # Find active requests targeting this book
        req_res = await db.execute(
            select(CommunityRequest).where(
                CommunityRequest.book_id == book_id,
                CommunityRequest.status.in_(["open", "matched"]),
            )
        )
        needs = list(req_res.scalars().all())
        for need in needs:
            # Check if need targets this chapter specifically or chapters scope
            is_targeted = False
            if need.scope_type == "chapters":
                if not need.target_chapters or chapter_id in need.target_chapters:
                    is_targeted = True
            elif need.scope_type == "page_range":
                is_targeted = True

            if is_targeted:
                need.revalidation_required = True
                db.add(
                    OutboxEvent(
                        event_type="NEED_REVALIDATION_REQUIRED",
                        aggregate_type="community_request",
                        aggregate_id=need.id,
                        payload={
                            "need_id": need.id,
                            "chapter_id": chapter_id,
                            "old_range": list(old_range),
                            "new_range": list(new_range),
                            "reason": "Phạm vi trang của chương đã được cập nhật bởi quản trị viên.",
                        },
                    )
                )

                # Also flag offers for this need
                offer_res = await db.execute(
                    select(SupportOffer).where(
                        SupportOffer.need_id == need.id,
                        SupportOffer.status.in_(["proposed", "selected"]),
                    )
                )
                for offer in offer_res.scalars().all():
                    offer.revalidation_required = True

        await db.flush()

    @classmethod
    async def get_user_progress(
        cls,
        db: AsyncSession,
        user_id: str,
        book_id: str,
    ) -> Dict[str, Any]:
        """
        Get personal study progress for a user on a book.
        Invariant:
        - Primary chapters (parent_id is None) form the denominator.
        - Subsections (children) are details and not double-counted in denominator.
        """
        # Query active chapters
        chap_res = await db.execute(
            select(Chapter).where(
                Chapter.book_id == book_id,
                Chapter.is_archived == False,
            ).order_by(Chapter.order_index, Chapter.chapter_number)
        )
        chapters = list(chap_res.scalars().all())

        # Query user progress entries
        prog_res = await db.execute(
            select(UserChapterProgress).where(
                UserChapterProgress.user_id == user_id,
                UserChapterProgress.book_id == book_id,
            )
        )
        progress_map = {p.chapter_id: p for p in prog_res.scalars().all()}

        # Calculate progress
        primary_chapters = [ch for ch in chapters if ch.parent_id is None]
        # If no hierarchy exists, all active chapters are primary
        if not primary_chapters:
            primary_chapters = chapters

        completed_primary_count = sum(
            1 for ch in primary_chapters
            if progress_map.get(ch.id) and progress_map[ch.id].reading_state == "completed"
        )
        in_progress_count = sum(
            1 for p in progress_map.values() if p.reading_state == "in_progress"
        )

        entries = []
        for ch in chapters:
            p = progress_map.get(ch.id)
            entries.append({
                "chapter_id": ch.id,
                "chapter_number": ch.chapter_number,
                "chapter_code": ch.chapter_code or str(ch.chapter_number),
                "title": ch.title,
                "order_index": ch.order_index,
                "parent_id": ch.parent_id,
                "reading_state": p.reading_state if p else "not_started",
                "bookmark_page": p.bookmark_page if p else None,
                "bookmark_note": p.bookmark_note if p else None,
                "personal_notes": p.personal_notes if p else None,
                "started_at": p.started_at.isoformat() if (p and p.started_at) else None,
                "completed_at": p.completed_at.isoformat() if (p and p.completed_at) else None,
                "updated_at": p.updated_at.isoformat() if (p and p.updated_at) else None,
            })

        total_denom = len(primary_chapters)
        pct = round((completed_primary_count / total_denom * 100), 1) if total_denom > 0 else 0.0

        return {
            "book_id": book_id,
            "user_id": user_id,
            "total_primary_chapters": total_denom,
            "completed_primary_chapters": completed_primary_count,
            "in_progress_chapters": in_progress_count,
            "completion_percentage": pct,
            "display_text": f"Đã đọc {completed_primary_count}/{total_denom} chương",
            "entries": entries,
        }

    @classmethod
    async def update_chapter_progress(
        cls,
        db: AsyncSession,
        user_id: str,
        book_id: str,
        chapter_id: str,
        reading_state: str,
        bookmark_page: Optional[int] = None,
        bookmark_note: Optional[str] = None,
        personal_notes: Optional[str] = None,
    ) -> UserChapterProgress:
        """
        Updates user personal reading progress on a specific chapter.
        CRITICAL INVARIANT #8:
        Reading/studying progress changes strictly NEVER mutate Loan status,
        copy availability, Need status, or trust score!
        """
        valid_states = ("not_started", "in_progress", "completed", "paused")
        if reading_state not in valid_states:
            raise BoconicException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Trạng thái đọc không hợp lệ: {reading_state}. Hợp lệ: {valid_states}",
                status_code=400,
            )

        chapter = await db.get(Chapter, chapter_id)
        if not chapter or chapter.book_id != book_id:
            raise BoconicException(
                code=ErrorCode.NOT_FOUND,
                message="Không tìm thấy chương tương ứng với sách này.",
                status_code=404,
            )

        prog_res = await db.execute(
            select(UserChapterProgress).where(
                UserChapterProgress.user_id == user_id,
                UserChapterProgress.chapter_id == chapter_id,
            )
        )
        progress = prog_res.scalar_one_or_none()

        now = utc_now()
        if not progress:
            progress = UserChapterProgress(
                user_id=user_id,
                book_id=book_id,
                chapter_id=chapter_id,
                reading_state=reading_state,
                bookmark_page=bookmark_page,
                bookmark_note=bookmark_note.strip() if bookmark_note else None,
                personal_notes=personal_notes.strip() if personal_notes else None,
                started_at=now if reading_state in ("in_progress", "completed") else None,
                completed_at=now if reading_state == "completed" else None,
                version=1,
            )
            db.add(progress)
        else:
            old_state = progress.reading_state
            progress.reading_state = reading_state
            if bookmark_page is not None:
                progress.bookmark_page = bookmark_page
            if bookmark_note is not None:
                progress.bookmark_note = bookmark_note.strip()
            if personal_notes is not None:
                progress.personal_notes = personal_notes.strip()

            if old_state != "completed" and reading_state == "completed":
                progress.completed_at = now
            elif old_state == "completed" and reading_state != "completed":
                progress.completed_at = None

            if not progress.started_at and reading_state in ("in_progress", "completed"):
                progress.started_at = now

            progress.version += 1
            progress.updated_at = now

        await db.flush()
        return progress

    @classmethod
    async def export_user_notes(
        cls,
        db: AsyncSession,
        user_id: str,
        book_id: str,
    ) -> str:
        """
        Export user's private notes and bookmarks for a book as Markdown.
        Private to user only.
        """
        book = await db.get(Book, book_id)
        title = book.title if book else "Sách"

        summary = await cls.get_user_progress(db, user_id, book_id)
        lines = [
            f"# Ghi chú học tập cá nhân: {title}",
            f"Tiến độ: {summary['display_text']} ({summary['completion_percentage']}%)",
            "",
            "---",
            "",
        ]

        has_notes = False
        for entry in summary["entries"]:
            if entry["bookmark_page"] or entry["bookmark_note"] or entry["personal_notes"]:
                has_notes = True
                lines.append(f"## {entry['chapter_code']}. {entry['title']}")
                lines.append(f"**Trạng thái**: `{entry['reading_state']}`")
                if entry["bookmark_page"]:
                    bm = f"Trang {entry['bookmark_page']}"
                    if entry["bookmark_note"]:
                        bm += f" ({entry['bookmark_note']})"
                    lines.append(f"- 🔖 **Bookmark**: {bm}")
                if entry["personal_notes"]:
                    lines.append(f"- 📝 **Ghi chú**:\n{entry['personal_notes']}")
                lines.append("")

        if not has_notes:
            lines.append("*Chưa có ghi chú hoặc bookmark nào cho các chương sách này.*")

        return "\n".join(lines)

    @classmethod
    async def add_chapter_resource(
        cls,
        db: AsyncSession,
        user_id: str,
        chapter_id: str,
        title: str,
        resource_type: str = "link",
        url: Optional[str] = None,
        file_path: Optional[str] = None,
        page_start: Optional[int] = None,
        page_end: Optional[int] = None,
        rights_basis: str = "personal_fair_use",
        allowed_actions: Optional[List[str]] = None,
    ) -> ChapterResource:
        """
        Attach a digital resource/link to a chapter.
        Defaults to quarantine/private. Requires rights verification to become public.
        """
        chapter = await db.get(Chapter, chapter_id)
        if not chapter:
            raise BoconicException(ErrorCode.NOT_FOUND, "Không tìm thấy chương.")

        resource = ChapterResource(
            chapter_id=chapter_id,
            book_id=chapter.book_id,
            owner_id=user_id,
            title=title.strip(),
            resource_type=resource_type,
            url=url.strip() if url else None,
            file_path=file_path,
            page_start=page_start,
            page_end=page_end,
            rights_basis=rights_basis,
            allowed_actions=allowed_actions or ["view"],
            verification_status="quarantine", # quarantine by default!
            is_public=False,
            version=1,
        )
        db.add(resource)
        await db.flush()
        return resource

    @classmethod
    async def review_chapter_resource(
        cls,
        db: AsyncSession,
        resource_id: str,
        reviewer_id: str,
        approved: bool,
        is_public: bool = True,
    ) -> ChapterResource:
        """
        Moderator reviews chapter resource. If approved, can be set to verified and public.
        """
        res = await db.get(ChapterResource, resource_id)
        if not res:
            raise BoconicException(ErrorCode.NOT_FOUND, "Không tìm thấy tài nguyên chương.")

        now = utc_now()
        res.verified_by = reviewer_id
        res.verified_at = now
        res.verification_status = "verified" if approved else "rejected"
        res.is_public = (approved and is_public)
        res.version += 1
        res.updated_at = now

        await db.flush()
        return res

    @classmethod
    async def watch_chapter(
        cls,
        db: AsyncSession,
        user_id: str,
        book_id: str,
        chapter_id: Optional[str] = None,
        notify_preference: str = "all",
    ) -> ChapterWatch:
        """
        Subscribe user to watch for newly available sources for a missing chapter.
        """
        watch_q = select(ChapterWatch).where(
            ChapterWatch.user_id == user_id,
            ChapterWatch.book_id == book_id,
            ChapterWatch.chapter_id == chapter_id,
        )
        existing = (await db.execute(watch_q)).scalar_one_or_none()
        if existing:
            existing.is_active = True
            existing.notify_preference = notify_preference
            await db.flush()
            return existing

        watch = ChapterWatch(
            user_id=user_id,
            book_id=book_id,
            chapter_id=chapter_id,
            notify_preference=notify_preference,
            is_active=True,
        )
        db.add(watch)
        await db.flush()
        return watch

    @classmethod
    async def unwatch_chapter(
        cls,
        db: AsyncSession,
        user_id: str,
        book_id: str,
        chapter_id: Optional[str] = None,
    ) -> bool:
        watch_q = select(ChapterWatch).where(
            ChapterWatch.user_id == user_id,
            ChapterWatch.book_id == book_id,
            ChapterWatch.chapter_id == chapter_id,
        )
        existing = (await db.execute(watch_q)).scalar_one_or_none()
        if existing:
            existing.is_active = False
            await db.flush()
            return True
        return False

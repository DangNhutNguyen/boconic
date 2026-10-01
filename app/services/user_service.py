"""
Service for User Management and Tracking Resources in Use.
Manages user lifecycle, queries physical copies in custody, lent items,
owned inventory, digital resources, study progress, trust profile, and warnings.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import BoconicException, ErrorCode
from app.db.models.catalog import Book, BookCopy, Chapter, ChapterResource, UserChapterProgress
from app.db.models.community import (
    CommunityRequest,
    SupportOffer,
    TrustEvent,
    UserWarning,
)
from app.db.models.identity import User, UserLocation, UserSettings
from app.db.models.jobs import AuditLog, OutboxEvent
from app.db.models.lending import CustodyEvent, Loan, LoanEvent
from app.services.audit import AuditService
from app.services.trust import TrustService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserService:
    @classmethod
    async def list_users(
        cls,
        db: AsyncSession,
        search: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        List users with pagination, search, status filtering, and summarized resource metrics.
        """
        stmt = select(User)

        if search and search.strip():
            term = f"%{search.strip()}%"
            conditions = [
                User.display_name.ilike(term),
                User.public_alias.ilike(term),
                User.telegram_username.ilike(term),
            ]
            if search.strip().isdigit():
                conditions.append(User.telegram_user_id == int(search.strip()))
            stmt = stmt.where(or_(*conditions))

        if status and status != "all":
            stmt = stmt.where(User.status == status)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = (await db.execute(count_stmt)).scalar_one() or 0

        # Paginate
        stmt = stmt.order_by(desc(User.created_at)).offset((page - 1) * page_size).limit(page_size)
        res = await db.execute(stmt)
        users = list(res.scalars().all())

        now = utc_now()
        user_list = []
        for u in users:
            # Active borrowings (Loan where borrower == u and status in reserved, active, return_pending)
            borrowings_q = select(func.count(Loan.id)).where(
                Loan.borrower_id == u.id,
                Loan.status.in_(["reserved", "active", "return_pending"]),
            )
            active_borrowings = (await db.execute(borrowings_q)).scalar_one() or 0

            # Overdue borrowings
            overdue_q = select(func.count(Loan.id)).where(
                Loan.borrower_id == u.id,
                Loan.status == "active",
                Loan.due_at < now,
            )
            overdue_borrowings = (await db.execute(overdue_q)).scalar_one() or 0

            # Active lendings (Loan where lender == u and status in reserved, active, return_pending)
            lendings_q = select(func.count(Loan.id)).where(
                Loan.lender_id == u.id,
                Loan.status.in_(["reserved", "active", "return_pending"]),
            )
            active_lendings = (await db.execute(lendings_q)).scalar_one() or 0

            # Owned copies
            owned_q = select(func.count(BookCopy.id)).where(BookCopy.owner_id == u.id)
            owned_copies = (await db.execute(owned_q)).scalar_one() or 0

            # Warnings count
            warnings_q = select(func.count(UserWarning.id)).where(UserWarning.subject_user_id == u.id)
            warnings_count = (await db.execute(warnings_q)).scalar_one() or 0

            # Trust profile
            trust_profile = await TrustService.get_user_trust_profile(db, u.id)

            user_list.append({
                "user": u,
                "active_borrowings": active_borrowings,
                "overdue_borrowings": overdue_borrowings,
                "active_lendings": active_lendings,
                "owned_copies": owned_copies,
                "warnings_count": warnings_count,
                "trust_profile": trust_profile,
            })

        # Global stats for dashboard cards
        total_users_count = (await db.execute(select(func.count(User.id)))).scalar_one() or 0
        active_users_count = (await db.execute(select(func.count(User.id)).where(User.status == "active"))).scalar_one() or 0
        borrowing_users_count = (
            await db.execute(
                select(func.count(func.distinct(Loan.borrower_id))).where(
                    Loan.status.in_(["reserved", "active", "return_pending"])
                )
            )
        ).scalar_one() or 0
        flagged_users_count = (
            await db.execute(
                select(func.count(User.id)).where(User.status.in_(["suspended", "banned"]))
            )
        ).scalar_one() or 0

        total_pages = max(1, (total_count + page_size - 1) // page_size)

        return {
            "users": user_list,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "stats": {
                "total_users": total_users_count,
                "active_users": active_users_count,
                "borrowing_users": borrowing_users_count,
                "flagged_users": flagged_users_count,
            },
        }

    @classmethod
    async def get_user_resource_details(cls, db: AsyncSession, user_id: str) -> Dict[str, Any]:
        """
        Get complete details of a user and all physical/digital resources currently in use.
        """
        user = await db.get(User, user_id)
        if not user:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy người dùng.", status_code=404)

        now = utc_now()

        # 1. Location and Settings
        loc_res = await db.execute(select(UserLocation).where(UserLocation.user_id == user_id))
        locations = list(loc_res.scalars().all())

        set_res = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
        settings_obj = set_res.scalar_one_or_none()

        # 2. Trust Profile and Warnings
        trust_profile = await TrustService.get_user_trust_profile(db, user_id)
        warn_res = await db.execute(
            select(UserWarning)
            .where(UserWarning.subject_user_id == user_id)
            .order_by(desc(UserWarning.created_at))
        )
        warnings = list(warn_res.scalars().all())

        # 3. Tài nguyên đang mượn / đang giữ (Borrowings in Custody)
        borrowings_res = await db.execute(
            select(Loan)
            .options(
                selectinload(Loan.copy).selectinload(BookCopy.book),
                selectinload(Loan.lender),
            )
            .where(
                Loan.borrower_id == user_id,
                Loan.status.in_(["reserved", "active", "return_pending"]),
            )
            .order_by(desc(Loan.created_at))
        )
        borrowed_loans_raw = list(borrowings_res.scalars().all())
        borrowed_loans = []
        for loan in borrowed_loans_raw:
            due = loan.due_at
            if due is not None and due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            is_overdue = loan.status == "active" and due is not None and due < now
            borrowed_loans.append({
                "loan": loan,
                "book": loan.copy.book if loan.copy else None,
                "copy": loan.copy,
                "book_copy": loan.copy,
                "lender": loan.lender,
                "is_overdue": is_overdue,
                "due_at": due,
            })

        # 4. Tài nguyên cá nhân đang cho người khác mượn (Currently Lent Out)
        lendings_res = await db.execute(
            select(Loan)
            .options(
                selectinload(Loan.copy).selectinload(BookCopy.book),
                selectinload(Loan.borrower),
            )
            .where(
                Loan.lender_id == user_id,
                Loan.status.in_(["reserved", "active", "return_pending"]),
            )
            .order_by(desc(Loan.created_at))
        )
        lent_loans_raw = list(lendings_res.scalars().all())
        lent_loans = []
        for loan in lent_loans_raw:
            due = loan.due_at
            if due is not None and due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            is_overdue = loan.status == "active" and due is not None and due < now
            lent_loans.append({
                "loan": loan,
                "book": loan.copy.book if loan.copy else None,
                "copy": loan.copy,
                "book_copy": loan.copy,
                "borrower": loan.borrower,
                "is_overdue": is_overdue,
                "due_at": due,
            })

        # 5. Kho sách cá nhân sở hữu (Owned Copies & Coverage)
        copies_res = await db.execute(
            select(BookCopy)
            .options(
                selectinload(BookCopy.book),
                selectinload(BookCopy.coverage_ranges),
                selectinload(BookCopy.current_holder),
            )
            .where(BookCopy.owner_id == user_id)
            .order_by(desc(BookCopy.created_at))
        )
        owned_copies = list(copies_res.scalars().all())

        # 6. Tài nguyên số / Chương sách đã tải lên (Chapter Resources)
        resources_res = await db.execute(
            select(ChapterResource)
            .options(
                selectinload(ChapterResource.chapter).selectinload(Chapter.book)
            )
            .where(ChapterResource.owner_id == user_id)
            .order_by(desc(ChapterResource.created_at))
        )
        chapter_resources = list(resources_res.scalars().all())

        # 7. Nhu cầu cộng đồng đang mở (Active Needs)
        needs_res = await db.execute(
            select(CommunityRequest)
            .options(selectinload(CommunityRequest.book))
            .where(CommunityRequest.user_id == user_id, CommunityRequest.status == "open")
            .order_by(desc(CommunityRequest.created_at))
        )
        open_needs = list(needs_res.scalars().all())

        # 8. Đề nghị hỗ trợ đang mở (Active Support Offers)
        offers_res = await db.execute(
            select(SupportOffer)
            .options(selectinload(SupportOffer.need).selectinload(CommunityRequest.book))
            .where(
                SupportOffer.provider_user_id == user_id,
                SupportOffer.status.in_(["pending", "accepted"]),
            )
            .order_by(desc(SupportOffer.created_at))
        )
        open_offers = list(offers_res.scalars().all())

        # 9. Tiến độ học tập cá nhân (Study Progress)
        progress_res = await db.execute(
            select(UserChapterProgress)
            .options(
                selectinload(UserChapterProgress.chapter),
                selectinload(UserChapterProgress.book),
            )
            .where(UserChapterProgress.user_id == user_id)
            .order_by(desc(UserChapterProgress.updated_at))
        )
        progress_records = list(progress_res.scalars().all())
        completed_chapters = sum(1 for p in progress_records if p.reading_state == "completed")
        in_progress_chapters = sum(1 for p in progress_records if p.reading_state == "in_progress")
        notes_count = sum(1 for p in progress_records if p.personal_notes and p.personal_notes.strip())

        return {
            "user": user,
            "locations": locations,
            "settings": settings_obj,
            "trust_profile": trust_profile,
            "warnings": warnings,
            "borrowed_loans": borrowed_loans,
            "lent_loans": lent_loans,
            "owned_copies": owned_copies,
            "chapter_resources": chapter_resources,
            "open_needs": open_needs,
            "open_offers": open_offers,
            "study_progress": {
                "records": progress_records,
                "completed_chapters": completed_chapters,
                "in_progress_chapters": in_progress_chapters,
                "notes_count": notes_count,
            },
        }

    @classmethod
    async def update_user_status(
        cls,
        db: AsyncSession,
        user_id: str,
        new_status: str,
        reason: str,
        admin_id: str,
    ) -> User:
        """
        Update user account status (active, suspended, banned).
        Records audit log with diff.
        """
        valid_statuses = {"active", "suspended", "banned"}
        if new_status not in valid_statuses:
            raise BoconicException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Trạng thái '{new_status}' không hợp lệ. Phải là: {', '.join(valid_statuses)}.",
                status_code=400,
            )

        user = await db.get(User, user_id)
        if not user:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy người dùng.", status_code=404)

        old_status = user.status
        user.status = new_status
        user.updated_at = utc_now()

        await AuditService.log_action(
            db,
            action="update_user_status",
            entity_type="user",
            entity_id=user.id,
            actor_id=admin_id,
            actor_type="admin",
            diff_before={"status": old_status},
            diff_after={"status": new_status},
            reason=reason.strip() if reason else "Admin status update",
        )

        await db.flush()
        return user

    @classmethod
    async def admin_force_return_loan(
        cls,
        db: AsyncSession,
        loan_id: str,
        admin_id: str,
        resolution_notes: str,
    ) -> Loan:
        """
        Admin resolution: forcibly complete a loan and restore physical copy availability.
        Used when book has been physically returned or dispute resolved administratively.
        """
        loan = await db.get(Loan, loan_id)
        if not loan:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy giao dịch mượn.", status_code=404)

        if loan.status not in ("reserved", "active", "return_pending", "disputed"):
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message=f"Giao dịch ở trạng thái '{loan.status}' không thể thực hiện hoàn tất cưỡng chế.",
                status_code=409,
            )

        now = utc_now()
        old_status = loan.status
        loan.status = "returned"
        loan.returned_at = now

        copy = await db.get(BookCopy, loan.copy_id)
        if copy:
            copy.circulation_status = "available"
            copy.current_holder_id = copy.owner_id

        # Custody event
        custody = CustodyEvent(
            copy_id=loan.copy_id,
            loan_id=loan.id,
            from_holder_id=loan.borrower_id,
            to_holder_id=copy.owner_id if copy else loan.lender_id,
            reason="admin_force_return",
        )
        db.add(custody)

        # Trust event (correction)
        trust_event = TrustEvent(
            user_id=loan.borrower_id,
            loan_id=loan.id,
            event_type="correction",
            score_delta=0.0,
            reason=f"Quản trị viên hoàn tất giao dịch: {resolution_notes}",
        )
        db.add(trust_event)

        # Loan event
        loan_event = LoanEvent(
            loan_id=loan.id,
            actor_id=admin_id,
            action="admin_force_return",
            from_status=old_status,
            to_status="returned",
            reason=resolution_notes,
        )
        db.add(loan_event)

        # Audit log
        await AuditService.log_action(
            db,
            action="admin_force_return_loan",
            entity_type="loan",
            entity_id=loan.id,
            actor_id=admin_id,
            actor_type="admin",
            diff_before={"status": old_status},
            diff_after={"status": "returned"},
            reason=resolution_notes,
        )

        # Outbox event
        outbox = OutboxEvent(
            event_type="LOAN_ADMIN_RESOLVED",
            aggregate_type="loan",
            aggregate_id=loan.id,
            payload={
                "loan_id": loan.id,
                "copy_id": loan.copy_id,
                "borrower_id": loan.borrower_id,
                "resolved_by": admin_id,
                "notes": resolution_notes,
            },
        )
        db.add(outbox)

        await db.flush()
        return loan

    @classmethod
    async def get_user_resources_summary_api(cls, db: AsyncSession, user_id: str) -> Dict[str, Any]:
        """
        JSON-serializable summary of all user resources in use for client & bot APIs.
        """
        details = await cls.get_user_resource_details(db, user_id)
        u = details["user"]

        borrowed = []
        for b in details["borrowed_loans"]:
            loan = b["loan"]
            book = b["book"]
            copy = b["copy"]
            lender = b["lender"]
            borrowed.append({
                "loan_id": loan.id,
                "book_id": book.id if book else None,
                "book_title": book.title if book else "N/A",
                "copy_id": copy.id if copy else None,
                "copy_code": copy.barcode if copy else None,
                "lender_id": lender.id if lender else None,
                "lender_name": lender.display_name if lender else "N/A",
                "status": loan.status,
                "handed_over_at": loan.handed_over_at.isoformat() if loan.handed_over_at else None,
                "due_at": b["due_at"].isoformat() if b["due_at"] else None,
                "is_overdue": b["is_overdue"],
            })

        lent = []
        for l in details["lent_loans"]:
            loan = l["loan"]
            book = l["book"]
            copy = l["copy"]
            borrower = l["borrower"]
            lent.append({
                "loan_id": loan.id,
                "book_id": book.id if book else None,
                "book_title": book.title if book else "N/A",
                "copy_id": copy.id if copy else None,
                "copy_code": copy.barcode if copy else None,
                "borrower_id": borrower.id if borrower else None,
                "borrower_name": borrower.display_name if borrower else "N/A",
                "status": loan.status,
                "due_at": l["due_at"].isoformat() if l["due_at"] else None,
                "is_overdue": l["is_overdue"],
            })

        owned = []
        for c in details["owned_copies"]:
            owned.append({
                "copy_id": c.id,
                "book_id": c.book_id,
                "book_title": c.book.title if c.book else "N/A",
                "is_partial": c.is_partial,
                "circulation_status": c.circulation_status,
                "condition_status": c.condition,
                "condition": c.condition,
                "current_holder_id": c.current_holder_id,
            })

        resources = []
        for r in details["chapter_resources"]:
            resources.append({
                "resource_id": r.id,
                "chapter_id": r.chapter_id,
                "chapter_title": r.chapter.title if r.chapter else "N/A",
                "book_title": r.chapter.book.title if r.chapter and r.chapter.book else "N/A",
                "resource_type": r.resource_type,
                "title": r.title,
                "url": r.url,
                "rights_status": r.verification_status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

        needs = []
        for req in details["open_needs"]:
            needs.append({
                "need_id": req.id,
                "book_id": req.book_id,
                "book_title": req.book.title if req.book else "N/A",
                "scope_type": req.scope_type,
                "target_chapters": req.target_chapters,
                "revalidation_required": req.revalidation_required,
                "created_at": req.created_at.isoformat() if req.created_at else None,
            })

        return {
            "user_id": u.id,
            "display_name": u.display_name,
            "public_alias": u.public_alias,
            "status": u.status,
            "telegram_user_id": u.telegram_user_id,
            "borrowed_loans": borrowed,
            "lent_loans": lent,
            "owned_copies": owned,
            "chapter_resources": resources,
            "open_needs": needs,
            "study_progress": {
                "completed_chapters": details["study_progress"]["completed_chapters"],
                "in_progress_chapters": details["study_progress"]["in_progress_chapters"],
                "notes_count": details["study_progress"]["notes_count"],
            },
            "trust_profile": details["trust_profile"],
        }

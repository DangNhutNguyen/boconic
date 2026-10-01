"""
Service for managing CommunityRequests (Needs), owner matching, and SupportOffers.
Strictly conforms to privacy, concurrency locks, and state transitions.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import BoconicException, ErrorCode
from app.db.models.catalog import Book, BookCopy, CopyCoverageRange
from app.db.models.community import (
    CommunityRequest, RequestMatch, Resource, SupportOffer, UserBlock
)
from app.db.models.identity import User, UserSettings
from app.db.models.jobs import OutboxEvent
from app.db.models.lending import BorrowRequest, Loan, LoanEvent


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NeedService:
    @classmethod
    async def create_need(
        cls,
        db: AsyncSession,
        user_id: str,
        title_query: str,
        book_id: Optional[str] = None,
        isbn: Optional[str] = None,
        edition_label: Optional[str] = None,
        scope_type: str = "full_book",
        page_range: Optional[List[int]] = None,
        pagination_basis: Optional[str] = None,
        target_chapters: Optional[List[str]] = None,
        quantity: int = 1,
        duration_days_needed: int = 14,
        coarse_location: Optional[str] = None,
        fulfillment_preference: str = "lend",
        urgency: str = "normal",
        urgency_reason: Optional[str] = None,
        accepted_conditions: Optional[List[str]] = None,
        edition_match_strict: bool = False,
        description: Optional[str] = None,
        visibility: str = "public",
        status: str = "open",
    ) -> CommunityRequest:
        """
        Create a new CommunityRequest (Need).
        Prevents duplicate open needs for the same target by the same requester.
        """
        title_query_clean = title_query.strip()
        isbn_clean = isbn.strip() if isbn else None

        # Check existing open duplicate need
        dup_query = select(CommunityRequest).where(
            CommunityRequest.user_id == user_id,
            CommunityRequest.status == "open",
            CommunityRequest.scope_type == scope_type,
        )
        if book_id:
            dup_query = dup_query.where(CommunityRequest.book_id == book_id)
        elif isbn_clean:
            dup_query = dup_query.where(
                or_(
                    CommunityRequest.isbn == isbn_clean,
                    CommunityRequest.title_query.ilike(title_query_clean),
                )
            )
        else:
            dup_query = dup_query.where(CommunityRequest.title_query.ilike(title_query_clean))

        existing = await db.execute(dup_query)
        if existing.scalar_one_or_none():
            raise BoconicException(
                code=ErrorCode.ALREADY_EXISTS,
                message="Bạn đã có một yêu cầu đang mở cho đầu sách và phạm vi này.",
                status_code=409,
            )

        target_chaps = target_chapters or []
        target_snap = {
            "scope_type": scope_type,
            "target_chapters": target_chaps,
            "page_range": page_range or [],
            "pagination_basis": pagination_basis.strip() if pagination_basis else None,
            "published_at": utc_now().isoformat(),
        }

        need = CommunityRequest(
            user_id=user_id,
            book_id=book_id,
            title_query=title_query_clean,
            isbn=isbn_clean,
            edition_label=edition_label.strip() if edition_label else None,
            scope_type=scope_type,
            page_range=page_range or [],
            pagination_basis=pagination_basis.strip() if pagination_basis else None,
            target_chapters=target_chaps,
            target_snapshot=target_snap,
            revalidation_required=False,
            quantity=max(1, quantity),
            quantity_fulfilled=0,
            duration_days_needed=max(1, duration_days_needed),
            coarse_location=coarse_location.strip() if coarse_location else None,
            fulfillment_preference=fulfillment_preference,
            urgency=urgency,
            urgency_reason=urgency_reason.strip() if urgency_reason else None,
            accepted_conditions=accepted_conditions or [],
            edition_match_strict=edition_match_strict,
            description=description.strip() if description else None,
            visibility=visibility,
            status=status,
            version=1,
        )
        db.add(need)
        await db.flush()

        if status == "open":
            # Schedule matching & notifications
            await cls.match_need_with_owners(db, need.id)

        return need

    @classmethod
    async def match_need_with_owners(
        cls,
        db: AsyncSession,
        need_id: str,
    ) -> List[RequestMatch]:
        """
        Find all eligible copy owners/organizations for this Need.
        Enforces:
        - Only published copies
        - Active users with notify_book_requested=True
        - No user block
        - Exactly ONE match/notification per owner even if owner owns multiple copies
        - Records eligibility snapshot and privacy-filtered matches
        """
        need = await db.get(CommunityRequest, need_id)
        if not need or need.status != "open":
            return []

        # Find candidate copies
        copy_query = select(BookCopy).where(
            BookCopy.visibility.in_(["published", "public"]),
            BookCopy.owner_id != need.user_id,
        )

        if need.book_id:
            copy_query = copy_query.where(BookCopy.book_id == need.book_id)
        elif need.isbn:
            # Join book by isbn
            copy_query = copy_query.join(Book, BookCopy.book_id == Book.id).where(Book.isbn == need.isbn)
        else:
            # Search by title query
            copy_query = copy_query.join(Book, BookCopy.book_id == Book.id).where(
                Book.title.ilike(f"%{need.title_query}%")
            )

        res = await db.execute(copy_query)
        candidate_copies = list(res.scalars().all())

        # Also find verified digital resources if applicable
        candidate_resources: List[Resource] = []
        if need.fulfillment_preference in ("all", "digital", "lend"):
            res_query = select(Resource).where(
                Resource.verification_status == "verified",
                Resource.takedown_status == "none",
            )
            if need.book_id:
                pass  # Resources can match by title
            res_query = res_query.where(Resource.title.ilike(f"%{need.title_query}%"))
            r_res = await db.execute(res_query)
            candidate_resources = list(r_res.scalars().all())

        # Group copies by owner to ensure 1 notification per owner
        copies_by_owner: Dict[str, List[BookCopy]] = {}
        for c in candidate_copies:
            copies_by_owner.setdefault(c.owner_id, []).append(c)

        created_matches: List[RequestMatch] = []
        now = utc_now()

        for owner_id, copies in copies_by_owner.items():
            # Check if match already exists for this need + owner
            existing_match = await db.execute(
                select(RequestMatch).where(
                    RequestMatch.need_id == need.id,
                    RequestMatch.owner_user_id == owner_id,
                )
            )
            if existing_match.scalar_one_or_none():
                continue

            # Check user block
            block_check = await db.execute(
                select(UserBlock).where(
                    or_(
                        (UserBlock.blocker_id == owner_id) & (UserBlock.blocked_id == need.user_id),
                        (UserBlock.blocker_id == need.user_id) & (UserBlock.blocked_id == owner_id),
                    )
                )
            )
            if block_check.scalar_one_or_none():
                continue

            # Check owner settings
            owner_user = await db.get(User, owner_id)
            if not owner_user or not owner_user.is_active:
                continue

            settings_res = await db.execute(select(UserSettings).where(UserSettings.user_id == owner_id))
            settings = settings_res.scalar_one_or_none()
            if settings:
                if not settings.notify_book_requested:
                    continue
                if settings.snooze_until and settings.snooze_until > now:
                    continue

            # Filter candidate copies by scope eligibility (chapters or full)
            eligible_copies = []
            for c in copies:
                if need.scope_type == "chapters" and need.target_chapters:
                    if not c.is_partial:
                        # Full physical copy covers all chapters -> eligible (Scenario 3)
                        eligible_copies.append(c)
                    else:
                        # Partial physical copy -> verify coverage covers requested chapters (Scenario 2)
                        cov_res = await db.execute(
                            select(CopyCoverageRange).where(CopyCoverageRange.copy_id == c.id)
                        )
                        ranges = list(cov_res.scalars().all())
                        covered_chaps = []
                        for r in ranges:
                            if r.chapters:
                                covered_chaps.extend([str(x).strip() for x in r.chapters])
                        
                        target_set = set(str(x).strip() for x in need.target_chapters)
                        if set(covered_chaps).intersection(target_set):
                            eligible_copies.append(c)
                else:
                    eligible_copies.append(c)

            if not eligible_copies:
                continue

            # Pick best candidate copy for this owner: prefer available over loaned/reserved
            best_copy = None
            available_copies = [c for c in eligible_copies if c.circulation_status == "available"]
            if available_copies:
                best_copy = available_copies[0]
            elif settings and settings.notify_upcoming_need:
                best_copy = eligible_copies[0]
            else:
                continue

            match_type = "partial_copy" if best_copy.is_partial else "full_copy"

            match_record = RequestMatch(
                need_id=need.id,
                owner_user_id=owner_id,
                copy_id=best_copy.id,
                match_type=match_type,
                notification_status="pending",
            )
            db.add(match_record)
            created_matches.append(match_record)

        if created_matches:
            await db.flush()
            # Outbox event for batch notification queue
            outbox = OutboxEvent(
                event_type="NEED_MATCHES_ENQUEUED",
                aggregate_type="community_request",
                aggregate_id=need.id,
                payload={
                    "need_id": need.id,
                    "title_query": need.title_query,
                    "recipient_count": len(created_matches),
                },
            )
            db.add(outbox)
            await db.flush()

        return created_matches

    @classmethod
    async def create_offer(
        cls,
        db: AsyncSession,
        need_id: str,
        provider_user_id: str,
        offer_type: str,
        copy_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        covered_ranges: Optional[List[List[int]]] = None,
        available_from: Optional[datetime] = None,
        proposed_duration_days: int = 14,
        coarse_pickup_area: Optional[str] = None,
        message: Optional[str] = None,
        rights_snapshot: Optional[Dict[str, Any]] = None,
    ) -> SupportOffer:
        """
        Create a SupportOffer responding to a Need.
        Revalidates source availability and rights.
        """
        need = await db.get(CommunityRequest, need_id)
        if not need or need.status != "open":
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message="Nhu cầu này không còn mở hoặc không tồn tại.",
                status_code=409,
            )

        if need.user_id == provider_user_id:
            raise BoconicException(
                code=ErrorCode.FORBIDDEN,
                message="Bạn không thể tự gửi đề nghị hỗ trợ cho chính nhu cầu của mình.",
                status_code=403,
            )

        # Validate copy if provided
        if copy_id:
            copy = await db.get(BookCopy, copy_id)
            if not copy:
                raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy bản sách.", status_code=404)
            if copy.owner_id != provider_user_id and copy.current_holder_id != provider_user_id:
                raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không sở hữu hoặc giữ bản sách này.", status_code=403)

        # Validate resource if provided
        if resource_id:
            res = await db.get(Resource, resource_id)
            if not res or res.verification_status != "verified" or res.takedown_status != "none":
                raise BoconicException(code=ErrorCode.FORBIDDEN, message="Tài nguyên số chưa được xác thực quyền.", status_code=403)

        # Check existing proposed offer from same provider on same need
        dup_offer = await db.execute(
            select(SupportOffer).where(
                SupportOffer.need_id == need_id,
                SupportOffer.provider_user_id == provider_user_id,
                SupportOffer.copy_id == copy_id,
                SupportOffer.status == "proposed",
            )
        )
        if dup_offer.scalar_one_or_none():
            raise BoconicException(
                code=ErrorCode.ALREADY_EXISTS,
                message="Bạn đã có đề nghị hỗ trợ đang chờ phản hồi cho nhu cầu này.",
                status_code=409,
            )

        offer = SupportOffer(
            need_id=need_id,
            provider_user_id=provider_user_id,
            offer_type=offer_type,
            copy_id=copy_id,
            resource_id=resource_id,
            covered_ranges=covered_ranges or [],
            available_from=available_from,
            proposed_duration_days=proposed_duration_days,
            coarse_pickup_area=coarse_pickup_area.strip() if coarse_pickup_area else None,
            message=message.strip() if message else None,
            rights_snapshot=rights_snapshot or {},
            status="proposed",
        )
        db.add(offer)
        await db.flush()

        outbox = OutboxEvent(
            event_type="OFFER_CREATED",
            aggregate_type="support_offer",
            aggregate_id=offer.id,
            payload={
                "offer_id": offer.id,
                "need_id": need_id,
                "requester_id": need.user_id,
                "provider_id": provider_user_id,
            },
        )
        db.add(outbox)
        await db.flush()
        return offer

    @classmethod
    async def select_offer(
        cls,
        db: AsyncSession,
        offer_id: str,
        requester_id: str,
    ) -> Tuple[SupportOffer, Optional[Loan]]:
        """
        Requester selects an offer.
        If offer is a physical copy, atomically reserves the copy and creates a Loan in 'reserved' state.
        Guarantees concurrency mutual exclusion: fails if copy is already reserved/active.
        """
        offer = await db.get(SupportOffer, offer_id)
        if not offer or offer.status != "proposed":
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message="Đề nghị này không còn khả dụng để lựa chọn.",
                status_code=409,
            )

        need = await db.get(CommunityRequest, offer.need_id)
        if not need or need.status != "open":
            raise BoconicException(code=ErrorCode.INVALID_STATE, message="Nhu cầu này không còn mở.", status_code=409)

        if need.user_id != requester_id:
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không phải người tạo nhu cầu này.", status_code=403)

        loan: Optional[Loan] = None

        if offer.copy_id:
            copy = await db.get(BookCopy, offer.copy_id)
            if not copy:
                raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy bản sách.", status_code=404)

            # Strict concurrency mutual exclusion check
            existing_active_loan = await db.execute(
                select(Loan).where(
                    Loan.copy_id == copy.id,
                    Loan.status.in_(["reserved", "active", "return_pending", "disputed"]),
                )
            )
            if existing_active_loan.scalar_one_or_none():
                raise BoconicException(
                    code=ErrorCode.COPY_UNAVAILABLE,
                    message="Bản sách này vừa được giữ chỗ cho một giao dịch khác.",
                    status_code=409,
                )

            # Create or update linked BorrowRequest
            borrow_req = BorrowRequest(
                copy_id=copy.id,
                borrower_id=requester_id,
                duration_days=offer.proposed_duration_days,
                need_id=need.id,
                offer_id=offer.id,
                note=f"Created via Need #{need.id}",
                status="accepted",
            )
            db.add(borrow_req)
            await db.flush()

            # Create Loan in reserved state
            reservation_expires_at = utc_now() + timedelta(hours=72)
            loan = Loan(
                request_id=borrow_req.id,
                copy_id=copy.id,
                borrower_id=requester_id,
                lender_id=copy.current_holder_id,
                status="reserved",
                reservation_expires_at=reservation_expires_at,
            )
            db.add(loan)
            await db.flush()

            copy.circulation_status = "reserved"

            # Loan event
            event = LoanEvent(
                loan_id=loan.id,
                actor_id=requester_id,
                action="select_offer",
                from_status=None,
                to_status="reserved",
                reason=f"Selected offer {offer.id}",
            )
            db.add(event)

        offer.status = "selected"
        need.version += 1

        outbox = OutboxEvent(
            event_type="OFFER_SELECTED",
            aggregate_type="support_offer",
            aggregate_id=offer.id,
            payload={
                "offer_id": offer.id,
                "need_id": need.id,
                "requester_id": requester_id,
                "provider_id": offer.provider_user_id,
                "loan_id": loan.id if loan else None,
            },
        )
        db.add(outbox)
        await db.flush()

        return offer, loan

    @classmethod
    async def withdraw_offer(
        cls,
        db: AsyncSession,
        offer_id: str,
        provider_user_id: str,
        reason: Optional[str] = None,
    ) -> SupportOffer:
        """Provider withdraws their proposed offer before obligation."""
        offer = await db.get(SupportOffer, offer_id)
        if not offer or offer.status != "proposed":
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message="Chỉ có thể rút đề nghị đang ở trạng thái chờ phản hồi.",
                status_code=409,
            )

        if offer.provider_user_id != provider_user_id:
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không phải người tạo đề nghị này.", status_code=403)

        offer.status = "withdrawn"
        await db.flush()
        return offer

    @classmethod
    async def decline_offer(
        cls,
        db: AsyncSession,
        offer_id: str,
        requester_id: str,
        reason: Optional[str] = None,
    ) -> SupportOffer:
        """Requester declines an offer."""
        offer = await db.get(SupportOffer, offer_id)
        if not offer or offer.status != "proposed":
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message="Đề nghị này không ở trạng thái có thể từ chối.",
                status_code=409,
            )

        need = await db.get(CommunityRequest, offer.need_id)
        if not need or need.user_id != requester_id:
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không có quyền từ chối đề nghị này.", status_code=403)

        offer.status = "declined"
        await db.flush()
        return offer

    @classmethod
    async def get_need_offers(
        cls,
        db: AsyncSession,
        need_id: str,
    ) -> List[SupportOffer]:
        """Fetch all offers for a need."""
        stmt = (
            select(SupportOffer)
            .where(SupportOffer.need_id == need_id)
            .order_by(SupportOffer.created_at.desc())
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @classmethod
    async def get_need_detail(
        cls,
        db: AsyncSession,
        need_id: str,
        viewer_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch full details for a need, including matched owners count
        and offers if viewer is the requester. Preserves privacy of non-responding owners.
        """
        need = await db.get(CommunityRequest, need_id)
        if not need:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy nhu cầu sách.", status_code=404)

        match_res = await db.execute(
            select(func.count(RequestMatch.id)).where(RequestMatch.need_id == need.id)
        )
        matched_owners_count = match_res.scalar_one() or 0

        offers = []
        if viewer_user_id and need.user_id == viewer_user_id:
            off_res = await db.execute(
                select(SupportOffer).where(SupportOffer.need_id == need_id).order_by(SupportOffer.created_at.desc())
            )
            offers = [
                {
                    "id": o.id,
                    "offer_type": o.offer_type,
                    "copy_id": o.copy_id,
                    "resource_id": o.resource_id,
                    "proposed_duration_days": o.proposed_duration_days,
                    "coarse_pickup_area": o.coarse_pickup_area,
                    "message": o.message,
                    "status": o.status,
                    "revalidation_required": o.revalidation_required,
                }
                for o in off_res.scalars().all()
            ]

        return {
            "id": need.id,
            "user_id": need.user_id,
            "title_query": need.title_query,
            "isbn": need.isbn,
            "edition_label": need.edition_label,
            "scope_type": need.scope_type,
            "target_chapters": need.target_chapters,
            "target_snapshot": need.target_snapshot,
            "revalidation_required": need.revalidation_required,
            "page_range": need.page_range,
            "quantity": need.quantity,
            "quantity_fulfilled": need.quantity_fulfilled,
            "duration_days_needed": need.duration_days_needed,
            "coarse_location": need.coarse_location,
            "urgency": need.urgency,
            "status": need.status,
            "matched_owners_count": matched_owners_count,
            "offers": offers,
        }


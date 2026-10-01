from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import BoconicException, ErrorCode
from app.db.models.catalog import BookCopy
from app.db.models.community import TrustEvent, UserBlock
from app.db.models.jobs import OutboxEvent
from app.db.models.lending import (
    BorrowRequest, CustodyEvent, HandoverConfirmation, Loan, LoanEvent
)

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class LendingService:
    @classmethod
    async def create_borrow_request(
        cls,
        db: AsyncSession,
        copy_id: str,
        borrower_id: str,
        duration_days: int = 14,
        note: Optional[str] = None,
    ) -> BorrowRequest:
        copy = await db.get(BookCopy, copy_id)
        if not copy:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy bản sách.", status_code=404)

        if copy.circulation_status != "available":
            raise BoconicException(
                code=ErrorCode.COPY_UNAVAILABLE,
                message="Bản sách này hiện không ở trạng thái sẵn sàng cho mượn.",
                status_code=409,
            )

        if copy.owner_id == borrower_id:
            raise BoconicException(
                code=ErrorCode.FORBIDDEN,
                message="Bạn không thể mượn bản sách do chính mình sở hữu.",
                status_code=403,
            )

        # Check user block
        block_check = await db.execute(
            select(UserBlock).where(
                UserBlock.blocker_id == copy.owner_id,
                UserBlock.blocked_id == borrower_id,
            )
        )
        if block_check.scalar_one_or_none():
            raise BoconicException(
                code=ErrorCode.FORBIDDEN,
                message="Yêu cầu không thể hoàn tất do chính sách hạn chế kết nối.",
                status_code=403,
            )

        # Check existing pending request
        pending_check = await db.execute(
            select(BorrowRequest).where(
                BorrowRequest.copy_id == copy_id,
                BorrowRequest.borrower_id == borrower_id,
                BorrowRequest.status == "pending",
            )
        )
        if pending_check.scalar_one_or_none():
            raise BoconicException(
                code=ErrorCode.ALREADY_EXISTS,
                message="Bạn đã có một yêu cầu đang chờ phản hồi cho bản sách này.",
                status_code=409,
            )

        request = BorrowRequest(
            copy_id=copy_id,
            borrower_id=borrower_id,
            duration_days=min(duration_days, copy.maximum_loan_days),
            note=note,
            status="pending",
        )
        db.add(request)
        await db.flush()

        # Outbox event
        outbox = OutboxEvent(
            event_type="REQUEST_CREATED",
            aggregate_type="borrow_request",
            aggregate_id=request.id,
            payload={
                "copy_id": copy_id,
                "borrower_id": borrower_id,
                "owner_id": copy.owner_id,
                "duration_days": request.duration_days,
            },
        )
        db.add(outbox)
        await db.flush()

        return request

    @classmethod
    async def accept_borrow_request(
        cls,
        db: AsyncSession,
        request_id: str,
        owner_id: str,
    ) -> Loan:
        # Load request and copy
        req = await db.get(BorrowRequest, request_id)
        if not req or req.status != "pending":
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message="Yêu cầu mượn không tồn tại hoặc đã được xử lý.",
                status_code=409,
            )

        copy = await db.get(BookCopy, req.copy_id)
        if not copy:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy bản sách.", status_code=404)

        if copy.owner_id != owner_id and copy.current_holder_id != owner_id:
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không có quyền quản lý bản sách này.", status_code=403)

        # Verify no active or reserved loan exists for this copy (Concurrency mutual exclusion)
        existing_loan = await db.execute(
            select(Loan).where(
                Loan.copy_id == copy.id,
                Loan.status.in_(["reserved", "active", "return_pending", "disputed"]),
            )
        )
        if existing_loan.scalar_one_or_none():
            raise BoconicException(
                code=ErrorCode.COPY_UNAVAILABLE,
                message="Bản sách này vừa được giữ chỗ cho một giao dịch khác.",
                status_code=409,
            )

        # Update request
        req.status = "accepted"

        # Update other pending requests for the same copy to waitlisted/expired
        other_reqs = await db.execute(
            select(BorrowRequest).where(
                BorrowRequest.copy_id == copy.id,
                BorrowRequest.id != req.id,
                BorrowRequest.status == "pending",
            )
        )
        for other in other_reqs.scalars().all():
            other.status = "expired"

        # Create Loan in reserved state
        reservation_expires_at = utc_now() + timedelta(hours=72)
        loan = Loan(
            request_id=req.id,
            copy_id=copy.id,
            borrower_id=req.borrower_id,
            lender_id=copy.current_holder_id,
            status="reserved",
            reservation_expires_at=reservation_expires_at,
        )
        db.add(loan)
        await db.flush()

        # Update copy status
        copy.circulation_status = "reserved"

        # Log event
        loan_event = LoanEvent(
            loan_id=loan.id,
            actor_id=owner_id,
            action="accept_request",
            from_status=None,
            to_status="reserved",
            reason="Owner accepted borrow request",
        )
        db.add(loan_event)

        # Outbox event
        outbox = OutboxEvent(
            event_type="REQUEST_ACCEPTED",
            aggregate_type="loan",
            aggregate_id=loan.id,
            payload={
                "loan_id": loan.id,
                "borrower_id": loan.borrower_id,
                "lender_id": loan.lender_id,
                "reservation_expires_at": reservation_expires_at.isoformat(),
            },
        )
        db.add(outbox)

        await db.flush()
        return loan

    @classmethod
    async def reject_borrow_request(
        cls,
        db: AsyncSession,
        request_id: str,
        owner_id: str,
        reason: Optional[str] = None,
    ) -> BorrowRequest:
        req = await db.get(BorrowRequest, request_id)
        if not req or req.status != "pending":
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message="Yêu cầu mượn không tồn tại hoặc đã được xử lý.",
                status_code=409,
            )

        copy = await db.get(BookCopy, req.copy_id)
        if not copy:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy bản sách.", status_code=404)

        if copy.owner_id != owner_id and copy.current_holder_id != owner_id:
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không có quyền quản lý bản sách này.", status_code=403)

        req.status = "rejected"

        outbox = OutboxEvent(
            event_type="REQUEST_REJECTED",
            aggregate_type="borrow_request",
            aggregate_id=req.id,
            payload={
                "request_id": req.id,
                "borrower_id": req.borrower_id,
                "owner_id": owner_id,
                "reason": reason,
            },
        )
        db.add(outbox)
        await db.flush()
        return req

    @classmethod
    async def confirm_handover(
        cls,
        db: AsyncSession,
        loan_id: str,
        actor_id: str,
    ) -> Tuple[Loan, bool]:
        """
        Record handover confirmation. Returns (loan, is_active).
        Both lender and borrower must confirm for state to transition to active.
        """
        loan = await db.get(Loan, loan_id)
        if not loan:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy thông tin lượt mượn.", status_code=404)

        if loan.status != "reserved":
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message=f"Giao dịch đang ở trạng thái '{loan.status}', không thể xác nhận giao nhận.",
                status_code=409,
            )

        if actor_id == loan.lender_id:
            role = "lender"
        elif actor_id == loan.borrower_id:
            role = "borrower"
        else:
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không thuộc danh sách các bên của giao dịch này.", status_code=403)

        # Check if already confirmed by this actor
        existing_conf = await db.execute(
            select(HandoverConfirmation).where(
                HandoverConfirmation.loan_id == loan.id,
                HandoverConfirmation.role == role,
                HandoverConfirmation.action == "handover",
            )
        )
        if not existing_conf.scalar_one_or_none():
            conf = HandoverConfirmation(
                loan_id=loan.id,
                actor_id=actor_id,
                role=role,
                action="handover",
                confirmed_at=utc_now(),
            )
            db.add(conf)
            await db.flush()

        # Check total handover confirmations for this loan
        all_confs = await db.execute(
            select(HandoverConfirmation).where(
                HandoverConfirmation.loan_id == loan.id,
                HandoverConfirmation.action == "handover",
            )
        )
        conf_roles = {c.role for c in all_confs.scalars().all()}

        is_active = False
        if "lender" in conf_roles and "borrower" in conf_roles:
            # Dual handshake complete! Transition to active
            copy = await db.get(BookCopy, loan.copy_id)
            req = await db.get(BorrowRequest, loan.request_id) if loan.request_id else None
            duration_days = req.duration_days if req else 14

            now = utc_now()
            loan.status = "active"
            loan.handed_over_at = now
            loan.due_at = now + timedelta(days=duration_days)
            is_active = True

            if copy:
                copy.circulation_status = "loaned"
                copy.current_holder_id = loan.borrower_id

            # Custody event
            custody = CustodyEvent(
                copy_id=loan.copy_id,
                loan_id=loan.id,
                from_holder_id=loan.lender_id,
                to_holder_id=loan.borrower_id,
                reason="handover",
            )
            db.add(custody)

            # Loan event
            event = LoanEvent(
                loan_id=loan.id,
                actor_id=actor_id,
                action="confirm_handover_complete",
                from_status="reserved",
                to_status="active",
                reason="Both lender and borrower confirmed handover",
            )
            db.add(event)

            # Outbox
            outbox = OutboxEvent(
                event_type="HANDOVER_CONFIRMED",
                aggregate_type="loan",
                aggregate_id=loan.id,
                payload={
                    "loan_id": loan.id,
                    "borrower_id": loan.borrower_id,
                    "due_at": loan.due_at.isoformat() if loan.due_at else None,
                },
            )
            db.add(outbox)

            # If linked to a BorrowRequest with need_id or offer_id, update fulfillment
            if loan.request_id:
                borrow_req = await db.get(BorrowRequest, loan.request_id)
                if borrow_req:
                    if borrow_req.offer_id:
                        from app.db.models.community import SupportOffer
                        offer = await db.get(SupportOffer, borrow_req.offer_id)
                        if offer:
                            offer.status = "fulfilled"
                    if borrow_req.need_id:
                        from app.db.models.community import CommunityRequest
                        need = await db.get(CommunityRequest, borrow_req.need_id)
                        if need:
                            need.quantity_fulfilled = (need.quantity_fulfilled or 0) + 1
                            if need.quantity_fulfilled >= need.quantity:
                                need.status = "fulfilled"
                            need.version += 1

        await db.flush()
        return loan, is_active

    @classmethod
    async def request_return(
        cls,
        db: AsyncSession,
        loan_id: str,
        actor_id: str,
        note: Optional[str] = None,
    ) -> Loan:
        loan = await db.get(Loan, loan_id)
        if not loan or loan.status != "active":
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message="Giao dịch không ở trạng thái đang mượn để yêu cầu trả.",
                status_code=409,
            )

        if actor_id not in (loan.borrower_id, loan.lender_id):
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không có quyền trong giao dịch này.", status_code=403)

        loan.status = "return_pending"

        event = LoanEvent(
            loan_id=loan.id,
            actor_id=actor_id,
            action="request_return",
            from_status="active",
            to_status="return_pending",
            reason=note or "Party requested return confirmation",
        )
        db.add(event)

        outbox = OutboxEvent(
            event_type="RETURN_REQUESTED",
            aggregate_type="loan",
            aggregate_id=loan.id,
            payload={"loan_id": loan.id, "requested_by": actor_id},
        )
        db.add(outbox)

        await db.flush()
        return loan

    @classmethod
    async def confirm_return(
        cls,
        db: AsyncSession,
        loan_id: str,
        actor_id: str,
    ) -> Tuple[Loan, bool]:
        """
        Record return confirmation. Returns (loan, is_returned).
        Both lender and borrower must confirm for state to transition to returned.
        """
        loan = await db.get(Loan, loan_id)
        if not loan:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy lượt mượn.", status_code=404)

        if loan.status != "return_pending":
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message=f"Giao dịch đang ở trạng thái '{loan.status}', phải ở 'return_pending' để xác nhận trả.",
                status_code=409,
            )

        if actor_id == loan.lender_id:
            role = "lender"
        elif actor_id == loan.borrower_id:
            role = "borrower"
        else:
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không thuộc giao dịch này.", status_code=403)

        # Check existing return confirmation
        existing_conf = await db.execute(
            select(HandoverConfirmation).where(
                HandoverConfirmation.loan_id == loan.id,
                HandoverConfirmation.role == role,
                HandoverConfirmation.action == "return",
            )
        )
        if not existing_conf.scalar_one_or_none():
            conf = HandoverConfirmation(
                loan_id=loan.id,
                actor_id=actor_id,
                role=role,
                action="return",
                confirmed_at=utc_now(),
            )
            db.add(conf)
            await db.flush()

        all_confs = await db.execute(
            select(HandoverConfirmation).where(
                HandoverConfirmation.loan_id == loan.id,
                HandoverConfirmation.action == "return",
            )
        )
        conf_roles = {c.role for c in all_confs.scalars().all()}

        is_returned = False
        if "lender" in conf_roles and "borrower" in conf_roles:
            now = utc_now()
            loan.status = "returned"
            loan.returned_at = now
            is_returned = True

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
                reason="return",
            )
            db.add(custody)

            # Trust event: determine on-time vs late
            due = loan.due_at
            if due is not None and due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            is_on_time = due is None or now <= due
            trust_event = TrustEvent(
                user_id=loan.borrower_id,
                loan_id=loan.id,
                event_type="on_time_return" if is_on_time else "late_return",
                score_delta=1.0 if is_on_time else -0.5,
                reason="Trả sách đúng hạn" if is_on_time else "Trả sách quá hạn quy định",
            )
            db.add(trust_event)

            # Loan event
            event = LoanEvent(
                loan_id=loan.id,
                actor_id=actor_id,
                action="confirm_return_complete",
                from_status="return_pending",
                to_status="returned",
                reason="Both parties confirmed physical return",
            )
            db.add(event)

            # Outbox
            outbox = OutboxEvent(
                event_type="LOAN_RETURNED",
                aggregate_type="loan",
                aggregate_id=loan.id,
                payload={
                    "loan_id": loan.id,
                    "copy_id": loan.copy_id,
                    "borrower_id": loan.borrower_id,
                    "is_on_time": is_on_time,
                },
            )
            db.add(outbox)

        await db.flush()
        return loan, is_returned

    @classmethod
    async def raise_dispute(
        cls,
        db: AsyncSession,
        loan_id: str,
        actor_id: str,
        reason: str,
    ) -> Loan:
        loan = await db.get(Loan, loan_id)
        if not loan or loan.status not in ("active", "return_pending"):
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message="Chỉ có thể mở tranh chấp khi giao dịch đang mượn hoặc chờ xác nhận trả.",
                status_code=409,
            )

        if actor_id not in (loan.borrower_id, loan.lender_id):
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không thuộc giao dịch này.", status_code=403)

        old_status = loan.status
        loan.status = "disputed"

        event = LoanEvent(
            loan_id=loan.id,
            actor_id=actor_id,
            action="raise_dispute",
            from_status=old_status,
            to_status="disputed",
            reason=reason,
        )
        db.add(event)

        outbox = OutboxEvent(
            event_type="LOAN_DISPUTED",
            aggregate_type="loan",
            aggregate_id=loan.id,
            payload={"loan_id": loan.id, "raised_by": actor_id, "reason": reason},
        )
        db.add(outbox)

        await db.flush()
        return loan

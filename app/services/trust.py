from typing import Any, Dict, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BoconicException, ErrorCode
from app.db.models.community import Review, TrustEvent
from app.db.models.lending import Loan

class TrustService:
    @classmethod
    async def get_user_trust_profile(cls, db: AsyncSession, user_id: str) -> Dict[str, Any]:
        """Compute transparent algorithmic trust metrics for a user."""
        # Query trust events
        events_res = await db.execute(
            select(TrustEvent.event_type, func.count(TrustEvent.id))
            .where(TrustEvent.user_id == user_id)
            .group_by(TrustEvent.event_type)
        )
        counts = dict(events_res.all())

        on_time = counts.get("on_time_return", 0)
        late = counts.get("late_return", 0)
        disputes = counts.get("dispute_incident", 0)
        total_returns = on_time + late

        if total_returns == 0:
            history_label = "Chưa đủ lịch sử"
            reliability_score = None
        else:
            # Bayesian smoothed reliability (Laplace prior)
            reliability_score = round(((on_time + 3) / (total_returns + 4)) * 100, 1)
            history_label = f"{on_time}/{total_returns} lượt trả đúng hẹn"
            if late > 0:
                history_label += f" ({late} lượt trễ)"

        return {
            "user_id": user_id,
            "total_returns": total_returns,
            "on_time_returns": on_time,
            "late_returns": late,
            "disputes": disputes,
            "reliability_score": reliability_score,
            "history_label": history_label,
            "is_established": total_returns >= 3,
        }

    @classmethod
    async def create_review(
        cls,
        db: AsyncSession,
        loan_id: str,
        author_id: str,
        rating: int,
        comment: Optional[str] = None,
    ) -> Review:
        loan = await db.get(Loan, loan_id)
        if not loan or loan.status != "returned":
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message="Chỉ có thể đánh giá sau khi giao dịch đã hoàn tất và sách đã được trả.",
                status_code=409,
            )

        if author_id not in (loan.borrower_id, loan.lender_id):
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không thuộc giao dịch này.", status_code=403)

        target_user_id = loan.lender_id if author_id == loan.borrower_id else loan.borrower_id

        # Check existing review by this author for this loan
        existing = await db.execute(
            select(Review).where(Review.loan_id == loan_id, Review.author_id == author_id)
        )
        if existing.scalar_one_or_none():
            raise BoconicException(
                code=ErrorCode.ALREADY_EXISTS,
                message="Bạn đã gửi đánh giá cho lượt mượn này rồi.",
                status_code=409,
            )

        if rating < 1 or rating > 5:
            raise BoconicException(code=ErrorCode.VALIDATION_ERROR, message="Điểm đánh giá phải từ 1 đến 5 sao.")

        review = Review(
            loan_id=loan_id,
            author_id=author_id,
            target_user_id=target_user_id,
            rating=rating,
            comment=comment.strip() if comment else None,
        )
        db.add(review)
        await db.flush()
        return review

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.errors import BoconicException, ErrorCode
from app.core.security import generate_public_alias
from app.db.models.catalog import Book, BookCopy
from app.db.models.community import CommunityRequest, Report, Resource
from app.db.models.identity import AdminAccount, User
from app.db.models.lending import BorrowRequest, Loan
from app.db.models.organization import Organization
from app.db.session import get_db
from app.services.catalog import CatalogService
from app.services.community import CommunityService
from app.services.coverage_service import CoverageService
from app.services.lending import LendingService
from app.services.library_service import LibraryService
from app.services.moderation import ModerationService
from app.services.need_service import NeedService
from app.services.warning_service import WarningService

router = APIRouter(prefix="/internal/telegram", tags=["Internal Bot Gateway"])

async def verify_bot_actor(
    x_bot_api_key: str = Header(..., alias="X-Bot-Api-Key"),
    x_telegram_user_id: int = Header(..., alias="X-Telegram-User-Id"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate bot service key and resolve the verified delegated Telegram user."""
    if x_bot_api_key != settings.BOT_API_KEY:
        raise BoconicException(
            code=ErrorCode.UNAUTHORIZED,
            message="Khóa truy cập Bot API không hợp lệ.",
            status_code=401,
        )

    res = await db.execute(select(User).where(User.telegram_user_id == x_telegram_user_id))
    user = res.scalar_one_or_none()
    if not user:
        # Auto-provision user on first verified Telegram message
        user = User(
            telegram_user_id=x_telegram_user_id,
            display_name=f"Telegram User {x_telegram_user_id}",
            public_alias=generate_public_alias(),
            language_code="vi",
            status="active",
        )
        db.add(user)
        await db.commit()

    if user.status in ("banned", "deleted"):
        raise BoconicException(
            code=ErrorCode.FORBIDDEN,
            message="Tài khoản này đã bị khóa hoặc ngừng hoạt động.",
            status_code=403,
        )

    return user

class SyncUserDTO(BaseModel):
    display_name: Optional[str] = None
    telegram_username: Optional[str] = None
    language_code: Optional[str] = "vi"

class AddCopyDTO(BaseModel):
    book_id: str
    condition: str = "good"
    maximum_loan_days: int = 14
    notes: Optional[str] = None

class CreateRequestDTO(BaseModel):
    copy_id: str
    duration_days: int = 14
    note: Optional[str] = None

class ReturnRequestDTO(BaseModel):
    note: Optional[str] = None

class RejectRequestDTO(BaseModel):
    reason: Optional[str] = None

class ReportCreateDTO(BaseModel):
    category: str = "other"
    description: str
    target_entity_type: str = "other"
    target_entity_id: str = "general"

class CommunityNeedDTO(BaseModel):
    title_query: str
    grade_level: Optional[int] = None
    subject: Optional[str] = None
    curriculum: Optional[str] = None
    quantity: int = 1
    fulfillment_preference: str = "lend"

@router.post("/users/sync")
async def sync_user_profile(
    dto: SyncUserDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    if dto.display_name:
        actor.display_name = dto.display_name.strip()
    if dto.telegram_username:
        actor.telegram_username = dto.telegram_username.strip()
    if dto.language_code:
        actor.language_code = dto.language_code
    await db.commit()
    return {
        "id": actor.id,
        "telegram_user_id": actor.telegram_user_id,
        "display_name": actor.display_name,
        "public_alias": actor.public_alias,
        "status": actor.status,
    }

@router.get("/books/search")
async def bot_search_books(
    q: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    grade: Optional[int] = Query(None),
    curriculum: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=20),
    offset: int = Query(0, ge=0),
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    books, total = await CatalogService.search_books(
        db, query=q, subject=subject, grade_level=grade, curriculum=curriculum,
        limit=limit, offset=offset
    )

    results = []
    for b in books:
        authors = [a.author.name for a in b.authors]
        available_copies = [
            {
                "copy_id": c.id,
                "public_code": c.public_code,
                "condition": c.condition,
                "max_days": c.maximum_loan_days,
                "is_mine": c.owner_id == actor.id,
                "is_partial": c.is_partial,
            }
            for c in b.copies
            if c.circulation_status == "available"
        ]
        results.append({
            "book_id": b.id,
            "title": b.title,
            "authors": authors,
            "publisher": b.publisher,
            "grade_level": b.grade_level,
            "subject": b.subject,
            "curriculum": b.curriculum,
            "isbn13": b.isbn13,
            "available_count": len(available_copies),
            "copies": available_copies,
        })

    return {"items": results, "total": total}

@router.post("/copies")
async def bot_add_copy(
    dto: AddCopyDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    copy = await CatalogService.add_book_copy(
        db=db,
        book_id=dto.book_id,
        owner_id=actor.id,
        condition=dto.condition,
        maximum_loan_days=dto.maximum_loan_days,
        notes=dto.notes,
    )
    await db.commit()
    return {
        "id": copy.id,
        "public_code": copy.public_code,
        "condition": copy.condition,
        "status": copy.circulation_status,
        "message": f"Bản sách '{copy.public_code}' đã được đăng thành công!",
    }

@router.post("/borrow-requests")
async def bot_create_borrow_request(
    dto: CreateRequestDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    req = await LendingService.create_borrow_request(
        db=db,
        copy_id=dto.copy_id,
        borrower_id=actor.id,
        duration_days=dto.duration_days,
        note=dto.note,
    )
    copy = await db.get(BookCopy, req.copy_id)
    book = await db.get(Book, copy.book_id) if copy else None
    owner = await db.get(User, copy.owner_id) if copy else None
    await db.commit()
    return {
        "request_id": req.id,
        "status": req.status,
        "duration_days": req.duration_days,
        "book_title": book.title if book else "Sách",
        "copy_code": copy.public_code if copy else "",
        "owner_telegram_id": owner.telegram_user_id if owner else None,
        "owner_alias": owner.public_alias if owner else "Chủ sách",
        "requester_alias": actor.public_alias,
        "message": "Yêu cầu mượn sách đã được gửi tới chủ sở hữu!",
    }

@router.post("/borrow-requests/{request_id}/accept")
async def bot_accept_borrow_request(
    request_id: str,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    loan = await LendingService.accept_borrow_request(db, request_id, actor.id)
    copy = await db.get(BookCopy, loan.copy_id)
    book = await db.get(Book, copy.book_id) if copy else None
    borrower = await db.get(User, loan.borrower_id)
    await db.commit()
    return {
        "loan_id": loan.id,
        "status": loan.status,
        "book_title": book.title if book else "Sách",
        "copy_code": copy.public_code if copy else "",
        "borrower_telegram_id": borrower.telegram_user_id if borrower else None,
        "borrower_alias": borrower.public_alias if borrower else "Người mượn",
        "reservation_expires_at": loan.reservation_expires_at,
        "message": "Bạn đã chấp nhận yêu cầu và giữ chỗ sách cho người mượn.",
    }

@router.post("/borrow-requests/{request_id}/reject")
async def bot_reject_borrow_request(
    request_id: str,
    dto: Optional[RejectRequestDTO] = None,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    reason = dto.reason if dto else None
    req = await LendingService.reject_borrow_request(db, request_id, actor.id, reason)
    copy = await db.get(BookCopy, req.copy_id)
    book = await db.get(Book, copy.book_id) if copy else None
    borrower = await db.get(User, req.borrower_id)
    await db.commit()
    return {
        "request_id": req.id,
        "status": req.status,
        "book_title": book.title if book else "Sách",
        "copy_code": copy.public_code if copy else "",
        "borrower_telegram_id": borrower.telegram_user_id if borrower else None,
        "message": "Bạn đã từ chối yêu cầu mượn sách này.",
    }

@router.post("/loans/{loan_id}/confirm-handover")
async def bot_confirm_handover(
    loan_id: str,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    loan, is_active = await LendingService.confirm_handover(db, loan_id, actor.id)
    copy = await db.get(BookCopy, loan.copy_id)
    book = await db.get(Book, copy.book_id) if copy else None
    other_user_id = loan.borrower_id if actor.id == loan.lender_id else loan.lender_id
    other_user = await db.get(User, other_user_id)
    await db.commit()
    return {
        "loan_id": loan.id,
        "status": loan.status,
        "is_active": is_active,
        "due_at": loan.due_at,
        "book_title": book.title if book else "Sách",
        "other_telegram_id": other_user.telegram_user_id if other_user else None,
        "message": "Sách đã chính thức bắt đầu lượt mượn!" if is_active else "Đã ghi nhận xác nhận giao nhận từ bạn. Đang chờ đối phương xác nhận.",
    }

@router.post("/loans/{loan_id}/request-return")
async def bot_request_return(
    loan_id: str,
    dto: ReturnRequestDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    loan = await LendingService.request_return(db, loan_id, actor.id, dto.note)
    copy = await db.get(BookCopy, loan.copy_id)
    book = await db.get(Book, copy.book_id) if copy else None
    other_user_id = loan.borrower_id if actor.id == loan.lender_id else loan.lender_id
    other_user = await db.get(User, other_user_id)
    await db.commit()
    return {
        "loan_id": loan.id,
        "status": loan.status,
        "book_title": book.title if book else "Sách",
        "other_telegram_id": other_user.telegram_user_id if other_user else None,
        "message": "Đã gửi đề nghị xác nhận trả sách tới đối phương.",
    }

@router.post("/loans/{loan_id}/confirm-return")
async def bot_confirm_return(
    loan_id: str,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    loan, is_returned = await LendingService.confirm_return(db, loan_id, actor.id)
    copy = await db.get(BookCopy, loan.copy_id)
    book = await db.get(Book, copy.book_id) if copy else None
    other_user_id = loan.borrower_id if actor.id == loan.lender_id else loan.lender_id
    other_user = await db.get(User, other_user_id)
    await db.commit()
    return {
        "loan_id": loan.id,
        "status": loan.status,
        "is_returned": is_returned,
        "book_title": book.title if book else "Sách",
        "other_telegram_id": other_user.telegram_user_id if other_user else None,
        "message": "Lượt mượn đã hoàn tất thành công! Bản sách đã được đưa lại kho khả dụng." if is_returned else "Đã ghi nhận xác nhận trả từ bạn. Đang chờ đối phương xác nhận.",
    }

@router.get("/my-books")
async def bot_my_books(
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(BookCopy)
        .where(BookCopy.owner_id == actor.id)
        .options(selectinload(BookCopy.book))
        .order_by(BookCopy.created_at.desc())
    )
    res = await db.execute(stmt)
    copies = res.scalars().all()
    return [
        {
            "copy_id": c.id,
            "public_code": c.public_code,
            "book_title": c.book.title if c.book else "Sách",
            "condition": c.condition,
            "status": c.circulation_status,
            "is_lent": c.circulation_status == "loaned",
        }
        for c in copies
    ]

@router.get("/my-loans")
async def bot_my_loans(
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Loan)
        .where(
            Loan.borrower_id == actor.id,
            Loan.status.in_(["reserved", "active", "return_pending"]),
        )
        .options(
            selectinload(Loan.copy).selectinload(BookCopy.book),
            selectinload(Loan.lender),
        )
        .order_by(Loan.created_at.desc())
    )
    res = await db.execute(stmt)
    loans = res.scalars().all()
    return [
        {
            "loan_id": l.id,
            "status": l.status,
            "book_title": l.copy.book.title if l.copy and l.copy.book else "Sách",
            "public_code": l.copy.public_code if l.copy else "",
            "lender_alias": l.lender.public_alias if l.lender else "Chủ sách",
            "due_at": l.due_at,
            "handed_over_at": l.handed_over_at,
        }
        for l in loans
    ]

@router.get("/my-lendings")
async def bot_my_lendings(
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Loan)
        .where(
            Loan.lender_id == actor.id,
            Loan.status.in_(["reserved", "active", "return_pending"]),
        )
        .options(
            selectinload(Loan.copy).selectinload(BookCopy.book),
            selectinload(Loan.borrower),
        )
        .order_by(Loan.created_at.desc())
    )
    res = await db.execute(stmt)
    loans = res.scalars().all()
    return [
        {
            "loan_id": l.id,
            "status": l.status,
            "book_title": l.copy.book.title if l.copy and l.copy.book else "Sách",
            "public_code": l.copy.public_code if l.copy else "",
            "borrower_alias": l.borrower.public_alias if l.borrower else "Người mượn",
            "due_at": l.due_at,
            "handed_over_at": l.handed_over_at,
        }
        for l in loans
    ]

@router.get("/requests")
async def bot_get_requests(
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt_inc = (
        select(BorrowRequest)
        .join(BookCopy, BorrowRequest.copy_id == BookCopy.id)
        .where(
            BookCopy.owner_id == actor.id,
            BorrowRequest.status == "pending",
        )
        .options(
            selectinload(BorrowRequest.copy).selectinload(BookCopy.book),
            selectinload(BorrowRequest.borrower),
        )
        .order_by(BorrowRequest.created_at.desc())
    )
    res_inc = await db.execute(stmt_inc)
    incoming = res_inc.scalars().all()

    stmt_out = (
        select(BorrowRequest)
        .where(BorrowRequest.borrower_id == actor.id)
        .options(
            selectinload(BorrowRequest.copy).selectinload(BookCopy.book),
            selectinload(BorrowRequest.copy).selectinload(BookCopy.owner),
        )
        .order_by(BorrowRequest.created_at.desc())
        .limit(10)
    )
    res_out = await db.execute(stmt_out)
    outgoing = res_out.scalars().all()

    return {
        "incoming": [
            {
                "request_id": r.id,
                "copy_id": r.copy_id,
                "copy_code": r.copy.public_code if r.copy else "",
                "book_title": r.copy.book.title if r.copy and r.copy.book else "Sách",
                "borrower_alias": r.borrower.public_alias if r.borrower else "Người mượn",
                "duration_days": r.duration_days,
                "note": r.note,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in incoming
        ],
        "outgoing": [
            {
                "request_id": r.id,
                "copy_id": r.copy_id,
                "copy_code": r.copy.public_code if r.copy else "",
                "book_title": r.copy.book.title if r.copy and r.copy.book else "Sách",
                "owner_alias": r.copy.owner.public_alias if r.copy and r.copy.owner else "Chủ sách",
                "duration_days": r.duration_days,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in outgoing
        ],
    }

@router.post("/community-needs")
async def bot_create_community_need(
    dto: CommunityNeedDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    need = await CommunityService.create_community_request(
        db=db,
        user_id=actor.id,
        title_query=dto.title_query,
        grade_level=dto.grade_level,
        subject=dto.subject,
        curriculum=dto.curriculum,
        quantity=dto.quantity,
        fulfillment_preference=dto.fulfillment_preference,
    )
    await db.commit()
    return {
        "need_id": need.id,
        "title": need.title_query,
        "message": f"Nhu cầu mượn/tìm sách '{need.title_query}' của bạn đã được ghi nhận vào hệ thống cộng đồng.",
    }

@router.get("/libraries")
async def bot_get_libraries(
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Organization)
        .where(Organization.verification_status == "verified")
        .order_by(Organization.name.asc())
        .limit(10)
    )
    res = await db.execute(stmt)
    orgs = res.scalars().all()
    return [
        {
            "id": o.id,
            "name": o.name,
            "kind": o.kind,
            "city": o.city,
            "district": o.district,
            "public_address": o.public_address,
            "public_phone": o.public_phone,
            "opening_hours": o.opening_hours,
            "inventory_policy": o.inventory_policy,
        }
        for o in orgs
    ]

@router.get("/resources")
async def bot_get_resources(
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    res_list = await CommunityService.get_verified_resources(db, required_action="link")
    return [
        {
            "id": r.id,
            "title": r.title,
            "resource_type": r.resource_type,
            "source_name": r.source_name,
            "source_url": r.source_url,
            "license_name": r.license_name,
            "rights_basis": r.rights_basis,
        }
        for r in res_list
    ]

@router.post("/reports")
async def bot_create_report(
    dto: ReportCreateDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    report = Report(
        reporter_id=actor.id,
        target_entity_type=dto.target_entity_type,
        target_entity_id=dto.target_entity_id,
        category=dto.category,
        description=dto.description.strip(),
        status="open",
    )
    db.add(report)
    await db.commit()
    return {
        "report_id": report.id,
        "message": "Báo cáo của bạn đã được chuyển tới Ban Quản Trị Boconic để xác minh.",
    }

@router.get("/admin/stats")
async def bot_admin_stats(
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    admin_id_match = (
        settings.ADMIN_TELEGRAM_ID
        and str(actor.telegram_user_id) == str(settings.ADMIN_TELEGRAM_ID)
    )
    if not admin_id_match:
        adm = await db.execute(select(AdminAccount).where(AdminAccount.telegram_user_id == actor.telegram_user_id))
        if not adm.scalar_one_or_none():
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Chỉ Quản trị viên mới có quyền xem thông tin này.", status_code=403)

    total_users = (await db.execute(select(func.count(User.id)))).scalar_one() or 0
    total_books = (await db.execute(select(func.count(Book.id)))).scalar_one() or 0
    total_copies = (await db.execute(select(func.count(BookCopy.id)))).scalar_one() or 0
    available_copies = (await db.execute(select(func.count(BookCopy.id)).where(BookCopy.circulation_status == "available"))).scalar_one() or 0
    loaned_copies = (await db.execute(select(func.count(BookCopy.id)).where(BookCopy.circulation_status == "loaned"))).scalar_one() or 0
    active_loans = (await db.execute(select(func.count(Loan.id)).where(Loan.status.in_(["reserved", "active", "return_pending"])))).scalar_one() or 0
    pending_requests = (await db.execute(select(func.count(BorrowRequest.id)).where(BorrowRequest.status == "pending"))).scalar_one() or 0
    community_needs = (await db.execute(select(func.count(CommunityRequest.id)).where(CommunityRequest.status == "open"))).scalar_one() or 0
    resources_count = (await db.execute(select(func.count(Resource.id)).where(Resource.verification_status == "verified"))).scalar_one() or 0

    return {
        "total_users": total_users,
        "total_books": total_books,
        "total_copies": total_copies,
        "available_copies": available_copies,
        "loaned_copies": loaned_copies,
        "active_loans": active_loans,
        "pending_requests": pending_requests,
        "community_needs": community_needs,
        "resources_count": resources_count,
    }


# ==========================================
# PERSONAL LIBRARY BOT ENDPOINTS
# ==========================================

class SetVisibilityDTO(BaseModel):
    visibility: str  # 'published' or 'private'


class UpdateReadingStatusDTO(BaseModel):
    book_id: str
    reading_status: str
    personal_notes: Optional[str] = None


@router.get("/library")
async def bot_get_library(
    tab: str = "all",
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve user's personal library items categorized by tab."""
    return await LibraryService.get_user_library(db=db, user_id=actor.id, tab=tab)


@router.post("/library/copies/{copy_id}/visibility")
async def bot_set_copy_visibility(
    copy_id: str,
    dto: SetVisibilityDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Set copy lending/discovery visibility."""
    copy = await LibraryService.set_copy_visibility(
        db=db,
        user_id=actor.id,
        copy_id=copy_id,
        visibility=dto.visibility,
    )
    await db.commit()
    return {"copy_id": copy.id, "visibility": copy.visibility}


@router.delete("/library/copies/{copy_id}")
async def bot_remove_copy(
    copy_id: str,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Remove a copy. Invariant: Cannot remove if in an active/reserved loan."""
    success = await LibraryService.remove_copy(db=db, user_id=actor.id, copy_id=copy_id)
    await db.commit()
    return {"success": success, "message": "Bản sách đã được xóa khỏi thư viện."}


@router.post("/library/reading-status")
async def bot_update_reading_status(
    dto: UpdateReadingStatusDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Update user reading status and notes."""
    entry = await LibraryService.update_reading_status(
        db=db,
        user_id=actor.id,
        book_id=dto.book_id,
        reading_status=dto.reading_status,
        personal_notes=dto.personal_notes,
    )
    await db.commit()
    return {"book_id": entry.book_id, "reading_status": entry.reading_status}


# ==========================================
# COMMUNITY NEEDS BOT ENDPOINTS
# ==========================================

class BotCreateNeedDTO(BaseModel):
    title_query: str
    book_id: Optional[str] = None
    isbn: Optional[str] = None
    edition_label: Optional[str] = None
    scope_type: str = "full_book"
    page_range: Optional[List[int]] = None
    pagination_basis: Optional[str] = None
    target_chapters: Optional[List[str]] = None
    quantity: int = 1
    duration_days_needed: int = 14
    coarse_location: Optional[str] = None
    urgency: str = "normal"
    urgency_reason: Optional[str] = None
    accepted_conditions: Optional[List[str]] = None
    edition_match_strict: bool = False
    description: Optional[str] = None
    visibility: str = "public"


@router.post("/needs")
async def bot_create_need(
    dto: BotCreateNeedDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Create a new book need (CommunityRequest)."""
    need = await NeedService.create_need(
        db=db,
        user_id=actor.id,
        title_query=dto.title_query,
        book_id=dto.book_id,
        isbn=dto.isbn,
        edition_label=dto.edition_label,
        scope_type=dto.scope_type,
        page_range=dto.page_range,
        pagination_basis=dto.pagination_basis,
        target_chapters=dto.target_chapters,
        quantity=dto.quantity,
        duration_days_needed=dto.duration_days_needed,
        coarse_location=dto.coarse_location,
        urgency=dto.urgency,
        urgency_reason=dto.urgency_reason,
        accepted_conditions=dto.accepted_conditions,
        edition_match_strict=dto.edition_match_strict,
        description=dto.description,
        visibility=dto.visibility,
        status="open",
    )
    await db.commit()
    return {
        "need_id": need.id,
        "title_query": need.title_query,
        "status": need.status,
        "scope_type": need.scope_type,
        "quantity": need.quantity,
    }


@router.get("/needs/my")
async def bot_get_my_needs(
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Fetch user's open and active needs with offer counts."""
    from app.db.models.community import SupportOffer
    stmt = (
        select(CommunityRequest)
        .where(CommunityRequest.user_id == actor.id)
        .order_by(CommunityRequest.created_at.desc())
    )
    res = await db.execute(stmt)
    needs = res.scalars().all()

    items = []
    for n in needs:
        offers_res = await db.execute(
            select(func.count(SupportOffer.id)).where(SupportOffer.need_id == n.id)
        )
        offer_count = offers_res.scalar_one() or 0

        items.append({
            "id": n.id,
            "title_query": n.title_query,
            "isbn": n.isbn,
            "scope_type": n.scope_type,
            "quantity": n.quantity,
            "quantity_fulfilled": n.quantity_fulfilled,
            "status": n.status,
            "urgency": n.urgency,
            "offer_count": offer_count,
            "created_at": n.created_at.isoformat(),
        })

    return items


@router.get("/needs/{need_id}")
async def bot_get_need_detail(
    need_id: str,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Get full details for a need including offers if actor is requester."""
    need = await db.get(CommunityRequest, need_id)
    if not need:
        raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy nhu cầu sách.", status_code=404)

    offers = []
    if need.user_id == actor.id:
        from app.db.models.community import SupportOffer
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
            }
            for o in off_res.scalars().all()
        ]

    return {
        "id": need.id,
        "title_query": need.title_query,
        "isbn": need.isbn,
        "edition_label": need.edition_label,
        "scope_type": need.scope_type,
        "page_range": need.page_range,
        "quantity": need.quantity,
        "quantity_fulfilled": need.quantity_fulfilled,
        "duration_days_needed": need.duration_days_needed,
        "coarse_location": need.coarse_location,
        "urgency": need.urgency,
        "status": need.status,
        "is_owner": (need.user_id == actor.id),
        "offers": offers,
    }


@router.post("/needs/{need_id}/cancel")
async def bot_cancel_need(
    need_id: str,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Requester cancels an open need."""
    need = await db.get(CommunityRequest, need_id)
    if not need:
        raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy nhu cầu sách.", status_code=404)
    if need.user_id != actor.id:
        raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không có quyền hủy nhu cầu này.", status_code=403)

    need.status = "cancelled"
    await db.commit()
    return {"id": need.id, "status": "cancelled"}


# ==========================================
# SUPPORT OFFERS BOT ENDPOINTS
# ==========================================

class BotCreateOfferDTO(BaseModel):
    need_id: str
    offer_type: str
    copy_id: Optional[str] = None
    resource_id: Optional[str] = None
    covered_ranges: Optional[List[List[int]]] = None
    proposed_duration_days: int = 14
    coarse_pickup_area: Optional[str] = None
    message: Optional[str] = None


@router.post("/offers")
async def bot_create_offer(
    dto: BotCreateOfferDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Provider creates a support offer for an open need."""
    offer = await NeedService.create_offer(
        db=db,
        need_id=dto.need_id,
        provider_user_id=actor.id,
        offer_type=dto.offer_type,
        copy_id=dto.copy_id,
        resource_id=dto.resource_id,
        covered_ranges=dto.covered_ranges,
        proposed_duration_days=dto.proposed_duration_days,
        coarse_pickup_area=dto.coarse_pickup_area,
        message=dto.message,
    )
    await db.commit()
    return {
        "offer_id": offer.id,
        "need_id": offer.need_id,
        "status": offer.status,
    }


@router.post("/offers/{offer_id}/select")
async def bot_select_offer(
    offer_id: str,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Requester selects a support offer, reserving the physical copy or resource."""
    offer, loan = await NeedService.select_offer(
        db=db,
        offer_id=offer_id,
        requester_id=actor.id,
    )
    await db.commit()
    return {
        "offer_id": offer.id,
        "status": offer.status,
        "loan_id": loan.id if loan else None,
        "reservation_expires_at": loan.reservation_expires_at.isoformat() if loan and loan.reservation_expires_at else None,
    }


@router.post("/offers/{offer_id}/withdraw")
async def bot_withdraw_offer(
    offer_id: str,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Provider withdraws their proposed offer."""
    offer = await NeedService.withdraw_offer(db=db, offer_id=offer_id, provider_user_id=actor.id)
    await db.commit()
    return {"offer_id": offer.id, "status": offer.status}


@router.post("/offers/{offer_id}/decline")
async def bot_decline_offer(
    offer_id: str,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Requester declines a proposed offer."""
    offer = await NeedService.decline_offer(db=db, offer_id=offer_id, requester_id=actor.id)
    await db.commit()
    return {"offer_id": offer.id, "status": offer.status}


# ==========================================
# PARTIAL MATERIALS BOT ENDPOINTS
# ==========================================

class BotPartialCopyDTO(BaseModel):
    book_id: str
    condition: str = "good"
    barcode: Optional[str] = None
    start_page: int
    end_page: int
    pagination_basis: Optional[str] = None
    chapters: Optional[List[str]] = None
    source_description: Optional[str] = None


@router.post("/partial/copies")
async def bot_register_partial_copy(
    dto: BotPartialCopyDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """
    Register metadata for a partial physical copy/photocopy in user's private library.
    Strict Policy: Private by default; never public without verified rights.
    """
    from app.db.models.catalog import CopyCoverageRange
    if dto.start_page < 1 or dto.end_page < dto.start_page:
        raise BoconicException(code=ErrorCode.BAD_REQUEST, message="Khoảng trang không hợp lệ (1 <= start <= end).", status_code=400)

    # 1. Add copy with is_partial=True and private visibility
    coverage_summary = {
        "ranges": [[dto.start_page, dto.end_page]],
        "pagination_basis": dto.pagination_basis or "original_edition",
        "chapters": dto.chapters or [],
    }
    copy = await CatalogService.add_book_copy(
        db=db,
        book_id=dto.book_id,
        owner_id=actor.id,
        condition=dto.condition,
        barcode=dto.barcode,
        visibility="private",
        format_type="partial_photocopy",
        is_partial=True,
        coverage_summary=coverage_summary,
    )

    # 2. Add coverage range record
    coverage_range = CopyCoverageRange(
        copy_id=copy.id,
        start_page=dto.start_page,
        end_page=dto.end_page,
        pagination_basis=dto.pagination_basis or "original_edition",
        chapters=dto.chapters or [],
        source_description=dto.source_description,
        verification_status="unverified",
    )
    db.add(coverage_range)
    await db.commit()

    return {
        "copy_id": copy.id,
        "is_partial": True,
        "visibility": copy.visibility,
        "start_page": dto.start_page,
        "end_page": dto.end_page,
        "message": "Đã lưu bản tài liệu một phần vào Thư viện cá nhân của bạn (chế độ Riêng tư).",
    }


# ==========================================
# USER WARNINGS BOT ENDPOINTS
# ==========================================

class BotAppealWarningDTO(BaseModel):
    appeal_note: str


@router.get("/warnings/my")
async def bot_get_my_warnings(
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Fetch all warnings issued to user."""
    warnings = await WarningService.get_user_warnings(db=db, user_id=actor.id)
    return [
        {
            "id": w.id,
            "category": w.category,
            "severity": w.severity,
            "message": w.message,
            "reason": w.reason,
            "appeal_status": w.appeal_status,
            "acknowledged_at": w.acknowledged_at.isoformat() if w.acknowledged_at else None,
            "created_at": w.created_at.isoformat(),
        }
        for w in warnings
    ]


@router.post("/warnings/{warning_id}/acknowledge")
async def bot_acknowledge_warning(
    warning_id: str,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """User acknowledges a warning."""
    warning = await WarningService.acknowledge_warning(db=db, warning_id=warning_id, user_id=actor.id)
    await db.commit()
    return {"id": warning.id, "acknowledged_at": warning.acknowledged_at.isoformat()}


@router.post("/warnings/{warning_id}/appeal")
async def bot_appeal_warning(
    warning_id: str,
    dto: BotAppealWarningDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """User appeals a warning."""
    warning = await WarningService.submit_appeal(
        db=db,
        warning_id=warning_id,
        user_id=actor.id,
        appeal_note=dto.appeal_note,
    )
    await db.commit()
    return {"id": warning.id, "appeal_status": warning.appeal_status}


# ==========================================
# CHAPTERS & PERSONAL PROGRESS BOT ENDPOINTS
# ==========================================

class BotUpdateChapterProgressDTO(BaseModel):
    reading_state: str # not_started, in_progress, completed, paused
    bookmark_page: Optional[int] = None
    bookmark_note: Optional[str] = None
    personal_notes: Optional[str] = None


class BotCreateChapterProposalDTO(BaseModel):
    action: str = "create" # create, update, delete, reorder
    base_version: int = 1
    proposed_data: Dict[str, Any]
    reason: str
    source_evidence: Optional[str] = None
    chapter_id: Optional[str] = None


@router.get("/books/{book_id}/chapters")
async def bot_get_book_chapters_and_progress(
    book_id: str,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve book chapters combined with actor's personal reading progress."""
    from app.services.chapter_service import ChapterService
    book = await db.get(Book, book_id)
    chapters = await ChapterService.get_book_chapters(db, book_id=book_id)
    progress_summary = await ChapterService.get_user_progress(db, user_id=actor.id, book_id=book_id)
    return {
        "book_id": book_id,
        "book_title": book.title if book else "Sách",
        "chapters": chapters,
        "progress_summary": progress_summary,
    }


@router.post("/books/{book_id}/chapters/{chapter_id}/progress")
async def bot_update_chapter_progress(
    book_id: str,
    chapter_id: str,
    dto: BotUpdateChapterProgressDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Update personal chapter study progress via bot."""
    from app.services.chapter_service import ChapterService
    progress = await ChapterService.update_chapter_progress(
        db=db,
        user_id=actor.id,
        book_id=book_id,
        chapter_id=chapter_id,
        reading_state=dto.reading_state,
        bookmark_page=dto.bookmark_page,
        bookmark_note=dto.bookmark_note,
        personal_notes=dto.personal_notes,
    )
    await db.commit()
    return {
        "chapter_id": progress.chapter_id,
        "reading_state": progress.reading_state,
        "bookmark_page": progress.bookmark_page,
        "version": progress.version,
    }


@router.post("/books/{book_id}/chapter-proposals")
async def bot_create_chapter_proposal(
    book_id: str,
    dto: BotCreateChapterProposalDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Submit a chapter proposal via bot."""
    from app.services.chapter_service import ChapterService
    proposal = await ChapterService.create_chapter_proposal(
        db=db,
        user_id=actor.id,
        book_id=book_id,
        action=dto.action,
        proposed_data=dto.proposed_data,
        reason=dto.reason,
        source_evidence=dto.source_evidence,
        chapter_id=dto.chapter_id,
        base_version=dto.base_version,
    )
    await db.commit()
    return {
        "proposal_id": proposal.id,
        "action": proposal.action,
        "status": proposal.status,
    }


@router.get("/users/me/resources")
async def bot_get_my_resources(
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Get active resources in use for the requesting Telegram user."""
    from app.services.user_service import UserService
    return await UserService.get_user_resources_summary_api(db, user_id=actor.id)


@router.get("/users/{user_id}/resources")
async def bot_get_user_resources(
    user_id: str,
    x_bot_api_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Get active resources in use by user ID."""
    verify_bot_api_key(x_bot_api_key)
    from app.services.user_service import UserService
    return await UserService.get_user_resources_summary_api(db, user_id=user_id)


# ==========================================
# BOT PARTIAL MATERIALS ENDPOINTS
# ==========================================

class BotDeclarePhysicalPartialDTO(BaseModel):
    book_id: str
    start_page: int
    end_page: int
    chapters: Optional[List[Any]] = None
    condition: str = "good"
    source_description: Optional[str] = None
    visibility: str = "private"
    storage_location_private: Optional[str] = None
    notes: Optional[str] = None
    barcode: Optional[str] = None


class BotUploadDigitalPartialDTO(BaseModel):
    book_id: str
    chapter_id: Optional[str] = None
    title: str = "Tài liệu học tập"
    resource_type: str = "digital_fragment"
    url: Optional[str] = None
    file_bytes_base64: Optional[str] = None
    filename: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    rights_basis: str = "personal_fair_use"
    consent_given: bool = True
    provenance: Optional[str] = None
    is_public: bool = False


@router.post("/partial-materials/physical")
async def bot_declare_physical_partial(
    dto: BotDeclarePhysicalPartialDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Declare personal physical photocopy or partial holding via Bot."""
    from app.services.partial_material_service import PartialMaterialService
    copy, coverage_range = await PartialMaterialService.create_physical_partial_material(
        db=db,
        user_id=actor.id,
        book_id=dto.book_id,
        start_page=dto.start_page,
        end_page=dto.end_page,
        chapters=dto.chapters,
        condition=dto.condition,
        source_description=dto.source_description,
        visibility=dto.visibility,
        storage_location_private=dto.storage_location_private,
        notes=dto.notes,
        barcode=dto.barcode,
    )
    await db.commit()
    return {
        "status": "success",
        "copy_id": copy.id,
        "public_code": copy.public_code,
        "range_id": coverage_range.id,
        "coverage_summary": copy.coverage_summary,
        "visibility": copy.visibility,
    }


@router.post("/partial-materials/digital")
async def bot_upload_digital_partial(
    dto: BotUploadDigitalPartialDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Declare personal digital fragment or chapter link / file via Bot."""
    from app.services.partial_material_service import PartialMaterialService
    import base64

    file_bytes = None
    filename = dto.filename
    if dto.file_bytes_base64:
        try:
            file_bytes = base64.b64decode(dto.file_bytes_base64)
        except Exception:
            raise BoconicException(ErrorCode.VALIDATION_ERROR, "Tệp dữ liệu base64 không hợp lệ.", status_code=400)

    resource = await PartialMaterialService.create_digital_partial_material(
        db=db,
        user_id=actor.id,
        book_id=dto.book_id,
        chapter_id=dto.chapter_id or "auto",
        title=dto.title,
        resource_type="file" if file_bytes else dto.resource_type,
        url=dto.url,
        file_bytes=file_bytes,
        filename=filename,
        page_start=dto.page_start,
        page_end=dto.page_end,
        rights_basis=dto.rights_basis,
        consent_given=dto.consent_given,
        provenance=dto.provenance,
        is_public=dto.is_public,
    )
    await db.commit()
    return {
        "status": "success",
        "resource_id": resource.id,
        "title": resource.title,
        "chapter_id": resource.chapter_id,
        "book_id": resource.book_id,
        "verification_status": resource.verification_status,
        "is_public": resource.is_public,
        "has_file": bool(resource.file_path),
    }


@router.get("/partial-materials/me")
async def bot_get_my_partial_materials(
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Fetch personal partial materials owned by the requesting Telegram user."""
    from app.services.partial_material_service import PartialMaterialService
    return await PartialMaterialService.get_user_partial_materials(db=db, user_id=actor.id)


@router.delete("/partial-materials/physical/{copy_id}")
async def bot_delete_my_physical_partial(
    copy_id: str,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Delete personal physical partial copy via Bot."""
    from app.services.partial_material_service import PartialMaterialService
    await PartialMaterialService.delete_physical_partial_copy(db=db, user_id=actor.id, copy_id=copy_id)
    await db.commit()
    return {"status": "success", "deleted_copy_id": copy_id}


@router.delete("/partial-materials/digital/{resource_id}")
async def bot_delete_my_digital_partial(
    resource_id: str,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Delete personal digital partial resource via Bot."""
    from app.services.partial_material_service import PartialMaterialService
    await PartialMaterialService.delete_digital_partial_resource(db=db, user_id=actor.id, resource_id=resource_id)
    await db.commit()
    return {"status": "success", "deleted_resource_id": resource_id}


@router.get("/partial-materials/available")
async def bot_search_available_partial_materials(
    q: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Search and list available physical partial copies and verified digital fragments in the community."""
    from app.services.partial_material_service import PartialMaterialService
    return await PartialMaterialService.search_available_partial_materials(
        db=db,
        query=q,
        limit=limit,
    )


class BotQuickCreateBookDTO(BaseModel):
    title: str
    subject: Optional[str] = "Tài liệu học tập"
    curriculum: Optional[str] = "Cộng đồng"


@router.post("/books/quick-create")
async def bot_quick_create_book(
    dto: BotQuickCreateBookDTO,
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Instantly create a book entry so any user can upload or borrow arbitrary materials."""
    from app.db.models.catalog import Book, Chapter
    clean_title = dto.title.strip()
    if not clean_title:
        raise BoconicException(ErrorCode.VALIDATION_ERROR, "Tên tài liệu / sách không được để trống.", status_code=400)

    book = Book(
        title=clean_title,
        subject=dto.subject or "Tài liệu học tập",
        curriculum=dto.curriculum or "Cộng đồng",
        language="vi",
    )
    db.add(book)
    await db.flush()

    chapter = Chapter(
        book_id=book.id,
        chapter_number=1,
        title="Tài liệu & Trích đoạn chung",
    )
    db.add(chapter)
    await db.commit()
    return {
        "status": "success",
        "book_id": book.id,
        "title": book.title,
        "chapter_id": chapter.id,
    }


@router.get("/community/library")
async def bot_get_community_library(
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    actor: User = Depends(verify_bot_actor),
    db: AsyncSession = Depends(get_db),
):
    """Fetch all available community resources (full books, partial copies, digital resources)."""
    from app.services.partial_material_service import PartialMaterialService
    return await PartialMaterialService.get_all_community_available_resources(
        db=db,
        limit=limit,
        offset=offset,
    )






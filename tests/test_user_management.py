"""
Integration tests for User Management and Tracking Resources in Use.
Tests UserService, admin routes, API /me/resources, status updates, and force return.
"""
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.catalog import Author, Book, BookAuthor, BookCopy, Chapter, ChapterResource, UserChapterProgress
from app.db.models.community import CommunityRequest, SupportOffer, TrustEvent, UserWarning
from app.db.models.identity import AdminAccount, AdminSession, User, UserLocation, UserSettings
from app.db.models.lending import Loan
from app.services.user_service import UserService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_user_service_list_users(db_session: AsyncSession):
    """Test listing users with search, status filtering, and summarized resource metrics."""
    suffix = uuid.uuid4().hex[:6]
    u1 = User(
        display_name=f"Nguyen Van A {suffix}",
        public_alias=f"nguyenvana_{suffix}",
        telegram_user_id=8888001 + int(suffix[:4], 16),
        status="active",
    )
    u2 = User(
        display_name=f"Tran Thi B {suffix}",
        public_alias=f"tranthib_{suffix}",
        status="suspended",
    )
    db_session.add_all([u1, u2])
    await db_session.commit()

    # Add a book and copy owned by u1
    book = Book(title=f"Toán 10 {suffix}", subject="Toán", grade_level=10)
    db_session.add(book)
    await db_session.flush()

    copy = BookCopy(
        book_id=book.id,
        owner_id=u1.id,
        current_holder_id=u2.id,
        public_code=f"CPY-{suffix}",
        barcode=f"BC-{suffix}",
        circulation_status="on_loan",
    )
    db_session.add(copy)
    await db_session.flush()

    # Loan: u1 lent to u2
    loan = Loan(
        copy_id=copy.id,
        lender_id=u1.id,
        borrower_id=u2.id,
        status="active",
        due_at=utc_now() + timedelta(days=7),
    )
    db_session.add(loan)
    await db_session.commit()

    # Query list
    res = await UserService.list_users(db_session, search=suffix, status="all")
    assert res["total_count"] == 2
    users_data = res["users"]
    assert len(users_data) == 2

    # Check u1 metrics (lender)
    u1_item = next(item for item in users_data if item["user"].id == u1.id)
    assert u1_item["owned_copies"] == 1
    assert u1_item["active_lendings"] == 1
    assert u1_item["active_borrowings"] == 0

    # Check u2 metrics (borrower)
    u2_item = next(item for item in users_data if item["user"].id == u2.id)
    assert u2_item["active_borrowings"] == 1
    assert u2_item["user"].status == "suspended"

    # Test filtering by status
    res_active = await UserService.list_users(db_session, search=suffix, status="active")
    assert res_active["total_count"] == 1
    assert res_active["users"][0]["user"].id == u1.id


@pytest.mark.asyncio
async def test_user_resource_details_and_overdue(db_session: AsyncSession):
    """Test detailed breakdown of all resources currently in use by a user, including overdue check."""
    suffix = uuid.uuid4().hex[:6]
    borrower = User(
        display_name=f"Le Van C {suffix}",
        public_alias=f"levanc_{suffix}",
        telegram_user_id=7777001 + int(suffix[:4], 16),
        status="active",
    )
    lender = User(
        display_name=f"Pham Thi D {suffix}",
        public_alias=f"phamthid_{suffix}",
        status="active",
    )
    db_session.add_all([borrower, lender])
    await db_session.commit()

    book = Book(title=f"Vật lý 11 {suffix}", subject="Vật lý", grade_level=11)
    db_session.add(book)
    await db_session.flush()

    copy = BookCopy(
        book_id=book.id,
        owner_id=lender.id,
        current_holder_id=borrower.id,
        public_code=f"CPY-PHYS-{suffix}",
        barcode=f"BC-PHYS-{suffix}",
        circulation_status="on_loan",
    )
    db_session.add(copy)
    await db_session.flush()

    # Overdue active loan
    past_due = utc_now() - timedelta(days=3)
    loan = Loan(
        copy_id=copy.id,
        lender_id=lender.id,
        borrower_id=borrower.id,
        status="active",
        handed_over_at=utc_now() - timedelta(days=17),
        due_at=past_due,
    )
    db_session.add(loan)

    # Add chapter & chapter resource uploaded by borrower
    chapter = Chapter(book_id=book.id, chapter_number=1, title="Dao động điều hòa")
    db_session.add(chapter)
    await db_session.flush()

    resource = ChapterResource(
        chapter_id=chapter.id,
        book_id=book.id,
        owner_id=borrower.id,
        resource_type="excerpt",
        title="Tóm tắt công thức chương 1",
        verification_status="quarantine",
    )
    db_session.add(resource)

    # Add study progress
    progress = UserChapterProgress(
        user_id=borrower.id,
        book_id=book.id,
        chapter_id=chapter.id,
        reading_state="completed",
        bookmark_page=15,
        personal_notes="Ghi chú quan trọng về chu kỳ T.",
    )
    db_session.add(progress)

    # Add warning
    warning = UserWarning(
        subject_user_id=borrower.id,
        category="transaction_reminder",
        severity="warning",
        message="Sách đã quá hạn 3 ngày.",
        reason="Due date exceeded",
        issued_by="system",
    )
    db_session.add(warning)

    await db_session.commit()

    # Call get_user_resource_details
    details = await UserService.get_user_resource_details(db_session, user_id=borrower.id)
    assert details["user"].id == borrower.id
    assert len(details["borrowed_loans"]) == 1
    borrowed_item = details["borrowed_loans"][0]
    assert borrowed_item["book"].title == f"Vật lý 11 {suffix}"
    assert borrowed_item["is_overdue"] is True

    assert len(details["chapter_resources"]) == 1
    assert details["chapter_resources"][0].title == "Tóm tắt công thức chương 1"

    assert details["study_progress"]["completed_chapters"] == 1
    assert details["study_progress"]["notes_count"] == 1

    assert len(details["warnings"]) == 1
    assert details["warnings"][0].category == "transaction_reminder"


@pytest.mark.asyncio
async def test_update_user_status_and_audit(db_session: AsyncSession):
    """Test administrative user status update with audit log verification."""
    suffix = uuid.uuid4().hex[:6]
    user = User(
        display_name=f"User Audit {suffix}",
        public_alias=f"useraudit_{suffix}",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()

    # Update to suspended
    updated = await UserService.update_user_status(
        db=db_session,
        user_id=user.id,
        new_status="suspended",
        reason="Vi phạm quy tắc hoàn trả nhiều lần",
        admin_id="admin_test",
    )
    await db_session.commit()
    assert updated.status == "suspended"

    # Verify invalid status rejection
    with pytest.raises(Exception):
        await UserService.update_user_status(
            db=db_session,
            user_id=user.id,
            new_status="invalid_status",
            reason="Test",
            admin_id="admin_test",
        )


@pytest.mark.asyncio
async def test_admin_force_return_loan(db_session: AsyncSession):
    """Test administrative forced completion of a disputed/active loan."""
    suffix = uuid.uuid4().hex[:6]
    borrower = User(display_name=f"Borrower {suffix}", public_alias=f"b_{suffix}")
    lender = User(display_name=f"Lender {suffix}", public_alias=f"l_{suffix}")
    db_session.add_all([borrower, lender])
    await db_session.commit()

    book = Book(title=f"Hóa học 12 {suffix}", subject="Hóa", grade_level=12)
    db_session.add(book)
    await db_session.flush()

    copy = BookCopy(
        book_id=book.id,
        owner_id=lender.id,
        current_holder_id=borrower.id,
        public_code=f"CPY-CHEM-{suffix}",
        barcode=f"BC-CHEM-{suffix}",
        circulation_status="on_loan",
    )
    db_session.add(copy)
    await db_session.flush()

    loan = Loan(
        copy_id=copy.id,
        lender_id=lender.id,
        borrower_id=borrower.id,
        status="active",
        due_at=utc_now() + timedelta(days=5),
    )
    db_session.add(loan)
    await db_session.commit()

    # Admin forces return
    resolved_loan = await UserService.admin_force_return_loan(
        db=db_session,
        loan_id=loan.id,
        admin_id="super_admin",
        resolution_notes="Xác nhận người mượn đã trao trả sách trực tiếp tại thư viện",
    )
    await db_session.commit()

    assert resolved_loan.status == "returned"
    assert resolved_loan.returned_at is not None

    # Verify copy is back to available and holder restored to owner
    await db_session.refresh(copy)
    assert copy.circulation_status == "available"
    assert copy.current_holder_id == lender.id


@pytest.mark.asyncio
async def test_api_me_resources_json_serializable(db_session: AsyncSession):
    """Test that UserService.get_user_resources_summary_api produces valid JSON serializable structure."""
    suffix = uuid.uuid4().hex[:6]
    user = User(
        display_name=f"API User {suffix}",
        public_alias=f"apiuser_{suffix}",
        telegram_user_id=9999001 + int(suffix[:4], 16),
        status="active",
    )
    db_session.add(user)
    await db_session.commit()

    # Add book, copy, loan, chapter resource, and community request
    book = Book(title=f"Đại Số Tuyến Tính {suffix}")
    other_user = User(display_name=f"Partner {suffix}", public_alias=f"partner_{suffix}")
    db_session.add_all([book, other_user])
    await db_session.flush()

    copy = BookCopy(
        book_id=book.id,
        owner_id=user.id,
        current_holder_id=user.id,
        public_code=f"CPY-OWN-{suffix}",
        barcode=f"BC-OWN-{suffix}",
        condition="good",
        circulation_status="available",
    )
    copy_borrowed = BookCopy(
        book_id=book.id,
        owner_id=other_user.id,
        current_holder_id=user.id,
        public_code=f"CPY-BOR-{suffix}",
        condition="like_new",
        circulation_status="on_loan",
    )
    db_session.add_all([copy, copy_borrowed])
    await db_session.flush()

    loan = Loan(
        copy_id=copy_borrowed.id,
        lender_id=other_user.id,
        borrower_id=user.id,
        status="active",
        due_at=utc_now() + timedelta(days=5),
    )
    chapter = Chapter(book_id=book.id, chapter_number=1, title="Không gian vector")
    db_session.add_all([loan, chapter])
    await db_session.flush()

    c_res = ChapterResource(
        chapter_id=chapter.id,
        book_id=book.id,
        owner_id=user.id,
        title="Ghi chú bài giảng",
        resource_type="notes",
        verification_status="verified",
    )
    req = CommunityRequest(
        user_id=user.id,
        book_id=book.id,
        title_query=f"Đại Số Tuyến Tính {suffix}",
        status="open",
    )
    db_session.add_all([c_res, req])
    await db_session.commit()

    # Get API summary
    api_summary = await UserService.get_user_resources_summary_api(db_session, user_id=user.id)
    assert api_summary["user_id"] == user.id
    assert api_summary["display_name"] == f"API User {suffix}"
    assert len(api_summary["owned_copies"]) == 1
    assert api_summary["owned_copies"][0]["condition"] == "good"
    assert api_summary["owned_copies"][0]["condition_status"] == "good"
    assert len(api_summary["borrowed_loans"]) == 1
    assert len(api_summary["chapter_resources"]) == 1
    assert len(api_summary["open_needs"]) == 1


@pytest.mark.asyncio
async def test_api_internal_telegram_users_me_resources_endpoint(db_session: AsyncSession):
    """Test full HTTP GET /api/v1/internal/telegram/users/me/resources delegated endpoint."""
    import httpx
    from app.core.config import settings
    from app.main import app
    from app.db.session import get_db

    suffix = uuid.uuid4().hex[:6]
    tg_id = 7770001 + int(suffix[:4], 16)
    user = User(
        display_name=f"Bot TG User {suffix}",
        public_alias=f"bottg_{suffix}",
        telegram_user_id=tg_id,
        status="active",
    )
    book = Book(title=f"Sinh học 12 {suffix}")
    db_session.add_all([user, book])
    await db_session.flush()

    copy = BookCopy(
        book_id=book.id,
        owner_id=user.id,
        current_holder_id=user.id,
        public_code=f"CPY-TG-{suffix}",
        barcode=f"BC-TG-{suffix}",
        condition="fair",
        circulation_status="available",
    )
    db_session.add(copy)
    await db_session.commit()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {
                "X-Bot-Api-Key": settings.BOT_API_KEY,
                "X-Telegram-User-Id": str(tg_id),
            }
            res = await client.get("/api/v1/internal/telegram/users/me/resources", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["display_name"] == f"Bot TG User {suffix}"
            assert len(data["owned_copies"]) == 1
            assert data["owned_copies"][0]["condition"] == "fair"
            assert data["owned_copies"][0]["condition_status"] == "fair"
    finally:
        app.dependency_overrides.clear()

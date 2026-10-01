"""
Comprehensive integration tests for Admin Console web interface.
Tests authentication, authorization, CRUD operations on books, copies, chapters,
loans, users, RBAC roles, and all administrative views.
"""
import uuid
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, generate_session_token, generate_csrf_token
from app.db.models.catalog import Author, Book, BookAuthor, BookCopy, Chapter, ChapterResource
from app.db.models.community import AuthorizedCollection, CommunityRequest, Report, UserWarning
from app.db.models.identity import AdminAccount, AdminSession, User
from app.db.models.lending import Loan
from app.db.models.rbac import Role, Permission
from app.db.session import get_db
from app.main import app


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def create_test_admin(db_session: AsyncSession) -> tuple[AdminAccount, str]:
    suffix = uuid.uuid4().hex[:6]
    admin = AdminAccount(
        username=f"admin_{suffix}",
        email=f"admin_{suffix}@boconic.org",
        password_hash=hash_password("SuperSecretAdminPass123!"),
        is_active=True,
    )
    db_session.add(admin)
    await db_session.flush()

    token = generate_session_token()
    csrf = generate_csrf_token()
    session = AdminSession(
        admin_id=admin.id,
        session_token=token,
        csrf_token=csrf,
        expires_at=utc_now() + timedelta(days=1),
    )
    db_session.add(session)
    await db_session.commit()
    return admin, token


@pytest.mark.asyncio
async def test_admin_login_and_logout(db_session: AsyncSession):
    """Test login form GET, POST with credentials, session cookie issuance, and logout."""
    admin, _ = await create_test_admin(db_session)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. GET login page
            res = await client.get("/admin/login")
            assert res.status_code == 200
            assert "Boconic" in res.text

            # 2. POST login with correct password
            res_login = await client.post(
                "/admin/login",
                data={"username": admin.username, "password": "SuperSecretAdminPass123!"},
                follow_redirects=False,
            )
            assert res_login.status_code == 303
            assert res_login.headers["location"] == "/admin/dashboard"
            assert "boconic_session" in res_login.cookies

            # 3. POST login with invalid password
            res_fail = await client.post(
                "/admin/login",
                data={"username": admin.username, "password": "WrongPassword"},
            )
            assert res_fail.status_code == 200
            assert "không chính xác" in res_fail.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_dashboard_and_core_views(db_session: AsyncSession):
    """Test accessing all core admin navigation pages with valid session."""
    admin, token = await create_test_admin(db_session)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"boconic_session": token}) as client:
            # 1. Dashboard
            r = await client.get("/admin/dashboard")
            assert r.status_code == 200
            assert "Bảng điều khiển" in r.text
            assert "Lượt mượn quá hạn" in r.text

            # 2. Books list
            r = await client.get("/admin/books")
            assert r.status_code == 200
            assert "Đầu sách (Catalog)" in r.text

            # 3. Copies list
            r = await client.get("/admin/copies")
            assert r.status_code == 200
            assert "Bản sách vật lý" in r.text

            # 4. Loans list
            r = await client.get("/admin/loans")
            assert r.status_code == 200
            assert "Lượt mượn" in r.text

            # 5. Users list
            r = await client.get("/admin/users")
            assert r.status_code == 200
            assert "Quản lý người dùng" in r.text

            # 6. Chapter proposals
            r = await client.get("/admin/chapter-proposals")
            assert r.status_code == 200

            # 7. Moderation / warnings
            r = await client.get("/admin/moderation")
            assert r.status_code == 200

            # 8. Process audit
            r = await client.get("/admin/process-audit")
            assert r.status_code == 200

            # 9. Requests
            r = await client.get("/admin/requests")
            assert r.status_code == 200

            # 10. Inventory
            r = await client.get("/admin/inventory")
            assert r.status_code == 200

            # 11. Partial materials
            r = await client.get("/admin/partial-materials")
            assert r.status_code == 200

            # 12. Collections
            r = await client.get("/admin/collections")
            assert r.status_code == 200

            # 13. Analytics
            r = await client.get("/admin/analytics")
            assert r.status_code == 200

            # 14. Custom fields
            r = await client.get("/admin/custom-fields")
            assert r.status_code == 200

            # 15. Backups
            r = await client.get("/admin/backups")
            assert r.status_code == 200

            # 16. Import wizard
            r = await client.get("/admin/import")
            assert r.status_code == 200

            # 17. Roles & RBAC
            r = await client.get("/admin/roles")
            assert r.status_code == 200
            assert "Phân quyền" in r.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_book_lifecycle_and_details(db_session: AsyncSession):
    """Test full book CRUD: create, view detail, edit metadata, add chapter, add copy."""
    admin, token = await create_test_admin(db_session)
    suffix = uuid.uuid4().hex[:6]

    # Pre-create an author and user
    author = Author(name=f"Tác giả {suffix}")
    user = User(display_name=f"Chủ sách {suffix}", public_alias=f"owner_{suffix}", status="active")
    db_session.add_all([author, user])
    await db_session.commit()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"boconic_session": token}) as client:
            # 1. Create a book via POST /admin/books
            isbn = f"978-604-0-{suffix[:4]}-1"
            res_create = await client.post(
                "/admin/books",
                data={
                    "title": f"Sách Thử Nghiệm {suffix}",
                    "authors": author.name,
                    "isbn": isbn,
                    "publisher": "NXB Giáo Dục",
                    "publication_year": 2024,
                    "description": "Mô tả sách thử nghiệm",
                    "subject": "Toán học",
                    "grade_level": 11,
                },
                follow_redirects=False,
            )
            assert res_create.status_code == 303
            loc = res_create.headers["location"]
            book_id = loc.split("/admin/books/")[1].split("?")[0]

            # 2. View book detail page
            res_detail = await client.get(f"/admin/books/{book_id}")
            assert res_detail.status_code == 200
            assert f"{suffix}" in res_detail.text
            assert "panel-info" in res_detail.text
            assert "panel-copies" in res_detail.text
            assert "panel-chapters" in res_detail.text

            # 3. GET edit book page
            res_edit_page = await client.get(f"/admin/books/{book_id}/edit")
            assert res_edit_page.status_code == 200
            assert "form" in res_edit_page.text

            # 4. POST edit book
            res_edit = await client.post(
                f"/admin/books/{book_id}/edit",
                data={
                    "title": f"Sách Thử Nghiệm {suffix} (Đã cập nhật)",
                    "authors": author.name,
                    "publisher": "NXB Kim Đồng",
                    "publication_year": 2025,
                    "subject": "Toán Nâng Cao",
                    "grade_level": 12,
                    "description": "Mô tả cập nhật mới",
                },
                follow_redirects=False,
            )
            assert res_edit.status_code == 303

            # 5. Add Chapter to book
            res_chap_page = await client.get(f"/admin/books/{book_id}/chapters/add")
            assert res_chap_page.status_code == 200

            res_add_chap = await client.post(
                f"/admin/books/{book_id}/chapters/add",
                data={
                    "title": "Chương 1: Khởi động",
                    "chapter_code": "CH-01",
                    "page_start": 1,
                    "page_end": 25,
                    "pagination_basis": "edition_page_numbers",
                    "order_index": 1,
                },
                follow_redirects=False,
            )
            assert res_add_chap.status_code == 303

            # 6. Add Physical Copy to book
            res_copy_page = await client.get(f"/admin/books/{book_id}/copies/add")
            assert res_copy_page.status_code == 200

            res_add_copy = await client.post(
                f"/admin/books/{book_id}/copies/add",
                data={
                    "owner_id": user.id,
                    "condition": "like_new",
                    "format_type": "physical",
                    "barcode": f"BC-{suffix}",
                    "lending_policy": "free_return",
                },
                follow_redirects=False,
            )
            assert res_add_copy.status_code == 303

            # Verify in detail page that chapter and copy show up
            res_detail2 = await client.get(f"/admin/books/{book_id}")
            assert res_detail2.status_code == 200
            assert "CH-01" in res_detail2.text
            assert f"BC-{suffix}" in res_detail2.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_copy_and_loan_lifecycle(db_session: AsyncSession):
    """Test copy detail, condition/status update, loan detail, dispute resolution, and force return."""
    admin, token = await create_test_admin(db_session)
    suffix = uuid.uuid4().hex[:6]

    u_lender = User(display_name=f"Lender {suffix}", public_alias=f"lender_{suffix}")
    u_borrower = User(display_name=f"Borrower {suffix}", public_alias=f"borrower_{suffix}")
    book = Book(title=f"Vật Lý 11 {suffix}")
    db_session.add_all([u_lender, u_borrower, book])
    await db_session.flush()

    copy = BookCopy(
        book_id=book.id,
        owner_id=u_lender.id,
        current_holder_id=u_borrower.id,
        public_code=f"CPY-PHY-{suffix}",
        barcode=f"BC-PHY-{suffix}",
        condition="good",
        circulation_status="on_loan",
    )
    db_session.add(copy)
    await db_session.flush()

    loan = Loan(
        copy_id=copy.id,
        lender_id=u_lender.id,
        borrower_id=u_borrower.id,
        status="active",
        due_at=utc_now() + timedelta(days=7),
    )
    db_session.add(loan)
    await db_session.commit()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"boconic_session": token}) as client:
            # 1. Copy detail page
            res_copy = await client.get(f"/admin/copies/{copy.id}")
            assert res_copy.status_code == 200
            assert f"CPY-PHY-{suffix}" in res_copy.text

            # 2. Update copy status/condition
            res_upd_copy = await client.post(
                f"/admin/copies/{copy.id}/update",
                data={
                    "condition": "fair",
                    "visibility": "private",
                    "notes": "Sách có ghi chú bút chì",
                },
                follow_redirects=False,
            )
            assert res_upd_copy.status_code == 303

            # 3. Loan detail page
            res_loan = await client.get(f"/admin/loans/{loan.id}")
            assert res_loan.status_code == 200
            assert f"Lender {suffix}" in res_loan.text
            assert f"Borrower {suffix}" in res_loan.text
            assert "Cưỡng chế trả" in res_loan.text

            # 4. Resolve dispute / force return
            res_force = await client.post(
                f"/admin/loans/{loan.id}/force-return",
                data={"resolution_notes": "Admin can thiệp xác nhận đã hoàn trả tại văn phòng"},
                follow_redirects=False,
            )
            assert res_force.status_code == 303

            # Verify loan is now completed
            await db_session.refresh(loan)
            assert loan.status == "returned"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_rbac_operations(db_session: AsyncSession):
    """Test RBAC role creation, account creation, and status toggle."""
    admin, token = await create_test_admin(db_session)
    suffix = uuid.uuid4().hex[:6]

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"boconic_session": token}) as client:
            # 1. GET /admin/roles (triggers auto-seeding of default roles/permissions)
            res_roles = await client.get("/admin/roles")
            assert res_roles.status_code == 200
            assert "superadmin" in res_roles.text
            assert "catalog.read" in res_roles.text

            # 2. Create custom role
            role_name = f"auditor_{suffix}"
            res_new_role = await client.post(
                "/admin/roles/create",
                data={"name": role_name, "description": "Kiểm toán viên"},
                follow_redirects=False,
            )
            assert res_new_role.status_code == 303

            # Verify role created in DB
            role_db = (await db_session.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
            assert role_db is not None

            # 3. Create new Admin Account
            new_username = f"newops_{suffix}"
            res_new_acc = await client.post(
                "/admin/roles/accounts/create",
                data={
                    "username": new_username,
                    "password": "ValidStrongPassword123!",
                    "email": f"{new_username}@boconic.org",
                    "role_id": role_db.id,
                },
                follow_redirects=False,
            )
            assert res_new_acc.status_code == 303

            # Verify admin account created
            new_acc_db = (await db_session.execute(select(AdminAccount).where(AdminAccount.username == new_username))).scalar_one_or_none()
            assert new_acc_db is not None
            assert new_acc_db.is_active is True

            # 4. Toggle account status (lock account)
            res_lock = await client.post(
                f"/admin/roles/accounts/{new_acc_db.id}/toggle-status",
                follow_redirects=False,
            )
            assert res_lock.status_code == 303
            await db_session.refresh(new_acc_db)
            assert new_acc_db.is_active is False
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_user_detail_view(db_session: AsyncSession):
    """Test viewing user detail page with full resources, loans, copies, and warnings."""
    admin, token = await create_test_admin(db_session)
    suffix = uuid.uuid4().hex[:6]

    user = User(
        display_name=f"Chi Tiet User {suffix}",
        public_alias=f"chitiet_{suffix}",
        telegram_user_id=12345000 + int(suffix[:4], 16),
        status="active",
    )
    partner = User(display_name=f"Partner {suffix}", public_alias=f"partner_{suffix}")
    book = Book(title=f"Sách Giáo Khoa {suffix}")
    db_session.add_all([user, partner, book])
    await db_session.flush()

    # Owned copy
    copy1 = BookCopy(
        book_id=book.id,
        owner_id=user.id,
        current_holder_id=user.id,
        public_code=f"CPY-U1-{suffix}",
        barcode=f"BC-U1-{suffix}",
        condition="good",
        circulation_status="available",
    )
    # Borrowed copy
    copy2 = BookCopy(
        book_id=book.id,
        owner_id=partner.id,
        current_holder_id=user.id,
        public_code=f"CPY-U2-{suffix}",
        condition="fair",
        circulation_status="on_loan",
    )
    # Lent copy
    copy3 = BookCopy(
        book_id=book.id,
        owner_id=user.id,
        current_holder_id=partner.id,
        public_code=f"CPY-U3-{suffix}",
        condition="like_new",
        circulation_status="on_loan",
    )
    db_session.add_all([copy1, copy2, copy3])
    await db_session.flush()

    loan_borrowed = Loan(
        copy_id=copy2.id,
        lender_id=partner.id,
        borrower_id=user.id,
        status="active",
        due_at=utc_now() - timedelta(days=2), # overdue!
    )
    loan_lent = Loan(
        copy_id=copy3.id,
        lender_id=user.id,
        borrower_id=partner.id,
        status="active",
        due_at=utc_now() + timedelta(days=5),
    )
    chapter = Chapter(book_id=book.id, chapter_number=1, title="Chương mở đầu")
    db_session.add_all([loan_borrowed, loan_lent, chapter])
    await db_session.flush()

    c_res = ChapterResource(
        chapter_id=chapter.id,
        book_id=book.id,
        owner_id=user.id,
        title="Tài liệu tham khảo",
        resource_type="link",
        url="https://example.com/doc",
        verification_status="verified",
    )
    req = CommunityRequest(
        user_id=user.id,
        book_id=book.id,
        title_query=f"Sách Giáo Khoa {suffix}",
        target_chapters=[1, 2],
        status="open",
    )
    warn = UserWarning(
        subject_user_id=user.id,
        category="transaction_reminder",
        severity="high",
        message="Quá hạn trả sách",
        reason="Chưa trả sách sau 14 ngày",
        issued_by=admin.username,
    )
    db_session.add_all([c_res, req, warn])
    await db_session.commit()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"boconic_session": token}) as client:
            res = await client.get(f"/admin/users/{user.id}")
            assert res.status_code == 200
            assert f"Chi Tiet User {suffix}" in res.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_loans_search_dispute_resolution_and_reports(db_session: AsyncSession):
    """
    Test comprehensive admin management of loans and disputes:
    1. Filter and keyword search on /admin/loans
    2. Dispute resolution post action
    3. Moderation dashboard with disputed loans and reports
    4. Report resolution post action
    """
    suffix = uuid.uuid4().hex[:6]
    admin, token = await create_test_admin(db_session)

    lender = User(display_name=f"Lender {suffix}", public_alias=f"lender_{suffix}", status="active")
    borrower = User(display_name=f"Borrower {suffix}", public_alias=f"borrower_{suffix}", status="active")
    book = Book(title=f"Triết học Mác Lênin {suffix}", subject="Lý luận")
    db_session.add_all([lender, borrower, book])
    await db_session.commit()

    copy = BookCopy(
        book_id=book.id,
        owner_id=lender.id,
        current_holder_id=borrower.id,
        public_code=f"BC-TEST-{suffix[:4]}",
        circulation_status="loaned",
        visibility="published",
    )
    db_session.add(copy)
    await db_session.commit()

    # Create disputed loan
    loan = Loan(
        copy_id=copy.id,
        borrower_id=borrower.id,
        lender_id=lender.id,
        status="disputed",
        custom_data={"notes": "Tranh chấp tình trạng sách sau khi trả"},
    )
    db_session.add(loan)
    await db_session.flush()

    # Create community report
    report = Report(
        reporter_id=borrower.id,
        target_entity_type="loan",
        target_entity_id=loan.id,
        category="damaged_or_lost",
        description="Chủ sách báo mất sách nhưng tôi đã gửi trả qua bưu điện",
        status="open",
    )
    db_session.add(report)
    await db_session.commit()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"boconic_session": token}) as client:
            # 1. Search loans by keyword
            res_search = await client.get(f"/admin/loans?q={suffix}")
            assert res_search.status_code == 200
            assert book.title in res_search.text
            assert "disputed" in res_search.text

            # 2. View moderation page - should list disputed loan and user report
            res_mod = await client.get("/admin/moderation")
            assert res_mod.status_code == 200
            assert "Tranh chấp Lượt mượn" in res_mod.text
            assert book.title in res_mod.text
            assert "Chủ sách báo mất sách nhưng tôi đã gửi trả" in res_mod.text

            # 3. Resolve dispute -> mark returned
            res_dispute = await client.post(
                f"/admin/loans/{loan.id}/resolve",
                data={
                    "resolution": "returned",
                    "reason": "Đã xác minh vận đơn bưu chính hợp lệ",
                    "redirect_to": "/admin/loans",
                },
                follow_redirects=True,
            )
            assert res_dispute.status_code == 200
            await db_session.refresh(loan)
            assert loan.status == "returned"
            await db_session.refresh(copy)
            assert copy.circulation_status == "available"

            # 4. Resolve community report
            res_rep = await client.post(
                f"/admin/reports/{report.id}/resolve",
                data={
                    "status": "resolved",
                    "resolution_note": "Tranh chấp đã được xử lý thỏa đáng qua bưu cục",
                },
                follow_redirects=True,
            )
            assert res_rep.status_code == 200
            await db_session.refresh(report)
            assert report.status == "resolved"
            assert report.resolution_note == "Tranh chấp đã được xử lý thỏa đáng qua bưu cục"
    finally:
        app.dependency_overrides.clear()


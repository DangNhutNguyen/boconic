"""
Integration tests for User Account Partial Materials Upload & Declaration.
Tests:
1. Physical photocopy declaration (BookCopy with is_partial=True + CopyCoverageRange).
2. Range validation and anti-circumvention policy checks.
3. Digital excerpt upload (ChapterResource with fair-use pledge and quarantine status).
4. Personal partial material aggregation (GET /me/partial-materials).
5. Safe deletion guards (loan conflict protection and file cleanup).
6. HTTP endpoints for user account self-service.
"""
import base64
import os
import uuid
import pytest
from datetime import datetime, timezone
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import BoconicException
from app.db.models.catalog import Book, BookCopy, Chapter, ChapterResource, CopyCoverageRange
from app.db.models.identity import User
from app.db.models.jobs import OutboxEvent
from app.db.models.lending import Loan
from app.db.session import get_db
from app.main import app
from app.services.partial_material_service import PartialMaterialService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_create_physical_partial_material_success(db_session: AsyncSession):
    """Test declaring a physical photocopy holding with automatic coverage range and private visibility."""
    suffix = uuid.uuid4().hex[:6]
    user = User(
        display_name=f"User Partial {suffix}",
        public_alias=f"userpart_{suffix}",
        telegram_user_id=990001 + int(suffix[:4], 16),
        status="active",
    )
    book = Book(
        title=f"Giáo trình Giải tích 1 - {suffix}",
        subject="Toán học",
        custom_data={"total_pages": 350},
    )
    db_session.add_all([user, book])
    await db_session.commit()

    copy, coverage_range = await PartialMaterialService.create_physical_partial_material(
        db=db_session,
        user_id=user.id,
        book_id=book.id,
        start_page=1,
        end_page=50,
        chapters=[1, 2],
        condition="good",
        source_description="Bản photocopy học tập tại ĐHBK",
        visibility="private",
    )
    await db_session.commit()

    assert copy.is_partial is True
    assert copy.format == "physical"
    assert copy.visibility == "private"
    assert copy.owner_id == user.id
    assert copy.current_holder_id == user.id
    assert copy.coverage_summary["total_pages_covered"] == 50
    assert copy.coverage_summary["ranges"][0] == {"start": 1, "end": 50}

    assert coverage_range.copy_id == copy.id
    assert coverage_range.start_page == 1
    assert coverage_range.end_page == 50
    assert coverage_range.verification_status == "unverified"

    # Outbox event check
    outbox_stmt = select(OutboxEvent).where(
        OutboxEvent.aggregate_id == copy.id,
        OutboxEvent.event_type == "PARTIAL_COPY_DECLARED",
    )
    outbox = (await db_session.execute(outbox_stmt)).scalar_one_or_none()
    assert outbox is not None
    assert outbox.payload["pages_count"] == 50


@pytest.mark.asyncio
async def test_physical_partial_validation_errors(db_session: AsyncSession):
    """Test range validation: start < 1, end < start, or end > total_pages."""
    suffix = uuid.uuid4().hex[:6]
    user = User(
        display_name=f"User Val {suffix}",
        public_alias=f"userval_{suffix}",
        status="active",
    )
    book = Book(
        title=f"Đại số tuyến tính - {suffix}",
        custom_data={"total_pages": 200},
    )
    db_session.add_all([user, book])
    await db_session.commit()

    # Case 1: start_page < 1
    with pytest.raises(BoconicException) as exc1:
        await PartialMaterialService.create_physical_partial_material(
            db=db_session,
            user_id=user.id,
            book_id=book.id,
            start_page=0,
            end_page=50,
        )
    assert exc1.value.status_code == 400

    # Case 2: end_page < start_page
    with pytest.raises(BoconicException) as exc2:
        await PartialMaterialService.create_physical_partial_material(
            db=db_session,
            user_id=user.id,
            book_id=book.id,
            start_page=60,
            end_page=40,
        )
    assert exc2.value.status_code == 400

    # Case 3: end_page > book.total_pages
    with pytest.raises(BoconicException) as exc3:
        await PartialMaterialService.create_physical_partial_material(
            db=db_session,
            user_id=user.id,
            book_id=book.id,
            start_page=1,
            end_page=250,
        )
    assert exc3.value.status_code == 400


@pytest.mark.asyncio
async def test_create_digital_partial_material_quarantine(db_session: AsyncSession):
    """Test digital excerpt upload enforces fair-use pledge and sets quarantine status."""
    suffix = uuid.uuid4().hex[:6]
    user = User(
        display_name=f"User Dig {suffix}",
        public_alias=f"userdig_{suffix}",
        status="active",
    )
    book = Book(title=f"Vật lý đại cương - {suffix}", custom_data={"total_pages": 400})
    db_session.add_all([user, book])
    await db_session.flush()

    chapter = Chapter(book_id=book.id, chapter_number=1, title="Cơ học chất điểm")
    db_session.add(chapter)
    await db_session.commit()

    # Fair-use consent required
    with pytest.raises(BoconicException) as exc:
        await PartialMaterialService.create_digital_partial_material(
            db=db_session,
            user_id=user.id,
            book_id=book.id,
            chapter_id=chapter.id,
            title="Bài tập chương 1",
            consent_given=False,
        )
    assert exc.value.status_code == 400

    # Successful upload with file bytes
    sample_content = b"Mock excerpt content for Chapter 1 study."
    resource = await PartialMaterialService.create_digital_partial_material(
        db=db_session,
        user_id=user.id,
        book_id=book.id,
        chapter_id=chapter.id,
        title="Tóm tắt công thức Chương 1",
        file_bytes=sample_content,
        filename="ch1_summary.pdf",
        page_start=1,
        page_end=20,
        rights_basis="personal_fair_use",
        consent_given=True,
    )
    await db_session.commit()

    assert resource.verification_status == "quarantine"
    assert resource.is_public is False
    assert resource.checksum_sha256 is not None
    assert resource.file_path is not None
    assert os.path.exists(resource.file_path)

    # Clean up file in test
    if os.path.exists(resource.file_path):
        os.remove(resource.file_path)


@pytest.mark.asyncio
async def test_get_user_partial_materials_aggregation(db_session: AsyncSession):
    """Test retrieving combined physical and digital partial materials for user."""
    suffix = uuid.uuid4().hex[:6]
    user = User(
        display_name=f"User Agg {suffix}",
        public_alias=f"useragg_{suffix}",
        status="active",
    )
    book = Book(title=f"Hóa học hữu cơ - {suffix}", custom_data={"total_pages": 500})
    db_session.add_all([user, book])
    await db_session.flush()

    chapter = Chapter(book_id=book.id, chapter_number=2, title="Ankan & Anken")
    db_session.add(chapter)
    await db_session.commit()

    # Add 1 physical partial
    await PartialMaterialService.create_physical_partial_material(
        db=db_session,
        user_id=user.id,
        book_id=book.id,
        start_page=50,
        end_page=120,
        source_description="Tài liệu photo bài tập",
    )

    # Add 1 digital partial link
    await PartialMaterialService.create_digital_partial_material(
        db=db_session,
        user_id=user.id,
        book_id=book.id,
        chapter_id=chapter.id,
        title="Link slide bài giảng chương 2",
        url="https://drive.google.com/sample_slide",
        rights_basis="personal_fair_use",
        consent_given=True,
    )
    await db_session.commit()

    summary = await PartialMaterialService.get_user_partial_materials(db=db_session, user_id=user.id)
    assert summary["total_physical_partial"] == 1
    assert summary["total_digital_partial"] == 1
    assert len(summary["physical_copies"]) == 1
    assert len(summary["digital_resources"]) == 1

    phys = summary["physical_copies"][0]
    assert phys["ranges"][0]["pages_count"] == 71
    assert phys["visibility"] == "private"

    dig = summary["digital_resources"][0]
    assert dig["title"] == "Link slide bài giảng chương 2"
    assert dig["verification_status"] == "quarantine"


@pytest.mark.asyncio
async def test_delete_protection_when_on_loan(db_session: AsyncSession):
    """Test invariant: user cannot delete a partial copy while locked in active/reserved loan."""
    suffix = uuid.uuid4().hex[:6]
    u1 = User(display_name=f"Lender {suffix}", public_alias=f"lender_{suffix}", status="active")
    u2 = User(display_name=f"Borrower {suffix}", public_alias=f"borrower_{suffix}", status="active")
    book = Book(title=f"Kinh tế lượng - {suffix}", custom_data={"total_pages": 300})
    db_session.add_all([u1, u2, book])
    await db_session.commit()

    copy, _ = await PartialMaterialService.create_physical_partial_material(
        db=db_session,
        user_id=u1.id,
        book_id=book.id,
        start_page=10,
        end_page=60,
    )
    await db_session.commit()

    # Lock in an active loan
    loan = Loan(
        copy_id=copy.id,
        lender_id=u1.id,
        borrower_id=u2.id,
        status="active",
        due_at=utc_now(),
    )
    copy.circulation_status = "on_loan"
    db_session.add(loan)
    await db_session.commit()

    # Should raise 409 Conflict
    with pytest.raises(BoconicException) as exc:
        await PartialMaterialService.delete_physical_partial_copy(
            db=db_session,
            user_id=u1.id,
            copy_id=copy.id,
        )
    assert exc.value.status_code == 409

    # Test deleting an unloaned partial copy -> succeeds
    unloaned_copy, _ = await PartialMaterialService.create_physical_partial_material(
        db=db_session,
        user_id=u1.id,
        book_id=book.id,
        start_page=70,
        end_page=90,
    )
    await db_session.commit()

    await PartialMaterialService.delete_physical_partial_copy(
        db=db_session,
        user_id=u1.id,
        copy_id=unloaned_copy.id,
    )
    await db_session.commit()

    deleted_copy = await db_session.get(BookCopy, unloaned_copy.id)
    assert deleted_copy is None


@pytest.mark.asyncio
async def test_api_partial_materials_endpoints(db_session: AsyncSession):
    """Test user HTTP endpoints /api/v1/me/partial-materials/..."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    suffix = uuid.uuid4().hex[:6]
    user = User(
        display_name=f"HTTP User {suffix}",
        public_alias=f"httpuser_{suffix}",
        status="active",
    )
    book = Book(title=f"Lập trình Python - {suffix}", custom_data={"total_pages": 280})
    db_session.add_all([user, book])
    await db_session.flush()

    chapter = Chapter(book_id=book.id, chapter_number=1, title="Cơ bản")
    db_session.add(chapter)
    await db_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. POST physical
        phys_payload = {
            "user_id": user.id,
            "book_id": book.id,
            "start_page": 1,
            "end_page": 40,
            "condition": "good",
            "source_description": "Photo cá nhân",
            "visibility": "private",
        }
        res1 = await ac.post("/api/v1/me/partial-materials/physical", json=phys_payload)
        assert res1.status_code == 200
        copy_id = res1.json()["copy_id"]
        assert res1.json()["visibility"] == "private"

        # 2. POST digital json
        dig_payload = {
            "user_id": user.id,
            "book_id": book.id,
            "chapter_id": chapter.id,
            "title": "Ghi chú Python Chương 1",
            "url": "https://example.com/notes.pdf",
            "page_start": 1,
            "page_end": 15,
            "rights_basis": "personal_fair_use",
            "consent_given": True,
        }
        res2 = await ac.post("/api/v1/me/partial-materials/digital/json", json=dig_payload)
        assert res2.status_code == 200
        resource_id = res2.json()["resource_id"]
        assert res2.json()["verification_status"] == "quarantine"

        # 3. GET list
        res3 = await ac.get(f"/api/v1/me/partial-materials?user_id={user.id}")
        assert res3.status_code == 200
        data = res3.json()
        assert data["total_physical_partial"] == 1
        assert data["total_digital_partial"] == 1

        # 4. DELETE digital
        res4 = await ac.delete(f"/api/v1/me/partial-materials/digital/{resource_id}?user_id={user.id}")
        assert res4.status_code == 200

        # 5. DELETE physical
        res5 = await ac.delete(f"/api/v1/me/partial-materials/physical/{copy_id}?user_id={user.id}")
        assert res5.status_code == 200

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_digital_partial_multipart_upload_and_download(db_session: AsyncSession):
    """Test uploading digital partial file via multipart form and downloading it."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    suffix = uuid.uuid4().hex[:6]
    user = User(
        display_name=f"Upload User {suffix}",
        public_alias=f"upuser_{suffix}",
        status="active",
    )
    book = Book(title=f"Triết học Mác-Lênin - {suffix}", custom_data={"total_pages": 450})
    db_session.add_all([user, book])
    await db_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        file_content = b"PDF sample content for Philosophy chapter 2 excerpt."
        files = {
            "file": ("de_cuong_on_tap.pdf", file_content, "application/pdf")
        }
        data = {
            "user_id": user.id,
            "book_id": book.id,
            "chapter_id": "auto", # Tests auto-chapter resolution when no chapters exist!
            "title": "Đề cương ôn tập Triết",
            "page_start": "10",
            "page_end": "35",
            "rights_basis": "personal_fair_use",
            "consent_given": "true",
        }
        res_upload = await ac.post("/api/v1/me/partial-materials/digital", data=data, files=files)
        assert res_upload.status_code == 200
        res_data = res_upload.json()
        assert res_data["status"] == "success"
        assert res_data["has_file"] is True
        resource_id = res_data["resource_id"]

        # Download file
        res_dl = await ac.get(f"/api/v1/me/partial-materials/digital/{resource_id}/file?user_id={user.id}")
        assert res_dl.status_code == 200
        assert res_dl.content == file_content

        # Get summary and verify filename
        res_list = await ac.get(f"/api/v1/me/partial-materials?user_id={user.id}")
        assert res_list.status_code == 200
        dig_items = res_list.json()["digital_resources"]
        assert len(dig_items) == 1
        assert dig_items[0]["has_file"] is True
        assert dig_items[0]["filename"] is not None

        # Clean up
        res_del = await ac.delete(f"/api/v1/me/partial-materials/digital/{resource_id}?user_id={user.id}")
        assert res_del.status_code == 200

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_bot_digital_partial_base64_upload_and_auto_chapter(db_session: AsyncSession):
    """Test bot endpoint for uploading digital partial material with base64 encoded file and auto-chaptering."""
    import base64
    from app.core.config import settings

    suffix = uuid.uuid4().hex[:6]
    tg_id = 998800 + int(suffix[:4], 16)
    user = User(
        display_name=f"Bot TG User {suffix}",
        public_alias=f"bottg_{suffix}",
        telegram_user_id=tg_id,
        status="active",
    )
    book = Book(title=f"Xác suất thống kê - {suffix}")
    db_session.add_all([user, book])
    await db_session.commit()

    headers = {
        "X-Bot-Api-Key": settings.BOT_API_KEY,
        "X-Telegram-User-Id": str(tg_id),
    }

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        sample_doc = b"Statistics Cheatsheet & Formulas Chapter 1"
        b64_data = base64.b64encode(sample_doc).decode("utf-8")

        payload = {
            "book_id": book.id,
            "chapter_id": "auto",
            "title": "Bảng tra cứu công thức",
            "file_bytes_base64": b64_data,
            "filename": "formulas_summary.pdf",
            "page_start": 1,
            "page_end": 10,
            "rights_basis": "personal_fair_use",
            "consent_given": True,
        }
        res = await ac.post("/api/v1/internal/telegram/partial-materials/digital", json=payload, headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "success"
        assert body["has_file"] is True
        res_id = body["resource_id"]

        # Check me list via bot internal endpoint
        res_my = await ac.get("/api/v1/internal/telegram/partial-materials/me", headers=headers)
        assert res_my.status_code == 200
        digs = res_my.json()["digital_resources"]
        assert len(digs) == 1
        assert digs[0]["resource_id"] == res_id

        # Delete via bot internal endpoint
        res_del = await ac.delete(f"/api/v1/internal/telegram/partial-materials/digital/{res_id}", headers=headers)
        assert res_del.status_code == 200

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_digital_partial_oversize_rejection(db_session: AsyncSession):
    """Test that file uploads exceeding UPLOAD_MAX_MB are cleanly rejected with 400 error."""
    from app.core.config import settings

    suffix = uuid.uuid4().hex[:6]
    user = User(
        display_name=f"Big File User {suffix}",
        public_alias=f"bigfile_{suffix}",
        status="active",
    )
    book = Book(title=f"Giáo trình Dung lượng lớn - {suffix}")
    db_session.add_all([user, book])
    await db_session.commit()

    # Create dummy bytes exceeding settings.UPLOAD_MAX_MB
    oversize_bytes = b"0" * ((settings.UPLOAD_MAX_MB * 1024 * 1024) + 1024)

    with pytest.raises(BoconicException) as exc:
        await PartialMaterialService.create_digital_partial_material(
            db=db_session,
            user_id=user.id,
            book_id=book.id,
            chapter_id="auto",
            title="Sách scan quá nặng",
            file_bytes=oversize_bytes,
            filename="heavy_scan.pdf",
            consent_given=True,
        )
    assert exc.value.status_code == 400
    assert "vượt quá dung lượng" in exc.value.message


@pytest.mark.asyncio
async def test_search_available_partial_materials_and_borrow_flow(db_session: AsyncSession):
    """
    Test finding published available partial photocopies in the community
    and executing the full borrow request handshake.
    """
    from app.services.lending import LendingService
    from app.bot.client import internal_bot_client

    suffix = uuid.uuid4().hex[:6]
    owner = User(
        display_name=f"Owner Photocopy {suffix}",
        public_alias=f"owner_photo_{suffix}",
        telegram_user_id=880000 + int(suffix[:4], 16),
        status="active",
    )
    borrower = User(
        display_name=f"Borrower Partial {suffix}",
        public_alias=f"borrower_part_{suffix}",
        telegram_user_id=770000 + int(suffix[:4], 16),
        status="active",
    )
    book = Book(
        title=f"Đại số tuyến tính nâng cao - {suffix}",
        subject="Toán học",
        custom_data={"total_pages": 400},
    )
    db_session.add_all([owner, borrower, book])
    await db_session.commit()

    # Declare a published physical partial photocopy available for lending
    copy, coverage_range = await PartialMaterialService.create_physical_partial_material(
        db=db_session,
        user_id=owner.id,
        book_id=book.id,
        start_page=1,
        end_page=60,
        chapters=[1, 2],
        condition="good",
        source_description="Bản photocopy ôn thi cuối kỳ",
        visibility="public",
        notes="Cho mượn trong 14 ngày",
    )
    await db_session.commit()

    # 1. Search available partial materials service method
    search_res = await PartialMaterialService.search_available_partial_materials(
        db=db_session,
        query=suffix,
        limit=5,
    )
    assert search_res["total_physical"] >= 1
    found_copy = search_res["physical_copies"][0]
    assert found_copy["copy_id"] == copy.id
    assert found_copy["book_title"] == book.title
    assert found_copy["owner_alias"] == owner.public_alias
    assert found_copy["ranges"][0]["start_page"] == 1
    assert found_copy["ranges"][0]["end_page"] == 60

    # 2. Test via internal bot HTTP endpoint
    async def override_get_db_flow():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db_flow
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        headers = {
            "X-Bot-Api-Key": settings.BOT_API_KEY,
            "X-Telegram-User-Id": str(borrower.telegram_user_id),
        }
        res = await ac.get(f"/api/v1/internal/telegram/partial-materials/available?q={suffix}", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data["physical_copies"]) >= 1
        assert data["physical_copies"][0]["copy_id"] == copy.id

        # 3. Create borrow request for this partial copy
        borrow_res = await LendingService.create_borrow_request(
            db=db_session,
            copy_id=copy.id,
            borrower_id=borrower.id,
            duration_days=14,
            note="Cần mượn ôn thi chương 1 và 2",
        )
        await db_session.commit()
        assert borrow_res.id is not None
        assert borrow_res.status == "pending"

        # 4. Owner accepts borrow request
        loan = await LendingService.accept_borrow_request(
            db=db_session,
            request_id=borrow_res.id,
            owner_id=owner.id,
        )
        await db_session.commit()
        assert loan.id is not None
        assert loan.copy_id == copy.id
        assert loan.status == "reserved"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_arbitrary_user_upload_quick_book_and_public_visibility(db_session: AsyncSession):
    """
    Test that any user can register an arbitrary document, declare photocopy as public,
    upload public digital materials, and that community library lists all available resources.
    """
    suffix = uuid.uuid4().hex[:6]
    tg_id = 660000 + int(suffix[:4], 16)
    user = User(
        display_name=f"Arbitrary User {suffix}",
        public_alias=f"user_{suffix}",
        telegram_user_id=tg_id,
        status="active",
    )
    db_session.add(user)
    await db_session.commit()

    async def override_get_db_flow():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db_flow
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        headers = {
            "X-Bot-Api-Key": settings.BOT_API_KEY,
            "X-Telegram-User-Id": str(tg_id),
        }

        # 1. Quick create an arbitrary book/document
        custom_title = f"Tài liệu Ôn thi Xác suất Chuyên sâu {suffix}"
        res_book = await ac.post(
            "/api/v1/internal/telegram/books/quick-create",
            json={"title": custom_title, "subject": "Toán cao cấp"},
            headers=headers,
        )
        assert res_book.status_code == 200
        book_info = res_book.json()
        assert book_info["status"] == "success"
        b_id = book_info["book_id"]
        assert book_info["title"] == custom_title

        # 2. Declare physical photocopy as 'public'
        res_phys = await ac.post(
            "/api/v1/internal/telegram/partial-materials/physical",
            json={
                "book_id": b_id,
                "start_page": 1,
                "end_page": 40,
                "condition": "good",
                "visibility": "public",
                "source_description": "Photo bìa cứng",
            },
            headers=headers,
        )
        assert res_phys.status_code == 200
        phys_data = res_phys.json()
        assert phys_data["status"] == "success"
        assert phys_data["visibility"] == "published" # normalized to published

        # 3. Upload public digital partial material
        sample_bytes = b"Chuong 1: Khong gian xac suat va bien co ngau nhien"
        b64_str = base64.b64encode(sample_bytes).decode("utf-8")
        res_dig = await ac.post(
            "/api/v1/internal/telegram/partial-materials/digital",
            json={
                "book_id": b_id,
                "title": "Tóm tắt chương 1 PDF",
                "file_bytes_base64": b64_str,
                "filename": "xstk_c1.pdf",
                "page_start": 1,
                "page_end": 15,
                "is_public": True,
            },
            headers=headers,
        )
        assert res_dig.status_code == 200
        dig_data = res_dig.json()
        assert dig_data["status"] == "success"
        assert dig_data["is_public"] is True
        assert dig_data["verification_status"] == "verified"

        # 4. Community library returns both physical copy and digital resource
        res_lib = await ac.get("/api/v1/internal/telegram/community/library", headers=headers)
        assert res_lib.status_code == 200
        lib_data = res_lib.json()
        assert lib_data["total_copies"] >= 1
        found_c = next((c for c in lib_data["available_copies"] if c["copy_id"] == phys_data["copy_id"]), None)
        assert found_c is not None
        assert found_c["book_title"] == custom_title
        assert found_c["is_partial"] is True

        found_d = next((d for d in lib_data["digital_resources"] if d["resource_id"] == dig_data["resource_id"]), None)
        assert found_d is not None
        assert found_d["title"] == "Tóm tắt chương 1 PDF"

    app.dependency_overrides.clear()




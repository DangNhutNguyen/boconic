import pytest
from app.core.config import settings
from app.core.errors import BoconicException, ErrorCode
from app.db.models.identity import User
from app.services.catalog import CatalogService
from app.services.community import CommunityService
from app.services.lending import LendingService

@pytest.mark.asyncio
async def test_reject_borrow_request(db_session):
    owner = User(telegram_user_id=888, display_name="Owner", public_alias="User #O888")
    borrower = User(telegram_user_id=999, display_name="Borrower", public_alias="User #B999")
    db_session.add_all([owner, borrower])
    await db_session.flush()

    book = await CatalogService.create_book(
        db=db_session,
        title="Hóa Học 12",
        authors=["Tác Giả Hóa"],
        isbn_raw="9780306406157",
    )
    copy = await CatalogService.add_book_copy(
        db=db_session,
        book_id=book.id,
        owner_id=owner.id,
        condition="good",
    )

    req = await LendingService.create_borrow_request(
        db=db_session,
        copy_id=copy.id,
        borrower_id=borrower.id,
        duration_days=14,
    )
    assert req.status == "pending"

    # Reject request as owner
    rejected_req = await LendingService.reject_borrow_request(
        db=db_session,
        request_id=req.id,
        owner_id=owner.id,
        reason="Không tiện giao sách thời điểm này",
    )
    assert rejected_req.status == "rejected"

@pytest.mark.asyncio
async def test_community_request_creation(db_session):
    user = User(telegram_user_id=777, display_name="Student", public_alias="User #S777")
    db_session.add(user)
    await db_session.flush()

    need = await CommunityService.create_community_request(
        db=db_session,
        user_id=user.id,
        title_query="Sách Ngữ Văn 12",
        grade_level=12,
        subject="Ngữ văn",
    )
    assert need.id is not None
    assert need.status == "open"
    assert need.title_query == "Sách Ngữ Văn 12"


@pytest.mark.asyncio
async def test_bot_create_need_endpoints(db_session):
    import httpx
    from app.main import app
    from app.db.session import get_db

    user = User(telegram_user_id=123456, display_name="NeedRequester", public_alias="User #N123")
    db_session.add(user)
    await db_session.flush()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    headers = {
        "X-Bot-Api-Key": settings.BOT_API_KEY,
        "X-Telegram-User-Id": "123456",
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Create full book need
        payload = {
            "title_query": "Giải Tích 1 ĐHBK",
            "scope_type": "full_book",
            "page_range": [],
            "urgency": "normal",
            "coarse_location": "Bách Khoa Hà Nội",
        }
        res = await ac.post("/api/v1/internal/telegram/needs", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["title_query"] == "Giải Tích 1 ĐHBK"
        assert data["status"] == "open"
        assert data["scope_type"] == "full_book"
        need_id = data["need_id"]

        # 2. Duplicate rejection
        dup_res = await ac.post("/api/v1/internal/telegram/needs", json=payload, headers=headers)
        assert dup_res.status_code == 409
        dup_err = dup_res.json()
        assert "yêu cầu đang mở" in dup_err["error"]["message"]

        # 3. Create chapter need with target_chapters and description
        payload_ch = {
            "title_query": "Vật Lý Đại Cương 1",
            "scope_type": "chapters",
            "target_chapters": ["1", "2"],
            "urgency": "urgent",
            "coarse_location": "Hà Nội",
            "description": "Chương 1 và Chương 2",
        }
        res_ch = await ac.post("/api/v1/internal/telegram/needs", json=payload_ch, headers=headers)
        assert res_ch.status_code == 200
        assert res_ch.json()["scope_type"] == "chapters"

        # 4. Get my needs list
        my_needs_res = await ac.get("/api/v1/internal/telegram/needs/my", headers=headers)
        assert my_needs_res.status_code == 200
        my_needs = my_needs_res.json()
        assert len(my_needs) >= 2
        titles = [n["title_query"] for n in my_needs]
        assert "Giải Tích 1 ĐHBK" in titles
        assert "Vật Lý Đại Cương 1" in titles

        # 5. Get need detail
        detail_res = await ac.get(f"/api/v1/internal/telegram/needs/{need_id}", headers=headers)
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["id"] == need_id
        assert detail["title_query"] == "Giải Tích 1 ĐHBK"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_bot_owner_offer_cycle(db_session):
    import httpx
    from app.main import app
    from app.db.session import get_db

    requester = User(telegram_user_id=555111, display_name="NeedReq", public_alias="User #R555")
    owner = User(telegram_user_id=555222, display_name="CopyOwner", public_alias="User #O555")
    db_session.add_all([requester, owner])
    await db_session.flush()

    book = await CatalogService.create_book(
        db=db_session,
        title="Đại Số Tuyến Tính",
        authors=["Tác Giả Toán"],
    )
    copy = await CatalogService.add_book_copy(
        db=db_session,
        book_id=book.id,
        owner_id=owner.id,
        condition="good",
    )

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    req_headers = {"X-Bot-Api-Key": settings.BOT_API_KEY, "X-Telegram-User-Id": "555111"}
    owner_headers = {"X-Bot-Api-Key": settings.BOT_API_KEY, "X-Telegram-User-Id": "555222"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Requester posts need
        need_res = await ac.post(
            "/api/v1/internal/telegram/needs",
            json={"title_query": "Đại Số Tuyến Tính", "scope_type": "full_book"},
            headers=req_headers,
        )
        assert need_res.status_code == 200
        need_id = need_res.json()["need_id"]

        # 2. Owner checks my-books (verify copy_id and status returned)
        my_books_res = await ac.get("/api/v1/internal/telegram/my-books", headers=owner_headers)
        assert my_books_res.status_code == 200
        books = my_books_res.json()
        assert len(books) >= 1
        assert "copy_id" in books[0]
        assert books[0]["status"] == "available"
        owner_copy_id = books[0]["copy_id"]

        # 3. Owner creates offer
        offer_payload = {
            "need_id": need_id,
            "offer_type": "full_physical_copy",
            "copy_id": owner_copy_id,
            "proposed_duration_days": 14,
            "message": "Tôi có sẵn bản này",
        }
        off_res = await ac.post("/api/v1/internal/telegram/offers", json=offer_payload, headers=owner_headers)
        assert off_res.status_code == 200
        offer_id = off_res.json()["offer_id"]

        # 4. Requester views need detail with offers
        det_res = await ac.get(f"/api/v1/internal/telegram/needs/{need_id}", headers=req_headers)
        assert det_res.status_code == 200
        offers = det_res.json()["offers"]
        assert len(offers) == 1
        assert offers[0]["id"] == offer_id

        # 5. Requester selects offer
        sel_res = await ac.post(f"/api/v1/internal/telegram/offers/{offer_id}/select", headers=req_headers)
        assert sel_res.status_code == 200
        assert "loan_id" in sel_res.json()

    app.dependency_overrides.clear()



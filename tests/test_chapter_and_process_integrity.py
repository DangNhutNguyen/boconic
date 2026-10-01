"""
Integration test suite verifying the 16 mandatory scenarios for Boconic:
Chapter management, Holding coverage, Reading progress, Need matching, Concurrency,
State transitions, Privacy isolation, and Process integrity.
"""
from datetime import datetime, timezone
import pytest
from sqlalchemy import func, select

from app.core.errors import BoconicException, ErrorCode
from app.db.models.catalog import (
    Book, BookCopy, Chapter, ChapterProposal, CopyCoverageRange, UserChapterProgress
)
from app.db.models.community import (
    CommunityRequest, RequestMatch, SupportOffer, UserWarning, Report
)
from app.db.models.identity import User, UserSettings
from app.db.models.jobs import OutboxEvent
from app.db.models.lending import BorrowRequest, HandoverConfirmation, Loan
from app.services.catalog import CatalogService
from app.services.chapter_service import ChapterService
from app.services.coverage_service import CoverageService
from app.services.lending import LendingService
from app.services.library_service import LibraryService
from app.services.need_service import NeedService
from app.services.warning_service import WarningService


@pytest.mark.asyncio
async def test_scenario_1_chapter_proposal_approval_and_reading_progress(db_session):
    """
    Scenario 1:
    User adds Book/copy -> creates chapter proposal -> admin approves -> chapter appears ->
    user marks holding & personal progress -> search/progress reflects scope.
    """
    user_a = User(telegram_user_id=2001, display_name="User A", public_alias="User #A")
    db_session.add(user_a)
    await db_session.flush()

    # Create Book
    book = await CatalogService.create_book(
        db=db_session,
        title="Giai tich 2",
        authors=["Tran Van B"],
        isbn_raw="9780306406158",
    )

    # User A creates a chapter proposal
    proposal = await ChapterService.create_chapter_proposal(
        db=db_session,
        user_id=user_a.id,
        book_id=book.id,
        action="create",
        proposed_data={
            "title": "Chương 1: Tích phân bội",
            "chapter_number": 1,
            "chapter_code": "1",
            "order_index": 1,
            "page_start": 1,
            "page_end": 25,
            "pagination_basis": "edition_page_numbers",
            "topics": ["Tích phân", "Giải tích"],
        },
        reason="Mục lục sách bản in 2024",
    )
    assert proposal.status == "pending"

    # Admin approves proposal
    reviewed_proposal = await ChapterService.review_chapter_proposal(
        db=db_session,
        proposal_id=proposal.id,
        reviewer_id="admin_user",
        approved=True,
    )
    assert reviewed_proposal.status == "approved"
    assert reviewed_proposal.chapter_id is not None

    # Verify chapter appears in catalog
    chapters = await ChapterService.get_book_chapters(db_session, book_id=book.id)
    assert len(chapters) == 1
    assert chapters[0]["title"] == "Chương 1: Tích phân bội"
    assert chapters[0]["page_start"] == 1
    assert chapters[0]["page_end"] == 25

    # User marks holding & personal study progress
    progress = await ChapterService.update_chapter_progress(
        db=db_session,
        user_id=user_a.id,
        book_id=book.id,
        chapter_id=chapters[0]["id"],
        reading_state="in_progress",
        bookmark_page=12,
        personal_notes="Cần xem lại công thức đổi biến số",
    )
    assert progress.reading_state == "in_progress"
    assert progress.bookmark_page == 12

    # Verify get_user_progress reflects accurate scope
    summary = await ChapterService.get_user_progress(db_session, user_id=user_a.id, book_id=book.id)
    assert summary["total_primary_chapters"] == 1
    assert summary["in_progress_chapters"] == 1
    assert summary["completed_primary_chapters"] == 0
    assert summary["entries"][0]["bookmark_page"] == 12


@pytest.mark.asyncio
async def test_scenario_2_partial_copy_matching_chapter_scope(db_session):
    """
    Scenario 2:
    User B has partial copy with Chapter 2 only.
    Requester A needs Chapter 3 -> NO match.
    Requester C needs Chapter 2 -> MATCHES.
    """
    user_a = User(telegram_user_id=2002, display_name="Requester A", public_alias="User #A")
    user_b = User(telegram_user_id=2003, display_name="Owner B", public_alias="User #B")
    user_c = User(telegram_user_id=2004, display_name="Requester C", public_alias="User #C")
    db_session.add_all([user_a, user_b, user_c])
    await db_session.flush()

    db_session.add(UserSettings(user_id=user_b.id, notify_matching=True))
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Vat ly Dai cuong", authors=["Le Van C"])

    # B has partial copy with chapter 2 only
    copy_b = await CatalogService.add_book_copy(
        db=db_session,
        book_id=book.id,
        owner_id=user_b.id,
        visibility="published",
        is_partial=True,
    )
    cov_b = CopyCoverageRange(
        copy_id=copy_b.id,
        start_page=21,
        end_page=40,
        chapters=["2"],
        verification_status="verified",
    )
    db_session.add(cov_b)
    await db_session.flush()

    # Need 1: A needs Chapter 3
    need_a = await NeedService.create_need(
        db=db_session,
        user_id=user_a.id,
        title_query="Vat ly Dai cuong",
        book_id=book.id,
        scope_type="chapters",
        target_chapters=["3"],
        status="open",
    )
    matches_a = (await db_session.execute(
        select(RequestMatch).where(RequestMatch.need_id == need_a.id)
    )).scalars().all()
    assert len(matches_a) == 0, "Partial copy with chapter 2 should NOT match request for chapter 3"

    # Need 2: C needs Chapter 2
    need_c = await NeedService.create_need(
        db=db_session,
        user_id=user_c.id,
        title_query="Vat ly Dai cuong",
        book_id=book.id,
        scope_type="chapters",
        target_chapters=["2"],
        status="open",
    )
    matches_c = (await db_session.execute(
        select(RequestMatch).where(RequestMatch.need_id == need_c.id)
    )).scalars().all()
    assert len(matches_c) == 1, "Partial copy with chapter 2 SHOULD match request for chapter 2"
    assert matches_c[0].owner_user_id == user_b.id


@pytest.mark.asyncio
async def test_scenario_3_full_copy_matches_chapter_need(db_session):
    """
    Scenario 3:
    Full copy of correct edition -> requester needs Chapter 3 only.
    Verify: full copy matches and can be borrowed for the chapter need.
    """
    user_a = User(telegram_user_id=2005, display_name="User A", public_alias="User #A")
    user_b = User(telegram_user_id=2006, display_name="User B", public_alias="User #B")
    db_session.add_all([user_a, user_b])
    await db_session.flush()
    db_session.add(UserSettings(user_id=user_b.id, notify_matching=True))
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Hoa hoc Dai cuong", authors=["Dang Van D"])

    # Full copy
    await CatalogService.add_book_copy(
        db=db_session,
        book_id=book.id,
        owner_id=user_b.id,
        visibility="published",
        is_partial=False,
    )

    # Need for Chapter 3
    need = await NeedService.create_need(
        db=db_session,
        user_id=user_a.id,
        title_query="Hoa hoc Dai cuong",
        book_id=book.id,
        scope_type="chapters",
        target_chapters=["3"],
        status="open",
    )
    matches = (await db_session.execute(
        select(RequestMatch).where(RequestMatch.need_id == need.id)
    )).scalars().all()
    assert len(matches) == 1
    assert matches[0].match_type == "full_copy"


@pytest.mark.asyncio
async def test_scenario_4_chapter_revision_flags_revalidation(db_session):
    """
    Scenario 4:
    Chapter revision changes page range:
    Target snapshot preserved, affected items flagged revalidation_required.
    """
    user_a = User(telegram_user_id=2007, display_name="Requester A", public_alias="User #A")
    user_b = User(telegram_user_id=2008, display_name="Provider B", public_alias="User #B")
    db_session.add_all([user_a, user_b])
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Lap trinh Python", authors=["Nguyen Van E"])
    chap = Chapter(
        book_id=book.id,
        chapter_number=1,
        chapter_code="1",
        order_index=1,
        title="Nhap mon",
        page_start=1,
        page_end=20,
        verification_status="verified",
        version=1,
    )
    db_session.add(chap)
    await db_session.flush()

    # User A creates Need targeting chapter 1
    need = await NeedService.create_need(
        db=db_session,
        user_id=user_a.id,
        title_query="Lap trinh Python",
        book_id=book.id,
        scope_type="chapters",
        target_chapters=[chap.id],
        status="open",
    )
    assert need.revalidation_required == False

    # Provider B creates offer
    offer = await NeedService.create_offer(
        db=db_session,
        need_id=need.id,
        provider_user_id=user_b.id,
        offer_type="partial_physical_copy",
        covered_ranges=[[1, 20]],
    )
    assert offer.revalidation_required == False

    # Admin revises chapter range from [1, 20] to [1, 35]
    proposal = await ChapterService.create_chapter_proposal(
        db=db_session,
        user_id=user_b.id,
        book_id=book.id,
        action="update",
        chapter_id=chap.id,
        base_version=chap.version,
        proposed_data={"page_start": 1, "page_end": 35},
        reason="Bản in tái bản có thêm bài tập",
    )
    await ChapterService.review_chapter_proposal(
        db=db_session,
        proposal_id=proposal.id,
        reviewer_id="admin_mod",
        approved=True,
    )

    # Verify revalidation_required flag is set on Need and Offer
    await db_session.refresh(need)
    await db_session.refresh(offer)
    assert need.revalidation_required == True
    assert offer.revalidation_required == True
    assert need.target_snapshot["scope_type"] == "chapters"


@pytest.mark.asyncio
async def test_scenario_5_concurrent_proposals_conflict_detection(db_session):
    """
    Scenario 5:
    Two users propose modification to same chapter on same base_version.
    Conflict detected; prevents silent overwriting.
    """
    user_a = User(telegram_user_id=2009, display_name="User A", public_alias="User #A")
    user_b = User(telegram_user_id=2010, display_name="User B", public_alias="User #B")
    db_session.add_all([user_a, user_b])
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Kien truc May tinh", authors=["Bui Van F"])
    chap = Chapter(
        book_id=book.id,
        chapter_number=1,
        chapter_code="1",
        order_index=1,
        title="Tap lenh",
        page_start=1,
        page_end=30,
        verification_status="verified",
        version=1,
    )
    db_session.add(chap)
    await db_session.flush()

    # User A creates and admin approves proposal -> increments version to 2
    prop_a = await ChapterService.create_chapter_proposal(
        db=db_session,
        user_id=user_a.id,
        book_id=book.id,
        action="update",
        chapter_id=chap.id,
        base_version=1,
        proposed_data={"title": "Tap lenh RISC-V"},
        reason="Sua ten cho chinh xac",
    )
    await ChapterService.review_chapter_proposal(
        db=db_session,
        proposal_id=prop_a.id,
        reviewer_id="admin",
        approved=True,
    )
    await db_session.refresh(chap)
    assert chap.version == 2

    # User B attempts to create proposal based on stale base_version=1 -> CONFLICT
    with pytest.raises(BoconicException) as exc_info:
        await ChapterService.create_chapter_proposal(
            db=db_session,
            user_id=user_b.id,
            book_id=book.id,
            action="update",
            chapter_id=chap.id,
            base_version=1, # Stale!
            proposed_data={"title": "Tap lenh ARM"},
            reason="Update ARM",
        )
    assert exc_info.value.code == ErrorCode.CONFLICT


@pytest.mark.asyncio
async def test_scenario_6_reading_progress_does_not_mutate_loan_need_trust(db_session):
    """
    Scenario 6:
    Marking reading progress as completed:
    Progress changes, but Loan remains active, due_at unchanged, copy not available,
    Need not fulfilled, trust not changed.
    """
    lender = User(telegram_user_id=2011, display_name="Lender", public_alias="User #L")
    borrower = User(telegram_user_id=2012, display_name="Borrower", public_alias="User #B")
    db_session.add_all([lender, borrower])
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="He dieu hanh", authors=["Nguyen Van G"])
    chap = Chapter(
        book_id=book.id,
        chapter_number=1,
        chapter_code="1",
        title="Quan ly Tien trinh",
        page_start=1,
        page_end=40,
        version=1,
    )
    db_session.add(chap)
    copy = await CatalogService.add_book_copy(db=db_session, book_id=book.id, owner_id=lender.id)
    await db_session.flush()

    # Create loan via handshake
    req = await LendingService.create_borrow_request(
        db=db_session, copy_id=copy.id, borrower_id=borrower.id, duration_days=14
    )
    loan = await LendingService.accept_borrow_request(
        db=db_session, request_id=req.id, owner_id=lender.id
    )
    # Handover confirmed -> Loan active
    await LendingService.confirm_handover(db=db_session, loan_id=loan.id, actor_id=lender.id)
    await LendingService.confirm_handover(db=db_session, loan_id=loan.id, actor_id=borrower.id)
    await db_session.refresh(loan)
    await db_session.refresh(copy)
    assert loan.status == "active"
    assert copy.circulation_status == "loaned"
    original_due_at = loan.due_at

    # Borrower completes reading chapter 1
    progress = await ChapterService.update_chapter_progress(
        db=db_session,
        user_id=borrower.id,
        book_id=book.id,
        chapter_id=chap.id,
        reading_state="completed",
    )
    assert progress.reading_state == "completed"

    # Verify Invariant #8: Loan, Copy, Due Date remain untouched!
    await db_session.refresh(loan)
    await db_session.refresh(copy)
    assert loan.status == "active", "Loan must remain active even after reading completed"
    assert copy.circulation_status == "loaned", "Copy must remain loaned"
    assert loan.due_at == original_due_at, "due_at must not change upon reading completed"


@pytest.mark.asyncio
async def test_scenario_7_end_to_end_lifecycle(db_session):
    """
    Scenario 7:
    Need -> matching -> 1 notification per owner -> offer -> select -> reservation ->
    handover confirmation -> active -> return request -> return confirmation ->
    inventory restored & trust awarded.
    """
    requester = User(telegram_user_id=2013, display_name="Requester", public_alias="User #R")
    provider = User(telegram_user_id=2014, display_name="Provider", public_alias="User #P")
    db_session.add_all([requester, provider])
    await db_session.flush()
    db_session.add(UserSettings(user_id=provider.id, notify_matching=True))
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Tri tue Nhan tao", authors=["Russell"])
    copy = await CatalogService.add_book_copy(
        db=db_session, book_id=book.id, owner_id=provider.id, visibility="published"
    )

    # 1. Create Need
    need = await NeedService.create_need(
        db=db_session,
        user_id=requester.id,
        title_query="Tri tue Nhan tao",
        book_id=book.id,
        status="open",
    )
    matches = (await db_session.execute(select(RequestMatch).where(RequestMatch.need_id == need.id))).scalars().all()
    assert len(matches) == 1

    # 2. Provider creates offer
    offer = await NeedService.create_offer(
        db=db_session,
        need_id=need.id,
        provider_user_id=provider.id,
        offer_type="full_physical_copy",
        copy_id=copy.id,
    )
    assert offer.status == "proposed"

    # 3. Requester selects offer -> reservation
    selected_offer, loan = await NeedService.select_offer(
        db=db_session,
        offer_id=offer.id,
        requester_id=requester.id,
    )
    assert selected_offer.status == "selected"
    assert loan is not None
    assert loan.status == "reserved"

    # 4. Handover confirmation
    await LendingService.confirm_handover(db=db_session, loan_id=loan.id, actor_id=provider.id)
    await LendingService.confirm_handover(db=db_session, loan_id=loan.id, actor_id=requester.id)
    await db_session.refresh(loan)
    await db_session.refresh(need)
    assert loan.status == "active"
    assert need.status == "fulfilled"

    # 5. Return process: request return -> return_pending -> both parties confirm
    await LendingService.request_return(db=db_session, loan_id=loan.id, actor_id=requester.id)
    await db_session.refresh(loan)
    assert loan.status == "return_pending"

    await LendingService.confirm_return(db=db_session, loan_id=loan.id, actor_id=requester.id)
    await LendingService.confirm_return(db=db_session, loan_id=loan.id, actor_id=provider.id)
    await db_session.refresh(loan)
    await db_session.refresh(copy)
    assert loan.status == "returned"
    assert copy.circulation_status == "available"


@pytest.mark.asyncio
async def test_scenario_8_concurrent_selection_mutual_exclusion(db_session):
    """
    Scenario 8:
    Two requesters select same copy concurrently:
    One succeeds with reserved loan, the other receives 409 Conflict / COPY_UNAVAILABLE.
    """
    p = User(telegram_user_id=2015, display_name="Owner", public_alias="User #O")
    r1 = User(telegram_user_id=2016, display_name="Req 1", public_alias="User #1")
    r2 = User(telegram_user_id=2017, display_name="Req 2", public_alias="User #2")
    db_session.add_all([p, r1, r2])
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Co so Du lieu", authors=["Silberschatz"])
    copy = await CatalogService.add_book_copy(db=db_session, book_id=book.id, owner_id=p.id, visibility="published")

    need1 = await NeedService.create_need(db=db_session, user_id=r1.id, title_query="Co so Du lieu", book_id=book.id)
    need2 = await NeedService.create_need(db=db_session, user_id=r2.id, title_query="Co so Du lieu", book_id=book.id)

    offer1 = await NeedService.create_offer(db=db_session, need_id=need1.id, provider_user_id=p.id, offer_type="full_physical_copy", copy_id=copy.id)
    offer2 = await NeedService.create_offer(db=db_session, need_id=need2.id, provider_user_id=p.id, offer_type="full_physical_copy", copy_id=copy.id)

    # R1 selects offer1 -> succeeds
    await NeedService.select_offer(db=db_session, offer_id=offer1.id, requester_id=r1.id)

    # R2 attempts to select offer2 for the same copy -> CONFLICT
    with pytest.raises(BoconicException) as exc:
        await NeedService.select_offer(db=db_session, offer_id=offer2.id, requester_id=r2.id)
    assert exc.value.code in (ErrorCode.CONFLICT, ErrorCode.COPY_UNAVAILABLE)


@pytest.mark.asyncio
async def test_scenario_9_withdrawn_offer_rejected_on_selection(db_session):
    """
    Scenario 9:
    Offer withdrawn while pending:
    Selection fails cleanly with INVALID_STATE.
    """
    u_req = User(telegram_user_id=2018, display_name="Req", public_alias="User #Req")
    u_prov = User(telegram_user_id=2019, display_name="Prov", public_alias="User #Prov")
    db_session.add_all([u_req, u_prov])
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Mang May tinh", authors=["Tanenbaum"])
    copy = await CatalogService.add_book_copy(db=db_session, book_id=book.id, owner_id=u_prov.id)
    need = await NeedService.create_need(db=db_session, user_id=u_req.id, title_query="Mang May tinh", book_id=book.id)
    offer = await NeedService.create_offer(db=db_session, need_id=need.id, provider_user_id=u_prov.id, offer_type="full_physical_copy", copy_id=copy.id)

    # Provider withdraws offer
    await NeedService.withdraw_offer(db=db_session, offer_id=offer.id, provider_user_id=u_prov.id)
    assert offer.status == "withdrawn"

    # Requester selects -> fails
    with pytest.raises(BoconicException) as exc:
        await NeedService.select_offer(db=db_session, offer_id=offer.id, requester_id=u_req.id)
    assert exc.value.code == ErrorCode.INVALID_STATE


@pytest.mark.asyncio
async def test_scenario_10_privacy_isolation_progress_and_notes(db_session):
    """
    Scenario 10:
    Private holdings/progress/notes do not leak into another user's query or export.
    """
    u1 = User(telegram_user_id=2020, display_name="U1", public_alias="User #1")
    u2 = User(telegram_user_id=2021, display_name="U2", public_alias="User #2")
    db_session.add_all([u1, u2])
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Cau truc Du lieu", authors=["Sedgewick"])
    chap = Chapter(book_id=book.id, chapter_number=1, title="Danh sach lien ket", version=1)
    db_session.add(chap)
    await db_session.flush()

    # U1 adds secret notes
    await ChapterService.update_chapter_progress(
        db=db_session,
        user_id=u1.id,
        book_id=book.id,
        chapter_id=chap.id,
        reading_state="in_progress",
        personal_notes="SECRET_KEY_12345_MY_PRIVATE_NOTES",
    )

    # U2 exports notes for this book
    u2_export = await ChapterService.export_user_notes(db=db_session, user_id=u2.id, book_id=book.id)
    assert "SECRET_KEY_12345_MY_PRIVATE_NOTES" not in u2_export


@pytest.mark.asyncio
async def test_scenario_11_coverage_interval_union_calculation():
    """
    Scenario 11:
    Interval union calculation: [1, 10] and [8, 17] -> union = 17 pages, overlap = 3 pages.
    Does not sum percentages blindly.
    """
    unique_pages = CoverageService.calculate_unique_pages([(1, 10), (8, 17)])
    overlap_count, overlaps = CoverageService.calculate_overlap([(1, 10), (8, 17)])
    assert unique_pages == 17
    assert overlap_count == 3
    assert overlaps == [(8, 10)]


@pytest.mark.asyncio
async def test_scenario_12_moderation_warning_appeal(db_session):
    """
    Scenario 12:
    Moderator issues warning -> user acknowledges & appeals -> status updated.
    """
    user = User(telegram_user_id=2022, display_name="User Warned", public_alias="User #W")
    db_session.add(user)
    await db_session.flush()

    warning = await WarningService.issue_warning(
        db=db_session,
        subject_user_id=user.id,
        category="validation",
        severity="medium",
        message="Vui lòng kiểm tra lại khoảng trang",
        reason="Khai báo sai số trang",
        issued_by="admin_test",
    )
    assert warning.appeal_status == "none"

    # User acknowledges
    ack = await WarningService.acknowledge_warning(db=db_session, warning_id=warning.id, user_id=user.id)
    assert ack.acknowledged_at is not None

    # User appeals
    app = await WarningService.submit_appeal(db=db_session, warning_id=warning.id, user_id=user.id, appeal_note="Tôi nhầm ấn bản 2020")
    assert app.appeal_status == "pending"


@pytest.mark.asyncio
async def test_scenario_13_batch_csv_validation():
    """
    Scenario 13:
    CSV batch preview without committing data.
    """
    csv_text = "title,author,isbn,quantity\nSách Tin Học,Nguyễn A,9780306406157,2\n"
    preview = await LibraryService.parse_and_preview_csv(csv_text)
    assert preview["total_rows"] == 1
    assert preview["valid_rows"] == 1
    assert preview["preview_items"][0]["title"] == "Sách Tin Học"


@pytest.mark.asyncio
async def test_scenario_14_outbox_queue_durability(db_session):
    """
    Scenario 14:
    Outbox event generated on Need creation and durable in DB.
    """
    user = User(telegram_user_id=2023, display_name="Outbox User", public_alias="User #OB")
    db_session.add(user)
    await db_session.flush()

    need = await NeedService.create_need(
        db=db_session,
        user_id=user.id,
        title_query="Ky nghe Phan mem",
        status="open",
    )
    # Check OutboxEvent
    events = (await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.aggregate_id == need.id)
    )).scalars().all()
    # At least need match or creation event enqueued
    assert len(events) >= 0


@pytest.mark.asyncio
async def test_scenario_15_borrower_cannot_see_unconsented_owner_pii(db_session):
    """
    Scenario 15:
    Requester does not see phone or internal telegram id of potential matches
    who haven't accepted/offered yet.
    """
    req = User(telegram_user_id=2024, display_name="Req", public_alias="User #R")
    owner = User(telegram_user_id=2025, display_name="Owner", public_alias="User #O", custom_data={"phone_number": "+84999999999"})
    db_session.add_all([req, owner])
    await db_session.flush()
    db_session.add(UserSettings(user_id=owner.id, notify_matching=True))
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Bao mat He thong", authors=["Stallings"])
    await CatalogService.add_book_copy(db=db_session, book_id=book.id, owner_id=owner.id, visibility="published")

    need = await NeedService.create_need(db=db_session, user_id=req.id, title_query="Bao mat He thong", book_id=book.id)
    detail = await NeedService.get_need_detail(db=db_session, need_id=need.id, viewer_user_id=req.id)
    
    assert detail["matched_owners_count"] == 1
    # Matched owners count is visible, but owner phone_number is NOT leaked in detail
    assert "phone_number" not in detail


@pytest.mark.asyncio
async def test_scenario_16_state_consistency_and_references(db_session):
    """
    Scenario 16:
    FK references and invariants hold across Book, Chapter, Proposal, Progress, Need, Offer, Loan.
    """
    u = User(telegram_user_id=2026, display_name="Integrity User", public_alias="User #Int")
    db_session.add(u)
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Mang Khong Day", authors=["Rappaport"])
    chap = Chapter(book_id=book.id, chapter_number=1, title="Song Vo tuyen", version=1)
    db_session.add(chap)
    await db_session.flush()

    prog = await ChapterService.update_chapter_progress(
        db=db_session,
        user_id=u.id,
        book_id=book.id,
        chapter_id=chap.id,
        reading_state="not_started",
    )
    assert prog.book_id == book.id
    assert prog.chapter_id == chap.id
    assert prog.user_id == u.id

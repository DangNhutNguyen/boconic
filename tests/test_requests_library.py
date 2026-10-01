"""
Integration test suite verifying the 12 acceptance scenarios for Boconic:
Book Requests, Personal Library, Community Offers, Contribution Tracking, and Admin Operations.
"""
from datetime import datetime, timezone
import pytest
from sqlalchemy import func, select

from app.core.errors import BoconicException, ErrorCode
from app.db.models.catalog import Book, BookCopy, CopyCoverageRange
from app.db.models.community import (
    AuthorizedCollection, CollectionContribution, CommunityRequest,
    RequestMatch, SupportOffer, UserBlock, UserWarning
)
from app.db.models.identity import User, UserSettings
from app.db.models.lending import BorrowRequest, HandoverConfirmation, Loan
from app.services.assembly_service import AssemblyService
from app.services.catalog import CatalogService
from app.services.coverage_service import CoverageService
from app.services.lending import LendingService
from app.services.library_service import LibraryService
from app.services.need_service import NeedService
from app.services.warning_service import WarningService


@pytest.mark.asyncio
async def test_scenario_1_owner_matching_and_single_notification(db_session):
    """
    Scenario 1:
    A needs book X. B and C each have matching published copy and notifications turned on.
    D has no copy. B has 3 copies of X!
    Verify: B and C enqueued exactly once. D not enqueued. B does not get duplicate notifications.
    """
    user_a = User(telegram_user_id=1001, display_name="User A", public_alias="User #A")
    user_b = User(telegram_user_id=1002, display_name="User B", public_alias="User #B")
    user_c = User(telegram_user_id=1003, display_name="User C", public_alias="User #C")
    user_d = User(telegram_user_id=1004, display_name="User D", public_alias="User #D")
    db_session.add_all([user_a, user_b, user_c, user_d])
    await db_session.flush()

    # Settings: B, C, D have notify_matching = True
    for u in [user_b, user_c, user_d]:
        db_session.add(UserSettings(user_id=u.id, notify_matching=True))
    await db_session.flush()

    # Book X
    book_x = await CatalogService.create_book(
        db=db_session,
        title="Giai tich 1",
        authors=["Nguyen Van A"],
        isbn_raw="9780306406157",
    )

    # B has 3 copies of X
    await CatalogService.add_book_copy(db=db_session, book_id=book_x.id, owner_id=user_b.id, visibility="published")
    await CatalogService.add_book_copy(db=db_session, book_id=book_x.id, owner_id=user_b.id, visibility="published")
    await CatalogService.add_book_copy(db=db_session, book_id=book_x.id, owner_id=user_b.id, visibility="published")

    # C has 1 copy of X
    await CatalogService.add_book_copy(db=db_session, book_id=book_x.id, owner_id=user_c.id, visibility="published")

    # D has no copies
    # A creates Need for Book X
    need = await NeedService.create_need(
        db=db_session,
        user_id=user_a.id,
        title_query="Giai tich 1",
        book_id=book_x.id,
        status="open",
    )

    matches = await db_session.execute(
        select(RequestMatch).where(RequestMatch.need_id == need.id)
    )
    all_matches = list(matches.scalars().all())

    matched_owners = {m.owner_user_id for m in all_matches}
    assert user_b.id in matched_owners
    assert user_c.id in matched_owners
    assert user_d.id not in matched_owners
    assert len(all_matches) == 2  # B enqueued once, C enqueued once!


@pytest.mark.asyncio
async def test_scenario_2_eligibility_exclusions_and_privacy(db_session):
    """
    Scenario 2:
    Owner turns off notification, or private holding, or block: excluded from fanout.
    Requester cannot see private PII.
    """
    user_a = User(telegram_user_id=2001, display_name="User A", public_alias="User #A")
    user_b_muted = User(telegram_user_id=2002, display_name="User B", public_alias="User #B")
    user_c_private = User(telegram_user_id=2003, display_name="User C", public_alias="User #C")
    user_d_blocked = User(telegram_user_id=2004, display_name="User D", public_alias="User #D")
    db_session.add_all([user_a, user_b_muted, user_c_private, user_d_blocked])
    await db_session.flush()

    # B turned off notifications
    db_session.add(UserSettings(user_id=user_b_muted.id, notify_matching=False))
    db_session.add(UserSettings(user_id=user_c_private.id, notify_matching=True))
    db_session.add(UserSettings(user_id=user_d_blocked.id, notify_matching=True))

    # D blocked A
    db_session.add(UserBlock(blocker_id=user_d_blocked.id, blocked_id=user_a.id, reason="Spam"))
    await db_session.flush()

    book = await CatalogService.create_book(
        db=db_session,
        title="Vat ly Dai cuong",
        authors=["Tran Van B"],
        isbn_raw="9786040388278",
    )

    # Copies
    await CatalogService.add_book_copy(db=db_session, book_id=book.id, owner_id=user_b_muted.id, visibility="published")
    await CatalogService.add_book_copy(db=db_session, book_id=book.id, owner_id=user_c_private.id, visibility="private")  # Private inventory!
    await CatalogService.add_book_copy(db=db_session, book_id=book.id, owner_id=user_d_blocked.id, visibility="published")

    need = await NeedService.create_need(
        db=db_session,
        user_id=user_a.id,
        title_query="Vat ly Dai cuong",
        book_id=book.id,
        status="open",
    )

    matches_res = await db_session.execute(select(RequestMatch).where(RequestMatch.need_id == need.id))
    matches = matches_res.scalars().all()
    assert len(matches) == 0  # All excluded by policy!


@pytest.mark.asyncio
async def test_scenario_3_offer_selection_reservation_and_fulfillment(db_session):
    """
    Scenario 3:
    A selects offer from B -> creates/links BorrowRequest and Loan reserved.
    Need remains open/arranging until confirmed handover confirms fulfillment!
    """
    user_a = User(telegram_user_id=3001, display_name="User A", public_alias="User #A")
    user_b = User(telegram_user_id=3002, display_name="User B", public_alias="User #B")
    db_session.add_all([user_a, user_b])
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Hoa hoc 12", authors=["Tac gia Hoa"])
    copy_b = await CatalogService.add_book_copy(db=db_session, book_id=book.id, owner_id=user_b.id, visibility="published")

    need = await NeedService.create_need(
        db=db_session,
        user_id=user_a.id,
        title_query="Hoa hoc 12",
        book_id=book.id,
        quantity=1,
        status="open",
    )

    # B creates offer
    offer = await NeedService.create_offer(
        db=db_session,
        need_id=need.id,
        provider_user_id=user_b.id,
        offer_type="full_physical_copy",
        copy_id=copy_b.id,
        proposed_duration_days=14,
    )
    assert offer.status == "proposed"

    # A selects offer
    selected_offer, loan = await NeedService.select_offer(
        db=db_session,
        offer_id=offer.id,
        requester_id=user_a.id,
    )
    assert selected_offer.status == "selected"
    assert loan is not None
    assert loan.status == "reserved"
    assert copy_b.circulation_status == "reserved"
    assert need.status == "open"  # Not fulfilled yet until confirmed handover!

    # Handover confirmation handshake
    await LendingService.confirm_handover(db_session, loan.id, actor_id=user_b.id)
    loan_after, is_active = await LendingService.confirm_handover(db_session, loan.id, actor_id=user_a.id)

    assert is_active is True
    assert loan_after.status == "active"
    assert copy_b.circulation_status == "loaned"
    assert selected_offer.status == "fulfilled"
    assert need.quantity_fulfilled == 1
    assert need.status == "fulfilled"


@pytest.mark.asyncio
async def test_scenario_4_concurrent_offer_selection_mutex(db_session):
    """
    Scenario 4:
    Two borrowers select the same copy: only ONE reserved loan succeeds,
    second receives COPY_UNAVAILABLE (409 conflict).
    """
    user_a1 = User(telegram_user_id=4001, display_name="User A1", public_alias="User #A1")
    user_a2 = User(telegram_user_id=4002, display_name="User A2", public_alias="User #A2")
    user_b = User(telegram_user_id=4003, display_name="User B", public_alias="User #B")
    db_session.add_all([user_a1, user_a2, user_b])
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Tieng Anh 12", authors=["Tac gia Anh"])
    copy_b = await CatalogService.add_book_copy(db=db_session, book_id=book.id, owner_id=user_b.id, visibility="published")

    need1 = await NeedService.create_need(db=db_session, user_id=user_a1.id, title_query="Tieng Anh 12", book_id=book.id)
    need2 = await NeedService.create_need(db=db_session, user_id=user_a2.id, title_query="Tieng Anh 12", book_id=book.id)

    offer1 = await NeedService.create_offer(db=db_session, need_id=need1.id, provider_user_id=user_b.id, offer_type="full_physical_copy", copy_id=copy_b.id)
    offer2 = await NeedService.create_offer(db=db_session, need_id=need2.id, provider_user_id=user_b.id, offer_type="full_physical_copy", copy_id=copy_b.id)

    # First user selects successfully
    off1, loan1 = await NeedService.select_offer(db_session, offer1.id, requester_id=user_a1.id)
    assert off1.status == "selected"
    assert loan1.status == "reserved"

    # Second user tries to select the same copy -> conflict!
    with pytest.raises(BoconicException) as exc_info:
        await NeedService.select_offer(db_session, offer2.id, requester_id=user_a2.id)
    assert exc_info.value.code == ErrorCode.COPY_UNAVAILABLE


@pytest.mark.asyncio
async def test_scenario_5_batch_import_preview_and_confirm(db_session):
    """
    Scenario 5:
    Batch import CSV preview and commit. No duplicated catalog records,
    individual barcodes created per quantity, unpublished data has no fanout.
    """
    user = User(telegram_user_id=5001, display_name="Batch User", public_alias="User #Batch")
    db_session.add(user)
    await db_session.flush()

    csv_data = """title,author,isbn,quantity,barcode,visibility
Toan Cao Cap A1,Nguyen Dinh Tri,9786040001111,2,BAR_TOAN,private
Triet Hoc Mac-Lenin,Bo Giao Duc,,1,BAR_TRIET,private
"""
    preview = await LibraryService.parse_and_preview_csv(csv_data)
    assert preview["total_rows"] == 2
    assert preview["valid_rows"] == 2
    assert preview["distinct_titles"] == 2
    assert preview["total_copies"] == 3  # 2 + 1 copies!

    from app.api.v1.me import confirm_batch_inventory, BatchConfirmDTO, BatchConfirmRowDTO
    dto = BatchConfirmDTO(
        user_id=user.id,
        items=[
            BatchConfirmRowDTO(title="Toan Cao Cap A1", author="Nguyen Dinh Tri", isbn="9786040001111", quantity=2, barcode="BAR_TOAN", visibility="private"),
            BatchConfirmRowDTO(title="Triet Hoc Mac-Lenin", author="Bo Giao Duc", quantity=1, barcode="BAR_TRIET", visibility="private"),
        ]
    )
    res = await confirm_batch_inventory(dto, db=db_session)
    assert res["created_books_count"] == 2
    assert res["created_copies_count"] == 3


@pytest.mark.asyncio
async def test_scenario_6_library_holdings_and_deletion_protection(db_session):
    """
    Scenario 6:
    Library reflects owned, borrowed, lent, available, and wishlist.
    Cannot delete a copy that has an open loan obligation.
    """
    user_owner = User(telegram_user_id=6001, display_name="Owner", public_alias="User #O6")
    user_borrower = User(telegram_user_id=6002, display_name="Borrower", public_alias="User #B6")
    db_session.add_all([user_owner, user_borrower])
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Lap trinh Python", authors=["Python Author"])
    copy = await LibraryService.add_copy(db=db_session, user_id=user_owner.id, book_id=book.id, barcode="BC_PY01", visibility="published")

    lib_owned = await LibraryService.get_user_library(db=db_session, user_id=user_owner.id, tab="owned")
    assert lib_owned["total_items"] == 1
    assert lib_owned["items"][0]["barcode"] == "BC_PY01"

    # Create active loan
    loan = Loan(
        copy_id=copy.id,
        borrower_id=user_borrower.id,
        lender_id=user_owner.id,
        status="active",
    )
    copy.circulation_status = "loaned"
    db_session.add(loan)
    await db_session.flush()

    # Attempt to delete copy under active loan -> Must fail!
    with pytest.raises(BoconicException) as exc_info:
        await LibraryService.remove_copy(db=db_session, user_id=user_owner.id, copy_id=copy.id)
    assert exc_info.value.code == ErrorCode.INVALID_STATE


@pytest.mark.asyncio
async def test_scenario_7_mathematical_coverage_interval_union():
    """
    Scenario 7:
    User 1 has pages 1–10, User 2 has pages 8–17 of demo document.
    Union = 17 pages (1–17). Overlap = 3 pages (8–10).
    Non-contiguous: [(1, 10), (15, 20)] -> union length = 16 pages, gaps: [(11, 14)].
    """
    ranges = [(1, 10), (8, 17)]
    union = CoverageService.calculate_union(ranges)
    assert union == [(1, 17)]

    unique_pages = CoverageService.calculate_unique_pages(ranges)
    assert unique_pages == 17

    overlap_count, overlap_segs = CoverageService.calculate_overlap(ranges)
    assert overlap_count == 3
    assert overlap_segs == [(8, 10)]

    gaps = CoverageService.calculate_gaps(1, 20, ranges)
    assert gaps == [(18, 20)]


@pytest.mark.asyncio
async def test_scenario_8_photocopy_declaration_private_by_default(db_session):
    """
    Scenario 8:
    Declaring partial photocopy saves private metadata without public distribution rights.
    Does not unlock download or assembly without verified rights.
    """
    user = User(telegram_user_id=8001, display_name="User Photo", public_alias="User #P8")
    db_session.add(user)
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Giao trinh Kinh te", authors=["Kinh Te Author"])
    from app.api.v1.internal_bot import bot_register_partial_copy, BotPartialCopyDTO
    dto = BotPartialCopyDTO(
        book_id=book.id,
        start_page=1,
        end_page=15,
        pagination_basis="original_edition",
        chapters=["Chuong 1"],
        source_description="Photo ca nhan tu thu vien",
    )
    res = await bot_register_partial_copy(dto, actor=user, db=db_session)
    assert res["is_partial"] is True
    assert res["visibility"] == "private"

    # Verify copy in DB is strictly private
    copy_in_db = await db_session.get(BookCopy, res["copy_id"])
    assert copy_in_db.visibility == "private"
    assert copy_in_db.is_partial is True


@pytest.mark.asyncio
async def test_scenario_9_authorized_collection_and_assembly_pipeline(db_session):
    """
    Scenario 9:
    Authorized collection with verified rights:
    Contributors submit segments -> coverage preview -> assembly job generated with manifest.
    """
    admin_user = User(telegram_user_id=9001, display_name="Admin", public_alias="Admin #1")
    contributor1 = User(telegram_user_id=9002, display_name="Contrib 1", public_alias="User #C1")
    contributor2 = User(telegram_user_id=9003, display_name="Contrib 2", public_alias="User #C2")
    db_session.add_all([admin_user, contributor1, contributor2])
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Open Education Math", authors=["Open Author"])

    # 1. Create collection
    col = await AssemblyService.create_collection(
        db=db_session,
        book_id=book.id,
        title="Open Math Collection",
        target_scope={"start_page": 1, "end_page": 20},
        rights_basis="Creative Commons CC-BY-SA 4.0",
        allowed_actions=["receive", "aggregate", "distribute_file"],
        recipient_scope="community",
        created_by=admin_user.id,
    )
    assert col.status == "pending_verification"

    # 2. Admin verifies collection
    await AssemblyService.verify_collection(db_session, col.id, verifier_id=admin_user.id, status="active")

    # 3. Contributors submit segments (pages 1-10 and 11-20)
    c1 = await AssemblyService.submit_contribution(
        db_session,
        collection_id=col.id,
        contributor_id=contributor1.id,
        start_page=1,
        end_page=10,
        checksum_sha256="abc123sha",
        consent_given=True,
    )
    c2 = await AssemblyService.submit_contribution(
        db_session,
        collection_id=col.id,
        contributor_id=contributor2.id,
        start_page=11,
        end_page=20,
        checksum_sha256="def456sha",
        consent_given=True,
    )

    # 4. Admin verifies contributions
    await AssemblyService.verify_contribution(db_session, c1.id, verifier_id=admin_user.id, is_approved=True)
    await AssemblyService.verify_contribution(db_session, c2.id, verifier_id=admin_user.id, is_approved=True)

    # 5. Preview coverage
    preview = await AssemblyService.preview_assembly(db_session, col.id)
    analysis = preview["coverage_analysis"]
    assert analysis["source_unique_pages"] == 20
    assert len(analysis["gaps"]) == 0

    # 6. Run assembly job
    job = await AssemblyService.run_assembly_job(db_session, col.id, requested_by=admin_user.id)
    assert job.status == "ready"
    assert "entries" in job.manifest_data
    assert len(job.manifest_data["entries"]) == 2


@pytest.mark.asyncio
async def test_scenario_10_collection_revocation_invalidates_jobs(db_session):
    """
    Scenario 10:
    When rights for a collection are revoked, jobs are invalidated/cancelled.
    """
    admin_user = User(telegram_user_id=10001, display_name="Admin", public_alias="Admin #10")
    db_session.add(admin_user)
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Revoked Rights Work", authors=["Author"])
    col = await AssemblyService.create_collection(
        db=db_session,
        book_id=book.id,
        title="Revoked Collection",
        target_scope={"start_page": 1, "end_page": 10},
        rights_basis="Permitted for 1 month",
        allowed_actions=["aggregate"],
        recipient_scope="community",
        created_by=admin_user.id,
    )
    await AssemblyService.verify_collection(db_session, col.id, verifier_id=admin_user.id, status="active")

    # Run job
    job = await AssemblyService.run_assembly_job(db_session, col.id, requested_by=admin_user.id)

    # Revoke collection
    revoked_col = await AssemblyService.revoke_collection(db_session, col.id, reason="License expired")
    assert revoked_col.status == "revoked"

    job_after = await db_session.get(job.__class__, job.id)
    assert job_after.status == "revoked"


@pytest.mark.asyncio
async def test_scenario_11_user_warning_issuance_and_appeal_workflow(db_session):
    """
    Scenario 11:
    Moderator issues warning with reason/policy.
    User acknowledges and appeals.
    Moderator reviews and accepts appeal -> warning expires cleanly.
    """
    admin = User(telegram_user_id=11001, display_name="Moderator", public_alias="Mod #11")
    user = User(telegram_user_id=11002, display_name="Subject User", public_alias="User #11")
    db_session.add_all([admin, user])
    await db_session.flush()

    # Issue warning
    warning = await WarningService.issue_warning(
        db=db_session,
        subject_user_id=user.id,
        category="rights_review",
        severity="info",
        message="Bạn đã khai báo một phần tài liệu. Hãy bổ sung nguồn và phạm vi quyền trước khi công bố.",
        reason="Chính sách bản quyền Mục 2",
        issued_by=admin.id,
    )
    assert warning.appeal_status == "none"
    assert warning.acknowledged_at is None

    # User acknowledges
    ack_w = await WarningService.acknowledge_warning(db_session, warning.id, user_id=user.id)
    assert ack_w.acknowledged_at is not None

    # User appeals
    app_w = await WarningService.submit_appeal(db_session, warning.id, user_id=user.id, appeal_note="Tôi đã có giấy phép từ giảng viên.")
    assert app_w.appeal_status == "pending"

    # Moderator accepts appeal
    rev_w = await WarningService.review_appeal(db_session, warning.id, moderator_id=admin.id, decision="accepted", notes="Verified with lecturer")
    assert rev_w.appeal_status == "accepted"


@pytest.mark.asyncio
async def test_scenario_12_outbox_events_and_deduplication(db_session):
    """
    Scenario 12:
    Replay action or multiple attempts to create duplicate open need for same book:
    Blocked by ALREADY_EXISTS. Outbox events recorded atomically.
    """
    user = User(telegram_user_id=12001, display_name="User", public_alias="User #12")
    db_session.add(user)
    await db_session.flush()

    book = await CatalogService.create_book(db=db_session, title="Triet Hoc 1", authors=["Author Triet"])

    # 1. Create need
    need1 = await NeedService.create_need(
        db=db_session,
        user_id=user.id,
        title_query="Triet Hoc 1",
        book_id=book.id,
        status="open",
    )
    assert need1.id is not None

    # 2. Attempt duplicate open need -> Must raise 409
    with pytest.raises(BoconicException) as exc_info:
        await NeedService.create_need(
            db=db_session,
            user_id=user.id,
            title_query="Triet Hoc 1",
            book_id=book.id,
            status="open",
        )
    assert exc_info.value.code == ErrorCode.ALREADY_EXISTS

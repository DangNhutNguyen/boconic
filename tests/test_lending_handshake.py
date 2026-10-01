import pytest
from app.core.errors import BoconicException, ErrorCode
from app.db.models.identity import User
from app.services.catalog import CatalogService
from app.services.lending import LendingService
from app.services.trust import TrustService

@pytest.mark.asyncio
async def test_borrow_request_and_self_borrow_block(db_session):
    # Setup users
    owner = User(telegram_user_id=111, display_name="Owner", public_alias="User #O1")
    borrower = User(telegram_user_id=222, display_name="Borrower", public_alias="User #B2")
    db_session.add_all([owner, borrower])
    await db_session.flush()

    # Create book and copy
    book = await CatalogService.create_book(
        db=db_session,
        title="Lịch Sử 12",
        authors=["Tác Giả Sử"],
        isbn_raw="9780306406157",
    )
    copy = await CatalogService.add_book_copy(
        db=db_session,
        book_id=book.id,
        owner_id=owner.id,
        condition="good",
    )

    # 1. Attempt self-borrow -> Must fail with FORBIDDEN
    with pytest.raises(BoconicException) as exc_info:
        await LendingService.create_borrow_request(
            db=db_session,
            copy_id=copy.id,
            borrower_id=owner.id,
        )
    assert exc_info.value.code == ErrorCode.FORBIDDEN

    # 2. Legitimate borrow request -> Succeeds
    req = await LendingService.create_borrow_request(
        db=db_session,
        copy_id=copy.id,
        borrower_id=borrower.id,
        duration_days=14,
    )
    assert req.id is not None
    assert req.status == "pending"

    # 3. Duplicate pending request by same borrower -> Must fail with ALREADY_EXISTS
    with pytest.raises(BoconicException) as dup_info:
        await LendingService.create_borrow_request(
            db=db_session,
            copy_id=copy.id,
            borrower_id=borrower.id,
        )
    assert dup_info.value.code == ErrorCode.ALREADY_EXISTS

@pytest.mark.asyncio
async def test_full_lending_handshake_flow(db_session):
    owner = User(telegram_user_id=333, display_name="Lender", public_alias="User #L1")
    borrower = User(telegram_user_id=444, display_name="Borrower", public_alias="User #B1")
    db_session.add_all([owner, borrower])
    await db_session.flush()

    book = await CatalogService.create_book(
        db=db_session,
        title="Toán 12",
        authors=["Nhiều tác giả"],
        isbn_raw="9786040388278",
    )
    copy = await CatalogService.add_book_copy(
        db=db_session,
        book_id=book.id,
        owner_id=owner.id,
    )

    # 1. Request
    req = await LendingService.create_borrow_request(
        db=db_session, copy_id=copy.id, borrower_id=borrower.id, duration_days=10
    )

    # 2. Accept
    loan = await LendingService.accept_borrow_request(
        db=db_session, request_id=req.id, owner_id=owner.id
    )
    assert loan.status == "reserved"
    assert copy.circulation_status == "reserved"

    # 3. Concurrency check: another accept or request while reserved must fail
    with pytest.raises(BoconicException) as lock_info:
        await LendingService.create_borrow_request(
            db=db_session, copy_id=copy.id, borrower_id=borrower.id
        )
    assert lock_info.value.code == ErrorCode.COPY_UNAVAILABLE

    # 4. Handover handshake: Lender confirms
    loan, is_active1 = await LendingService.confirm_handover(db_session, loan.id, owner.id)
    assert not is_active1
    assert loan.status == "reserved"

    # Handover handshake: Borrower confirms -> Transitions to active
    loan, is_active2 = await LendingService.confirm_handover(db_session, loan.id, borrower.id)
    assert is_active2
    assert loan.status == "active"
    assert loan.handed_over_at is not None
    assert loan.due_at is not None
    assert copy.circulation_status == "loaned"
    assert copy.current_holder_id == borrower.id

    # 5. Return request
    loan = await LendingService.request_return(db_session, loan.id, borrower.id)
    assert loan.status == "return_pending"

    # 6. Return handshake: Borrower confirms return
    loan, is_ret1 = await LendingService.confirm_return(db_session, loan.id, borrower.id)
    assert not is_ret1
    assert loan.status == "return_pending"

    # Return handshake: Lender confirms return -> Transitions to returned
    loan, is_ret2 = await LendingService.confirm_return(db_session, loan.id, owner.id)
    assert is_ret2
    assert loan.status == "returned"
    assert copy.circulation_status == "available"
    assert copy.current_holder_id == owner.id

    # 7. Trust profile verification
    trust = await TrustService.get_user_trust_profile(db_session, borrower.id)
    assert trust["total_returns"] == 1
    assert trust["on_time_returns"] == 1
    assert trust["reliability_score"] is not None

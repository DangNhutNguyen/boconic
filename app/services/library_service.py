"""
Service for managing Personal Library tabs, holdings, reading progress, and batch operations.
Strictly respects ownership, active loan invariants, and privacy settings.
"""
from datetime import datetime, timezone
import io
import csv
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import BoconicException, ErrorCode
from app.db.models.catalog import Book, BookAuthor, BookCopy, CopyCoverageRange, LibraryEntry
from app.db.models.community import CommunityRequest, Resource
from app.db.models.lending import Loan


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LibraryService:
    @classmethod
    async def get_user_library(
        cls,
        db: AsyncSession,
        user_id: str,
        tab: str = "all",
    ) -> Dict[str, Any]:
        """
        Fetch personal library entries categorized by tab.
        Tabs: all, owned, available, lent, borrowed, wishlist, resources, history.
        """
        tab = tab.lower()
        items: List[Dict[str, Any]] = []

        # 1. Owned copies
        owned_copies_stmt = (
            select(BookCopy, Book)
            .join(Book, BookCopy.book_id == Book.id)
            .options(selectinload(Book.authors).selectinload(BookAuthor.author))
            .where(BookCopy.owner_id == user_id)
        )

        if tab == "available":
            owned_copies_stmt = owned_copies_stmt.where(
                BookCopy.circulation_status == "available",
                BookCopy.visibility.in_(["published", "public"]),
            )
        elif tab == "lent":
            owned_copies_stmt = owned_copies_stmt.where(
                BookCopy.circulation_status.in_(["loaned", "reserved", "return_pending"])
            )
        elif tab == "resources":
            owned_copies_stmt = owned_copies_stmt.where(BookCopy.is_partial == True)  # noqa: E712

        res_copies = await db.execute(owned_copies_stmt)
        copies_rows = res_copies.all()

        # Load reading statuses / library entries for this user
        entries_res = await db.execute(
            select(LibraryEntry).where(LibraryEntry.user_id == user_id)
        )
        library_entries_map = {e.book_id: e for e in entries_res.scalars().all()}

        if tab in ("all", "owned", "available", "lent", "resources"):
            for copy, book in copies_rows:
                entry = library_entries_map.get(book.id)
                items.append({
                    "type": "owned_copy",
                    "copy_id": copy.id,
                    "book_id": book.id,
                    "title": book.title,
                    "author": book.author,
                    "isbn": book.isbn,
                    "barcode": copy.barcode,
                    "condition": copy.condition,
                    "circulation_status": copy.circulation_status,
                    "visibility": copy.visibility,
                    "format": copy.format,
                    "is_partial": copy.is_partial,
                    "available_from": copy.available_from.isoformat() if copy.available_from else None,
                    "reading_status": entry.reading_status if entry else "unread",
                    "tags": entry.tags if entry else [],
                })

        # 2. Borrowed items (Active loans)
        if tab in ("all", "borrowed"):
            borrowed_stmt = (
                select(Loan, BookCopy, Book)
                .join(BookCopy, Loan.copy_id == BookCopy.id)
                .join(Book, BookCopy.book_id == Book.id)
                .options(selectinload(Book.authors).selectinload(BookAuthor.author))
                .where(
                    Loan.borrower_id == user_id,
                    Loan.status.in_(["reserved", "active", "return_pending"]),
                )
            )
            borrowed_res = await db.execute(borrowed_stmt)
            for loan, copy, book in borrowed_res.all():
                items.append({
                    "type": "borrowed_loan",
                    "loan_id": loan.id,
                    "copy_id": copy.id,
                    "book_id": book.id,
                    "title": book.title,
                    "author": book.author,
                    "status": loan.status,
                    "due_at": loan.due_at.isoformat() if loan.due_at else None,
                    "reservation_expires_at": loan.reservation_expires_at.isoformat() if loan.reservation_expires_at else None,
                    "lender_id": loan.lender_id,
                })

        # 3. Wishlist / Active needs
        if tab in ("all", "wishlist"):
            needs_stmt = select(CommunityRequest).where(
                CommunityRequest.user_id == user_id,
                CommunityRequest.status.in_(["open", "draft"]),
            )
            needs_res = await db.execute(needs_stmt)
            for need in needs_res.scalars().all():
                items.append({
                    "type": "wishlist_need",
                    "need_id": need.id,
                    "title_query": need.title_query,
                    "isbn": need.isbn,
                    "scope_type": need.scope_type,
                    "quantity": need.quantity,
                    "quantity_fulfilled": need.quantity_fulfilled,
                    "status": need.status,
                    "created_at": need.created_at.isoformat(),
                })

        # 4. History (Returned loans)
        if tab in ("all", "history"):
            history_stmt = (
                select(Loan, BookCopy, Book)
                .join(BookCopy, Loan.copy_id == BookCopy.id)
                .join(Book, BookCopy.book_id == Book.id)
                .where(
                    or_(Loan.borrower_id == user_id, Loan.lender_id == user_id),
                    Loan.status == "returned",
                )
                .order_by(Loan.returned_at.desc())
            )
            history_res = await db.execute(history_stmt)
            for loan, copy, book in history_res.all():
                role = "borrower" if loan.borrower_id == user_id else "lender"
                items.append({
                    "type": "history_loan",
                    "loan_id": loan.id,
                    "role": role,
                    "book_title": book.title,
                    "status": loan.status,
                    "handed_over_at": loan.handed_over_at.isoformat() if loan.handed_over_at else None,
                    "returned_at": loan.returned_at.isoformat() if loan.returned_at else None,
                })

        return {
            "tab": tab,
            "total_items": len(items),
            "items": items,
        }

    @classmethod
    async def add_copy(
        cls,
        db: AsyncSession,
        user_id: str,
        book_id: str,
        barcode: str,
        condition: str = "good",
        visibility: str = "private",
        format_type: str = "physical",
        is_partial: bool = False,
        coverage_summary: Optional[Dict[str, Any]] = None,
    ) -> BookCopy:
        """Add a new physical copy to user's library."""
        book = await db.get(Book, book_id)
        if not book:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy đầu sách.", status_code=404)

        # Check duplicate barcode
        existing = await db.execute(select(BookCopy).where(BookCopy.public_code == barcode.strip()))
        if existing.scalar_one_or_none():
            raise BoconicException(code=ErrorCode.ALREADY_EXISTS, message="Mã barcode này đã tồn tại.", status_code=409)

        copy = BookCopy(
            book_id=book_id,
            owner_id=user_id,
            current_holder_id=user_id,
            public_code=barcode.strip(),
            condition=condition,
            circulation_status="available",
            visibility=visibility,
            format=format_type,
            is_partial=is_partial,
            coverage_summary=coverage_summary or {},
            custom_data={"barcode": barcode.strip()},
        )
        db.add(copy)
        await db.flush()
        return copy

    @classmethod
    async def set_copy_visibility(
        cls,
        db: AsyncSession,
        user_id: str,
        copy_id: str,
        visibility: str,  # 'published' or 'private'
    ) -> BookCopy:
        """Toggle lending/discovery visibility for a copy."""
        copy = await db.get(BookCopy, copy_id)
        if not copy:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy bản sách.", status_code=404)
        if copy.owner_id != user_id:
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không sở hữu bản sách này.", status_code=403)

        if visibility == "public":
            visibility = "published"
        if visibility not in ("published", "private"):
            raise BoconicException(code=ErrorCode.BAD_REQUEST, message="Trạng thái hiển thị không hợp lệ.", status_code=400)

        copy.visibility = visibility
        await db.flush()
        return copy

    @classmethod
    async def remove_copy(
        cls,
        db: AsyncSession,
        user_id: str,
        copy_id: str,
    ) -> bool:
        """Remove a copy. Invariant: Cannot remove if in an active or reserved loan."""
        copy = await db.get(BookCopy, copy_id)
        if not copy:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy bản sách.", status_code=404)
        if copy.owner_id != user_id:
            raise BoconicException(code=ErrorCode.FORBIDDEN, message="Bạn không sở hữu bản sách này.", status_code=403)

        # Check for open loans
        open_loans = await db.execute(
            select(Loan).where(
                Loan.copy_id == copy_id,
                Loan.status.in_(["reserved", "active", "return_pending", "disputed"]),
            )
        )
        if open_loans.scalar_one_or_none():
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message="Bản sách đang có giao dịch mượn chưa kết thúc, không thể xóa.",
                status_code=409,
            )

        await db.delete(copy)
        await db.flush()
        return True

    @classmethod
    async def update_reading_status(
        cls,
        db: AsyncSession,
        user_id: str,
        book_id: str,
        reading_status: str,
        rating: Optional[int] = None,
        personal_notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> LibraryEntry:
        """Update personal reading status / notes in LibraryEntry."""
        entry_res = await db.execute(
            select(LibraryEntry).where(
                LibraryEntry.user_id == user_id,
                LibraryEntry.book_id == book_id,
                LibraryEntry.entry_type == "personal",
            )
        )
        entry = entry_res.scalar_one_or_none()
        if not entry:
            entry = LibraryEntry(
                user_id=user_id,
                book_id=book_id,
                entry_type="personal",
                reading_status=reading_status,
                rating=rating,
                personal_notes=personal_notes,
                tags=tags or [],
                is_public=False,
            )
            db.add(entry)
        else:
            entry.reading_status = reading_status
            if rating is not None:
                entry.rating = rating
            if personal_notes is not None:
                entry.personal_notes = personal_notes
            if tags is not None:
                entry.tags = tags

        await db.flush()
        return entry

    @classmethod
    async def parse_and_preview_csv(
        cls,
        csv_content: str,
    ) -> Dict[str, Any]:
        """
        Parse CSV and preview books and copies before committing.
        Normalizes ISBN, counts titles vs copies, detects duplicate barcodes.
        """
        reader = csv.DictReader(io.StringIO(csv_content.strip()))
        rows = list(reader)

        preview_items = []
        errors = []
        seen_barcodes = set()
        titles = set()
        total_copies = 0

        for idx, row in enumerate(rows, start=1):
            title = row.get("title", "").strip()
            isbn = row.get("isbn", "").strip()
            barcode = row.get("barcode", "").strip()
            quantity_str = row.get("quantity", "1").strip()

            if not title:
                errors.append(f"Dòng {idx}: Thiếu tiêu đề sách.")
                continue

            try:
                quantity = max(1, int(quantity_str))
            except ValueError:
                quantity = 1

            if barcode in seen_barcodes:
                errors.append(f"Dòng {idx}: Trùng mã barcode '{barcode}'.")
                continue
            if barcode:
                seen_barcodes.add(barcode)

            titles.add(title.lower())
            total_copies += quantity

            preview_items.append({
                "row_index": idx,
                "title": title,
                "author": row.get("author", "").strip(),
                "isbn": isbn,
                "publisher": row.get("publisher", "").strip(),
                "barcode": barcode,
                "condition": row.get("condition", "good").strip(),
                "quantity": quantity,
                "visibility": row.get("visibility", "private").strip(),
            })

        return {
            "total_rows": len(rows),
            "valid_rows": len(preview_items),
            "distinct_titles": len(titles),
            "total_copies": total_copies,
            "errors": errors,
            "preview_items": preview_items,
        }

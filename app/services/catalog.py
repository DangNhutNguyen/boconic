import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import BoconicException, ErrorCode
from app.core.security import generate_public_copy_code
from app.db.models.catalog import Author, Book, BookAuthor, BookCopy, Chapter, Publisher

def normalize_isbn(isbn_raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Clean, validate and convert ISBN-10 to canonical ISBN-13 if valid.
    Returns (isbn10, isbn13).
    """
    if not isbn_raw:
        return None, None

    cleaned = re.sub(r"[^0-9X]", "", isbn_raw.upper())
    
    isbn10 = None
    isbn13 = None

    if len(cleaned) == 10:
        # Validate ISBN-10 checksum
        total = sum((10 - i) * (10 if char == "X" else int(char)) for i, char in enumerate(cleaned))
        if total % 11 == 0:
            isbn10 = cleaned
            # Convert to ISBN-13
            prefix = "978" + cleaned[:9]
            check = (10 - sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(prefix)) % 10) % 10
            isbn13 = prefix + str(check)
    elif len(cleaned) == 13:
        # Validate ISBN-13 checksum
        total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(cleaned))
        if total % 10 == 0:
            isbn13 = cleaned

    return isbn10, isbn13

class CatalogService:
    @staticmethod
    async def get_or_create_author(db: AsyncSession, name: str) -> Author:
        name_clean = name.strip()
        result = await db.execute(select(Author).where(Author.name == name_clean))
        author = result.scalar_one_or_none()
        if not author:
            author = Author(name=name_clean)
            db.add(author)
            await db.flush()
        return author

    @classmethod
    async def create_book(
        cls,
        db: AsyncSession,
        title: str,
        authors: List[str],
        publisher: Optional[str] = None,
        publication_year: Optional[int] = None,
        edition_label: Optional[str] = None,
        language: str = "vi",
        subject: Optional[str] = None,
        grade_level: Optional[int] = None,
        curriculum: Optional[str] = None,
        isbn_raw: Optional[str] = None,
        description: Optional[str] = None,
        cover_media_id: Optional[str] = None,
        custom_data: Optional[Dict[str, Any]] = None,
    ) -> Book:
        isbn10, isbn13 = normalize_isbn(isbn_raw)

        # Check for unique ISBN-13
        if isbn13:
            existing = await db.execute(select(Book).where(Book.isbn13 == isbn13))
            if existing.scalar_one_or_none():
                raise BoconicException(
                    code=ErrorCode.ALREADY_EXISTS,
                    message=f"Đầu sách với ISBN {isbn13} đã tồn tại trong hệ thống.",
                    status_code=409,
                    details={"isbn13": isbn13},
                )

        book = Book(
            title=title.strip(),
            publisher=publisher.strip() if publisher else None,
            publication_year=publication_year,
            edition_label=edition_label.strip() if edition_label else None,
            language=language,
            subject=subject.strip() if subject else None,
            grade_level=grade_level,
            curriculum=curriculum.strip() if curriculum else None,
            isbn10=isbn10,
            isbn13=isbn13,
            description=description,
            cover_media_id=cover_media_id,
            custom_data=custom_data or {},
        )
        db.add(book)
        await db.flush()

        # Link authors
        for author_name in authors:
            if author_name.strip():
                author = await cls.get_or_create_author(db, author_name)
                link = BookAuthor(book_id=book.id, author_id=author.id)
                db.add(link)

        await db.flush()
        return book

    @classmethod
    async def add_book_copy(
        cls,
        db: AsyncSession,
        book_id: str,
        owner_id: str,
        condition: str = "good",
        maximum_loan_days: int = 14,
        lending_policy: str = "free_return",
        storage_location_private: Optional[str] = None,
        notes: Optional[str] = None,
        barcode: Optional[str] = None,
        visibility: str = "published",
        format_type: str = "physical",
        is_partial: bool = False,
        available_from: Optional[Any] = None,
        coverage_summary: Optional[Dict[str, Any]] = None,
        custom_data: Optional[Dict[str, Any]] = None,
    ) -> BookCopy:
        book = await db.get(Book, book_id)
        if not book:
            raise BoconicException(
                code=ErrorCode.NOT_FOUND,
                message="Không tìm thấy đầu sách tương ứng.",
                status_code=404,
            )

        public_code = generate_public_copy_code()
        c_data = dict(custom_data or {})
        c_data["barcode"] = barcode.strip() if barcode else public_code
        copy = BookCopy(
            book_id=book_id,
            owner_id=owner_id,
            current_holder_id=owner_id,
            public_code=public_code,
            condition=condition,
            circulation_status="available",
            visibility=visibility,
            format=format_type,
            is_partial=is_partial,
            available_from=available_from,
            coverage_summary=coverage_summary or {},
            maximum_loan_days=maximum_loan_days,
            lending_policy=lending_policy,
            storage_location_private=storage_location_private,
            notes=notes,
            custom_data=c_data,
        )
        db.add(copy)
        await db.flush()
        return copy

    @classmethod
    async def search_books(
        cls,
        db: AsyncSession,
        query: Optional[str] = None,
        subject: Optional[str] = None,
        grade_level: Optional[int] = None,
        curriculum: Optional[str] = None,
        available_only: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Book], int]:
        stmt = select(Book).options(
            selectinload(Book.authors).selectinload(BookAuthor.author),
            selectinload(Book.copies),
        )

        filters = []
        if query:
            q_clean = f"%{query.strip()}%"
            filters.append(
                or_(
                    Book.title.ilike(q_clean),
                    Book.isbn10.ilike(q_clean),
                    Book.isbn13.ilike(q_clean),
                    Book.publisher.ilike(q_clean),
                )
            )

        if subject:
            filters.append(Book.subject.ilike(f"%{subject.strip()}%"))

        if grade_level is not None:
            filters.append(Book.grade_level == grade_level)

        if curriculum:
            filters.append(Book.curriculum.ilike(f"%{curriculum.strip()}%"))

        if filters:
            stmt = stmt.where(*filters)

        # Count total
        count_stmt = select(func.count(Book.id))
        if filters:
            count_stmt = count_stmt.where(*filters)
        total_res = await db.execute(count_stmt)
        total = total_res.scalar_one()

        stmt = stmt.order_by(Book.title.asc()).offset(offset).limit(limit)
        results = await db.execute(stmt)
        books = list(results.scalars().all())

        if available_only:
            books = [b for b in books if any(c.circulation_status == "available" for c in b.copies)]

        return books, total

    @classmethod
    async def get_book_detail(cls, db: AsyncSession, book_id: str) -> Optional[Book]:
        stmt = (
            select(Book)
            .where(Book.id == book_id)
            .options(
                selectinload(Book.authors).selectinload(BookAuthor.author),
                selectinload(Book.copies).selectinload(BookCopy.owner),
                selectinload(Book.chapters),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

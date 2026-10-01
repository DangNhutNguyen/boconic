import pytest
from app.services.catalog import CatalogService, normalize_isbn
from app.db.models.catalog import Book, BookCopy

def test_isbn_normalization_and_checksum():
    # Valid ISBN-10 (e.g. 0-306-40615-2)
    isbn10, isbn13 = normalize_isbn("0306406152")
    assert isbn10 == "0306406152"
    assert isbn13 == "9780306406157"

    # Valid ISBN-13
    isbn10_b, isbn13_b = normalize_isbn("978-604-0-38827-8")
    assert isbn13_b == "9786040388278"

    # Invalid ISBN checksum
    inv10, inv13 = normalize_isbn("1234567890")
    assert inv10 is None
    assert inv13 is None

@pytest.mark.asyncio
async def test_book_crud_and_search(db_session):
    # Create Book
    book = await CatalogService.create_book(
        db=db_session,
        title="Toán Học Nâng Cao Lớp 11",
        authors=["Nguyễn Huy Hoàng"],
        publisher="NXB Giáo dục Việt Nam",
        publication_year=2024,
        grade_level=11,
        subject="Toán học",
        curriculum="Chân trời sáng tạo",
        isbn_raw="9780306406157",
    )
    assert book.id is not None
    assert book.title == "Toán Học Nâng Cao Lớp 11"
    assert book.isbn13 == "9780306406157"

    # Search Book
    results, total = await CatalogService.search_books(
        db=db_session,
        query="Toán Học Nâng Cao",
        grade_level=11,
    )
    assert total >= 1
    assert any(b.title == "Toán Học Nâng Cao Lớp 11" for b in results)

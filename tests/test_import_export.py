import pytest
from app.db.models.catalog import Book
from app.db.models.jobs import ImportJob
from app.services.import_export import (
    ImportExportService,
    sanitize_csv_cell,
)

def test_sanitize_csv_cell_formula_injection():
    # Dangerous formula injection triggers
    assert sanitize_csv_cell("=1+1").startswith("\t=")
    assert sanitize_csv_cell("+cmd|' /C calc'!A0").startswith("\t+")
    assert sanitize_csv_cell("-2+3").startswith("\t-")
    assert sanitize_csv_cell("@SUM(A1:A10)").startswith("\t@")
    # Normal safe cells
    assert sanitize_csv_cell("Toán 12") == "Toán 12"
    assert sanitize_csv_cell(123) == "123"

def test_csv_parser_with_utf8_bom():
    raw_csv = (
        b"\xef\xbb\xbf"  # UTF-8 BOM
        b"T\xc3\xaan s\xc3\xa1ch;T\xc3\xa1c gi\xe1\xba\xa3;ISBN\n"
        b'"H\xc3\xb3a h\xe1\xbb\x8dc 12";"Nguy\xe1\xbb\x85n V\xc4\x83n A";9786040388278\n'
    )
    headers, rows, delimiter = ImportExportService.parse_csv_content(raw_csv)
    assert delimiter == ";"
    assert len(headers) == 3
    assert len(rows) == 1
    assert rows[0]["Tên sách"] == "Hóa học 12"
    assert rows[0]["ISBN"] == "9786040388278"

@pytest.mark.asyncio
async def test_csv_import_and_export_roundtrip(db_session):
    raw_csv = (
        "Tên sách,Tác giả,ISBN,Năm XB\n"
        "Vật lý đại cương,Nguyễn Văn B,9786040388278,2024\n"
        ",Tác giả ẩn,123456,2023\n" # Invalid row: missing title
    ).encode("utf-8")

    headers, rows, delimiter = ImportExportService.parse_csv_content(raw_csv)
    mapping = {
        "title": "Tên sách",
        "authors": "Tác giả",
        "isbn": "ISBN",
        "publication_year": "Năm XB",
    }

    # 1. Preview
    preview = await ImportExportService.preview_book_import(db_session, rows, mapping)
    assert preview["preview_valid_count"] == 1
    assert preview["preview_error_count"] == 1

    # 2. Execute
    job = ImportJob(
        entity_type="books",
        filename="test.csv",
        file_hash="dummy_hash",
        status="staged",
        mapping=mapping,
    )
    db_session.add(job)
    await db_session.flush()

    res_job = await ImportExportService.execute_book_import(
        db=db_session, job_id=job.id, rows=rows, mapping=mapping, mode="upsert"
    )
    assert res_job.created_count == 1
    assert res_job.error_count == 1
    assert res_job.status == "completed"

    # 3. Export
    books = [Book(title="=Hacker Book", publisher="NXB Test", isbn13="9786040388278")]
    csv_str = await ImportExportService.export_books_csv(db_session, books)
    assert "\ufeff" in csv_str # contains UTF-8 BOM
    assert "\t=Hacker Book" in csv_str # formula injection defused

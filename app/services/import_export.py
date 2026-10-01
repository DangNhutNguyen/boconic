import csv
import hashlib
import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import BoconicException, ErrorCode
from app.db.models.catalog import Book
from app.db.models.jobs import ImportJob, ImportRow
from app.services.catalog import CatalogService, normalize_isbn
from app.services.custom_fields import CustomFieldsService

def sanitize_csv_cell(value: Any) -> str:
    """Prevent CSV Formula Injection in spreadsheet software by prefixing formula triggers with a tab."""
    if value is None:
        return ""
    val_str = str(value)
    if val_str and val_str[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"\t{val_str}"
    return val_str

class ImportExportService:
    @staticmethod
    def parse_csv_content(raw_bytes: bytes) -> Tuple[List[str], List[Dict[str, str]], str]:
        """Detect encoding, BOM, delimiter, and parse CSV into rows."""
        # Detect UTF-8 BOM
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            text = raw_bytes[3:].decode("utf-8", errors="replace")
        else:
            text = raw_bytes.decode("utf-8", errors="replace")

        # Detect delimiter
        sample = text[:2048]
        delimiter = ","
        if ";" in sample and sample.count(";") > sample.count(","):
            delimiter = ";"
        elif "\t" in sample and sample.count("\t") > sample.count(","):
            delimiter = "\t"

        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        try:
            headers = [h.strip() for h in next(reader)]
        except StopIteration:
            return [], [], delimiter

        rows = []
        for line in reader:
            if not any(cell.strip() for cell in line):
                continue
            row_dict = {}
            for i, h in enumerate(headers):
                row_dict[h] = line[i].strip() if i < len(line) else ""
            rows.append(row_dict)

        return headers, rows, delimiter

    @classmethod
    async def preview_book_import(
        cls,
        db: AsyncSession,
        rows: List[Dict[str, str]],
        mapping: Dict[str, str], # e.g. {"Tên sách": "title", "ISBN": "isbn", "Tác giả": "authors"}
        mode: str = "upsert",
    ) -> Dict[str, Any]:
        """Validate mapped rows and produce preview metrics (valid, error, skipped)."""
        valid_rows = []
        errors = []
        warnings = []
        skipped = 0

        # Mapped keys: title, authors, publisher, publication_year, grade_level, subject, curriculum, isbn
        for idx, row in enumerate(rows[:500], start=1):
            title = row.get(mapping.get("title", ""), "").strip()
            if not title:
                errors.append({"row": idx, "field": "title", "code": "REQUIRED", "msg": "Tên sách không được để trống"})
                continue

            isbn_raw = row.get(mapping.get("isbn", ""), "").strip()
            isbn10, isbn13 = normalize_isbn(isbn_raw) if isbn_raw else (None, None)
            if isbn_raw and not isbn13:
                warnings.append({"row": idx, "field": "isbn", "code": "INVALID_CHECKSUM", "msg": f"Mã ISBN '{isbn_raw}' không hợp lệ"})

            valid_rows.append({
                "row_number": idx,
                "title": title,
                "isbn13": isbn13,
                "publisher": row.get(mapping.get("publisher", ""), "").strip(),
                "grade_level": row.get(mapping.get("grade_level", ""), "").strip(),
            })

        return {
            "total_sample_rows": len(rows),
            "preview_valid_count": len(valid_rows),
            "preview_error_count": len(errors),
            "preview_warning_count": len(warnings),
            "errors": errors[:50],
            "warnings": warnings[:50],
            "sample_valid": valid_rows[:10],
        }

    @classmethod
    async def execute_book_import(
        cls,
        db: AsyncSession,
        job_id: str,
        rows: List[Dict[str, str]],
        mapping: Dict[str, str],
        mode: str = "upsert",
    ) -> ImportJob:
        job = await db.get(ImportJob, job_id)
        if not job:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy import job.")

        job.status = "running"
        job.total_rows = len(rows)
        await db.flush()

        created_count = 0
        updated_count = 0
        error_count = 0
        skipped_count = 0
        error_records = []

        for idx, row in enumerate(rows, start=1):
            title = row.get(mapping.get("title", ""), "").strip()
            if not title:
                error_count += 1
                error_records.append((idx, "title", "REQUIRED", "Tên sách bị thiếu"))
                continue

            isbn_raw = row.get(mapping.get("isbn", ""), "").strip()
            isbn10, isbn13 = normalize_isbn(isbn_raw) if isbn_raw else (None, None)

            author_raw = row.get(mapping.get("authors", ""), "").strip()
            authors = [a.strip() for a in author_raw.split(",") if a.strip()] or ["Nhiều tác giả"]

            grade_str = row.get(mapping.get("grade_level", ""), "").strip()
            grade_level = int(grade_str) if grade_str.isdigit() else None

            year_str = row.get(mapping.get("publication_year", ""), "").strip()
            year = int(year_str) if year_str.isdigit() else None

            # Upsert check by ISBN-13
            existing_book = None
            if isbn13:
                res = await db.execute(select(Book).where(Book.isbn13 == isbn13))
                existing_book = res.scalar_one_or_none()

            try:
                if existing_book:
                    if mode == "create_only":
                        skipped_count += 1
                        continue
                    # Update
                    existing_book.title = title
                    if year:
                        existing_book.publication_year = year
                    if grade_level:
                        existing_book.grade_level = grade_level
                    updated_count += 1
                else:
                    if mode == "update_only":
                        skipped_count += 1
                        continue
                    # Create
                    await CatalogService.create_book(
                        db=db,
                        title=title,
                        authors=authors,
                        publisher=row.get(mapping.get("publisher", ""), "").strip() or None,
                        publication_year=year,
                        grade_level=grade_level,
                        curriculum=row.get(mapping.get("curriculum", ""), "").strip() or None,
                        isbn_raw=isbn_raw,
                    )
                    created_count += 1
            except Exception as e:
                error_count += 1
                error_records.append((idx, "general", "DB_ERROR", str(e)))

        # Write errors.csv if any
        if error_records:
            errors_filename = f"errors_job_{job_id}.csv"
            errors_path = Path(settings.STORAGE_DIR) / errors_filename
            with open(errors_path, "w", encoding="utf-8-sig", newline="") as ef:
                writer = csv.writer(ef)
                writer.writerow(["Dòng", "Trường", "Mã lỗi", "Thông báo"])
                for rec in error_records:
                    writer.writerow([rec[0], rec[1], rec[2], sanitize_csv_cell(rec[3])])
            job.errors_csv_path = str(errors_path)

        job.status = "completed"
        job.processed_rows = len(rows)
        job.created_count = created_count
        job.updated_count = updated_count
        job.error_count = error_count
        job.skipped_count = skipped_count
        await db.flush()

        return job

    @classmethod
    async def export_books_csv(
        cls,
        db: AsyncSession,
        books: List[Book],
        include_sensitive: bool = False,
    ) -> str:
        """Export list of books to RFC-4180 CSV with UTF-8 BOM and formula injection protection."""
        output = io.StringIO()
        output.write("\ufeff") # UTF-8 BOM
        writer = csv.writer(output)

        headers = ["ID", "Tên sách", "Nhà xuất bản", "Năm XB", "Lớp", "Môn", "Bộ sách", "ISBN-13", "Bản khả dụng"]
        writer.writerow(headers)

        for b in books:
            available_copies = sum(1 for c in b.copies if c.circulation_status == "available")
            writer.writerow([
                b.id,
                sanitize_csv_cell(b.title),
                sanitize_csv_cell(b.publisher),
                b.publication_year or "",
                b.grade_level or "",
                sanitize_csv_cell(b.subject),
                sanitize_csv_cell(b.curriculum),
                sanitize_csv_cell(b.isbn13),
                available_copies,
            ])

        return output.getvalue()

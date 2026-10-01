"""
Service for User Partial Material Management.
Handles:
1. Physical photocopy / partial holding declaration (BookCopy with is_partial=True + CopyCoverageRange).
2. Digital excerpt / chapter resource uploads (ChapterResource with secure storage and quarantine).
3. Retrieval, download, and deletion of personal partial materials.
Strictly adheres to docs/partial-material-policy.md anti-circumvention rules.
"""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.errors import BoconicException, ErrorCode
from app.db.models.catalog import Book, BookCopy, Chapter, ChapterResource, CopyCoverageRange
from app.db.models.identity import User
from app.db.models.jobs import AuditLog, OutboxEvent
from app.db.models.lending import CustodyEvent, Loan
from app.services.audit import AuditService
from app.services.catalog import CatalogService
from app.services.coverage_service import CoverageService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


STORAGE_DIR = Path("data/storage/partial_materials")


class PartialMaterialService:
    @classmethod
    async def create_physical_partial_material(
        cls,
        db: AsyncSession,
        user_id: str,
        book_id: str,
        start_page: int,
        end_page: int,
        chapters: Optional[List[Any]] = None,
        condition: str = "good",
        source_description: Optional[str] = None,
        visibility: str = "private", # Default private per policy
        storage_location_private: Optional[str] = None,
        notes: Optional[str] = None,
        barcode: Optional[str] = None,
    ) -> Tuple[BookCopy, CopyCoverageRange]:
        """
        Declare a physical photocopy or excerpt holding in user account.
        Validates page range and calculates unique coverage intervals.
        """
        user = await db.get(User, user_id)
        if not user:
            raise BoconicException(ErrorCode.NOT_FOUND, "Không tìm thấy người dùng.", status_code=404)

        book = await db.get(Book, book_id)
        if not book:
            raise BoconicException(ErrorCode.NOT_FOUND, "Không tìm thấy đầu sách.", status_code=404)

        # Range validation
        if start_page < 1 or end_page < start_page:
            raise BoconicException(
                ErrorCode.VALIDATION_ERROR,
                f"Khoảng trang không hợp lệ: {start_page} đến {end_page}. Trang bắt đầu phải >= 1 và <= trang kết thúc.",
                status_code=400,
            )

        if book.total_pages and end_page > book.total_pages:
            raise BoconicException(
                ErrorCode.VALIDATION_ERROR,
                f"Trang kết thúc ({end_page}) vượt quá tổng số trang của sách ({book.total_pages}).",
                status_code=400,
            )

        unique_pages = CoverageService.calculate_unique_pages([(start_page, end_page)])
        norm_chapters = list(chapters or [])

        coverage_summary = {
            "total_pages_covered": unique_pages,
            "ranges": [{"start": start_page, "end": end_page}],
            "chapters": norm_chapters,
            "declared_at": utc_now().isoformat(),
        }

        norm_vis = "published" if visibility in ("public", "published") else visibility
        # 1. Create BookCopy with is_partial = True
        copy = await CatalogService.add_book_copy(
            db=db,
            book_id=book_id,
            owner_id=user_id,
            condition=condition,
            visibility=norm_vis,
            format_type="physical",
            is_partial=True,
            coverage_summary=coverage_summary,
            storage_location_private=storage_location_private,
            notes=notes,
            barcode=barcode,
        )

        # 2. Create CopyCoverageRange
        coverage_range = CopyCoverageRange(
            copy_id=copy.id,
            start_page=start_page,
            end_page=end_page,
            pagination_basis="edition_page_numbers",
            chapters=norm_chapters,
            source_description=source_description or "Bản photocopy học tập cá nhân",
            verification_status="unverified",
            notes=notes,
        )
        db.add(coverage_range)

        # 3. Custody Event
        custody = CustodyEvent(
            copy_id=copy.id,
            from_holder_id=None,
            to_holder_id=user_id,
            reason="partial_copy_declaration",
        )
        db.add(custody)

        # 4. Outbox Event
        outbox = OutboxEvent(
            event_type="PARTIAL_COPY_DECLARED",
            aggregate_type="book_copy",
            aggregate_id=copy.id,
            payload={
                "copy_id": copy.id,
                "owner_id": user_id,
                "book_id": book_id,
                "start_page": start_page,
                "end_page": end_page,
                "pages_count": unique_pages,
                "visibility": visibility,
            },
        )
        db.add(outbox)

        await db.flush()
        return copy, coverage_range

    @classmethod
    async def get_or_create_default_chapter(cls, db: AsyncSession, book_id: str) -> Chapter:
        """Get the first chapter of a book, or create Chapter 1 automatically if none exists."""
        stmt = select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.order_index)
        res = await db.execute(stmt)
        chapter = res.scalars().first()
        if not chapter:
            chapter = Chapter(
                book_id=book_id,
                chapter_number=1,
                chapter_code="1",
                order_index=1,
                title="Tài liệu & Học liệu chung",
                source="system_auto",
                verification_status="verified",
            )
            db.add(chapter)
            await db.flush()
        return chapter

    @classmethod
    async def create_digital_partial_material(
        cls,
        db: AsyncSession,
        user_id: str,
        book_id: str,
        chapter_id: Optional[str] = None,
        title: str = "Tài liệu học tập",
        resource_type: str = "digital_fragment", # file, link, digital_fragment, notes
        url: Optional[str] = None,
        file_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
        page_start: Optional[int] = None,
        page_end: Optional[int] = None,
        rights_basis: str = "personal_fair_use",
        consent_given: bool = True,
        provenance: Optional[str] = None,
        is_public: bool = False,
    ) -> ChapterResource:
        """
        Upload digital partial material (file or link) attached to a book chapter.
        Enforces fair-use consent, validates file size, and defaults to quarantine for rights review unless public.
        """
        if not consent_given:
            raise BoconicException(
                ErrorCode.VALIDATION_ERROR,
                "Bạn cần đồng ý cam kết tài liệu dùng cho mục đích học tập cá nhân theo chính sách bản quyền.",
                status_code=400,
            )

        user = await db.get(User, user_id)
        if not user:
            raise BoconicException(ErrorCode.NOT_FOUND, "Không tìm thấy người dùng.", status_code=404)

        book = await db.get(Book, book_id)
        if not book:
            raise BoconicException(ErrorCode.NOT_FOUND, "Không tìm thấy đầu sách.", status_code=404)

        # Chapter auto-resolution if not supplied or marked auto/default
        if not chapter_id or chapter_id in ("auto", "default"):
            chapter = await cls.get_or_create_default_chapter(db, book_id)
            chapter_id = chapter.id
        else:
            chapter = await db.get(Chapter, chapter_id)
            if not chapter or chapter.book_id != book_id:
                raise BoconicException(
                    ErrorCode.NOT_FOUND,
                    "Chương đã chọn không thuộc về đầu sách tương ứng.",
                    status_code=404,
                )

        if page_start is not None and page_end is not None:
            if page_start < 1 or page_end < page_start:
                raise BoconicException(
                    ErrorCode.VALIDATION_ERROR,
                    f"Khoảng trang không hợp lệ: {page_start} đến {page_end}.",
                    status_code=400,
                )

        if file_bytes:
            max_bytes = settings.UPLOAD_MAX_MB * 1024 * 1024
            if len(file_bytes) > max_bytes:
                raise BoconicException(
                    ErrorCode.VALIDATION_ERROR,
                    f"Tệp tải lên vượt quá dung lượng tối đa cho phép ({settings.UPLOAD_MAX_MB}MB).",
                    status_code=400,
                )

        file_path_str = None
        sha256_hash = None
        if file_bytes and filename:
            # Secure file persistence
            user_dir = STORAGE_DIR / user_id
            user_dir.mkdir(parents=True, exist_ok=True)
            safe_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.path.basename(filename)}"
            dest_path = user_dir / safe_name
            with open(dest_path, "wb") as f:
                f.write(file_bytes)
            file_path_str = str(dest_path)
            sha256_hash = hashlib.sha256(file_bytes).hexdigest()
            resource_type = "file"
        elif url and resource_type in ("digital_fragment", "file"):
            resource_type = "link"

        clean_title = (title or "").strip()
        if not clean_title and filename:
            clean_title = os.path.splitext(os.path.basename(filename))[0]
        if not clean_title:
            clean_title = "Tài liệu học tập"

        resource = ChapterResource(
            book_id=book_id,
            chapter_id=chapter_id,
            owner_id=user_id,
            title=clean_title,
            resource_type=resource_type,
            url=url.strip() if url else None,
            file_path=file_path_str,
            checksum_sha256=sha256_hash,
            page_start=page_start,
            page_end=page_end,
            rights_basis=rights_basis,
            allowed_actions=["view"],
            verification_status="verified" if is_public else "quarantine",
            is_public=is_public,
            version=1,
        )
        db.add(resource)
        await db.flush()

        # Outbox event
        outbox = OutboxEvent(
            event_type="PARTIAL_DIGITAL_UPLOADED",
            aggregate_type="chapter_resource",
            aggregate_id=resource.id,
            payload={
                "resource_id": resource.id,
                "owner_id": user_id,
                "book_id": book_id,
                "chapter_id": chapter_id,
                "title": clean_title,
                "resource_type": resource_type,
                "rights_basis": rights_basis,
                "verification_status": resource.verification_status,
                "is_public": is_public,
                "has_file": bool(file_path_str),
            },
        )
        db.add(outbox)
        await db.flush()
        return resource

    @classmethod
    async def get_user_partial_materials(cls, db: AsyncSession, user_id: str) -> Dict[str, Any]:
        """
        Retrieve all partial materials (both physical photocopy holdings and digital excerpts)
        owned by the specified user.
        """
        user = await db.get(User, user_id)
        if not user:
            raise BoconicException(ErrorCode.NOT_FOUND, "Không tìm thấy người dùng.", status_code=404)

        # 1. Physical partial copies
        copies_stmt = (
            select(BookCopy)
            .options(
                selectinload(BookCopy.book),
                selectinload(BookCopy.coverage_ranges),
                selectinload(BookCopy.current_holder),
            )
            .where(BookCopy.owner_id == user_id, BookCopy.is_partial == True)
            .order_by(desc(BookCopy.created_at))
        )
        copies_res = await db.execute(copies_stmt)
        copies = list(copies_res.scalars().all())

        physical_list = []
        for c in copies:
            ranges_data = []
            for r in c.coverage_ranges:
                ranges_data.append({
                    "range_id": r.id,
                    "start_page": r.start_page,
                    "end_page": r.end_page,
                    "pages_count": r.end_page - r.start_page + 1,
                    "chapters": r.chapters,
                    "source_description": r.source_description,
                    "verification_status": r.verification_status,
                })

            physical_list.append({
                "copy_id": c.id,
                "public_code": c.public_code,
                "barcode": c.barcode,
                "book_id": c.book_id,
                "book_title": c.book.title if c.book else "N/A",
                "condition": c.condition,
                "circulation_status": c.circulation_status,
                "visibility": c.visibility,
                "coverage_summary": c.coverage_summary,
                "ranges": ranges_data,
                "created_at": c.created_at.isoformat(),
            })

        # 2. Digital chapter resources
        resources_stmt = (
            select(ChapterResource)
            .options(
                selectinload(ChapterResource.chapter),
                selectinload(ChapterResource.book),
            )
            .where(ChapterResource.owner_id == user_id)
            .order_by(desc(ChapterResource.created_at))
        )
        res_res = await db.execute(resources_stmt)
        resources = list(res_res.scalars().all())

        digital_list = []
        for r in resources:
            book_title = "N/A"
            if r.book:
                book_title = r.book.title
            elif r.chapter and r.chapter.book:
                book_title = r.chapter.book.title

            filename_disp = os.path.basename(r.file_path) if r.file_path else None
            digital_list.append({
                "resource_id": r.id,
                "title": r.title,
                "resource_type": r.resource_type,
                "url": r.url,
                "filename": filename_disp,
                "has_file": bool(r.file_path and os.path.exists(r.file_path)),
                "page_start": r.page_start,
                "page_end": r.page_end,
                "chapter_id": r.chapter_id,
                "chapter_title": r.chapter.title if r.chapter else "N/A",
                "chapter_number": r.chapter.chapter_number if r.chapter else None,
                "book_id": r.book_id,
                "book_title": book_title,
                "rights_basis": r.rights_basis,
                "verification_status": r.verification_status,
                "is_public": r.is_public,
                "created_at": r.created_at.isoformat(),
            })

        return {
            "user_id": user_id,
            "total_physical_partial": len(physical_list),
            "total_digital_partial": len(digital_list),
            "physical_copies": physical_list,
            "digital_resources": digital_list,
        }

    @classmethod
    async def delete_physical_partial_copy(cls, db: AsyncSession, user_id: str, copy_id: str) -> None:
        """
        Delete a personal partial copy if it is not currently on loan or reserved.
        """
        copy = await db.get(BookCopy, copy_id)
        if not copy or copy.owner_id != user_id:
            raise BoconicException(ErrorCode.NOT_FOUND, "Không tìm thấy bản sách của bạn.", status_code=404)

        if not copy.is_partial:
            raise BoconicException(ErrorCode.VALIDATION_ERROR, "Chỉ có thể xóa tài liệu một phần qua thao tác này.", status_code=400)

        # Invariant check: cannot delete copy while locked in active/reserved loan
        if copy.circulation_status in ("on_loan", "reserved", "loaned"):
            raise BoconicException(
                ErrorCode.CONFLICT,
                "Không thể xóa bản sách đang trong giao dịch mượn hoặc đang giữ chỗ.",
                status_code=409,
            )

        loans_q = select(func.count(Loan.id)).where(Loan.copy_id == copy_id)
        if (await db.execute(loans_q)).scalar_one() > 0:
            raise BoconicException(
                ErrorCode.CONFLICT,
                "Không thể xóa bản sách đang có giao dịch mượn hoặc đã có lịch sử lưu thông.",
                status_code=409,
            )

        await db.delete(copy)
        await db.flush()

    @classmethod
    async def delete_digital_partial_resource(cls, db: AsyncSession, user_id: str, resource_id: str) -> None:
        """
        Delete personal digital partial resource and remove physical file if exists.
        """
        resource = await db.get(ChapterResource, resource_id)
        if not resource or resource.owner_id != user_id:
            raise BoconicException(ErrorCode.NOT_FOUND, "Không tìm thấy tài nguyên của bạn.", status_code=404)

        if resource.file_path and os.path.exists(resource.file_path):
            try:
                os.remove(resource.file_path)
            except Exception:
                pass

        await db.delete(resource)
        await db.flush()

    @classmethod
    async def get_digital_partial_file(
        cls,
        db: AsyncSession,
        user_id: str,
        resource_id: str,
        is_admin: bool = False,
    ) -> Tuple[str, str]:
        """
        Retrieve stored file path and safe filename for download.
        Authorized for the owning user or administrators.
        """
        resource = await db.get(ChapterResource, resource_id)
        if not resource:
            raise BoconicException(ErrorCode.NOT_FOUND, "Không tìm thấy tài nguyên.", status_code=404)

        if not is_admin and resource.owner_id != user_id:
            raise BoconicException(ErrorCode.FORBIDDEN, "Bạn không có quyền truy cập tệp này.", status_code=403)

        if not resource.file_path or not os.path.exists(resource.file_path):
            raise BoconicException(ErrorCode.NOT_FOUND, "Tài nguyên không có tệp đính kèm hoặc tệp đã bị xóa.", status_code=404)

        filename = os.path.basename(resource.file_path)
        return resource.file_path, filename

    @classmethod
    async def search_available_partial_materials(
        cls,
        db: AsyncSession,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Query published and available physical partial copies (photocopies) and verified digital fragments.
        """
        # 1. Available physical partial copies
        stmt = (
            select(BookCopy)
            .options(
                selectinload(BookCopy.book),
                selectinload(BookCopy.owner),
                selectinload(BookCopy.coverage_ranges),
            )
            .join(Book, BookCopy.book_id == Book.id)
            .where(
                BookCopy.is_partial == True,
                BookCopy.circulation_status == "available",
                BookCopy.visibility.in_(["published", "public"]),
            )
        )
        if query and query.strip():
            kw = f"%{query.strip()}%"
            stmt = stmt.where(
                (Book.title.ilike(kw)) | (Book.subject.ilike(kw)) | (Book.curriculum.ilike(kw))
            )

        stmt = stmt.order_by(BookCopy.created_at.desc()).limit(limit)
        res = await db.execute(stmt)
        copies = res.scalars().all()

        physical_list = []
        for c in copies:
            ranges = [
                {
                    "start_page": r.start_page,
                    "end_page": r.end_page,
                    "pages_count": (r.end_page - r.start_page + 1) if (r.start_page and r.end_page) else None,
                    "chapters": r.chapters or [],
                    "source": r.source_description,
                }
                for r in (c.coverage_ranges or [])
            ]
            physical_list.append({
                "copy_id": c.id,
                "public_code": c.public_code,
                "book_id": c.book_id,
                "book_title": c.book.title if c.book else "Sách không xác định",
                "author": c.book.author if c.book else "",
                "condition": c.condition,
                "maximum_loan_days": c.maximum_loan_days,
                "owner_id": c.owner_id,
                "owner_alias": c.owner.public_alias if c.owner else "Thành viên",
                "ranges": ranges,
                "coverage_summary": c.coverage_summary,
                "notes": c.notes,
            })

        # 2. Verified digital resources
        res_stmt = (
            select(ChapterResource)
            .options(
                selectinload(ChapterResource.chapter).selectinload(Chapter.book),
                selectinload(ChapterResource.owner),
            )
            .join(Chapter, ChapterResource.chapter_id == Chapter.id)
            .join(Book, Chapter.book_id == Book.id)
            .where(
                or_(
                    ChapterResource.verification_status == "verified",
                    and_(ChapterResource.is_public == True, ChapterResource.verification_status != "rejected"),
                )
            )
        )
        if query and query.strip():
            kw = f"%{query.strip()}%"
            res_stmt = res_stmt.where(
                (ChapterResource.title.ilike(kw)) | (Book.title.ilike(kw))
            )

        res_stmt = res_stmt.order_by(ChapterResource.created_at.desc()).limit(limit)
        digital_res = await db.execute(res_stmt)
        resources = digital_res.scalars().all()

        digital_list = []
        for r in resources:
            book_title = r.chapter.book.title if (r.chapter and r.chapter.book) else ""
            digital_list.append({
                "resource_id": r.id,
                "title": r.title,
                "book_title": book_title,
                "chapter_number": r.chapter.chapter_number if r.chapter else None,
                "chapter_title": r.chapter.title if r.chapter else None,
                "page_start": r.page_start,
                "page_end": r.page_end,
                "url": r.url,
                "has_file": bool(r.file_path),
                "rights_basis": r.rights_basis,
                "owner_alias": r.owner.public_alias if r.owner else "Thành viên",
            })

        return {
            "physical_copies": physical_list,
            "digital_resources": digital_list,
            "total_physical": len(physical_list),
            "total_digital": len(digital_list),
        }

    @classmethod
    async def get_all_community_available_resources(
        cls,
        db: AsyncSession,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Retrieve all available community library holdings (full books and partial copies)
        plus discoverable digital materials.
        """
        from app.db.models.catalog import BookAuthor
        # 1. All available copies
        stmt = (
            select(BookCopy)
            .options(
                selectinload(BookCopy.book).selectinload(Book.authors).selectinload(BookAuthor.author),
                selectinload(BookCopy.owner),
                selectinload(BookCopy.coverage_ranges),
            )
            .join(Book, BookCopy.book_id == Book.id)
            .where(
                BookCopy.circulation_status == "available",
                BookCopy.visibility.in_(["published", "public"]),
            )
            .order_by(BookCopy.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await db.execute(stmt)
        copies = res.scalars().all()

        available_copies = []
        for c in copies:
            author_names = ", ".join([a.author.name for a in (c.book.authors or [])]) if c.book else ""
            ranges = [
                {
                    "start_page": r.start_page,
                    "end_page": r.end_page,
                    "pages_count": (r.end_page - r.start_page + 1) if (r.start_page and r.end_page) else None,
                    "chapters": r.chapters or [],
                }
                for r in (c.coverage_ranges or [])
            ]
            available_copies.append({
                "copy_id": c.id,
                "public_code": c.public_code,
                "book_id": c.book_id,
                "book_title": c.book.title if c.book else "Sách",
                "author": author_names or (c.book.author if c.book else ""),
                "is_partial": c.is_partial,
                "condition": c.condition,
                "maximum_loan_days": c.maximum_loan_days,
                "owner_id": c.owner_id,
                "owner_alias": c.owner.public_alias if c.owner else "Thành viên",
                "ranges": ranges,
                "notes": c.notes,
            })

        # 2. Public / verified digital resources
        dig_stmt = (
            select(ChapterResource)
            .options(
                selectinload(ChapterResource.chapter).selectinload(Chapter.book),
                selectinload(ChapterResource.owner),
            )
            .where(
                or_(
                    ChapterResource.verification_status == "verified",
                    and_(ChapterResource.is_public == True, ChapterResource.verification_status != "rejected"),
                )
            )
            .order_by(ChapterResource.created_at.desc())
            .limit(limit)
        )
        dig_res = await db.execute(dig_stmt)
        digital_resources = [
            {
                "resource_id": r.id,
                "title": r.title,
                "book_title": r.chapter.book.title if (r.chapter and r.chapter.book) else "Tài liệu học tập",
                "chapter_number": r.chapter.chapter_number if r.chapter else None,
                "page_start": r.page_start,
                "page_end": r.page_end,
                "url": r.url,
                "has_file": bool(r.file_path),
                "owner_alias": r.owner.public_alias if r.owner else "Thành viên",
            }
            for r in dig_res.scalars().all()
        ]

        return {
            "available_copies": available_copies,
            "digital_resources": digital_resources,
            "total_copies": len(available_copies),
            "total_digital": len(digital_resources),
        }



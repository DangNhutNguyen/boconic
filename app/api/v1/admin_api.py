from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.auth import get_current_admin
from app.core.errors import BoconicException, ErrorCode
from app.db.models.catalog import Author, Book, BookAuthor, BookCopy
from app.db.models.community import CommunityRequest, Report
from app.db.models.custom_fields import CustomFieldDefinition
from app.db.models.identity import AdminAccount, User
from app.db.models.jobs import AuditLog, BackupJob, ImportJob
from app.db.models.lending import Loan, LoanEvent
from app.db.session import get_db
from app.services.audit import AuditService
from app.services.backup import BackupService
from app.services.catalog import CatalogService
from app.services.import_export import ImportExportService

router = APIRouter(prefix="/admin", tags=["Admin API"])

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class CreateBookDTO(BaseModel):
    title: str
    authors: List[str]
    publisher: Optional[str] = None
    publication_year: Optional[int] = None
    edition_label: Optional[str] = None
    language: str = "vi"
    subject: Optional[str] = None
    grade_level: Optional[int] = None
    curriculum: Optional[str] = None
    isbn: Optional[str] = None
    description: Optional[str] = None
    custom_data: Optional[Dict[str, Any]] = None

class CreateCustomFieldDTO(BaseModel):
    entity_type: str
    key: str
    label: str
    description: Optional[str] = None
    field_type: str
    required: bool = False
    options: Optional[List[Dict[str, str]]] = None

class ResolveDisputeDTO(BaseModel):
    resolution: str # active, returned, closed_lost
    reason: str

@router.get("/dashboard")
async def get_dashboard_metrics(
    admin: AdminAccount = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    now = utc_now()
    user_count = (await db.execute(select(func.count(User.id)))).scalar_one()
    book_count = (await db.execute(select(func.count(Book.id)))).scalar_one()
    copy_count = (await db.execute(select(func.count(BookCopy.id)))).scalar_one()
    available_copy_count = (
        await db.execute(select(func.count(BookCopy.id)).where(BookCopy.circulation_status == "available"))
    ).scalar_one()

    active_loans_count = (
        await db.execute(select(func.count(Loan.id)).where(Loan.status == "active"))
    ).scalar_one()
    reserved_loans_count = (
        await db.execute(select(func.count(Loan.id)).where(Loan.status == "reserved"))
    ).scalar_one()

    # Derived overdue condition: active and due_at < now
    overdue_loans_count = (
        await db.execute(select(func.count(Loan.id)).where(Loan.status == "active", Loan.due_at < now))
    ).scalar_one()

    open_requests_count = (
        await db.execute(select(func.count(CommunityRequest.id)).where(CommunityRequest.status == "open"))
    ).scalar_one()

    unresolved_reports_count = (
        await db.execute(select(func.count(Report.id)).where(Report.status.in_(["open", "reviewing"])))
    ).scalar_one()

    return {
        "users_count": user_count,
        "books_count": book_count,
        "copies_count": copy_count,
        "available_copies_count": available_copy_count,
        "active_loans_count": active_loans_count,
        "reserved_loans_count": reserved_loans_count,
        "overdue_loans_count": overdue_loans_count,
        "open_community_requests_count": open_requests_count,
        "unresolved_reports_count": unresolved_reports_count,
    }

@router.post("/books")
async def admin_create_book(
    dto: CreateBookDTO,
    admin: AdminAccount = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    book = await CatalogService.create_book(
        db=db,
        title=dto.title,
        authors=dto.authors,
        publisher=dto.publisher,
        publication_year=dto.publication_year,
        edition_label=dto.edition_label,
        language=dto.language,
        subject=dto.subject,
        grade_level=dto.grade_level,
        curriculum=dto.curriculum,
        isbn_raw=dto.isbn,
        description=dto.description,
        custom_data=dto.custom_data,
    )
    await AuditService.log_action(
        db,
        action="create_book",
        entity_type="book",
        entity_id=book.id,
        actor_id=admin.id,
        diff_after={"title": book.title, "isbn13": book.isbn13},
    )
    await db.commit()
    return {"id": book.id, "title": book.title, "isbn13": book.isbn13}

@router.post("/custom-fields")
async def admin_create_custom_field(
    dto: CreateCustomFieldDTO,
    admin: AdminAccount = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.entity_type == dto.entity_type,
            CustomFieldDefinition.key == dto.key,
        )
    )
    if existing.scalar_one_or_none():
        raise BoconicException(
            code=ErrorCode.ALREADY_EXISTS,
            message=f"Trường '{dto.key}' cho '{dto.entity_type}' đã tồn tại.",
            status_code=409,
        )

    field_def = CustomFieldDefinition(
        entity_type=dto.entity_type,
        key=dto.key,
        label=dto.label,
        description=dto.description,
        field_type=dto.field_type,
        required=dto.required,
        options=dto.options or [],
    )
    db.add(field_def)
    await db.flush()

    await AuditService.log_action(
        db,
        action="create_custom_field",
        entity_type="custom_field_definition",
        entity_id=field_def.id,
        actor_id=admin.id,
        diff_after={"key": field_def.key, "type": field_def.field_type},
    )
    await db.commit()
    return {"id": field_def.id, "key": field_def.key, "label": field_def.label}

@router.post("/loans/{loan_id}/resolve-dispute")
async def admin_resolve_dispute(
    loan_id: str,
    dto: ResolveDisputeDTO,
    admin: AdminAccount = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    loan = await db.get(Loan, loan_id)
    if not loan:
        raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy lượt mượn.")

    if loan.status != "disputed":
        raise BoconicException(code=ErrorCode.INVALID_STATE, message="Giao dịch không ở trạng thái tranh chấp.")

    valid_targets = {"active", "returned", "closed_lost"}
    if dto.resolution not in valid_targets:
        raise BoconicException(code=ErrorCode.VALIDATION_ERROR, message="Hướng giải quyết không hợp lệ.")

    old_status = loan.status
    loan.status = dto.resolution

    copy = await db.get(BookCopy, loan.copy_id)
    if copy:
        if dto.resolution == "returned":
            copy.circulation_status = "available"
            copy.current_holder_id = copy.owner_id
        elif dto.resolution == "closed_lost":
            copy.circulation_status = "lost"

    event = LoanEvent(
        loan_id=loan.id,
        actor_id=admin.id,
        action="resolve_dispute",
        from_status=old_status,
        to_status=dto.resolution,
        reason=dto.reason,
    )
    db.add(event)

    await AuditService.log_action(
        db,
        action="resolve_dispute",
        entity_type="loan",
        entity_id=loan.id,
        actor_id=admin.id,
        diff_before={"status": old_status},
        diff_after={"status": dto.resolution},
        reason=dto.reason,
    )

    await db.commit()
    return {"loan_id": loan.id, "status": loan.status, "message": "Tranh chấp đã được xử lý thành công."}

@router.post("/backups")
async def admin_trigger_backup(
    admin: AdminAccount = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    job = await BackupService.create_backup(db, created_by=admin.id)
    await AuditService.log_action(
        db,
        action="create_backup",
        entity_type="backup_job",
        entity_id=job.id,
        actor_id=admin.id,
        diff_after={"archive_path": job.archive_path, "checksum": job.checksum_sha256},
    )
    await db.commit()
    return {
        "job_id": job.id,
        "archive_path": job.archive_path,
        "checksum_sha256": job.checksum_sha256,
        "size_bytes": job.size_bytes,
        "created_at": job.created_at,
    }

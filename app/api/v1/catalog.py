from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BoconicException, ErrorCode
from app.db.session import get_db
from app.services.catalog import CatalogService
from app.services.community import CommunityService

router = APIRouter(prefix="/catalog", tags=["Public Catalog"])

class PublicCopyDTO(BaseModel):
    id: str
    public_code: str
    condition: str
    circulation_status: str
    maximum_loan_days: int
    lending_policy: str
    notes: Optional[str] = None

class PublicBookDTO(BaseModel):
    id: str
    title: str
    subtitle: Optional[str] = None
    publisher: Optional[str] = None
    publication_year: Optional[int] = None
    edition_label: Optional[str] = None
    language: str
    subject: Optional[str] = None
    grade_level: Optional[int] = None
    curriculum: Optional[str] = None
    isbn13: Optional[str] = None
    description: Optional[str] = None
    available_copies_count: int
    authors: List[str]

@router.get("/books", response_model=Dict[str, Any])
async def search_public_books(
    q: Optional[str] = Query(None, description="Search by title, author, publisher, ISBN"),
    subject: Optional[str] = Query(None),
    grade: Optional[int] = Query(None, ge=1, le=12),
    curriculum: Optional[str] = Query(None),
    available_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    books, total = await CatalogService.search_books(
        db, query=q, subject=subject, grade_level=grade, curriculum=curriculum,
        available_only=available_only, limit=limit, offset=offset
    )

    items = []
    for b in books:
        authors = [a.author.name for a in b.authors]
        available_count = sum(1 for c in b.copies if c.circulation_status == "available")
        items.append(
            PublicBookDTO(
                id=b.id,
                title=b.title,
                subtitle=b.subtitle,
                publisher=b.publisher,
                publication_year=b.publication_year,
                edition_label=b.edition_label,
                language=b.language,
                subject=b.subject,
                grade_level=b.grade_level,
                curriculum=b.curriculum,
                isbn13=b.isbn13,
                description=b.description,
                available_copies_count=available_count,
                authors=authors,
            )
        )

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }

@router.get("/books/{book_id}")
async def get_public_book_detail(book_id: str, db: AsyncSession = Depends(get_db)):
    book = await CatalogService.get_book_detail(db, book_id)
    if not book:
        raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy đầu sách.", status_code=404)

    copies = [
        PublicCopyDTO(
            id=c.id,
            public_code=c.public_code,
            condition=c.condition,
            circulation_status=c.circulation_status,
            maximum_loan_days=c.maximum_loan_days,
            lending_policy=c.lending_policy,
            notes=c.notes,
        )
        for c in book.copies
    ]

    chapters = [
        {
            "chapter_number": ch.chapter_number,
            "title": ch.title,
            "page_start": ch.page_start,
            "page_end": ch.page_end,
            "topics": ch.topics,
        }
        for ch in sorted(book.chapters, key=lambda x: x.chapter_number)
    ]

    return {
        "id": book.id,
        "title": book.title,
        "subtitle": book.subtitle,
        "publisher": book.publisher,
        "publication_year": book.publication_year,
        "edition_label": book.edition_label,
        "language": book.language,
        "subject": book.subject,
        "grade_level": book.grade_level,
        "curriculum": book.curriculum,
        "isbn13": book.isbn13,
        "description": book.description,
        "authors": [a.author.name for a in book.authors],
        "copies": copies,
        "chapters": chapters,
    }

@router.get("/resources")
async def list_verified_resources(db: AsyncSession = Depends(get_db)):
    resources = await CommunityService.get_verified_resources(db, required_action="link")
    return [
        {
            "id": r.id,
            "title": r.title,
            "resource_type": r.resource_type,
            "source_name": r.source_name,
            "source_url": r.source_url,
            "license_name": r.license_name,
            "license_url": r.license_url,
            "allowed_actions": r.allowed_actions,
        }
        for r in resources
    ]


class ChapterProposalCreateDTO(BaseModel):
    user_id: str
    action: str = "create" # create, update, delete, reorder
    base_version: int = 1
    proposed_data: Dict[str, Any]
    reason: str
    source_evidence: Optional[str] = None
    chapter_id: Optional[str] = None


class ChapterResourceCreateDTO(BaseModel):
    user_id: str
    title: str
    resource_type: str = "link"
    url: Optional[str] = None
    file_path: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    rights_basis: str = "personal_fair_use"
    allowed_actions: Optional[List[str]] = None


class ChapterWatchDTO(BaseModel):
    user_id: str
    notify_preference: str = "all"


@router.get("/books/{book_id}/chapters")
async def get_book_chapters(
    book_id: str,
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve canonical chapters for a specific book edition."""
    from app.services.chapter_service import ChapterService
    return await ChapterService.get_book_chapters(db, book_id=book_id, include_archived=include_archived)


@router.post("/books/{book_id}/chapter-proposals")
async def create_chapter_proposal(
    book_id: str,
    dto: ChapterProposalCreateDTO,
    db: AsyncSession = Depends(get_db),
):
    """Submit a proposal to add, update, delete or reorder chapters."""
    from app.services.chapter_service import ChapterService
    proposal = await ChapterService.create_chapter_proposal(
        db=db,
        user_id=dto.user_id,
        book_id=book_id,
        action=dto.action,
        proposed_data=dto.proposed_data,
        reason=dto.reason,
        source_evidence=dto.source_evidence,
        chapter_id=dto.chapter_id,
        base_version=dto.base_version,
    )
    await db.commit()
    return {
        "status": "success",
        "proposal_id": proposal.id,
        "action": proposal.action,
        "proposal_status": proposal.status,
    }


@router.post("/chapters/{chapter_id}/resources")
async def add_chapter_resource(
    chapter_id: str,
    dto: ChapterResourceCreateDTO,
    db: AsyncSession = Depends(get_db),
):
    """Add a digital resource to a chapter (quarantined by default pending rights review)."""
    from app.services.chapter_service import ChapterService
    resource = await ChapterService.add_chapter_resource(
        db=db,
        user_id=dto.user_id,
        chapter_id=chapter_id,
        title=dto.title,
        resource_type=dto.resource_type,
        url=dto.url,
        file_path=dto.file_path,
        page_start=dto.page_start,
        page_end=dto.page_end,
        rights_basis=dto.rights_basis,
        allowed_actions=dto.allowed_actions,
    )
    await db.commit()
    return {
        "status": "success",
        "resource_id": resource.id,
        "verification_status": resource.verification_status,
        "is_public": resource.is_public,
    }


@router.post("/chapters/{chapter_id}/watch")
async def watch_chapter(
    chapter_id: str,
    book_id: str = Query(..., description="Book ID"),
    dto: ChapterWatchDTO = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Subscribe to alerts when new sources become available for a missing chapter."""
    from app.services.chapter_service import ChapterService
    watch = await ChapterService.watch_chapter(
        db=db,
        user_id=dto.user_id,
        book_id=book_id,
        chapter_id=chapter_id,
        notify_preference=dto.notify_preference,
    )
    await db.commit()
    return {"status": "success", "is_active": watch.is_active}


@router.delete("/chapters/{chapter_id}/watch")
async def unwatch_chapter(
    chapter_id: str,
    book_id: str = Query(...),
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Unsubscribe from chapter alerts."""
    from app.services.chapter_service import ChapterService
    success = await ChapterService.unwatch_chapter(
        db=db, user_id=user_id, book_id=book_id, chapter_id=chapter_id
    )
    await db.commit()
    return {"status": "success", "unwatched": success}


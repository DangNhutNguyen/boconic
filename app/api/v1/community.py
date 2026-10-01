"""
Public and authenticated REST API endpoints for Community Requests (Needs),
Support Offers, Authorized Collections, and Community Library.
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import BoconicException, ErrorCode
from app.db.models.catalog import Book, BookCopy
from app.db.models.community import (
    AuthorizedCollection, CommunityRequest, RequestMatch, Resource, SupportOffer
)
from app.db.models.identity import User
from app.db.session import get_db
from app.services.assembly_service import AssemblyService
from app.services.coverage_service import CoverageService
from app.services.need_service import NeedService


router = APIRouter(prefix="/community-requests", tags=["Community Requests & Offers"])
collections_router = APIRouter(prefix="/collections", tags=["Authorized Collections"])
community_library_router = APIRouter(prefix="/community-library", tags=["Community Library"])


# DTOs
class CreateNeedRequestDTO(BaseModel):
    user_id: str
    title_query: str
    book_id: Optional[str] = None
    isbn: Optional[str] = None
    edition_label: Optional[str] = None
    scope_type: str = "full_book"
    page_range: Optional[List[int]] = None
    pagination_basis: Optional[str] = None
    quantity: int = 1
    duration_days_needed: int = 14
    coarse_location: Optional[str] = None
    fulfillment_preference: str = "lend"
    urgency: str = "normal"
    urgency_reason: Optional[str] = None
    accepted_conditions: Optional[List[str]] = None
    edition_match_strict: bool = False
    description: Optional[str] = None
    visibility: str = "public"


class CreateOfferRequestDTO(BaseModel):
    provider_user_id: str
    offer_type: str
    copy_id: Optional[str] = None
    resource_id: Optional[str] = None
    covered_ranges: Optional[List[List[int]]] = None
    proposed_duration_days: int = 14
    coarse_pickup_area: Optional[str] = None
    message: Optional[str] = None
    rights_snapshot: Optional[Dict[str, Any]] = None


class SelectOfferRequestDTO(BaseModel):
    requester_id: str


class WithdrawOfferRequestDTO(BaseModel):
    provider_user_id: str
    reason: Optional[str] = None


class CreateCollectionDTO(BaseModel):
    created_by: str
    book_id: str
    title: str
    target_scope: Dict[str, Any]
    rights_basis: str
    allowed_actions: List[str]
    recipient_scope: str = "community"


class SubmitContributionDTO(BaseModel):
    contributor_id: str
    start_page: int
    end_page: int
    chapters: Optional[List[str]] = None
    source_type: str = "physical_scan"
    file_path: Optional[str] = None
    checksum_sha256: Optional[str] = None
    consent_given: bool = True


# Endpoints for Community Requests
@router.post("")
async def create_community_request(
    dto: CreateNeedRequestDTO,
    db: AsyncSession = Depends(get_db),
):
    need = await NeedService.create_need(
        db=db,
        user_id=dto.user_id,
        title_query=dto.title_query,
        book_id=dto.book_id,
        isbn=dto.isbn,
        edition_label=dto.edition_label,
        scope_type=dto.scope_type,
        page_range=dto.page_range,
        pagination_basis=dto.pagination_basis,
        quantity=dto.quantity,
        duration_days_needed=dto.duration_days_needed,
        coarse_location=dto.coarse_location,
        fulfillment_preference=dto.fulfillment_preference,
        urgency=dto.urgency,
        urgency_reason=dto.urgency_reason,
        accepted_conditions=dto.accepted_conditions,
        edition_match_strict=dto.edition_match_strict,
        description=dto.description,
        visibility=dto.visibility,
        status="open",
    )
    await db.commit()
    return {
        "id": need.id,
        "title_query": need.title_query,
        "status": need.status,
        "scope_type": need.scope_type,
        "quantity": need.quantity,
        "version": need.version,
    }


@router.get("")
async def list_community_requests(
    status: Optional[str] = "open",
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CommunityRequest)
    if status:
        stmt = stmt.where(CommunityRequest.status == status)
    stmt = stmt.order_by(CommunityRequest.created_at.desc()).offset(offset).limit(limit)
    res = await db.execute(stmt)
    needs = res.scalars().all()

    return [
        {
            "id": n.id,
            "title_query": n.title_query,
            "isbn": n.isbn,
            "edition_label": n.edition_label,
            "scope_type": n.scope_type,
            "quantity": n.quantity,
            "quantity_fulfilled": n.quantity_fulfilled,
            "duration_days_needed": n.duration_days_needed,
            "coarse_location": n.coarse_location,
            "urgency": n.urgency,
            "status": n.status,
            "created_at": n.created_at.isoformat(),
        }
        for n in needs
    ]


@router.get("/{need_id}")
async def get_community_request_detail(
    need_id: str,
    db: AsyncSession = Depends(get_db),
):
    need = await db.get(CommunityRequest, need_id)
    if not need:
        raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy nhu cầu sách.", status_code=404)

    # Count offers
    offers_res = await db.execute(
        select(func.count(SupportOffer.id)).where(SupportOffer.need_id == need_id)
    )
    offers_count = offers_res.scalar_one() or 0

    # Count eligible matched owners
    matches_res = await db.execute(
        select(func.count(RequestMatch.id)).where(RequestMatch.need_id == need_id)
    )
    matches_count = matches_res.scalar_one() or 0

    return {
        "id": need.id,
        "title_query": need.title_query,
        "isbn": need.isbn,
        "edition_label": need.edition_label,
        "scope_type": need.scope_type,
        "page_range": need.page_range,
        "pagination_basis": need.pagination_basis,
        "quantity": need.quantity,
        "quantity_fulfilled": need.quantity_fulfilled,
        "duration_days_needed": need.duration_days_needed,
        "coarse_location": need.coarse_location,
        "urgency": need.urgency,
        "status": need.status,
        "version": need.version,
        "eligible_owners_count": matches_count,
        "offers_count": offers_count,
        "created_at": need.created_at.isoformat(),
    }


@router.get("/{need_id}/offers")
async def list_need_offers(
    need_id: str,
    db: AsyncSession = Depends(get_db),
):
    offers = await NeedService.get_need_offers(db, need_id)
    return [
        {
            "id": o.id,
            "offer_type": o.offer_type,
            "copy_id": o.copy_id,
            "resource_id": o.resource_id,
            "covered_ranges": o.covered_ranges,
            "proposed_duration_days": o.proposed_duration_days,
            "coarse_pickup_area": o.coarse_pickup_area,
            "message": o.message,
            "status": o.status,
            "created_at": o.created_at.isoformat(),
        }
        for o in offers
    ]


@router.post("/{need_id}/offers")
async def create_need_offer(
    need_id: str,
    dto: CreateOfferRequestDTO,
    db: AsyncSession = Depends(get_db),
):
    offer = await NeedService.create_offer(
        db=db,
        need_id=need_id,
        provider_user_id=dto.provider_user_id,
        offer_type=dto.offer_type,
        copy_id=dto.copy_id,
        resource_id=dto.resource_id,
        covered_ranges=dto.covered_ranges,
        proposed_duration_days=dto.proposed_duration_days,
        coarse_pickup_area=dto.coarse_pickup_area,
        message=dto.message,
        rights_snapshot=dto.rights_snapshot,
    )
    await db.commit()
    return {
        "id": offer.id,
        "need_id": offer.need_id,
        "offer_type": offer.offer_type,
        "status": offer.status,
    }


# Endpoints for Offers action
offers_action_router = APIRouter(prefix="/offers", tags=["Offers Action"])


@offers_action_router.post("/{offer_id}/select")
async def select_offer_endpoint(
    offer_id: str,
    dto: SelectOfferRequestDTO,
    db: AsyncSession = Depends(get_db),
):
    offer, loan = await NeedService.select_offer(
        db=db,
        offer_id=offer_id,
        requester_id=dto.requester_id,
    )
    await db.commit()
    return {
        "offer_id": offer.id,
        "status": offer.status,
        "loan_id": loan.id if loan else None,
        "loan_status": loan.status if loan else None,
        "reservation_expires_at": loan.reservation_expires_at.isoformat() if loan and loan.reservation_expires_at else None,
    }


@offers_action_router.post("/{offer_id}/withdraw")
async def withdraw_offer_endpoint(
    offer_id: str,
    dto: WithdrawOfferRequestDTO,
    db: AsyncSession = Depends(get_db),
):
    offer = await NeedService.withdraw_offer(
        db=db,
        offer_id=offer_id,
        provider_user_id=dto.provider_user_id,
        reason=dto.reason,
    )
    await db.commit()
    return {"offer_id": offer.id, "status": offer.status}


# Community Library Endpoint
@community_library_router.get("")
async def search_community_library(
    q: Optional[str] = None,
    isbn: Optional[str] = None,
    subject: Optional[str] = None,
    grade_level: Optional[int] = None,
    format_type: Optional[str] = None,
    available_only: bool = True,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """
    Search published copies in the community library.
    Excludes private holdings and unverified personal metadata.
    """
    stmt = (
        select(BookCopy, Book)
        .join(Book, BookCopy.book_id == Book.id)
        .where(BookCopy.visibility.in_(["published", "public"]))
    )
    if available_only:
        stmt = stmt.where(BookCopy.circulation_status == "available")
    if format_type:
        stmt = stmt.where(BookCopy.format == format_type)
    if q:
        stmt = stmt.where(Book.title.ilike(f"%{q.strip()}%"))
    if isbn:
        stmt = stmt.where(Book.isbn == isbn.strip())
    if subject:
        stmt = stmt.where(Book.subject.ilike(f"%{subject.strip()}%"))
    if grade_level is not None:
        stmt = stmt.where(Book.grade_level == grade_level)

    stmt = stmt.order_by(Book.title.asc()).offset(offset).limit(limit)
    res = await db.execute(stmt)
    rows = res.all()

    return [
        {
            "copy_id": copy.id,
            "book_id": book.id,
            "title": book.title,
            "author": book.author,
            "isbn": book.isbn,
            "edition_label": book.edition_label,
            "format": copy.format,
            "condition": copy.condition,
            "circulation_status": copy.circulation_status,
            "is_partial": copy.is_partial,
            "coverage_summary": copy.coverage_summary,
            "available_from": copy.available_from.isoformat() if copy.available_from else None,
        }
        for copy, book in rows
    ]


# Authorized Collections Endpoints
@collections_router.post("")
async def create_collection_endpoint(
    dto: CreateCollectionDTO,
    db: AsyncSession = Depends(get_db),
):
    col = await AssemblyService.create_collection(
        db=db,
        book_id=dto.book_id,
        title=dto.title,
        target_scope=dto.target_scope,
        rights_basis=dto.rights_basis,
        allowed_actions=dto.allowed_actions,
        recipient_scope=dto.recipient_scope,
        created_by=dto.created_by,
    )
    await db.commit()
    return {
        "id": col.id,
        "title": col.title,
        "status": col.status,
    }


@collections_router.post("/{collection_id}/contributions")
async def submit_collection_contribution(
    collection_id: str,
    dto: SubmitContributionDTO,
    db: AsyncSession = Depends(get_db),
):
    contrib = await AssemblyService.submit_contribution(
        db=db,
        collection_id=collection_id,
        contributor_id=dto.contributor_id,
        start_page=dto.start_page,
        end_page=dto.end_page,
        chapters=dto.chapters,
        source_type=dto.source_type,
        file_path=dto.file_path,
        checksum_sha256=dto.checksum_sha256,
        consent_given=dto.consent_given,
    )
    await db.commit()
    return {
        "contribution_id": contrib.id,
        "collection_id": contrib.collection_id,
        "verification_status": contrib.verification_status,
        "start_page": contrib.start_page,
        "end_page": contrib.end_page,
    }


@collections_router.get("/{collection_id}/assembly-preview")
async def preview_collection_assembly(
    collection_id: str,
    db: AsyncSession = Depends(get_db),
):
    preview = await AssemblyService.preview_assembly(db, collection_id)
    return preview

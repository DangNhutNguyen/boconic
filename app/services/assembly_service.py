"""
Service for managing Authorized Contribution Collections and Assembly Pipeline.
Strictly gated by copyright/IP verification: assembly is disabled by default for unverified works.
"""
from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BoconicException, ErrorCode
from app.db.models.catalog import Book
from app.db.models.community import (
    AssemblyJob, AuthorizedCollection, CollectionContribution
)
from app.services.coverage_service import CoverageService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AssemblyService:
    @classmethod
    async def create_collection(
        cls,
        db: AsyncSession,
        book_id: str,
        title: str,
        target_scope: Dict[str, Any],
        rights_basis: str,
        allowed_actions: List[str],
        recipient_scope: str,
        created_by: str,
    ) -> AuthorizedCollection:
        """Create an Authorized Collection plan."""
        book = await db.get(Book, book_id)
        if not book:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy đầu sách.", status_code=404)

        collection = AuthorizedCollection(
            book_id=book_id,
            title=title.strip(),
            target_scope=target_scope,
            rights_basis=rights_basis.strip(),
            allowed_actions=allowed_actions,
            recipient_scope=recipient_scope,
            status="pending_verification",
            created_by=created_by,
        )
        db.add(collection)
        await db.flush()
        return collection

    @classmethod
    async def verify_collection(
        cls,
        db: AsyncSession,
        collection_id: str,
        verifier_id: str,
        status: str = "active",
    ) -> AuthorizedCollection:
        """Admin verifies rights and activates the collection."""
        collection = await db.get(AuthorizedCollection, collection_id)
        if not collection:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy bộ sưu tập.", status_code=404)

        collection.status = status
        collection.verified_by = verifier_id
        collection.verified_at = utc_now()
        await db.flush()
        return collection

    @classmethod
    async def submit_contribution(
        cls,
        db: AsyncSession,
        collection_id: str,
        contributor_id: str,
        start_page: int,
        end_page: int,
        chapters: Optional[List[str]] = None,
        source_type: str = "physical_scan",
        file_path: Optional[str] = None,
        checksum_sha256: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        consent_given: bool = True,
    ) -> CollectionContribution:
        """
        Submit a verified segment contribution.
        Rejects submission if collection is not active or consent is false.
        """
        collection = await db.get(AuthorizedCollection, collection_id)
        if not collection or collection.status != "active":
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message="Bộ sưu tập này chưa được duyệt quyền hoặc không ở trạng thái hoạt động.",
                status_code=403,
            )

        if not consent_given:
            raise BoconicException(
                code=ErrorCode.BAD_REQUEST,
                message="Cần có sự đồng ý (consent) của người đóng góp.",
                status_code=400,
            )

        if start_page < 1 or end_page < start_page:
            raise BoconicException(
                code=ErrorCode.BAD_REQUEST,
                message="Khoảng trang không hợp lệ (cần 1 <= start <= end).",
                status_code=400,
            )

        contribution = CollectionContribution(
            collection_id=collection_id,
            contributor_id=contributor_id,
            source_type=source_type,
            start_page=start_page,
            end_page=end_page,
            chapters=chapters or [],
            file_path=file_path,
            checksum_sha256=checksum_sha256,
            file_size_bytes=file_size_bytes,
            consent_given=True,
            verification_status="pending",
        )
        db.add(contribution)
        await db.flush()
        return contribution

    @classmethod
    async def verify_contribution(
        cls,
        db: AsyncSession,
        contribution_id: str,
        verifier_id: str,
        is_approved: bool,
        rejection_reason: Optional[str] = None,
    ) -> CollectionContribution:
        """Verify an individual contribution."""
        contrib = await db.get(CollectionContribution, contribution_id)
        if not contrib:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy đóng góp.", status_code=404)

        if is_approved:
            contrib.verification_status = "verified"
            contrib.verified_by = verifier_id
            contrib.verified_at = utc_now()
        else:
            contrib.verification_status = "rejected"
            contrib.rejection_reason = rejection_reason

        await db.flush()
        return contrib

    @classmethod
    async def preview_assembly(
        cls,
        db: AsyncSession,
        collection_id: str,
    ) -> Dict[str, Any]:
        """Preview coverage and overlap across all verified contributions."""
        collection = await db.get(AuthorizedCollection, collection_id)
        if not collection:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy bộ sưu tập.", status_code=404)

        contrib_res = await db.execute(
            select(CollectionContribution).where(
                CollectionContribution.collection_id == collection_id,
                CollectionContribution.verification_status == "verified",
            )
        )
        verified_contribs = list(contrib_res.scalars().all())

        source_ranges = [(c.start_page, c.end_page) for c in verified_contribs]
        target_ranges = []
        if collection.target_scope and "start_page" in collection.target_scope and "end_page" in collection.target_scope:
            target_ranges = [(int(collection.target_scope["start_page"]), int(collection.target_scope["end_page"]))]

        analysis = CoverageService.analyze_coverage(
            target_ranges=target_ranges,
            source_ranges=source_ranges,
        )

        return {
            "collection_id": collection.id,
            "title": collection.title,
            "status": collection.status,
            "verified_contributions_count": len(verified_contribs),
            "coverage_analysis": analysis,
        }

    @classmethod
    async def run_assembly_job(
        cls,
        db: AsyncSession,
        collection_id: str,
        requested_by: str,
    ) -> AssemblyJob:
        """
        Assemble verified contributions into a final manifest and output.
        Fails if collection rights are not active or required coverage has critical gaps.
        """
        collection = await db.get(AuthorizedCollection, collection_id)
        if not collection or collection.status != "active":
            raise BoconicException(
                code=ErrorCode.INVALID_STATE,
                message="Chỉ có thể tổng hợp bộ sưu tập đã được duyệt quyền và đang active.",
                status_code=403,
            )

        preview = await cls.preview_assembly(db, collection_id)
        analysis = preview["coverage_analysis"]

        # Build manifest
        contrib_res = await db.execute(
            select(CollectionContribution).where(
                CollectionContribution.collection_id == collection_id,
                CollectionContribution.verification_status == "verified",
            )
        )
        verified_contribs = list(contrib_res.scalars().all())

        manifest_entries = []
        for c in verified_contribs:
            manifest_entries.append({
                "contribution_id": c.id,
                "contributor_id": c.contributor_id,
                "page_range": [c.start_page, c.end_page],
                "checksum_sha256": c.checksum_sha256,
                "source_type": c.source_type,
            })

        has_gaps = bool(analysis.get("gaps"))
        job_status = "ready" if not has_gaps else "needs_review"

        job = AssemblyJob(
            collection_id=collection_id,
            requested_by=requested_by,
            status=job_status,
            manifest_data={
                "collection_title": collection.title,
                "rights_basis": collection.rights_basis,
                "allowed_actions": collection.allowed_actions,
                "recipient_scope": collection.recipient_scope,
                "entries": manifest_entries,
                "version": 1,
            },
            coverage_summary=analysis,
            completed_at=utc_now() if job_status == "ready" else None,
        )
        db.add(job)
        await db.flush()
        return job

    @classmethod
    async def revoke_collection(
        cls,
        db: AsyncSession,
        collection_id: str,
        reason: str,
    ) -> AuthorizedCollection:
        """Revoke rights for a collection and invalidate pending/ready assembly jobs."""
        collection = await db.get(AuthorizedCollection, collection_id)
        if not collection:
            raise BoconicException(code=ErrorCode.NOT_FOUND, message="Không tìm thấy bộ sưu tập.", status_code=404)

        collection.status = "revoked"

        # Invalidate jobs
        jobs_res = await db.execute(
            select(AssemblyJob).where(AssemblyJob.collection_id == collection_id)
        )
        for job in jobs_res.scalars().all():
            job.status = "revoked"
            job.failure_reason = f"Collection revoked: {reason}"

        await db.flush()
        return collection

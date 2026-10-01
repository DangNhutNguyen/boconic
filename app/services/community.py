from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BoconicException, ErrorCode
from app.db.models.catalog import Book
from app.db.models.community import CommunityRequest, Resource, SchoolShortage
from app.db.models.organization import Organization

class CommunityService:
    @classmethod
    async def create_community_request(
        cls,
        db: AsyncSession,
        user_id: str,
        title_query: str,
        grade_level: Optional[int] = None,
        subject: Optional[str] = None,
        curriculum: Optional[str] = None,
        topics: Optional[List[str]] = None,
        quantity: int = 1,
        coarse_location: Optional[str] = None,
        fulfillment_preference: str = "lend",
    ) -> CommunityRequest:
        req = CommunityRequest(
            user_id=user_id,
            title_query=title_query.strip(),
            grade_level=grade_level,
            subject=subject.strip() if subject else None,
            curriculum=curriculum.strip() if curriculum else None,
            topics=topics or [],
            quantity=quantity,
            coarse_location=coarse_location,
            fulfillment_preference=fulfillment_preference,
            status="open",
        )
        db.add(req)
        await db.flush()
        return req

    @classmethod
    async def create_resource(
        cls,
        db: AsyncSession,
        title: str,
        resource_type: str,
        source_name: str,
        source_url: str,
        license_name: str,
        license_url: Optional[str] = None,
        rights_basis: str = "",
        allowed_actions: Optional[List[str]] = None,
        evidence: Optional[str] = None,
    ) -> Resource:
        """
        Create a digital resource with strict 3-tier permissions:
        allowed_actions may include 'metadata', 'link', 'distribute_file'
        """
        valid_actions = {"metadata", "link", "distribute_file"}
        actions = [a for a in (allowed_actions or ["metadata"]) if a in valid_actions]

        res = Resource(
            title=title.strip(),
            resource_type=resource_type,
            source_name=source_name.strip(),
            source_url=source_url.strip(),
            license_name=license_name.strip(),
            license_url=license_url.strip() if license_url else None,
            rights_basis=rights_basis.strip(),
            allowed_actions=actions,
            evidence=evidence,
            verification_status="pending",
            takedown_status="none",
        )
        db.add(res)
        await db.flush()
        return res

    @classmethod
    async def get_verified_resources(
        cls, db: AsyncSession, required_action: str = "link"
    ) -> List[Resource]:
        """Fetch only verified resources that have not been taken down and allow the required action."""
        stmt = (
            select(Resource)
            .where(
                Resource.verification_status == "verified",
                Resource.takedown_status == "none",
            )
            .order_by(Resource.created_at.desc())
        )
        res = await db.execute(stmt)
        all_resources = list(res.scalars().all())
        return [r for r in all_resources if required_action in (r.allowed_actions or [])]

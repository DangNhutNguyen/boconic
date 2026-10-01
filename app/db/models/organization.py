import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, String, Text, JSON
)
from sqlalchemy.orm import relationship
from app.db.base import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    kind = Column(String(32), nullable=False, default="library") # library, school, community_group
    public_address = Column(String(255), nullable=True)
    city = Column(String(128), nullable=False, default="TP. Hồ Chí Minh")
    district = Column(String(128), nullable=True)
    website = Column(String(255), nullable=True)
    public_phone = Column(String(32), nullable=True)
    opening_hours = Column(String(255), nullable=True)
    verification_status = Column(String(32), nullable=False, default="unverified") # unverified, verified
    verification_source = Column(String(255), nullable=True)
    inventory_policy = Column(Text, nullable=True)
    custom_data = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    members = relationship("OrganizationMember", back_populates="organization", cascade="all, delete-orphan")
    shortages = relationship("SchoolShortage", back_populates="organization", cascade="all, delete-orphan")

class OrganizationMember(Base):
    __tablename__ = "organization_members"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=False, default="member") # manager, coordinator, member
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    organization = relationship("Organization", back_populates="members")
    user = relationship("User")

class Party(Base):
    __tablename__ = "parties"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND organization_id IS NULL) OR (user_id IS NULL AND organization_id IS NOT NULL)",
            name="chk_party_single_entity"
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    kind = Column(String(32), nullable=False) # user, organization
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    user = relationship("User")
    organization = relationship("Organization")

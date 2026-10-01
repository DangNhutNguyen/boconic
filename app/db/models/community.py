import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, JSON
)
from sqlalchemy.orm import relationship
from app.db.base import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class CommunityRequest(Base):
    __tablename__ = "community_requests"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    book_id = Column(String(36), ForeignKey("books.id", ondelete="SET NULL"), nullable=True)
    title_query = Column(String(255), nullable=False)
    isbn = Column(String(32), nullable=True, index=True)
    edition_label = Column(String(128), nullable=True)
    grade_level = Column(Integer, nullable=True)
    subject = Column(String(64), nullable=True)
    curriculum = Column(String(64), nullable=True)
    topics = Column(JSON, nullable=False, default=list)
    scope_type = Column(String(32), nullable=False, default="full") # full, chapters, page_range
    page_range = Column(JSON, nullable=False, default=dict) # {"start": 1, "end": 50, "basis": "print"}
    pagination_basis = Column(String(64), nullable=True)
    quantity = Column(Integer, nullable=False, default=1)
    quantity_fulfilled = Column(Integer, nullable=False, default=0)
    deadline = Column(DateTime(timezone=True), nullable=True)
    duration_days_needed = Column(Integer, nullable=False, default=14)
    urgency = Column(String(32), nullable=False, default="normal") # low, normal, urgent
    urgency_reason = Column(String(255), nullable=True)
    coarse_location = Column(String(128), nullable=True)
    fulfillment_preference = Column(String(32), nullable=False, default="lend") # lend, donate, physical_pickup, digital_authorized, any
    accepted_conditions = Column(JSON, nullable=False, default=list) # e.g. ["new", "like_new", "good", "fair"]
    edition_match_strict = Column(Boolean, nullable=False, default=True)
    target_chapters = Column(JSON, nullable=False, default=list) # List of chapter IDs or chapter codes requested
    target_snapshot = Column(JSON, nullable=False, default=dict) # Snapshot of requested chapters/pages at publish time
    revalidation_required = Column(Boolean, nullable=False, default=False) # Flagged if chapter ranges change
    description = Column(Text, nullable=True)
    visibility = Column(String(32), nullable=False, default="community") # community, organization
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, default="open", index=True) # draft, open, matched, fulfilled, expired, cancelled
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    user = relationship("User")
    book = relationship("Book")
    offers = relationship("SupportOffer", back_populates="need", cascade="all, delete-orphan")
    matches = relationship("RequestMatch", back_populates="need", cascade="all, delete-orphan")

class SchoolShortage(Base):
    __tablename__ = "school_shortages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    book_id = Column(String(36), ForeignKey("books.id", ondelete="SET NULL"), nullable=True)
    book_title_fallback = Column(String(255), nullable=True)
    quantity_needed = Column(Integer, nullable=False, default=1)
    pledged_quantity = Column(Integer, nullable=False, default=0)
    confirmed_received_quantity = Column(Integer, nullable=False, default=0)
    priority = Column(String(32), nullable=False, default="normal") # urgent, normal, low
    deadline = Column(DateTime(timezone=True), nullable=True)
    preferred_support = Column(String(32), nullable=False, default="lend") # lend, donate
    status = Column(String(32), nullable=False, default="open") # open, fulfilled, closed

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    organization = relationship("Organization", back_populates="shortages")
    book = relationship("Book")

class Resource(Base):
    __tablename__ = "resources"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    title = Column(String(255), nullable=False, index=True)
    resource_type = Column(String(64), nullable=False, default="curriculum_guide") # syllabus, textbook_excerpt, open_courseware
    source_name = Column(String(255), nullable=False)
    source_url = Column(String(512), nullable=False)
    license_name = Column(String(128), nullable=False) # e.g. "CC BY-NC 4.0", "Public Domain"
    license_url = Column(String(512), nullable=True)
    rights_basis = Column(Text, nullable=False)
    allowed_actions = Column(JSON, nullable=False, default=list) # ["metadata", "link", "distribute_file"]
    evidence = Column(Text, nullable=True)
    verification_status = Column(String(32), nullable=False, default="pending", index=True) # pending, verified, rejected, needs_review
    verified_by = Column(String(36), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    takedown_status = Column(String(32), nullable=False, default="none") # none, takedown_requested, taken_down
    custom_data = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

class MediaFile(Base):
    __tablename__ = "media_files"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    mime_type = Column(String(64), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    checksum_sha256 = Column(String(64), nullable=False, index=True)
    purpose = Column(String(64), nullable=False, default="book_cover") # book_cover, report_evidence, resource_file
    owner_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

class Report(Base):
    __tablename__ = "reports"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    reporter_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_entity_type = Column(String(32), nullable=False) # user, copy, loan, resource
    target_entity_id = Column(String(36), nullable=False, index=True)
    category = Column(String(32), nullable=False) # spam, harassment, fraud, unsafe_meeting, copyright, fake_book, wrong_information, damaged_or_lost, other
    description = Column(Text, nullable=False)
    evidence_media_ids = Column(JSON, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="open", index=True) # open, reviewing, resolved, rejected
    resolution_note = Column(Text, nullable=True)
    resolved_by = Column(String(36), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    reporter = relationship("User")

class UserBlock(Base):
    __tablename__ = "user_blocks"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_user_block"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    blocker_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    blocked_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("loan_id", "author_id", name="uq_loan_review_per_author"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    loan_id = Column(String(36), ForeignKey("loans.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rating = Column(Integer, nullable=False) # 1 to 5
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    loan = relationship("Loan", back_populates="reviews")
    author = relationship("User", foreign_keys=[author_id])
    target_user = relationship("User", foreign_keys=[target_user_id])

class TrustEvent(Base):
    __tablename__ = "trust_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    loan_id = Column(String(36), ForeignKey("loans.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(64), nullable=False) # on_time_return, late_return, dispute_incident, correction
    score_delta = Column(Numeric(5, 2), nullable=False, default=0.0)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

class SupportOffer(Base):
    __tablename__ = "support_offers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    need_id = Column(String(36), ForeignKey("community_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    offer_type = Column(String(32), nullable=False) # full_physical_copy, partial_physical_copy, authorized_digital_resource, future_availability, library_referral
    copy_id = Column(String(36), ForeignKey("book_copies.id", ondelete="SET NULL"), nullable=True, index=True)
    resource_id = Column(String(36), ForeignKey("resources.id", ondelete="SET NULL"), nullable=True, index=True)
    covered_ranges = Column(JSON, nullable=False, default=dict) # {"start_page": 1, "end_page": 20, "chapters": []}
    available_from = Column(DateTime(timezone=True), nullable=True)
    proposed_duration_days = Column(Integer, nullable=False, default=14)
    coarse_pickup_area = Column(String(128), nullable=True)
    message = Column(Text, nullable=True)
    rights_snapshot = Column(JSON, nullable=False, default=dict)
    revalidation_required = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, default="proposed", index=True) # proposed, selected, declined, withdrawn, expired, fulfilled
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    need = relationship("CommunityRequest", back_populates="offers")
    provider_user = relationship("User", foreign_keys=[provider_user_id])
    provider_organization = relationship("Organization")
    copy = relationship("BookCopy")
    resource = relationship("Resource")

class RequestMatch(Base):
    __tablename__ = "request_matches"
    __table_args__ = (
        UniqueConstraint("need_id", "owner_user_id", "copy_id", name="uq_request_match_copy"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    need_id = Column(String(36), ForeignKey("community_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    copy_id = Column(String(36), ForeignKey("book_copies.id", ondelete="SET NULL"), nullable=True, index=True)
    resource_id = Column(String(36), ForeignKey("resources.id", ondelete="SET NULL"), nullable=True, index=True)
    match_type = Column(String(32), nullable=False, default="exact_edition") # exact_edition, similar_edition, partial_coverage, verified_resource
    notification_status = Column(String(32), nullable=False, default="pending", index=True) # pending, queued, sent, failed, excluded
    exclusion_reason = Column(String(128), nullable=True) # privacy_disabled, quiet_hours, user_blocked, loan_active
    notified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    need = relationship("CommunityRequest", back_populates="matches")
    owner_user = relationship("User")
    copy = relationship("BookCopy")
    resource = relationship("Resource")

class UserWarning(Base):
    __tablename__ = "user_warnings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    subject_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    related_entity_type = Column(String(32), nullable=True) # need, offer, copy, loan, collection, report
    related_entity_id = Column(String(36), nullable=True, index=True)
    category = Column(String(32), nullable=False) # validation, rights_review, transaction_reminder, conduct_warning, copyright_inquiry
    severity = Column(String(32), nullable=False, default="medium") # low, medium, high, critical
    message = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    issued_by = Column(String(64), nullable=False, default="admin")
    appeal_status = Column(String(32), nullable=False, default="none") # none, pending, approved, rejected
    appeal_note = Column(Text, nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    subject_user = relationship("User")

class AuthorizedCollection(Base):
    __tablename__ = "authorized_collections"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    book_id = Column(String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    target_scope = Column(JSON, nullable=False, default=dict) # {"start_page": 1, "end_page": 100, "chapters": []}
    rights_basis = Column(Text, nullable=False)
    allowed_actions = Column(JSON, nullable=False, default=list) # ["receive", "aggregate", "distribute"]
    recipient_scope = Column(String(64), nullable=False, default="verified_students_only")
    status = Column(String(32), nullable=False, default="active", index=True) # draft, active, completed, suspended, revoked
    created_by = Column(String(64), nullable=False, default="admin")
    verified_by = Column(String(64), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    book = relationship("Book")
    contributions = relationship("CollectionContribution", back_populates="collection", cascade="all, delete-orphan")
    assembly_jobs = relationship("AssemblyJob", back_populates="collection", cascade="all, delete-orphan")

class CollectionContribution(Base):
    __tablename__ = "collection_contributions"
    __table_args__ = (
        CheckConstraint("start_page <= end_page AND start_page >= 1", name="chk_contrib_page_order"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    collection_id = Column(String(36), ForeignKey("authorized_collections.id", ondelete="CASCADE"), nullable=False, index=True)
    contributor_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(32), nullable=False, default="physical_scan") # physical_scan, digital_excerpt, author_direct
    start_page = Column(Integer, nullable=False)
    end_page = Column(Integer, nullable=False)
    chapters = Column(JSON, nullable=False, default=list)
    file_path = Column(String(512), nullable=True)
    checksum_sha256 = Column(String(64), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    consent_given = Column(Boolean, nullable=False, default=True)
    verification_status = Column(String(32), nullable=False, default="quarantine", index=True) # quarantine, verified, rejected
    verified_by = Column(String(64), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    collection = relationship("AuthorizedCollection", back_populates="contributions")
    contributor = relationship("User")

class AssemblyJob(Base):
    __tablename__ = "assembly_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    collection_id = Column(String(36), ForeignKey("authorized_collections.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by = Column(String(64), nullable=False, default="admin")
    status = Column(String(32), nullable=False, default="draft", index=True) # draft, processing, needs_review, ready, revoked, failed
    manifest_data = Column(JSON, nullable=False, default=dict)
    coverage_summary = Column(JSON, nullable=False, default=dict) # {"total_pages_covered": 30, "missing_ranges": [], "overlap_ranges": []}
    output_file_path = Column(String(512), nullable=True)
    failure_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    collection = relationship("AuthorizedCollection", back_populates="assembly_jobs")


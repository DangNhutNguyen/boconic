import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, JSON
)
from sqlalchemy.orm import relationship
from app.db.base import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class BorrowRequest(Base):
    __tablename__ = "borrow_requests"
    __table_args__ = (
        Index("ix_pending_req_borrower_copy", "borrower_id", "copy_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    copy_id = Column(String(36), ForeignKey("book_copies.id", ondelete="CASCADE"), nullable=False, index=True)
    borrower_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    need_id = Column(String(36), ForeignKey("community_requests.id", ondelete="SET NULL"), nullable=True, index=True)
    offer_id = Column(String(36), ForeignKey("support_offers.id", ondelete="SET NULL"), nullable=True, index=True)
    duration_days = Column(Integer, nullable=False, default=14)
    note = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="pending", index=True) # pending, accepted, rejected, cancelled, expired

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    copy = relationship("BookCopy", back_populates="borrow_requests")
    borrower = relationship("User", back_populates="borrow_requests")
    loan = relationship("Loan", back_populates="request", uselist=False)
    need = relationship("CommunityRequest")
    offer = relationship("SupportOffer")

class Loan(Base):
    __tablename__ = "loans"
    __table_args__ = (
        CheckConstraint("borrower_id != lender_id", name="chk_loan_different_parties"),
        Index("ix_loans_status", "status"),
        Index("ix_loans_due_at", "due_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    request_id = Column(String(36), ForeignKey("borrow_requests.id", ondelete="RESTRICT"), nullable=True, unique=True)
    copy_id = Column(String(36), ForeignKey("book_copies.id", ondelete="RESTRICT"), nullable=False, index=True)
    borrower_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    lender_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    
    # States: reserved, active, return_pending, returned, cancelled, expired, disputed, closed_lost
    status = Column(String(32), nullable=False, default="reserved")
    
    reservation_expires_at = Column(DateTime(timezone=True), nullable=True)
    handed_over_at = Column(DateTime(timezone=True), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    returned_at = Column(DateTime(timezone=True), nullable=True)
    
    version = Column(Integer, nullable=False, default=1)
    custom_data = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    copy = relationship("BookCopy", back_populates="loans")
    borrower = relationship("User", foreign_keys=[borrower_id])
    lender = relationship("User", foreign_keys=[lender_id])
    request = relationship("BorrowRequest", back_populates="loan")
    confirmations = relationship("HandoverConfirmation", back_populates="loan", cascade="all, delete-orphan")
    events = relationship("LoanEvent", back_populates="loan", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="loan", cascade="all, delete-orphan")

class HandoverConfirmation(Base):
    __tablename__ = "handover_confirmations"
    __table_args__ = (
        UniqueConstraint("loan_id", "role", "action", name="uq_loan_confirmation_role_action"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    loan_id = Column(String(36), ForeignKey("loans.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=False)   # lender, borrower
    action = Column(String(32), nullable=False) # handover, return
    confirmed_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    loan = relationship("Loan", back_populates="confirmations")
    actor = relationship("User")

class LoanEvent(Base):
    __tablename__ = "loan_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    loan_id = Column(String(36), ForeignKey("loans.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(String(36), nullable=True)
    action = Column(String(64), nullable=False)
    from_status = Column(String(32), nullable=True)
    to_status = Column(String(32), nullable=False)
    reason = Column(Text, nullable=True)
    extra_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    loan = relationship("Loan", back_populates="events")

class CustodyEvent(Base):
    __tablename__ = "custody_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    copy_id = Column(String(36), ForeignKey("book_copies.id", ondelete="CASCADE"), nullable=False, index=True)
    loan_id = Column(String(36), ForeignKey("loans.id", ondelete="SET NULL"), nullable=True, index=True)
    from_holder_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    to_holder_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reason = Column(String(64), nullable=False) # handover, return, manual_assignment
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

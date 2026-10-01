import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Index,
    Integer, Numeric, String, Text, JSON
)
from sqlalchemy.orm import relationship
from app.db.base import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def generate_uuid() -> str:
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    telegram_user_id = Column(BigInteger, unique=True, nullable=True, index=True)
    telegram_username = Column(String(64), nullable=True)
    display_name = Column(String(128), nullable=False)
    public_alias = Column(String(32), unique=True, nullable=False, index=True)
    language_code = Column(String(8), nullable=False, default="vi")
    status = Column(String(32), nullable=False, default="active", index=True) # active, suspended, banned, deleted
    custom_data = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    # Relationships
    locations = relationship("UserLocation", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    owned_copies = relationship("BookCopy", foreign_keys="BookCopy.owner_id", back_populates="owner")
    borrow_requests = relationship("BorrowRequest", back_populates="borrower")

    @property
    def is_active(self) -> bool:
        return self.status == "active"

class UserLocation(Base):
    __tablename__ = "user_locations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    country = Column(String(64), nullable=False, default="Vietnam")
    city = Column(String(128), nullable=False, default="TP. Hồ Chí Minh")
    district = Column(String(128), nullable=True)
    neighborhood = Column(String(128), nullable=True)
    latitude = Column(Numeric(9, 6), nullable=True)
    longitude = Column(Numeric(9, 6), nullable=True)
    precision_level = Column(String(32), nullable=False, default="coarse") # coarse, precise
    consent_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="locations")

class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    notify_matching = Column(Boolean, nullable=False, default=True)
    notify_upcoming_need = Column(Boolean, nullable=False, default=True)
    notify_loan_updates = Column(Boolean, nullable=False, default=True)
    notify_reminders = Column(Boolean, nullable=False, default=True)
    quiet_hours_start = Column(Integer, nullable=True) # e.g. 22 (10 PM)
    quiet_hours_end = Column(Integer, nullable=True)   # e.g. 7 (7 AM)
    snooze_until = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="settings")

    @property
    def notify_book_requested(self) -> bool:
        return self.notify_matching

    @notify_book_requested.setter
    def notify_book_requested(self, val: bool):
        self.notify_matching = val

class AdminAccount(Base):
    __tablename__ = "admin_accounts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    telegram_user_id = Column(BigInteger, unique=True, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    sessions = relationship("AdminSession", back_populates="admin", cascade="all, delete-orphan")
    role_assignments = relationship("AdminRoleAssignment", back_populates="admin", cascade="all, delete-orphan")

class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    admin_id = Column(String(36), ForeignKey("admin_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    session_token = Column(String(128), unique=True, nullable=False, index=True)
    csrf_token = Column(String(64), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    admin = relationship("AdminAccount", back_populates="sessions")

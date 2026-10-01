import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, JSON
)
from sqlalchemy.orm import relationship
from app.db.base import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    __table_args__ = (
        Index("ix_bg_job_status_next", "status", "next_attempt_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    job_type = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True) # pending, running, completed, failed, cancelled
    payload = Column(JSON, nullable=False, default=dict)
    result = Column(JSON, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    dedupe_key = Column(String(128), unique=True, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_status_next", "status", "next_attempt_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    event_type = Column(String(64), nullable=False, index=True)
    aggregate_type = Column(String(64), nullable=False)
    aggregate_id = Column(String(36), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="pending", index=True) # pending, dispatched, failed
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)

class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(32), nullable=False, default="telegram")
    category = Column(String(64), nullable=False, default="loan_update")
    message_text = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="pending") # pending, sent, failed
    telegram_message_id = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    sent_at = Column(DateTime(timezone=True), nullable=True)

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    actor_id = Column(String(36), nullable=True, index=True)
    actor_type = Column(String(32), nullable=False, default="admin") # admin, bot, user, system
    action = Column(String(64), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(36), nullable=True, index=True)
    diff_before = Column(JSON, nullable=True)
    diff_after = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    correlation_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(64), primary_key=True)
    value = Column(JSON, nullable=False)
    description = Column(Text, nullable=True)
    updated_by = Column(String(36), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    key = Column(String(64), primary_key=True)
    is_enabled = Column(Boolean, nullable=False, default=False)
    description = Column(Text, nullable=True)
    updated_by = Column(String(36), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

class ImportJob(Base):
    __tablename__ = "import_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    entity_type = Column(String(64), nullable=False)
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False)
    mode = Column(String(32), nullable=False, default="upsert") # create_only, update_only, upsert
    mapping = Column(JSON, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="staged") # staged, running, completed, failed
    total_rows = Column(Integer, nullable=False, default=0)
    processed_rows = Column(Integer, nullable=False, default=0)
    created_count = Column(Integer, nullable=False, default=0)
    updated_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    errors_csv_path = Column(String(512), nullable=True)
    created_by = Column(String(36), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    rows = relationship("ImportRow", back_populates="job", cascade="all, delete-orphan")

class ImportRow(Base):
    __tablename__ = "import_rows"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    job_id = Column(String(36), ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number = Column(Integer, nullable=False)
    raw_data = Column(JSON, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="pending") # pending, valid, warning, error, skipped
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    job = relationship("ImportJob", back_populates="rows")

class ExportJob(Base):
    __tablename__ = "export_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    entity_type = Column(String(64), nullable=False)
    filters = Column(JSON, nullable=False, default=dict)
    columns = Column(JSON, nullable=False, default=list)
    format = Column(String(16), nullable=False, default="csv") # csv, json
    status = Column(String(32), nullable=False, default="pending") # pending, running, completed, failed
    file_path = Column(String(512), nullable=True)
    created_by = Column(String(36), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at = Column(DateTime(timezone=True), nullable=True)

class SavedView(Base):
    __tablename__ = "saved_views"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    admin_id = Column(String(36), ForeignKey("admin_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    columns = Column(JSON, nullable=False, default=list)
    filters = Column(JSON, nullable=False, default=dict)
    sort = Column(JSON, nullable=False, default=dict)
    shared_scope = Column(String(32), nullable=False, default="private") # private, global
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    status = Column(String(32), nullable=False, default="running") # running, completed, failed
    archive_path = Column(String(512), nullable=False)
    checksum_sha256 = Column(String(64), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    manifest = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(36), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at = Column(DateTime(timezone=True), nullable=True)

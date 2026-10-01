import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint, JSON
)
from app.db.base import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class CustomFieldDefinition(Base):
    __tablename__ = "custom_field_definitions"
    __table_args__ = (
        UniqueConstraint("entity_type", "key", name="uq_custom_field_entity_key"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    entity_type = Column(String(64), nullable=False, index=True) # book, book_copy, user, organization, loan, resource
    key = Column(String(64), nullable=False) # e.g. "curriculum", "shelf_location"
    label = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    
    # Types: text, textarea, integer, decimal, boolean, date, datetime,
    # single_select, multi_select, url, email, phone, image, file, json, reference
    field_type = Column(String(32), nullable=False)
    
    required = Column(Boolean, nullable=False, default=False)
    default_value = Column(JSON, nullable=True)
    validation_rules = Column(JSON, nullable=False, default=dict) # min, max, regex, etc.
    options = Column(JSON, nullable=False, default=list) # [{"id": "opt1", "label": "Label"}]
    reference_entity = Column(String(64), nullable=True) # e.g. "books", "organizations"
    
    visibility = Column(String(32), nullable=False, default="public") # public, internal, private
    sensitivity = Column(String(32), nullable=False, default="normal") # normal, pii, restricted
    display_order = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True) # False means archived
    schema_version = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

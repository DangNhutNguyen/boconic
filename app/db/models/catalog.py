import uuid
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, JSON
)
from sqlalchemy.orm import relationship
from app.db.base import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Book(Base):
    __tablename__ = "books"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    title = Column(String(255), nullable=False, index=True)
    subtitle = Column(String(255), nullable=True)
    publisher = Column(String(255), nullable=True, index=True)
    publication_year = Column(Integer, nullable=True)
    edition_label = Column(String(64), nullable=True) # e.g. "Tái bản lần 1", "2024"
    language = Column(String(32), nullable=False, default="vi")
    subject = Column(String(64), nullable=True, index=True) # e.g. "Toán học", "Vật lý"
    grade_level = Column(Integer, nullable=True, index=True) # 1 to 12
    curriculum = Column(String(64), nullable=True, index=True) # e.g. "Kết nối tri thức", "Chân trời sáng tạo"
    isbn10 = Column(String(16), nullable=True, index=True)
    isbn13 = Column(String(32), unique=True, nullable=True, index=True)
    description = Column(Text, nullable=True)
    cover_media_id = Column(String(36), nullable=True)
    metadata_source = Column(String(64), nullable=False, default="manual")
    verification_status = Column(String(32), nullable=False, default="unverified") # unverified, verified
    archived_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    custom_data = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    copies = relationship("BookCopy", back_populates="book", cascade="all, delete-orphan")
    chapters = relationship("Chapter", back_populates="book", cascade="all, delete-orphan")
    authors = relationship("BookAuthor", back_populates="book", cascade="all, delete-orphan")

    @property
    def author(self) -> str:
        if "authors" in self.__dict__:
            authors_list = self.__dict__["authors"]
            if authors_list:
                author_names = []
                for a in authors_list:
                    if "author" in a.__dict__ and a.__dict__["author"]:
                        author_names.append(a.__dict__["author"].name)
                if author_names:
                    return ", ".join(author_names)
        return "Unknown"

    @property
    def isbn(self) -> str:
        return self.isbn13 or self.isbn10 or ""

    @property
    def total_pages(self) -> Optional[int]:
        if self.custom_data and isinstance(self.custom_data, dict):
            return self.custom_data.get("total_pages")
        return None

class Author(Base):
    __tablename__ = "authors"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, unique=True, index=True)
    bio = Column(Text, nullable=True)

    books = relationship("BookAuthor", back_populates="author")

class BookAuthor(Base):
    __tablename__ = "book_authors"
    __table_args__ = (
        UniqueConstraint("book_id", "author_id", name="uq_book_author"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    book_id = Column(String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(String(36), ForeignKey("authors.id", ondelete="CASCADE"), nullable=False, index=True)

    book = relationship("Book", back_populates="authors")
    author = relationship("Author", back_populates="books")

class Publisher(Base):
    __tablename__ = "publishers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, unique=True, index=True)
    address = Column(String(255), nullable=True)

class BookCopy(Base):
    __tablename__ = "book_copies"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    book_id = Column(String(36), ForeignKey("books.id", ondelete="RESTRICT"), nullable=False, index=True)
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    current_holder_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    public_code = Column(String(32), unique=True, nullable=False, index=True) # e.g. "BOC-9A4F"
    condition = Column(String(32), nullable=False, default="good") # new, like_new, good, fair, poor
    circulation_status = Column(String(32), nullable=False, default="available", index=True) # available, reserved, loaned, maintenance, lost
    maximum_loan_days = Column(Integer, nullable=False, default=14)
    chain_lending_allowed = Column(Integer, nullable=False, default=0) # 0: False, 1: True
    lending_policy = Column(String(64), nullable=False, default="free_return")
    visibility = Column(String(32), nullable=False, default="public", index=True) # public, private, unlisted
    format = Column(String(32), nullable=False, default="physical") # physical, photocopy, partial_physical
    is_partial = Column(Boolean, nullable=False, default=False)
    available_from = Column(DateTime(timezone=True), nullable=True)
    coverage_summary = Column(JSON, nullable=False, default=dict)
    storage_location_private = Column(Text, nullable=True) # private note for owner
    notes = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    custom_data = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    book = relationship("Book", back_populates="copies")
    owner = relationship("User", foreign_keys=[owner_id], back_populates="owned_copies")
    current_holder = relationship("User", foreign_keys=[current_holder_id])
    borrow_requests = relationship("BorrowRequest", back_populates="copy")
    loans = relationship("Loan", back_populates="copy")
    coverage_ranges = relationship("CopyCoverageRange", back_populates="copy", cascade="all, delete-orphan")

    @property
    def barcode(self) -> str:
        if self.custom_data and "barcode" in self.custom_data:
            return self.custom_data["barcode"]
        return self.public_code

    @barcode.setter
    def barcode(self, val: str):
        if not self.custom_data:
            self.custom_data = {}
        self.custom_data["barcode"] = val

    @property
    def condition_status(self) -> str:
        return self.condition

class CopyCoverageRange(Base):
    __tablename__ = "copy_coverage_ranges"
    __table_args__ = (
        CheckConstraint("start_page <= end_page AND start_page >= 1", name="chk_coverage_page_order"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    copy_id = Column(String(36), ForeignKey("book_copies.id", ondelete="CASCADE"), nullable=False, index=True)
    start_page = Column(Integer, nullable=False)
    end_page = Column(Integer, nullable=False)
    pagination_basis = Column(String(64), nullable=False, default="edition_page_numbers")
    chapters = Column(JSON, nullable=False, default=list)
    source_description = Column(String(255), nullable=True)
    verification_status = Column(String(32), nullable=False, default="unverified") # unverified, verified, rejected
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    copy = relationship("BookCopy", back_populates="coverage_ranges")

class LibraryEntry(Base):
    __tablename__ = "library_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", "entry_type", name="uq_user_book_entry_type"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    book_id = Column(String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    entry_type = Column(String(32), nullable=False, default="holding") # holding, wishlist, reading, favorite
    reading_status = Column(String(32), nullable=False, default="plan_to_read") # plan_to_read, reading, completed, dropped
    rating = Column(Integer, nullable=True) # 1 to 5
    personal_notes = Column(Text, nullable=True)
    tags = Column(JSON, nullable=False, default=list)
    is_public = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    user = relationship("User")
    book = relationship("Book")

class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (
        CheckConstraint(
            "(page_start IS NULL AND page_end IS NULL) OR (page_start IS NOT NULL AND page_end IS NOT NULL AND page_start <= page_end AND page_start >= 1)",
            name="chk_chapter_page_order",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    book_id = Column(String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_number = Column(Integer, nullable=False, default=1)
    chapter_code = Column(String(64), nullable=True) # e.g. "1", "1.1", "Phụ lục A"
    order_index = Column(Integer, nullable=False, default=1)
    parent_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    pagination_basis = Column(String(64), nullable=False, default="edition_page_numbers")
    topics = Column(JSON, nullable=False, default=list) # array of topic names
    source = Column(String(64), nullable=False, default="manual")
    verification_status = Column(String(32), nullable=False, default="unverified") # unverified, verified, rejected
    version = Column(Integer, nullable=False, default=1)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    book = relationship("Book", back_populates="chapters")
    parent = relationship("Chapter", remote_side=[id], backref="children")
    chapter_topics = relationship("ChapterTopic", back_populates="chapter", cascade="all, delete-orphan")
    resources = relationship("ChapterResource", back_populates="chapter", cascade="all, delete-orphan")
    proposals = relationship("ChapterProposal", back_populates="chapter")
    progress_entries = relationship("UserChapterProgress", back_populates="chapter", cascade="all, delete-orphan")

class ChapterProposal(Base):
    __tablename__ = "chapter_proposals"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    book_id = Column(String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True, index=True)
    proposer_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(32), nullable=False) # create, update, delete, reorder
    base_version = Column(Integer, nullable=False, default=1)
    proposed_data = Column(JSON, nullable=False, default=dict)
    current_data = Column(JSON, nullable=False, default=dict)
    source_evidence = Column(Text, nullable=True)
    reason = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="pending", index=True) # draft, pending, approved, rejected, withdrawn
    reviewed_by = Column(String(64), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    book = relationship("Book")
    chapter = relationship("Chapter", back_populates="proposals")
    proposer = relationship("User")

class UserChapterProgress(Base):
    __tablename__ = "user_chapter_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "chapter_id", name="uq_user_chapter_progress"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    book_id = Column(String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    reading_state = Column(String(32), nullable=False, default="not_started") # not_started, in_progress, completed, paused
    bookmark_page = Column(Integer, nullable=True)
    bookmark_note = Column(String(255), nullable=True)
    personal_notes = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    user = relationship("User")
    book = relationship("Book")
    chapter = relationship("Chapter", back_populates="progress_entries")

class ChapterResource(Base):
    __tablename__ = "chapter_resources"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    book_id = Column(String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    resource_type = Column(String(64), nullable=False, default="link") # link, digital_fragment, notes
    url = Column(String(512), nullable=True)
    file_path = Column(String(512), nullable=True)
    checksum_sha256 = Column(String(64), nullable=True)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    rights_basis = Column(Text, nullable=False, default="personal_fair_use")
    allowed_actions = Column(JSON, nullable=False, default=list) # ["view", "link"]
    verification_status = Column(String(32), nullable=False, default="quarantine", index=True) # quarantine, pending_review, verified, rejected, revoked
    verified_by = Column(String(64), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    is_public = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    chapter = relationship("Chapter", back_populates="resources")
    book = relationship("Book")
    owner = relationship("User")

class ChapterWatch(Base):
    __tablename__ = "chapter_watches"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", "chapter_id", name="uq_user_chapter_watch"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    book_id = Column(String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True, index=True)
    notify_preference = Column(String(32), nullable=False, default="all") # physical_only, digital_only, all
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    user = relationship("User")
    book = relationship("Book")
    chapter = relationship("Chapter")

class Topic(Base):
    __tablename__ = "topics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(128), nullable=False, unique=True, index=True)
    subject = Column(String(64), nullable=True)

class ChapterTopic(Base):
    __tablename__ = "chapter_topics"
    __table_args__ = (
        UniqueConstraint("chapter_id", "topic_id", name="uq_chapter_topic"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_id = Column(String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)

    chapter = relationship("Chapter", back_populates="chapter_topics")
    topic = relationship("Topic")


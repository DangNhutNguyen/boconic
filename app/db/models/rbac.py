import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, String, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.db.base import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Role(Base):
    __tablename__ = "roles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(64), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    is_system = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    admin_assignments = relationship("AdminRoleAssignment", back_populates="role", cascade="all, delete-orphan")

class Permission(Base):
    __tablename__ = "permissions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    code = Column(String(64), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)

    roles = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")

class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    role_id = Column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id = Column(String(36), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True)

    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="roles")

class AdminRoleAssignment(Base):
    __tablename__ = "admin_role_assignments"
    __table_args__ = (
        UniqueConstraint("admin_id", "role_id", name="uq_admin_role_assignment"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    admin_id = Column(String(36), ForeignKey("admin_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    admin = relationship("AdminAccount", back_populates="role_assignments")
    role = relationship("Role", back_populates="admin_assignments")

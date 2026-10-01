from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Cookie, Depends, Header, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.errors import BoconicException, ErrorCode
from app.core.security import generate_csrf_token, generate_session_token, verify_password
from app.db.models.identity import AdminAccount, AdminSession
from app.db.models.rbac import AdminRoleAssignment, Role, RolePermission
from app.db.session import get_db

router = APIRouter(prefix="/admin/auth", tags=["Admin Auth"])

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class AdminLoginDTO(BaseModel):
    username: str
    password: str

async def get_current_admin(
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> AdminAccount:
    """Validate server-side session cookie and return active AdminAccount."""
    if not boconic_session:
        raise BoconicException(code=ErrorCode.UNAUTHORIZED, message="Vui lòng đăng nhập để tiếp tục.", status_code=401)

    now = utc_now()
    stmt = (
        select(AdminSession)
        .where(
            AdminSession.session_token == boconic_session,
            AdminSession.expires_at > now,
        )
        .options(
            selectinload(AdminSession.admin)
            .selectinload(AdminAccount.role_assignments)
            .selectinload(AdminRoleAssignment.role)
            .selectinload(Role.permissions)
            .selectinload(RolePermission.permission)
        )
    )
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()
    if not session or not session.admin or not session.admin.is_active:
        raise BoconicException(code=ErrorCode.UNAUTHORIZED, message="Phiên làm việc đã hết hạn hoặc bị hủy.", status_code=401)

    return session.admin

@router.post("/login")
async def admin_login(
    dto: AdminLoginDTO,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AdminAccount).where(AdminAccount.username == dto.username.strip())
    res = await db.execute(stmt)
    admin = res.scalar_one_or_none()

    if not admin or not verify_password(dto.password, admin.password_hash):
        raise BoconicException(
            code=ErrorCode.UNAUTHORIZED,
            message="Tên đăng nhập hoặc mật khẩu không chính xác.",
            status_code=401,
        )

    if not admin.is_active:
        raise BoconicException(
            code=ErrorCode.FORBIDDEN,
            message="Tài khoản quản trị viên này đã bị vô hiệu hóa.",
            status_code=403,
        )

    # Create server session
    session_token = generate_session_token()
    csrf_token = generate_csrf_token()
    expires_at = utc_now() + timedelta(seconds=settings.SESSION_MAX_AGE_SECONDS)

    session = AdminSession(
        admin_id=admin.id,
        session_token=session_token,
        csrf_token=csrf_token,
        expires_at=expires_at,
    )
    db.add(session)
    await db.commit()

    # Set cookie
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.APP_ENV == "production",
    )

    return {
        "status": "success",
        "username": admin.username,
        "csrf_token": csrf_token,
        "expires_at": expires_at.isoformat(),
    }

@router.post("/logout")
async def admin_logout(
    response: Response,
    boconic_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if boconic_session:
        res = await db.execute(select(AdminSession).where(AdminSession.session_token == boconic_session))
        session = res.scalar_one_or_none()
        if session:
            await db.delete(session)
            await db.commit()

    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    return {"status": "logged_out"}

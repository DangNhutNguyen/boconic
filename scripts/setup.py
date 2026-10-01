import asyncio
import os
import sys
from pathlib import Path

# Ensure root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.core.config import settings
from app.core.permissions import Permissions, ROLE_PERMISSIONS_MAP
from app.core.security import hash_password
from app.db.models.identity import AdminAccount
from app.db.models.rbac import AdminRoleAssignment, Permission, Role, RolePermission
from app.db.session import async_session_factory

async def setup():
    print("==================================================")
    print("           BOCONIC SETUP & INITIALIZATION         ")
    print("==================================================")

    # 1. Run migrations
    print("[1/3] Đang kiểm tra và áp dụng Alembic migrations...")
    alembic_cfg = Config(str(BASE_DIR / "alembic.ini"))
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    print("      -> Migrations hoàn tất thành công.")

    # 2. Seed RBAC Roles & Permissions
    print("[2/3] Đang khởi tạo bảng phân quyền RBAC và Roles...")
    async with async_session_factory() as db:
        # Create all permissions
        perm_objs = {}
        for p_code in Permissions.ALL:
            res = await db.execute(select(Permission).where(Permission.code == p_code))
            perm = res.scalar_one_or_none()
            if not perm:
                perm = Permission(code=p_code, description=f"Quyền thực thi {p_code}")
                db.add(perm)
                await db.flush()
            perm_objs[p_code] = perm

        # Create system roles
        role_objs = {}
        for role_name, p_codes in ROLE_PERMISSIONS_MAP.items():
            res = await db.execute(select(Role).where(Role.name == role_name))
            role = res.scalar_one_or_none()
            if not role:
                role = Role(name=role_name, is_system=True, description=f"Vai trò hệ thống {role_name}")
                db.add(role)
                await db.flush()
            role_objs[role_name] = role

            # Assign permissions to role
            for pc in p_codes:
                link_check = await db.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == perm_objs[pc].id,
                    )
                )
                if not link_check.scalar_one_or_none():
                    db.add(RolePermission(role_id=role.id, permission_id=perm_objs[pc].id))

        await db.commit()
    print("      -> Hệ thống Roles và Permissions đã sẵn sàng.")

    # 3. Create Super Admin Account
    print("[3/3] Đang tạo tài khoản Super Admin mặc định...")
    admin_user = settings.ADMIN_LOGIN or "admin"
    admin_pass = "Boconic@2026"

    async with async_session_factory() as db:
        res = await db.execute(select(AdminAccount).where(AdminAccount.username == admin_user))
        admin = res.scalar_one_or_none()
        if not admin:
            admin = AdminAccount(
                username=admin_user,
                email="admin@boconic.local",
                password_hash=hash_password(admin_pass),
                is_active=True,
            )
            db.add(admin)
            await db.flush()

            # Assign Super Admin role
            super_role = (await db.execute(select(Role).where(Role.name == "Super Admin"))).scalar_one()
            db.add(AdminRoleAssignment(admin_id=admin.id, role_id=super_role.id))
            await db.commit()
            print(f"      -> Tài khoản admin đã được tạo: Username: '{admin_user}' | Mật khẩu: '{admin_pass}'")
            print("      -> [LƯU Ý]: Hãy đăng nhập tại http://localhost:8000/admin để sử dụng hệ thống!")
        else:
            print(f"      -> Tài khoản admin '{admin_user}' đã tồn tại từ trước.")

        if settings.ADMIN_TELEGRAM_ID and settings.ADMIN_TELEGRAM_ID.isdigit():
            admin.telegram_user_id = int(settings.ADMIN_TELEGRAM_ID)
            await db.commit()
            print(f"      -> Đã gắn Telegram numeric ID: {settings.ADMIN_TELEGRAM_ID} (@{settings.ADMIN_USERNAME}) cho admin.")

    print("\n==================================================")
    print("          BOCONIC SẴN SÀNG HOẠT ĐỘNG!             ")
    print("==================================================")
    print("Lệnh chạy web server và Admin Console:")
    print("  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
    print("\nĐăng nhập Admin Console tại: http://127.0.0.1:8000/admin")

if __name__ == "__main__":
    asyncio.run(setup())

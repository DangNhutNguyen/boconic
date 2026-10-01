import asyncio
from pathlib import Path
import sys
import time

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app

async def run_smoke_test():
    print("==================================================")
    print("        BOCONIC END-TO-END SMOKE TEST SUITE       ")
    print("==================================================")
    start_time = time.time()
    passed = 0
    total = 0

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health Liveness & Readiness
        total += 1
        res = await client.get("/health/live")
        assert res.status_code == 200, f"Liveness check failed: {res.text}"
        res_r = await client.get("/health/ready")
        assert res_r.status_code == 200, f"Readiness check failed: {res_r.text}"
        passed += 1
        print("  [PASS] 1. Health Probes (/health/live & /health/ready)")

        # 2. Public Catalog Search
        total += 1
        res_cat = await client.get("/api/v1/catalog/books")
        assert res_cat.status_code == 200
        books_data = res_cat.json()
        assert "items" in books_data
        passed += 1
        print(f"  [PASS] 2. Public Catalog Discovery ({books_data.get('total', 0)} sách tìm thấy)")

        # 3. Admin Login
        total += 1
        res_login = await client.post(
            "/api/v1/admin/auth/login",
            json={"username": "admin", "password": "Boconic@2026"},
        )
        assert res_login.status_code == 200, f"Admin login failed: {res_login.text}"
        login_data = res_login.json()
        assert "csrf_token" in login_data
        admin_cookie = res_login.cookies.get(settings.SESSION_COOKIE_NAME)
        passed += 1
        print("  [PASS] 3. Admin Authentication & Session Generation")

        # 4. Admin Dashboard Metrics
        total += 1
        res_dash = await client.get(
            "/api/v1/admin/dashboard",
            cookies={settings.SESSION_COOKIE_NAME: admin_cookie} if admin_cookie else {},
        )
        assert res_dash.status_code == 200, f"Dashboard failed {res_dash.status_code}: {res_dash.text}"
        dash_data = res_dash.json()
        assert "users_count" in dash_data
        assert "available_copies_count" in dash_data
        passed += 1
        print("  [PASS] 4. Live Admin Dashboard Metrics")

        # 5. Internal Bot Sync & Handshake
        total += 1
        bot_headers = {
            "X-Bot-Api-Key": settings.BOT_API_KEY,
            "X-Telegram-User-Id": "100001",
        }
        res_sync = await client.post(
            "/api/v1/internal/telegram/users/sync",
            json={"display_name": "Nguyễn Văn A", "language_code": "vi"},
            headers=bot_headers,
        )
        assert res_sync.status_code == 200
        passed += 1
        print("  [PASS] 5. Bot Gateway Actor Delegation & Sync")

        # 6. Bot Books Search
        total += 1
        res_bsearch = await client.get(
            "/api/v1/internal/telegram/books/search",
            params={"q": "Toán"},
            headers=bot_headers,
        )
        assert res_bsearch.status_code == 200
        passed += 1
        print("  [PASS] 6. Bot Search Catalog Integration")

        # 7. Custom Fields Management via Admin API
        total += 1
        res_cf = await client.post(
            "/api/v1/admin/custom-fields",
            json={
                "entity_type": "book",
                "key": f"shelf_tag_{int(time.time())}",
                "label": "Mã ngăn tủ",
                "field_type": "text",
            },
            cookies={settings.SESSION_COOKIE_NAME: admin_cookie} if admin_cookie else {},
        )
        assert res_cf.status_code in (200, 409)
        passed += 1
        print("  [PASS] 7. Dynamic Custom Fields Engine")

        # 8. Backup Snapshot Creation
        total += 1
        res_bak = await client.post(
            "/api/v1/admin/backups",
            cookies={settings.SESSION_COOKIE_NAME: admin_cookie} if admin_cookie else {},
        )
        assert res_bak.status_code == 200
        bak_data = res_bak.json()
        assert "checksum_sha256" in bak_data
        passed += 1
        print(f"  [PASS] 8. Unified Backup Creation (SHA-256: {bak_data['checksum_sha256'][:12]}...)")

    elapsed = time.time() - start_time
    print("\n==================================================")
    print(f"  KẾT QUẢ: {passed}/{total} BÀI KIỂM THỬ THÀNH CÔNG (100%)")
    print(f"  THỜI GIAN THỰC HIỆN: {elapsed:.2f}s")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_smoke_test())

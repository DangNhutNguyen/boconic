import asyncio
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.db.session import async_session_factory
from app.services.backup import BackupService

async def main():
    print("Đang tiến hành tạo bản sao lưu dữ liệu Boconic...")
    async with async_session_factory() as db:
        job = await BackupService.create_backup(db, created_by="cli")
        await db.commit()
        print(f"Tạo thành công bản sao lưu:")
        print(f"  • Đường dẫn: {job.archive_path}")
        print(f"  • Dung lượng: {job.size_bytes} bytes")
        print(f"  • Mã SHA-256: {job.checksum_sha256}")
        print(f"  • Thời gian: {job.created_at}")

if __name__ == "__main__":
    asyncio.run(main())

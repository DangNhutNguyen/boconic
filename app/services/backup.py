import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import time
from typing import Any, Dict, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.catalog import Book, BookCopy
from app.db.models.identity import User
from app.db.models.jobs import BackupJob
from app.db.models.lending import Loan

class BackupService:
    @classmethod
    async def create_backup(cls, db: AsyncSession, created_by: Optional[str] = None) -> BackupJob:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_name = f"boconic_backup_{timestamp}"
        temp_dir = Path(settings.BACKUP_DIR) / f"temp_{backup_name}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 1. Collect table counts for integrity manifest
        u_count = (await db.execute(select(func.count(User.id)))).scalar_one()
        b_count = (await db.execute(select(func.count(Book.id)))).scalar_one()
        c_count = (await db.execute(select(func.count(BookCopy.id)))).scalar_one()
        l_count = (await db.execute(select(func.count(Loan.id)))).scalar_one()

        manifest = {
            "version": "2.0.0",
            "timestamp": timestamp,
            "counts": {
                "users": u_count,
                "books": b_count,
                "copies": c_count,
                "loans": l_count,
            },
        }

        with open(temp_dir / "manifest.json", "w", encoding="utf-8") as mf:
            json.dump(manifest, mf, indent=2)

        # 2. Database snapshot
        if settings.is_sqlite:
            db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
            if os.path.exists(db_path):
                shutil.copy2(db_path, temp_dir / "database.sqlite")

        # 3. Create compressed tar.gz
        archive_path = Path(settings.BACKUP_DIR) / f"{backup_name}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            for item in temp_dir.iterdir():
                tar.add(item, arcname=item.name)

        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

        # 4. Compute SHA-256
        sha256 = hashlib.sha256()
        with open(archive_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        checksum = sha256.hexdigest()
        size_bytes = archive_path.stat().st_size

        job = BackupJob(
            status="completed",
            archive_path=str(archive_path),
            checksum_sha256=checksum,
            size_bytes=size_bytes,
            manifest=manifest,
            created_by=created_by,
        )
        db.add(job)
        await db.flush()
        return job

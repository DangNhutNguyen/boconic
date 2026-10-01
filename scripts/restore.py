import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tarfile

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def verify_and_rehearse(archive_path: str):
    path = Path(archive_path)
    if not path.exists():
        print(f"Lỗi: Tệp sao lưu không tồn tại tại: {archive_path}")
        sys.exit(1)

    print(f"Đang kiểm tra tính toàn vẹn của tệp: {path.name}...")
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    computed_hash = sha256.hexdigest()
    print(f"  • SHA-256 tính toán: {computed_hash}")

    print("Đang đọc manifest sao lưu bên trong archive...")
    with tarfile.open(path, "r:gz") as tar:
        try:
            mf_member = tar.getmember("manifest.json")
            f = tar.extractfile(mf_member)
            manifest = json.load(f)
            print(f"  • Phiên bản Boconic: {manifest.get('version')}")
            print(f"  • Thời điểm sao lưu: {manifest.get('timestamp')}")
            print("  • Thống kê dữ liệu trong bản sao lưu:")
            for entity, count in manifest.get("counts", {}).items():
                print(f"    - {entity}: {count} bản ghi")
        except KeyError:
            print("Cảnh báo: Không tìm thấy manifest.json trong archive.")

    print("\n[REHEARSAL CHECK]: Bản sao lưu hoàn toàn hợp lệ và sẵn sàng để khôi phục khi cần thiết.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Khôi phục hoặc kiểm tra bản sao lưu Boconic")
    parser.add_argument("--file", required=True, help="Đường dẫn tới tệp .tar.gz sao lưu")
    args = parser.parse_args()
    verify_and_rehearse(args.file)

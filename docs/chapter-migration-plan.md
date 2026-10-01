# BOCONIC — KẾ HOẠCH MIGRATION & SỬA CHỮA DỮ LIỆU CHƯƠNG (CHAPTER MIGRATION PLAN)

> **Boconic Platform** — *"Find what you need. Find who can help."*  
> Quy trình áp dụng migration cơ sở dữ liệu không phá hủy (non-destructive), cơ chế đảo ngược an toàn (rollback), và tập lệnh tự động rà soát sửa chữa dữ liệu mục lục chương.

---

## 1. Nguyên tắc An toàn Dữ liệu

1. **Bảo toàn dữ liệu lịch sử:** Không thực hiện bất kỳ lệnh `DROP TABLE`, `TRUNCATE` hoặc xóa trắng database. Toàn bộ các bảng hiện có (`books`, `book_copies`, `loans`, `community_requests`, `users`) được giữ nguyên vẹn.
2. **Server Defaults cho cột Non-Null:** Các cột mới có thuộc tính `nullable=False` bắt buộc phải có `server_default` để các bản ghi cũ trong cơ sở dữ liệu không bị lỗi vi phạm ràng buộc (constraint violation).
3. **Cơ chế Hồi quy (Reversibility):** Mọi migration Alembic đều có hàm `downgrade()` hoàn chỉnh để khôi phục cấu trúc schema về trạng thái trước đó khi cần thiết.

---

## 2. Chi tiết Bản cập nhật Schema (Revision `f9a50259f31d`)

- **Bản sửa đổi:** `20261001_f9a50259f31d_chapter_management_progress_proposals.py`
- **Revises:** `ab48b6d18e9f`
- **Các bảng mới được tạo:**
  1. `chapter_proposals`: Lưu đề xuất thêm/sửa/xóa chương từ cộng đồng.
  2. `user_chapter_progress`: Lưu tiến độ học tập cá nhân, bookmark, ghi chú.
  3. `chapter_resources`: Quản lý học liệu số/link đính kèm chương (quarantined).
  4. `chapter_watches`: Danh sách đăng ký theo dõi nguồn mới cho chương thiếu.
- **Các cột mở rộng trên bảng hiện có:**
  - `chapters`: Thêm `chapter_code`, `order_index`, `parent_id`, `pagination_basis`, `version`, `is_archived`, `created_at`, `updated_at`. Cho phép `page_start`, `page_end` có giá trị `NULL` nếu chưa rõ số trang.
  - `community_requests`: Thêm `target_chapters` (JSON), `target_snapshot` (JSON), `revalidation_required` (Boolean, default `False`).
  - `support_offers`: Thêm `revalidation_required` (Boolean, default `False`).

---

## 3. Lệnh Thực thi & Kiểm tra Dry-Run

### 3.1. Áp dụng Migration (Upgrade)
```bash
alembic upgrade head
```

### 3.2. Kiểm tra Trạng thái Schema
```bash
alembic current
```

### 3.3. Khôi phục nếu có Sự cố (Downgrade / Rollback)
```bash
alembic downgrade -1
```

---

## 4. Tập lệnh Rà soát & Sửa chữa Dữ liệu (Data Repair Script)

Đối với các bản ghi `chapters` cũ được tạo trước khi có tính năng phân cấp và versioning, tập lệnh dưới đây tự động chuẩn hóa dữ liệu mà không làm gián đoạn hệ thống:

```python
# scripts/repair_chapters_data.py
import asyncio
from sqlalchemy import select, update
from app.db.session import async_session_factory
from app.db.models.catalog import Chapter

async def repair_chapters():
    async with async_session_factory() as db:
        res = await db.execute(select(Chapter).where(Chapter.chapter_code.is_(None)))
        chapters = list(res.scalars().all())
        for ch in chapters:
            ch.chapter_code = str(ch.chapter_number)
            ch.order_index = ch.chapter_number
            ch.version = 1
            ch.pagination_basis = "edition_page_numbers"
        await db.commit()
        print(f"Đã chuẩn hóa thành công {len(chapters)} chương cũ.")

if __name__ == "__main__":
    asyncio.run(repair_chapters())
```

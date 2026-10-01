# BOCONIC — TÍNH NĂNG QUẢN LÝ SÁCH THEO CHƯƠNG & TIẾN ĐỘ HỌC CÁ NHÂN

> **Boconic Platform** — *"Find what you need. Find who can help."*  
> Tài liệu kỹ thuật kiến trúc, phân quyền và quy trình vận hành tính năng Quản lý sách theo Chương (Chapter-level Management), Phần tài liệu đang có (Holding Coverage) và Tiến độ học tập cá nhân (Personal Study Progress).

---

## 1. Tổng quan và Nguyên tắc cốt lõi

Hệ thống Boconic phân biệt tuyệt đối giữa **ba miền dữ liệu khác nhau** liên quan đến chương sách:

```
+---------------------------------------------------------------------------------------+
|                                    BOOK METADATA                                      |
|                            (Ấn bản cụ thể / Edition)                                  |
+-------------------------------------------+-------------------------------------------+
                                            |
           +--------------------------------+-------------------------------+
           |                                |                               |
           v                                v                               v
+-----------------------+       +-----------------------+       +-----------------------+
|  A. DANH MỤC CHƯƠNG   |       |   B. PHẦN ĐANG CÓ     |       |   C. TIẾN ĐỘ CÁ NHÂN  |
|      DÙNG CHUNG       |       |  (HOLDING COVERAGE)   |       |   (STUDY PROGRESS)    |
+-----------------------+       +-----------------------+       +-----------------------+
| - Cấu trúc mục lục    |       | - Bản sách cụ thể     |       | - Chưa đọc / Đang đọc |
| - Chapter code/number |       | - CopyCoverageRange   |       | - Đã hoàn thành       |
| - Khoảng trang chuẩn  |       | - Khoảng trang sở hữu |       | - Bookmark trang      |
| - Phân cấp (tối đa 3) |       | - Phân biệt bản photo |       | - Ghi chú riêng tư    |
| - Duyệt qua Proposal  |       | - Không đổi mục lục   |       | - Invariant #8: Không |
| - Versioning chuẩn    |       | - Quyền xác minh riêng|       |   ảnh hưởng Loan/Trust|
+-----------------------+       +-----------------------+       +-----------------------+
```

### Các bất biến kiến trúc (Invariants)
1. **Chapter thuộc đúng Book/edition:** Các edition khác nhau không tự động gộp chung chương hoặc khoảng trang in.
2. **Catalog chung được bảo vệ:** Thành viên sở hữu bản sách không có quyền tùy ý sửa catalog của cộng đồng; mọi thay đổi phải qua cơ chế đề xuất (`ChapterProposal`) và được Admin/Moderator phê duyệt.
3. **Phần tài liệu đang có tách biệt với cấu trúc chương:** Khai báo một copy có chương 1-2 không làm thay đổi định nghĩa chung của sách.
4. **Tiến độ học tập là dữ liệu riêng tư (Invariant #8):** Việc đánh dấu "Đã đọc xong chương" **tuyệt đối không làm**:
   - Giao dịch mượn (`Loan`) kết thúc hoặc đổi trạng thái.
   - Hạn trả (`due_at`) bị thay đổi.
   - Bản sách (`BookCopy`) trở thành khả dụng (`available`) cho người khác.
   - Nhu cầu tìm sách (`CommunityRequest`) tự động hoàn tất.
   - Điểm uy tín (`TrustEvent`) tự động cộng điểm.
5. **Cơ sở tính toán Coverage là Interval Union:** Không cộng dồn các phần trăm tự khai; chỉ tính hợp các khoảng đóng `[page_start, page_end]` trên cùng cơ sở đánh số trang.

---

## 2. Mô hình Dữ liệu và Phân cấp

### 2.1. Cấu trúc Chapter (Mục lục chung)
- `id`: Định danh UUID ổn định, không thay đổi khi sửa tên hoặc đổi thứ tự.
- `book_id`: Khóa ngoại liên kết tới `books.id` (ondelete CASCADE).
- `chapter_number`: Số thứ tự số học (integer) dùng để sắp xếp mặc định.
- `chapter_code`: Mã hiển thị linh hoạt (string, e.g. `"1"`, `"1.1"`, `"Chương đặc biệt"`, `"Phụ lục A"`).
- `order_index`: Thứ tự sắp xếp hiển thị tùy biến.
- `parent_id`: Khóa ngoại tự tham chiếu (`chapters.id`, ondelete SET NULL). Hỗ trợ tối đa 3 cấp (Chương -> Mục -> Tiểu mục). Chống chu trình (cycle prevention).
- `title`: Tên chương/chủ đề.
- `page_start`, `page_end`: Khoảng trang chuẩn của edition (có thể null nếu chưa xác minh được trang in).
- `pagination_basis`: Cơ sở đánh số trang (mặc định `"edition_page_numbers"`).
- `verification_status`: Trạng thái thẩm định (`"unverified"`, `"verified"`, `"rejected"`).
- `version`: Phiên bản sửa đổi nguyên tử (bắt đầu từ 1, tăng khi có approval).

### 2.2. Đề xuất sửa đổi (`ChapterProposal`)
- Lưu trữ mọi yêu cầu: Thêm mới (`create`), Sửa đổi (`update`), Lưu trữ (`delete`), Sắp xếp lại (`reorder`).
- `base_version`: Phiên bản cơ sở tại thời điểm người dùng tạo đề xuất.
- **Phát hiện xung đột (Conflict Detection):** Nếu `chapter.version != proposal.base_version`, hệ thống chặn với mã lỗi `409 Conflict`, ngăn chặn tình trạng ghi đè âm thầm giữa hai người cùng chỉnh sửa.
- Khi phê duyệt đề xuất thay đổi khoảng trang (`page_start`, `page_end`):
  Hệ thống quét tất cả `CommunityRequest` và `SupportOffer` đang mở có phạm vi liên quan, gắn cờ `revalidation_required = True` và phát sinh sự kiện `OutboxEvent("CHAPTER_RANGE_REVISED")`.

### 2.3. Tiến độ học tập cá nhân (`UserChapterProgress`)
- Liên kết: `user_id`, `book_id`, `chapter_id`.
- `reading_state`: `"not_started"`, `"in_progress"`, `"completed"`, `"paused"`.
- `bookmark_page`: Trang đang đọc dở.
- `bookmark_note`: Ghi chú nhanh tại bookmark.
- `personal_notes`: Toàn văn ghi chú học tập cá nhân.
- **Quy tắc mẫu số tổng hợp (Denominator Policy):**
  Khi tính tỷ lệ hoàn thành cuốn sách, hệ thống chỉ lấy các chương cấp đầu (`parent_id is None`) làm mẫu số. Các tiểu mục con là chi tiết bổ trợ, không bị đếm trùng làm sai lệch mẫu số.

### 2.4. Tài nguyên số theo chương (`ChapterResource`)
- Đính kèm file số hoặc liên kết tài liệu vào từng chương cụ thể.
- Mặc định ở trạng thái kiểm dịch (`verification_status = "quarantine"`, `is_public = False`).
- Yêu cầu người kiểm duyệt phê duyệt cơ sở quyền (`rights_basis`) trước khi công khai.

---

## 3. Quy trình Người dùng (User Workflows)

### 3.1. Xem danh mục chương & Cập nhật tiến độ trên Bot Telegram
1. Từ **Thư viện của tôi**, chọn một đầu sách -> Bấm **📑 Danh mục chương** (hoặc gõ `/chapters <book_id>`).
2. Danh sách chương hiển thị kèm biểu tượng trực quan:
   - `⚪`: Chưa đọc (`not_started`)
   - `⏳`: Đang đọc (`in_progress`)
   - `✅`: Đã đọc xong (`completed`)
3. Bấm vào một chương cụ thể:
   - Xem khoảng trang chuẩn, ghi chú cá nhân, bookmark.
   - Bấm **✅ Đã đọc xong** / **⏳ Đang đọc** / **⚪ Chưa đọc** để đổi trạng thái tức thì.
   - Bấm **📢 Tôi cần chương này** để khởi tạo nhanh nhu cầu tìm sách theo chương.
   - Bấm **🔔 Theo dõi nguồn** để nhận thông báo khi có bản sách/tài liệu mới cho chương này.
   - Bấm **📥 Xuất ghi chú** để nhận tệp Markdown tổng hợp toàn bộ ghi chú học tập riêng tư.

### 3.2. Tạo nhu cầu sách theo chương ("Tôi cần chương này")
1. Người dùng bấm **📢 Tôi cần chương này** từ chi tiết chương (hoặc chọn phạm vi `📑 Chương / Chủ đề` trong wizard `/request`).
2. Hệ thống ghi nhận `scope_type = "chapters"`, lưu `target_chapters = [chapter_id]` và tạo snapshot bất biến `target_snapshot`.
3. **Logic Matching tương ứng:**
   - **Bản sách vật lý đầy đủ (`full_copy`):** Khớp điều kiện! Người học có thể mượn toàn bộ bản sách để học chương mong muốn (Scenario 3).
   - **Bản sách photocopy một phần (`partial_copy`):** Chỉ khớp điều kiện khi bản photocopy đó có khai báo chứa chương đang cần (Scenario 2). Nếu chỉ có chương 2 mà người học cần chương 3, hệ thống loại bỏ khỏi danh sách thông báo.

### 3.3. Đề xuất thêm/sửa chương và Quy trình Duyệt Admin
1. Người dùng bấm **📝 Đề xuất sửa** -> Gửi form đề xuất (tiêu đề, khoảng trang, lý do).
2. Hệ thống kiểm tra cấu trúc phân cấp (tối đa 3 cấp, không chu trình) và xung đột `base_version`.
3. Đề xuất chuyển vào hàng đợi duyệt của Quản trị viên (`/admin/chapter-proposals`).
4. Quản trị viên kiểm tra bằng chứng:
   - **Duyệt (Approve):** Catalog cập nhật tự động trong database transaction; nếu khoảng trang đổi, hệ thống kích hoạt revalidation cho các nhu cầu mở liên quan.
   - **Từ chối (Reject):** Lưu lý do từ chối, gửi thông báo phản hồi cho người đề xuất.

---

## 4. API Endpoints

| Method | Endpoint | Quyền hạn | Mô tả |
| --- | --- | --- | --- |
| `GET` | `/api/v1/catalog/books/{id}/chapters` | Public | Lấy danh mục chương chuẩn của đầu sách |
| `POST` | `/api/v1/catalog/books/{id}/chapter-proposals` | Authenticated | Gửi đề xuất thêm/sửa chương |
| `GET` | `/api/v1/me/progress/{book_id}` | Owner | Lấy tiến độ đọc cá nhân theo sách |
| `POST` | `/api/v1/me/progress/{chapter_id}` | Owner | Cập nhật trạng thái đọc, bookmark, ghi chú |
| `GET` | `/api/v1/me/notes/{book_id}/export` | Owner | Xuất ghi chú học tập ra định dạng Markdown |
| `POST` | `/api/v1/catalog/chapters/{id}/resources` | Authenticated | Đính kèm tài nguyên số (quarantined) |
| `POST` | `/api/v1/catalog/chapters/{id}/watch` | Authenticated | Bật theo dõi nguồn mới cho chương |
| `GET` | `/admin/chapter-proposals` | Admin | Quản lý danh sách đề xuất chương |
| `POST` | `/admin/chapter-proposals/{id}/review` | Admin | Duyệt hoặc từ chối đề xuất chương |
| `GET` | `/admin/process-audit` | Admin | Chẩn đoán tính toàn vẹn và các nhu cầu cần revalidate |

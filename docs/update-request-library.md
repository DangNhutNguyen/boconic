# BOCONIC — TÀI LIỆU CẬP NHẬT: BOOK REQUESTS, PERSONAL LIBRARY & ADMIN OPERATIONS

**Boconic — Find what you need. Find who can help.**  
Admin Telegram numeric ID: Cấu hình qua `ADMIN_TELEGRAM_ID` trong `.env`. Xác thực quản trị dựa trên ID số học và session bảo mật, không dựa trên username.

---

## 1. Tổng quan bản cập nhật

Bản cập nhật này mở rộng nền tảng Boconic với 5 nhóm chức năng cốt lõi:
1. **Book Requests (Nhu cầu sách — "Tôi cần sách A"):** Tạo, quản lý, khớp nối tự động với các chủ sách đủ điều kiện và gửi thông báo theo hàng đợi.
2. **Personal Library (Thư viện của tôi):** Quản lý toàn diện các danh mục sách: Tôi sở hữu, Đang sẵn sàng, Đang cho mượn, Đang mượn, Wishlist, Tài liệu 1 phần / Photocopy, và Lịch sử giao dịch.
3. **Community Offers (Đề nghị hỗ trợ):** Cho phép các chủ sách phản hồi nhu cầu (bản đầy đủ, bản 1 phần, sắp có lại, giới thiệu nguồn); cơ chế khóa nguyên tử (mutex lock) giữ chỗ trong 72h.
4. **Contribution Tracking & Authorized Collection:** Thu thập học liệu số theo phân đoạn trang với kiểm định quyền chặt chẽ; tính toán độ phủ (coverage) theo hợp khoảng toán học (Interval Union), không cộng dồn phần trăm tự khai báo.
5. **Admin Operations & Moderation:** Giao diện điều hành trực quan cho Nhu cầu, Kho sách, Tài liệu một phần, Bộ sưu tập được cấp phép, Báo cáo & Cảnh báo người dùng minh bạch.

---

## 2. Bản đồ Thay đổi & Mở rộng Dữ liệu

| Module | Tên bảng / Entity | Trạng thái | Mục đích & Ràng buộc chính |
| :--- | :--- | :--- | :--- |
| **Catalog** | `book_copies` | **Mở rộng** | Thêm `visibility` (public/private), `format`, `is_partial`, `available_from`, `coverage_summary`. |
| **Catalog** | `copy_coverage_ranges` | **Mới** | Lưu khoảng trang 1-indexed (`1 <= start <= end`), chapters, pagination basis cho bản photo/1 phần. |
| **Catalog** | `library_entries` | **Mới** | Lưu metadata đọc cá nhân: reading status, rating, tags, notes. |
| **Community** | `community_requests` | **Mở rộng** | Thêm `isbn`, `edition_label`, `scope_type`, `page_range`, `quantity_fulfilled`, `urgency`, `version`. |
| **Community** | `request_matches` | **Mới** | Snapshot kết quả rà soát chủ sách đủ điều kiện (1 thông báo duy nhất / owner). |
| **Community** | `support_offers` | **Mới** | Đề nghị hỗ trợ liên kết Need và Copy/Resource: proposed, selected, fulfilled, withdrawn. |
| **Community** | `authorized_collections` | **Mới** | Bộ sưu tập tài liệu số có cơ sở quyền đã được duyệt (CC, Public Domain, Author consent). |
| **Community** | `collection_contributions`| **Mới** | Phân đoạn đóng góp trang từ thành viên có consent và kiểm duyệt. |
| **Community** | `assembly_jobs` | **Mới** | Job tổng hợp tài nguyên thành manifest khi độ phủ hợp lệ và không có khoảng trống. |
| **Moderation** | `user_warnings` | **Mới** | Cảnh báo có cấu trúc (validation, rights_review, conduct), cơ chế phản hồi và khiếu nại (appeal). |
| **Lending** | `borrow_requests` | **Mở rộng** | Thêm khóa ngoại `need_id` và `offer_id` liên kết nhu cầu ban đầu. |
| **Identity** | `user_settings` | **Mở rộng** | Thêm `notify_upcoming_need` và `snooze_until` quản lý nhận thông báo tìm sách. |

---

## 3. Danh mục API Mới & Cập nhật

### 3.1. REST API Công khai & Cá nhân
- `POST /api/v1/community-requests`: Đăng nhu cầu tìm sách mới.
- `GET /api/v1/community-requests`: Danh sách nhu cầu sách đang mở.
- `GET /api/v1/community-requests/{id}`: Chi tiết nhu cầu kèm số chủ sách phù hợp và số đề nghị.
- `GET /api/v1/community-requests/{id}/offers`: Danh sách các đề nghị hỗ trợ cho nhu cầu.
- `POST /api/v1/community-requests/{id}/offers`: Gửi đề nghị hỗ trợ.
- `POST /api/v1/offers/{id}/select`: Chọn đề nghị hỗ trợ ➔ Tự động tạo Loan ở trạng thái `reserved`.
- `POST /api/v1/offers/{id}/withdraw`: Rút đề nghị trước khi có nghĩa vụ mượn.
- `GET /api/v1/community-library`: Tra cứu kho sách công khai từ cộng đồng và trường học.
- `GET /api/v1/me/library`: Lấy danh mục thư viện người dùng theo tab (`owned`, `available`, `lent`, `borrowed`, `wishlist`, `resources`, `history`).
- `POST /api/v1/inventory/batch-preview`: Xem trước nhập liệu CSV, kiểm tra ISBN và barcode trùng lặp.
- `POST /api/v1/inventory/batch-confirm`: Xác nhận nhập hàng loạt sách và bản sao vật lý.
- `GET /api/v1/me/warnings`: Danh sách cảnh báo người dùng.
- `POST /api/v1/me/warnings/{id}/acknowledge`: Xác nhận đã đọc cảnh báo.
- `POST /api/v1/me/warnings/{id}/appeal`: Gửi khiếu nại về cảnh báo.

### 3.2. Cổng Gateway Bot Nội bộ (`/api/v1/internal/telegram`)
Xác thực qua cặp header `X-Bot-Api-Key` và `X-Telegram-User-Id`, tự động map sang tài khoản người dùng đã xác minh:
- `/library`: Lấy danh mục thư viện theo tab.
- `/library/copies/{copy_id}/visibility`: Chuyển đổi trạng thái hiển thị công khai / riêng tư.
- `/library/copies/{copy_id}` (DELETE): Xóa bản sách (chặn nếu đang có lượt mượn mở).
- `/needs`: Tạo nhu cầu qua FSM Wizard.
- `/needs/my`: Nhu cầu của tôi kèm số lượng đề nghị.
- `/needs/{id}/cancel`: Hủy nhu cầu sách.
- `/offers`: Tạo đề nghị hỗ trợ từ chủ sách.
- `/offers/{id}/select`: Chọn đề nghị hỗ trợ.
- `/partial/copies`: Đăng ký tài liệu photocopy một phần vào thư viện riêng tư.
- `/warnings/my`, `/acknowledge`, `/appeal`: Quản lý cảnh báo và khiếu nại trên Telegram.

---

## 4. Telegram Bot Flows

1. **📢 Yêu cầu sách (`/request`, `/need`):**
   - Bước 1: Nhập tên sách, tác giả hoặc ISBN.
   - Bước 2: Chọn phạm vi (Cả quyển sách, Chương/Chủ đề, Khoảng trang cụ thể).
   - Bước 3: Chọn mức độ cần gấp (Bình thường, Cần gấp, Rất gấp).
   - Bước 4: Nhập khu vực nhận sách thuận tiện (hoặc Bỏ qua).
   - Hệ thống tự động rà soát mạng lưới và hiển thị thông báo đã đưa vào hàng đợi.

2. **📚 Thư viện của tôi (`/library`):**
   - Chuyển tab nhanh chóng qua bàn phím Inline: Sách sở hữu, Sẵn sàng, Đang cho mượn, Đang mượn, Wishlist, Tài liệu 1 phần, Lịch sử.

3. **Phản hồi thông báo từ Chủ sách:**
   - Tin nhắn thông báo đính kèm 6 nút chức năng: *Tôi có bản đầy đủ*, *Tôi có một phần*, *Sắp có lại*, *Giới thiệu nguồn*, *Không thể hỗ trợ*, *Tắt thông báo*.

---

## 5. Bảng điều khiển Quản trị (Admin Console)

Được tích hợp tại `/admin`:
- **Nhu cầu & Đề nghị (`/admin/requests`):** Lọc theo trạng thái, xem số lượng chủ sách khớp, số đề nghị, Re-match và Hủy nhu cầu vi phạm.
- **Kho & Thư viện (`/admin/inventory`):** Quản lý định dạng (vật lý, photocopy, số), trạng thái lưu thông, hiển thị công khai/riêng tư.
- **Tài liệu 1 phần & Photo (`/admin/partial-materials`):** Kiểm duyệt khoảng trang, hệ đánh số trang, nguồn và duyệt/từ chối quyền.
- **Authorized Collections (`/admin/collections`):** Quản lý bộ sưu tập mở, xem trước độ phủ trang (Coverage Preview), kích hoạt Assembly Job tổng hợp manifest.
- **Báo cáo & Cảnh báo (`/admin/moderation`):** Phát hành cảnh báo minh bạch (validation, rights_review, conduct_warning), xét duyệt khiếu nại (appeal).
- **Thống kê & Vận hành (`/admin/analytics`):** Theo dõi số liệu thời gian thực (phễu nhu cầu, tỷ lệ chọn đề nghị, lượt mượn quá hạn, cảnh báo mở).

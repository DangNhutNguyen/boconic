# Boconic — Tài liệu Thiết kế & Vận hành Quản lý Người dùng và Tài nguyên (User Management & Resource Tracking)

**Phiên bản:** 3.1  
**Ngày cập nhật:** 01/10/2026  
**Module:** User Management, Resource Lifecycle & Physical/Digital Custody  
**Trạng thái:** ✅ Hoàn thành & Đã kiểm thử tích hợp tự động 100%

---

## 1. Mục tiêu & Nguyên tắc Cốt lõi

Hệ thống quản lý người dùng và tài nguyên trong Boconic được thiết kế nhằm mục đích:
1. **Minh bạch hóa quyền sở hữu và quyền cầm giữ (Ownership vs Custody):**
   - Phân biệt rõ người sở hữu bản sách (`BookCopy.owner_id`) với người đang cầm giữ bản sách trong thực tế (`BookCopy.current_holder_id`). Người đang mượn sách **tuyệt đối không** có quyền cho bên thứ ba mượn tiếp.
2. **Theo dõi đa diện các tài nguyên người dùng đang sử dụng (Comprehensive In-Use Resources):**
   - Một người dùng trong hệ thống có thể đồng thời là người mượn, người cho mượn, người sở hữu kho sách, người đóng góp tài nguyên số, người đăng nhu cầu tìm sách hoặc người đang học theo chương.
3. **An toàn & Kiểm soát Kỷ luật (Safety & Moderation):**
   - Cung cấp công cụ cho Quản trị viên (Admin) giám sát các trường hợp quá hạn mượn sách, mở tranh chấp, phát cảnh cáo có phân loại, tạm khóa/cấm tài khoản kèm lý do kiểm toán (Audit Trail), và giải quyết cưỡng chế hoàn tất giao dịch mượn khi phát sinh tranh chấp thực địa.
4. **Bảo mật Quyền riêng tư (Privacy Guardrails):**
   - Dữ liệu học tập cá nhân (tiến độ đọc, ghi chú riêng tư, bookmark) không bao giờ bị rò rỉ ra kết quả tìm kiếm công cộng hay chia sẻ cho các bên ngoài thẩm quyền.

---

## 2. Bảy Nhóm Tài nguyên Theo dõi trong Thời gian Thực

Hệ thống tổng hợp và hiển thị tại Admin Web Console (`/admin/users/{user_id}`) cũng như qua API người dùng (`/me/resources`):

| Nhóm Tài nguyên | Thực thể / Bảng Dữ liệu | Trạng thái Theo dõi | Ý nghĩa Nghiệp vụ |
| :--- | :--- | :--- | :--- |
| **1. Sách đang mượn & Cầm giữ (Custody)** | `Loan` (vai trò `borrower_id`) | `reserved`, `active`, `return_pending` | Sách vật lý người dùng đang trực tiếp giữ trong tay. Tự động gắn cờ ⚠️ **ĐÃ QUÁ HẠN** nếu thời điểm hiện tại vượt quá `due_at`. Admin có thể thực hiện **Cưỡng chế hoàn tất (Force Return)**. |
| **2. Sách cá nhân đang cho mượn (Lent Out)** | `Loan` (vai trò `lender_id`) | `reserved`, `active`, `return_pending` | Sách thuộc quyền sở hữu của user nhưng đang được người khác mượn sử dụng. Giúp chủ sách theo dõi hạn hoàn trả. |
| **3. Kho sách & Tài liệu sở hữu (Owned Library)** | `BookCopy` (vai trò `owner_id`) | `available`, `on_loan`, `reserved`, `maintenance` | Toàn bộ bản sách vật lý và tài liệu photocopy một phần (`CopyCoverageRange`) đã đăng ký. |
| **4. Tài nguyên số theo chương (Chapter Resources)** | `ChapterResource` (vai trò `owner_id`) | `quarantine`, `pending_review`, `verified`, `rejected` | File, liên kết hoặc trích đoạn số do người dùng tải lên và gắn vào các chương sách. Tuân thủ cách ly bản quyền. |
| **5. Nhu cầu cộng đồng đang mở (Active Needs)** | `CommunityRequest` (vai trò `user_id`) | `open` | Yêu cầu tìm sách hoặc chương sách cụ thể kèm cờ cảnh báo `revalidation_required` khi có thay đổi trang mục lục. |
| **6. Đề nghị hỗ trợ đang chờ (Support Offers)** | `SupportOffer` (vai trò `provider_user_id`) | `pending`, `accepted` | Lời đề nghị cho mượn hoặc chia sẻ tài nguyên tới các nhu cầu cộng đồng khác. |
| **7. Tiến độ học tập theo chương (Study Progress)** | `UserChapterProgress` (vai trò `user_id`) | `not_started`, `in_progress`, `completed` | Số chương đã hoàn thành, đang học, bookmark trang dừng và số lượng ghi chú tự viết riêng tư. |

---

## 3. Quản trị Người dùng & Các Thao tác Nghiệp vụ

### 3.1. Danh sách Người dùng (`/admin/users`)
- **Thống kê tổng quan:** Tổng người dùng, số người dùng đang hoạt động, số người đang giữ sách mượn, số tài khoản bị hạn chế/khóa.
- **Tìm kiếm đa năng:** Hỗ trợ tìm kiếm theo tên hiển thị (`display_name`), bí danh (`public_alias`), username Telegram (`telegram_username`), hoặc số nguyên Telegram ID (`telegram_user_id`).
- **Bộ lọc trạng thái:** `all`, `active`, `suspended`, `banned`.
- **Chỉ số Uy tín (Trust Profile):** Tính toán theo thuật toán Bayes làm mượt (Laplace smoothing) tỷ lệ trả sách đúng hạn (`reliability_score`), số lần trả đúng hạn, số lần trễ hạn và các sự vụ tranh chấp.

### 3.2. Chi tiết Người dùng & Tài nguyên (`/admin/users/{user_id}`)
- **Hồ sơ định danh:** Tên hiển thị, bí danh, Telegram ID, ngày gia nhập, địa chỉ khu vực đăng ký.
- **Cập nhật trạng thái tài khoản:**
  - `active` -> `suspended`: Tạm ngưng quyền mượn sách và tạo đề xuất.
  - `active` -> `banned`: Khóa vĩnh viễn quyền truy cập.
  - Mọi thao tác bắt buộc kèm lý do và được ghi nhận tự động vào bảng `audit_logs`.
- **Phát Cảnh cáo Vi phạm (Issue Warning):**
  - Phân loại: `conduct_warning` (ứng xử), `transaction_reminder` (nhắc nhở trả sách), `rights_review` (vi phạm bản quyền), `validation` (sai lệch thông tin).
  - Mức độ: `info` (nhắc nhở), `warning` (cảnh cáo), `critical` (nghiêm trọng).
- **Cưỡng chế Hoàn tất Lượt mượn (Admin Force Return):**
  - Áp dụng khi người mượn đã trao trả sách vật lý nhưng chủ sách quên bấm xác nhận hoặc phát sinh tranh chấp đã được giải quyết.
  - Cập nhật `Loan.status = "returned"`, đưa `BookCopy.circulation_status = "available"`, trả `current_holder_id` về cho chủ sách, ghi nhận sự kiện chuyển giao `CustodyEvent` và `AuditLog`.

---

## 4. Giao diện & Kênh Tương tác Người dùng

### 4.1. Web Console Admin
- Sidebar: **👥 Quản lý người dùng** (`/admin/users`).
- Chi tiết người dùng: `http://localhost:8000/admin/users/{user_id}`.

### 4.2. Telegram Bot Gateway
- Bàn phím chính: Nút **🎒 Tài nguyên đang dùng** và **📖 Quản lý theo chương**.
- Lệnh: `/myresources`
- Nội dung trả về:
  1. Danh sách sách đang mượn kèm hạn trả và cảnh báo quá hạn.
  2. Sách cá nhân đang cho mượn kèm tên người mượn.
  3. Tổng số sách trong kho cá nhân.
  4. Số nhu cầu tìm sách đang mở.
  5. Tiến độ học tập tổng quan (số chương đã đọc, đang đọc, ghi chú).
  6. Điểm uy tín và tỷ lệ trả đúng hẹn.

### 4.3. REST API Endpoints
- `GET /api/v1/me/resources?user_id={user_id}`: Trả về cấu trúc JSON đầy đủ về các tài nguyên người dùng đang dùng.
- `GET /api/v1/internal/telegram/users/me/resources`: Endpoint nội bộ cho Telegram Bot actor.

---

## 5. Bằng chứng Kiểm thử Tích hợp

Bộ kiểm thử `tests/test_user_management.py` bao gồm 5 kịch bản tích hợp chuyên sâu và đã vượt qua 100%:

```text
tests/test_user_management.py::test_user_service_list_users PASSED            [ 20%]
tests/test_user_management.py::test_user_resource_details_and_overdue PASSED [ 40%]
tests/test_user_management.py::test_update_user_status_and_audit PASSED       [ 60%]
tests/test_user_management.py::test_admin_force_return_loan PASSED            [ 80%]
tests/test_user_management.py::test_api_me_resources_json_serializable PASSED [100%]
============================== 5 passed in 2.89s ==============================
```

Toàn bộ test suite hệ thống: **45 passed in 33.40s**.
Smoke test: **8/8 checks passed in 1.84s**.

# BOCONIC — CHÍNH SÁCH XỬ LÝ SÁCH PHOTO, TÀI LIỆU MỘT PHẦN & TỔNG HỢP HỌC LIỆU CÓ BẢN QUYỀN

**Tagline:** *Find what you need. Find who can help.*  
Tài liệu định hình chuẩn mực pháp lý, giới hạn công nghệ và quy trình nghiệp vụ của Boconic đối với các tài liệu một phần, bản photocopy học tập và các bộ sưu tập học liệu mở.

---

## 1. Nguyên tắc Cốt lõi: Phân biệt Sở hữu Bản sao và Quyền Phân phối

1. **Người dùng sở hữu một bản sao tài liệu (Holding/Custody):**
   - Không mặc định mọi bản photo là vi phạm pháp luật (sinh viên, học sinh photo bài tập, chương sách phục vụ nghiên cứu cá nhân).
   - Người dùng được phép khai báo thông tin metadata của bản sao này (tên sách, chương, khoảng trang bắt đầu/kết thúc, hình thức vật lý) vào **Thư viện cá nhân của mình**.
   - Mặc định, mọi tài liệu photocopy hoặc một phần được lưu ở chế độ **Riêng tư (Private)**.

2. **Quyền Sao chép, Phân phối và Tổng hợp (Distribution & Reproduction Rights):**
   - Việc người dùng khai báo "tôi có 10% sách" **tuyệt đối không phải bằng chứng** chứng minh họ có quyền chia sẻ hoặc phát tán tài liệu đó ra cộng đồng.
   - Việc công bố ra thư viện cộng đồng, tạo liên kết tải về hoặc chuyển đổi số chỉ được phép khi cơ sở quyền hợp lệ đã được kiểm duyệt.

---

## 2. Quy tắc Chống Lách luật đối với Tác phẩm còn Bảo hộ (Anti-Circumvention Rules)

Đối với các tác phẩm, giáo trình, sách giáo khoa còn trong thời hạn bảo hộ quyền tác giả mà **chưa có thỏa thuận cấp phép phù hợp**:

1. **Tuyệt đối không tổ chức thu gom các phần nhỏ:**
   - Hệ thống không được tổ chức tiếp nhận các phần 10% liên tiếp từ nhiều người dùng nhằm mục đích ghép lại thành toàn bộ cuốn sách.
2. **Tuyệt đối không phát lệnh kêu gọi bổ sung:**
   - Không phát thông báo "hãy photo các trang tiếp theo" hoặc "chúng ta còn thiếu 30 trang để hoàn chỉnh sách".
3. **Tuyệt đối không tự động xử lý số:**
   - Không tự động đưa file chưa có quyền sang OCR, tạo embedding AI, merge PDF hoặc phân phối file qua Bot.
4. **Định hướng giải pháp thay thế hợp pháp:**
   - Khi người học cần cả quyển sách, hệ thống hướng dẫn tìm **sách vật lý đầy đủ để mượn**, tra cứu tại **thư viện trường học đối tác**, hoặc cung cấp liên kết tới **nhà xuất bản / nguồn chính thức**.

---

## 3. Chương trình Thu thập Học liệu được Cấp phép (Authorized Contribution Collection)

Chỉ được áp dụng đối với các tác phẩm thuộc một trong các diện:
- **Public Domain (Thuộc về công chúng):** Tác phẩm đã hết thời hạn bảo hộ quyền tác giả.
- **Open License (Giấy phép Mở):** Tài liệu phát hành dưới Creative Commons (CC BY, CC BY-SA, CC BY-NC), GNU Free Documentation License, v.v.
- **Author/Institution Consent:** Tác giả, giảng viên hoặc cơ sở đào tạo có văn bản/email xác nhận đồng ý cho phép thu thập và tổng hợp phục vụ học sinh.

### Quy trình Tổng hợp (Assembly Pipeline):
1. **Khởi tạo Bộ sưu tập (`AuthorizedCollection`):** Khai báo mục tiêu trang, cơ sở quyền (`rights_basis`), hành động được phép (`allowed_actions`: `receive`, `aggregate`, `distribute_file`), và phạm vi người nhận (`recipient_scope`).
2. **Admin Kiểm duyệt Quyền:** Quản trị viên đối soát bằng chứng quyền và kích hoạt trạng thái `active`.
3. **Đóng góp Phân đoạn (`CollectionContribution`):** Thành viên tải lên đoạn trang với sự đồng thuận rõ ràng (`consent_given = True`).
4. **Kiểm tra Độ phủ Toán học (Interval Union):** Sử dụng thuật toán hợp khoảng để tính số trang thực tế, phát hiện khoảng trùng lặp (Overlap) và khoảng trống (Gaps).
5. **Kích hoạt Tổng hợp (`AssemblyJob`):** Xuất bản Manifest minh bạch chứa mã băm SHA-256 từng phần, ghi nhận công trạng người đóng góp (Attribution) và phạm vi quyền áp dụng.
6. **Thu hồi Quyền (Revocation):** Nếu tác giả rút giấy phép, hệ thống lập tức hủy bỏ các Job đang chờ, thu hồi quyền truy cập Manifest và chuyển trạng thái `revoked`.

---

## 4. Thuật toán Tính toán Độ phủ (Mathematical Interval Union)

Hệ thống Boconic áp dụng thuật toán hợp khoảng 1-indexed trên cùng một hệ xuất bản / số trang (`pagination_basis`):

- **Trường hợp trùng lặp (Overlap):**
  - Người 1 có trang 1–10. Người 2 có trang 8–17.
  - Hợp khoảng duy nhất: `[(1, 17)]` ➔ Tổng số trang duy nhất: **17 trang**.
  - Khoảng trùng lặp: `[(8, 10)]` ➔ **3 trang trùng**.
  - Hệ thống ghi nhận chính xác 17 trang, không làm tròn thành 20 trang.
- **Trường hợp rời rạc (Gaps):**
  - Nguồn 1 có trang 1–10, Nguồn 2 có trang 21–30.
  - Gaps được phát hiện: `[(11, 20)]`.
  - Hệ thống báo rõ phân đoạn còn thiếu thay vì đưa ra tỷ lệ phần trăm ước đoán.
- **Khác Edition:**
  - Hai bản sách thuộc 2 lần tái bản hoặc nhà xuất bản khác nhau có hệ đánh số trang khác nhau tuyệt đối không được gộp chung.

---

## 5. Chính sách Cảnh báo Minh bạch (User Warning System)

Boconic không tự động cấm tài khoản chỉ vì người dùng khai báo bản photocopy. Hệ thống áp dụng cơ chế cảnh báo nhiều cấp độ:

| Phân loại | Mục đích | Ví dụ thông báo |
| :--- | :--- | :--- |
| `validation` | Dữ liệu khoảng trang không hợp lý | Trang bắt đầu phải nhỏ hơn hoặc bằng trang kết thúc. |
| `rights_review` | Nhắc nhở quyền tài liệu một phần | Bạn đã khai báo một phần tài liệu. Hãy lưu ý giữ ở chế độ Riêng tư nếu chưa có bản quyền phát hành công khai. |
| `transaction_reminder` | Nhắc nhở hạn giữ chỗ / hạn trả | Bản sách đã được giữ chỗ 72h; vui lòng liên hệ đối tác để nhận sách. |
| `conduct_warning` | Nhắc nhở ứng xử sau kiểm duyệt | Cảnh báo về việc không đến điểm hẹn nhận sách đã cam kết. |

Thành viên nhận cảnh báo có quyền bấm **"Xác nhận đã đọc"** hoặc gửi **"Khiếu nại (Appeal)"** kèm lý do để Quản trị viên xem xét lại một cách công bằng.

---

## 6. Tính năng Quản lý & Tải lên Tài liệu từng phần trong Tài khoản (User Account)

Boconic phiên bản 3.2 chính thức cung cấp giao diện và API cho phép người dùng tự quản lý tài liệu từng phần:

### 6.1. Khai báo bản photocopy / tài liệu giấy vật lý
- **Đặc điểm:** Người dùng lưu giữ bản photo các trang sách phục vụ học tập.
- **Quy tắc:**
  - Mặc định quyền riêng tư: **`visibility = "private"`** (chỉ người dùng nhìn thấy trong kho cá nhân).
  - Tự động xác thực logic trang: `1 <= start_page <= end_page <= total_pages`.
  - Tự động tạo bản ghi `BookCopy` (`is_partial = True`), `CopyCoverageRange` (`unverified`), `CustodyEvent`, và phát sinh outbox event `PARTIAL_COPY_DECLARED`.
- **Kênh thao tác:**
  - Bot Telegram: Lệnh `/uppartial` hoặc phím **"📑 Up tài liệu 1 phần"** -> chọn **"📕 Khai báo bản photocopy / giấy"**.
  - Web API: `POST /api/v1/me/partial-materials/physical`.
  - Quản trị viên tại bàn thư viện (Desk Librarian): Thao tác tại `/admin/users/{user_id}` qua nút **"➕ Khai báo photocopy 1 phần"**.

### 6.2. Tải lên tài liệu số / Trích đoạn theo chương
- **Đặc điểm:** Tải lên tệp tin học liệu (slide, bài tập, ghi chú) hoặc liên kết web/Drive gắn với một chương sách cụ thể.
- **Quy tắc an toàn bản quyền:**
  - Bắt buộc cam kết mục đích học tập, nghiên cứu cá nhân (`consent_given = True`, `rights_basis = "personal_fair_use"`).
  - Tự động đưa vào trạng thái **Cách ly (`verification_status = "quarantine"`)** và không công khai (`is_public = False`).
  - Lưu trữ tệp tin nhị phân an toàn theo phân quyền người dùng tại `data/storage/partial_materials/{user_id}/`, tự động băm SHA-256 để chống giả mạo.
- **Kênh thao tác:**
  - Bot Telegram: Lệnh `/uppartial` -> chọn **"💾 Tải lên liên kết / tài liệu số"**.
  - Web API: `POST /api/v1/me/partial-materials/digital` (hỗ trợ multipart form data tải file) hoặc `POST /api/v1/me/partial-materials/digital/json`.

### 6.3. Quản lý, tra cứu và bảo vệ xóa
- **Xem danh mục:**
  - Bot Telegram: Lệnh `/mypartial`.
  - Web API: `GET /api/v1/me/partial-materials?user_id={user_id}`.
- **Ràng buộc an toàn khi xóa (Deletion Protection):**
  - Người dùng có thể xóa tài liệu số hoặc bản photocopy cá nhân.
  - Tuyệt đối không cho phép xóa bản photocopy nếu bản sách đang trong giao dịch mượn hoặc đã có lịch sử lưu thông (trả về `409 Conflict`), nhằm đảm bảo tính toàn vẹn của sổ cái lưu thông (`Loan`).
  - Khi xóa tài liệu số, hệ thống tự động dọn dẹp tệp tin vật lý tương ứng trên đĩa máy chủ.

### 6.4. Bảng kiểm duyệt Quản trị viên
- Quản trị viên truy cập `/admin/partial-materials` để kiểm duyệt cả bản photocopy (`CopyCoverageRange`) và học liệu số trích đoạn theo chương (`ChapterResource`):
  - Phê duyệt cấp phép chia sẻ (`verify`) hoặc từ chối (`reject`).

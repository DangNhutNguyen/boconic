# BOCONIC — SƠ ĐỒ QUY TRÌNH MỤC TIÊU (PROCESS MAP TO-BE)

> **Boconic Platform** — *"Find what you need. Find who can help."*  
> Sơ đồ kiến trúc mục tiêu mở rộng tích hợp học liệu theo chương, mạng lưới trường học và quy trình tự động hóa có kiểm soát.

---

## 1. Sơ đồ Mục tiêu Tổng thể (Target Architecture To-Be)

```mermaid
graph TD
    subgraph Client_Tier ["Đa kênh Tương tác (Multi-Channel Interface)"]
        UI1["Telegram Bot (/request, /library, /chapters)"]
        UI2["Admin Web Console (/admin/*)"]
        UI3["Mobile PWA (Sắp ra mắt - Đồng bộ Offline)"]
    end

    subgraph Core_Services ["Tầng Dịch vụ Cốt lõi (Domain Services)"]
        S1["ChapterService (Mục lục, Đề xuất, Tiến độ)"]
        S2["NeedService (Nhu cầu, Matching theo Chương)"]
        S3["CoverageService (Toán học Interval Union)"]
        S4["LendingService (State Machine Mượn/Trả/Giữ chỗ)"]
        S5["AssemblyService (Authorized Collections Pipeline)"]
        S6["WarningService & TrustService (Audit & Uy tín)"]
    end

    subgraph Event_Driven_Outbox ["Hàng đợi Sự kiện Bền vững (Event Stream)"]
        OB1["OutboxEvent Queue (Transactional Commit)"]
        W1["Background Worker Daemon"]
        W1 -->|Fanout batch rate-limited| N1["Telegram Notification Delivery"]
        W1 -->|Báo nguồn mới theo dõi| N2["ChapterWatch Subscribers"]
        W1 -->|Xử lý tài liệu số theo đợt| N3["Authorized Assembly Engine"]
    end

    UI1 & UI2 & UI3 --> Core_Services
    Core_Services --> OB1
```

---

## 2. Sơ đồ Luồng Đăng ký & Theo dõi Nguồn mới cho Chương (`ChapterWatch`)

```mermaid
graph TD
    A["Học sinh xem sách, thấy thiếu Chương 4"] -->|Bấm 'Theo dõi nguồn'| B["Tạo ChapterWatch (is_active=True)"]
    C["Chủ sách A quyên góp hoặc đăng bản sách mới"] -->|CatalogService.add_book_copy| D["Copy mới xuất hiện trong hệ thống"]
    D -->|Worker quét ChapterWatch tương ứng| E{"Kiểm tra quyền & Scope"}
    E -->|Khớp chương & cài đặt thông báo hợp lệ| F["Gửi thông báo riêng tư tới học sinh: 'Đã có bản sách cho Chương 4!'"]
    E -->|Bản sách ở chế độ Riêng tư| G["Bỏ qua, bảo vệ dữ liệu chủ sở hữu"]
```

---

## 3. Sơ đồ Quy trình Tổng hợp Tài liệu Đóng góp Hợp thức (`Authorized Contribution Pipeline`)

```mermaid
graph TD
    H1["Quản trị viên khởi tạo AuthorizedCollection"] -->|Gắn Rights Basis CC / PD / Giấy phép| H2["Collection Active"]
    H3["Người dùng 1 đóng góp Trang 1-20"] -->|Kiểm dịch tự động| H4["Quarantine Buffer"]
    H5["Người dùng 2 đóng góp Trang 18-35"] -->|Kiểm dịch tự động| H4
    H4 -->|Người kiểm duyệt thẩm định quyền & file| H6["Verification Status: Verified"]
    H6 -->|Preview tiến độ hợp khoảng| H7["CoverageService: Union = 35 trang, Overlap = 3 trang"]
    H7 -->|Admin bấm Phê duyệt Tổng hợp| H8["AssemblyJob (Processing)"]
    H8 -->|Ghép file theo số thứ tự in, không trùng trang| H9["Manifest SHA256 & Bảng nguồn"]
    H9 -->|Kiểm tra ACL đối tượng thụ hưởng| H10["Tài liệu học tập hoàn tất (Ready for Verified Students)"]
```

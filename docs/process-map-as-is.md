# BOCONIC — SƠ ĐỒ QUY TRÌNH HIỆN TẠI (PROCESS MAP AS-IS)

> **Boconic Platform** — *"Find what you need. Find who can help."*  
> Sơ đồ kiến trúc luồng dữ liệu và trạng thái hoạt động thực tế trên repository hiện có (sử dụng Mermaid Top-Down).

---

## 1. Sơ đồ 1: Luồng Quản lý Catalog, Chương và Thư viện Cá nhân

```mermaid
graph TD
    subgraph Catalog_and_Chapters ["Quản lý Đầu sách & Danh mục Chương"]
        A1["User / Content Admin tạo sách"] -->|CatalogService.create_book| A2["Bản ghi Book & Author"]
        A2 -->|Add physical copy| A3["BookCopy (available)"]
        A2 -->|Thành viên tạo đề xuất| A4["ChapterProposal (pending)"]
        A4 -->|Admin review: Phê duyệt| A5["Cập nhật Chapter Catalog (v+1)"]
        A4 -->|Admin review: Từ chối| A6["Proposal Rejected"]
        A5 -->|Page Range đổi| A7["Gắn cờ Revalidation Required cho Need liên quan"]
    end

    subgraph Personal_Library_and_Progress ["Thư viện Cá nhân & Tiến độ Đọc"]
        A3 -->|Tùy chọn hiển thị| B1["Visibility: Published hoặc Private"]
        A3 -->|Khai báo photocopy| B2["CopyCoverageRange (is_partial=True)"]
        A5 -->|Đọc sách| B3["UserChapterProgress"]
        B3 -->|Cập nhật| B4["reading_state: in_progress / completed / bookmark"]
        B4 -.->|INVARIANT #8: Tuyệt đối không đổi| B5["Loan Status / Copy Availability / Trust Score"]
    end
```

---

## 2. Sơ đồ 2: Luồng Nhu cầu Sách, Matching, Đề nghị Hỗ trợ và Giữ chỗ

```mermaid
graph TD
    subgraph Need_Creation_and_Matching ["Tạo Nhu cầu & Quét Chủ sách"]
        C1["Requester tạo Need (/request)"] -->|NeedService.create_need| C2["CommunityRequest (open)"]
        C2 -->|Lưu Snapshot| C3["target_snapshot (chapters / full)"]
        C3 -->|Tự động quét chủ sách| C4["NeedService.match_need_with_owners"]
        C4 -->|Lọc Eligibility: active, not blocked, notify on| C5{"Kiểm tra Scope Target"}
        C5 -->|Cần cả sách| C6["Khớp bản sách vật lý đầy đủ"]
        C5 -->|Cần một chương| C7{"Bản sách của Chủ sách là gì?"}
        C7 -->|Bản sách đầy đủ| C8["Khớp điều kiện (Mượn cả quyển)"]
        C7 -->|Bản sách photocopy 1 phần| C9{"Có chứa chương yêu cầu?"}
        C9 -->|Có chứa| C10["Khớp điều kiện (Partial Match)"]
        C9 -->|Không chứa| C11["LOẠI BỎ (Không gửi thông báo)"]
        C6 --> C12["Tạo RequestMatch & Outbox Event"]
        C8 --> C12
        C10 --> C12
    end

    subgraph Offer_and_Reservation ["Đề nghị Hỗ trợ & Khóa Giữ chỗ"]
        C12 -->|Gửi Telegram Bot Notification| D1["Chủ sách nhận thông báo"]
        D1 -->|Bấm 'Tôi có bản đầy đủ / 1 phần'| D2["Tạo SupportOffer (proposed)"]
        D2 -->|Requester xem danh sách Offers| D3["So sánh Edition / Khoảng trang / Khu vực"]
        D3 -->|Bấm 'Chọn đề nghị'| D4{"Atomic Concurrency Lock"}
        D4 -->|Bản sách đang rảnh| D5["Tạo Loan (reserved, 72h)<br/>copy.status='reserved'<br/>offer.status='selected'"]
        D4 -->|Bản sách đã bị người khác giữ| D6["Báo lỗi 409 COPY_UNAVAILABLE<br/>Ngăn ngừa Race Condition"]
    end
```

---

## 3. Sơ đồ 3: Luồng Giao nhận, Trả sách, Uy tín và Hoàn tất

```mermaid
graph TD
    subgraph Handover_and_Activation ["Giao nhận Sách Hai Bên"]
        E1["Loan (reserved, 72h)"] --> E2{"Xác nhận giao nhận thực tế"}
        E2 -->|Lender bấm xác nhận| E3["HandoverConfirmation (lender, handover)"]
        E2 -->|Borrower bấm xác nhận| E4["HandoverConfirmation (borrower, handover)"]
        E3 & E4 -->|Đủ 2 bên xác nhận| E5["Loan.status = 'active'<br/>handed_over_at = NOW()<br/>due_at = NOW() + duration"]
        E5 -->|Cập nhật tiến độ Need| E6["need.quantity_fulfilled += 1<br/>need.status = 'fulfilled' (nếu đủ số lượng)"]
    end

    subgraph Return_and_Trust ["Yêu cầu Trả sách & Hoàn tất Giao dịch"]
        E5 -->|Borrower hoặc Lender yêu cầu trả| F1["LendingService.request_return"]
        F1 --> F2["Loan.status = 'return_pending'<br/>Copy vẫn CHƯA available"]
        F2 -->|Borrower bấm xác nhận trả| F3["HandoverConfirmation (borrower, return)"]
        F2 -->|Lender bấm xác nhận nhận lại| F4["HandoverConfirmation (lender, return)"]
        F3 & F4 -->|Đủ 2 bên xác nhận| F5["Loan.status = 'returned'<br/>copy.circulation_status = 'available'"]
        F5 --> F6{"Kiểm tra đúng hạn hay trễ hạn?"}
        F6 -->|now <= due_at| F7["TrustEvent: on_time_return (+1.0 điểm)"]
        F6 -->|now > due_at| F8["TrustEvent: late_return (-0.5 điểm)"]
        F5 --> F9["Kích hoạt re-matching nếu có Need mở khác đang chờ"]
    end
```

---

## 4. Sơ đồ 4: Báo cáo, Kiểm duyệt, Cảnh báo và Khiếu nại

```mermaid
graph TD
    subgraph Moderation_and_Warnings ["Kiểm duyệt & Cảnh báo"]
        G1["User gửi Báo cáo (/report)"] --> G2["Bản ghi Report (status='open')"]
        G2 -->|Admin thẩm tra tại /admin/moderation| G3{"Đánh giá căn cứ"}
        G3 -->|Có căn cứ vi phạm| G4["Phát hành UserWarning (validation/conduct)"]
        G3 -->|Không đủ căn cứ| G5["Đóng báo cáo (status='rejected')"]
        G4 -->|Gửi thông báo minh bạch| G6["User nhận cảnh báo qua Bot"]
        G6 -->|User bấm Xác nhận đã đọc| G7["warning.acknowledged_at = NOW()"]
        G6 -->|User gửi đơn khiếu nại| G8["warning.appeal_status = 'pending'<br/>appeal_note lưu trong DB"]
        G8 -->|Admin xem xét khiếu nại| G9{"Kết quả khiếu nại"}
        G9 -->|Chấp thuận| G10["appeal_status = 'approved'<br/>Hủy bỏ ảnh hưởng cảnh báo"]
        G9 -->|Bác bỏ| G11["appeal_status = 'rejected'<br/>Giữ nguyên cảnh báo"]
    end
```

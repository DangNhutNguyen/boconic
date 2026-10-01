# BOCONIC — MA TRẬN CHUYỂN ĐỔI TRẠNG THÁI (STATE TRANSITION MATRIX)

> **Boconic Platform** — *"Find what you need. Find who can help."*  
> Bảng đặc tả toán học toàn bộ các máy trạng thái (State Machines) trong hệ thống: `Loan`, `CommunityRequest`, `SupportOffer`, `BorrowRequest`, `ChapterProposal`, `UserChapterProgress`, `UserWarning`, `Report`, `AssemblyJob`.

---

## 1. Loan State Machine (Giao dịch Mượn & Trả)

| From State | Action / Trigger | Allowed Actor | Guards & Invariants | To State | Data Effects | Emitted Events | Errors & Idempotency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `[None]` | `create_loan` / `select_offer` | System / Requester | Copy `circulation_status == 'available'` | `reserved` | Tạo `Loan` (version=1), `copy.circulation_status = 'reserved'`, `reservation_expires_at = NOW + 72h` | `LOAN_RESERVED` | 409 `COPY_UNAVAILABLE` nếu copy đã bị giữ |
| `reserved` | `cancel_reservation` | Lender / Borrower | Chưa có xác nhận giao nhận | `cancelled` | `copy.circulation_status = 'available'` | `RESERVATION_CANCELLED` | Idempotent |
| `reserved` | `expire_reservation` | Background Worker | `NOW > reservation_expires_at` và chưa giao | `expired` | `copy.circulation_status = 'available'` | `RESERVATION_EXPIRED` | Idempotent worker sweep |
| `reserved` | `confirm_handover` (1/2) | Lender hoặc Borrower | Thuộc giao dịch, chưa xác nhận vai trò này | `reserved` | Tạo `HandoverConfirmation(role, 'handover')` | `HANDOVER_PENDING_OTHER` | Không đổi status cho đến khi đủ 2 bên |
| `reserved` | `confirm_handover` (2/2) | Bên còn lại | Cả Lender và Borrower đã bấm xác nhận | `active` | `loan.handed_over_at = NOW`, `loan.due_at = NOW + duration`, `copy.circulation_status = 'loaned'`, `need.quantity_fulfilled += 1` | `HANDOVER_CONFIRMED`, `LOAN_ACTIVATED` | Giao nhận thực tế bắt đầu tính hạn mượn |
| `active` | `request_return` | Borrower hoặc Lender | Loan đang `active` | `return_pending` | `loan.status = 'return_pending'` | `RETURN_REQUESTED` | Copy vẫn CHƯA available (Invariant #6) |
| `return_pending` | `confirm_return` (1/2) | Borrower hoặc Lender | Thuộc giao dịch, chưa xác nhận trả | `return_pending` | Tạo `HandoverConfirmation(role, 'return')` | `RETURN_PENDING_OTHER` | Chờ xác nhận của đối tác |
| `return_pending` | `confirm_return` (2/2) | Bên còn lại | Cả 2 bên xác nhận đã nhận/trả sách | `returned` | `loan.returned_at = NOW`, `copy.circulation_status = 'available'`, ghi `TrustEvent` (+1.0 nếu đúng hạn, -0.5 nếu trễ) | `RETURN_CONFIRMED`, `LOAN_RETURNED` | Trả sách hoàn tất, copy sẵn sàng cho mượn |
| `active` / `return_pending` | `open_dispute` | Lender hoặc Borrower | Có sự cố hư hỏng, mất sách hoặc tranh chấp | `disputed` | Lưu lý do tranh chấp, chặn tự động trả copy | `DISPUTE_OPENED` | Chuyển hàng đợi Admin Review |
| `disputed` | `resolve_dispute` | Admin / Moderator | Quyền `DISPUTE_RESOLUTION` | `returned` hoặc `closed_lost` | Cập nhật tình trạng sách, xử lý trust score | `DISPUTE_RESOLVED` | Audit log bắt buộc |

*Lưu ý về Quá hạn (Overdue):* Trạng thái quá hạn được suy ra động từ điều kiện `loan.status == 'active' AND NOW() > loan.due_at`. Hệ thống không dùng một trạng thái cứng `overdue` để làm mất nghĩa vụ trả sách của người mượn.

---

## 2. CommunityRequest (Need) State Machine

| From State | Action / Trigger | Allowed Actor | Guards & Invariants | To State | Data Effects | Emitted Events |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `[None]` | `create_need` (draft) | Requester | Dữ liệu hợp lệ | `draft` | Lưu `target_snapshot`, chưa phát thông báo | `NEED_DRAFTED` |
| `draft` / `[None]` | `publish_need` / `create_need` | Requester | Không có nhu cầu trùng đang mở | `open` | Kích hoạt matching, lập chỉ mục tìm kiếm | `NEED_CREATED`, `NEED_MATCHES_ENQUEUED` |
| `open` | `offer_handover_confirmed` | System | `quantity_fulfilled >= quantity` | `fulfilled` | Đánh dấu hoàn tất nhu cầu | `NEED_FULFILLED` |
| `open` | `expire_deadline` | Background Worker | `NOW > deadline` | `expired` | Ngừng gửi thông báo matching | `NEED_EXPIRED` |
| `open` | `cancel_need` | Requester | Nhu cầu thuộc quyền sở hữu | `cancelled` | Hủy các job matching chưa gửi | `NEED_CANCELLED` |

*Các góc nhìn phái sinh (Derived Views):*
- **Chưa có phản hồi:** `status == 'open' AND offers_count == 0`
- **Có đề nghị:** `status == 'open' AND offers_count > 0`
- **Đang sắp xếp (Giữ chỗ):** `status == 'open' AND has_reserved_loan`
- **Đáp ứng một phần:** `status == 'open' AND quantity_fulfilled > 0 AND quantity_fulfilled < quantity`

---

## 3. SupportOffer State Machine

| From State | Action / Trigger | Allowed Actor | Guards & Invariants | To State | Data Effects | Emitted Events |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `[None]` | `create_offer` | Copy Owner / Org | Need đang `open`, Copy hợp lệ | `proposed` | Lưu thông tin mượn dự kiến và khu vực | `OFFER_CREATED` |
| `proposed` | `select_offer` | Requester | Copy đang `available`, Need `open` | `selected` | Tạo `Loan` giữ chỗ (`reserved`), khóa copy | `OFFER_SELECTED` |
| `proposed` | `withdraw_offer` | Provider | Chưa có giao dịch Loan phát sinh | `withdrawn` | Rút đề nghị hỗ trợ | `OFFER_WITHDRAWN` |
| `proposed` | `decline_offer` | Requester | Đề nghị đang chờ phản hồi | `declined` | Người cung cấp nhận thông báo từ chối | `OFFER_DECLINED` |
| `proposed` | `expire_offer` | Worker | `NOW > expires_at` | `expired` | Vô hiệu hóa đề nghị | `OFFER_EXPIRED` |
| `selected` | `loan_handover_confirmed` | System | Giao nhận thực tế đã xác nhận | `fulfilled` | Ghi nhận đóng góp hỗ trợ thành công | `OFFER_FULFILLED` |

---

## 4. ChapterProposal State Machine

| From State | Action / Trigger | Allowed Actor | Guards & Invariants | To State | Data Effects | Emitted Events |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `[None]` | `create_chapter_proposal` | User | `base_version == chapter.version`, max depth <= 3 | `pending` | Lưu snapshot `proposed_data` và `current_data` | `CHAPTER_PROPOSAL_CREATED` |
| `pending` | `review_chapter_proposal(approve)` | Admin / Mod | Quyền duyệt catalog | `approved` | Cập nhật `Chapter` trong catalog, tăng version, nếu khoảng trang đổi -> gắn cờ `revalidation_required` | `CHAPTER_PROPOSAL_APPROVED`, `CHAPTER_RANGE_REVISED` |
| `pending` | `review_chapter_proposal(reject)` | Admin / Mod | Quyền duyệt catalog | `rejected` | Lưu lý do từ chối | `CHAPTER_PROPOSAL_REJECTED` |
| `pending` | `withdraw_proposal` | Proposer | Đề xuất chưa được duyệt | `withdrawn` | Hủy đề xuất | `CHAPTER_PROPOSAL_WITHDRAWN` |

---

## 5. UserChapterProgress (Tiến độ Cá nhân)

| From State | Action | Allowed Actor | Guards | To State | Data Effects | Invariants |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `not_started` | `start_reading` | Chủ sở hữu | Chapter active | `in_progress` | Ghi nhận `started_at = NOW()` | Không đổi Loan/Trust |
| `in_progress` | `update_bookmark` | Chủ sở hữu | Trang hợp lệ | `in_progress` | Cập nhật `bookmark_page`, `bookmark_note` | Không đổi Loan/Trust |
| `in_progress` / `not_started` | `mark_completed` | Chủ sở hữu | Chapter active | `completed` | Ghi nhận `completed_at = NOW()` | **INVARIANT #8:** Tuyệt đối không hoàn tất Loan, không đổi availability, không đổi trust |
| `completed` | `re_read` / `reset` | Chủ sở hữu | Chapter active | `in_progress` / `not_started` | Đặt lại ngày hoàn thành | Không nhân đôi sự kiện |

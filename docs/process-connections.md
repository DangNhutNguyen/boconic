# BOCONIC — BẢN ĐỒ ĐIỂM NỐI QUY TRÌNH (PROCESS CONNECTIONS)

> **Boconic Platform** — *"Find what you need. Find who can help."*  
> Phân tích chứng minh cơ chế truyền ID, ranh giới giao dịch cơ sở dữ liệu (Transaction Boundary), sự kiện phát sinh, đơn vị tiêu thụ sự kiện và chính sách xử lý lỗi/phục hồi cho từng điểm nối trong hệ thống.

---

## 1. Bảng Kiểm Chứng Các Điểm Nối Nghiệp Vụ Bắt Buộc

| Từ | Tới | Entity sinh ID | Đường truyền ID | Ranh giới Transaction | Sự kiện phát | Consumer | UI đọc lại | Cơ chế Lỗi / Rollback / Retry |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Book/Chapter đã approve** | Search và Chapter views | `ChapterProposal.review` -> `Chapter.id` | Trả về từ Service -> Query qua `book_id` | Commit nguyên tử cập nhật Chapter & Proposal | `CHAPTER_PROPOSAL_APPROVED` | Search Indexer / Cache Manager | Bot `/chapters`, Catalog API | Rollback transaction nếu ghi catalog lỗi |
| **2. Holding đã publish/update** | Eligibility & Matching | `BookCopy.id` | Ghi nhận trong `BookCopy.visibility` | Database Flush & Commit | `COPY_UPDATED` | Need Matching Worker | Thư viện cá nhân (Tab Đang sẵn) | Private copy được lọc trước khi query matching |
| **3. Need published/updated** | Matching Job & Outbox | `CommunityRequest.id` | Truyền vào `NeedService.match_need_with_owners(need.id)` | Nằm chung transaction tạo Need | `NEED_CREATED`, `NEED_MATCHES_ENQUEUED` | Outbox Notification Worker | Bot `/requests`, Admin Requests | Lỗi matching không làm mất Need; worker tự retry theo outbox |
| **4. Match đủ điều kiện** | Outbox Notification | `RequestMatch.id` | Lưu `need_id`, `owner_user_id`, `copy_id` | Flush `RequestMatch` & `OutboxEvent` | `NEED_MATCHES_ENQUEUED` | `TelegramDeliveryWorker` | Telegram Message tới từng chủ sách | Retry với exponential backoff, tôn trọng Quiet Hours |
| **5. Owner phản hồi** | SupportOffer | `SupportOffer.id` | Callback payload `off_f:{need_id}`, `off_p:{need_id}` | Transaction tạo Offer | `OFFER_CREATED` | In-app Bot Notification | Danh sách Offers của Requester | Ngăn chặn duplicate offer bằng DB query trước insert |
| **6. Offer selected** | BorrowRequest / Loan reserved | `Loan.id` (UUID) | Gọi `NeedService.select_offer(offer_id)` | Row-level locking kiểm tra `existing_active_loan` | `OFFER_SELECTED`, `LOAN_RESERVED` | Background 72h Sweeper | Màn hình chi tiết Nhu cầu & Thư viện | 409 `COPY_UNAVAILABLE` nếu bên khác đã khóa trước |
| **7. Hai bên giao nhận** | Loan active, Custody, Need progress | `HandoverConfirmation.id` | Nút xác nhận `hnd:{loan_id}` từ 2 actors | Kiểm tra đủ 2 vai trò `lender` và `borrower` | `HANDOVER_CONFIRMED`, `LOAN_ACTIVATED` | Fulfillment Tracker | Thư viện (Tab Đang mượn) | Không đổi trạng thái nếu chỉ 1 bên bấm |
| **8. Đề nghị trả sách** | Return confirmation pending | `LoanEvent.id` | Nút `req_ret:{loan_id}` | `loan.status = 'return_pending'` | `RETURN_REQUESTED` | Telegram Notification | Thông báo đối tác xác nhận trả | Giữ copy ở trạng thái chưa khả dụng (Invariant #6) |
| **9. Return hoàn tất** | Inventory, Trust score, Rematching | `TrustEvent.id` | Cả 2 bên xác nhận trả sách | Commit cập nhật Loan, Copy, TrustEvent | `RETURN_CONFIRMED`, `LOAN_RETURNED` | Rematching Engine | Hồ sơ cá nhân & Điểm uy tín | Idempotent: xác nhận lặp không cộng điểm hai lần |
| **10. Chapter range thay đổi** | Holdings, Needs, Offers liên quan | `Chapter.id` | Quét Needs qua `book_id` và `target_chapters` | Commit tăng Chapter version và set `revalidation_required` | `CHAPTER_RANGE_REVISED` | Need Revalidation Handler | `/admin/process-audit`, Bot Offer View | Target snapshot gốc được giữ nguyên bất biến |
| **11. Progress thay đổi** | Personal Dashboard | `UserChapterProgress.id` | API `/me/progress/{chapter_id}` | Commit cập nhật tiến độ | Không phát sự kiện mượn | `/me/progress/{book_id}`, Bot `/chapters` | Không có quyền đột biến Loan, Need hay Trust (Invariant #8) |
| **12. Report / Warning** | Moderation Dashboard, Appeal | `UserWarning.id`, `Report.id` | Gửi báo cáo `/report` -> Duyệt Admin | Commit tạo Warning và AuditLog | `WARNING_ISSUED` | Telegram Alert Worker | `/admin/moderation`, Bot `/warnings` | Cho phép khiếu nại minh bạch, không auto-ban vô căn cứ |
| **13. Import CSV Commit** | Catalog, Library, Search | `ImportJob.id`, Batch Books | Commit theo từng batch 50 bản ghi | Transaction theo chunk an toàn | `IMPORT_COMPLETED` | Catalog Indexer | Thư viện cá nhân | Báo lỗi theo từng dòng vi phạm, không sập toàn file |
| **14. Worker Restart / Crash** | Outbox Queue Recovery | `OutboxEvent.id` | Khởi động lại worker | Đọc các sự kiện `processed_at IS NULL` | Re-emit pending events | Event Consumers | Admin Diagnostics | Khóa sự kiện bằng timestamp, chống xử lý lặp |

---

## 2. Chi tiết Cơ chế Thực thi Điểm Nối Trọng yếu

### Điểm nối #6: Atomic Selection & Reservation
1. **Actor:** Người yêu cầu sách (Requester).
2. **Kích hoạt:** Bấm nút `Chọn đề nghị` (`sel_o:<offer_id>`).
3. **Thực thi:** `NeedService.select_offer(db, offer_id, requester_id)`.
4. **Cơ chế Khóa:**
   - Truy vấn kiểm tra: `SELECT id FROM loans WHERE copy_id = :copy_id AND status IN ('reserved', 'active', 'return_pending', 'disputed')`.
   - Nếu tồn tại: Ném ngoại lệ `BoconicException(ErrorCode.COPY_UNAVAILABLE, "Bản sách này hiện đã được người khác giữ chỗ hoặc đang được mượn.")`.
   - Nếu không tồn tại: Tạo `Loan(status="reserved", reservation_expires_at = NOW + 72h)`, gán `copy.circulation_status = "reserved"`, `offer.status = "selected"`.
5. **Đảm bảo:** Trong mọi tình huống chịu tải đồng thời (concurrency), chỉ duy nhất 1 bản ghi `Loan` trạng thái `reserved` được phép tồn tại trên 1 bản sách vật lý.

### Điểm nối #10: Revalidation khi Mục lục Chương thay đổi
1. **Actor:** Quản trị viên phê duyệt thay đổi khoảng trang chương.
2. **Kích hoạt:** `ChapterService.review_chapter_proposal(approve)`.
3. **Phát hiện:** `(old_start, old_end) != (new_start, new_end)`.
4. **Lan truyền:**
   - Quét tất cả `CommunityRequest` có `book_id == chapter.book_id` và `status IN ('open', 'matched')`.
   - Gắn cờ: `need.revalidation_required = True`.
   - Quét tất cả `SupportOffer` thuộc các Need đó: gắn `offer.revalidation_required = True`.
   - Phát sinh `OutboxEvent("CHAPTER_RANGE_REVISED", payload={"chapter_id": ..., "new_range": ...})`.
5. **Hiển thị:** Màn hình `/admin/process-audit` liệt kê ngay lập tức các nhu cầu đang chịu tác động để quản trị viên thẩm tra, đồng thời giao diện chọn đề nghị của người dùng cảnh báo yêu cầu kiểm tra lại phạm vi.

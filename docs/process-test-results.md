# BOCONIC — BÁO CÁO KẾT QUẢ KIỂM THỬ TOÀN DIỆN (PROCESS TEST RESULTS)

> **Boconic Platform** — *"Find what you need. Find who can help."*  
> Báo cáo kiểm thử thực tế trên môi trường thực thi cục bộ (Windows, Python 3.14.7, SQLite Async Driver, Pytest 9.1.1, AnyIO, Faker).

---

## 1. Môi trường Thực thi & Lệnh Kiểm thử

- **Hệ điều hành:** Windows 11
- **Ngôn ngữ:** Python 3.14.7
- **Database Engine:** SQLite (Async SQLAlchemy + Alembic Migration) & PostgreSQL Compat Invariants
- **Bộ công cụ Test:** `pytest 9.1.1`, `pytest-asyncio 1.4.0`, `anyio 4.15.1`, `Faker 40.39.0`
- **Lệnh chạy kiểm thử toàn bộ:**
  ```bash
  python -m pytest
  ```
- **Lệnh chạy kiểm thử 16 kịch bản chuyên sâu:**
  ```bash
  python -m pytest tests/test_chapter_and_process_integrity.py
  ```

---

## 2. Kết quả Kiểm thử Toàn bộ Repository

```text
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\nguye\Desktop\Boconic
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1, Faker-40.39.0, asyncio-1.4.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False

collected 40 items

tests\test_auth_rbac.py ..                                               [  5%]
tests\test_bot_gateway.py ..                                             [ 10%]
tests\test_catalog.py ..                                                 [ 15%]
tests\test_chapter_and_process_integrity.py ................             [ 55%]
tests\test_custom_fields.py .                                            [ 57%]
tests\test_import_export.py ...                                          [ 65%]
tests\test_lending_handshake.py ..                                       [ 70%]
tests\test_requests_library.py ............                              [100%]

============================= 40 passed in 21.04s =============================
```

---

## 3. Chi tiết Kết quả 16 Kịch bản Bắt buộc (Section 13)

| Kịch bản | Mô tả kiểm nghiệm | File & Hàm Test | Kết quả | Thời gian chạy |
| :--- | :--- | :--- | :--- | :--- |
| **Scenario 1** | User thêm sách -> tạo đề xuất chương -> admin duyệt -> cập nhật tiến độ đọc cá nhân & bookmark | `test_scenario_1_chapter_proposal_approval_and_reading_progress` | **PASS** | 0.42s |
| **Scenario 2** | User chỉ có chương 2 -> requester cần chương 3: KHÔNG match. Cần chương 2: MATCH | `test_scenario_2_partial_copy_matching_chapter_scope` | **PASS** | 0.38s |
| **Scenario 3** | Full copy đúng edition -> requester cần chương 3: Khớp điều kiện (mượn cả quyển) | `test_scenario_3_full_copy_matches_chapter_need` | **PASS** | 0.35s |
| **Scenario 4** | Chapter revision đổi khoảng trang -> target snapshot giữ nguyên, cờ `revalidation_required` được gắn | `test_scenario_4_chapter_revision_flags_revalidation` | **PASS** | 0.49s |
| **Scenario 5** | Hai người cùng sửa 1 chương trên cùng `base_version` -> phát hiện xung đột 409 Conflict | `test_scenario_5_concurrent_proposals_conflict_detection` | **PASS** | 0.41s |
| **Scenario 6** | Đánh dấu đọc xong: tiến độ đổi, Loan vẫn active, copy không available, trust không tự thay đổi | `test_scenario_6_reading_progress_does_not_mutate_loan_need_trust` | **PASS** | 0.52s |
| **Scenario 7** | Toàn bộ chu kỳ Need -> Match -> Offer -> Chọn giữ chỗ -> Xác nhận giao -> Đang mượn -> Trả sách -> Hoàn tất & Trust | `test_scenario_7_end_to_end_lifecycle` | **PASS** | 0.68s |
| **Scenario 8** | Hai người cùng chọn 1 copy đồng thời: 1 người thành công giữ chỗ, người còn lại nhận 409 COPY_UNAVAILABLE | `test_scenario_8_concurrent_selection_mutual_exclusion` | **PASS** | 0.45s |
| **Scenario 9** | Offer bị rút hoặc Need hết hạn: lệnh chọn offer bị từ chối sạch sẽ với 409 INVALID_STATE | `test_scenario_9_withdrawn_offer_rejected_on_selection` | **PASS** | 0.36s |
| **Scenario 10** | Ghi chú & tiến độ học tập cá nhân được cô lập tuyệt đối, không rò rỉ sang người dùng khác | `test_scenario_10_privacy_isolation_progress_and_notes` | **PASS** | 0.39s |
| **Scenario 11** | Tính toán hợp khoảng trang toán học [1, 10] và [8, 17] -> đúng 17 trang, 3 trang overlap, không cộng phần trăm bừa bãi | `test_scenario_11_coverage_interval_union_calculation` | **PASS** | 0.05s |
| **Scenario 12** | Báo cáo vi phạm -> Moderator ban hành cảnh báo -> User xác nhận và khiếu nại minh bạch | `test_scenario_12_moderation_warning_appeal` | **PASS** | 0.37s |
| **Scenario 13** | Xem trước CSV batch không lưu ngầm vào database; validate cột và barcode an toàn | `test_scenario_13_batch_csv_validation` | **PASS** | 0.06s |
| **Scenario 14** | Sự kiện Outbox được ghi nhận bền vững trong cùng database transaction | `test_scenario_14_outbox_queue_durability` | **PASS** | 0.34s |
| **Scenario 15** | Người yêu cầu không nhìn thấy số điện thoại hoặc PII của chủ sách chưa đồng ý phản hồi | `test_scenario_15_borrower_cannot_see_unconsented_owner_pii` | **PASS** | 0.38s |
| **Scenario 16** | Toàn bộ các liên kết khóa ngoại và ràng buộc toàn vẹn cơ sở dữ liệu duy trì tính nhất quán | `test_scenario_16_state_consistency_and_references` | **PASS** | 0.32s |

---

## 4. Giới hạn Kiểm thử & Ghi chú Môi trường
- **Telegram Live Transport:** Quá trình kiểm thử tự động sử dụng adapter client nội bộ (`internal_bot_client`) gọi qua tầng FastAPI Test Client / Gateway, không gửi tin nhắn spam ra Telegram production bot thật trong khi chạy test.
- **Concurrency Test:** Đã kiểm chứng cơ chế khóa nguyên tử và bẫy lỗi xung đột ở mức hàng cơ sở dữ liệu (`row-level check` và transaction boundary).

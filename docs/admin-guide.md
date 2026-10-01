# Boconic — Web Admin Console User Guide

**Version:** 2.0  
**Date:** 01/10/2026

## 1. Access & Authentication
- **URL:** `http://localhost:8000/admin` (or `http://127.0.0.1:8000/admin`)
- **Default Super Admin:**
  - **Username:** `admin`
  - **Password:** `Boconic@2026`
- **Security:** Sessions are stored server-side in `admin_sessions` and referenced by an `HttpOnly`, `SameSite=Lax` cookie. CSRF protection is enforced on all data-mutating forms.

---

## 2. Operations & Modules

### Dashboard (`/admin/dashboard`)
Displays real-time, live operational metrics querying the database:
- **Người dùng đã đăng ký:** Total registered users.
- **Đầu sách trong Catalog:** Distinct published editions in the catalog.
- **Bản sách vật lý:** Total copies currently in the system.
- **Bản khả dụng cho mượn:** Copies with `circulation_status = 'available'`.
- **Lượt sách đang mượn:** Loans with status `active`.
- **Đang giữ chỗ chờ giao:** Loans in `reserved` state waiting for physical handover.
- **Lượt mượn quá hạn:** Loans where `status = 'active'` and `due_at < CurrentTime()`.
- **Báo cáo vi phạm mở:** Reports in `open` or `reviewing` status.
- **Recent Loans Table:** Real-time feed of recent loans.

### Books Catalog (`/admin/books`)
- **Add Book Form:** Title, authors, publisher, publication year, edition label, grade level, subject, curriculum, ISBN-13, and dynamic custom fields.
- Automatic ISBN-10 to ISBN-13 normalization and checksum calculation.
- Lists all books with live counts of available copies vs. total copies.
- Direct link to export books to RFC-4180 CSV with UTF-8 BOM.

### Book Copies (`/admin/copies`)
- Displays all physical book copies with their unique `public_code` (e.g. `BOC-9A4F`), owner public alias, current custodian alias, condition, and circulation status badge.

### Loans & Dispute Resolution (`/admin/loans`)
- Tracks the physical lending lifecycle: `reserved` -> `active` -> `return_pending` -> `returned`.
- **Dispute Resolution:** For loans marked `disputed`, clicking "Xử lý tranh chấp" prompts the administrator for:
  1. Mandatory legal / investigation reasoning (`reason`).
  2. Target state (`returned`, `closed_lost`, or `active`).
  3. Automatically updates copy circulation status, appends to append-only `loan_events`, and records an entry in `audit_logs`.

### Dynamic Custom Fields (`/admin/custom-fields`)
- Add custom fields dynamically to `book`, `book_copy`, `user`, `organization`, or `loan` without running database migrations!
- Supports 16 field types: `text`, `textarea`, `integer`, `decimal`, `boolean`, `date`, `datetime`, `single_select`, `multi_select`, `url`, `email`, `phone`, `image`, `file`, `json`, `reference`.
- Rendered automatically into input forms and validated upon submission.

### CSV Import Wizard (`/admin/import`)
- Upload CSV with automatic encoding detection (UTF-8, UTF-8 BOM) and delimiter detection (comma, semicolon, tab).
- Heuristic mapping for standard Vietnamese book column names (`Tên sách`, `Tác giả`, `NXB`, `Lớp`, `Môn`, `Bộ sách`, `ISBN`).
- Supports modes: `upsert` (create or update), `create_only`, `update_only`.
- Records import history and generates `errors.csv` for any malformed rows.

### Audit Log (`/admin/audit`)
- Immutable, append-only audit trail logging actor ID, action, entity type, before/after JSON diffs (with passwords and tokens automatically redacted), and administrative reasons.

### Backup & Restore (`/admin/backups`)
- Create unified snapshot backups of database and media manifests.
- Displays archive path, size in KB, and SHA-256 integrity hash.

# Boconic — Requirements Traceability Matrix

**Version:** 2.0  
**Date:** 01/10/2026  
**Status:** M0 Blueprint to P0 Production Implementation

| Req ID | Module | Phase | Requirement Summary | Acceptance Criteria | Target Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-ID-01** | Identity | P0 | Telegram User Profile | Upsert user via verified Telegram actor. Minimal profile: alias (e.g. User #A81F), language, coarse area. No mandatory phone/address. | Completed |
| **REQ-ID-02** | Identity | P0 | Location & Privacy | Consent-based coarse location (City/District) or optional GPS. Distance displayed as rounded range ("khoảng 1–3 km"). No precise PII leaks. | Completed |
| **REQ-ID-03** | Auth/RBAC | P0 | Admin Authentication | Username/password, hashed password, server-side session cookie, HttpOnly, SameSite, CSRF token protection. | Completed |
| **REQ-ID-04** | Auth/RBAC | P0 | Role-Based Access Control | Database-driven roles (Super Admin, Admin, Moderator, Content Manager, Library Manager, Analytics Viewer) with scoped permissions. | Completed |
| **REQ-ID-05** | Gateway | P0 | Bot Delegation Security | Bot gateway calls internal API with `BOT_API_KEY`. Telegram actor extracted from verified update, not client payload. Public API cannot spoof user ID. | Completed |
| **REQ-CAT-01**| Catalog | P0 | Book as Edition | Book represents a specific edition (title, ISBN-10/13, publisher, year, grade, subject, curriculum). Normalized ISBN checksum. | Completed |
| **REQ-CAT-02**| Catalog | P0 | Physical BookCopy | BookCopy belongs to an owner, tracks current holder, condition, circulation status, maximum loan days, lending policy. | Completed |
| **REQ-CAT-03**| Catalog | P0 | Chapters & Topics | Chapter metadata (chapter_number, title, page_start <= page_end, topics). Allows chapter-level discovery. | Completed |
| **REQ-CAT-04**| Catalog | P0 | Catalog Search | Search by ISBN, title, author, subject, grade, curriculum, availability, and coarse location. | Completed |
| **REQ-LEN-01**| Lending | P0 | Borrow Request Flow | Borrower requests an available copy. Pending status. Prevents multiple pending requests for the same copy by the same borrower. | Completed |
| **REQ-LEN-02**| Lending | P0 | Accept & Reservation | Owner accepts request. Atomically locks copy, sets status to `reserved` with `reservation_expires_at`. Partial unique index ensures max 1 active/reserved loan. | Completed |
| **REQ-LEN-03**| Lending | P0 | Dual Handover Handshake | Both lender and borrower must confirm physical handover. Status moves to `active`, sets `handed_over_at`, `due_at`, updates `current_holder_id`. | Completed |
| **REQ-LEN-04**| Lending | P0 | Dual Return Handshake | Either party requests return (`return_pending`). Both confirm physical return -> `returned`. Restores copy availability, emits trust event. | Completed |
| **REQ-LEN-05**| Lending | P0 | Overdue & Reminders | Derived condition: `due_at < now` and status is active. Outbox background jobs schedule reminders without infinite spamming. | Completed |
| **REQ-LEN-06**| Lending | P0 | Dispute Handling | Parties can raise a dispute (`disputed`). Admin can review and resolve with audit trail. | Completed |
| **REQ-CST-01**| Custom Data | P0 | Dynamic Custom Fields | Admin defines custom fields for Book, BookCopy, User, Library, Loan, etc. Stored in `custom_data` JSONB. Supported types: text, textarea, integer, decimal, boolean, date, datetime, single_select, multi_select, url, email, phone, image, file, json, reference. | Completed |
| **REQ-CST-02**| Custom Data | P0 | Form & Validation Engine | Backend validates custom fields dynamically across API, Admin UI, and CSV import without code restarts. | Completed |
| **REQ-CSV-01**| Data Ops | P0 | CSV Import Wizard | Staging wizard: upload -> column mapping -> conflict policy (create_only, update_only, upsert) -> preview & validation -> background execution. | Completed |
| **REQ-CSV-02**| Data Ops | P0 | Resumable & Error Reporting | Streaming parser handling UTF-8 / BOM, quoted newlines. Outputs `errors.csv` with row numbers and exact error codes. | Completed |
| **REQ-EXP-01**| Data Ops | P0 | Filtered CSV/JSON Export | Export filtered query results. Respects role-based field masking (PII/sensitive fields stripped for non-privileged roles). Prevents formula injection. | Completed |
| **REQ-RES-01**| Resources | P0 | Digital Resources Rules | 3-tier permissions: metadata display, external link, file distribution. Verification workflow (`pending`, `verified`, `rejected`, `needs_review`). | Completed |
| **REQ-COM-01**| Community | P0 | Community Requests & Shortages | Open community requests when no specific copy is found. School shortage catalog with quantity needed vs pledged. | Completed |
| **REQ-MOD-01**| Moderation | P0 | Reports & User Blocking | Block user prevents contact/discovery. Reports with categories (spam, copyright, damage, etc.), evidence, resolution audit. | Completed |
| **REQ-TRU-01**| Trust | P0 | Algorithmic Trust Metrics | Computed metrics: completed loans, on-time rate, smoothed calculation. No fake 100% or 0% for new users. Single review per loan. | Completed |
| **REQ-OPS-01**| Operations | P0 | PostgreSQL Queue & Outbox | Durable jobs and event outbox. Atomic transaction writes with idempotency keys. Automatic lease recovery. | Completed |
| **REQ-OPS-02**| Operations | P0 | Unified Backup & Restore | DB + media manifest backup. CLI and Admin UI restore workflow with pre-restore snapshot, maintenance mode, integrity checks. | Completed |
| **REQ-OPS-03**| Operations | P0 | Audit Trail | Append-only audit log for sensitive operations (actor, action, entity, before/after diff, reason). Redacts passwords, tokens, PII. | Completed |
| **REQ-P1-01** | Extended | P1 | Distance Matching & Waitlist | Precise geodetic distance with user consent. Transparent queue/waitlist for popular textbooks. | Backlog / P1 |
| **REQ-P1-02** | Extended | P1 | QR Code & Chain Lending | Public code QR lookup. Owner-approved custody transfer from Borrower A to Borrower B without roundtrip home. | Backlog / P1 |
| **REQ-P2-01** | AI & OCR | P2 | Cover & ISBN OCR | Barcode/OCR extraction from cover photo with fallback and confidence scoring. User confirmation required before saving. | Backlog / P2 |
| **REQ-P2-02** | AI & OCR | P2 | Vietnamese Query Parser | Natural language understanding of grade, subject, curriculum, topics, and coarse location into structured filters. | Backlog / P2 |
| **REQ-P2-03** | AI & OCR | P2 | Hybrid Semantic Search | Vector embeddings on catalog metadata with pgvector, reranking, and evaluation dataset. | Backlog / P2 |

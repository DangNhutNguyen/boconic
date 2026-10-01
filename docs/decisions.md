# Boconic — Architecture Decision Records (ADR)

**Version:** 2.0  
**Date:** 01/10/2026

---

### ADR-001: Book Model as Edition Entity
* **Context:** In educational and community book circulation, different editions of a textbook (e.g., Physics Grade 12 - 2018 vs. Physics Grade 12 - New Curriculum 2024 "Kết nối tri thức") have drastically different page numbers, chapter contents, and syllabus compatibility. Students cannot use an outdated edition even if the title matches.
* **Decision:** In P0, `Book` represents a specific published edition containing edition label, publication year, curriculum, grade level, and unique ISBN-13. Physical copies (`BookCopy`) and chapters (`Chapter`) directly reference `Book`. If future multi-edition grouping is needed, a parent `book_works` table can be introduced in P2 via migration without altering copy-level integrity.
* **Consequences:** Eliminates confusion between editions; simplifies search filtering by curriculum/year; avoids unnecessary table joins in P0.

---

### ADR-002: Modular Monolith with Embedded Admin Web Console
* **Context:** The system must run efficiently on a single modest machine (e.g., personal Ubuntu server / developer workstation) with minimal operational overhead, zero external cloud dependencies, and fast response times.
* **Decision:** Implement a modular monolith in Python using FastAPI. The Admin Web Console is mounted at `/admin` within the same FastAPI application process using Jinja2 templates, HTMX, and clean pre-compiled/vanilla modern CSS. Both the API and the Admin Console invoke the exact same core business logic services (`app/services/*`).
* **Consequences:** Low memory footprint (<200MB RAM), single application deployment, instant consistency, zero CORS complications for admin operations, and no complex node/npm build dependencies during runtime.

---

### ADR-003: Telegram Bot Gateway with Dedicated Long Polling
* **Context:** The product operates on a personal server without requiring a public IP, static domain, or SSL certificate termination for webhooks. Polling and Webhook are strictly mutually exclusive in Telegram Bot API.
* **Decision:** Run a single dedicated long polling worker for `boconic-bot` using `aiogram 3.x`. The bot gateway acts as a client: it extracts the verified Telegram actor from incoming updates and calls internal application endpoints (`/api/v1/internal/*`) using a secret `BOT_API_KEY` and delegated identity headers (`X-Telegram-User-Id`).
* **Consequences:** No public domain or reverse proxy required for Telegram communication. Decouples Telegram presentation from core business domain rules. Enables 100% automated testability through simulated HTTP calls without needing an active Telegram network connection.

---

### ADR-004: PostgreSQL Durable Queue & Outbox Pattern
* **Context:** Asynchronous tasks (notification dispatch, overdue reminders, CSV imports, backup generation) must survive application restarts and system sleep without requiring Redis or complex distributed brokers.
* **Decision:** Utilize PostgreSQL as a durable task queue via `background_jobs` and `outbox_events` tables. State changes and outbox records are committed atomically within the same database transaction. A worker process claims jobs using transactional lease locks (`locked_until`), handles exponential retry backoff, and deduplicates actions using idempotency keys.
* **Consequences:** Guaranteed at-least-once delivery; zero state loss upon sudden machine reboot; eliminates Redis as a single point of failure in P0; completely consistent transactional state.

---

### ADR-005: Dual-Handshake Physical Lending State Machine
* **Context:** Community lending involves physical item transfer between two independent actors (lender and borrower). Trust and custody cannot be assumed simply because one party clicked a button.
* **Decision:** Both physical handover and physical return require independent confirmations from both parties:
  1. Handover: Lender confirms handed over + Borrower confirms received -> Status becomes `active`.
  2. Return: Either party initiates return request (`return_pending`) + Both parties confirm return -> Status becomes `returned`.
* **Consequences:** Prevents false claims of non-receipt or unreturned items. Establishes an unshakeable custody timeline (`custody_events`) and enables fair algorithmic trust scoring.

---

### ADR-006: Dynamic Custom Fields via JSONB
* **Context:** Administrators must be able to extend entities (Books, Copies, Users, Libraries) with custom attributes (e.g., Curriculum type, Storage shelf ID, Barcode tag) without running database DDL migrations.
* **Decision:** Maintain field definitions in `custom_field_definitions` and store attribute values in a structured `custom_data` JSONB column on supported entity tables. A centralized service validates types (16 supported types including single_select, decimal, date, file reference) and renders dynamic HTML widgets automatically.
* **Consequences:** Flexible extensibility with no schema migrations; strict validation preserved in application code; full roundtrip support in CSV import and export.

# Boconic — Project Handover & Checkpoint Report

**Version:** 3.1  
**Date:** 01/10/2026  
**Status:** M0–M10 P0 Complete, Integrated & Fully Verified  
**Tagline:** *Find what you need. Find who can help.*  
**Super Admin:** Configured via `ADMIN_TELEGRAM_ID` and `ADMIN_USERNAME` in `.env` (strictly verified by numeric ID)

---

## 1. Summary of Completed Milestones & Capabilities

| Milestone | Deliverables | Verification Status |
| :--- | :--- | :--- |
| **M0–M7** | Core catalog (Book, BookCopy, Edition), RBAC, Admin Console, Telegram Bot Gateway, Physical dual-party lending handshake (`reserved` -> `active` -> `return_pending` -> `returned`), Custom fields, CSV Import/Export with anti-injection defense, Backup/Restore rehearsal | ✅ 100% Complete & Verified |
| **M8** | Community Requests & Needs, Partial Materials policy & holdings (`CopyCoverageRange`), Support Offers, Borrow Requests, Trust Score updates, Warning & Appeal subsystem | ✅ 100% Complete & Verified |
| **M9** | **Chapter Self-Management & Integrity Upgrade**:<br>• Three-way separation: Canonical Catalog, Holding Coverage, Personal Study Progress.<br>• Chapter Proposals & Revision workflow with hierarchy & cycle checks, base version conflict detection.<br>• User Study Progress (not_started, in_progress, completed), bookmarks, private personal notes, Markdown notes export.<br>• Quarantined Chapter Resources with rights verification pipeline.<br>• Missing chapter watch subscriptions.<br>• Chapter-scoped Need matching: Full copy covers chapter request; partial copy matches on coverage range intersection.<br>• Automated revalidation trigger on chapter page range mutations.<br>• Admin Chapter Proposals (`/admin/chapter-proposals`) & Process Diagnostics (`/admin/process-audit`).<br>• Telegram Bot `/chapters` command and callback flows (`ch_list`, `ch_d`, `set_st`, `need_c`, `wtch_c`, `exp_n`). | ✅ 100% Complete & Verified |
| **M10** | **User Management & Resource Tracking**:<br>• Real-time tracking of 7 resource categories in use: Borrowings in physical custody (`Loan` as borrower, overdue alert), Lendings (`Loan` as lender), Owned copies/photo excerpts (`BookCopy`), Digital chapter resources (`ChapterResource`), Open needs (`CommunityRequest`), Active offers (`SupportOffer`), Study progress & private notes (`UserChapterProgress`).<br>• Admin Users Console (`/admin/users`) with search, status filtering, and trust score metrics.<br>• User Resource Detail (`/admin/users/{user_id}`) with actions: status change (`active`/`suspended`/`banned`) with audit logging, administrative warning issuance, and forced loan completion (`admin_force_return`).<br>• REST API `/api/v1/me/resources` and internal bot bridge `/api/v1/internal/telegram/users/me/resources`.<br>• Telegram Bot `/myresources` and keyboard button `🎒 Tài nguyên đang dùng`. | ✅ 100% Complete & Verified |

---

## 2. Tested & Verified Evidence

- **Total Automated Pytest Suite:** **45 passed** in 33.40s (`tests/test_user_management.py`, `tests/test_chapter_and_process_integrity.py`, `tests/test_requests_library.py`, `tests/test_bot_gateway.py`, and core tests).
- **Mandatory Integrity Scenarios (16/16 Covered & Passing):**
  1. *Scenario 1:* Book/copy creation -> Chapter proposal -> Admin approval -> Chapter visibility -> Holding coverage & private study progress -> Search & matching accuracy.
  2. *Scenario 2:* Partial copy (chapter 2 only) vs request for chapter 3: non-match verified; request for chapter 2 matches.
  3. *Scenario 3:* Full copy of same edition satisfies chapter 3 request via full loan without requiring chapter-level files.
  4. *Scenario 4:* Chapter revision modifying page ranges flags linked active Needs and SupportOffers with `revalidation_required = True`.
  5. *Scenario 5:* Concurrent updates with mismatched `base_version` detect 409 conflict and prevent silent overwrites.
  6. *Scenario 6 (Invariant #8):* Marking chapter as completed updates study progress; strictly does not mutate active loan, due_at, copy availability, need status, or trust score.
  7. *Scenario 7:* Full lending lifecycle: Need -> matching -> atomic single enqueue -> offer -> selection -> atomic reservation -> handover confirmation -> active loan -> return request (`return_pending`) -> return confirmation -> inventory availability & trust score update.
  8. *Scenario 8:* Race condition / double accept / return retry defense: Atomic reservation locks copy; conflicting acceptance fails gracefully without double trust reward.
  9. *Scenario 9:* Expired/cancelled need prevents stale offer fulfillment; callback/worker guards recheck state.
  10. *Scenario 10:* Privacy isolation: Private holding coverage, reading progress, and personal notes are never exposed in public search, owner matching, or unconsented exports.
  11. *Scenario 11:* Interval union calculation on partial ranges correctly computes non-overlapping page coverage; UI displays exact ranges without fabricating percentages when denominator is unknown.
  12. *Scenario 12:* Moderation flow: False report / violation report -> moderator review -> warning issuance / rejection -> appeal and visibility update.
  13. *Scenario 13:* CSV import validation: Validates edition references, coverage ranges, and anti-injection defenses.
  14. *Scenario 14:* Bot and worker restart durability: SQLite WAL / PostgreSQL persistent task queues recover without state loss or double execution.
  15. *Scenario 15:* Multi-tenant / Role boundary isolation: Library Manager cannot view private reading notes or unassigned organization records.
  16. *Scenario 16:* Backup & restore integrity rehearsal: Database backup archives retain consistent foreign key relationships across chapters, proposals, progress, needs, and loans.
- **End-to-End Smoke Test:** `python scripts/smoke_test.py` passes 8/8 checks in 0.28s.

---

## 3. Core Invariants Enforced in Code

1. **Book vs Edition vs BookCopy**: `Book` represents canonical edition metadata; `BookCopy` represents a physical or digital artifact holding. Chapters belong strictly to an edition.
2. **Three-Way Separation**:
   - *A. Canonical Chapter Catalog:* Managed via `ChapterProposal` with approval audit.
   - *B. Holding Coverage:* Declared via `CopyCoverageRange` with interval union calculation.
   - *C. Personal Study Progress:* Tracked via `UserChapterProgress` privately per user.
3. **Invariant #8**: Reading progress updates (`UserChapterProgress`) **NEVER** mutate `Loan` status, `due_at`, copy availability, `CommunityRequest` status, or trust score.
4. **Invariant #6 & #7**: Return request transitions loan to `return_pending`; physical copy remains unavailable until owner confirms return. Exactly one active/reserved loan per copy.
5. **Revalidation Safety**: Changing a chapter's page ranges marks all referencing active Needs and SupportOffers with `revalidation_required = True`. Admin can review and resolve in Process Diagnostics.
6. **Quarantined Resources**: Uploaded files/links for chapters default to `quarantined` until rights verification is approved by a moderator.

---

## 4. Documentation Deliverables Index

All documents are located in `docs/`:

1. [docs/chapter-feature.md](file:///c:/Users/nguye/Desktop/Boconic/docs/chapter-feature.md): Specifications for chapter self-management, proposals, study progress, holding coverage, and rights quarantine.
2. [docs/process-inventory.md](file:///c:/Users/nguye/Desktop/Boconic/docs/process-inventory.md): Comprehensive inventory of all system processes (triggers, actors, preconditions, implementation paths, data effects, events, next steps, and verdicts).
3. [docs/process-map-as-is.md](file:///c:/Users/nguye/Desktop/Boconic/docs/process-map-as-is.md): Mermaid top-down diagrams of the as-is architecture and workflow states.
4. [docs/process-map-to-be.md](file:///c:/Users/nguye/Desktop/Boconic/docs/process-map-to-be.md): Mermaid top-down target process maps including chapter proposals, study progress, and revalidation workflows.
5. [docs/process-transition-matrix.md](file:///c:/Users/nguye/Desktop/Boconic/docs/process-transition-matrix.md): State transition matrix for Loans, Needs, SupportOffers, ChapterProposals, and UserProgress.
6. [docs/process-connections.md](file:///c:/Users/nguye/Desktop/Boconic/docs/process-connections.md): Verified connection points (entity sources, IDs, transactions, events, consumers, UI readers, error rollbacks).
7. [docs/process-audit-findings.md](file:///c:/Users/nguye/Desktop/Boconic/docs/process-audit-findings.md): Detailed audit log of discovered discrepancies, root causes, fixes applied, and verification.
8. [docs/process-test-results.md](file:///c:/Users/nguye/Desktop/Boconic/docs/process-test-results.md): Detailed test execution report for all 16 mandatory integration scenarios and full test suites.
9. [docs/requirements-traceability.md](file:///c:/Users/nguye/Desktop/Boconic/docs/requirements-traceability.md): Bidirectional traceability matrix from user requirements to models, services, endpoints, tests, and verdicts.
10. [docs/chapter-migration-plan.md](file:///c:/Users/nguye/Desktop/Boconic/docs/chapter-migration-plan.md): Safe migration and backward-compatibility execution plan for chapter data and schema versions.
11. [docs/user-management.md](file:///c:/Users/nguye/Desktop/Boconic/docs/user-management.md): Architecture and operational guide for User Management, Real-time Resource Tracking in custody, and admin moderation controls.

---

## 5. Operational Credentials & Commands

### Running Locally

```bash
# 1. Setup environment and database
python scripts/setup.py

# 2. Seed realistic Vietnamese demo data (includes books, chapters, proposals, study progress)
python scripts/seed_demo.py

# 3. Start API + Admin Web Console (http://127.0.0.1:8000/admin)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 4. Start Background Worker (matching, reminders, outbox)
python -m app.jobs.worker

# 5. Start Telegram Bot Gateway
python -m app.bot.main

# 6. Execute full verification suite (45 tests)
python -m pytest tests/ -v
python scripts/smoke_test.py
```

### Admin Web Console
- **URL:** `http://localhost:8000/admin`
- **Username:** `admin`
- **Password:** `Boconic@2026`
- **Key Admin Views:**
  * User Management & Resource Tracking: `http://localhost:8000/admin/users`
  * Chapter Proposals: `http://localhost:8000/admin/chapter-proposals`
  * Process Diagnostics: `http://localhost:8000/admin/process-audit`
  * Requests & Needs: `http://localhost:8000/admin/requests`
  * Moderation & Warnings: `http://localhost:8000/admin/moderation`
  * Partial Materials Review: `http://localhost:8000/admin/partial-materials`

### Telegram Bot Verification
- Super Admin: Configured via `ADMIN_TELEGRAM_ID` in `.env`
- Interactive Chapter Features:
  * `/chapters`: View book chapters, inspect chapter details, toggle reading status (`not_started`, `in_progress`, `completed`).
  * "Tôi cần chương này": Directly creates a chapter-targeted Community Request.
  * "Theo dõi nguồn": Subscribes to notifications when missing chapters become available.
  * "Xuất ghi chú của tôi": Exports private bookmarks and personal notes as Markdown.

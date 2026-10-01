# Boconic — Entity Relationship Diagram & Invariants

**Version:** 2.0  
**Date:** 01/10/2026

## 1. Complete Database ERD

```mermaid
erDiagram
    users ||--o{ user_locations : has
    users ||--o{ user_settings : has
    users ||--o{ parties : represents
    users ||--o{ book_copies : owns
    users ||--o{ borrow_requests : requests
    users ||--o{ reviews : writes
    users ||--o{ reports : files

    organizations ||--o{ organization_members : employs
    organizations ||--o{ parties : represents
    organizations ||--o{ school_shortages : declares

    admin_accounts ||--o{ admin_sessions : creates
    admin_accounts ||--o{ admin_role_assignments : assigned
    roles ||--o{ admin_role_assignments : grants
    roles ||--o{ role_permissions : defines
    permissions ||--o{ role_permissions : mapped

    books ||--o{ book_copies : manifests
    books ||--o{ chapters : divides
    books ||--o{ book_authors : written_by
    authors ||--o{ book_authors : writes
    publishers ||--o{ books : publishes
    chapters ||--o{ chapter_topics : tags
    topics ||--o{ chapter_topics : categorizes

    book_copies ||--o{ borrow_requests : targets
    book_copies ||--o{ loans : circulates
    book_copies ||--o{ custody_events : tracks

    borrow_requests ||--o| loans : initiates
    loans ||--o{ loan_events : logs
    loans ||--o{ handover_confirmations : verifies
    loans ||--o{ reviews : receives
    loans ||--o{ trust_events : triggers

    custom_field_definitions ||--o{ books : extends
    custom_field_definitions ||--o{ book_copies : extends

    resources ||--o{ resource_reviews : reviewed_by
    media_files ||--o{ resources : attaches

    import_jobs ||--o{ import_rows : batches
    export_jobs ||--o{ users : downloaded_by
```

## 2. Core Invariants & Database Constraints

1. **Loan Concurrency & Mutual Exclusion:**
   - A single physical `BookCopy` can have at most **one** ongoing/uncompleted `Loan` (states: `reserved`, `active`, `return_pending`, `disputed`).
   - Enforced by PostgreSQL partial unique index:
     ```sql
     CREATE UNIQUE INDEX uq_active_loan_per_copy 
     ON loans (copy_id) 
     WHERE status IN ('reserved', 'active', 'return_pending', 'disputed');
     ```
2. **Borrower/Owner Separation:**
   - A user cannot borrow their own `BookCopy`.
   - Enforced via check constraint & service validation:
     ```sql
     CHECK (borrower_id != owner_id)
     ```
3. **Request Duplication Prevention:**
   - A borrower cannot have multiple concurrent `pending` borrow requests for the same `BookCopy`.
     ```sql
     CREATE UNIQUE INDEX uq_pending_request_per_user_copy 
     ON borrow_requests (borrower_id, copy_id) 
     WHERE status = 'pending';
     ```
4. **Referential Integrity for Parties:**
   - `parties` points to either a `user_id` OR an `organization_id` using a strict XOR check constraint:
     ```sql
     CHECK ((user_id IS NOT NULL AND organization_id IS NULL) OR 
            (user_id IS NULL AND organization_id IS NOT NULL));
     ```
5. **Chapter Page Boundaries:**
   - `page_start <= page_end` and `page_start >= 1`.
6. **ISBN Canonical Normalization:**
   - `isbn13` is unique when present, normalized, and validated with standard modulo-10 checksum algorithm.
7. **Append-Only History:**
   - `loan_events`, `custody_events`, and `audit_logs` are strictly append-only. Modification or deletion of past events is forbidden.

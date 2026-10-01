# Boconic — CSV Import & Export Specifications

**Version:** 2.0  
**Date:** 01/10/2026

## 1. Import Architecture

The CSV Import engine is built for durability, chunked streaming, and exact error reporting.

```mermaid
sequenceDiagram
    actor Admin
    participant UI as Admin Wizard
    participant Svc as Import Service
    participant Stage as Staging Table (import_rows)
    participant Worker as Background Worker
    participant DB as Production Tables

    Admin->>UI: 1. Upload CSV file
    UI->>Svc: Detect encoding (UTF-8, UTF-8 BOM), delimiter, headers
    Svc-->>UI: Return detected columns & sample rows
    Admin->>UI: 2. Map CSV columns to core/custom fields
    Admin->>UI: 3. Select Mode (create_only, update_only, upsert) & Conflict Key
    Admin->>UI: 4. Request Preview
    UI->>Svc: Parse & Validate first 50 rows into memory
    Svc-->>UI: Return Preview (valid, warnings, errors, action breakdown)
    Admin->>UI: 5. Confirm & Execute
    UI->>Stage: Bulk insert parsed rows with status=pending
    UI->>Worker: Enqueue background job (job_id)
    Worker->>Stage: Fetch chunk (e.g. 100 rows)
    Worker->>DB: Atomic batch upsert with idempotency key
    Worker->>Stage: Mark rows (valid, error, skipped)
    Worker-->>Admin: Job complete. errors.csv available for download
```

## 2. Invariants & Formats
1. **Encoding & Format Support:**
   - UTF-8 and UTF-8 with BOM (`\xef\xbb\xbf`).
   - Delimiters: Comma (`,`), Semicolon (`;`), Tab (`\t`).
   - Handles multi-line text enclosed in RFC-4180 quotes.
2. **Conflict & Null Policy:**
   - `create_only`: If conflict key exists, row marked as `skipped` (with warning) or `error`.
   - `update_only`: If conflict key not found, row marked as `error`.
   - `upsert`: If conflict key exists, update record; otherwise create new. Empty cells do not overwrite existing non-null data unless explicitly specified.
3. **Partial Failure & Isolation:**
   - Valid rows in committed batches are preserved.
   - Failed rows are logged with line number, column name, error code, and error message into `errors.csv`.
4. **Export Safety:**
   - Export queries respect caller RBAC permissions. Users without `exports.pii` will have email, phone numbers, exact coordinates, and sensitive custom fields redacted.
   - Spreadsheet Formula Injection prevention: prepends a tab (`\t`) or quote if cell string starts with `=`, `+`, `-`, or `@`.

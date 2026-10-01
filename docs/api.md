# Boconic — REST API Contract (`/api/v1`)

**Version:** 2.0  
**Date:** 01/10/2026

## 1. Authentication Schemes & Security Domains

1. **Public Discovery (`/api/v1/catalog/*`, `/api/v1/health/*`):**
   - Unauthenticated or client rate-limited.
   - Responses use sanitized DTOs with PII stripped and coordinates blurred.

2. **Internal Bot Gateway (`/api/v1/internal/*`):**
   - Header `X-Bot-Api-Key`: Must match server `BOT_API_KEY`.
   - Header `X-Telegram-User-Id`: Numeric Telegram ID of the actor, extracted strictly from verified Telegram update.
   - Header `X-Idempotency-Key` (Optional): Prevents duplicate execution on network retries.

3. **Admin Web & API (`/api/v1/admin/*` and `/admin/*`):**
   - Cookie `boconic_session`: HttpOnly, SameSite=Lax.
   - Header `X-CSRF-Token` for state-mutating requests (POST, PUT, DELETE).
   - Enforces RBAC permissions per endpoint.

## 2. Standard Error Response Schema

All errors follow a unified contract:
```json
{
  "error": {
    "code": "COPY_UNAVAILABLE",
    "message": "Bản sách này vừa được giữ chỗ hoặc đang trong giao dịch.",
    "details": {
      "copy_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "current_status": "reserved"
    },
    "request_id": "req-c8d76e4f-2a3b"
  }
}
```

Standard Status Codes:
- `400 Bad Request`: Malformed payload or validation rule failure.
- `401 Unauthorized`: Missing or invalid credentials / session.
- `403 Forbidden`: Actor lacks required RBAC permission or scope.
- `404 Not Found`: Entity does not exist or hidden by privacy policy.
- `409 Conflict`: Concurrency conflict, duplicate request, or invalid state machine transition.
- `422 Unprocessable Entity`: Schema/field validation error.
- `429 Too Many Requests`: Rate limit exceeded with `Retry-After` header.
- `503 Service Unavailable`: Dependent service (e.g. database, worker) degraded.

## 3. Key Endpoint Groups

### Health & Readiness
- `GET /health/live` — Returns 200 if FastAPI process is alive.
- `GET /health/ready` — Verifies database connection and worker responsiveness.
- `GET /api/health` — Alias for readiness.

### Internal Bot Gateway Endpoints (`/api/v1/internal/telegram/*`)
- `POST /api/v1/internal/telegram/users/sync` — Register or update user from verified Telegram update.
- `GET /api/v1/internal/telegram/books/search` — Search books by keyword, ISBN, grade, subject.
- `POST /api/v1/internal/telegram/copies` — Add a new physical copy for a user.
- `POST /api/v1/internal/telegram/borrow-requests` — Submit a borrow request.
- `POST /api/v1/internal/telegram/borrow-requests/{id}/accept` — Accept request & create reserved loan.
- `POST /api/v1/internal/telegram/borrow-requests/{id}/reject` — Reject request.
- `POST /api/v1/internal/telegram/loans/{id}/confirm-handover` — Register physical handover confirmation.
- `POST /api/v1/internal/telegram/loans/{id}/request-return` — Initiate return process.
- `POST /api/v1/internal/telegram/loans/{id}/confirm-return` — Register physical return confirmation.
- `GET /api/v1/internal/telegram/my-books` — List user's registered copies.
- `GET /api/v1/internal/telegram/my-loans` — List active/reserved loans for borrower.
- `GET /api/v1/internal/telegram/my-lendings` — List copies currently lent out.

### Admin Management Endpoints (`/api/v1/admin/*`)
- `GET /api/v1/admin/dashboard` — Live operational statistics.
- `GET /api/v1/admin/books`, `POST /api/v1/admin/books` — Book catalog management.
- `GET /api/v1/admin/copies` — Physical copies management.
- `GET /api/v1/admin/loans` — Lending oversight and dispute resolution.
- `GET /api/v1/admin/custom-fields`, `POST /api/v1/admin/custom-fields` — Dynamic field definitions.
- `POST /api/v1/admin/imports/preview` — CSV staging preview.
- `POST /api/v1/admin/imports/execute` — Launch background import job.
- `GET /api/v1/admin/exports` — Generate filtered CSV/JSON export.
- `GET /api/v1/admin/audit-logs` — Query append-only audit trail.
- `POST /api/v1/admin/backups` — Trigger snapshot backup.

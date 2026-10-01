# Boconic — System Architecture & Trust Boundaries

**Version:** 2.0  
**Date:** 01/10/2026

## 1. System Overview

Boconic is designed as a **modular monolith** with clean separation between delivery layers (FastAPI REST API, Jinja2/HTMX Admin Console, aiogram Telegram Gateway) and core application domain services.

```mermaid
flowchart TD
    subgraph ClientLayer["Clients & Interfaces"]
        T["Telegram User"] -->|Interacts with| BG["Boconic Bot Gateway (aiogram 3.x)"]
        A["Admin User"] -->|Browser HTTPS/HTTP| AC["Admin Web Console (/admin)"]
        P["Public Clients"] -->|REST /api/v1| PA["Public Discovery API"]
    end

    subgraph AppLayer["FastAPI Application Process"]
        AC --> SM["Session & CSRF Middleware"]
        SM --> AS["Admin Services & Views"]
        
        BG -->|Internal REST + BOT_API_KEY + Delegated Actor| IA["Internal Bot API (/internal/telegram/*)"]
        
        PA --> CS["Catalog Discovery Service"]
        IA --> CS
        IA --> LS["Lending State Machine Service"]
        IA --> US["User Profile & Location Service"]
        
        AS --> CS
        AS --> LS
        AS --> CF["Custom Fields Service"]
        AS --> IE["CSV Import/Export Service"]
        AS --> MS["Moderation & Trust Service"]
        AS --> BS["Backup & Restore Service"]
    end

    subgraph DataLayer["Persistence & Storage"]
        CS & LS & US & AS & CF & IE & MS & BS --> ORM["SQLAlchemy 2.0 (Asyncpg)"]
        ORM --> DB[("PostgreSQL 16 Database")]
        BS & AS --> FS[("Private File Storage (/data/storage)")]
    end

    subgraph WorkerLayer["Background Worker Process"]
        W["Boconic Worker"] -->|Poll durable queue| DB
        W -->|Dispatch Outbox Events| NT["Telegram Notification Service"]
        W -->|Execute Async Imports/Exports| IE
        W -->|Scheduled Reminders| LS
    end
```

## 2. Trust Boundaries & Security Domains

1. **Telegram Gateway Trust Boundary:**
   - The bot gateway runs as an authorized internal client.
   - It authenticates to `/api/v1/internal/*` using a high-entropy `BOT_API_KEY`.
   - The actor identity is passed via header `X-Telegram-User-Id`, which the bot extracts strictly from verified aiogram `Update` objects.
   - The backend validates the `BOT_API_KEY`, resolves the user from the database, and enforces authorization.
   - Public API requests are strictly forbidden from supplying or spoofing `X-Telegram-User-Id`.

2. **Admin Web Console Trust Boundary:**
   - Admin authentication is based on server-side stored sessions referenced by an `HttpOnly`, `SameSite=Lax`, secure cookie (`boconic_session`).
   - Mutations (POST/PUT/DELETE) require valid CSRF tokens verified against the active session.
   - Granular RBAC permissions (`users.read`, `books.write`, `loans.resolve_dispute`, `backups.restore`, etc.) are checked at both router and service levels.
   - Scoped permissions prevent multi-tenant violations (e.g., a Library Manager can only manage resources of their assigned organization).

3. **Privacy & Public Discovery Boundary:**
   - Public DTOs intentionally strip all PII: phone numbers, emails, precise GPS coordinates, internal database IDs, and numeric Telegram IDs.
   - User identity in public catalog views is replaced with randomized obfuscated aliases (e.g., `User #A81F`).
   - Distances are rounded into discrete intervals (e.g., "Khoảng 1–3 km") to prevent trilateration attacks.

4. **Resource Rights & Digital Assets:**
   - Three distinct permission tiers for resources:
     - Tier 1: Metadata display only.
     - Tier 2: External link referral (link verified).
     - Tier 3: Direct file storage & distribution (requires verified open license or explicit copyright permission).
   - Resources have statuses: `pending`, `verified`, `rejected`, `needs_review`. Only verified actions are permitted.

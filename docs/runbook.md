# Boconic — Operational Runbook & Disaster Recovery

**Version:** 2.0  
**Date:** 01/10/2026

## 1. Startup, Services & Graceful Shutdown

### Service Topology
- `boconic-api`: FastAPI backend web server serving REST API and Admin Console (`http://localhost:8000/admin`).
- `boconic-bot`: aiogram 3.x long polling gateway communicating with Telegram Bot API.
- `boconic-worker`: Asynchronous task worker processing background jobs, reminders, and outbox event dispatch.
- `postgres`: PostgreSQL 16 database with persistent storage.

### Commands
```bash
# Setup database, migrations, and super-admin
python scripts/setup.py

# Run API + Admin Console
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Run Telegram Bot Gateway
python -m app.bot.main

# Run Durable Worker
python -m app.jobs.worker
```

### Graceful Shutdown
All services register SIGINT / SIGTERM handlers.
- `boconic-api`: Finishes in-flight HTTP requests before closing connection pools.
- `boconic-bot`: Stops polling, waits for active handler completion, closes bot session.
- `boconic-worker`: Releases task lease locks if interrupted mid-task, ensuring tasks can be re-claimed upon restart.

---

## 2. Backup & Restore Procedures

### Creating a Snapshot Backup
```bash
python scripts/backup.py create
```
This produces a structured archive in `/data/backups/boconic_backup_<timestamp>.tar.gz` containing:
1. `database.sql` (PostgreSQL dump or consistent SQLite snapshot).
2. `media_manifest.json` (SHA-256 hashes of all stored book covers and evidence files).
3. `media/` directory with physical files.
4. `backup_manifest.json` with schema version, app version, timestamp, and row counts.

### Performing a Restore Rehearsal
```bash
python scripts/restore.py --archive /data/backups/boconic_backup_<timestamp>.tar.gz --target-db boconic_rehearsal
```
The script:
1. Verifies SHA-256 integrity of the archive.
2. Creates a pre-restore safety snapshot of the target database.
3. Sets maintenance mode and suspends worker jobs.
4. Restores database schema and rows.
5. Verifies core invariant counts (users, books, copies, active loans).
6. Revokes existing admin sessions to prevent stale session hijacking.
7. Reports verification status.

---

## 3. Incident Management & Recovery

### Offline Catch-Up
- When the host machine sleeps or disconnects from the internet, Telegram holds incoming updates for up to 24 hours.
- Upon reconnection, `boconic-bot` consumes updates sequentially.
- Critical transaction idempotency prevents duplicate state transitions even if Telegram redelivers updates.
- Stale loan reminders (>24h overdue during downtime) are consolidated rather than spammed all at once.

### Admin Session Revocation & Key Rotation
- To revoke an admin session immediately: Delete the session from `admin_sessions` or call `POST /api/v1/admin/auth/revoke-all`.
- To rotate `BOT_API_KEY`: Update `BOT_API_KEY` in `.env` and restart both `boconic-api` and `boconic-bot`.

# Boconic — Product & Technical Roadmap

**Version:** 2.0  
**Date:** 01/10/2026

## Overview

Boconic prioritizes functional correctness, data invariants, dual-party handshake safety, and operational simplicity before extending into advanced AI or distributed architectures.

---

## Phase Breakdown

### P0 — Production MVP (Current Phase)
* **Goal:** A fully working, operable community textbook lending platform running on a single Ubuntu / local machine with minimal cost.
* **Scope:**
  - Complete Telegram Bot onboarding, catalog discovery, copy listing, and borrow requests.
  - Dual-handshake physical lending state machine (`reserved`, `active`, `return_pending`, `returned`, `disputed`).
  - Embedded Admin Web Console (`/admin`) with real database dashboard, CRUD forms, and relations.
  - Dynamic Custom Fields with 16 supported types and dynamic form rendering.
  - Resumable CSV Import Wizard with staging, preview, conflict resolution, and `errors.csv`.
  - Filtered CSV/JSON export with PII redaction and formula injection protection.
  - Digital resource catalog with 3-tier permissions and verification status.
  - PostgreSQL durable task queue, outbox events, and background worker.
  - Database and media backup manifest generator and restore rehearsal procedure.
  - Append-only audit logging and comprehensive automated test suite.

### P1 — Community Network & Logistics Enhancement
* **Scope:**
  - Geodetic distance search with explicit consent ("khoảng 1–3 km").
  - Transparent queue and waitlist for in-demand school textbooks.
  - Random alphanumeric QR code generator (`public_code`) for physical copy identification.
  - Chain lending protocol: Borrower A transfers custody to Borrower B with owner's explicit cryptographic consent.
  - School shortage pledge and fulfillment tracking.
  - Post-loan community ratings with Bayesian smoothing.

### P2 — AI Assistance with Strict Fallbacks
* **Scope:**
  - Book cover & ISBN OCR pipeline with confidence scoring and manual confirmation.
  - Vietnamese query understanding extracting subject, grade, curriculum, and coarse location.
  - Semantic vector search on catalog metadata using pgvector with hybrid retrieval and reranking.
  - Quantitative AI evaluation benchmarks (`docs/ai-evaluation.md`).

### P3 — Ecosystem & Enterprise Scale
* **Scope:**
  - Telegram Mini App (TMA) web experience.
  - Direct ILS / Z39.50 university library integrations.
  - Aggregated shortage analytics with privacy differential thresholds.
  - Dedicated multi-node deployment with PostgreSQL replication and S3 storage.

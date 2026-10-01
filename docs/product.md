# Boconic — Product Context, Personas & Rules

**Version:** 2.0  
**Date:** 01/10/2026

## 1. Brand Identity & Purpose
- **Name:** Boconic
- **Tagline:** Find what you need. Find who can help.
- **Mission:** Democratize textbook and educational book access through community circulation, physical lending, verified libraries, and compliant open digital resources.

## 2. Core Personas & User Journeys
1. **Học sinh / Sinh viên (Students):**
   - Need specific textbook editions matching their curriculum (e.g. "Toán 12 - Chân trời sáng tạo").
   - Limited financial budget; only need a book for a semester or a specific exam period.
2. **Phụ huynh (Parents):**
   - Seek full textbook sets for primary/secondary children; prioritize safe handovers at school gates or libraries.
3. **Chủ sách / Người yêu sách (Book Donors/Lenders):**
   - Have textbooks sitting unused; want to help younger students while retaining ownership and tracking who has their book.
4. **Thư viện trường / Cộng đồng (Libraries & Schools):**
   - Maintain physical inventory, publish shortage lists, and facilitate collective book donations.

## 3. Digital Resource Rules & Copyright Compliance
In strict adherence to ethical and copyright principles:
1. **Physical First:** Prioritize physical book lending. A request for a chapter should first be fulfilled by borrowing the physical book edition containing that chapter.
2. **No Unauthorized Slicing:** Boconic will **never** build features that crowdsource, slice, or assemble unauthorized digital book fragments into a whole work.
3. **No Arbitrary "10% Fair Use" Automation:** The system does not automate legal claims or assume copying 10% is inherently lawful.
4. **Three Distinct Permission Tiers for Resources:**
   - **Tier 1 (Metadata Display):** Display citation, title, author, table of contents.
   - **Tier 2 (External Referral Link):** Display link to official open repositories or publisher pages.
   - **Tier 3 (File Hosting/Distribution):** Store and distribute files via bot only when explicit open licenses (Creative Commons, Public Domain) or authorized publisher agreements are verified.
5. **Verification Pipeline:**
   - Resources must have: `source_name`, `source_url`, `license_name`, `license_url`, `rights_basis`, `evidence`, `verification_status` (`pending`, `verified`, `rejected`, `needs_review`), `verified_by`, `verified_at`.
   - Any takedown request immediately hides Tier 2/Tier 3 distribution pending audit.

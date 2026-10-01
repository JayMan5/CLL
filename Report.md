# COURTLOG — Codebase Analysis & Status Report

**Project:** COURTLOG — Intelligent Court Case Tracking & Compliance Platform
**Target:** COUCH 2026 Competition
**Report basis:** Full read-only codebase audit (entire project excluding `venv/`)
**Status tagline:** Fully implemented (v2 backend/frontend); final verification & competition deliverables outstanding.

---

## 1. Project Overview

COURTLOG is a Nigerian judicial case-tracking platform built to enforce the Administration of Criminal Justice Act (ACJA) timelines and surface delay risk before it happens. It addresses four chronic court-system pain points — lost case files, excessive adjournments, un-enforced judgments, and invisible case backlogs — through four integrated modules. The system is designed to complement (not replace) Nigeria's existing e-filing infrastructure, with the Chief Registrar as the governing authority.

## 2. The Four Core Modules

| Module | Function | Enforcement Rule |
|--------|----------|------------------|
| **QR Chain of Custody** | Physical file tracking via scan events; bailiff/sheriff handoffs logged | 7-day no-scan alert (file presumed missing) |
| **Hearing Compliance** | Adjournment ledger with judicial logging | 5th adjournment **blocked** (ACJA §396); DCR override possible |
| **Delay-Risk ML** | Predicts stall probability at filing | Logistic Regression, alert threshold **0.70** |
| **Execution Tracker** | Post-judgment enforcement (Writ of Fi Fa, Garnishee) | 90-day enforcement window → non-compliance flag |

## 3. Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, **FastAPI**, Uvicorn |
| Auth | **RS256 JWT** (30-min access, 7-day refresh), bcrypt password hashing |
| Database | **SQLite** (`data/courtlog.db`) with JSON-blob columns for nested records |
| ML | scikit-learn **LogisticRegression**, joblib persistence, label encoders |
| Frontend | Vanilla JS SPA (`app.js` + `index.html` + Tailwind CDN), no framework |
| Integration | WhatsApp Business API **webhook simulator** (adjournment broadcast) |
| Serving | FastAPI serves `/` → `index.html`, `/static` → frontend assets; CORS open |

## 4. Architecture Notes (verified)

- `backend/main.py` (~1090 lines, ~25 endpoints) — routes, business rules, compliance sweeps.
- `backend/auth.py` — RS256 signing from `private_key.pem`/`public_key.pem` (present, gitignored).
- `backend/database.py` — SQLite helpers, `parse_date`/`format_date`, `SEED_USERS`.
- `db.update_case` **appends** to list fields (`scan_events`, `hearing_log`, `execution_log`, `documents`) and overwrites scalars.
- Path params use `{case_id:path}` converter (IDs contain slashes, e.g. `SC/CV/123/2021`).
- Compliance sweep runs on startup **and on every `GET /api/cases`** (see Issue 6).
- WhatsApp broadcast → background task → POSTs to its own `webhook-simulator` → in-memory `whatsapp_logs` (max 30).
- ML heuristic fallback (model absent): `score = min(0.99, 0.10 + adj*0.12 + days*0.0005)`, `+0.15` if Land Dispute; `risk_flag = score > 0.70`.
- Judgment recording: `POST /hearings` with `outcome="Heard"` + `reason_code ∈ ["Judgment Delivered","Ruling Delivered"]` → `judgment_status="Delivered"`.
- Execution completed statuses: `"Garnishee Order Executed"`, `"Writ of Fi Fa Completed"`, `"Enforcement Completed"` → `judgment_status="Executed"`.
- QR codes via `api.qrserver.com`; Writ of Fi Fa template = FORM 27, Sheriffs & Civil Process Act Cap. S6 LFN 2004, Order VII Rule 1.
- Writ & Garnishee documents both print through a single shared `printWrit()` (`app.js:1313`, `index.html:1189`) using `window.open()` with inline CSS, `@page` rules, auto-print script and a popup-blocker fallback.

## 5. Data & Users

- **`data/courtlog.db`** — live SQLite DB.
- **Seed:** `backend/seed_db.py` injects **66 real cases** from `real_scn_cases_sample.csv`, distributions enriched by `scn_appeal_cases_data.csv` (4,696 SCN appeal cases).
- **ML dataset:** `data/courtlog_delay_dataset.csv` — 3,000 records (2828 High / 124 Moderate / 48 Low → see Issue 4).
- **ML artifacts:** `data/delay_model.joblib`, `data/label_encoders.joblib` (gitignored).
- **Accounts:** `sheriff`/`clerk`/`dcr`/`judge` (password `123`), `cr` (password `12345`).

## 6. What Is Done

- ✅ Full FastAPI backend (~25 endpoints), JWT auth complete.
- ✅ Complete frontend SPA (8 tabs, 5 modals, login overlay).
- ✅ All four compliance/ML modules implemented.
- ✅ Real-case seeding pipeline (66 cases + 4,696-case distribution source).
- ✅ WhatsApp adjournment broadcast simulation.
- ✅ Export endpoints (`/api/export/njc`, `/api/export/dcr-weekly`).
- ✅ **All 12 bugs in `task.md` marked fixed.**
- ✅ **Blank print/save for Writ & Garnishee documents — FIXED** (see Issue/FIX-1 below).

## 7. What Is Left

1. **Re-seed the database** with the corrected seed logic.
2. **Start the server & run smoke tests** (login, scan, hearing, dcr-override, predict, execution, export, whatsapp logs).
3. **End-to-end rule validation:** 7-day custody alert · 5th-adjournment block + DCR override · 90-day enforcement flag · ML 0.70 threshold.
4. **Competition deliverables:**
   - Abstract — drafted, needs revision per DCR feedback (frame as *complementing* e-filing; **WhatsApp not SMS**; **Chief Registrar** pathway).
   - Pitch deck — **exists** (`docs/COURTLOG_Pitch_Deck.pptx`).
   - Business Model Canvas — **not started.**
   - Pitch video — **not started.**
   - ⏳ Deadline ~13 days — **reconfirm**.

## 8. Issues Found & Remediation Plan

### 🔧 FIX-1 — Blank print/save for Writ & Garnishee — ✅ FIXED
Confirmation (`app.js:1313`, `index.html:1189`): `printWrit()` now builds a clean HTML document, injects inline print CSS with `@page` margins and `page-break` rules, auto-triggers `window.print()` on load, and alerts if the popup is blocked. The orphaned `@media print` stylesheet (old cause) is superseded — verified no `<link>` references it.
**Residual action:** delete orphaned `frontend/print-fix.css`.

### 🔴 Issue 1 — `test_api.py` broken / pseudo-auth — **High**
Legacy `X-User-Role`/`X-User-Id` headers; references removed `usr_dev_01`/old mock case IDs. Backend enforces JWT → all RBAC tests 401.
**Fix:** Rewrite to `POST /api/login` per role → `Authorization: Bearer` → real seeded case IDs; drop test_09.

### 🔴 Issue 2 — Empty Clerk & Sheriff role views — **High (demo-critical)**
Clerk hardcoded to `"FHC Abuja Court 4"` (seeded courts differ); Sheriff keyed on scanner `staff_id` (`ST-002…`) that never equals `usr_sheriff_01`. Both see zero cases.
**Fix:** Align seed `assigned_division`/scanner IDs to seeded users, or broaden scoping.

### 🔴 Issue 3 — Case-type dropdown ≠ ML encoder classes — **High**
Unseen classes collapse to encoder index 0 → wrong predictions.
**Fix:** Match dropdown values to `label_encoders.joblib` classes exactly.

### 🟠 Issue 4 — ML training data imbalance — **Medium**
94% "High" class → model predicts High nearly always.
**Fix:** Rebalance `build_dataset.py`; retrain; re-verify 0.70 threshold.

### 🟠 Issue 5 — No client-side refresh-token flow — **Medium**
Refresh token stored, never used → sessions die at 30 min.
**Fix:** 401-interceptor → `POST /api/refresh` → retry → else re-login.

### 🟠 Issue 6 — Compliance sweep on every `GET /api/cases` — **Medium**
Redundant O(n) recompute on each list call.
**Fix:** Startup + scheduled job only; read cached flags.

### 🟡 Issue 7 — `usr_dev_01` leftover — **Low**
Dead branch, `app.js:219`.
**Fix:** `select.value = user.user_id;`

### 🟡 Issue 8 — Orphaned files & unused deps — **Low**
`frontend/print-fix.css`, `legal/Writ_of_Fi_Fa_Nigeria_Template(updated).md`, legacy `data/cases.json`/`users.json`, root `seed_app_database.py`, `extract.py`, `test_render*.js`, `update_*.js`; unused `xhtml2pdf`, `python-multipart`.
**Fix:** Delete; trim `requirements.txt`.

### 🟡 Issue 9 — Documentation inaccuracies — **Low**
`docs/generate_docx.py` says "Random Forest" (actual: Logistic Regression); older docs still mention Firebase.
**Fix:** Sync docs to implementation.

### 🟡 Issue 10 — No VCS & stray lock files — **Low**
Not a git repo; `~$*.docx` Word lock files in `docs/`.
**Fix:** `git init`, ignore lock files, branch-per-fix.

---

## 9. One-Line Verdict

> COURTLOG is **feature-complete and functional**; remaining work is concentrated in **verification, demo-blocking data/scoping fixes (Issues 1–3), and competition deliverables** — not new feature development.

*Generated from full codebase audit — COURTLOG project, `venv/` excluded.*
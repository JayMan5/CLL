# COURTLOG — Full Project Audit

| | |
|---|---|
| **Repo** | `JayMan5/CLL` · branch `arena/01a0f82f-cll` · commit `723a583` ("Initial commit", 54 tracked files) |
| **Audit date** | 2026-10-01 |
| **Scope** | Backend, frontend, ML pipeline, data, tests, dependencies, repo hygiene, every `.md` / `.docx` / `.pptx` in the repo, and the legal/platform premises the product depends on |
| **Method** | Read every source file, then **ran the code** in a scratch copy outside the repo (Python 3.11 venv, exact pinned `requirements.txt`): trained the model, started the API, hit it with scripted requests, drove the real `index.html` + `app.js` in jsdom against the live API, ran the repo's own tests, `pip-audit`, `bandit`, `pyflakes`, `node --check`. **The repository was not modified — this file is the only addition.** |
| **Evidence tags** | **[R]** reproduced by running code · **[S]** static code reading · **[D]** from a document or web source |
| **Effort sizes** | S ≈ under ½ day · M ≈ 1–3 days · L ≈ a week or more (rough, one developer) |

**Contents:** 1 Executive summary · 2 What is DONE · 3 What is YET TO BE DONE · 4 Detailed findings · 5 Claims vs reality · 6 Legal and platform premises · 7 State of the repo's own self-assessment docs · 8 What checked out fine / what I could not verify · Appendices A–C

---

## 1. Executive summary

**Verdict.** COURTLOG is a broad, genuinely working **prototype**. All four modules exist end to end, a clean install from the pinned requirements boots first time, JWT login and role checks work on most write routes, and the demo is seeded with real case titles. But three things stand between it and a credible COUCH demo, let alone a pilot:

1. **It is not safe to expose to anyone outside the team.** Six endpoints need no login — including the user list with password hashes, case PII, and a webhook that feeds unescaped HTML into every user's WhatsApp tab. Combined with `innerHTML` rendering, that chains into **token theft and Chief-Registrar takeover [R]**. The login page ships pre-filled with the Chief Registrar's credentials.
2. **The headline AI feature does not hold up.** The training label is produced by a hand-written rule *on the same features* (0 mismatches in 3,000 rows), 94% of rows are "High", the score is essentially case *age*, and on the demo data the model flags **65 of 65** cases High — so the AI tab, the chart and the NJC "compliance score" show no discrimination at all.
3. **Several things the docs, deck and UI say are true are not.** "Trained on 3,000+ real Nigerian court records" (it is synthetic — the team's own data study says so), "98% accuracy on authentic trends", "immutable audit logs with the officer's User ID", "Random Forest", "integrates with existing registry WhatsApp groups". See §5.

Two demo-blocking usability bugs also surfaced: **the Sheriff cannot scan or report anything in the UI** (their case dropdowns are empty — F-01), and a **Clerk who creates a case with the form's default values never sees it** (F-02).

Most of the serious items are quick fixes. I estimate the P0 list in §3 at roughly **8–10 developer-days in total, parallelisable**.

### Scorecard

| Area | Status | Demo-ready? | Main blocker |
|---|---|---|---|
| Module 1 — QR chain of custody | Partial | Not yet | Scanning is a simulated form; Sheriff UI deadlock; missing-file alert wiped by next sweep |
| Module 2 — Hearing compliance | Partial | Mostly | Statute modelled differently from ACJA s.396; WhatsApp is simulation-only and port-bound |
| Module 3 — AI delay-risk | Built, **not credible** | No | Circular labels; 65/65 flagged High; "Why?" is hard-coded text |
| Module 4 — Execution tracker | Partial | Partly | UI cannot record completion; 2 of 4 writ types render the wrong document |
| Auth / RBAC / security | Needs work | **No** | Open endpoints, XSS chain, spoofable audit IDs, public admin login |
| Seed data | Partial | No | 64/65 cases already decided; random state; role scoping yields empty views |
| Tests / CI / packaging | Missing | — | 0 of 9 tests pass; no README, `.env.example`, Dockerfile or CI |
| Docs / non-code deliverables | Partial | — | Business Model Canvas and pitch video absent; claims inconsistent |

### Fix these first (impact ÷ effort)

| # | Fix | Size | Ref |
|---|---|---|---|
| 1 | Add auth to the 6 open endpoints (and auth header on the cron button) | S | S-01 |
| 2 | Stop rendering server data via `innerHTML` / inline `onclick`; add a CSP | S–M | S-02 |
| 3 | Remove the pre-filled `cr` / `12345` login; env-driven seed passwords; explicit demo mode | S | S-03 |
| 4 | Rebuild the demo data: pending cases, realistic adjournments, courts and staff IDs that match the demo users | M | D-01, F-01, F-02 |
| 5 | Make the AI module defensible (honest labelling, sane features/data, real per-case explanations) | M | M-01…M-07 |
| 6 | Close the execution loop and fix the writ templates | M | L-04, L-05 |
| 7 | Take the actor identity from the JWT, not the request body | S | S-05 |
| 8 | Handle token expiry (401 → refresh → login) | S | S-06 |
| 9 | Reconcile every claim in UI / deck / docs with reality | S–M | §5 |
| 10 | Make tests runnable + CI + README + `.env.example`; delete junk files | M | E-01, E-02, E-05 |

---

## 2. What has been DONE

Everything below was exercised unless marked otherwise. "Works" means the feature behaves as coded; where I question the *design*, the finding ID is given.

### Module 1 — QR chain of custody
| Capability | Status |
|---|---|
| `POST /api/scan` appends location, timestamp, staff_id; custody-history panel in UI | **Works [R]** — but `staff_id` is client-supplied (S-05) |
| 7-day idle `custody_alert` computed in the compliance sweep | **Works [R]** on seed data (1 alert). Boundary conditions (day 6/7/8) untested |
| Sheriff "Report file missing" endpoint + form | **Works [R]**, but the alert is erased by the next sweep (L-07) |
| QR image per case | **Works online only [R]** — rendered by third-party `api.qrserver.com` (S-13) |

### Module 2 — Hearing compliance
| Capability | Status |
|---|---|
| Hearing log (Adjourned / Heard), adjournment counter | **Works [R]** |
| Role limits: Judge may only deliver rulings; Sheriff and DCR get 403 | **Works [R]** |
| Block at count ≥ 4 + DCR override endpoint + DCR queue UI | **Works as coded [R]**; semantics questioned in L-01 |
| WhatsApp broadcast (Meta-template-shaped payload) + log tab | **Works only on port 8000 [R]**; simulator only (L-06) |
| Clerk call-over screen with live message preview; Judge docket + "Deliver Ruling" | **Works [R]/[S]** |
| 24-hour auto-escalation | Sets a flag and writes a log line only (L-02) |

### Module 3 — Delay-risk model
| Capability | Status |
|---|---|
| Synthetic dataset generator (3,000 rows, `random.seed(42)`) | **Works [R]** |
| Logistic-regression training script (≈1.4 s, ROC-AUC 0.98 on a synthetic hold-out); artefacts saved | **Works [R]** — metric is not meaningful (M-01, M-02) |
| Inference on create / scan / hearing / sweep; `risk_flag` when score > 0.70; deterministic fallback | **Works [R]** |
| Batch re-score endpoint + "AI Risk Intelligence" tab (summary cards, distribution bar, ranked table, "Why?") | **Works mechanically [R]**; output is uninformative (M-06) |

### Module 4 — Execution tracker
| Capability | Status |
|---|---|
| `POST …/execution` (Sheriff/CR) logs action, date, sheriff_id | **Works [R]** |
| 90-day `enforcement_non_compliant` flag | **Works [R]** on seed (51 flagged). Boundaries untested |
| Execution tab: delivered-judgments list, writ compiler, browser print | **Works [R]** for 2 of 4 writ types (L-05) |
| "Executed" transition | **API only [R]** — the UI never sends a completion action (L-04) |

### Platform
| Capability | Status |
|---|---|
| FastAPI app: 25 `/api` routes + static SPA | **[R]** boots first time |
| RS256 JWT login, bcrypt (cost 12), refresh endpoint | **[R]** |
| 5-role RBAC on the mutating routes — except `predict`, `cron` and the webhook simulator (open) and the batch endpoint (no role check) | **[R]** 403s verified |
| Role-scoped case list: Sheriff = scanned-by-me, Clerk = my court, DCR = my division, Judge = assigned | **Works [R]** — yet yields empty views on the demo data (F-01, F-02) |
| SQLite store with a write lock | **[R]** |
| Case reassign, assign-judge, document-metadata endpoints; NJC + DCR-weekly JSON exports; judge-alerts endpoint | **[R]** (scoping issues S-04, L-08) |
| 65-case real-data seed (source CSV has 66 rows, one duplicate) | **[R]** (D-01) |
| SPA: 9 tabs, login overlay, dark/light theme, toasts, Chart.js; loads with **no JS errors** | **[R]** |
| `task.md`'s 12 listed bug fixes | **[S]** consistent with current code |

### Documents and deliverables that exist
Abstract; Team Brief; System Overview; "Overview & Production Guide"; Security Framework (a *plan*); Gap Analysis; RBAC Mismatches; Nigerian Court Data Availability study; Data Integration Update; Writ of Fi Fa and Garnishee templates (`.md` + `.docx`); **10-slide Pitch Deck** (team slide still has `[Name]` placeholders). Several are stale or overclaim — see §5 and §7.

---

## 3. What is YET TO BE DONE

### P0 — before any demo, and before the repo is shared or deployed anywhere

1. **[S] Authenticate the open endpoints.** Add `Depends(get_current_user)` plus a role check to `GET /api/users`, `GET /api/cases/{id}`, `POST …/predict`, `POST /api/cron`, `GET /api/whatsapp/logs`; protect or remove the webhook simulator; never return the `password` field; send the auth header from the cron button. *(S-01)*
2. **[S–M] Fix the XSS.** Escape or build DOM nodes for all server data; replace inline `onclick="fn('${id}')"` with `data-` attributes and event delegation; validate `case_id` against a pattern server-side; add a Content-Security-Policy. *(S-02)*
3. **[S] Remove the public admin login.** No pre-filled `cr` / `12345`; seed passwords from environment; stop printing them in docs; add a `DEMO_MODE` switch for anything demo-only (role switcher, simulator). *(S-03, F-04)*
4. **[M] Rebuild the demo dataset.** Mostly *pending* cases (not 64/65 decided), 0–5 adjournments, a handful near the limit, courts and staff IDs matching the demo users so every role sees data, deterministic seeding, and stop tracking the live DB in git. *(D-01, F-01, F-02, S-12)*
5. **[M] Make the AI module defensible.** Label it "prototype trained on synthetic data" everywhere; use features that mean something (age ÷ expected duration for the case type, adjournment pace, days since last hearing); one-hot the case type; generate data covering the live 0–5 adjournment range; **label from simulated outcomes, not a rule on the same inputs**; score only pending cases; report PR-AUC and calibration, not accuracy; compute "Why?" from the model's own contributions; show model-vs-fallback. *(M-01…M-07)*
6. **[M] Close the execution loop and fix writs.** Add a "record return / mark executed" action; fix the Possession and Delivery templates; capture judgment sum, creditor, debtor, garnishee; don't log an enforcement event merely for previewing; **Law Lead review** of every template. *(L-04, L-05)*
7. **[S] Server-side identity for the audit trail.** Take scan/execution/hearing actor from the JWT; store `logged_by`, `override_by`, `override_at`. *(S-05)*
8. **[S] Token expiry.** On 401 try refresh, else show the login screen. *(S-06)*
9. **[S–M] Reconcile claims** across UI, deck and docs; state plainly that the model is trained on synthetic data. *(§5)*
10. **[M] Tests and packaging.** Add `httpx`, rewrite `test_api.py` for JWT and current IDs, add CI, write a README and `.env.example`, delete the junk files. *(E-01, E-02, E-05)*

### P1 — before a pilot with real registry staff

- **Authorisation:** object-level checks (court / division / judge) on every write and export; DCR scoped on reassign and exports; validate roles and divisions. *(S-04, S-09)*
- **Validation:** Pydantic `Literal` / regex / ISO dates / E.164 phones / `case_id` format; fix the path traversal; length limits. *(S-08, L-01)*
- **Sessions:** logout and revocation (`jti` + denylist); deleting or disabling a user revokes tokens; block self-delete and last-CR delete; password change/reset and forced first-login change; rate limit and lockout; refresh token in an HttpOnly cookie; 15-minute access token. *(S-06)*
- **User admin:** a real form (username, initial password, role dropdown, court, division); a `/api/me` endpoint so the UI isn't driven by a hard-coded profile map; remove the role switcher outside demo mode. *(S-09, F-04)*
- **Hardening:** CORS allow-list, security headers, disable `/docs` in production, HTTPS reverse proxy, self-host JS/CSS/fonts (no CDN) with SRI, generate QR codes locally. *(S-07, S-13)*
- **Adjournment engine that matches the statute** — needs a Law Lead decision first (per-party counts, interval limits, criminal-only, who approves, who/when recorded). *(L-01)*
- **Judgment lifecycle:** a state machine; separate ruling from judgment; stop the clock at judgment; resolve flow for missing files; real escalation notifications; CR acknowledgement tracking. *(L-02, L-03, L-07, L-09)*
- **Notifications:** pick a real design — 1:1 template messages to counsel and litigants (with consent), or API-created groups of ≤ 8; configurable base URL; persist delivery status; surface failures; fix env-var names. *(L-06)*
- **Real QR workflow:** camera / USB-scanner input, signed QR payloads, offline tolerance. *(F-03)*
- **Documents:** real upload with type/size validation, storage and download — or remove the feature. *(F-06)*
- **Exports:** month filter, role scoping, PII minimisation, CSV/PDF, and make "stalled" mean stalled. *(L-08)*
- **Data layer:** decide Postgres vs Firestore; migrations; backups; a Pydantic case model to stop schema drift; remove the Firestore claim or build it. *(L-11, E-06)*
- **Dependencies:** bump PyJWT, cryptography, requests, python-dotenv; drop `passlib`, `xhtml2pdf`, `python-multipart`; run `pip-audit` in CI. *(S-10, E-03)*
- **Unit tests for the rule boundaries** (7-day, 24-hour, 90-day, adjournment limit).

### P2 — before wider or government rollout

NDPA 2023 compliance (DPO, DPIA, NDPC registration, retention, breach plan — already outlined in your Security Framework §4) · NITDA clearance · MFA (TOTP) · role-based data masking · backups and DR drills · WAF · accessibility, mobile and i18n · load testing · third-party penetration test · **validate the model on real data** (Citizens' Gavel's 1,388-case dataset; a registry partnership) · model monitoring and governance · independent legal review of every generated instrument.

### Non-code deliverables for COUCH 2026
- **Business Model Canvas** — not started.
- **Pitch video** — not started.
- **Deck:** fill the `[Name]` team placeholders; remove claims the model contradicts (M-08); add measured impact; replace the "~12% per adjournment" and "admiralty higher" statements.
- **Abstract revision** — the brief says it "needs rewrite"; the current text already mentions WhatsApp and the registrar review, so confirm whether this is done.
- **Confirm the submission deadline** — the brief leaves it to the team lead; the "13 days" countdown in `Report.md` is stale.
- **Evidence for "proposal submitted" and the DCR review** (the deck says submitted; the brief says "drafted, sending now"), and permission to name Barrister Antonia Oyibo publicly.
- **Contact Citizens' Gavel** — marked "ACTION REQUIRED" in your data study, with no sign it happened.
- **Rehearse the demo on stable infrastructure**; the page needs internet for Tailwind, Chart.js, Font Awesome and Google Fonts.

---

## 4. Detailed findings

Severity: **Critical** = exploitable by an unauthenticated or low-privilege actor to read/alter sensitive data or take over admin, or invalidates a headline claim · **High** = breaks a core promise or the integrity of the audit trail · **Medium** = functional gap or missing hardening · **Low** = polish / hygiene.

### 4.1 Security

**S-01 · Critical · [R] · Six endpoints need no login**
- `GET /api/users` returns all users **including bcrypt hashes**; `bcrypt.checkpw('12345', hash)` is `True` for the `cr` account.
- `GET /api/cases/{id}` returns party phone numbers. `POST /api/cases/{id}/predict` rewrites a case's score and flag. `POST /api/cron` triggers the sweep. `GET /api/whatsapp/logs` is public. `POST /api/whatsapp/webhook-simulator` accepted an `<img onerror>` payload and `GET /api/whatsapp/logs` served it back to every user.
- Fix: auth + role check on all six; the simulator only in demo mode behind a shared secret; never serialise `password`. Note the SPA's cron button sends no auth header and will need one.

**S-02 · Critical · [R, jsdom] · Stored XSS → token theft → admin takeover**
- Server data is interpolated unescaped into `innerHTML` in `renderHeatmapTable`, `renderWhatsAppLogs`, `renderDCRTable`, `renderJudgeDocketTable`, `renderUsersAdminTable`, `renderAIRiskDashboard`, `updateQRDisplay` and `showWritModal`; IDs are also placed inside inline `onclick="fn('${id}')"` attributes.
- Entry points: the unauthenticated webhook (S-01), and fields low-privilege users control (`case_id`, scan `location`, `staff_id`).
- Reproduced by loading the real `index.html` + `app.js`: an injected `<img onerror>` element is present in the DOM; a crafted `case_id` breaks out of the `onclick` attribute and the handler read `localStorage` (**token exfiltrated**). Tokens, including the 7-day refresh token, live in `localStorage`.
- Fix: escape helper or DOM builders, event delegation, server-side `case_id` pattern, CSP, and move the refresh token to an HttpOnly cookie.

**S-03 · High · [R] · Public admin credentials**
- The login form is **pre-filled with `cr` / `12345`** (Chief Registrar). Seed passwords are `123` / `12345` and appear in `Report.md` and `project_analysis.md`.
- Fix: no prefill; env-driven seeds; `DEMO_MODE` flag.

**S-04 · High · [R] · No object-level authorisation**
- A Clerk of "FHC Abuja Court 4" logged a hearing and attached a document on a **Supreme Court** case (HTTP 200).
- DCR (division Criminal) reassigned a case to an arbitrary division and court — the endpoint's own docstring says "within their division".
- `GET /api/predict/batch` returns all cases to **any** authenticated role (a Sheriff and a Clerk, whose own scope is 0 cases, received all 65) and writes scores for all of them.
- Fix: one `authorize(case, user)` helper applied to every case-touching route; DCR scoping on reassign/exports; role check on batch.

**S-05 · High · [R + S] · The audit trail is spoofable and incomplete**
- Scan `staff_id` and execution `sheriff_id` come from the request body (a Sheriff scanned as `usr_cr_01`; stored as sent).
- `hearing_log` entries contain only `date`, `next_date`, `outcome`, `reason_code` — **no actor**. The DCR override stores only the reason text — no approver, no timestamp.
- Records are mutable JSON blobs in a SQLite row, not an append-only log.
- This contradicts the System Overview ("every scan, hearing and DCR override is permanently logged with … the specific User ID") and Security Framework §2.6.
- Fix: actor from the JWT; add `logged_by` / `override_by` / `override_at`; write to an append-only audit table.

**S-06 · High · [R] · Session and credential lifecycle**
- Deleting a user does not invalidate their tokens: after the CR deleted their own account, the token still worked and `/api/refresh` still issued new access tokens; login then failed (**self-lockout, no CR left**).
- No logout/revocation, no password change or reset, no rate limiting: 40 wrong passwords in 9.8 s, all HTTP 401, no 429, correct password still accepted.
- The SPA never calls `/api/refresh`; with an expired token the overlay stays hidden, the dashboard stays empty and **no sign-in prompt appears**.
- Plan vs code: access token 30 min (plan 15), refresh token in `localStorage` (plan HttpOnly cookie), no `jti`/denylist.

**S-07 · Medium · [R] · CORS, headers, public API docs**
- A preflight from `https://evil.example` was answered with that origin reflected plus `allow-credentials: true`. With S-01, any web page opened on a court-staff browser can read `/api/users` and case PII from an intranet deployment.
- 0 of 6 planned security headers are present. `/docs`, `/redoc`, `/openapi.json` are public.

**S-08 · Medium · [R] · Path traversal creates directories**
- A Clerk can create a case with `case_id` `../../../../tmp/X`, then POST to `…/documents` with percent-encoded dots; a directory was created **outside** `data/` (`/tmp/CLL_TRAVERSAL_PROOF`). Directory creation only — no file content — but arbitrary location.

**S-09 · Medium · [R] · User management cannot produce usable accounts**
- `POST /api/users` stores no username or password, so the new user **cannot log in**. The role is unvalidated (`"Banana Overlord"` accepted). IDs are `usr_<role>_<unix-seconds>`: two creations in the same second got the **same ID** (overwrite). The UI collects input via five `prompt()` dialogs.

**S-10 · Medium · [R] · Vulnerable pinned dependencies**
- `pip-audit` on the direct pins reports **33 advisories**: PyJWT 2.9.0 (15), cryptography 43.0.0 (7), python-multipart 0.0.12 (7, **unused**), requests 2.32.3 (2), python-dotenv 1.0.1 (1), xhtml2pdf 0.2.16 (1, **unused**).
- Transitive dependencies (e.g. Starlette) were not scanned; applicability of each advisory was not individually triaged.

**S-11 · Medium · [R] · PII exposure contradicts your own classification**
- The Security Framework classes party phone numbers as CONFIDENTIAL (Judge + CR only, masked for others). In practice every authenticated role receives `party_contact` (verified for Clerk and DCR), the NJC export embeds it, and S-01 serves it unauthenticated.

**S-12 · Low–Medium · [R] · Live DB and credentials tracked in git**
- `data/courtlog.db` is committed and holds the demo users' bcrypt hashes. **Merely starting the server rewrites it** (sha256 changed with no HTTP requests), so a fresh clone is dirty after first run. Legacy `data/users.json` holds a `dev` Chief-Registrar hash (unused). `*.pem` and `*.joblib` are correctly ignored; no private keys are tracked.

**S-13 · Low · [S] · Third-party runtime dependencies**
- Tailwind Play CDN, un-versioned Chart.js, Font Awesome, Google Fonts — no SRI, and the app breaks offline. `api.qrserver.com` receives every case number shown as a QR.

### 4.2 Business logic and compliance rules

**L-01 · High · [D + R] · ACJA s.396 is modelled differently from the statute** (see §6.1)
- Statute: no party is entitled to **more than five adjournments** from arraignment to judgment, intervals ≤ 14 working days; after the parties exhaust their five, intervals ≤ 7 days including weekends (it does not cap further adjournments); costs may be awarded. The duty is addressed to the court.
- App: one case-level counter; blocks logging of the 5th (count ≥ 4); requires a **DCR** (not in the statute); **one override unlocks unlimited adjournments** (7 of 7 further requests passed); applies to civil cases too; **never checks the intervals** (`next_date` is unvalidated — `"not-a-date"` was accepted and broadcast); an *empty* override reason is accepted but doesn't unblock; the seed marks blocked at ≥ 5 while the code blocks at ≥ 4.
- Fix: Law Lead to confirm intent; per-party counters; interval validation; criminal-only; record approver, time and reason for each exceptional adjournment; consider presenting it as an alert/escalation rather than a hard stop.

**L-02 · High · [R + S] · `risk_flag` is overloaded; escalation is resettable and inert**
- It is set by the ML score, by the adjournment block, and by missing-file reports. Any later inference overwrites it: an **unauthenticated** `POST /predict` cleared the block's red flag while `dcr_approval_required` stayed `True`.
- The sweep resets `red_flag_notified_at` / `auto_escalated`, so the 24-hour CR escalation clock can be restarted. "Escalation" only sets a flag and logs a line — nobody is notified, the UI has no escalation view, and there is no acknowledgement endpoint (the RBAC doc's "CR 48 h response tracking" is not implemented).
- Fix: separate fields (`ml_risk_flag`, `adjournment_blocked`, `file_missing`); one-way escalation timestamps; a notification and an acknowledgement action.

**L-03 · High · [R] · No judgment state machine**
- A Sheriff marked a **Pending** case "Executed". A Judge then re-delivered judgment on that Executed case → status flipped back to Delivered, with duplicate delivery events. "Ruling Delivered" (an interlocutory ruling) sets Delivered and starts the 90-day clock. Hearing `outcome` is free text (`"Banana"` stored). The "Judgment Delivered" reason is dropped from the hearing log (`reason_code: "None"`).

**L-04 · High · [R/S] · The execution loop cannot be closed from the UI**
- No completion action ("…Completed", "Garnishee Order Executed", "Enforcement Completed") appears anywhere in the frontend, so no case can reach **Executed** through the UI. Every "Compile & Lodge Writ" click appends an enforcement event — including a re-print or preview. Logging completion clears `enforcement_non_compliant`, so breaches disappear from NJC counts.

**L-05 · High · [R] · Writ generator defects** (needs Law Lead review; see §6.3)
- "Writ of Possession" and "Writ of Delivery" render the **Garnishee** document under their own title (verified for all four types).
- The Fi Fa header is hard-coded "**High Court of the Federal Capital Territory**"; the project targets the Federal High Court, and the seeded cases are SC/CA/FHC (appellate judgments are enforced through the court of first instance).
- No judgment sum, creditor, debtor or garnishee in the data model — the template says "the sum awarded". Parties are inferred from title order, which is wrong for appeals ("X v The State"). Defaults pre-fill "First Bank of Nigeria PLC" and "SH-045" for every writ type.

**L-06 · High · [R + D] · WhatsApp**
- Messages go only to the hard-coded group `registry-group-104`. Counsel and litigant phones are collected but **never used**.
- The loop-back URL is fixed at `localhost:8000`: on port 8001 the API returned **200** while the log showed "Failed to connect…", and the UI still says "payload sent".
- Delivery status is not persisted. No overdue-writ message exists (the Overview doc says sheriffs get one). The Overview doc's env vars (`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`) don't match the code (`WHATSAPP_API_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`).
- **Feasibility:** Meta's Groups API covers only API-created, invite-link groups of at most 8 people (§6.2), so "integrates with existing registry WhatsApp groups" is not achievable as designed.

**L-07 · Medium · [R] · Missing-file report doesn't stick**
- `custody_alert` is set, then erased by the next sweep (recomputed from scan timestamps); `file_missing_report.resolved` can never change — no resolve/found endpoint exists.

**L-08 · Medium · [R] · Exports**
- JSON only. The DCR's NJC export contained **every division** and **party phone numbers**. "Stalled" equals the `risk_flag` count, so on the demo data it printed `speedy_trial_compliance_score: 1.4%` (68 of 69 flagged in my run; ≈ 0% on the committed 65). The DCR weekly score was 3.7%. The jurisdiction label is hard-coded "Federal High Court / High Court Division" though the data is SC/CA/FHC, and the "Monthly" report isn't month-filtered.

**L-09 · Medium · [R/S] · The delay timer never stops**
- `days_since_filing` keeps growing after judgment (e.g. 6,639 days on a case decided in 2017) while the UI promises "Case timer successfully closed". The Judge docket shows "Deliver Ruling" on already-delivered cases.

**L-10 · Low · [R] · Sweep-on-read**
- `GET /api/cases` runs a full sweep that rewrites every case (one sweep per request in the log). Cost is currently small and linear: 12 ms at 74 cases, 41 ms at 574. A design smell (reads mutate state; escalations happen as read side-effects), not a present performance problem.

**L-11 · Low · [R] · Schema drift and weak create validation**
- API-created cases lack 13 fields that seeded cases have (`case_title`, `documents`, `file_missing_report`, `auto_escalated`, `red_flag_notified_at`, `judgment_date`, …) — I hit a `KeyError` in my own test. `create_case` hard-codes the judge `usr_judge_01` and accepts any `case_id` and any phone string (`"not-a-phone"`).

### 4.3 AI / ML

**M-01 · Critical (for the award claim) · [R] · The labels are circular**
- Re-applying `build_dataset.classify_delay_risk` to each row's own features reproduces the "High" label for **3000 / 3000** rows (0 mismatches). The model re-learns a hand-written rule; there is no ground truth ("did this case actually stall?"), no temporal split, no external validation. ROC-AUC 0.98 is therefore not evidence of predictive power.

**M-02 · High · [R] · Heavy class imbalance**
- 94.3% High (2,828 / 124 / 48). "Always predict High" scores ≈ 94% accuracy; the model's 96% is a marginal gain, and recall on the non-High class is 0.57.

**M-03 · High · [R] · Training data is unlike the live app**
- Mean 14 adjournments (median 14); **85%** of rows have ≥ 5 (the limit the app blocks at); 1.4% have zero. Live cases sit at 0–5, so the model is extrapolating.

**M-04 · High · [R] · The score mostly measures case age**
- With the encoding the live app uses, a Criminal case with **zero** adjournments crosses 0.70 at ~**day 315**; with four at ~day 219; with five at ~day 196. At day 365 with zero adjournments P = 0.85; beyond ~day 730 it is 1.0 regardless of anything else. A case **at the statutory limit** (5 adjournments) on day 90 scores only 0.26. Every case becomes "High" simply by getting older.

**M-05 · High · [R] · Categoricals are alphabetical ordinals, and the vocabulary doesn't match the app**
- `case_type` and `court` are label-encoded integers fed to a linear model, so ordering is meaningless: Admiralty = 0 (lowest contribution), Land/Property = 7 (highest).
- UI "Case Type": **4 of 6** options (Land Dispute, Civil Debt, Family, Intellectual Property) aren't in the encoder. UI "Courtroom": **0 of 5** are. Seeded courts: 0 of 3. Code defaults ("Civil Debt", "FHC Abuja Court 2") aren't either. Unseen values silently become code 0 — so court has no effect on live data and case type is arbitrary.

**M-06 · High · [R] · On the demo data the model cannot discriminate**
- All 65 seeded cases score ≥ 0.92 (median 1.000) → **65 / 65 High**; AI tab shows High 65 · Medium 0 · Low 0; the overview chart is flat. Also, 64 of 65 cases are *already decided*, so "delay risk" is conceptually moot for them.

**M-07 · Medium · [R] · "Why?" is not an explanation of the model**
- `showExplainability` uses fixed JS thresholds and a case-type list that doesn't match real types (`['Land Dispute','Constitutional Rights','Admiralty']`), says "10 adjournments — approaching statutory limit" for a case already past it, and ends with "Logistic Regression trained on 3,000+ Nigerian court records". The AI-tab header repeats "3,000+ Nigerian Court Records".

**M-08 · Medium · [R] · Deck claims the model contradicts**
- "Land disputes **and admiralty** show higher delay risk": Admiralty is the *lowest*-risk type in the model. With zero adjournments it crosses the 0.70 line later (day 335) than Criminal (day 315) or Land/Property (day 301). "Each adjournment increases stalling probability by ~12%": the coefficient is odds × 1.54 per adjournment, and the probability effect ranges from +0.7 to +10.7 points depending on age. "Court assignment correlates with delay": no effect on live data (M-05).

**M-09 · Medium · [S/R] · Operational gaps**
- `*.joblib` is gitignored, so a fresh clone silently uses the heuristic fallback (and the UI doesn't say which produced the score); training is undocumented; no stored metrics or model card; no versioning or calibration.

**M-10 · Low · [D] · Algorithm named inconsistently**
- Code and deck: Logistic Regression. `CourtLOG_Overview.docx`, `docs/generate_docx.py` and `Report.md`: Random Forest.

### 4.4 Frontend / UX

**F-01 · High · [R] · The Sheriff cannot do anything in the UI**
- The Sheriff's case list is "cases whose scan `staff_id` equals my user ID" (`usr_sheriff_01`). On the committed data it is empty, so the **scan and report-missing dropdowns have 0 options** — you can only scan cases you can already see. A scan made through the form's default `ST-809` returns 200 yet the Sheriff still sees 0; only typing `usr_sheriff_01` makes a case appear.

**F-02 · High · [R] · A Clerk who uses the form defaults never sees their own case**
- The create-case form defaults to court "Lagos High Court 2" and type "Civil Debt"; the Clerk is scoped to "FHC Abuja Court 4". The UI said "cataloged and initialized successfully!" yet the case never appeared in that Clerk's list (it exists for the CR). Clerks can create cases in any court (S-04).

**F-03 · High · [R/S] · The "QR scanner" is a simulation**
- The panel is literally titled "Simulated Scanner Input": a dropdown and a typed staff ID (default `ST-809`). No camera or barcode capture exists; the QR encodes the bare case ID (forgeable) and comes from a third party. Module 1's core claim — scan at every checkpoint — isn't achievable with real devices yet.

**F-04 · Medium · [R] · Role switcher is client-only; profiles are hard-coded**
- Logged in as a Clerk, switching to "Chief Registrar" reveals the CR UI, but the JWT is still the Clerk's (`/api/export/njc` → 403). The five profiles are hard-coded in `USER_PROFILES`, so any admin-created user would render as the Clerk.

**F-05 · Medium · [R/S] · Misleading or silent error handling**
- *Any* failed hearing POST (403, 404, 500) is shown as "5TH ADJOURNMENT HARD BLOCKED … auto-escalated to the DCR queue". Execution check-in and scan network failures only log to the console. 401 is unhandled (S-06). Core flows use `alert()` / `prompt()`.

**F-06 · Medium · [R] · "Upload Document" uploads nothing**
- The form has a text box for a filename, not a file input; the endpoint stores metadata and creates empty directories. There is no way to view a document afterwards.

**F-07 · Low · [S] · Stale hard-coded UI values**
- "100% QR cataloged", "Division: Criminal & Civil", placeholder IDs `CR-104-2025` / `CR/104/2025`, preview date `2026-07-28`, default clock text "July 18, 2026". The overview chart is titled "Delay Risk Probability Distributions" but plots averages by case type, with a fixed list of 8 types.

**F-08 · Low · [S] · Unused code**
- `fetchJudgeAlerts()` is defined but never called, so `/api/judge/alerts` (the judge's 24-hour alert) never reaches the UI; `/api/refresh`, `/api/cases/{id}/alerts`, `GET /api/cases/{id}` and `POST …/predict` are unused by the SPA; `print-fix.css` is linked nowhere.

**F-09 · Info · Not assessed**
- Responsive layout, keyboard/screen-reader accessibility and cross-browser rendering — no real browser was available (the Chromium download was blocked).

### 4.5 Data and seed

**D-01 · High · [R] · The seed is real in name only**
- 66 CSV rows but **65 unique** cases (`SC.532/2015` is duplicated) — docs say 66. Real: titles, citations, years. **Simulated:** adjournment counts (0–16), scans, flags, phone numbers, scores. 64 of 65 are already Delivered; 48 of 66 are pre-ACJA and 46 of 66 were decided in 2016–17; all are assigned to one judge; 35 are "blocked" so the CR's DCR hub lists 41 entries for concluded matters; 51 of 64 delivered cases are "enforcement non-compliant"; 21 are auto-escalated. Seeding uses unseeded randomness, so it isn't reproducible.

**D-02 · Medium · [R] · Mis-named duplicate datasets**
- Root `courtlog_delay_dataset.csv` is **byte-identical to `data/real_scn_cases_sample.csv`** — not the training set (that is `data/courtlog_delay_dataset.csv`, 3,000 rows). Root `courtlog_delay_dataset.txt` is a tab-separated, mojibake copy.

**D-03 · Low · [S] · Legacy data**
- `data/cases.json` (5 cases) and `data/users.json` are unused by the current code.

### 4.6 Engineering hygiene

**E-01 · High · [R] · The test suite is dead**
- `backend/test_api.py` has 9 tests; **0 pass**. As shipped it fails at import (`httpx` is not in `requirements.txt`); with `httpx` installed it gives 7 failures + 2 errors (obsolete `X-User-Role` headers, old case IDs, a `dev` user that isn't in the DB). No CI.

**E-02 · Medium · [S] · Missing project scaffolding**
- No README, `.env.example`, Dockerfile, CI, run script or `backend/__init__.py`; I ran everything from the repo root with `PYTHONPATH` set.

**E-03 · Medium · [R] · Dependency hygiene**
- Unused `passlib`, `xhtml2pdf` (with a heavy transitive tree) and `python-multipart`; `httpx` missing for tests; no lockfile or hashes. (The pinned set does install cleanly on Python 3.11 in about 20 s.)

**E-04 · Low · [R] · Code structure and lint**
- `backend/main.py` is 1,124 lines mixing routes, business rules, the sweep and ML. `pyflakes`: unused `timedelta`, `Header`, `numpy`, redundant `global` statements. `bandit` (medium+): nothing — **scanners cannot see the missing-auth and logic problems above.**

**E-05 · Low · [R] · Repo junk**
- `test_render2.js` (syntax error), `test_render.js`, `update_modals.js`, `update_tabs.js`, `extract.py`, `seed_app_database.py`, empty `reports.md`, `docs/~$*.docx` Word lock files, duplicate datasets (D-02), orphan `print-fix.css`.

**E-06 · Low · [S] · Firestore is a stub**
- The deck and System Overview describe Firestore with "zero code changes"; the code has a stub and SQLite.

---

## 5. Claims vs reality

| # | Claim | Where | Reality | Ref |
|---|---|---|---|---|
| 1 | "Trained on thousands of **real** Nigerian court cases" / "3,000+ Nigerian Court Records" | System Overview; AI-tab header; "Why?" popup | 3,000 **synthetic** rows; your own data study: "NO publicly downloadable dataset exists… prototyping only" | M-01 |
| 2 | "98% accuracy … authentic Nigerian court trends" | Data Integration Update | AUC 0.98 on synthetic data where label = rule(features); trivial baseline ≈ 94% | M-01, M-02 |
| 3 | "Dashboard now running on **real** data" | Data Integration Update | Real titles/citations/years; workflow state simulated; 64/65 already decided | D-01 |
| 4 | "Immutable audit logs … specific User ID" | System Overview | No actor on hearings; scan/exec IDs client-supplied; override has no author | S-05 |
| 5 | "Sheriffs receive WhatsApp the moment a writ becomes overdue" | Overview & Production Guide | Not implemented; only adjournments trigger a message | L-06 |
| 6 | "Integrates with existing registry WhatsApp groups" | Deck slides 4–5; Gap Analysis | Meta's group API can't join existing groups; code posts to a simulator | L-06, §6.2 |
| 7 | "Random Forest classifier" | Overview docx; `generate_docx.py`; `Report.md` | Logistic Regression | M-10 |
| 8 | "Flags cases adjourned more than 3 times" | Overview docx | Code blocks after 4 | L-01 |
| 9 | `WHATSAPP_TOKEN` / `WHATSAPP_PHONE_ID` → "real messages" | Overview docx | Code reads `WHATSAPP_API_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID`; no real send path configured | L-06 |
| 10 | Firestore in production, "zero code changes" | Deck slide 5; System Overview | Stub only | E-06 |
| 11 | "Each adjournment +~12%"; "admiralty higher risk" | Deck slide 6 | Odds ×1.54; effect +0.7…+10.7 pts; Admiralty is lowest | M-08 |
| 12 | "Case timer successfully closed" on judgment | UI | `days_since_filing` keeps growing | L-09 |
| 13 | "All dynamic content rendered using textContent (never innerHTML)" | Security Framework §3.6 | Pervasive `innerHTML`; exploitable | S-02 |
| 14 | Phase 1 "must be completed before any external demonstration" | Security Framework | 1 of 6 items done (bcrypt hashing) | App. B |
| 15 | "Writ templates use correct Nigerian terminology — Done" | Gap Analysis | 2 of 4 types wrong; FCT heading; no amounts | L-05 |
| 16 | "Module 3 … still to be built"; "Pitch deck: not started" | Team Brief | Both exist | — |
| 17 | "Concept reviewed by DCR…; proposal **submitted**" | Deck slide 8 | Brief says "drafted, sending now"; unverifiable from the repo | §3 non-code |
| 18 | "No authentication", ".gitignore missing", "clock frozen 2026-07-18", "MockDatabase reseeds" | Gap Analysis (July) | All fixed since — the doc is stale | §7 |
| 19 | RBAC doc's 12 "mismatches" | RBAC Mismatches | Mostly implemented; remaining: judge alert not in UI, CR response tracking absent, DCR scoping unenforced on writes | S-04, F-08 |
| 20 | "Product ≈ 85% complete" | Data Integration Update | Subjective; see scorecard | §1 |

---

## 6. Legal and platform premises to verify

*I am not a lawyer; these are points for the Law Lead to confirm against primary sources.*

### 6.1 ACJA 2015, section 396
Commentary quoting the text ([Wole Olanipekun & Co](https://www.woleolanipekun.com/section-396-of-administration-of-criminal-justice-act-2015/); [SAS Law Review overview](https://journals.sas.ac.uk/lawreview/article/download/5204/5055/)): s.396(3) day-to-day trial from arraignment; **s.396(4)** "no party shall be entitled to more than five adjournments from arraignment to final judgment" with intervals ≤ 14 working days; **s.396(5)** once the parties have exhausted their five each, intervals ≤ 7 days including weekends; s.396(6) costs against frivolous adjournments. The SAS review notes the additional-adjournment provision "does not peg the number". Press reporting describes the rule as routinely breached ([The Nation, Mar 2026](https://thenationonlineng.net/fast-tracking-corruption-trials/)).

Implications for the product: it is a **criminal** statute; the entitlement is **per party**; the *interval* limits are arguably the more checkable obligation (and are not checked); the duty rests on the **court**, so a "DCR approval" step is a product design choice the Registrar/Law Lead should validate; and the count semantics (block at the 5th vs the 6th) need confirming. See L-01.

### 6.2 WhatsApp Business Platform groups
Meta's [Groups API documentation](https://developers.facebook.com/documentation/business-messaging/whatsapp/groups) (updated 16 Jun 2026): groups are **created through the API** and are **invite-link-only**; **max 8 participants**; Official Business Account required; not available on WhatsApp Business app numbers; interactive messages and some other types unsupported. The docs describe no way to enrol the API number into an *existing* group. Third-party write-ups say the same ([Unipile, Aug 2026](https://www.unipile.com/whatsapp-group-api/)). Practical options: 1:1 template messages to counsel and litigants (with a lawful basis / consent under the NDPA), or small API-created groups per court.

### 6.3 Writs and garnishee
Sources describing the process ([Mondaq](https://www.mondaq.com/nigeria/trials-amp-appeals-amp-compensation/894722/a-focus-on-writ-of-fieri-facias-and-garnishee-proceedings); [AWJAI](https://awjai.org/2025/02/04/enforcement-of-judgement-in-nigeria/)): garnishee proceedings fall under the Sheriffs and Civil Process Act ss.83–92 and start with an application, then an order nisi served through the sheriff, then an order absolute; a process for enforcement is issued by the court that gave the judgment. The app's "Garnishee Proceeding Document" blends an application and an order and says it is "executed by the Sheriff on behalf of the Judgment Creditor". I could not verify the "Form 27 / Order VII Rule 1" label, and your template is for a *State* High Court while the app targets the Federal High Court. Law Lead sign-off needed (L-05).

### 6.4 Data protection
Your own Security Framework §4 correctly identifies NDPA 2023 duties (DPO, DPIA, 72-hour breach notice, retention). Notifying litigants and counsel by WhatsApp requires a lawful basis; nothing in the code records consent. I did not research this further.

---

## 7. State of the repo's own self-assessment docs

| File | Status |
|---|---|
| `project_audit.md` | **Stale.** Says there is no batch endpoint and no AI risk dashboard; both now exist (its #1 recommendation is built). |
| `project_analysis.md` | Stale. Describes a smaller frontend (~1,474-line `app.js`, ~1,074-line `index.html`; now 1,718 / 1,368), "8 tabs" (now 9), and prints the seed credentials. |
| `Report.md` | Stale. Says "Not a git repo" (it is) and carries a "13 days" countdown. Correctly notes that `generate_docx.py` says "Random Forest". |
| `task.md` | 12 fixes ticked; verification items (re-seed, browser check) still unticked. |
| `walkthrough.md` | Stale (Firebase, Windows paths). |
| `implementation-process.md`, `reports.md` | Stub / empty (0 bytes). |
| `docs/COURTLOG_Gap_Analysis.docx` | July snapshot; superseded. |
| `docs/CourtLOG_RBAC_Mismatches.docx` | Mostly fixed in code. |
| `docs/CourtLOG_Security_Framework.docx` | A plan — see Appendix B for plan vs code. |
| Team Brief | "Module 3 still to be built", "deck not started", stale countdown. |

**Recommendation:** replace the stack of conflicting self-assessments with one living `STATUS.md` (or fold this audit into it) and delete the rest.

---

## 8. What checked out fine — and what I could not verify

**Checked out fine**
- Pinned `requirements.txt` installs cleanly on Python 3.11 in ~20 s; the server boots first time; `app.js` loads with no JS errors; `node --check frontend/app.js` passes **[R]**.
- All five logins work; role 403s behave as designed (Judge cannot adjourn; Sheriff and DCR cannot log hearings) **[R]**.
- The adjournment block fires at count ≥ 4 and a DCR override lifts it **[R]**.
- **A race that bypasses the block was not reproducible:** 3 trials × 12 concurrent requests at count = 3 each allowed exactly one, ending at 4. Writes are serialised by a lock; the endpoint's check-then-act isn't transactional, so treat it as latent, not confirmed **[R]**.
- bcrypt (cost 12) for passwords; RS256 keys auto-generated and gitignored; no private keys tracked **[R/S]**.
- The model trains in ~1.4 s and a deterministic fallback exists **[R]**.

**Not verified**
- Real-browser rendering, responsiveness and accessibility (no browser available).
- Firestore, the real Meta API, and email/other channels (not implemented or not reachable).
- Legal correctness of any template or of the ACJA modelling (needs the Law Lead).
- Institutional claims (DCR review, proposal status).
- Behaviour beyond ~600 cases; transitive-dependency CVEs; a full penetration test.
- Visual quality of the `.docx` files and deck.

---

## Appendix A — Endpoint auth matrix (generated from `backend/main.py`)

| Method | Path | Auth | Roles allowed (code) | Called by SPA |
|---|---|---|---|---|
| POST | `/api/login` | no (expected) | — | yes |
| POST | `/api/refresh` | no (expected) | — | **no** |
| GET | `/api/users` | **NO** | — | yes |
| POST | `/api/users` | yes | Chief Registrar | yes |
| DELETE | `/api/users/{user_id}` | yes | Chief Registrar | yes |
| GET | `/api/cases` | yes | any authenticated (role-scoped list) | yes |
| POST | `/api/cases` | yes | Chief Registrar, Clerk | yes |
| POST | `/api/scan` | yes | Chief Registrar, Clerk, Sheriff | yes |
| POST | `/api/cases/{id}/hearings` | yes | Chief Registrar, Clerk, Judge (rulings only) | yes |
| POST | `/api/cases/{id}/dcr-override` | yes | Chief Registrar, DCR | yes |
| POST | `/api/cases/{id}/report-missing` | yes | Chief Registrar, Sheriff | yes |
| POST | `/api/cases/{id}/assign-judge` | yes | Chief Registrar | yes |
| POST | `/api/cases/{id}/reassign` | yes | Chief Registrar, DCR (not scoped) | yes |
| POST | `/api/cases/{id}/documents` | yes | Chief Registrar, Clerk | yes |
| POST | `/api/cases/{id}/execution` | yes | Chief Registrar, Sheriff | yes |
| GET | `/api/cases/{id}/alerts` | yes | any authenticated | no |
| GET | `/api/cases/{id}` | **NO** | — | no |
| POST | `/api/cases/{id}/predict` | **NO** | — | no |
| GET | `/api/predict/batch` | yes | **any authenticated, unscoped, writes** | yes |
| GET | `/api/judge/alerts` | yes | Chief Registrar, Judge | **defined, never called** |
| GET | `/api/export/njc` | yes | Chief Registrar, DCR (unscoped) | yes |
| GET | `/api/export/dcr-weekly` | yes | Chief Registrar, DCR | yes |
| POST | `/api/cron` | **NO** | — | yes (no auth header) |
| POST | `/api/whatsapp/webhook-simulator` | **NO** | — | no |
| GET | `/api/whatsapp/logs` | **NO** | — | yes |

## Appendix B — Security Framework plan vs code

| Planned control | Status |
|---|---|
| 2.1 Password hashing | **Partial** — bcrypt yes; Argon2id no; weak seeds; hashes exposed (S-01) |
| 2.2 Input validation (Pydantic `Literal`, regex) | **No** (S-09, L-01) |
| 2.3 CORS tightening | **No** — reflects any origin with credentials (S-07) |
| 2.4 Secrets management | **Partial** — env for keys; no `.env.example`; seeds in code |
| 2.5 Security headers | **No** — 0 of 6 |
| 2.6 Audit logging (append-only) | **No** (S-05) |
| 3.1 JWT: 15-min access, HttpOnly refresh, RS256, denylist, `jti` | **Partial** — RS256 only |
| 3.2 Rate limiting | **No** (S-06) |
| 3.3 HTTPS / reverse proxy | Not applicable until deployment |
| 3.4 MFA (TOTP) | No |
| 3.5 Role-based data masking | **No** (S-11) |
| 3.6 XSS prevention | **No — contradicted** (S-02) |
| 3.7 Docker hardening | No Dockerfile exists |
| 3.8 Dependency scanning | **No CI**; my one-off run found 33 advisories (S-10) |
| 3.9 Backups / DR | No |
| 3.10 Intrusion detection | No |
| 4.x NDPA 2023, NITDA, retention, incident plan | Not started (organisational) |

## Appendix C — Reproducing the key checks

```bash
# Use a scratch copy: starting the server INSIDE the repo rewrites the tracked data/courtlog.db (S-12)
mkdir /tmp/audit && git -C /path/to/CLL archive HEAD | tar -x -C /tmp/audit && cd /tmp/audit
python3 -m venv /tmp/venv && /tmp/venv/bin/pip install -r requirements.txt
PYTHONPATH=. /tmp/venv/bin/python backend/train_model.py
PYTHONPATH=. /tmp/venv/bin/uvicorn backend.main:app --port 8000 &

curl -s localhost:8000/api/users | head -c 400                 # S-01: hashes without login
curl -s localhost:8000/api/cases/SC.594/2014 | head -c 400     # S-01: party phone numbers

# M-01: the label is a function of the features
PYTHONPATH=. /tmp/venv/bin/python - <<'EOF'
import pandas as pd; from build_dataset import classify_delay_risk
df = pd.read_csv('data/courtlog_delay_dataset.csv')
rule = df.apply(lambda r: classify_delay_risk(r.days_since_filing, r.adjournment_count, r.case_type), axis=1)
print('mismatches:', ((rule=='High') != (df.delay_risk=='High')).sum(), 'of', len(df))
EOF

/tmp/venv/bin/pip install pip-audit && /tmp/venv/bin/pip-audit -r requirements.txt --no-deps   # S-10
```

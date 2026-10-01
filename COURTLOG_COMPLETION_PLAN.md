# COURTLOG — Completion Plan and Approval Checklist

**Prepared:** 1 October 2026  
**Status:** Proposed — awaiting user approval. No development authorised or started.  
**Source:** `COURTLOG_FULL_AUDIT.md`  
**First pilot test:** 21 October 2026  
**Competition showcase:** 5 November 2026

## 1. Delivery targets

| Milestone | Target | Required outcome |
|---|---|---|
| Scope and legal decisions | 2 October | Approved backlog, pilot environment, data policy, legal workflow and notification channel |
| Security and data foundation | 7 October | Access controls, session lifecycle, consistent data model, useful deterministic fixtures |
| Core workflow feature-complete | 12 October | Filing → custody → hearings → judgment → enforcement works for all five roles |
| Pilot release candidate | 16 October | Features integrated, tests passing, staging deployment available |
| Pilot freeze and rehearsal | 19 October | Release approved, backup restored successfully, end-to-end rehearsal complete |
| Pilot preparation buffer | 20 October | Only blocker fixes; accounts, devices, forms and support ready |
| **Pilot** | **21 October** | Observe staff workflows, record defects and feedback |
| Pilot feedback resolved | 28 October | Critical/high findings fixed and regression-tested |
| Showcase release candidate | 30 October | Product and submission materials complete |
| Showcase freeze and rehearsal | 2 November | Final deployment and presentation rehearsed |
| Showcase preparation buffer | 3–4 November | Only blocker fixes; offline contingency ready |
| **Showcase** | **5 November** | Demonstrate the approved release |

These are planning targets, not a guarantee. Delivery depends on approved scope, team capacity, legal sign-off, infrastructure, and third-party access. Features below are due before the pilot unless explicitly marked otherwise. No insecure release should be used to meet a date.

### What “completed” means

- **Pilot-complete:** a secure, tested and deployable version of the four-module workflow, suitable for the explicitly approved pilot data and staff.
- **Showcase-complete:** pilot feedback addressed, reliable demonstrations, finished competition deliverables and accurate claims.
- **Government production rollout:** a separate approval gate. Real-data AI validation, regulatory obligations and independent security review cannot be assumed complete by these dates.

A pilot using real court records requires privacy, legal and institutional approval. If these are unavailable, use approved synthetic or anonymised fixtures and clearly identify the exercise as a workflow pilot.

## 2. Decisions and external prerequisites

**Owners:** DEV = development team/agent after approval; LAW = Law Lead; LEAD = project lead; OPS = deployment owner. One person may hold several roles.

- [ ] **DEC-01 — Approve scope and responsibilities (LEAD, 2 Oct).** Confirm this checklist, available team capacity, pilot participants and who accepts each release.
- [ ] **DEC-02 — Approve pilot data policy (LEAD/LAW, 2 Oct).** Synthetic/anonymised or real records; lawful basis, permitted fields, retention, access, consent where appropriate and institutional permission.
- [ ] **DEC-03 — Confirm hearing rules (LAW, 2 Oct).** Criminal-only applicability, per-party counts, interval calculation, court holidays, judicial discretion and the DCR’s administrative role. Confirm the 7-day and 90-day alerts are approved operational thresholds, not unsupported statutory claims.
- [ ] **DEC-04 — Approve legal documents (LAW, draft by 9 Oct; sign-off by 16 Oct).** Court jurisdiction, form numbers, Fi Fa, garnishee stages, possession/delivery and authority to issue/approve documents.
- [ ] **DEC-05 — Choose notifications (LEAD/OPS, 2 Oct).** Recommended: consented 1:1 WhatsApp template messages; confirm account, approved templates, recipients, costs and credential availability. Do not assume existing registry groups can be used.
- [ ] **DEC-06 — Select pilot hosting and database (DEV/OPS, 2 Oct).** SQLite is acceptable only for an approved small, single-instance pilot with backups; use PostgreSQL if deployment/concurrency requires it. Firestore is not required unless explicitly approved.
- [ ] **DEC-07 — Confirm submission requirements (LEAD, 2 Oct).** Verify competition submission deadlines, format, duration, judging criteria, required materials and permission to name institutional contacts.

## 3. Build and fix backlog

### A. Security and authentication — highest priority

- [ ] **SEC-01 — Protect every sensitive route (DEV, 7 Oct).** Authenticate case details, users, predictions, cron and notification logs; scope batch operations; disable or protect the simulator. Never return password hashes. Add required frontend auth handling.
- [ ] **SEC-02 — Prevent XSS and unsafe paths (DEV, 7 Oct).** Safe DOM rendering/event listeners, validated identifiers, safe storage paths and an appropriate Content Security Policy. Test hostile input at every entry point.
- [ ] **SEC-03 — Enforce object-level permissions (DEV, 7 Oct).** Central case-access policy for court, division, judge and assigned custodian; apply it to reads, writes, alerts, documents, predictions and exports. UI visibility is not authorisation.
- [ ] **SEC-04 — Complete sessions (DEV, 7 Oct).** Refresh flow, visible expiry handling, logout, refresh rotation/revocation and immediate enforcement of disabled/deleted users. Secure cookie handling and CSRF protection where required.
- [ ] **SEC-05 — Secure account lifecycle (DEV, 7 Oct).** Usable account creation, unique IDs, validated role assignments, password change/reset, forced initial password change, disable accounts and protect the last administrator/self-deletion.
- [ ] **SEC-06 — Remove demo credentials and role confusion (DEV, 7 Oct).** No pre-filled admin password; environment-driven setup; explicit demo mode; `/api/me`-driven identity; remove role switching from pilot/production sessions.
- [ ] **SEC-07 — Add hardening (DEV/OPS, 7 Oct).** Login/API rate limits, explicit CORS, HTTPS, security headers, secure key management and restricted API docs in deployed environments.
- [ ] **SEC-08 — Update dependencies (DEV, 7 Oct).** Triage direct and transitive advisories, upgrade safely, remove unused packages, include test dependencies and reproducible dependency versions. Automate scanning.

**Acceptance:** unauthenticated and cross-scope requests fail correctly; no hashes/tokens leak; hostile input cannot execute or escape storage; revoked sessions stop working; each role passes positive and negative permission tests.

### B. Data model and accountability

- [ ] **DATA-01 — Standardise the schema (DEV, 7 Oct).** Shared validated case/user/event models; canonical case types and court/division IDs; consistent create and seed paths; migrations and duplicate handling.
- [ ] **DATA-02 — Build a useful deterministic pilot fixture set (DEV, 7 Oct).** Pending, delivered and executed cases; varied risk, custody and enforcement scenarios; meaningful assignments for every role; separate real source metadata from simulated workflow fields.
- [ ] **DATA-03 — Stop committing runtime state (DEV, 7 Oct).** Keep live DBs/uploads out of Git; retain reproducible seed scripts; remove legacy credential fixtures and confusing duplicate datasets.
- [ ] **DATA-04 — Record trustworthy audit events (DEV, 7 Oct).** Actor from authenticated identity; timestamps, reason and before/after state for significant actions; append-only application audit store and restricted access. Do not claim tamper-proof storage without stronger controls.

**Acceptance:** clean setup creates a consistent database; every role has usable cases; identities cannot be spoofed; updates and exports are attributable; restarting preserves valid state.

### C. Module 1 — QR chain of custody

- [ ] **QR-01 — Fix the Sheriff assignment deadlock (DEV, 12 Oct).** Explicit custody assignment and authorised lookup/scan flow; do not require a previous scan to make the first scan possible.
- [ ] **QR-02 — Implement real scanning and labels (DEV, 12 Oct).** Camera support with permission/error handling, keyboard/USB scanner support, safe signed/validated QR payloads and locally generated printable labels; manual fallback.
- [ ] **QR-03 — Finish custody hand-offs (DEV, 12 Oct).** Current custodian/location, hand-off events and consistent scan history; actor derived from session.
- [ ] **QR-04 — Complete missing/found workflow (DEV, 12 Oct).** Missing report, persistent alert, authorised resolution and resolution history. Sweeps must not erase unresolved reports.
- [ ] **QR-05 — Validate the idle rule (DEV/LAW, 12 Oct).** Correct threshold and lifecycle handling, clear alert explanation and authorised resolution.

**Acceptance:** assigned Sheriff scans a physical label on pilot hardware, records a hand-off, reports missing and resolves found; all events and alerts remain consistent after refresh/restart.

### D. Module 2 — Hearing compliance and escalation

- [ ] **HEAR-01 — Implement legally approved rules (DEV/LAW, 12 Oct).** Structured hearing outcomes/reasons, requesting party, interval validation and approved exceptions. Avoid a permanent unlimited-unlock field.
- [ ] **HEAR-02 — Complete approval workflow (DEV, 12 Oct).** Pending request, authorised decision, approver/time/reason and a bounded approval tied to the relevant request.
- [ ] **HEAR-03 — Separate judgment from interlocutory ruling (DEV, 12 Oct).** Preserve outcome details; validated state transitions; prevent duplicate final judgment and reopening executed cases accidentally; freeze appropriate duration metrics.
- [ ] **HEAR-04 — Separate compliance flags (DEV, 12 Oct).** Independent ML, custody, adjournment and enforcement statuses; persistent escalation timestamps.
- [ ] **HEAR-05 — Finish alerts and response tracking (DEV, 12 Oct).** Scheduled compliance job rather than writes on GET; judge hearing alerts wired to UI; DCR/CR escalation inbox and acknowledgement/resolution trail.
- [ ] **HEAR-06 — Fix dates and UI errors (DEV, 12 Oct).** Consistent timezones, next hearing date validation, accurate previews and errors; no generic “5th adjournment blocked” message for unrelated failures.

**Acceptance:** LAW-approved scenarios and threshold tests pass; no inference clears a compliance flag; exceptions are attributable; scheduled alerts occur without users opening the dashboard.

### E. Notifications

- [ ] **NOTIFY-01 — Build a configurable provider (DEV, 12 Oct).** Correct environment variables, real provider adapter and a clearly labelled isolated simulator. No fixed localhost/port dependency.
- [ ] **NOTIFY-02 — Send to approved recipients (DEV/LAW, 12 Oct).** Phone validation, consent/lawful-basis handling, per-case recipient selection, approved templates and PII minimisation.
- [ ] **NOTIFY-03 — Persist and expose delivery state (DEV, 12 Oct).** Queued/sent/failed/delivered where supported; retry/idempotency; verified callbacks; failures visible in UI.
- [ ] **NOTIFY-04 — Verify live integration (DEV/OPS, 16 Oct).** Send to approved test recipients and confirm delivery. If credentials/template approvals are late, document the limitation; simulator-only delivery is not live-integration completion.

**Acceptance:** a hearing update produces an attributable notification record; successful delivery is verified, failure/retry is observable and port changes do not break the flow.

### F. Module 3 — Defensible AI delay-risk

- [ ] **AI-01 — Define an outcome and prediction horizon (DEV/LAW, 7 Oct).** Specify what “stall” means, when prediction occurs and which pending cases qualify. Do not predict outcomes already known at judgment.
- [ ] **AI-02 — Acquire and document data (LEAD/DEV, start 2 Oct; status by 12 Oct).** Contact Citizens’ Gavel/registry partners; confirm licensing and data permissions. No completion guarantee for external data access.
- [ ] **AI-03 — Replace circular training/evaluation (DEV, 12 Oct).** Train/evaluate against an independent observed or simulated future outcome, with leakage checks, representative coverage and appropriate splits. Synthetic evaluation remains a prototype, not proof of real-world performance.
- [ ] **AI-04 — Fix features and encodings (DEV, 12 Oct).** Canonical categories, one-hot/appropriate encoding, explicit unknown handling and domain-informed elapsed/hearing features available at prediction time.
- [ ] **AI-05 — Evaluate honestly (DEV, 16 Oct).** Baseline comparison, minority-class precision/recall, PR-AUC, ROC-AUC where applicable, calibration and documented limitations. No artificial requirement to show a spread of scores on real records.
- [ ] **AI-06 — Deploy reproducibly (DEV, 16 Oct).** Versioned model artefacts/metadata, documented build or retrieval, startup validation and clear model-vs-rules fallback indicator.
- [ ] **AI-07 — Finish useful risk UI (DEV, 16 Oct).** Scoped ranking of eligible cases, consistent thresholds, model-derived factor explanations, refreshed overview and non-actionable closed-case handling.
- [ ] **AI-08 — Publish a model card (DEV/LEAD, 16 Oct).** Data provenance, synthetic/real distinction, metrics, intended use and human-review requirement; reconcile all AI claims.
- [ ] **AI-09 — Validate on real approved hold-out data (DEV/LAW, external dependency).** Required before claiming real-world predictive validity; aim before showcase if data permits, otherwise explicitly report this as unfinished.

**Acceptance:** pipeline reproducible; no known feature/target leakage; unknown categories handled; scores and explanations match the actual model; no unsupported real-data or accuracy claims; AI is advisory, not a legal decision-maker.

### G. Module 4 — Judgment enforcement and legal documents

- [ ] **EXEC-01 — Complete the execution state machine (DEV/LAW, 12 Oct).** Valid judgment prerequisites, authorised stages, issue/serve/return/complete actions, partial recovery and relevant stays/appeals where LAW requires them.
- [ ] **EXEC-02 — Add completion and return-of-service UI (DEV, 12 Oct).** Sheriff records outcome/evidence, completion or failure; historical breaches remain auditable after resolution.
- [ ] **EXEC-03 — Capture required document data (DEV/LAW, 12 Oct).** Court/jurisdiction, structured parties, judgment date, sum/costs/interest, garnishee/property details and issuing authority. Do not infer creditor/debtor solely from case title order.
- [ ] **EXEC-04 — Implement and validate supported templates (DEV/LAW, 16 Oct).** Correct Fi Fa, garnishee, possession and delivery forms/stages. If a template cannot be approved, disable it and explicitly record reduced scope.
- [ ] **EXEC-05 — Separate draft/preview/print from issuance (DEV, 12 Oct).** Reprinting must not create another enforcement action; mark drafts and require authorised approval before official issuance.
- [ ] **EXEC-06 — Verify enforcement alert semantics (DEV/LAW, 16 Oct).** Correct judgment-based timing and approved conditions; distinguish no action, stalled action, completed and exempt/stayed cases.

**Acceptance:** a delivered judgment reaches Executed through the UI; a pending case cannot; each supported document is legally approved, complete and printable; reprints do not duplicate events.

### H. Documents, reports and frontend completion

- [ ] **APP-01 — Implement actual document storage (DEV, 12 Oct).** File upload/download, validated size/type/name, safe storage, access control, metadata and appropriate scanning policy for the permitted formats.
- [ ] **APP-02 — Fix case creation and user administration (DEV, 12 Oct).** Court defaults based on session, constrained choices, usable account forms, assignment controls and coherent detail/history views.
- [ ] **APP-03 — Complete scoped exports (DEV/LAW, 16 Oct).** Monthly/weekly periods, approved metric definitions, DCR division scope, minimum PII, accurate jurisdiction labels and approved CSV/PDF outputs.
- [ ] **APP-04 — Standardise UI states (DEV, 16 Oct).** Loading/empty/error states, accessible forms/toasts, action permissions, clear session/provider/model status and no stale placeholder claims.
- [ ] **APP-05 — Remove avoidable internet dependencies (DEV, 16 Oct).** Build/self-host pinned styles/scripts/fonts and local QR generation; define and test an offline showcase contingency. Offline data editing/sync is not assumed in scope.
- [ ] **APP-06 — Test devices and accessibility (DEV/OPS, 16 Oct).** Real browsers, camera/scanner permissions, responsive mobile layout, keyboard navigation, labels, contrast and print pagination.

**Acceptance:** all visible actions are supported, authorised and tested; files can be retrieved; reports are truthful and scoped; UI works on the pilot’s actual devices.

### I. Testing, deployment and operational readiness

- [ ] **QA-01 — Replace stale tests (DEV, 7–16 Oct).** Isolated database fixtures, JWT auth, current schemas and no mutation of committed data; include missing test dependencies.
- [ ] **QA-02 — Add unit/regression coverage (DEV, 16 Oct).** Permission matrix, session revocation, threshold boundaries, state transitions, exception consumption, missing/found persistence, spoofing, XSS, traversal, duplicate/idempotent actions and notification failures.
- [ ] **QA-03 — Add end-to-end tests (DEV, 16 Oct).** All five roles and full lifecycle in a real browser; upload, scanner, exports and print; failure paths as well as successful paths.
- [ ] **QA-04 — Add CI and security checks (DEV, 7 Oct).** Tests, lint, syntax checks and dependency/security scanning; triage findings rather than trusting scanner silence.
- [ ] **OPS-01 — Document and package setup (DEV/OPS, 16 Oct).** README, `.env.example`, dependency management, start/train/seed commands, container or equivalent reproducible deployment, migrations and health checks.
- [ ] **OPS-02 — Deploy staging/pilot environment (OPS, 16 Oct).** HTTPS, approved accounts, protected secrets, persistent storage, scheduled jobs, restricted logs and basic monitoring.
- [ ] **OPS-03 — Backups and rollback (OPS, 19 Oct).** Automated backup, successful restore rehearsal, previous-release rollback and incident/support contacts.
- [ ] **OPS-04 — Verify capacity (DEV/OPS, 19 Oct).** Expected pilot concurrency/data volume, background jobs, duplicate requests and appropriate database behaviour.
- [ ] **OPS-05 — Clean and consolidate repository (DEV, 16 Oct).** Remove broken/obsolete scripts and lock files, archive stale docs, maintain one authoritative status checklist and remove unused Firestore claims.
- [ ] **PILOT-01 — Prepare staff and test script (LEAD/LAW/DEV, 19 Oct).** User guide, role accounts, training, approved scenarios/data, physical QR labels, device checks, feedback form and escalation/support procedure.
- [ ] **PILOT-02 — Release acceptance (LEAD/LAW/OPS, 19 Oct).** Sign off the release gates below before staff receive access.

### J. Pilot follow-up and competition completion

- [ ] **SHOW-01 — Record pilot results (LEAD/DEV, 21–22 Oct).** Observations, defects, task completion times, user feedback and any incident; do not claim impact beyond measured evidence.
- [ ] **SHOW-02 — Resolve pilot blockers (DEV, 28 Oct).** Reproduce, fix and regression-test critical/high findings; document remaining lower-priority limitations.
- [ ] **SHOW-03 — Finish pitch deck (LEAD/LAW, 30 Oct).** Real team names, correct architecture/AI/notification claims, approved institutional references and pilot evidence.
- [ ] **SHOW-04 — Complete Business Model Canvas (LEAD, 30 Oct).** Partners, deployment/support costs, adoption model, value proposition, channels and sustainability.
- [ ] **SHOW-05 — Complete abstract and proposal evidence (LEAD/LAW, 30 Oct).** Updated status, e-filing complement positioning, accurate pilot/model limitations and verifiable institutional pathway.
- [ ] **SHOW-06 — Record/edit pitch video (LEAD/DEV, 30 Oct).** Approved script, stable full-lifecycle demo, subtitles and required duration/file format.
- [ ] **SHOW-07 — Prepare showcase release and contingency (DEV/OPS, 30 Oct).** Repeatable seeded demo, frozen model/config, backup deployment, screenshots/recording and offline presentation assets.
- [ ] **SHOW-08 — Rehearse and finalise submission (ALL, 2 Nov or earlier official deadline).** Full presentation plus Q&A; verify links/files; ensure all completion claims match the release.

## 4. Release gates — definition of done

### Pilot gate — by 19 October

- [ ] Security tasks SEC-01–08 accepted; no known unmitigated critical/high security defect.
- [ ] LAW approves active legal workflows/templates; approved pilot data and institutional permissions recorded.
- [ ] Every role can complete its assigned tasks; full case lifecycle passes an end-to-end rehearsal.
- [ ] Custody, hearing, escalation and enforcement flags remain consistent; actor identity and history are trustworthy.
- [ ] Deployed test suite and regressions pass; actual pilot devices tested.
- [ ] Model/provider limitations are visible; no misleading success messages or unsupported AI claims.
- [ ] Backup/restore, rollback and support arrangements tested.
- [ ] Any dependency-related scope reduction is written down and approved; never silently marked complete.

### Showcase gate — by 2 November

- [ ] Pilot blockers resolved with evidence and regression tests.
- [ ] Demo is repeatable; rehearsal and contingency completed.
- [ ] Deck, abstract, BMC, video and required submission files approved.
- [ ] Documented limitations and external dependencies match presentation claims.

### Wider production gate — not automatically included in the deadline

- [ ] LAW/LEAD determine applicable NDPA/NDPC and NITDA duties, DPIA, DPO, retention and breach procedures.
- [ ] Real-data AI validation completed before predictive-validity claims.
- [ ] Independent security review/penetration test, MFA policy, recovery/monitoring and wider capacity requirements satisfied.
- [ ] Court approval for operational use and official document issuance obtained.

## 5. Approval requested

Approve or amend:
1. This scope and milestone schedule.
2. Pilot data type and target environment.
3. Law Lead decisions and notification approach.
4. Any intentionally deferred feature and the corresponding presentation limitation.

**Until approval is received, only the audit and this planning document are being added to the repository. No application development, dependency updates, data migrations or deployment work will begin.**

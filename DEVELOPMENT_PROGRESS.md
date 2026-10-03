# Development progress

> **Current status — 2 October 2026:** The latest local tranche adds a verified synthetic-only demo seeder, court-aware registration defaults, threshold/concurrency/notification-failure tests, and a first screenshot-driven UI refresh: grouped role-aware navigation, a quieter header, a prioritized worklist, and a dedicated case-intake view. Frontend tests pass locally; manual browser/device acceptance remains open. GitHub Actions and the Docker image have not yet been verified remotely/built. WhatsApp remains disabled by default; real delivery is untested. This is a competition-team prototype, not a government service, and government approval does not block feature development. Older checkpoints below are historical and are superseded where the latest entry or completion plan says so.

## 1 October 2026 — first security tranche

Development approved by the user. Overall release is NOT pilot-ready.

Implemented:
- Authentication on exposed case detail/prediction, user list, cron and message-log routes.
- Chief Registrar-only user list and message logs; password hashes omitted from user list.
- Simulator disabled by default, with an environment-configured shared secret when explicitly enabled.
- Shared fail-closed case authorization applied to case lookups, scoped batch predictions and the prototype summary export.
- Clerks cannot register cases outside their assigned court.
- Stored user profile determines token permissions; deleted/disabled users rejected on access and refresh.
- Prevent admin self-deletion/last-active-admin deletion.
- Scan/execution actors derived from authentication, not request input.
- Removed admin login prefill; cron button sends authentication headers.
- Explicit CORS configuration; reduced notification payload logging.
- Environment template, development requirements and temporary-database security regression tests.

Verification:
- `python -m pytest tests/test_security.py -q`: 7 passed (deprecation warnings remain).
- `node --check frontend/app.js`: passed.
- `git diff --check`: passed.
- Tests use temporary database and JWT key files; committed database was not used for test writes.

Still pending: frontend XSS remediation, complete session/logout/revocation, account creation/password management, strict input validation, dependency upgrades, explicit Sheriff assignment UI, actual QR capture, document storage, compliance/lifecycle correctness, AI rebuild, remaining tests and deployment.

Known integration changes: non-admin user/message-log requests now receive 403; frontend permission/error presentation still needs updating. Simulator broadcasts need DEMO_MODE=true and a strong SIMULATOR_SECRET; production notification integration remains pending. Legal-policy changes await Law Lead decisions.

## 1 October 2026 — publication and frontend security tranche

- Published the first security tranche to GitHub on `arena/01a0f82f-cll` (not main).
- Escaped server-controlled text at table, notification, scan-history, toast and writ rendering boundaries while retaining original identifiers in application state.
- Replaced dynamic inline JavaScript action attributes with delegated listeners and data attributes.
- URL-encoded QR payloads; added case identifier constraints/traversal rejection and nonblank override reasons.
- Added jsdom regression checks for malicious case IDs, webhook content, toast content and writ fields; verified buttons preserve original IDs without executing injected code.
- Verification: 8 backend security tests pass; frontend security harness passes; JavaScript syntax passes.
- Not complete: full CSP migration (static HTML handlers/CDN remain), comprehensive frontend/browser testing, session/logout/revocation and remaining completion-plan items.


## 1 October 2026 — session lifecycle and account-management tranche

Implemented:
- Added a server-side SQLite session ledger. Access JWTs now require an active session ID; logout revokes it immediately, and user deletion/disable/password change/reset revoke existing sessions.
- Login issues a short-lived access token in the response and a seven-day refresh JWT in a host-only, HttpOnly, SameSite=Strict cookie. Refresh tokens are not returned in JSON or stored in localStorage. `COOKIE_SECURE=true` by default; use `false` only for local plain-HTTP development.
- Refresh rechecks the current user and active session. Browser startup restores via the cookie; protected API requests retry once after refresh; logout clears the cookie and in-memory credentials. Old localStorage tokens are discarded and the browser-side role selector is disabled.
- Added unique usernames (SQLite migration/index), UUID-based account IDs, role/assignment validation, temporary-password provisioning, forced password change on first login, self-service password changes, and Chief Registrar password reset with session revocation.
- Added account provisioning and required-password-change dialogs to the UI.
- Added repeatable frontend-test tooling (`package.json` / lockfile with jsdom as a dev dependency).

Verification:
- `python -m compileall -q backend`: passed.
- `.venv/bin/python -m pytest tests/test_security.py -q`: 13 passed (three deprecation warnings remain).
- `npm ci && npm run test:frontend`: both jsdom suites passed (frontend XSS and session flows).
- `node --check frontend/app.js` and `git diff --check`: passed.
- Session tests use temporary DB/key files. Cookie tests set `COOKIE_SECURE=false` only for HTTP TestClient; the checked-in example defaults it to true.

At this checkpoint, not complete: no real-browser/device or staging test; forgot-password delivery is a manual Chief Registrar temporary-password process; rate limits, full CSP, legal approvals, remaining module workflows and deployment are pending. The old `backend/test_api.py` suite has not yet been migrated to the authenticated API, so this security suite is not a claim that every repository test passes.

## 1 October 2026 — bootstrap and demo-mode safeguards

- Live mode no longer creates sample users with hard-coded credentials. An empty database starts without an account unless `COURTLOG_BOOTSTRAP_USERNAME` and a strong `COURTLOG_BOOTSTRAP_PASSWORD` are provided; that one-time Chief Registrar must change the password at first sign-in.
- The five fictional convenience accounts are seeded only with explicit `DEMO_MODE=true`. Known legacy seed accounts are disabled when the app starts in live mode; a configured bootstrap administrator can then be created if no active Chief Registrar remains.
- Demo/simulator UI is hidden in live mode. `/api/config` exposes only the non-sensitive mode flag; simulator logs and ingestion are disabled unless demo mode is explicit and the simulator secret matches.
- The WhatsApp code now returns `disabled` without making any outbound network request outside demo mode. UI labels state that simulation is not live Meta/WhatsApp delivery; the mock API token default was removed.
- Verification: `.venv/bin/python -m pytest tests/test_security.py -q`: 16 passed; `npm ci && npm run test:frontend`: passed; `python -m compileall -q backend`, `node --check frontend/app.js`, `npm audit --audit-level=high`, and `git diff --check`: passed.
- Remaining before live use: secrets must be provisioned safely, the first admin must be bootstrapped and tested in staging, no real WhatsApp adapter is implemented, and the broader pilot/showcase gates remain open.

## 1 October 2026 — B7 request-validation slice

Implemented:
- Applied the existing constrained case-ID type to every `/api/cases/{case_id:path}` handler as well as case-creation and scan request bodies. Traversal-shaped IDs are rejected before a route uses them.
- Added maximum lengths and blank-value checks to scan, execution, hearing, assignment, reassignment, missing-file, case-registration, login, and document-metadata inputs.
- Validated hearing dates as ISO 8601; an adjournment now needs a date, while the existing date-only HTML input and optional next date for a matter heard remain supported. No statutory interval or adjournment-count rule was changed.
- Validated and normalized Nigerian contact numbers to `+234…` E.164 form while accepting the existing `+234`, `234`, and domestic `0` formats (including ordinary spacing/punctuation).
- Removed filesystem directory creation and path joining from the metadata-only document endpoint; rejects path-like filenames and returns `storage_status: metadata_only` / `storage_path: null`. Updated UI copy so it no longer claims a binary document was uploaded.
- Added baseline security response headers and disabled interactive API docs/OpenAPI unless explicit demo mode is enabled.
- Added regression tests for invalid path-route IDs, traversal filenames, valid/invalid phone numbers, blank/invalid dates, and production-mode docs/security headers.

Verification:
- `.venv/bin/python -m pytest tests/test_security.py -q`: 23 passed (three existing deprecation warnings).
- `node --check frontend/app.js`, `npm run test:frontend`, and `npm audit --audit-level=high`: passed; 0 npm vulnerabilities.
- `python -m compileall -q backend` and `git diff --check`: passed.

At this checkpoint B7 remained open: rate limiting/lockout, broad enum review, dependency upgrades/removals, and full scanner triage had not yet been completed. Document binary upload/storage remains a separate D3 task. Real-browser, device, staging and pilot readiness have not been established; legal-rule changes remain pending Law Lead sign-off.

## 1 October 2026 — B7 login throttling and dependency hardening

Implemented:
- Added SQLite-backed, atomic rolling-window login attempt reservations. Defaults: five failures per username/client pair and 25 failures per client address over 15 minutes; successful sign-ins clear their reservation. Rate-limited requests return 429 with `Retry-After`; there is no permanent account lockout.
- Persist only SHA-256 pseudonymous keys for username/client buckets; raw usernames and request peer addresses are not added to the limiter table. Login failures (including unknown usernames) perform a bcrypt verification against a dummy hash to reduce timing-based username discovery.
- Restrict `HearingRequest.outcome` to the existing `Heard`/`Adjourned` UI values. Reason codes and execution action strings remain open pending the broader workflow/schema review; no legal rule or threshold changed.
- Upgraded FastAPI/Starlette/Pydantic, PyJWT, cryptography, requests, python-dotenv, Uvicorn and bcrypt; removed unused `passlib`, `xhtml2pdf` and `python-multipart`. Updated dev tooling to current pytest/httpx2 and added `pip-audit`.
- Documented rate-limit settings in `.env.example` and updated B7 tracking in the completion plan.

Verification:
- Fresh `.venv`, `pip check`: no broken requirements.
- `.venv/bin/python -m pytest tests/test_security.py -q`: 28 passed, two FastAPI lifespan deprecation warnings.
- `npm run test:frontend`, `node --check frontend/app.js`, and `python -m compileall -q backend`: passed.
- `pip-audit -r requirements-dev.txt` and full fresh environment audit: no known vulnerabilities found (1 October 2026 database snapshot).
- Regression tests cover threshold, `Retry-After`, rolling expiry, clearing successful reservations, concurrent request atomicity, and rejection of unknown hearing outcomes.

Still open: proper trusted-proxy client-IP configuration/edge throttling for the deployment, review of reason/action enums, broader scanner/CI triage, and all remaining workflow, legal, staging and pilot gates. The rate limiter does not by itself establish production readiness.

## 1 October 2026 — B8 application audit trail

Implemented:
- Added a SQLite append-only `audit_events` table with event IDs, UTC timestamps, authenticated actor IDs, action/entity identifiers, optional reason text and bounded JSON metadata. SQL triggers reject ordinary update/delete statements.
- Added a Chief Registrar-only `/api/audit/events` endpoint with a bounded latest-event limit.
- Recorded successful login/logout, user create/password change/reset/delete, case registration/scans/hearings (including blocked attempts)/DCR overrides/missing-file reports/judge assignment/reassignment/document metadata/execution, predictions, exports and manual compliance sweeps.
- Session references in the audit trail are hashed; password values, refresh/access tokens and party contact numbers are not copied into event metadata. Hearing/override reasons and authenticated actors are recorded.
- If appending an event fails after the business write, the request returns an explicit 503 warning that the operation may already have applied; the client is told to verify before retrying.

Verification:
- `.venv/bin/python -m pytest tests/test_security.py -q`: 31 passed, two FastAPI lifespan deprecation warnings.
- Regression tests verify authentication and CR-only access, correct actor/time/reason, no phone/password leakage, and SQL update/delete guards.
- `python -m compileall -q backend` and `git diff --check`: passed.

Important limitation: the case/user mutation and audit insert are separate database commits. SQLite triggers deter ordinary app-level edits but are not protection against a database administrator or file replacement. Atomic write+audit transactions and off-host/tamper-evident retention remain production gates. Broad browser/device, staging, module and legal sign-offs remain pending.

## 1 October 2026 — C1 Sheriff assignment, check-in and handover

Implemented:
- Added a court-scoped Sheriff lookup for an authorised case. It returns only active Sheriff accounts for the case's exact court and exposes only the selection fields needed by the UI.
- Clerks/Chief Registrars can assign or reassign custody with a required reason. The authenticated, currently assigned Sheriff can hand a file to another active Sheriff in the same court, recording recipient, location, reason, actor and time.
- An explicit assignment grants the receiving Sheriff access before any scan/check-in. After a handover, the prior Sheriff loses Sheriff-scoped access even if they scanned the case previously; legacy cases without an explicit assignment retain the previous last-scan/missing-report fallback until assigned.
- Added custody-history entries and append-only audit events for assignment, reassignment and handover. Scan/check-in no longer accepts a required staff ID; the event actor is taken from the active session. The UI displays the authenticated operator and includes assignment/handover actions.
- Tightened adjacent B2 scope: DCR reassignment cannot move a case outside the DCR's division, and a malformed DCR profile cannot make the weekly export fall back to all cases. Judge assignment, reads and alerts require an active Judge in the case's court. New registrations are not silently attached to a hard-coded demo Judge.
- Removed the remote QR-image request that sent case IDs to a third-party service. The prototype now identifies the scanner/check-in and QR graphic as simulations; genuine local QR generation and camera/USB capture remain C2.
- Replaced the stale unauthenticated API smoke tests with isolated, JWT/session-aware tests using fictional users and records. Test setup now configures a temporary database before importing the app, so the committed `data/courtlog.db` is not used or mutated by tests.

Verification:
- `.venv/bin/python -m pytest -q`: 42 passed, two FastAPI lifespan deprecation warnings.
- `npm run test:frontend`: passed, including UI selection and request-body tests for assignment and handover.
- `python -m compileall -q backend tests`, `node --check frontend/app.js`, and `git diff --check`: passed.
- Regression coverage includes an unassigned file invisible to a Sheriff, assignment visibility before scan, cross-court candidate rejection, authenticated scan identity, handover history, revocation of prior-Sheriff access, DCR division-scope rejection, and Judge court-scope enforcement for assignment, reads and alerts.

Checklist reconciliation after implementation: 6 of 55 named A–H tasks are checked (10.9%); 12 of 78 total plan checkboxes are checked (15.4%). These are checklist counts, not a codebase-wide completion estimate. B1 remains open because the demo webhook uses a shared secret rather than a staff-role check; B3 remains open because the CSP/static-inline-handler migration is unfinished. The full C2 scanner and all pilot, legal, staging and production gates remain open. No legal rule was changed.

## 1 October 2026 — C2 installable Sheriff QR PWA implementation slice

Implemented in code:
- Added a registry-only QR-label issuance API. Each label is `courtlog:v1:` plus a cryptographically random token; the SQLite store keeps only its SHA-256 hash, case reference, issuer and timestamp. The QR itself and printed label contain no case number/details; the token is never treated as authorization.
- Added authenticated QR check-in for Sheriff accounts. The server resolves the token, checks current case/court scope and explicit Sheriff assignment, and atomically rechecks that assignment while appending the scan. The signed-in account is the recorded actor; the QR token is not included in the case event or audit metadata. Prior label tokens do not bypass a handover.
- Kept both fallbacks: a USB keyboard-wedge scanner can enter the opaque payload into the submit field, and a manual authorized-case selection check-in remains available. The browser reports success only when the API returns a matching event for the current signed-in actor and location.
- Added browser-local QR generation with `qrcode`, ZXing camera capture requesting the environment-facing camera, a print-only anonymous QR label, and a web app manifest/icons/install affordance. Registered a root-scoped service worker that caches only the static shell; `/api/` requests and non-GET requests bypass it. The offline page explicitly says scans are not saved or queued.
- Pinned `@zxing/browser@0.1.5` with `@zxing/library@0.21.3` for Node 22-compatible development; retained `qrcode@1.5.4` and added `esbuild@0.28.2`. The prior Node >=24 engine warning is resolved.

Verification:
- `.venv/bin/python -m pytest -q`: 45 passed, two existing FastAPI `on_event` deprecation warnings.
- `npm run test:frontend`: passed (XSS/session regression tests plus PWA token format, local QR encoder, camera constraints, cache policy, offline-no-queue and server-confirmation gating).
- `npm audit --audit-level=high`: 0 vulnerabilities; `.venv/bin/python -m pip check`: no broken requirements.
- `python -m compileall -q backend tests`, `node --check frontend/app.js`, and `git diff --check`: passed.
- API tests verify that tokens are not persisted raw, unauthorized/unassigned users cannot scan, server attribution is used, a pre-handover label cannot authorize the former Sheriff, and manifest/service-worker assets are served.

Still open: no printer output or actual pilot phone/browser camera test has been performed. Camera permission, focus, QR print size/readability, iOS/Android install prompts, and real network-loss recovery therefore remain unverified; C2 stays unchecked and is not reported complete. D6 local asset work was still open at the time of this entry and is closed in the later progress note. No real court data was used, no legal rule was changed, and this implementation does not establish staging or pilot readiness.

## 1 October 2026 — C3 missing/found workflow

Implemented:
- Split the physical-file-missing state from the idle-custody clock and ML delay-risk flag. Reporting a missing file no longer mutates either indicator; ordinary QR/manual check-ins and compliance sweeps cannot clear an open missing-file report.
- Added an authenticated, case-scoped `found` action for Sheriffs/Chief Registrar, with required found location and reason. An open report is resolved only by that explicit action; duplicate reports/resolutions return 409.
- Kept a per-case missing/found history with authenticated actor, UTC timestamp, location and notes/reason, plus append-only audit events for report and recovery. Resolving a legacy unassigned report also removes the old reporter-only Sheriff access fallback.
- Added separate dashboard counts, alert/filter state, report/recovery forms, and safe-text history rendering. Only roles permitted by the API see the report/recovery controls. Cron summaries now count open missing reports separately.

Verification:
- `.venv/bin/python -m pytest -q`: 46 passed, two existing FastAPI `on_event` deprecation warnings.
- `npm run test:frontend`: passed, including the malicious-value history-rendering regression; `npm audit --audit-level=high`: 0 vulnerabilities.
- `python -m compileall -q backend tests`, `node --check frontend/app.js`, `git diff --check`, and `.venv/bin/python -m pip check`: passed.
- API coverage verifies separation from idle/ML flags, persistence through check-ins and sweeps, explicit resolution, actor/reason history, authorization, and alert removal only after found action. Frontend coverage confirms Clerk controls stay hidden, Sheriff/Chief Registrar controls are available, and simultaneous idle/missing badges remain distinct.

C3 is checked in the completion plan. At this point in the log, counts were 7 of 55 named A–H tasks (12.7%) and 13 of 78 total plan checkboxes (16.7%). C2 remains unchecked pending printed-label and camera testing on the actual pilot phone. C4 remains open and requires Law Lead sign-off before any hearing-policy change; no legal rule was changed in this C3 tranche.

## 1 October 2026 — C5 alert/clock separation, D6 local assets, and current-claims review

Implemented:
- Removed the adjournment-review block's write to `risk_flag`; it now records only the separate DCR review state. Existing case-level trigger logic (`adjournment_count >= 4`) was not changed and remains a prototype setting pending A3/Law Lead sign-off.
- Added durable DCR request, acknowledgement, escalation, and decision history with actor/time/reason, an authorized DCR/Chief Registrar acknowledgement endpoint that does **not** approve or unblock, and a separate >24-hour in-app escalation clock anchored to the DCR request timestamp. The compliance sweep no longer uses the ML-risk notification clock for DCR escalation; historical records with no request timestamp initialize a new clock on first observation. This DCR escalation remains in-app only; it is separate from the C6 WhatsApp adjournment-notice path, which is now implemented but disabled by default.
- Updated the DCR queue to distinguish a configured threshold prompt from an actual pending review, show acknowledgement/escalation state, provide separate acknowledge and decision actions, and avoid presenting the count as a per-party statutory limit. Added the Judge/Chief Registrar scoped alert panel for upcoming hearing, adjournment-review, experimental delay-risk, and missing-file prompts; server content is rendered with `textContent`.
- Corrected frontend claims: hearing failures are no longer always reported as fifth-adjournment blocks; successful hearing logging no longer claims WhatsApp delivery; AI UI now discloses generated synthetic training rows, the possible heuristic fallback, lack of independent real-outcome validation, and the non-legal nature of the score. Updated the abstract/team brief and marked older project audit/status snapshots as superseded.
- Replaced the former NJC-labelled export and ML-derived compliance percentages with a scoped, PII-minimized prototype workflow summary; renamed the weekly DCR report fields to avoid treating ML risk as compliance. Print output is watermarked “Prototype Draft — Not Issued.” CSV/PDF formats, formal reporting schemas, and legal review remain open under D4/A4.
- Final UI/API label review replaced remaining compliance-themed page branding and sweep/status labels with prototype/workflow and execution-review wording. The configured 90-day behavior and stored legacy case flag are unchanged; only user-facing descriptions and the sweep response field name were clarified.
- Completed D6 local dependency assets: pinned Tailwind CSS, Chart.js, Font Awesome, and fonts are served from local bundles/assets; builder copies notices/licenses; service-worker cache is now v3. README documents the offline shell and confirms API/case data and scans are not cached or queued. QR generation remains local.

Verification:
- `npm run test:frontend`: passed (security/XSS, session/actions, and PWA suites; local frontend build included).
- `.venv/bin/python -m pytest -q`: **49 passed**, with two existing FastAPI `on_event` deprecation warnings. Backend tests use isolated temporary SQLite databases; the tracked `data/courtlog.db` was not used or modified.
- `python -m compileall -q backend tests`, `node --check frontend/app.js`, `node --check tests/frontend_security.cjs`, `node --check tests/frontend_session.cjs`, and `git diff --check`: passed.
- `npm audit --audit-level=high`: 0 vulnerabilities. `.venv/bin/pip-audit -r requirements.txt`: no known vulnerabilities. `.venv/bin/pip check`: no broken requirements.

Checklist reconciliation: C5 and D6 are checked. Current counts are **9 of 55 named A–H tasks (16.4%)** and **15 of 78 total plan checkboxes (19.2%)**. D7 remains open because complete 7/90-day boundary, concurrency, provider retry/failure, and actual device coverage are outstanding. C2 remains open pending phone/printer acceptance; C4/A3 legal approval, actual messaging integration, staging, live-data permission, production review, and pilot go/no-go remain external gates. No legal threshold or rule was changed; no real court data was used.


## 1 October 2026 — WhatsApp Cloud API prototype and hosting comparison

Implemented and reviewed against the current code:
- Added an opt-in-gated individual WhatsApp Cloud API adapter for generic, no-variable template messages. Real delivery is explicitly disabled unless configured and is always blocked in demo mode. No group integration is claimed.
- Added persisted WhatsApp preferences and delivery records; phone numbers are normalized to E.164, keyed-HMAC hashed for lookups, and masked in logs/UI. The phone normalizer rejects letters and unsupported punctuation before normalization.
- Added authorized consent-evidence recording, consent revocation, a STOP/STOP ALL/UNSUBSCRIBE and related inbound opt-out path, Meta webhook verification/signature validation, idempotent status callbacks, and an authenticated Chief Registrar delivery log. Provider errors are minimized in storage/logs. Ambiguous provider timeouts are marked `unknown`; they are not automatically retried because Meta may already have accepted a request.
- Added distinct idempotency keys for adjournment × recipient and controlled manual tests. The UI differentiates demo/simulated, disabled, queued, accepted, delivered, failed, and unknown statuses. The simulator never sends external messages.
- Updated the abstract, team brief, README, and completion plan to describe implementation truthfully, preserve legal-rule sign-off, distinguish development from future institutional deployment, and avoid treating historical institutional-review claims as verified.
- Added [`docs/HOSTING_COMPARISON_2026-10-01.md`](docs/HOSTING_COMPARISON_2026-10-01.md): compares Render, Railway, Fly.io, and DigitalOcean App Platform with current provider sources, SQLite/persistence implications, regional choices, indicative pricing, and a provisional Render staging recommendation. No cloud deployment/provider selection has happened.

Verification:
- `.venv/bin/python -m pytest -q`: **62 passed**, 2 FastAPI `on_event` deprecation warnings. Added direct accepted/rejected phone-normalization cases and asserted outbound HTTP timeout/redirect behavior.
- `npm run test:frontend`: **passed** (security, session, and PWA suites; local asset build included).
- `python -m compileall -q backend tests`, `node --check frontend/app.js`, `git diff --check`, `.venv/bin/python -m pip check`, and `.venv/bin/pip-audit -r requirements.txt`: passed; no known Python vulnerabilities. `npm audit --audit-level=high`: 0 vulnerabilities.
- Targeted phone normalization examples accepted Nigerian local/international forms and rejected alphabetic input; the complete backend suite also passed after the change.
- One-off `backend.main` import in an isolated temporary environment: approximately 80 MiB peak RSS; not a deployed load test.

Still open for C6 / staging: no Meta business account, access token, approved template, or controlled test recipient was supplied; webhook delivery/status callbacks have not been tested against Meta. Automated retry/recovery policy, operational backup/restore, and hosted staging acceptance remain open. The code does not invent legal rules or claim live delivery. Use synthetic records until specific real-data permission is documented; complete C2 phone/printer acceptance on the intended device. Feature development is approved and does not wait on public-sector approval because CourtLOG is currently a competition-team project. Any future institutional pilot/public-sector deployment is separate.

## 2 October 2026 — deterministic demo data, threshold tests, status/docs and delivery tooling

Implemented:
- Replaced the case-registration form's hard-coded Lagos default with the signed-in Clerk's court; the Clerk cannot select a different court in the form. Non-registering roles no longer see the registration panel. The backend's court and assignment checks remain authoritative.
- Added `scripts/seed_demo_data.py`, which creates eight deterministic-by-date, clearly fictional pending/concluded scenarios for the five demo roles. It reads no CSV or tracked database; it requires `DEMO_MODE=true`, an ignored `.local/` path, known demo accounts, and refuses mixed/non-demo records. Added a scenario catalog and tests for reproducibility, every-role scope, safe overwrite, risk bands, missing/found history, and overdue execution.
- Added regression coverage for the configured 7-day custody prompt, 24-hour DCR escalation, and 90-day execution-review prompt at their boundaries; added a concurrent WhatsApp outbox-claim test and an ambiguous timeout test that preserves `unknown` without retrying.
- Added `.github/workflows/ci.yml` for backend/frontend tests, dependency consistency, and Python/npm security audits. Added a non-root Dockerfile, `.dockerignore`, health check, and documented build/run instructions. The push-triggered [GitHub Actions run](https://github.com/JayMan5/CLL/actions/runs/36979457121) failed before starting either job because GitHub reports the account is locked due to a billing issue; no CI test step ran. Docker is unavailable in this workspace.
- Added a current evidence index (`STATUS.md`), linked it from README, replaced the inaccurate legacy root walkthrough, and added role-specific demo guidance, scenario catalog, and feedback/triage template. Historical Markdown reports remain explicitly labeled; binary `.docx`/`.pptx` and competition materials still need review.
- Updated the completion plan: D1 is fully checked after code/test verification. D7, D8, E2, and E3 remain unchecked with partial progress documented. The two legacy `task.md` verification items remain open; the tracked database was not reseeded.

Verification:
- `.venv/bin/python -m pytest -q`: **70 passed**, two existing FastAPI `on_event` deprecation warnings.
- `npm run test:frontend`: passed (security, session/registration-default, and PWA suites). The build emits a non-blocking outdated `caniuse-lite` advisory.
- `.venv/bin/python -m pip check`: no broken requirements. `.venv/bin/pip-audit -r requirements.txt`: no known vulnerabilities. `npm audit --audit-level=high`: 0 vulnerabilities.
- `.venv/bin/python -m compileall -q backend tests scripts`, `node --check frontend/app.js`, and `git diff --check`: passed.
- Isolated seed smoke test created eight fictional cases and five demo accounts in a disposable `.local/` directory, then removed that scratch database. Tests and smoke checks did not write to tracked `data/courtlog.db`.

Still open: full end-to-end workflow/browser/device acceptance, pilot role owners/feedback channel, Legal Lead decisions, real-data permission, provider-backed WhatsApp delivery, hosted staging, tested backups/restore/rollback, CI execution after the repository billing lock is resolved, container build, and review/correction of the tracked Word/PowerPoint materials. No legal rule changed, no real court data was used, and no pilot/deployment acceptance is implied.

## 2 October 2026 — first screenshot-driven UI refresh

Implemented:
- Replaced the flat left navigation with grouped workspaces, role-filtered links that follow the existing server permission matrix, an active-page indicator, and an accessible mobile drawer with Escape/backdrop close and keyboard focus containment. Server/API authorization remains authoritative.
- Simplified the header: removed the role-selector-shaped control, show authenticated role/scope once, moved account/theme/sign-out to a click-operated menu, and relocated export/workflow sweep actions to the dashboard.
- Rebuilt the dashboard hierarchy: one distinct “Needs attention” area, two non-duplicated metrics, a searchable case worklist before the experimental chart, and a collapsible metadata-only form.
- Moved case registration to a dedicated role-gated page, kept the Clerk court default and all server validation/required fields, improved mobile form stacking and contact/WhatsApp helper text, and replaced the case-create browser alert with server-confirmed loading/success/error feedback.
- Added consistent responsive shell/card/table/form styles, visible keyboard focus, a skip link, accessible labels/status regions, reduced-motion support, and mobile horizontal-scroll guidance for the case table.
- Kept the PWA manifest name `COURTLOG Sheriff Custody Check-In`; added in-app explanation that the browser owns its native install confirmation and origin/publisher text, and aligned manifest theme colors with the refreshed dark shell. Install is still requested only after the user clicks the supported-browser action; scans are not queued offline. Bumped the static shell cache to v5.

Verification:
- `npm ci`: passed; 0 reported npm vulnerabilities.
- `npm run test:frontend`: passed (security/XSS, session, PWA, and new role-aware UI/navigation/dashboard checks).
- `node --check frontend/app.js`, HTML ID/label consistency check, manifest parsing, and `git diff --check`: passed.
- No backend or legal-rule changes were made. Manual browser viewport, contrast review, and physical-device PWA acceptance remain open.

## 3 October 2026 — Tailwind v4 toolchain security migration

Implemented:
- Replaced Tailwind CSS 3.4.19 with pinned Tailwind CSS and `@tailwindcss/cli` 4.3.0. The v4 CLI now builds the same checked-in frontend CSS asset through the existing `npm run build:frontend` workflow.
- Migrated the input stylesheet to v4 `@import`, explicit source paths, `@source inline()` runtime utility safelisting, and an explicit compatibility config load. Preserved the custom fonts/timing/scale tokens and v3 border, placeholder, and button-cursor defaults.
- Updated the legacy JS config to keep only supported theme extensions, refreshed the third-party notices, and bumped the PWA shell cache to v6 for the regenerated CSS.
- Resolved the five high npm audit findings without `--force`: pinned the v4 CLI/engine at 4.3.0 and let `npm audit fix` select `@parcel/watcher` 2.6.0, outside the vulnerable range.

Verification:
- `npm ci`, `npm run test:frontend`, `npm audit --audit-level=high`, `npm audit --omit=dev`, `node --check frontend/app.js`, and `git diff --check`: passed; npm reports 0 vulnerabilities.
- The PWA regression suite confirms the v4 input configuration, aligned CLI/engine versions, retained hidden/font utilities, and service-worker cache invalidation.
- No backend, role-permission, or legal-rule changes were made. Manual browser screenshot/viewport acceptance remains open; Tailwind v4's minimum browser support must be checked against intended devices before production use.

## 3 October 2026 — priority alert review navigation

Implemented:
- Fixed the three dashboard review actions to filter cases by custody, execution-review, or open-missing status and scroll to the actual case worklist. The previous handler looked for a `.glass-panel` ancestor that the worklist no longer uses.
- Replaced these inline handlers with delegated `data-alert-filter` click handling; the worklist heading receives keyboard focus, respects reduced-motion settings, and clears the sticky-header offset.
- Bumped the PWA shell cache to v8 so installed clients receive the revised JavaScript/HTML.

Verification:
- `npm ci` and `npm run test:frontend`: passed; the UI suite clicks all three review actions and verifies the filtered fictional rows, scroll request, and focus target.
- No backend, permission, or legal-rule changes were made. Manual browser acceptance remains open.

## 3 October 2026 — responsive browser viewport pass

Implemented and reviewed:
- Added pinned Playwright 1.63.0 as a development dependency and `npm run test:viewport`. The test serves the real frontend locally, intercepts API calls with fictional fixtures, exercises alert filtering, mobile navigation, and case-registration forms, and saves repeatable screenshots plus geometry measurements under ignored `.local/viewport-pass/`.
- Exercised 1600×900, 1366×768, 1024×768, 768×1024, and 390×844. No page-wide horizontal overflow was found; the wider case table stays in its own horizontal scroll wrapper. The mobile drawer and phone/tablet form controls remained within the viewport.
- The form screenshots exposed required-field asterisks being forced onto a separate line by grid-styled labels. Changed the custom label layout to normal block flow and added browser assertions that required marks stay inline; the revised screenshots show the fixed layout.
- Playwright browser downloads failed in this sandbox with TLS `ECONNRESET`; the actual run used temporary, unsaved `@sparticuz/chromium` 153.0.0 with its bundled Amazon Linux libraries. That package is not an application dependency. The standard repeat command is `npx playwright install chromium` followed by `npm run test:viewport`.

Verification and remaining scope:
- `COURTLOG_USE_SPARTICUZ=1 npm run test:viewport`: passed at all five target sizes, including phone/tablet registration-form checks, mobile navigation open/close, custody alert filtering, and no page errors.
- Screenshots and measurements were inspected. Fresh test outputs stay ignored under `.local/viewport-pass/`; committed reference PNGs and `measurements.json` are in `docs/viewport-evidence/`. They contain fictional fixtures, not court material. No backend/API permission, legal rule, training data, or WhatsApp provider behavior was changed by the viewport work.
- UI-17 is checked in `UI_UPGRADE_PLAN.md`. Actual-device/PWA install and camera acceptance, 200% zoom, broader accessibility and cross-role review, and C2 remain open. No phone/printer test or live provider delivery was attempted.

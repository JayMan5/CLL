# Development progress

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
- Added durable DCR request, acknowledgement, escalation, and decision history with actor/time/reason, an authorized DCR/Chief Registrar acknowledgement endpoint that does **not** approve or unblock, and a separate >24-hour in-app escalation clock anchored to the DCR request timestamp. The compliance sweep no longer uses the ML-risk notification clock for DCR escalation; historical records with no request timestamp initialize a new clock on first observation. Escalation is in-app state only; no external notification is sent.
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

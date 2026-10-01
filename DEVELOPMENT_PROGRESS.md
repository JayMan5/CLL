# Development progress

## 1 October 2026 — first security tranche

Development approved by the user. Overall release is NOT pilot-ready.

Implemented:
- Authentication on exposed case detail/prediction, user list, cron and message-log routes.
- Chief Registrar-only user list and message logs; password hashes omitted from user list.
- Simulator disabled by default, with an environment-configured shared secret when explicitly enabled.
- Shared fail-closed case authorization applied to case lookups, scoped batch predictions and NJC export.
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

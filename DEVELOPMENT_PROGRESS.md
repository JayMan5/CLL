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

Not complete: no real-browser/device or staging test yet; built-in seeded accounts still have weak demo credentials and require the separate bootstrap/demo-mode tranche before any live use; forgot-password delivery is a manual Chief Registrar temporary-password process; rate limits, full CSP, legal approvals, remaining module workflows and deployment are still pending. The old `backend/test_api.py` suite has not yet been migrated to the authenticated API, so the 12-test security suite is not a claim that every repository test passes.

# COURTLOG

COURTLOG is a prototype for court-file custody tracking and registry workflows. It is **not certified for production use**. Some legal/workflow policies, real integrations, deployment controls, and field acceptance checks remain open; see [`COURTLOG_COMPLETION_PLAN.md`](COURTLOG_COMPLETION_PLAN.md) and [`DEVELOPMENT_PROGRESS.md`](DEVELOPMENT_PROGRESS.md).

## Safety before running

- Use fictional test data unless written permission authorizes specific real records. Do not use the tracked `data/courtlog.db` for manual testing; it is repository data and must be treated as read-only.
- The committed demo accounts and passwords are intentionally available only when `DEMO_MODE=true`. Their credentials are weak and for an isolated disposable demo only. Never enable demo mode in staging/production or expose those accounts publicly.
- Live/safe mode is the default. It does not seed those demo accounts. A live-mode first account must be provisioned using the bootstrap process in `.env.example` and a secret manager; do not commit `.env` or credentials.
- Legal-policy changes require Law Lead sign-off. Do not infer approval from a working screen or test result.

## Local development setup

Requirements: Python 3.11+, Node.js 22+, and npm.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
npm run build:frontend
```

On Windows, use `.venv\Scripts\python.exe` instead of `.venv/bin/python`.

### Start an isolated fictional local demo

1. Copy `.env.example` to `.env` and edit it for a **disposable local demo only**. Set `DEMO_MODE=true`, `COOKIE_SECURE=false` (plain HTTP is only for local development), and use a unique path under `.local/` for `COURTLOG_DB_PATH`, `JWT_PRIVATE_KEY_PATH`, and `JWT_PUBLIC_KEY_PATH`. Use a fresh database file rather than the tracked `data/courtlog.db`.
2. Set a local-only `SIMULATOR_SECRET` if you want to exercise the explicitly labelled simulator. It does not send real WhatsApp messages.
3. Start the API and static frontend:

```bash
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

4. Open `http://127.0.0.1:8000/` on the same development computer. Stop the process with Ctrl+C.

For a first-run demo, the application seeds fictional demo accounts only into the fresh database when `DEMO_MODE=true`. Keep that database private and disposable. When testing without demo accounts, leave `DEMO_MODE=false` and provision accounts through the documented bootstrap/admin flow.

**A local HTTP demo is not the C2 real-device test.** A phone cannot use the developer computer's `localhost`, and camera access on a remote plain-HTTP address is not a secure browser context. Use the approved HTTPS staging deployment for phone/printer acceptance and follow [`C2_REAL_DEVICE_ACCEPTANCE_TEST.md`](C2_REAL_DEVICE_ACCEPTANCE_TEST.md).

## Build and verification commands

```bash
# Rebuild pinned local frontend dependencies/assets (Tailwind, Chart.js, icons, fonts, QR/PWA bundle)
npm run build:frontend

# Frontend regression suites; the command rebuilds local assets first
npm run test:frontend

# Backend API/security tests use isolated temporary databases
.venv/bin/python -m pytest -q

# Additional checks
.venv/bin/python -m pip check
.venv/bin/pip-audit
node --check frontend/app.js
python -m compileall -q backend tests
git diff --check
npm audit --audit-level=high
```

`npm run build:frontend` writes deployable static bundles and the limited static vendor assets under `frontend/`. The exact package versions are pinned in `package.json` and `package-lock.json`; `npm ci` installs the lockfile versions. The service worker's cache list must be kept in step with changed static assets and its cache name bumped when the shell changes.

## Frontend dependencies and offline behavior

Tailwind CSS, Chart.js, Font Awesome, Outfit, and Plus Jakarta Sans are built/served from local, pinned assets. The app does not need a font, icon, CSS, chart, or QR-generation CDN at runtime. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and the copied licenses under `frontend/vendor/`.

The service worker caches the static app shell and `offline.html` only. `/api/` responses, credentials, case data, and POST requests are not cached. **Custody scans are never saved or queued offline.** The offline page is the honest fallback for an offline walkthrough: it says no scan was submitted and tells the operator to reconnect. It is not a functional offline mode; do not show an offline attempt as a successful check-in.

## Current prototype behavior and limits

- The hearing endpoint currently applies a **case-level application trigger** when `adjournment_count >= 4` and no override reason exists. It does not implement a validated per-party legal count and must not be presented as an ACJA/ACJL finding. The threshold and workflow remain unchanged pending Law Lead sign-off.
- A DCR/Chief Registrar acknowledgement records a note but does not approve or unblock the case. More than 24 hours after a pending review is requested, the scheduled workflow sweep records an in-app escalation state; it sends no external notification.
- Delay-risk scores use a synthetic prototype training set with rule-generated labels, or a deterministic heuristic fallback when a trained artifact is not present. There is no independent validation against real court outcomes; scores are not legal findings or a basis for decisions.
- WhatsApp is a demo-only simulator; it sends no real recipient notice.

## Pilot and legal gates

The C2 implementation is not accepted until the intended phone/browser and printer have passed the documented real-device procedure. Staging must use HTTPS, a dedicated database, provisioned test accounts, and fictional data unless separate data permission is documented. Real integrations and legal-policy rules must not be represented as implemented or approved without their respective external approvals.

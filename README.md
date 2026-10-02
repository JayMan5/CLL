# COURTLOG

COURTLOG is a **competition-team prototype**, not a governmental entity or certified public-sector service. Feature development is authorized and does not wait on government approval; use synthetic/demo data unless written permission authorizes specific real court records. It is **not certified for production use**. Some legal/workflow policies, real integrations, deployment controls, and field acceptance checks remain open; see the [current verified status](STATUS.md), [`COURTLOG_COMPLETION_PLAN.md`](COURTLOG_COMPLETION_PLAN.md), the screenshot-based [UI upgrade task list](UI_UPGRADE_PLAN.md) (first interface-refresh slice implemented; browser/device acceptance remains open), [`DEVELOPMENT_PROGRESS.md`](DEVELOPMENT_PROGRESS.md), and the [hosting comparison and recommendation](docs/HOSTING_COMPARISON_2026-10-01.md).

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
2. Set a local-only `SIMULATOR_SECRET` only if you need to exercise the redacted demo webhook. It does not send real WhatsApp messages. The Meta Cloud API remains disabled by default.
3. Optionally seed eight fixed fictional scenarios into the isolated database. Timestamps default to today's UTC date; pass `--as-of YYYY-MM-DD` to reproduce a specific dated walkthrough. The seeder never reads the tracked database or any CSV:

   ```bash
   .venv/bin/python scripts/seed_demo_data.py
   ```

   The command requires `DEMO_MODE=true` and a `COURTLOG_DB_PATH` inside the ignored `.local/` directory. It refuses mixed/non-demo case records; use `--overwrite-fixtures` only when intentionally resetting those sample cases.
4. Start the API and static frontend:

```bash
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

5. Open `http://127.0.0.1:8000/` on the same development computer. Stop the process with Ctrl+C.

For a first-run demo, the application seeds fictional demo accounts only into the fresh database when `DEMO_MODE=true`; the optional script above adds fictional case scenarios. Keep that database private and disposable. When testing without demo accounts, leave `DEMO_MODE=false` and provision accounts through the documented bootstrap/admin flow. Do not run `seed_app_database.py` or `backend/seed_db.py` against tracked data; they are legacy tooling, not part of this safe demo workflow.

**A local HTTP demo is not the C2 real-device test.** A phone cannot use the developer computer's `localhost`, and camera access on a remote plain-HTTP address is not a secure browser context. Use the approved HTTPS staging deployment for phone/printer acceptance. Follow the [`C2 PWA setup, installation, and user guide`](C2_PWA_SETUP_AND_USER_GUIDE.md), then complete the [`C2 real-device acceptance test`](C2_REAL_DEVICE_ACCEPTANCE_TEST.md).

## Container image (build tooling, not a deployment)

The repository includes a minimal Docker image for reproducible staging evaluation. It serves the same FastAPI app and built frontend, runs as a non-root user, keeps SQLite/JWT files under `/var/lib/courtlog`, and exposes `/api/config` as a health check. Use a persistent volume at `/var/lib/courtlog`; do not copy the tracked `data/` directory into an image. The image defaults to live mode, demo accounts off, secure cookies on, and WhatsApp off. Building or running this image is not staging acceptance and does not establish HTTPS, backups, restore, monitoring, rollback, or provider configuration.

```bash
docker build -t courtlog:local .
docker volume create courtlog-data
# Export bootstrap credentials from a secret manager in your shell before this step.
docker run --rm --name courtlog -p 8000:8000 \
  --mount type=volume,src=courtlog-data,dst=/var/lib/courtlog \
  -e COOKIE_SECURE=false \
  -e COURTLOG_BOOTSTRAP_USERNAME \
  -e COURTLOG_BOOTSTRAP_PASSWORD \
  courtlog:local
```

Use this only on a controlled machine. `COOKIE_SECURE=false` is present only because the example uses plain HTTP on the same computer; keep it `true` behind HTTPS. Keep the bootstrap password out of shell history and container logs, remove it from the environment after first provisioning, and terminate the container when finished. For real hosted use, configure HTTPS and secrets at the provider, retain the volume, and complete the separate staging/backup/restore/rollback checks first. Docker itself must be installed locally; this workspace has no Docker daemon, so the Docker build has not been executed here.

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

## WhatsApp Cloud API setup (optional; disabled by default)

CourtLOG sends only a one-to-one, Meta-approved template to a counsel/litigant contact whose explicit opt-in is currently recorded. The template must be generic and contain no case number, hearing date, or reason; the API payload does not send those fields. Inbound `STOP`, `STOP ALL`, `UNSUBSCRIBE`, `CANCEL`, `END`, `QUIT`, and `REMOVE` messages revoke the number's opt-in. The Chief Registrar console records existing consent evidence—it does not collect a recipient's consent. Do not infer consent from a phone number being present in a case.

Before enabling a real send:

1. Create/configure the Meta WhatsApp Business account, phone number, Cloud API app, and a public HTTPS webhook at `/api/whatsapp/webhook`; subscribe the app to the WhatsApp message/status fields. Meta's webhook challenge/signature is checked by the API.
2. Create and obtain approval for a generic utility template with no body variables, e.g. `CourtLOG has a schedule update. Sign in to the official portal to review it. Reply STOP to opt out.` Set `WHATSAPP_TEMPLATE_NAME` and its language to match the approved template. The application cannot verify Meta's template approval status.
3. Store the Cloud API access token, phone-number ID, Meta app secret, webhook verify token, and a stable `WHATSAPP_CONSENT_HASH_KEY` (at least 32 bytes) in the deployment's secret manager. Keep the HMAC key stable and back it up securely: consent lookups stop matching if it changes. Set `WHATSAPP_ENABLED=true` only after the webhook and consent path are ready. Never set these secrets in source control or browser JavaScript.
4. Use fictional cases and a recipient controlled by the team. Record the recipient's actual opt-in evidence with the Chief Registrar screen, then use its case/party selector to send a generic test template. `DEMO_MODE=true` always prevents real sends, even if WhatsApp variables are present.
5. Inspect the persistent delivery status and test the signed Meta callback plus opt-out flow. Unknown network outcomes are not automatically retried because the provider may already have accepted the message; verify status before any manual retry.

See [`.env.example`](.env.example) for the server variables. Meta's rules for opt-in, approved templates, business-initiated conversations, categories, and pricing still apply; hosting the integration does not satisfy them. Live delivery has not been exercised without real credentials and an approved test setup.

## Frontend dependencies and offline behavior

Tailwind CSS, Chart.js, Font Awesome, Outfit, and Plus Jakarta Sans are built/served from local, pinned assets. The app does not need a font, icon, CSS, chart, or QR-generation CDN at runtime. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and the copied licenses under `frontend/vendor/`.

The service worker caches the static app shell and `offline.html` only. `/api/` responses, credentials, case data, and POST requests are not cached. **Custody scans are never saved or queued offline.** The offline page is the honest fallback for an offline walkthrough: it says no scan was submitted and tells the operator to reconnect. It is not a functional offline mode; do not show an offline attempt as a successful check-in.

## Current prototype behavior and limits

- The hearing endpoint currently applies a **case-level application trigger** when `adjournment_count >= 4` and no override reason exists. It does not implement a validated per-party legal count and must not be presented as an ACJA/ACJL finding. The threshold and workflow remain unchanged pending Law Lead sign-off.
- A DCR/Chief Registrar acknowledgement records a note but does not approve or unblock the case. More than 24 hours after a pending review is requested, the scheduled workflow sweep records an in-app escalation state; it sends no external notification.
- Delay-risk scores use a synthetic prototype training set with rule-generated labels, or a deterministic heuristic fallback when a trained artifact is not present. There is no independent validation against real court outcomes; scores are not legal findings or a basis for decisions.
- WhatsApp now has a configurable Meta Cloud API adapter, a persistent privacy-minimized delivery log, signed webhook/status handling, and explicit opt-in/opt-out checks. It is disabled by default; `DEMO_MODE=true` can never send real messages. Live delivery still requires a Meta account, server-side secrets, a Meta-approved generic template, a public HTTPS webhook, a documented recipient opt-in, and a consented test. No live account/credentials were supplied for this code change, so real delivery remains unverified.

## Pilot and legal gates

The C2 implementation is not accepted until the intended phone/browser and printer have passed the documented real-device procedure. Staging must use HTTPS, a dedicated database, provisioned test accounts, and fictional data unless separate data permission is documented. Real integrations and legal-policy rules must not be represented as implemented or approved without their respective external approvals.

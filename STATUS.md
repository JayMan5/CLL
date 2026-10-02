# CourtLOG — Current Verified Status

**Verification date:** 2 October 2026

**Project status:** competition-team prototype; **not pilot-ready or production-certified**. This status reflects code and local test evidence only. It is not legal approval, institutional endorsement, permission to use real records, or acceptance on a phone/printer/provider.

Use this file as the quick status index. The detailed task owner/decision list is [`COURTLOG_COMPLETION_PLAN.md`](COURTLOG_COMPLETION_PLAN.md); setup and command instructions are in [`README.md`](README.md); dated implementation notes are in [`DEVELOPMENT_PROGRESS.md`](DEVELOPMENT_PROGRESS.md).

## Implemented in code (not equivalent to acceptance)

- **Authentication and access controls:** the API uses JWT-backed sessions, current stored user profiles, role/court/division scoping, protected routes, and password-hash filtering. The local automated suite exercises isolated databases and fictional users. This is not an independent security assessment.
- **Physical custody:** authenticated Sheriff assignment, handover, QR-token validation, server-attributed check-in, and separate missing/found history are implemented. The installable PWA provides local QR generation and camera/USB/manual paths; phone/browser/printer acceptance remains open.
- **Hearings and review:** hearing events, scoped case history, and a separate in-app DCR review/acknowledgement/escalation workflow exist. The current case-level adjournment trigger at four recorded adjournments and its override workflow are prototype settings, not approved legal rules or per-party statutory counting.
- **Delay-risk experiment:** the app can use a prototype Logistic Regression artifact or a deterministic heuristic fallback. Training data/labels are synthetic and rule-generated; no independent validation against real outcomes has been performed. Scores are not legal findings.
- **Execution/document screens:** prototype judgment/execution events, a configured 90-day application review prompt, and draft document output are present. Jurisdiction-specific legal review, lifecycle acceptance, and approved forms remain open.
- **WhatsApp adapter:** consent-gated individual template calls, privacy-minimized persistent delivery state, signed webhooks, and opt-out handling are implemented. It is disabled by default and blocked in demo mode. No live Meta account, approved template, controlled live recipient, delivery, recovery, or operational acceptance has been verified.
- **Local verification tooling:** the Python and npm dependencies are pinned; isolated backend tests and frontend regression scripts are present. This branch adds a GitHub Actions workflow, a non-root container build, and a synthetic-only local demo seeder. The push-triggered GitHub Actions run was blocked before test steps by an account billing lock; see the verification record below. The Docker image has not been built because Docker is unavailable in this workspace.

## Latest local verification

- `.venv/bin/python -m pytest -q`: **70 passed**, with two existing FastAPI lifespan deprecation warnings.
- `npm run test:frontend`: passed; build reports an outdated `caniuse-lite` advisory but no test failure.
- `.venv/bin/python -m pip check`: no broken requirements; `.venv/bin/pip-audit -r requirements.txt`: no known vulnerabilities; `npm audit --audit-level=high`: 0 vulnerabilities.
- `.venv/bin/python -m compileall -q backend tests scripts`, `node --check frontend/app.js`, and `git diff --check`: passed.
- Isolated demo-seed smoke test created eight fictional cases/five demo users in a temporary `.local/` database and removed it. Tests did not write to tracked `data/courtlog.db`.
- The push-triggered [GitHub Actions run](https://github.com/JayMan5/CLL/actions/runs/36979457121) was created, but both jobs failed before starting because GitHub reports the account is locked due to a billing issue. No remote test step ran; the local results above are the available test evidence until the account owner resolves billing. Docker is not installed in the workspace, so the image has not been built.

Re-run the commands below to reproduce the checks. Tests must never write to the tracked `data/courtlog.db`.

```bash
.venv/bin/python -m pytest -q
npm run test:frontend
.venv/bin/python -m pip check
.venv/bin/pip-audit -r requirements.txt
npm audit --audit-level=high
.venv/bin/python -m compileall -q backend tests scripts
node --check frontend/app.js
git diff --check
```

## Explicitly open gates

- Law Lead/registry decisions for adjournment policy, jurisdiction-specific execution rules, forms, and legal descriptions; engineering must not silently change them.
- Written permission and privacy/retention/incident arrangements before using any real case or party records.
- Actual phone/browser/camera/printer/USB-scanner acceptance for the PWA, plus network-loss/recovery testing.
- Hosting/provider selection, HTTPS staging, persistent storage behavior, monitoring, backup/restore, rollback, and acceptance checks.
- Meta account eligibility, approved template, real server secrets, webhook configuration, actual opt-in evidence, controlled recipient, provider delivery, and recovery path.
- Real-data ML provenance, leakage-resistant evaluation, calibration/performance evidence, and human oversight before any predictive reliance.
- End-to-end user/browser/device rehearsal, pilot permission/go-no-go, named feedback/triage owners, and independent review.
- Competition abstract/deck/video/submission materials and production/government rollout obligations.

## Self-assessment document index

| Document | Current standing |
|---|---|
| [`README.md`](README.md) | Current setup, safety, behavior, integration limits, and verification commands; update when the code or scripts change. |
| [`COURTLOG_COMPLETION_PLAN.md`](COURTLOG_COMPLETION_PLAN.md) | Current acceptance checklist and unresolved decisions; check a box only after its full criterion is verified. |
| [`UI_UPGRADE_PLAN.md`](UI_UPGRADE_PLAN.md) | Screenshot-based UI improvement backlog; planning only, with no redesign implemented yet. |
| [`DEVELOPMENT_PROGRESS.md`](DEVELOPMENT_PROGRESS.md) | Dated implementation log; older entries are historical and do not override current gates. |
| [`COURTLOG_Abstract.md`](COURTLOG_Abstract.md) | Current cautious prototype abstract; institutional and legal claims remain explicitly qualified. |
| [`COURTLOG_FULL_AUDIT.md`](COURTLOG_FULL_AUDIT.md) | Historical audit of commit `723a583`, not the current branch. Its individual reproduced findings are not automatically current evidence. |
| [`project_audit.md`](project_audit.md), [`project_analysis.md`](project_analysis.md), [`Report.md`](Report.md) | Historical snapshots with supersession warnings; do not use their former completion percentages, seed descriptions, or implementation claims as current status. |
| [`COURTLOG_Project_Update_TeamBrief.md`](COURTLOG_Project_Update_TeamBrief.md) | Team briefing with caveats; earlier institutional-review/proposal assertions are not verified approval evidence. |
| [`walkthrough.md`](walkthrough.md) | Current prototype walkthrough; the former inaccurate architecture description has been replaced. |
| Tracked `.docx` / `.pptx` under `docs/` | Not revalidated as part of this code pass; treat as historical/unapproved until reviewed against this status and current code before external use. |

**Claims that must not be made:** government/institutional endorsement or deployment; legally approved hearing/execution rules or forms; validated real-world AI performance; real WhatsApp delivery; functional offline scans; or completed phone/printer/staging/pilot acceptance.

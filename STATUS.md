# CourtLOG — Current Verified Status

**Verification date:** 14 October 2026

**Project status:** competition-team prototype; **not pilot-ready or production-certified**. This status reflects code and local test evidence only. It is not legal approval, institutional endorsement, permission to use real records, or acceptance on a phone/printer/provider.

Use this file as the quick status index. The detailed task owner/decision list is [`COURTLOG_COMPLETION_PLAN.md`](COURTLOG_COMPLETION_PLAN.md); setup and command instructions are in [`README.md`](README.md); dated implementation notes are in [`DEVELOPMENT_PROGRESS.md`](DEVELOPMENT_PROGRESS.md).

## Implemented in code (not equivalent to acceptance)

- **Authentication and access controls:** the API uses JWT-backed sessions, current stored user profiles, role/court/division scoping, protected routes, and password-hash filtering. A route-inventory regression now requires an explicit staff-auth dependency on every `/api/` route except the documented safe configuration, login/session, signed Meta webhook, and demo-secret simulator boundaries. Tests include Chief Registrar-only user/log access, scoped case/prediction denial, and Deputy Chief Registrar-only cron with audited attribution. The approved pilot roles are Chief Judge, Chief Registrar, Deputy Chief Registrar, Registrar, Filing Clerk, Registry Clerk, Court Clerk, Bailiff, and Sheriff; optional Presiding Judge access is read-only. Deferred Cashier/Fees Clerk, Counsel, and Counsel's Clerk are not assignable. Existing generic `Clerk` accounts are blocked from sign-in until a Chief Registrar explicitly assigns a new pilot role; they are never automatically granted Court Clerk access. Court Clerk access requires the server-side `COURTLOG_PAID_FEATURES=court_clerk` organization/deployment entitlement. This setting enables the feature but does not process or verify payment; there is no billing integration. The local automated suite exercises isolated databases and fictional users. This is not an independent security assessment. See [`docs/COURTLOG_ROLE_ACCESS_MATRIX.md`](docs/COURTLOG_ROLE_ACCESS_MATRIX.md).
- **Physical custody:** authenticated Sheriff assignment, handover, QR-token validation, server-attributed check-in, and separate missing/found history are implemented. The installable PWA provides local QR generation and camera/USB/manual paths; phone/browser/printer acceptance remains open.
- **Hearings and review:** hearing events, scoped case history, and a separate in-app DCR review/acknowledgement/escalation workflow exist. The current case-level adjournment trigger at four recorded adjournments and its override workflow are prototype settings, not approved legal rules or per-party statutory counting.
- **Delay-risk experiment:** the app can use a versioned one-hot Logistic Regression pipeline or a deterministic heuristic fallback, with the prediction source identified. The legacy tracked training CSV contains rule-generated labels calibrated from real-derived distributions with unverified permission; the trainer now requires explicit data/provenance and blocks treating that file as synthetic. The legacy top-level `build_dataset.py` remains unguarded and reads tracked source CSVs if invoked; do not run it without documented permission, and its generated rule labels are not observed outcomes. Synthetic-only pipeline tests pass, but no independent validation against real outcomes has been performed. Scores are not legal findings.
- **Execution/document screens:** prototype judgment/execution events, a configured 90-day application review prompt, and draft document output are present. Jurisdiction-specific legal review, lifecycle acceptance, and approved forms remain open.
- **WhatsApp adapter:** consent-gated individual template calls, privacy-minimized persistent delivery state, signed webhooks, and opt-out handling are implemented. It is disabled by default and blocked in demo mode. No live Meta account, approved template, controlled live recipient, delivery, recovery, or operational acceptance has been verified.
- **Local verification tooling:** the Python and npm dependencies are pinned; isolated backend tests and frontend regression scripts are present, including a Playwright viewport smoke test with fictional API fixtures. This branch adds a GitHub Actions workflow, a non-root container build, and a synthetic-only local demo seeder. The push-triggered GitHub Actions run was blocked before test steps by an account billing lock; see the verification record below. The Docker image has not been built because Docker is unavailable in this workspace.

## Latest local verification

- Full `.venv/bin/python -m pytest -q`: **86 passed, 8 warnings** (the remaining warnings are SciPy L-BFGS option deprecations). Coverage includes route-inventory authentication, the FastAPI lifespan startup sweep, Deputy Chief Registrar-only cron authorization/audit attribution, and a strict forward-time case-cohort split. The deprecated FastAPI `on_event` startup hook has been replaced with a lifespan handler that runs the existing sweep in a worker thread. Tests use isolated databases and fictional/synthetic fixtures; no court-data model was trained and no tracked court dataset was used. Pipeline tests fit only temporary models on fictional rows.
- `npm run test:frontend`: passed after building local assets; security, session, PWA, role-aware navigation, accessible menus, dashboard hierarchy, and alert-count checks pass. No frontend source change was part of this tranche.
- The latest recorded `npm run test:viewport` run (12 Oct) passed the dashboard and login suites in headless Chromium at 1600×900, 1366×768, 1024×768, 768×1024, and 390×844. Login card/fields/buttons stay within the viewport; dashboard checks include mobile/tablet registration forms, navigation, and contained table scrolling, with no page-wide horizontal overflow. Committed reference screenshots/measurements are in [`docs/viewport-evidence/`](docs/viewport-evidence/). Manual accessibility/zoom and physical-device acceptance remain open.
- Checks run 14 Oct: `.venv/bin/python -m pip check` found no broken requirements; `.venv/bin/pip-audit -r requirements.txt` found no known vulnerabilities; `npm audit --audit-level=high` and `npm audit --omit=dev` reported 0 vulnerabilities.
- `.venv/bin/python -m compileall -q backend tests scripts`, `node --check frontend/app.js`, and `git diff --check`: passed on 14 Oct.
- Isolated demo-seed smoke test created eight fictional cases/five demo users in a temporary `.local/` database and removed it. Tests did not write to tracked `data/courtlog.db`.
- GitHub Actions was checked after the 14 October push of `304c75e`; no run for that commit was visible at check time. The latest visible run, [38259574840](https://github.com/JayMan5/CLL/actions/runs/38259574840), ended before either job ran a step and reported empty step lists; this matches the previously reported account billing blocker, not a code-test failure. Earlier role-model/status pushes also show pre-step failures ([38257000805](https://github.com/JayMan5/CLL/actions/runs/38257000805), [38257093028](https://github.com/JayMan5/CLL/actions/runs/38257093028)). Local checks above are the available verification; Docker is not installed in the workspace, so the image has not been built.

Re-run the commands below to reproduce the checks. Tests must never write to the tracked `data/courtlog.db`.

```bash
.venv/bin/python -m pytest -q
npm run test:frontend
npx playwright install chromium  # first use only
npm run test:viewport
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
| [`docs/COURTLOG_ROLE_ACCESS_MATRIX.md`](docs/COURTLOG_ROLE_ACCESS_MATRIX.md), [`docs/PILOT_ROLE_QUICK_GUIDE.md`](docs/PILOT_ROLE_QUICK_GUIDE.md) | Current server-permission reference and staff walkthrough for the approved first-pilot roles; not a legal rulebook or proof of user acceptance. |
| [`UI_UPGRADE_PLAN.md`](UI_UPGRADE_PLAN.md) | Active UI task list; UI-17 headless viewport regression passed; cross-role, accessibility/zoom, and physical-device acceptance remain open. |
| [`DEVELOPMENT_PROGRESS.md`](DEVELOPMENT_PROGRESS.md) | Dated implementation log; older entries are historical and do not override current gates. |
| [`COURTLOG_Abstract.md`](COURTLOG_Abstract.md) | Current cautious prototype abstract; institutional and legal claims remain explicitly qualified. |
| [`COURTLOG_FULL_AUDIT.md`](COURTLOG_FULL_AUDIT.md) | Historical audit of commit `723a583`, not the current branch. Its individual reproduced findings are not automatically current evidence. |
| [`project_audit.md`](project_audit.md), [`project_analysis.md`](project_analysis.md), [`Report.md`](Report.md) | Historical snapshots with supersession warnings; do not use their former completion percentages, seed descriptions, or implementation claims as current status. |
| [`COURTLOG_Project_Update_TeamBrief.md`](COURTLOG_Project_Update_TeamBrief.md) | Team briefing with caveats; earlier institutional-review/proposal assertions are not verified approval evidence. |
| [`walkthrough.md`](walkthrough.md) | Current prototype walkthrough; the former inaccurate architecture description has been replaced. |
| [`docs/CourtLOG_Overview.docx`](docs/CourtLOG_Overview.docx) and other tracked `.docx` / `.pptx` | The overview is regenerated from `docs/generate_docx.py` and reflects the current role scope, ML provenance/limitations, and acceptance limits. `CourtLOG_RBAC_Mismatches.docx` is a historical role snapshot superseded by the current role matrix. Other binary documents and the pitch deck were not revalidated; review them against this status before external use. |

**Claims that must not be made:** government/institutional endorsement or deployment; legally approved hearing/execution rules or forms; validated real-world AI performance; real WhatsApp delivery; functional offline scans; or completed phone/printer/staging/pilot acceptance.

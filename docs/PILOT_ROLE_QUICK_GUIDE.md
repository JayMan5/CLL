# CourtLOG Local Demo: Pilot Role Quick Guide

**Status:** local competition-prototype walkthrough material; not staff training, legal guidance, proof of pilot approval, or production readiness. Use only a disposable `DEMO_MODE=true` database with fictional records. Never enter real case, party, contact, or staff information without written permission.

## Before you begin

1. Follow the isolated local-demo instructions in [`README.md`](../README.md). Never point a demo at the tracked `data/courtlog.db`.
2. Optionally seed the fixed fictional scenarios with `python scripts/seed_demo_data.py --as-of YYYY-MM-DD`; see [`DEMO_SCENARIO_CATALOG.md`](DEMO_SCENARIO_CATALOG.md).
3. Keep the demo local. Demo credentials are intentionally weak and must never be exposed publicly or used for hosting.
4. Sign out before handing the device to another role. Server-side authorization is authoritative; hidden UI controls are not a security boundary.

The default demo seeds accounts for Filing Clerk (`clerk`), Registry Clerk (`registry.clerk`), Bailiff (`bailiff`), Deputy Chief Registrar (`dcr`), Registrar (`registrar`), Chief Judge (`chief.judge`), Presiding Judge (`judge`), Sheriff (`sheriff`), and Chief Registrar (`cr`). The default password is `123`, except Chief Registrar's `12345`; these are fictional demo credentials only. A Court Clerk demo account is seeded only when the isolated demo deployment also enables `COURTLOG_PAID_FEATURES=court_clerk`.

## Pilot role/access summary

| Role | Current implemented access | Important limit |
|---|---|---|
| Chief Judge | Read-only court-scoped dashboard and sanitized judicial alerts | Cannot edit any record; the Chief Judge's decision itself is not captured in CourtLOG. |
| Chief Registrar | Read-only all-court case oversight; account create/list/delete/reset and explicit legacy-Clerk remapping; audit and summary reads | Cannot register or change case events. |
| Deputy Chief Registrar | Court-wide read; configured review acknowledgement/reasoned resolution, audited same-court division correction, reports, risk refresh and workflow sweep | Cannot manage users or change case court; application thresholds are not legal findings. |
| Registrar | Court-scoped Judge/Sheriff assignment, judgment-delivery date, separate notice request, writ issue/assignment, and WhatsApp consent administration | Cannot log hearing outcomes or record Sheriff execution on the Sheriff's behalf; assignment reason is stored but the source Chief Judge decision is not independently validated. |
| Filing Clerk | Assigned court/division case registration, opaque QR-label issuance, manual/QR scans, document metadata | No general post-filing case-field or hearing-event edit route; scans/metadata are separate append/record operations, and metadata is not a binary upload. QR issuance is Filing Clerk-only. |
| Registry Clerk | Court/division-scoped scans, missing-file report/recovery, document metadata, and Sheriff-choice reads | File movement is only a generic scan log; a complete registry-to-court custody workflow is not yet implemented. |
| Court Clerk | Entitlement-gated court/division-scoped scans, administrative hearing entry, and missing-file report/recovery | Requires the server-side Court Clerk entitlement; `Heard` entries cannot be marked as judgment/ruling delivery. Hearing entry does not send WhatsApp. |
| Bailiff | Court/division-scoped manual/QR custody check-ins | The per-defendant process-service, affidavit-of-service, and separate writ-execution workflows are not implemented. |
| Sheriff | Assigned-case reads, manual/QR check-ins, handover, missing-file report/recovery, and execution/return for a delivered judgment | Cannot issue a writ; explicit current assignment controls access (older unassigned cases have a limited last-scan/open-report fallback). |
| Presiding Judge | Optional read-only assigned-case dashboard fields and operational alert prompts | Access is limited to the Judge's own assigned cases and same court; case details/event histories are not exposed and no record edits are allowed. |

Court Clerk is a server-side organization/deployment entitlement, configured with `COURTLOG_PAID_FEATURES=court_clerk`. This setting only enables the role; it is not a payment/subscription connection and CourtLOG does not verify or process payment. Without the entitlement, Court Clerk account creation and sign-in are blocked even if a client changes the UI.

## Walkthrough by role

### Filing Clerk

- Register a clearly fictional case in the assigned court. The case record receives a stable ID and initial scan event; assignment to a judge is recorded separately by the Registrar.
- Generate/print an opaque QR label. The label contains a random token, not the case ID or party details.
- Do not use the Filing Clerk account for post-filing corrections. The implementation does not provide a full correction workflow; a DCR correction, where supported, records the old/new division and reason in the append-only audit log.

### Registry Clerk

- Use the QR/check-in workspace to append a scan as the authenticated user.
- Record a missing-file report or a recovery only for a fictional scenario.
- Document metadata can be recorded, but binary files, signed orders, CTC requests/releases, appeal bundles, and close-out custody states are not implemented.

### Court Clerk

- Use **Courtrooms** to record a supported `Heard` or `Adjourned` event and any required next date/reason.
- The existing configured case-level adjournment review threshold remains unchanged; it is an application prompt/hold, not a statutory or per-party determination. The Deputy Chief Registrar handles the flag.
- A Court Clerk cannot submit `Judgment Delivered`/`Ruling Delivered` as a hearing reason, and the endpoint does not let the Court Clerk change judgment status.
- WhatsApp notices are not sent automatically by the Court Clerk's log entry. The Registrar explicitly requests a generic notice, and only contacts with a current recorded opt-in are considered.

### Registrar

- Record a Presiding Judge assignment only with a Chief Judge decision reference. The app records the reference string; it does not capture or verify the underlying Chief Judge decision.
- Enter a judgment delivery date only; judgment text and legal reasons remain outside CourtLOG.
- On a delivered judgment, use the writ compiler to record an issued writ and an active Sheriff account ID. The generated PDF is a prototype copy and is not a court-issued instrument.
- Request a generic one-to-one WhatsApp notice for the latest adjournment. A phone number is not consent; use the stored consent evidence and inspect delivery status.

### Deputy Chief Registrar

- Open the court-wide flags and reports. Acknowledge or resolve an application flag with a reason; the existing trigger threshold is unchanged.
- Correct a division entry only within the assigned court. The prior value, new value, and reason are audited; cross-court reassignment and deletion are unavailable.
- Prototype risk scores and compliance sweeps are operational prompts, not legal determinations.

### Sheriff

- Confirm that the case is assigned to the signed-in Sheriff. A prior Sheriff loses access after a handover.
- Use the QR/camera or manual fallback; a success state appears only after server confirmation. Offline scans are not saved or queued.
- Record an allowed execution action/return only on a case assigned to that Sheriff. The Sheriff cannot issue or cancel a writ.

### Chief Registrar, Chief Judge, and Presiding Judge

- Chief Registrar: use **User Admin** to manage fictional accounts and explicitly map legacy Clerk accounts. A legacy account cannot sign in until a new pilot role is selected with an audit reason; Court Clerk is not offered unless the server entitlement is enabled.
- Chief Judge: read the court-scoped judicial dashboard/alerts only. The Registrar records a judge assignment against the Chief Judge's decision reference.
- Presiding Judge: read only the cases assigned to that account. No case event or judgment details can be edited from the judicial docket.

## Known workflow gaps versus the DOCX

This task implements the pilot role split and server-side access boundaries; it does **not** complete every stage in the workflow document. In particular, CourtLOG still lacks per-defendant service states and affidavit references, Chief-Judge-decision capture, full attendance/party-service call-over fields, registry/courtroom scan-out and scan-back closure, signed judgment/ruling PDF storage, CTC request/release tracking, and appeal-record/transit workflows. These remain implementation/acceptance work, not implied by the role names. Do not represent them as operationally complete.

## End the walkthrough

- Sign out, close the demo browser, and stop the local server.
- Keep or delete only the disposable synthetic database according to the team's reset procedure.
- Capture feedback without case details, phone numbers, credentials, tokens, or screenshots containing personal data. Use [`PILOT_FEEDBACK_AND_TRIAGE.md`](PILOT_FEEDBACK_AND_TRIAGE.md).

This guide does not show that staff training, device testing, legal review beyond the approved role model, WhatsApp delivery, staging, backup/restore, or pilot permission has happened. Record these as separate acceptance tasks in [`COURTLOG_COMPLETION_PLAN.md`](../COURTLOG_COMPLETION_PLAN.md).

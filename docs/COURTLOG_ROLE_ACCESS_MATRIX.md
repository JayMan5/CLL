# CourtLOG Pilot Role and Access Matrix

**Status:** code-aligned pilot reference, 12 October 2026. This documents the currently implemented server permissions for the approved first-pilot role set; it is not a legal ruling or a substitute for the source role specification.

The API is the authorization boundary. Hiding a page, button, or menu in the browser is only a usability measure; every protected operation must also pass the server-side role, entitlement, and case-scope checks.

## Role matrix

| Role | Server-enforced case scope | Implemented first-pilot access |
|---|---|---|
| **Chief Judge** | All cases in the assigned court, all divisions. Case-list and case-detail responses are reduced to dashboard fields. | Read-only court docket and operational alert prompts. Cannot register or alter cases, assign judges, administer users, or use registry workflows. |
| **Chief Registrar** | All courts and divisions. | Create, list, delete, and reset user accounts; explicitly remap legacy `Clerk` accounts; change Criminal/Civil assignments for Filing Clerk, Registry Clerk, entitlement-enabled Court Clerk, and Bailiff accounts with a required audit reason (target sessions are revoked); read audit events; read the all-court weekly/prototype summaries; view court Sheriff choices and WhatsApp status/logs. Case access is read-only through case endpoints; no case-registration, hearing, assignment, or custody mutation authority is granted by that role. |
| **Deputy Chief Registrar** | Assigned court, all divisions. | Review and acknowledge pending configured adjournment-review items; record a reasoned resolution; correct a case's division within the same court with before/after values and a reason in the audit event; run the scoped workflow sweep and risk refresh; read court-scoped summaries and audit events. Cannot change a case's court or administer users. |
| **Registrar** | Assigned court, all divisions. | Record a Presiding Judge assignment with an audit reason; assign/reassign a Sheriff; record the judgment-delivery date only; request the latest-adjournment notice through the separate notification route; issue a writ and record its Sheriff assignment. Does not log hearing outcomes or administer users. |
| **Filing Clerk** | Assigned court and division (or all divisions only if explicitly provisioned that scope). | Register a case only in the assigned court and division; issue opaque QR labels; perform manual/QR custody check-ins; record document metadata. Case type is checked against division on the server. The document endpoint records metadata only—it does not store file bytes. |
| **Registry Clerk** | Assigned court and division (or all divisions only if explicitly provisioned that scope). | View in-scope cases, perform manual/QR custody check-ins, record document metadata, report a missing file and record recovery, and view eligible Sheriff choices for an in-scope case. Sheriff assignment remains a Registrar action. |
| **Court Clerk** *(entitlement-gated)* | Assigned court and division (or all divisions only if explicitly provisioned that scope). | View in-scope cases, perform manual/QR custody check-ins, enter hearing outcomes, and report/resolve a missing file. The hearing endpoint rejects `Heard` entries whose reason is `Judgment Delivered` or `Ruling Delivered`. Hearing entry does **not** itself send WhatsApp; a Registrar must request a separate notice. |
| **Bailiff** | Assigned court and division (or all divisions only if explicitly provisioned that scope). | View in-scope cases and perform manual/QR custody check-ins. There is no separate Bailiff writ-issuance or execution-return operation: writ issue is a Registrar action and execution/return is recorded by the assigned Sheriff. |
| **Sheriff** | Assigned court and current file custody. Explicit assignment controls access; legacy cases without an assignment use the existing last-scan/open-missing-report fallback. | View assigned cases, check in assigned custody (QR scans require the current assignment), hand a file to another active same-court Sheriff, report/resolve a missing file, and record a valid execution/return action for a delivered judgment when currently assigned. A Sheriff cannot assign themself or another Sheriff to a case. |
| **Presiding Judge** *(optional, read-only)* | Cases assigned to that Judge in the Judge's assigned court. | Read-only assigned-case dashboard fields and operational alert prompts. The role cannot log hearings, deliver rulings through CourtLOG, or perform registry, custody, assignment, or user-management actions. |

### Scope and workflow details

- Every non-Chief-Registrar account must have a specific court. Chief Judge, Deputy Chief Registrar, and Registrar accounts are provisioned for **All Divisions** within that court; ordinary registry/service roles are limited to their assigned division unless an authorized account is intentionally provisioned with **All Divisions**. Presiding Judge visibility additionally requires the case's `assigned_judge_id` to match that user's ID.
- User Management allows the Chief Registrar to move an eligible Filing Clerk, Registry Clerk, entitlement-enabled Court Clerk, or Bailiff between the supported **Criminal** and **Civil** divisions. The change requires a reason, records before/after division values, and revokes the target's sessions. This editor cannot grant **All Divisions**, change the assigned court, or alter the scope rules for court-wide or assignment-based roles. Legacy `Clerk` accounts must still be explicitly remapped before their division can be changed.
- A Sheriff sees cases in the Sheriff's own court only. Once a file has an explicit active Sheriff assignment, that assignment is authoritative; a prior scan or missing-file report does not preserve access after handover. For older, unassigned cases, access is limited to the Sheriff's last scan or their still-open missing-file report. QR check-in is stricter and requires current assignment.
- Chief Judge and Presiding Judge case responses omit party contact data, case title, document records, scan history, hearing history, and execution history. Their alerts are operational prompts, not legal findings.
- Deputy Chief Registrar correction is limited to `assigned_division` in the same court. A cross-court move is rejected. The audit event stores both the prior and new value plus the supplied reason.
- Presiding Judge accounts are an optional read-only pilot assignment. A Registrar records the assignment; the server accepts only an active Presiding Judge account in the same court. The route records the Registrar's reason but does not independently validate a separate Chief Judge decision document.
- CourtLOG's configured adjournment-review threshold and any risk/custody flags remain application workflow prompts. They are not determinations of legal compliance; changing legal rules or thresholds requires the separately required Law Lead sign-off.

## Court Clerk entitlement—not payment processing

`Court Clerk` is present in the pilot role vocabulary, but is assignable and usable only when the **server-side organization/deployment entitlement** `COURTLOG_PAID_FEATURES=court_clerk` is enabled. The server checks that entitlement during account creation, login, token refresh, and authenticated requests; the browser only reflects the safe `/api/config` result.

This configuration enables the Court Clerk feature. It does **not** charge, verify, or establish payment, a subscription, or a commercial entitlement. CourtLOG has no payment provider or billing integration. Do not treat manual environment provisioning as payment processing.

## Roles that are not assignable in this pilot

Only the pilot roles in the table are accepted by the account-creation and role-remapping APIs. **Cashier / Fees Clerk** has no first-pilot task; **Counsel** and **Counsel's Clerk** are post-pilot. Appellate Justice and Appellate Registry Clerk are also deferred by the current role vocabulary. They are not exposed as assignable browser options and are rejected by the API until separately approved and implemented.

## Legacy role handling

- An old **`Clerk`** role combined duties that cannot safely be inferred. On a deployed SQLite database, migration preserves the account ID, records `legacy_role=Clerk`, changes the role to **Role Assignment Required**, marks remapping as required, revokes existing sessions, and writes a migration audit event. Login is blocked until a Chief Registrar explicitly selects a pilot role and supplies an audit reason. Remapping revokes sessions again; the account is not automatically assigned Court Clerk access.
- Old **`DCR`** and **`Judge`** roles are migrated on deployed SQLite startup to **Deputy Chief Registrar** and **Presiding Judge**, respectively, preserving the account ID and revoking its existing sessions.
- The tracked local `data/courtlog.db` is deliberately not rewritten during startup. Its legacy Clerk is exposed to Chief Registrar as requiring assignment and remains unable to sign in. The tracked data fixture was not edited as part of this role change; review/migrate any other old local roles before relying on that fixture.

## Known implementation boundaries

- The user-management interface and server authorization cover the pilot account/workflow set above; they do not add Cashier/Fees Clerk, Counsel, or Counsel's Clerk workflows.
- `POST /api/cases/{id}/documents` stores descriptive metadata only (`storage_status=metadata_only`, no binary upload/storage implementation).
- The Court Clerk entitlement has no billing provider, purchase flow, payment verification, or subscription lifecycle.
- The prototype summaries and alert/risk fields are operational, PII-minimized outputs where specified—not official NJC/NCMS submissions, legal compliance certificates, or legal determinations.
- This matrix is based on the server routes and role checks in the current repository. Any role-task change beyond this approved pilot scope needs separate authorization and tests.

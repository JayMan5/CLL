# COURTLOG — Completion Plan and Approval Checklist

**Prepared:** 1 October 2026  
**Status:** APPROVED by the user on 1 October 2026; development is in progress.
**Basis:** `COURTLOG_FULL_AUDIT.md` (finding IDs below refer to that audit).

## 1. Confirmed dates and proposed delivery targets

| Milestone | Date | Required outcome |
|---|---|---|
| Pilot-ready candidate | **16 October 2026** | Secure, complete core workflows; automated tests passing; deployed staging build |
| Pilot rehearsal and release freeze | **17–20 October** | Real-browser/device checks, staff walkthrough, backup/restore rehearsal, fixes only |
| First pilot test | **21 October 2026** | Controlled trial with staff, documented observations and incident support |
| Pilot feedback implementation | **22–29 October** | Fix defects and usability problems; validate with participating staff |
| Showcase-ready candidate | **30 October** | Stable release, accurate pitch materials, repeatable demonstration |
| Showcase rehearsal and release freeze | **31 October–4 November** | Final QA, video/deck completion, offline demonstration fallback |
| Full competition showcase | **5 November 2026** | Demonstrate filing → custody → hearing → judgment → execution, plus defensible AI |

There are **20 days to the pilot and 35 days to the showcase** from this plan's date. These targets assume parallel technical, legal and stakeholder work. External approvals, real training data and Meta onboarding cannot be guaranteed by a coding schedule.

**Definition of completion:** a secure and tested pilot/showcase release with all four workflows working, truthful AI claims, operational documentation and submission materials. This is not automatically certification for unrestricted government production use. Production approval has additional gates in §5.

## 2. Task list — required before the pilot

Every task is initially unchecked. Proposed owners are responsibility areas, not assigned individuals. Dependencies should be completed before dependent tasks.

### A. Agree scope and resolve legal/operational decisions — 1–3 October

- [ ] **A1 — Approve this plan and name owners.** Confirm technical lead, frontend/backend/QA support, Law Lead and stakeholder/submission lead; agree the daily progress/review process.
- [ ] **A2 — Confirm pilot conditions.** Number of staff, roles, courts, devices, network, hosting, support contact, and whether the trial uses fictional/anonymised data or authorised live records. Default: fictional/anonymised data until live-data permission is documented.
- [ ] **A3 — Sign off hearing policy.** Law Lead/registry confirm criminal versus civil rules, per-party counts, date intervals, exception authority and whether the system alerts or blocks. Do not represent a DCR workflow as a statutory requirement without approval. *(L-01)*
- [ ] **A4 — Sign off execution rules and forms.** Confirm judgment/ruling distinction, enforcement eligibility, stays/appeals, applicable jurisdiction, required fields and the source of the 90-day operational threshold. Approve all four templates and label unissued output as draft. *(L-03–L-05)*
- [ ] **A5 — Choose infrastructure and notifications.** Use one supported database and deployment path; decide between approved 1:1 WhatsApp templates and eligible API-created groups. A visible simulator may be used as a declared fallback, not represented as real delivery. *(L-06, E-06)*

**Gate:** approved workflow specification and pilot data policy; unresolved legal questions remain visible, not silently encoded as law.

### B. Secure access, sessions and data — 2–6 October

- [ ] **B1 — Protect exposed endpoints.** Authentication and role checks for users, case detail/prediction, cron, message logs and simulator; strip password hashes from all responses. *(S-01)*
- [ ] **B2 — Enforce object-level permissions everywhere.** Court/division/judge/custodian scoping on reads, writes, alerts, predictions and exports; reject cross-scope operations. *(S-04, S-11)*
- [ ] **B3 — Remove XSS sinks.** Safe DOM rendering, event listeners instead of interpolated inline handlers, input constraints and a compatible CSP. Regression tests for malicious case IDs, scan fields and webhook data. *(S-02)*
- [x] **B4 — Repair session lifecycle.** Refresh/re-login handling, secure refresh-token storage, logout/revocation, user-disable checks and last-admin/self-delete safeguards. *(S-06)*
- [x] **B5 — Finish account management.** Unique IDs, username/password setup, validated roles and assignments, password change/reset, forced initial password change; UI driven by authenticated profile rather than demo identities. *(S-09, F-04)*
- [ ] **B6 — Remove unsafe defaults.** No pre-filled admin password; environment-driven bootstrap; explicit demo mode; role switcher and simulator unavailable in live mode. *(S-03)*
- [ ] **B7 — Harden requests and dependencies.** Rate limits, CORS allowlist, appropriate headers, validated dates/phones/lengths/path containment, dependency upgrades and removal of unused packages. Retest compatibility and triage scanner results. *(S-07–S-10, E-03)*
- [ ] **B8 — Record trustworthy actions.** Actor identity from authentication; actor/time/reason on hearings and overrides; append-only application audit events for edits, exports and administrative changes. *(S-05)*

**Gate:** unauthenticated requests denied, cross-scope requests denied, no hashes leaked, XSS regression tests pass, disabled/deleted users lose access, no unresolved critical security findings.

### C. Complete all four modules — 4–11 October

#### Module 1 — physical custody
- [ ] **C1 — Fix Sheriff visibility and onboarding.** Explicit file assignment/handover and authorised lookup so a Sheriff can receive an unscanned file without seeing unrelated cases. Use authenticated identity, not typed staff IDs. *(F-01)*
- [ ] **C2 — Implement genuine QR capture.** Local QR generation; camera and keyboard/USB-scanner input with manual fallback; verify payload and case access; print labels. Test on the pilot device. *(F-03, S-13)*
- [ ] **C3 — Complete missing/found workflow.** Separate idle and missing flags; resolve/recover action, reason and audit history; alerts survive sweeps until properly resolved. *(L-07)*

#### Module 2 — hearings and compliance
- [ ] **C4 — Implement the approved hearing policy.** Structured outcomes/reasons, per-party information where required, date limits, criminal/civil distinctions and scoped exception records. Enforce changes atomically. *(L-01)*
- [ ] **C5 — Separate alerts and clocks.** ML risk, custody, adjournment and enforcement states must not overwrite one another; durable escalation/acknowledgement; surface Judge hearing alerts in the UI. *(L-02, F-08)*
- [ ] **C6 — Complete notification handling.** Configurable adapter, correct recipients, persistent delivery/failure status, webhook verification where applicable, retries with duplicate protection, and honest UI messages. *(L-06)*

#### Module 3 — delay intelligence
- [ ] **C7 — Define a defensible prediction target and data provenance.** Separate historical records from simulated workflow data; remove circular feature-derived labels; document intended use and limits. *(M-01–M-03)*
- [ ] **C8 — Repair preprocessing and scoring.** Consistent court/type vocabulary, appropriate categorical encoding, explicit unknown handling, temporal features and completed-case exclusion; compare with a simple rules/baseline approach. *(M-04–M-06, L-09)*
- [ ] **C9 — Evaluate and package the model.** Leakage checks, independent hold-out evaluation, class-specific performance/PR metrics and calibration; reproducible training, model version/metadata and documented fallback. Real-world accuracy must not be claimed without real-world validation. *(M-09)*
- [ ] **C10 — Finish AI interface.** Model-derived explanations, pending-case ranking, model/fallback indicator and uncertainty/limitations. If predictive validity is not established, display it as experimental decision support, not a validated predictor. *(M-07–M-08)*

#### Module 4 — judgment and execution
- [ ] **C11 — Add a guarded lifecycle.** Separate interlocutory ruling from final judgment; prevent premature execution, duplicate judgments and accidental backward transitions; freeze relevant elapsed time at completion. *(L-03, L-09)*
- [ ] **C12 — Finish all four approved forms.** Correct Fi Fa, Garnishee, Possession and Delivery templates; structured parties, amounts, jurisdiction and dates; print/download; preview does not lodge an event. *(L-05)*
- [ ] **C13 — Close enforcement workflow.** Lodge/issue/service/return/completion actions, attachment of evidence and authenticated actor; overdue history retained after resolution. *(L-04)*

**Gate:** every authorised role can complete its workflow from the UI; denied operations remain denied; no stuck missing-file, override or execution state; all generated forms match approved templates.

### D. Complete shared product and engineering foundations — 7–14 October

- [ ] **D1 — Repair registration and demo data.** Defaults match the user's court; validate assignments; deterministic pending and concluded samples for every role; include low/moderate/high scenarios, missing/found files and overdue execution. *(D-01, F-02)*
- [ ] **D2 — Standardise data models.** Shared validated schema, migrations and consistent case defaults; keep the runtime DB, credentials and model binaries outside tracked source with reproducible provisioning. *(L-11, S-12)*
- [ ] **D3 — Implement actual document storage.** File type/size validation, scoped upload/download, safe storage paths, metadata and retention policy; malware controls proportionate to accepted formats. *(F-06, S-08)*
- [ ] **D4 — Correct reports.** Monthly/weekly filters, division scoping, minimised PII, transparent compliance definitions, CSV/PDF exports; do not equate model risk with proven non-compliance. *(L-08)*
- [ ] **D5 — Finish usability.** Reliable loading/error/empty states, correct error messages, search/filter behaviour, keyboard access, responsive screens and mobile-device tests; remove stale placeholders. *(F-05, F-07, F-09)*
- [ ] **D6 — Remove runtime CDN reliance.** Bundle/version frontend dependencies, generate QR locally and provide a documented offline demo fallback. *(S-13)*
- [ ] **D7 — Restore automated verification.** Rewrite JWT-aware tests with isolated databases; unit/integration/UI tests for permissions and complete workflows; date boundaries (7/24/90 days), exceptions, concurrency and notification failures. *(E-01)*
- [ ] **D8 — Add delivery tooling.** README, environment template, setup/train/seed/test commands, container/build configuration, dependency lock and CI tests/security scans; clean obsolete scripts and lock files. *(E-02–E-05)*
- [ ] **D9 — Deploy controlled staging.** HTTPS, secrets configuration, health checks, persistent storage, scheduled jobs, logs/monitoring, backups, tested restore and rollback procedure. Keep sensitive data out of logs.

**Gate:** clean checkout can be built and deployed from documentation; automated checks pass; staging supports real browsers and pilot devices; backup and rollback work.

### E. Pilot preparation — 12–20 October

- [ ] **E1 — Obtain required pilot permission.** Document authorisation, lawful basis/data minimisation, privacy notice, data access, retention and incident contacts before accepting real records.
- [ ] **E2 — Publish truthful pilot documentation.** Correct abstract/status/security/ML claims and archive obsolete self-assessments; release notes distinguish implemented, experimental and simulated features. *(Audit §5–§7)*
- [ ] **E3 — Prepare staff materials.** Role-specific quick guides, sample cases, scripted walkthroughs, a feedback form and issue triage process.
- [ ] **E4 — Conduct full rehearsal by 16 October.** Filing → handover → hearing/exception → judgment → approved form → service/return → execution → reports, across all roles.
- [ ] **E5 — Run acceptance checks on 17–20 October.** Permission/security tests, real-browser/device checks, network failure/restore tests and defect fixes. Freeze features; tag an approved release on the session branch.
- [ ] **E6 — Approve pilot go/no-go.** Record sign-off from technical, legal and pilot leads; unresolved critical/high security issues mean no live-data pilot. Use fictional data and declared simulations if external integration or approvals are not ready.

## 3. After the pilot — required before the showcase

### F. Pilot feedback and release hardening — 22–29 October
- [ ] **F1 — Capture and prioritise feedback.** Categorise security, correctness, usability and optional requests; agree which scope changes fit the deadline.
- [ ] **F2 — Fix pilot defects and retest.** Add regression tests for every material issue; validate fixes with staff.
- [ ] **F3 — Validate operations.** Agreed-volume load test, notification recovery, backups/restore, retention and deployment monitoring; review access and audit records.
- [ ] **F4 — Obtain independent review where feasible.** Security review and legal form/policy recheck; do not imply a formal penetration test or legal certification unless performed.
- [ ] **F5 — Confirm unresolved external dependencies.** Real data access, Meta approval and institutional permissions; document fallbacks and limitations.

### G. Finish competition deliverables — drafting from 8 October, final by 30 October
- [ ] **G1 — Complete Business Model Canvas.** Customer/beneficiary, partners, adoption channel, operating costs, pricing/funding and sustainability.
- [ ] **G2 — Finalise abstract and proposal.** Accurate capabilities, e-filing complement positioning, measured pilot outcomes and consented institutional references.
- [ ] **G3 — Finish deck.** Replace team placeholders; correct AI/database/WhatsApp/legal claims; add pilot observations, honest metrics, architecture and adoption plan.
- [ ] **G4 — Produce pitch video and demonstration script.** Follow competition format/length requirements; show all four modules; explain experimental AI and notification fallbacks plainly.
- [ ] **G5 — Verify submission requirements.** Confirm platform, deadline/timezone, file formats, team details, required permissions and upload confirmation. The showcase date is not assumed to be the submission deadline.

### H. Showcase acceptance and rehearsal — 30 October–4 November
- [ ] **H1 — Approve showcase release by 30 October.** End-to-end tests passing, no critical security/correctness defects and every promised feature demonstrated.
- [ ] **H2 — Rehearse on the actual presentation setup.** Named demo accounts, resettable data, camera/USB scanner, printable forms and realistic time budget.
- [ ] **H3 — Prepare failure fallback.** Local/offline build, pre-recorded walkthrough, backups and troubleshooting instructions; disclose simulation if used.
- [ ] **H4 — Freeze, back up and submit.** Fix blockers only during the final window; verify all submission files and release documentation.

## 4. Acceptance criteria: what “complete” means on showcase day

- [ ] Every role logs in securely, sees only authorised records and can perform its required work.
- [ ] A new case can be registered, assigned and scanned; missing files can be reported and resolved.
- [ ] Approved hearing/exception rules work with preserved actor/date/reason history and durable alerts.
- [ ] Notifications are either genuinely delivered with visible status or clearly identified as simulation.
- [ ] Delay intelligence is reproducible, evaluated honestly, explained and clearly marked experimental where required.
- [ ] Judgment and execution lifecycle closes from the interface; all four forms are legally reviewed drafts/issued outputs as appropriate.
- [ ] Documents and scoped reports can be uploaded/downloaded/exported securely.
- [ ] Automated tests and deployment checks pass; browser/device, restore and failure-recovery checks are documented.
- [ ] Staff/user/deployment documentation and all competition deliverables are finished and accurate.
- [ ] Known limitations, external dependencies and any deferred work are recorded with owners.

## 5. Separate production/government rollout gates

These may run in parallel but must not be promised as automatically finished by 5 November:

- [ ] NDPA applicability review, DPIA, DPO/controller responsibilities, NDPC obligations and any required NITDA clearance confirmed by qualified advisers.
- [ ] Written institutional deployment/data-sharing approval and retention/access policies.
- [ ] Independent security assessment, MFA for privileged users, incident response and disaster-recovery validation appropriate to actual deployment risk.
- [ ] Real-world ML validation using authorised registry/partner data, monitoring and human oversight before consequential reliance.
- [ ] Production availability/support commitments, infrastructure budget, integration approval and long-term maintenance ownership.

## 6. Approval record and continuing external decisions

The user approved development on **1 October 2026**. Work is underway on the fixed Arena session branch; the prior approval gate is closed. The pilot (21 October) and showcase (5 November) remain targets, not readiness claims.

Continue to track the non-developer decisions in A1–A5. Real court data remains out of scope until written permission and privacy safeguards exist; WhatsApp and scanner behaviour must be represented truthfully; legal rules/forms require Law Lead or institutional approval. No developer implementation substitutes for those sign-offs.

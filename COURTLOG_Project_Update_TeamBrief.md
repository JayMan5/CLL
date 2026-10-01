*COURTLOG — Project Update & Current Scope*

> **Status update — 1 October 2026:** This brief contains historical proposal assumptions, not current implementation or approval evidence. Use [`COURTLOG_COMPLETION_PLAN.md`](COURTLOG_COMPLETION_PLAN.md), [`DEVELOPMENT_PROGRESS.md`](DEVELOPMENT_PROGRESS.md), and [`README.md`](README.md) for current status. Demo messaging is simulated, the delay-risk data is synthetic and unvalidated, legal thresholds/forms are pending Law Lead approval, C2 phone/printer acceptance is pending, and any institutional-review/proposal assertions below must be reconfirmed from current written evidence before external use. Do not use real court data without documented permission.

# COURTLOG

## Project Update & Current Scope — Team Brief

*Internal working document — read before touching any submission material*

## 1. What Changed, and Why It Matters

Earlier project notes state that the Deputy Chief Registrar of the Federal High Court, Barrister Antonia Oyibo, reviewed the COURTLOG concept and gave feedback on framing and notices. This development pass did not verify that account or any current approval. Confirm documentary evidence before using the person's name or describing institutional endorsement in submission material; this brief is not a current approval record.

| Feedback Received | What It Means For Us |
| --- | --- |
| Earlier project notes describe ongoing e-filing and virtual-court work | Verify the current deployment scope with the institution. COURTLOG is intended to complement existing workflows, but no integration or coverage gap is established by this code review. |
| Earlier project notes say hearing notices use registrar-managed WhatsApp groups | This practice was not independently verified in this code review. The current demo path is a simulator and sends no real recipient notice. The documented WhatsApp Groups API does not join existing consumer groups; it is limited to API-created groups (max eight participants) for eligible Official Business Accounts. Do not claim integration or design around an unapproved existing group. |
| Earlier notes describe a formal proposal path to the Chief Registrar's office, subject to further approvals | The existence, submission status, and current approval path were not verified in this development pass. Confirm documentary evidence before citing the pathway; a proposal or review is not deployment approval or permission to use live data. |

## 2. Full Project Scope — Everything We're Building

This is the complete, current feature list. Every module below is in scope. This section exists so the team always has one authoritative reference for what COURTLOG is meant to achieve — refer back to this rather than to earlier chat discussion, since some assumptions (noted below) have changed since the original concept was drafted.

| Feature | What It Does | Current Adaptation / Status |
| --- | --- | --- |
| **1. Physical File Tracking (QR Chain of Custody)** | The prototype issues an opaque local QR label and records authenticated check-ins; its seven-day clock is an idle-custody prompt, not proof that a file is missing. | Code is present, but real phone/camera/printer acceptance is pending. No offline scan is queued; staging must use fictional records. |
| **2. Hearing Workflow** | Clerks can record hearing outcomes and a next date. The prototype currently has a configured case-level adjournment review trigger; it is not a statutory finding or per-party count. | Real notices are not delivered. WhatsApp remains an explicitly labelled demo simulation; any production integration requires approved recipient/channel design and onboarding. Hearing policy requires Law Lead sign-off. |
| **3. Experimental Delay-Risk Score** | A prototype score uses case type, court, recorded case-level adjournments, and elapsed days. | The 3,000-row training CSV is generated synthetic data with rule-generated labels; there is no independent real-outcome validation. Treat the score as decision support only, not a legal finding. |
| **4. Post-Judgment Workflow Prototype** | The UI tracks execution events and can produce draft document output; the 90-day prompt is an operational prototype threshold. | Applicable rules, forms, stays/appeals, and threshold require legal review. Generated output is not an issued court process. |

Together, these four workflow areas describe the intended scope, not a validated end-to-end service. Current code is a prototype: policy approval, legal forms, live messaging, actual-device acceptance, authorized data, independent model validation, and controlled deployment remain separate gates. Do not describe an operational or legally compliant end-to-end service until those gates are documented.

Honest flag for the team: building and convincingly demoing all four modules by the November finale is ambitious. This section states the full intended scope so nothing is forgotten or built inconsistently — it is not a claim that all four will necessarily be equally built out for the live demo. That build-priority decision should be made deliberately by the team once the CS side has scoped what is realistically achievable, not by quietly dropping a module.

The team is targeting COUCH 2026's Public Sector / e-Governance track. Any Best AI Innovation claim must describe the model as synthetic-data prototyping without independent validation. Institutional review/proposal/approval assertions remain unverified in this code review and require current written evidence before inclusion in a feasibility case.

## 3. Status of Submission Deliverables

| Deliverable | Status | What Still Needs to Happen |
| --- | --- | --- |
| **Abstract** | Draft exists; status language revised | Verify any institutional assertions from current written evidence; clearly label the prototype, synthetic-risk score, pending legal/device gates, and simulator-only messaging. |
| **Pitch deck** | Not started | Add/reframe a slide showing COURTLOG alongside E-filing, not competing with it. Feasibility slide should name the Chief Registrar/Chief Judge pathway. |
| **Business Model Canvas** | Not started | Validate partners/approvals before naming them. Select a permitted messaging channel only after recipient, provider, legal, privacy, and delivery requirements are approved. |
| **Pitch video** | Not started | Script should land the 'complement, not competitor' framing early, and mention the registrar review. |
| **Proposal to Chief Registrar** | Drafted, sending now | Not a COUCH requirement, but strengthens every other document once a response (or even proof of submission) is in hand. |

Do not use the historical day-count or submission status above. The current project plan targets the pilot for 21 October 2026 and the full competition showcase for 5 November 2026; reconfirm official submission deadlines and requirements with the competition dashboard.

## 4. Build Impact for the Tech/CS Team

Messaging is not an approved or implemented production integration. The current `whatsapp.py` flow is an explicitly labelled simulator for a disposable demo and does not deliver real notices. Before any build decision, the institution must approve the channel, recipient consent/opt-in, templates, provider, data-processing terms, delivery/failure handling, and operational support. The Meta Groups API must not be assumed to join an existing registry-managed group; current published constraints require an eligible Official Business Account and API-created groups with a maximum of eight participants. Keep the simulator clearly labelled until those dependencies are resolved.

## 5. Immediate Action Items

- Everyone: read this document before drafting or editing any submission material.
- Team lead: confirm exact submission deadline and file requirements on the team dashboard.
- Law lead: review the configured adjournment trigger, applicable execution policy/forms, and any intended messaging notices; provide written sign-off before policy changes.
- CS team: keep the simulator clearly labelled; do not implement live messaging or use real case data until channel/onboarding and data permissions are documented. Continue only with synthetic-data risk prototyping and report its limitations.
- Team lead: track any response from the Chief Registrar's office and circulate it immediately — it directly strengthens the feasibility section of every remaining deliverable.

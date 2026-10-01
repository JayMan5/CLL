*COURTLOG — Project Update & Current Scope*

# COURTLOG

## Project Update & Current Scope — Team Brief

*Internal working document — read before touching any submission material*

## 1. What Changed, and Why It Matters

The Deputy Chief Registrar of the Federal High Court, Barrister Antonia Oyibo, reviewed the COURTLOG concept and gave us three pieces of feedback that change how the project is framed and how part of it should be built. This document exists so every team member is working from the same current picture — nobody should be drafting abstract, deck, BMC, or video content from the older framing after reading this.

| Feedback Received | What It Means For Us |
| --- | --- |
| The Court is already deploying an E-filing system and virtual court administration alongside the analog process | COURTLOG must be positioned as a complement to E-filing, not a competing or duplicate system. E-filing handles document submission; COURTLOG handles physical file custody, adjournment compliance, and delay prediction — the parts E-filing does not cover. |
| Hearing notices are already sent via registrar-managed WhatsApp groups, not SMS | Every reference to SMS/Termii in our materials and build plan is replaced with WhatsApp integration. This is a real build decision, not just messaging — see Section 4. |
| Implementation requires a formal proposal to the Chief Registrar's office, subject to the Chief Judge's approval | This gives us a genuine, named institutional pathway to cite in our feasibility case — far stronger than 'we spoke to a registrar.' A formal proposal letter has been drafted and is going to the Chief Registrar's office. |

## 2. Full Project Scope — Everything We're Building

This is the complete, current feature list. Every module below is in scope. This section exists so the team always has one authoritative reference for what COURTLOG is meant to achieve — refer back to this rather than to earlier chat discussion, since some assumptions (noted below) have changed since the original concept was drafted.

| Feature | What It Does | Current Adaptation / Status |
| --- | --- | --- |
| **1. Physical File Tracking (QR Chain of Custody)** | Every case file carries a QR code, scanned at filing, registry, and courtroom checkpoints. Dashboard shows current location in real time and flags files unscanned for 7+ days. | Positioned as a complement to the ongoing E-filing rollout, not a competing system — it covers physical custody, which E-filing does not. |
| **2. Hearing Compliance Engine** | Clerk logs the outcome of each call-over in one tap (heard, adjourned, reason). Next hearing date is communicated to parties/counsel. | Notice delivery updated from SMS/Termii to WhatsApp, to integrate with the registry-managed WhatsApp groups already in use for hearing notices. |
| **3. Delay-Risk Model (Predictive Layer)** | A model trained on case type, court, number of prior adjournments, and time elapsed flags which pending matters are statistically likely to stall, before they do. | This is the core AI/data component that fits the COUCH 2026 theme and the Best AI Innovation Award. Still to be built — see Section 4 for the technical spec status. |
| **4. Execution Tracker (Post-Judgment Non-Compliance Tracking)** | Dashboard lists judgments awaiting execution, generates enforcement forms (Writ of Fi Fa, Garnishee) from the Judgment Enforcement Rules, and logs sheriff action with timestamps. Flags matters with no action after 90 days as non-compliant. | Back in full scope. This is the module that closes the loop from filing through to actual enforcement — without it, COURTLOG only addresses delay up to judgment, not compliance after it. |

Together, these four features cover the full life of a case file: filing and physical custody, hearing and adjournment compliance, predictive early-warning of delay, and post-judgment enforcement compliance. That end-to-end coverage — not any single module — is the actual pitch: COURTLOG follows a case from the moment it is filed to the moment a judgment is actually enforced, and flags non-compliance and delay risk at every stage along the way.

Honest flag for the team: building and convincingly demoing all four modules by the November finale is ambitious. This section states the full intended scope so nothing is forgotten or built inconsistently — it is not a claim that all four will necessarily be equally built out for the live demo. That build-priority decision should be made deliberately by the team once the CS side has scoped what is realistically achievable, not by quietly dropping a module.

Sector fit for COUCH 2026: Public Sector / e-governance, with the predictive layer also making the project eligible for the Best AI Innovation Award. The institutional relationship — Deputy Chief Registrar review, formal proposal now with the Chief Registrar's office, pending Chief Judge approval — is now a core part of the feasibility case, not a background detail.

## 3. Status of Submission Deliverables

| Deliverable | Status | What Still Needs to Happen |
| --- | --- | --- |
| **Abstract** | Draft exists, needs revision | Rewrite feasibility paragraph to cite registrar review + Chief Registrar proposal; swap SMS for WhatsApp throughout. |
| **Pitch deck** | Not started | Add/reframe a slide showing COURTLOG alongside E-filing, not competing with it. Feasibility slide should name the Chief Registrar/Chief Judge pathway. |
| **Business Model Canvas** | Not started | Key Partners: add Federal High Court registry/NJC explicitly. Channels: WhatsApp, not SMS gateway. |
| **Pitch video** | Not started | Script should land the 'complement, not competitor' framing early, and mention the registrar review. |
| **Proposal to Chief Registrar** | Drafted, sending now | Not a COUCH requirement, but strengthens every other document once a response (or even proof of submission) is in hand. |

Days remaining to submit: 13 as of the last confirmed count — reconfirm the exact number and the team dashboard's file requirements before finalising anything, since a few days have passed since that count was taken.

## 4. Build Impact for the Tech/CS Team

One concrete change to the technical spec already shared: replace all SMS/Termii references with WhatsApp Business API integration for the Hearing Compliance Engine's notice function. This is a build simplification, not just a wording change — it removes the per-message SMS cost, and integrates with a channel registry staff are already trained on rather than asking them to adopt a new one. All other elements of the technical specification (data schema, delay-risk model design, tech stack, architecture, privacy notes) are unchanged.

## 5. Immediate Action Items

- Everyone: read this document before drafting or editing any submission material.
- Team lead: confirm exact submission deadline and file requirements on the team dashboard.
- Law lead: revise the abstract with the E-filing/WhatsApp/Chief Registrar framing.
- CS team: update build plan to replace SMS/Termii with WhatsApp Business API; continue on the delay-risk model per the existing technical spec.
- Team lead: track any response from the Chief Registrar's office and circulate it immediately — it directly strengthens the feasibility section of every remaining deliverable.

# Pilot/Demo Feedback and Issue Triage Template

**Status:** draft workflow template. A pilot owner, submission channel, response-time commitment, and independent review have not been named. Until those are agreed, collect notes only through the team's approved competition-project channel and use fictional/demo scenarios. Do not collect real case content, party/staff names, telephone numbers, credentials, access tokens, or unredacted screenshots.

## Feedback form (copy one per observation)

- **Reference:** `FB-YYYYMMDD-NNN` (no case number or person name)
- **Date/time and timezone:**
- **Role used:** Sheriff / Clerk / Judge / DCR / Chief Registrar / Other
- **Build/commit and environment:** local demo / staging (identify URL privately, never include secrets)
- **Scenario reference:** one of the `DEMO/2026/001`–`DEMO/2026/008` fixtures, or “new fictional scenario”
- **What were you trying to do?**
- **What did you expect?**
- **What happened instead?**
- **Could you safely recover?** yes / no / not applicable
- **Impact:** security/privacy / case integrity / legal-policy concern / blocked workflow / usability / accessibility / performance / other
- **Reproduction steps:** fictional data only; include the smallest reliable sequence
- **Evidence:** sanitized text or a screenshot with all names, identifiers, phone numbers, and tokens removed
- **Suggested change (optional):**
- **Reporter/contact for follow-up:** store separately from the issue body if the tracker is shared

## Triage protocol (proposed; owner approval needed)

1. **Acknowledge and protect.** A named pilot/technical lead should acknowledge receipt, remove exposed personal data/secrets from shared channels, and preserve a restricted incident record if required. Do not paste sensitive details into GitHub issues or commit history.
2. **Classify before changing code.** Assign a category, severity, owner, due date, and reproducible fictional test case. A legal-policy concern is routed to the Law Lead; engineering must not change the rule while that decision is pending.
3. **Stop unsafe use.** Any credible cross-user data exposure, unauthorized write, lost/duplicated custody event, or incorrect legal prompt affecting a real workflow should block the affected pilot activity until reviewed. Escalate privacy/security incidents through the separately approved incident path.
4. **Fix with regression evidence.** Every material code change gets a regression test. Verify role scope, audit actor/history, failure handling, and synthetic-only test data where relevant.
5. **Review and close.** Record the decision, verification result, remaining risk, reviewer, and release/build containing the fix. Do not claim a pilot issue is fixed until the affected role can reproduce the expected result.

## Suggested severity vocabulary

- **Critical — stop use:** credible unauthorized access/change, sensitive-data exposure, irreversible corruption, or a workflow state that could cause an unsafe real-world action.
- **High — block affected workflow:** repeatable role/permission failure, lost/duplicated history, materially misleading status, or unavailable core task without a safe workaround.
- **Medium — workaround available:** non-critical behavior or usability defect that slows or confuses a fictional walkthrough.
- **Low — polish/request:** cosmetic issue or optional enhancement with no correctness, access, or privacy impact.

Severity is a triage aid, not a security certification. A technical owner, Law Lead, privacy/security adviser, and pilot lead still need to agree the actual thresholds, communication channel, and response times before any live-data pilot.

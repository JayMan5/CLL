# CourtLOG Prototype Walkthrough

> This guide replaces the old architecture/status walkthrough. The earlier description incorrectly claimed CDN use, a working Firestore connection, real-time custody tracking, and real WhatsApp delivery. See [`STATUS.md`](STATUS.md) for current code-verified scope and open acceptance gates.

## Purpose and boundary

CourtLOG is a competition-team prototype for exploring registry workflows. It is not a government entity, certified public-sector service, e-filing integration, or approved live-data deployment. Use only synthetic/demo data unless written permission explicitly authorizes a specific use. Legal thresholds/forms remain under Law Lead review; no rule is changed by this walkthrough.

## Start a disposable local walkthrough

1. Follow [README local setup](README.md#local-development-setup) and configure a **fresh** `.local/` database with `DEMO_MODE=true`, `COOKIE_SECURE=false`, and local JWT key paths. Keep the server local-only.
2. Seed the fixed fictional sample scenarios if desired:

   ```bash
   .venv/bin/python scripts/seed_demo_data.py
   ```

3. Start the API/frontend using the command in the README. Open the local URL on the same development computer.
4. Use one role at a time and sign out before switching accounts. The demo credentials are weak and must never be exposed to the public internet.

See [`docs/DEMO_SCENARIO_CATALOG.md`](docs/DEMO_SCENARIO_CATALOG.md) for the seeded records and [`docs/PILOT_ROLE_QUICK_GUIDE.md`](docs/PILOT_ROLE_QUICK_GUIDE.md) for role-specific instructions.

## Suggested scripted demo

1. **Clerk:** show the court-scoped list; register a fictional case in the assigned court; assign a Sheriff; log a fictional hearing event. Do not describe the existing case-level adjournment trigger as statutory or per-party law.
2. **Sheriff:** sign in as the assigned Sheriff; open the QR Custody area; demonstrate check-in with the local camera/USB/manual path only if available. Show server-confirmed event attribution. If the network is unavailable, reconnect and verify before retrying; there is no offline scan queue.
3. **Sheriff / Chief Registrar:** demonstrate a fictional missing-file report and explicit found resolution. Explain that the seven-day idle prompt and an open missing-file report are distinct.
4. **DCR:** open the scoped review queue; acknowledge a synthetic pending item. Explain that acknowledgement does not approve or unblock it, and that the elapsed-time escalation is in-app only.
5. **Judge:** review the assigned docket and, if needed, record a fictional ruling event. Explain that the prototype does not decide legal eligibility for execution.
6. **Chief Registrar:** demonstrate a fictional Judge assignment and the internal prototype summary. State that the export is not an official compliance report.
7. **AI and notifications:** show the experimental delay-risk explanation and the WhatsApp status panel. Identify synthetic data/fallback clearly; in demo mode no real WhatsApp message is sent.
8. **Close:** sign out, stop the server, and capture feedback with no real names, identifiers, phones, credentials, tokens, or personal data. Use [`docs/PILOT_FEEDBACK_AND_TRIAGE.md`](docs/PILOT_FEEDBACK_AND_TRIAGE.md).

This script is not evidence that a full rehearsal, staff acceptance, real-browser/device test, legal review, backup/restore, or pilot has been completed. Track those separately in [`COURTLOG_COMPLETION_PLAN.md`](COURTLOG_COMPLETION_PLAN.md).

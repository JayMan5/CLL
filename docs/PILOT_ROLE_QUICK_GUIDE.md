# CourtLOG Local Demo: Role Quick Guide

**Status:** local walkthrough material for the competition prototype; not staff training, legal guidance, pilot approval, or evidence of production readiness. Use only a disposable `DEMO_MODE=true` database and fictional records. Do not enter real case, party, contact, or staff information.

## Before you begin

1. Follow the isolated local-demo instructions in [`README.md`](../README.md). Never point the app at the tracked `data/courtlog.db`.
2. Optionally seed the fixed fictional scenarios with `python scripts/seed_demo_data.py --as-of YYYY-MM-DD`; see [`DEMO_SCENARIO_CATALOG.md`](DEMO_SCENARIO_CATALOG.md).
3. Keep the demo reachable only on the local development computer. The demo passwords are intentionally weak. Do not expose demo mode to the internet or use its accounts in staging.
4. Sign out before handing the computer to another role. The app may display prototype workflow prompts; verify any action before submitting it.

The local demo account names are `clerk`, `sheriff`, `judge`, `dcr`, and `cr`. The demo passwords are `123` for Clerk, Sheriff, Judge, and DCR, and `12345` for Chief Registrar. These credentials exist only for the isolated local demo; live mode does not enable them.

## Clerk — register, route, and log

- Open **Overview** and confirm the case list is scoped to the signed-in account's configured court.
- Use **Register Case** to create a clearly fictional case. Clerks may register only in their assigned court. New cases do not receive a hard-coded Judge or Sheriff assignment.
- From a case row, use **Custody** to assign an active Sheriff from that court and record the reason. A Sheriff handover is a separate action performed by the currently assigned Sheriff.
- Use the **Courtrooms** tab to record a hearing outcome and any required next date/reason. A Judge cannot record an adjournment. The existing case-level application review trigger is a prototype setting, not an approved legal rule or per-party statutory count.
- If the API rejects a request, stop and read the returned error; do not interpret it as a successful filing or hearing entry.

## Sheriff — check in and record custody

- Confirm that the case is assigned to the signed-in Sheriff. An assigned Sheriff can access the case before the first scan; a prior Sheriff loses access after a handover.
- Open **QR Custody / Check-In**. Use the local QR label/camera flow, a supported USB keyboard-wedge scanner, or the manual authorized-case fallback. The account session supplies the recorded actor.
- A green success state is shown only after the server confirms the saved event. If the network is unavailable, reconnect and verify the case history before trying again; scans are not queued offline.
- Use **Report Missing** only to record a fictional scenario that a file is missing. Resolve it only after the file is actually represented as found in the demo, using the explicit found action and location/reason. An idle-custody prompt is not proof that a file is missing.
- For a transfer, use **Hand Over**, select an active Sheriff in the same court, and record the handover details. Confirm the new assignment before the prior operator signs out.

Follow [`C2_PWA_SETUP_AND_USER_GUIDE.md`](../C2_PWA_SETUP_AND_USER_GUIDE.md) for installation/QR steps. Real phone, camera, printer, and USB-scanner acceptance is still open.

## Judge — review the assigned docket

- Open **Judge Docket** to review cases assigned to this Judge within the configured court.
- Use the ruling action only for the available `Ruling Delivered` or `Judgment Delivered` outcome. The application does not treat this as a legal determination that execution is permitted.
- A Judge cannot use the hearing form to log adjournments. Ask a Clerk to record the supported hearing event; do not share the Judge account.
- Use **AI Risk** only as experimental decision support. The score comes from synthetic rule-generated scenarios or a deterministic fallback and is not independently validated against real court outcomes. It must not determine a judicial action.

## Deputy Chief Registrar (DCR) — review the scoped queue

- Open **DCR Console** to see the cases in the account's configured division.
- For the synthetic pending-review example, record an acknowledgement note to demonstrate history. Acknowledgement does **not** approve, unblock, or change the case outcome.
- If demonstrating the separate override action, record a reason and say clearly that this is only the current application workflow. It is not a statutory DCR requirement or a legal ruling; A3 remains open for Law Lead/registry approval.
- An elapsed-time escalation is recorded in-app only. It sends no automatic WhatsApp, email, or other external notification.

## Chief Registrar — administer the fictional demo

- Use **User Admin** to inspect demo users and demonstrate the account controls. Do not add real staff identities or set real passwords in the demo.
- Use the case assignment controls to assign a Judge only after selecting a Judge whose court matches the case.
- The prototype summary is an internal demonstration export, not an official court/NJCS compliance report. Audit and message-log access is restricted to the Chief Registrar role.
- The **WhatsApp** screen reports configuration and consent state. In demo mode no real message can be sent. Never enter a real party phone number or claim delivery from a simulator event.

## End the walkthrough

- Sign out of the account, close the demo browser, and stop the local server.
- Keep or delete only the disposable synthetic database according to the team's reset procedure. Do not copy it into a pilot or public demo without review.
- Capture feedback without case details, phone numbers, credentials, tokens, or screenshots containing personal data. Use the separate [`pilot feedback and triage template`](PILOT_FEEDBACK_AND_TRIAGE.md).

## Acceptance boundary

This guide does not show that staff training, an end-to-end pilot rehearsal, browser/device testing, legal review, WhatsApp delivery, staging, backup/restore, or pilot permission has happened. Record those as separate acceptance tasks in [`COURTLOG_COMPLETION_PLAN.md`](../COURTLOG_COMPLETION_PLAN.md).

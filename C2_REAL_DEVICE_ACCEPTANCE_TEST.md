# C2 — Real-Device Acceptance Test Guide

**Purpose:** verify the installable Sheriff QR check-in on the actual pilot phone and printer before C2 is marked complete. This is a field acceptance test, not a legal-rule review or production certification.

**Current status:** C2 remains open until this procedure is run, results are recorded, and the pilot owner accepts them. Automated API and frontend tests do not replace the phone, camera, printer, and network checks below.

## 1. Safety and test boundaries

- Run against an **approved HTTPS staging deployment**, not production. The page, API, and static assets must be served from the same origin, at its root (`https://staging-host/`). The app's service worker is scoped to `/` and the camera requires a secure context.
- Do not open `http://localhost` on the phone: on the phone, `localhost` means the phone itself. A plain-HTTP desktop development server is not a real-device camera test.
- Use an isolated staging database and **fictional test case and user records only**. Do not use real court files, party/counsel contact details, or live credentials without documented permission. Do not create phone numbers by guessing; case setup in the UI requires valid contact numbers, so have the staging administrator provision the fictional test case if you do not have approved synthetic contact values.
- Use provisioned test accounts: a Clerk or Chief Registrar to issue a label, the Sheriff assigned to the test case, and (for the authorization-negative check) a different, unassigned Sheriff. Do not put passwords, QR payloads, or refresh/session tokens in the test sheet.
- The QR contains an opaque token rather than a case number, but it is still a physical link to a case in that environment. Keep test labels controlled, do not upload or send their images to online QR tools, and destroy unused/void paper labels securely. Issued test tokens remain in the staging database; there is no label-revocation control in the UI. Clean/reset staging only through its approved process.
- No offline scan is queued. A scan is successful **only** when the page says CourtLOG confirmed it and the expected scan event is visible in the case history.

## 2. Required people, equipment, and records

Have these ready before the run:

- The pilot phone, with its OS/browser updated to the version intended for the pilot. Use Safari on iPhone/iPad or Chrome on Android; record exact versions. Do not use an in-app browser opened from a messaging app.
- The intended printer and stock. A normal A4/plain-paper first print is useful for checking the output; the acceptance run must also use the printer/stock intended for the pilot. The print stylesheet lays out a roughly **76 mm square label** with a **58 mm square QR**.
- Reliable staging Wi-Fi/mobile data for the online checks, and a way to deliberately disconnect the phone for the offline/no-queue check.
- A fictional, staging-only test case in the same court as the test Sheriff. The case must have an explicit current Sheriff assignment. Record the case ID and assigned Sheriff user ID in the restricted test sheet.
- A registry account (Clerk/Chief Registrar) that can access the case and issue a QR label; an assigned Sheriff account; and, where available, an unassigned Sheriff account for the negative permission check.
- A removable test folder/card or other safe surface for the printed label. Do not attach a test label to a live court file.

## 3. Record the test run

Create one run record before testing. Record **only**:

| Field | Value |
|---|---|
| Test run ID and date/time (include timezone) | |
| Tester and witness, if any | |
| Staging origin (no credentials) and deployed code revision | |
| Phone make/model and OS version | |
| Browser name/version | |
| Printer model, driver, and stock | |
| Test case ID (fictional) and court | |
| Assigned Sheriff user ID; registry tester user ID | |
| Network used | |

Do **not** record user passwords, raw QR text, cookies/tokens, party details, or an unobscured photo of the QR. If screenshots are needed, capture only the status/history area and ensure no QR or personal data is visible.

## 4. Preflight: confirm deployment, account, and assignment

1. Confirm the staging operator has deployed the approved C2 build (the Sheriff QR PWA implementation on the session branch, or a later approved build) and recorded its revision. If the deployment builds assets itself, build `frontend/c2-pwa.bundle.js` from the matching source before deploying.
2. On a desktop on the same network, open the staging origin in a current browser. Confirm the login page loads without a certificate warning and the URL remains HTTPS at the site root.
3. Sign in as the test Clerk or Chief Registrar. Confirm the account is a staging account and has access to the fictional test case.
4. Confirm that the test case is explicitly assigned to the intended active Sheriff, whose court matches the case. If not, have the Clerk/Chief Registrar use the case row's Sheriff custody assignment action to assign that Sheriff; record the assignment reason in accordance with normal staging procedure. Do not proceed on the assumption that a previous scan or a label alone grants access.
5. Confirm the other test Sheriff (if used) is active but is **not** assigned to this case. Prefer a same-court unassigned test Sheriff for this check.

**Stop** if the site is not HTTPS, the database/environment is uncertain, a test account or case contains real data, or the case assignment cannot be verified.

## 5. Install and launch the PWA on the pilot phone

1. Connect the phone to the same reachable staging environment and open the exact HTTPS staging origin in the system browser (not a chat-app webview).
2. Sign in as the **assigned test Sheriff**. Complete any required first-login password change using the approved process; never write the temporary or new password in the run record.
3. Navigate to **Custody Check-In**. Confirm the page shows **Online — a check-in is recorded only after CourtLOG confirms it** (wording may vary slightly by build).
4. Install CourtLOG:
   - **Android/Chrome:** use the in-page **Install CourtLOG** button if it appears, or Chrome's menu → **Install app** / **Add to Home screen**.
   - **iPhone/iPad/Safari:** Share → **Add to Home Screen**, then open CourtLOG from the new Home Screen icon. Safari may not show the in-page install prompt; that is expected.
5. Confirm the installed app opens the same HTTPS origin and displays the CourtLOG sign-in/app screen. The first opening may require sign-in. Record whether it launches in the expected standalone/app presentation.
6. On the phone, keep the app online and signed in as the assigned Sheriff for the scanning steps.

If install is unavailable, record the browser/OS and the exact outcome. Do not mark PWA installation as passed just because the website opened in a browser tab.

## 6. Issue and physically print a test label

Use a desktop/tablet browser and the registry test account. Keep the phone available for scanning.

1. Sign in as the test **Clerk or Chief Registrar** on the same staging origin/database as the phone.
2. Open **Custody Check-In**. In the label panel, select the fictional test case from the authorised-case selector. Verify the displayed **Selected case** is the intended case before issuing.
3. Select **Generate local QR label**. Wait for the UI to say that the opaque label is ready and the QR was rendered locally. If generation fails, record the displayed error and stop; do not take a screenshot containing the QR.
4. Select **Print label**. In the print dialog, use the intended printer and an appropriate stock/scale. Avoid “fit to page” if it makes the code materially smaller; do not crop the quiet margin. For the first plain-paper check, measure that the label is about 76 mm square and the QR about 58 mm square. Record actual measured dimensions and print settings.
5. Inspect the physical output: QR is sharp, high contrast, complete, not folded/smudged, and has no readable case ID or party details printed next to it. Place it on the removable test folder/card.
6. Keep the label with the test record and within the controlled test area. Do not send it in email/chat or use a public QR-decoding website.

**Optional stale-selection guard check:** after issuing a label, change the selected case. The print button should be disabled and the status should require a new label for the new selection. If you run this check, treat the already-issued label as a live staging token: mark it VOID, destroy its print, and do not use it. Changing the UI selection does not revoke the server-side token.

## 7. Verify the assigned Sheriff camera scan

1. On the installed PWA on the phone, confirm the signed-in account is still the assigned Sheriff. Select the correct **Checkpoint location** (for example, `Registry Desk A`) before scanning.
2. Tap **Start camera**. Allow camera access when prompted. Confirm the live preview appears and the phone is using its rear/environment-facing camera where available.
3. Hold the printed label steady in normal indoor lighting at the usual hand-held working distance. Let the QR fit inside the frame; do not start with a screenshot of the label or a QR image displayed on the same phone.
4. After recognition, expect the camera to stop and a pending message while CourtLOG contacts the server. Wait for the final status. A decoded QR alone is **not** a successful check-in.
5. Pass this scan only if the app shows **Check-in confirmed by CourtLOG for the signed-in account** (or equivalent success status), with no error toast.
6. Confirm the selected case's custody history updates and the latest event shows the expected checkpoint, the assigned Sheriff account, and a server-recorded time. If it does not, do not rescan yet; inspect history first to avoid creating a duplicate event after a delayed response.
7. Repeat the online camera scan twice more, tapping **Start camera** each time (the camera stops after each decoded QR). Suggested practical reliability target: **3 of 3 first-attempt reads** under the agreed normal pilot lighting/distance, all confirmed with the correct actor and location. Agree the target with the pilot owner before the run and record the actual distance/time-to-read; this is an operational test criterion, not a legal rule.

## 8. Verify the authorization boundary

Run this before considering the QR flow accepted:

1. Sign out of the assigned Sheriff session and sign in as the active **unassigned test Sheriff**. Confirm the UI shows that account, not the former user's identity.
2. Open **Custody Check-In**, start the camera, and scan the same staging label once.
3. Expected result: CourtLOG does **not** confirm the check-in. The UI reports an authorization/assignment failure or otherwise says the scan was not confirmed. A visible camera read without server confirmation is not a pass.
4. Sign back in as the assigned Sheriff. Verify the case history has **no new scan event** attributed to the unassigned user. If an event appears, stop the test and report a security defect.
5. If a separate unassigned test account is not available, record this check as **Not Run** (not Pass); the automated API tests cover unassigned access, but do not substitute for the manual result in the field-test record.

## 9. Verify USB/manual fallbacks (if included in the pilot)

### USB/Bluetooth keyboard-wedge scanner

1. Connect the intended scanner to the pilot phone (including the real adapter/pairing method that will be used in the pilot).
2. Sign in as the assigned Sheriff and open **Custody Check-In**.
3. Focus **USB scanner / manual QR token**, scan the printed label, and submit using the scanner's configured Enter suffix or the on-screen **Submit scanned token** button.
4. Confirm the input clears and the UI reports success only after server confirmation. Verify the case history has the authenticated Sheriff and selected location. Do not copy the token into the report.
5. If a scanner is not part of the pilot kit, mark this subtest **N/A** and record that manual case selection is the fallback tested instead.

### Manual case-selection fallback

1. As the assigned Sheriff, select the authorised test case under **Manual case-selection fallback**.
2. Select the test checkpoint and tap **Record manual check-in**.
3. Confirm the server success status and a new case-history event with the signed-in actor, selected location, and timestamp. Record this as the manual fallback result; do not count it as a QR-camera pass.

## 10. Verify offline behavior and recovery

Run this while signed in as the assigned Sheriff, with the app page already open and the test label available.

1. Record the latest case-history event/time and current network status while online.
2. Disconnect the phone (airplane mode or turn off Wi-Fi and mobile data). Keep the app open. Confirm the network status changes to Offline. Do not close/reload the app before this scan attempt.
3. Start the camera and scan the test label once. Expected result: the app says it was **not submitted/not confirmed**, explains that scans are not queued, and never displays a success state. If the browser does not report itself offline, the request may instead end in a network-error/not-confirmed message; either way, there must be no success confirmation.
4. Reconnect the phone and wait for Online status. Refresh/reopen the case history from the server before retrying. Confirm the offline attempt did not add a scan event. If an event did appear (for example, connectivity dropped after the server accepted a request), record it and **do not retry blindly**.
5. Only after confirming no offline event was recorded, scan again while online. Confirm the normal server-success status and history event. This verifies recovery requires a new, deliberate online scan; there is no background replay.
6. Optional shell check: after the PWA has been installed/loaded online, close it and attempt to open the root page while offline. The service worker may show CourtLOG's offline page. It must not present an offline scan queue or claim that a scan was saved.

## 11. Pass/fail checklist

| Check | Pass condition | Result / notes |
|---|---|---|
| HTTPS and correct staging origin | Valid HTTPS; UI and API use same staging origin; no production data | |
| PWA installation | Installed from browser flow and launches on target phone | |
| Correct account and case assignment | Assigned active Sheriff and exact case/court match verified | |
| Label issuance | Registry user can issue a label for the selected authorized test case | |
| Printed label | Intended printer/stock used; complete, crisp, measured; no case details printed | |
| Camera capture | Camera permission/preview works; agreed first-read target achieved | |
| Server-confirmed check-in | Correct case history event with signed-in Sheriff, chosen location, and time | |
| Unassigned Sheriff denied | No success confirmation and no event attributed to unassigned account | |
| USB scanner (if included) | Tested and confirmed; otherwise marked N/A because the pilot kit has no scanner | |
| Manual case-selection fallback | Tested and confirmed as the built-in fallback | |
| Offline behavior | No success, no queued/replayed event; a new online scan works after reconnect | |
| Evidence and cleanup | No credentials/raw token/real data in evidence; test labels controlled/destroyed | |

| Sign-off field | Entry |
|---|---|
| Overall result | Pass / Fail / Blocked |
| Defects or follow-up IDs | |
| Tester | |
| Pilot owner/witness | |
| Date/time and sign-off | |

C2 may be checked complete only after required checks pass on the actual target phone and intended printer, failures are resolved and retested, and the completed record is reviewed. A blocked or unrun physical test leaves C2 open.

## 12. Troubleshooting guide

- **Camera says HTTPS/secure context is required:** check the browser address bar, certificate, and root staging origin. Do not use a phone-local `localhost` URL or a plain-HTTP LAN address.
- **No camera prompt or permission denied:** check both OS camera permission for the browser/PWA and that browser's site permission for the staging origin. Close other apps using the camera, reload, and retry. Record denied permission separately from a successful camera test.
- **No camera found/busy:** close other camera apps, restart the browser/PWA, and try again. If the target hardware has no supported camera, test the approved USB/manual fallback and record camera as failed—not passed.
- **Generate/print controls unavailable:** QR issuance is for Clerk/Chief Registrar; check the authenticated server profile and case scope. Sheriff's camera controls require a Sheriff account.
- **403 / assignment failure:** stop and ask the registry administrator to verify the current Sheriff assignment and exact court on the staging case. Do not repeatedly retry or change a live case assignment to force a pass.
- **“QR label is not recognized” / 404:** labels are database/environment-specific. Ensure the label was generated on this same staging origin and has not been replaced by a label from local development or another environment.
- **Camera reads but no confirmation:** wait, inspect case history, and confirm the network/account/assignment before retrying. Never treat the camera's decode message as a saved check-in.
- **QR will not scan from print:** check actual-size/scale settings, printer focus/toner, complete quiet border, glare, smudges, and that the code was not resized from a screenshot. Reissue only when necessary; mark and securely destroy unusable labels, remembering their server tokens remain in staging.
- **Install button is absent:** this can be browser-specific. Use Chrome's install menu on Android or Safari Share → Add to Home Screen on iOS. Record the browser and actual install outcome.

## 13. What this test does not certify

Passing C2 does not certify production readiness, security accreditation, legal compliance, printer fleet compatibility, or permission to use real court data. It verifies the specific staged build, phone/browser, printer/stock, accounts, and network conditions recorded in the run sheet. Repeat the relevant checks after material changes to those items.

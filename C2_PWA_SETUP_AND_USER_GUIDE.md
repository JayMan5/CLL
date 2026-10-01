# COURTLOG C2 PWA — Setup, Installation, and User Guide

**Last reviewed:** 1 October 2026
**Audience:** local developers, staging administrators, registry label issuers, and Sheriff test users.

> **Status and safety:** C2 is implemented in code, but real-device acceptance is still open. This is a prototype, not a production-certified court system. Use fictional test records in an isolated database. Do not use the tracked `data/courtlog.db`, real court records, real party contact details, or live credentials without written authorization. The detailed phone/printer acceptance run is in [`C2_REAL_DEVICE_ACCEPTANCE_TEST.md`](C2_REAL_DEVICE_ACCEPTANCE_TEST.md).

## 1. What the C2 PWA is

The C2 PWA is the responsive COURTLOG website installed from a supported mobile browser as a home-screen app. **It is not a native iOS/Android app and is not downloaded from an app store.** It uses the same website and API as the desktop version.

A successful QR check-in works as follows:

1. Registry staff issue a random, opaque QR token for an authorized case. The QR is drawn locally in the browser and contains no case number or case details.
2. The currently assigned Sheriff signs in on the phone, scans the label, and selects a checkpoint.
3. CourtLOG sends the token and checkpoint to the server. The server checks the signed-in account and current case assignment.
4. The screen confirms success only after the server returns the matching custody event.

The app needs a network connection for check-in. Its offline shell may show a fallback page, but **it does not save or queue scans while offline**. A QR decode, an open camera preview, or an offline attempt is not a recorded check-in.

## 2. Choose the right setup path

| Goal | Use this setup | Important limit |
|---|---|---|
| Build and explore the interface on your computer | Local development setup in §3 | Local demo is not a real-phone camera/install test. |
| Install the app and test it on the intended phone/printer | Approved HTTPS staging in §4–§7 | Use provisioned staging accounts and fictional data. C2 remains open until the acceptance run is recorded and accepted. |

For a real phone, the app must be served over a certificate-trusted **HTTPS origin**. The PWA manifest and service worker are scoped to `/`, so deploy COURTLOG at the root of its own hostname, for example `https://courtlog-staging.example/`, not under a path such as `/courtlog/`. Keep the page, API, and static files on the same origin.

Do not type `localhost` into the phone: there it refers to the phone itself. A desktop `http://127.0.0.1:8000` development run is for the development computer only. Use the approved HTTPS staging URL for mobile installation and camera acceptance.

## 3. Local development setup (computer only)

### 3.1 Install prerequisites

Install:

- Python 3.11 or later
- Node.js 22 or later, with npm
- Git

Open a terminal in the repository root (the directory containing `backend/`, `frontend/`, and `package.json`).

### 3.2 Install Python and frontend dependencies

**macOS/Linux:**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
npm run build:frontend
```

**Windows PowerShell:**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm ci
npm run build:frontend
```

The frontend build creates the local QR/PWA bundle, styles, chart bundle, and pinned local font/icon assets. Run it again after changing dependencies or frontend build inputs.

### 3.3 Configure a disposable local database and signing keys

Create a private local storage directory and copy the environment template:

**macOS/Linux:**

```bash
mkdir -p .local
cp .env.example .env
```

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force .local
Copy-Item .env.example .env
```

Edit `.env` and set paths to fresh files **inside this repository's ignored `.local/` directory**. Use absolute paths; replace `/absolute/path/to/CLL` with the actual checkout path.

```dotenv
DEMO_MODE=true
COOKIE_SECURE=false
COURTLOG_DB_PATH=/absolute/path/to/CLL/.local/c2-demo.sqlite
JWT_PRIVATE_KEY_PATH=/absolute/path/to/CLL/.local/c2-demo-private.pem
JWT_PUBLIC_KEY_PATH=/absolute/path/to/CLL/.local/c2-demo-public.pem
```

For Windows `.env` values, forward slashes are convenient, for example:

```dotenv
COURTLOG_DB_PATH=C:/work/CLL/.local/c2-demo.sqlite
JWT_PRIVATE_KEY_PATH=C:/work/CLL/.local/c2-demo-private.pem
JWT_PUBLIC_KEY_PATH=C:/work/CLL/.local/c2-demo-public.pem
```

Notes:

- `COOKIE_SECURE=false` is only for local plain-HTTP development. **Never use it in HTTPS staging or production.**
- The RSA key pair is generated automatically if the configured key files do not exist. Keep the private key private; do not commit `.env`, key files, or database files.
- A fresh `DEMO_MODE=true` database receives fictional demo **users** with intentionally weak, source-controlled demo credentials. Those credentials are only for an isolated local demo. They must never be exposed on a network, used in staging/production, or reused for real accounts. The username/password fixtures are in `SEED_USERS` in `backend/database.py`.
- Demo mode does not guarantee a fictional case has been created. Do not run `python -m backend.seed_db` for this walkthrough: that legacy script reads repository datasets that may contain real court records. Use a case that an administrator has provisioned in the isolated test database.
- The `.local/` directory is ignored by Git, but still protect it and clean it using your team's approved process after testing.

### 3.4 Start and open the local demo

From the repository root, start the server:

**macOS/Linux:**

```bash
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**Windows PowerShell:**

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

On the same computer, open `http://127.0.0.1:8000/`. Sign in with one of the local demo users from the isolated fixture, or use the non-demo bootstrap procedure in §3.5. Stop the server with **Ctrl+C**.

This local page is useful for learning the controls and testing with browser automation. It is not evidence that camera access, PWA installation, printing, network recovery, or device permissions work on the pilot phone.

### 3.5 Safer local account setup without demo users (optional)

For a local setup that does not use the weak demo accounts, leave `DEMO_MODE=false` and configure a one-time Chief Registrar bootstrap user in `.env` **before starting with a fresh database**:

```dotenv
DEMO_MODE=false
COOKIE_SECURE=false
COURTLOG_DB_PATH=/absolute/path/to/CLL/.local/c2-safe-demo.sqlite
JWT_PRIVATE_KEY_PATH=/absolute/path/to/CLL/.local/c2-safe-demo-private.pem
JWT_PUBLIC_KEY_PATH=/absolute/path/to/CLL/.local/c2-safe-demo-public.pem
COURTLOG_BOOTSTRAP_USERNAME=your-unique-local-admin
COURTLOG_BOOTSTRAP_PASSWORD=your-strong-temporary-password-at-least-12-characters
COURTLOG_BOOTSTRAP_NAME=Local Test Administrator
```

Keep the bootstrap password in `.env` only for this isolated local setup; do not commit or share it. On first sign-in, CourtLOG requires a password change. After that, use **User Management** to create the Clerk and Sheriff test accounts with strong temporary passwords and follow the first-login password-change prompt. Do not reuse these local credentials in staging.

## 4. Prepare HTTPS staging for a phone

A staging administrator should complete these checks before the phone is handed to a tester:

1. Deploy the approved build to a dedicated staging environment. Build local frontend assets with `npm ci` and `npm run build:frontend` before deployment.
2. Use HTTPS with a certificate trusted by the phone. Serve the app from the origin root and keep API and `/static/` assets same-origin.
3. Keep `DEMO_MODE=false`, `COOKIE_SECURE=true`, and use a dedicated staging database and protected signing keys. Do not use the tracked database or local demo credentials.
4. Provision separate Clerk/Chief Registrar and Sheriff test accounts through the approved staging process. The Sheriff must be active and explicitly assigned to the fictional test case. Create a second unassigned Sheriff account if testing the permission boundary.
5. Ensure a fictional test case exists in the same court as the assigned Sheriff. Case registration requires counsel and litigant phone fields. Use only administrator-approved synthetic/test contact values; do not guess numbers or use real contacts. Do not use the legacy seed script to obtain cases.
6. From a desktop browser, check the exact URL `https://<staging-host>/`. Confirm there is no certificate warning and the page stays at the origin root.
7. Confirm these resources load successfully from that same host:
   - `/service-worker.js`
   - `/static/manifest.webmanifest`
   - `/static/app.js`
   - `/static/c2-pwa.bundle.js`
   - `/static/tailwind.css`
   - `/static/chart.bundle.js`
8. Confirm the Clerk/Chief Registrar can see the case and that the current Sheriff assignment is saved. The issuer and phone must use the same staging origin/database.

If the staging host is untrusted, the app is under a subpath, the test data/account is uncertain, or the Sheriff assignment is unclear, stop and resolve that before installing or printing a label.

## 5. Install COURTLOG on the phone

Use the phone's system browser, not a link opened inside WhatsApp, email, or another app's embedded browser. Copy the exact HTTPS staging URL from the staging administrator.

### Android — Chrome

1. Connect to the approved staging network and open the staging URL in Chrome.
2. Check the address bar for HTTPS and confirm the CourtLOG login screen loads.
3. Install using either method:
   - If **Install CourtLOG** appears in the page, tap it and accept Chrome's prompt.
   - Otherwise, open Chrome's **⋮** menu and choose **Install app** or **Add to Home screen**. The exact wording depends on Chrome/device version.
4. Return to the Home screen/app launcher and open the new **COURTLOG** icon.
5. Confirm it opens the HTTPS staging site, then sign in with the provisioned test Sheriff account.

### iPhone or iPad — Safari

1. Connect to the approved staging network and open the staging URL in **Safari**. Do not use an in-app browser.
2. Tap Safari's **Share** button.
3. Choose **Add to Home Screen**. If the system offers an **Open as Web App** option, leave it enabled for the app-like launch.
4. Tap **Add**, then open the new **COURTLOG** icon from the Home Screen.
5. Confirm it opens the HTTPS staging site, then sign in with the provisioned test Sheriff account.

Safari may not show the in-page **Install CourtLOG** button; that is expected. Use Safari's Share menu. On Android, the in-page button is shown only when the browser supports and offers its install prompt; use the browser menu if it is absent.

### Confirm installation

- The icon opens the intended staging environment, not a local computer URL.
- The app launches in the browser's installed/standalone presentation where supported.
- The role and name shown in the header match the signed-in test Sheriff.
- Installation does not grant camera permission automatically; camera permission is requested separately in §7.

If the installed icon opens the wrong environment or a stale build, stop. Ask the staging administrator to verify the deployment/revision and update the service-worker shell. Do not enter a different host's credentials into the wrong installation.

## 6. Issue and print a test QR label (registry staff)

Do this on a desktop/tablet browser connected to the **same staging origin and database** as the phone.

1. Sign in with the provisioned **Clerk** or **Chief Registrar** account.
2. Open **Custody Check-In** from the left navigation.
3. In **Select an authorised case file**, choose the fictional test case. Confirm the selected case ID shown in the label panel is correct.
4. Tap **Generate local QR label**. Wait for the status **Opaque label ready**. The server issues the opaque token; the QR image is drawn locally in the browser.
5. Tap **Print label** and select the approved test printer. For the acceptance run, use the intended label stock/printer. The print layout is approximately **76 mm square** with a **58 mm square QR**. Avoid scaling/cropping that removes the white margin; inspect the print before use.
6. Confirm the paper QR is sharp, high-contrast, and readable. The label should not include the case number, party contact details, or other case information.
7. Keep the test label in a controlled area. Do not upload its image to a QR website or send it in chat/email.

Changing the selected case after generating a label disables printing until a new label is generated. That does **not** revoke the old server-side token; the UI has no token-revocation control. Mark an unused label void, destroy its paper securely, and do not assume the token itself was revoked.

## 7. Record a QR check-in (assigned Sheriff)

1. Open the installed COURTLOG app while online. Sign in as the **currently assigned Sheriff** for the test case. Complete the required first-login password change if prompted.
2. Open **Custody Check-In**. Confirm the page shows **Online — a check-in is recorded only after CourtLOG confirms it** (or equivalent wording).
3. In **Checkpoint location**, select the location that matches the test (for example, `Registry Desk A`). The authenticated operator is shown by the app; do not type another person's staff ID.
4. Tap **Start camera**. Approve the browser's camera permission. Use the rear/environment-facing camera where available.
5. Hold the printed QR label steady inside the camera frame in even light. Avoid glare, blur, folds, or a QR displayed on the same phone screen.
6. When the QR is read, the camera stops and the page reports that it is waiting for server authorization. **Wait for the final result.**
7. Pass only when the page says **Check-in confirmed by CourtLOG for the signed-in account** (or equivalent success wording) and the status is successful.
8. Verify the case's **Chain of Custody History** shows a new event with the expected checkpoint, authenticated Sheriff account, and server-recorded timestamp.
9. If there is a delay or error, check the history before attempting another scan. A request may have reached the server even if the phone did not receive the response; avoid creating a duplicate event.
10. When finished on a shared phone, use the profile menu → **Log Out**, then close the app and return the test label to controlled storage.

A camera decoding animation or “QR read” message alone is not confirmation. The event must appear in server-backed custody history.

## 8. Fallback methods

Use these only when the camera method is unavailable; identify the method in any test notes.

### USB/Bluetooth keyboard-wedge scanner

1. Sign in as the assigned Sheriff and open **Custody Check-In**.
2. Focus the **USB scanner / manual QR token** field.
3. Scan the physical label with the paired keyboard-wedge scanner. It enters the opaque token as text; the scanner does not itself authorize the check-in.
4. Confirm the correct checkpoint is selected and submit the token.
5. Wait for the CourtLOG confirmation and verify the custody history event as in §7.

Do not copy the raw token into a test log or message.

### Manual case-selection fallback

1. Sign in with an account authorized for the case.
2. In **Manual case-selection fallback**, choose the authorized case and select the checkpoint.
3. Tap **Record manual check-in** and wait for the server confirmation.
4. Verify the history event. This is a manual case check-in, not a QR scan; record it accurately.

The server still applies authentication and case-scope checks. A manual fallback does not bypass Sheriff assignment rules.

## 9. Offline behavior and recovery

- If the app says **Offline**, do not scan expecting a saved event. The app deliberately does not queue scans.
- If connectivity drops after you submit, do not assume success or failure. Reconnect, reload or reopen the app, and inspect the case's custody history first.
- Retry only if the expected event is absent and the assigned Sheriff/case/checkpoint are still correct.
- The cached offline page is informational only. It does not permit case lookup, label issuance, or check-in while offline.

## 10. Troubleshooting

| Symptom | What to check / do |
|---|---|
| Install option is missing on Android | Use Chrome (not an in-app browser), confirm HTTPS, open the browser menu, and choose **Install app** or **Add to Home screen** if available. The in-page button appears only when Chrome offers its install prompt. |
| No in-page install button on iPhone/iPad | Expected for Safari. Use **Share → Add to Home Screen**. |
| Phone says camera needs a secure page, or camera option fails immediately | Confirm the phone is on the trusted HTTPS staging hostname. `localhost` on the phone is not the development computer. Do not use the plain-HTTP desktop URL. |
| Camera permission was denied | Allow camera access for the staging site in the browser/OS settings, fully close and reopen the app, then retry. If permission cannot be granted, use a documented fallback. |
| Camera is busy or no rear camera is found | Close other apps using the camera; check browser permission and device hardware. Use the USB/manual fallback if needed. |
| QR is not recognized | Clean/reprint it, use good light, keep the white margin, reduce glare, hold it steady, and check print scale and physical size. Do not use a screenshot of the QR on the same phone. |
| “QR label is not recognized” | The token may belong to another database/environment or be invalid. Confirm label issuer and Sheriff are on the same staging origin/database; ask registry staff to issue a fresh controlled label. |
| “Only the currently assigned Sheriff…” / permission denied | Have a registry administrator verify that this exact active Sheriff account is currently assigned to the case and has the correct court scope. Signing in as another role does not bypass the check. |
| Check-in not confirmed or network error | Do not immediately rescan. Reconnect and inspect custody history first; then retry only if no event was recorded. |
| Label panel is unavailable | Sign in as Clerk or Chief Registrar and confirm the case is in that account's authorized scope. Sheriffs scan labels; they do not issue them. |
| App opens an old or wrong version | Confirm the hostname/revision with the staging administrator. Reload while online and reopen the installed app. Do not continue if the environment is uncertain. |

## 11. Updating, removing, and data handling

- After a staging release, open the app online and refresh/reopen it so the browser can check the service-worker shell for updated static assets. Ask the staging administrator to confirm the deployed revision; an icon alone does not identify the version.
- To remove the PWA, remove the Home Screen/app icon using the phone's normal system controls. Removing the icon does not remove server-side records, revoke issued labels, or replace the staging team's data-retention/reset process.
- Keep the phone screen locked when unattended. Log out on shared devices. Do not take photos of QR labels or screenshots containing tokens, case details, party details, or credentials.

## 12. Completion and acceptance

Use [`C2_REAL_DEVICE_ACCEPTANCE_TEST.md`](C2_REAL_DEVICE_ACCEPTANCE_TEST.md) to record the run and pass/fail results for the actual phone, browser, printer, stock, account assignment, and network. Record versions, environment and outcome—but **never** passwords, refresh/access tokens, raw QR text, or party contact details.

Passing this guide does not certify production readiness, legal compliance, a printer fleet, or authorization to use live court data. C2 can be marked accepted only after the intended device test is completed, results are recorded, and the pilot owner accepts them.

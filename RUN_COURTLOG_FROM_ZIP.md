# Run CourtLOG on your PC (from a ZIP)

**Updated:** 1 November 2026<br>
**Audience:** someone receiving a copy of this repository as a ZIP file.

This guide gets the CourtLOG prototype running as a **private, fictional-data demo on one computer**. It does not set up a court deployment or make the application production-ready. You do not need Git, Docker, a Meta/WhatsApp account, or any credentials from the person who sent you the ZIP.

> **Safety:** Run only with fictional demo data. Do not enter real case, party, staff, or contact details. The demo accounts have deliberately weak passwords and are public in the source; keep the app on your own computer and never expose it to the internet or a shared network.

## Before sending the ZIP (for the person preparing it)

- Do not include `.env`, `.local/`, `.venv/`, `node_modules/`, private/public signing keys, or any locally generated database, model, or credentials. A manual ZIP of a folder can include ignored files; `.gitignore` does not protect a hand-created archive.
- The repository contains a tracked `data/courtlog.db` and court-related data/training files. Verify you are authorised to redistribute every such file. The local demo steps below do **not** need them; exclude any file that is not approved for sharing. Do not open, train on, or evaluate on those files as part of this setup guide.
- Include `.env.example`, source files, and this guide. The recipient will create their own `.env`, virtual environment, and `.local/` demo database.

## What you need

- Windows, macOS, or Linux, with permission to install software and write to the folder where you extract the ZIP.
- **Python 3.11** (recommended; the project requires Python 3.11 or newer).
- **Node.js 22 or newer**; npm is included with Node.js.
- Internet access while Python and npm download the project dependencies the first time.
- A browser.

No `.env`, database, model, virtual environment, or `node_modules` folder is included in a normal source ZIP. You will create fresh local copies below. These belong on your own PC and should not be sent to anyone.

## Step 1 — Extract the ZIP

1. Extract the ZIP fully; do not try to run CourtLOG from inside the compressed-file preview.
2. Put the extracted project in a folder you can write to, for example `Documents/CourtLOG`.
3. Open that folder. The project root is the folder containing `README.md`, `requirements-dev.txt`, and `package.json`.

## Step 2 — Check Python and Node.js

Open **PowerShell** on Windows, or **Terminal** on macOS/Linux, and change directory to the project root. For example:

```text
cd path/to/the/extracted/project
```

Check the installed versions:

**Windows PowerShell**

```powershell
py -3.11 --version
node --version
npm --version
```

**macOS / Linux**

```bash
python3.11 --version
node --version
npm --version
```

If `python3.11` is not a command on macOS/Linux, try `python3 --version`; use it in the next steps only if it reports Python 3.11 or newer. On Windows, `py -3.11` uses the Python launcher. Install Python 3.11 if neither command is available. Install Node.js 22+ if `node` or `npm` is not found, then reopen the terminal.

## Step 3 — Create an isolated Python environment

Run these commands from the project root.

**Windows PowerShell**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

**macOS / Linux**

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
```

If you used `python3` instead of `python3.11` above, replace the first command accordingly. Keep using the `.venv` Python path shown for your operating system in the remaining steps. This avoids installing project packages into your computer's system-wide Python.

## Step 4 — Install and build the frontend

From the same project root, on **Windows, macOS, or Linux**, run:

```bash
npm ci
npm run build:frontend
```

`npm ci` installs the exact versions recorded in the lock file. The build creates the local frontend bundles used by the app. It may take a little while the first time.

## Step 5 — Configure a safe local demo

Create a local environment file and the private working folder. Do not skip the `.local` paths: they keep the demo database and signing keys separate from repository data.

**Windows PowerShell**

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force .local | Out-Null
notepad .env
```

**macOS / Linux**

```bash
cp .env.example .env
mkdir -p .local
```

Open `.env` in a text editor on macOS/Linux. In that file, edit the existing settings so they read as follows (uncomment the path settings if they begin with `#`; do not leave duplicate active entries):

```dotenv
DEMO_MODE=true
COOKIE_SECURE=false
WHATSAPP_ENABLED=false
COURTLOG_DB_PATH=.local/courtlog-demo.db
JWT_PRIVATE_KEY_PATH=.local/private.pem
JWT_PUBLIC_KEY_PATH=.local/public.pem
COURTLOG_DURATION_MODEL_DIR=.local/courtlog-synthetic-demo/duration-model
```

`COOKIE_SECURE=false` is only for this local plain-HTTP demo. `WHATSAPP_ENABLED=false` keeps live messages disabled. The database and keys must stay under `.local/`; do not change them to `data/courtlog.db` or to a database from another person. Save `.env` in the project root. The application creates fresh signing keys there the first time it starts.

## Step 6 — Optional: enable the synthetic duration estimate demo

Skip this step if you only want to open the application and try its ordinary demo workflows. To see the DCR **Experimental risk** list estimate fictional days until the next simulated progress event, generate and train the separate synthetic-only duration model. These commands use generated fictional rows and do not read the repository's court-data files.

**Windows PowerShell**

```powershell
.\.venv\Scripts\python.exe scripts\generate_synthetic_demo_data.py --cases 1500 --seed 20261014
.\.venv\Scripts\python.exe -m backend.train_duration_model --dataset .local/courtlog-synthetic-demo/no_progress_30d.csv --output-dir .local/courtlog-synthetic-demo/duration-model
```

**macOS / Linux**

```bash
.venv/bin/python scripts/generate_synthetic_demo_data.py --cases 1500 --seed 20261014
.venv/bin/python -m backend.train_duration_model --dataset .local/courtlog-synthetic-demo/no_progress_30d.csv --output-dir .local/courtlog-synthetic-demo/duration-model
```

The output stays under `.local/` and is not part of the ZIP. These estimates demonstrate software behavior only; they are not predictions about real courts or the total time until a case concludes.

## Step 7 — Add fictional demo cases

The application creates demo user accounts automatically in a fresh database when `DEMO_MODE=true`. Case examples are added separately. Run this once from the project root:

**Windows PowerShell**

```powershell
.\.venv\Scripts\python.exe scripts\seed_demo_data.py
```

**macOS / Linux**

```bash
.venv/bin/python scripts/seed_demo_data.py
```

It creates twelve fictional case records in the isolated `.local/courtlog-demo.db`: eight workflow examples and four duration-demo cases. It does not read CSV files or change the tracked `data/courtlog.db`. Do not run the legacy `seed_app_database.py`, `backend/seed_db.py`, or `build_dataset.py` for this setup.

## Step 8 — Start CourtLOG

Start the server from the project root so it finds `.env`.

**Windows PowerShell**

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**macOS / Linux**

```bash
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Wait until the terminal says Uvicorn is running. Leave this terminal open while you use the app.

## Step 9 — Open it and sign in

1. On the **same computer**, open <http://127.0.0.1:8000/> in a browser.
2. To open the DCR workspace, use **username** `dcr` and **password** `123`.
3. The optional duration estimates appear in **Experimental risk** after Step 6; refresh the scoped list if needed.
4. Other local demo accounts are listed in `docs/PILOT_ROLE_QUICK_GUIDE.md`. The Chief Registrar account is `cr` / `12345`.

These simple credentials are intentionally unsafe and only suitable for this isolated local demo. Never reuse them, publish the server, or expose port 8000 to another computer. A phone cannot use the PC's `127.0.0.1`; phone-camera acceptance requires a separate approved HTTPS setup.

## Step 10 — Stop or reset the demo

- Stop the server by returning to its terminal and pressing **Ctrl+C**.
- To reset only the demo cases, stop the server and remove `.local/courtlog-demo.db` plus any matching `courtlog-demo.db-wal` or `courtlog-demo.db-shm` files, then repeat Step 7. Leave `.local/private.pem` and `.local/public.pem` in place unless you intentionally want to invalidate local sessions as well.
- Never delete or overwrite `data/courtlog.db` as part of a reset. A completely fresh setup can instead use a new `.local/` database filename in `.env`.

## Troubleshooting

| Problem | What to check |
|---|---|
| `python`, `py`, or `python3.11` is not found | Install Python 3.11 and reopen the terminal. On Windows use `py -3.11`; on macOS/Linux use `python3.11` or `python3` if it reports version 3.11+. |
| `npm` or `node` is not found | Install Node.js 22+ (which includes npm), reopen the terminal, and check `node --version` and `npm --version`. |
| `ModuleNotFoundError` when starting the server | Run the install commands with the `.venv` Python from Step 3; make sure the terminal is in the project root. |
| Port 8000 is already in use | Stop the other process, or start CourtLOG with `--port 8001` and open <http://127.0.0.1:8001/> instead. |
| Login loops or protected pages return 401 | Confirm `COOKIE_SECURE=false`, use exactly `http://127.0.0.1:8000/` (not a different hostname), confirm `DEMO_MODE=true`, and restart the server after editing `.env`. If the database was previously used in another mode, set a new `.local` database filename and repeat Step 7. |
| No sample cases appear | Run Step 7 once, check that `COURTLOG_DB_PATH` points to `.local/courtlog-demo.db`, and restart the server. |
| Duration estimates are absent | The normal demo can run without the model. To enable duration estimates, complete Step 6, keep `COURTLOG_DURATION_MODEL_DIR` pointed at that output folder, restart the server, and refresh the DCR list. |
| Permission or write errors | Move the extracted folder to a location owned by your user account. Avoid protected system folders and network shares. |

## Optional: run the tests

From the project root, run the Python backend tests with the virtual environment's Python. The tests use isolated temporary databases.

**Windows PowerShell**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm run test:frontend
```

**macOS / Linux**

```bash
.venv/bin/python -m pytest -q
npm run test:frontend
```

## Important limitations

CourtLOG is a competition prototype, not an approved or production-ready court system. The duration model and other predictive examples use synthetic data only. The duration output estimates days to a simulated next-progress event; it is not a real-world court forecast or time-to-conclusion estimate. WhatsApp sending is disabled in this local demo, and offline custody scans are not queued or submitted. Follow the repository's `STATUS.md` and `README.md` for current implementation and acceptance limits.

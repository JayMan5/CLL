# COURTLOG Bug Fix — Task Tracker

## app.js Inline Fixes
- `[x]` Bug 3: Fix corrupted `toggleTheme()` — remove merged `changeActiveRole` code
- `[x]` Bug 4/10: Fix `renderExecutionTable()` to match both `"Delivered"` and `"Judgment Delivered"`
- `[x]` Bug 5: Fix `populateDropdowns()` to also populate `missing-case-id`
- `[x]` Bug 9: Fix chart categories to match actual seed data case types
- `[x]` Bug 6: Fix `generateWritForm()` to use `getAuthHeaders()`

## app.js Missing Code
- `[x]` Bug 1: Add global variable declarations
- `[x]` Bug 2: Add missing functions (USER_PROFILES, getActiveUser, getTheme, etc.)
- `[x]` Bug 8: Add DOMContentLoaded initialization + updateSimulationClock

## Backend
- `[x]` Bug 4: Fix `seed_db.py` — change `"Judgment Delivered"` → `"Delivered"`

## Frontend HTML
- `[x]` Bug 7: Fix default login username from `"dev"` to `"cr"`
- `[x]` Bug 12: Simulation clock updates dynamically via JS (element already had correct ID)

## Config
- `[x]` Bug 11: Add `*.pem` to `.gitignore`

## Verification
- `[ ]` Re-seed database with fixed status values — **do not run the legacy seeders or mutate `data/courtlog.db`**: tracked court/sample data is read-only and no real-record permission was supplied. A separate safe alternative now exists at `scripts/seed_demo_data.py`; it generates only synthetic cases in an isolated `.local/` database.
- `[ ]` Start server and verify in browser — backend/frontend automated tests and an isolated seed smoke test pass, but this legacy browser-check item is not complete until a human checks the running UI. Real phone/camera/printer acceptance remains separately open in `C2_REAL_DEVICE_ACCEPTANCE_TEST.md`.

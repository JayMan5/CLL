# Fictional Demo Scenario Catalog

The local-only generator [`scripts/seed_demo_data.py`](../scripts/seed_demo_data.py) creates the fixed eight scenarios below. It reads no CSV or tracked database; every title, identifier, contact, note, and event is invented. It writes only when `DEMO_MODE=true` and `COURTLOG_DB_PATH` is inside the ignored `.local/` directory. The case identifiers use the explicit `DEMO/` prefix and are not canonical court references.

Run after configuring a fresh disposable local database in `.env`:

```bash
.venv/bin/python scripts/seed_demo_data.py --as-of 2026-10-02
```

The default `--as-of` is the current UTC date. Supplying a date makes the fixture timestamps reproducible for a walkthrough. Existing non-demo records cause the tool to refuse the seed. Replacing existing fixtures requires the explicit `--overwrite-fixtures` option.

| Demo reference | Case type / division | State shown | Notes |
|---|---|---|---|
| `DEMO/2026/001` | Civil Debt / Civil | Pending, low synthetic risk, recent custody scan | Basic case and assigned-custody example. |
| `DEMO/2026/002` | Land Dispute / Civil | Pending, moderate synthetic risk, scan older than seven days | Demonstrates the configured idle-custody prompt; it does not mark the file missing. |
| `DEMO/2026/003` | Criminal / Criminal | Pending, high synthetic risk and a recorded adjournment | Score and event are illustrative only, not validated prediction or legal classification. |
| `DEMO/2026/004` | Family / Civil | Pending with an open missing-file report | Shows the separate report state and Sheriff attribution. |
| `DEMO/2026/005` | Admiralty / Civil | Pending with a resolved missing-file report | Shows fictional found/recovery history. |
| `DEMO/2026/006` | Intellectual Property / Civil | Pending with a DCR review state and elapsed-time escalation | Demonstrates the current in-app prototype state only; no external message is sent. |
| `DEMO/2026/007` | Civil Debt / Civil | Judgment delivered 100 days before the selected `--as-of` date | Demonstrates the configured 90-day prototype execution-review prompt, not a legal compliance finding. |
| `DEMO/2026/008` | Land Dispute / Civil | Execution workflow marked complete | Demonstrates a concluded record with a short, fictional execution history. |

The eight records now cover every case type available in the case-registration form: Criminal, Civil Debt, Land Dispute, Family, Admiralty, and Intellectual Property. Case division follows the current registration rule: Criminal cases are assigned to Criminal; the other listed types are assigned to Civil. All records remain in the fictional `FHC Abuja Court 4` court scope and are assigned to the demo Presiding Judge `usr_judge_01` and demo Sheriff `usr_sheriff_01`. Consequently, Criminal-division Filing Clerk, Registry Clerk, Bailiff, and entitled Court Clerk accounts see only the Criminal example; the assigned Sheriff, Deputy Chief Registrar, Registrar, Chief Judge, Chief Registrar, and assigned Presiding Judge see cases according to their broader court scope or explicit assignment. These assignments are fixtures, not advice about real court access control.

## Limitations

- Values for risk, event histories, parties, locations, and outcomes are synthetic. No realistic predictive, legal, or operational conclusion can be inferred.
- No party telephone numbers are added, so the fixture set cannot be used to send WhatsApp messages.
- The scenarios seed existing workflow states; they do not prove every transition can be completed end to end.
- Do not import or merge these records into a live or institutional database.

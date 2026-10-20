# Fictional Demo Scenario Catalog

The local-only generator [`scripts/seed_demo_data.py`](../scripts/seed_demo_data.py) creates eight workflow walkthroughs and four additional duration-demo examples. It reads no CSV, model dataset, or tracked database; every title, identifier, note, and event is invented. It writes only when `DEMO_MODE=true` and `COURTLOG_DB_PATH` is inside the ignored `.local/` directory. Neither identifier pattern is a canonical court reference.

Run after configuring a disposable local database in `.env`:

```bash
.venv/bin/python scripts/seed_demo_data.py --as-of 2026-10-02 --overwrite-fixtures
```

The default `--as-of` is the current UTC date; supplying a date makes fixture timestamps reproducible for a walkthrough. Existing non-demo records cause the tool to refuse the seed. `--overwrite-fixtures` refreshes the known seeded IDs; it is not a command to delete other or non-fixture records.

## Workflow walkthroughs

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

These eight records cover the workflow case types Criminal, Civil Debt, Land Dispute, Family, Admiralty, and Intellectual Property. Case division follows the current registration rule: Criminal cases are assigned to Criminal; the other listed types are assigned to Civil.

## New duration-demo examples

| Demo reference | Fictional case type | Adjournments | Days since filing at seed | Days since last simulated progress event at seed | Model-only synthetic court |
|---|---|---:|---:|---:|---|
| `SYNTHETIC-DURATION-DEMO/2026/001` | Fictional Civil Claim | 0 | 120 | 12 | Synthetic Court A |
| `SYNTHETIC-DURATION-DEMO/2026/002` | Fictional Land Matter | 2 | 420 | 70 | Synthetic Court B |
| `SYNTHETIC-DURATION-DEMO/2026/003` | Fictional Criminal Appeal | 5 | 900 | 240 | Synthetic Court C |
| `SYNTHETIC-DURATION-DEMO/2026/004` | Fictional Commercial Appeal | 9 | 1,500 | 800 | Synthetic Court D |

All four are pending, marked `demo_fixture` and `duration_demo_fixture`, and have `data_provenance="synthetic_demo"`. Their application `court` field stays within the fictional DCR scope, `FHC Abuja Court 4`; the duration model receives only the separate synthetic court category shown above. It receives the approved features—adjournment count, filing age, age of last qualifying progress event, fictional case type, and that synthetic category—never case IDs, titles, or party data. The result is recomputed whenever the DCR Experimental risk list is refreshed and is not saved.

In demo mode, the Experimental risk **Scoped Cases** list includes only these four marked duration examples, keeping the older workflow examples out of that list while leaving them available in other workflow screens. If the local duration artifact passes its provenance/target metadata checks, the batch refresh auto-estimates the four; if not, the rows can still appear but no duration estimate is produced. No real or untagged case is sent to the duration model, and outside demo mode the duration model is not invoked.

All twelve records remain in the fictional `FHC Abuja Court 4` scope and are assigned to the demo Presiding Judge `usr_judge_01` and demo Sheriff `usr_sheriff_01`. Consequently, the Criminal-division Filing Clerk, Registry Clerk, Bailiff, and entitled Court Clerk accounts see only the Criminal workflow example and the fictional Criminal Appeal duration example; broader roles see cases according to their existing scope or explicit assignment. These assignments are fixtures, not advice about real court access control.

## Limitations

- The duration model estimates fictional days until a simulated next `Heard`/`Adjourned` event or judgment delivery—not time to case conclusion, a legal deadline, or a real-court forecast.
- Values for risk, event histories, parties, locations, and outcomes are synthetic. No realistic predictive, legal, or operational conclusion can be inferred.
- No party telephone numbers are added, so the fixture set cannot be used to send WhatsApp messages.
- The scenarios seed existing workflow states; they do not prove every transition can be completed end to end.
- Do not import or merge these records into a live or institutional database.

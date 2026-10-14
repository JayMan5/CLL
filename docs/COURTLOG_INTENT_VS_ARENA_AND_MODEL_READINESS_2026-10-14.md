# CourtLOG: original intent vs. Arena implementation, and prediction-model readiness

**Review date:** 14 October 2026  
**Main-branch snapshot reviewed:** `origin/main` at `c60b55e20c444fa90107f737d890e4261a352934`  
**Arena branch:** `arena/01a0f82f-cll` (follow-up to the earlier review and strict time-split fix committed as `029ef16`; this update adds the user-delegated synthetic-only 30-day demo model).

## Executive conclusion

CourtLOG's underlying purpose is clear: improve visibility of physical case-file custody, hearing/adjournment workflow, delay warning, and post-judgment execution, alongside—not instead of—electronic filing. The Arena branch preserves that purpose and its current abstract/status documents are substantially more candid about what is and is not implemented.

The Arena branch is **not yet a complete implementation of the full functionality described by the original main-branch materials**. It is a security-hardened competition prototype with working slices across the four headings, but real-device acceptance, live messaging, legal workflow approval, several stages of the proposed court lifecycle, and institutional integration are not established. “The code has a screen/route” is not the same as “the workflow is accepted or operational.”

The delay predictor is **not a validated court-delay model**. After the team delegated the remaining demo defaults, an optional Logistic Regression artifact was trained only on reproducible fictional data under ignored `.local/`; it is loaded only in disposable `DEMO_MODE=true`. The demo target is no recorded `Heard`/`Adjourned` hearing or judgment delivery in the next 30 days; QR scans and internal/admin changes do not count. This is an operational software-demo definition, not a legal deadline or real court outcome. The artifact is not tracked or present in the normal `data/` location; without an explicitly configured demo artifact, the app uses its deterministic heuristic. No model was trained or evaluated on the tracked court-data CSVs, and no real-world validity is established.

## Scope and source documents

I read the main-branch `COURTLOG_Abstract.md`, `COURTLOG_Project_Update_TeamBrief.md`, the 7-stage workflow outline, pitch deck, system/overview documents, data-availability assessment, data-integration update, and historical gap analysis. I compared these with the Arena abstract/team brief, `STATUS.md`, `COURTLOG_COMPLETION_PLAN.md`, role/access matrix, C2 acceptance material, model trainer/inference code, tests, and ML-readiness note.

**Data-use note:** I inspected source code and `data/dataset_metadata.json` only. I did not open rows from `real_scn_cases_sample.csv`, `scn_appeal_cases_data.csv`, or the legacy training CSV; I did not run the legacy dataset builder or train/evaluate on those files. No real case data was used in this review.

## What the original materials intended

The main-branch abstract and team brief describe four connected goals:

1. **Physical file custody:** identify and scan the paper file at registry/court checkpoints and flag long-idle files.
2. **Hearing workflow:** record call-over outcomes, adjournment reasons and next dates; notify parties/counsel using WhatsApp rather than the earlier SMS idea.
3. **Delay-risk warning:** use case type, court and case history to identify cases likely to stall, early enough for staff to review.
4. **Post-judgment execution:** record writ issuance and Sheriff actions, and bring unresolved enforcement activity to attention.

The abstract frames CourtLOG as complementary to e-filing. The more detailed workflow document expands that into a proposed seven-stage lifecycle, including filing and e-filing references, service per defendant, cause-list/call-over details, final addresses and judgment/CTC dates, execution, and appeal-record transit. It explicitly describes a design to be tested, not an approved court procedure.

The older architecture documents describe a FastAPI/SPA application, WhatsApp integration, QR tracking, a machine-learning risk score, and—in some versions—Firestore with a local fallback. They are not consistent with each other on model algorithm or current implementation status.

## Important contradictions in the main-branch source set

These documents cannot all be treated as verified technical evidence:

- `docs/CourtLOG_Data_Integration_Update.docx` claims 66 real cases were integrated and a delay model reached **98% accuracy** after training on 3,000 generated cases. That is a claim in a document, not a reproducible validation result in the repository.
- `docs/Nigerian_Court_Data_Availability.docx` says no public case-level delay dataset with the necessary features was found; it says the 4,696-case Supreme Court appeal data has no delay features and that the proposed synthetic data is for prototyping only. It identifies obtaining raw case-level data from Citizens' Gavel or a court partner as a future action. This conflicts with the data-integration document's implication that the needed real delay outcomes were already available.
- The pitch deck describes **Logistic Regression**; `docs/CourtLOG_Overview.docx` says **Random Forest**; the main-branch trainer is Logistic Regression. The algorithm claim should not be copied from the older overview without correction.
- The main-branch `backend/train_model.py` automatically reads the generated CSV, derives `stalled` from `delay_risk == "High"`, ordinal-encodes categories, and uses a random row split. That measures how well the model recovers synthetic rule-generated labels; it does not validate prediction of future real case outcomes. The dataset metadata reports 2,828 High labels out of 3,000 (94.3%); a trivial always-High classifier would already score about 94.3% accuracy on that label distribution. The claimed 98% cannot establish real-world predictive performance.
- `docs/COURTLOG_Gap_Analysis.docx` is a historical July snapshot that calls all four modules complete, describes a Firebase/Firestore abstraction, and refers to a third-party QR service. Those statements are not a current assessment of the Arena branch.

Accordingly, the original abstract is useful for understanding the *problem and intended direction*, but the historical data-integration, system-overview, and gap-analysis documents should not be used as proof of the current model, integrations, or completion level.

## Arena branch compared with intended functionality

| Area | Original intention | Arena implementation and evidence | Assessment |
|---|---|---|---|
| Purpose and positioning | Follow administrative work from paper-file custody through execution; complement e-filing. | Current Arena abstract and brief call this a prototype, qualify the complement positioning, and avoid claiming an integration or institutional approval that was not verified. | **Aligned in purpose; accurately qualified.** |
| Architecture | FastAPI/SPA and, in some main-branch materials, Firestore plus a local fallback. | FastAPI and a local SPA are present; the application database is SQLite with JSON case records. No Firestore/JSON dual-store or NCMS/e-filing integration is present. | **Partial.** A lean prototype exists, but it differs from the pitch architecture and has no demonstrated court-system integration. |
| QR custody | QR identity scanned at filing/registry/court; show current custody and idle-file prompts. | Opaque, server-resolved tokens, role/assignment checks, local QR/PWA support and online check-in are implemented. The PWA does not queue offline scans. The documented actual-phone/camera/printer acceptance has not been completed. | **Code slice present; field acceptance open.** The seven-day state is an idle-custody prompt, not proof a file is missing. |
| Hearing workflow | Record outcomes/reasons and next date; original materials describe a fifth-adjournment legal block. | Hearing events and a separate DCR review workflow exist. The configured trigger is case-level at four recorded adjournments; it is not a verified per-party legal count or approved statutory decision. | **Partial; policy deliberately unresolved.** Do not describe it as legal compliance. |
| WhatsApp | Original brief proposes WhatsApp notices, referencing existing registry groups. | A consent-gated individual-template Cloud API path, persistent status, signed webhook and opt-out handling exist. A Registrar separately requests a notice; demo mode sends nothing; live delivery has not been tested. It is not an integration with existing consumer WhatsApp groups. | **Adapter code present; provider/channel acceptance open.** |
| Delay prediction | Early warning from case type, court and case history. The workflow outline also mentions adjournment reasons, service status and time since last event. | The optional local demo uses a reproducible synthetic-only Logistic Regression pipeline and a clearly labeled 30-day no-recorded-progress target. Its features include case type, court, adjournments, filing age and days since the last qualifying hearing/judgment event. It is loaded only in disposable demo mode; otherwise the runtime uses a disclosed heuristic. | **Not a validated court predictor.** The training labels and holdout outcomes are invented for software testing; no court outcome has been used. |
| Execution | Record writ issuance, Sheriff action/return and overdue activity; original materials name 90 days. | Registrar/Sheriff workflow slices and draft document output exist. The 90-day value is an operational prototype prompt; legal rules/forms and complete lifecycle acceptance remain open. | **Partial prototype, not an approved enforcement system.** |
| Full lifecycle | Seven-stage outline includes fee/e-filing links, per-defendant service and returns, cause-list details, final-address/CTC events, and appeal-record transit. | The pilot code does not implement all of those detailed stages; the current role guide explicitly notes service/affidavit and other workflow gaps. | **Not a complete implementation of the broad workflow outline.** |
| Roles and security | Older documents show a five-role hierarchy and make broad security claims. | Arena implements a richer pilot-role model, current-profile authorization, object scoping, explicit legacy-Clerk remapping and security regressions. | **Substantially strengthened in code**, but not an independent security review or staff acceptance. |

### Bottom-line answer on accuracy

The Arena branch is an **accurate, more cautious description of the prototype it currently is**, and its core product direction matches the original problem statement. It is **not an accurate basis for repeating the old claims of a complete end-to-end service, real WhatsApp delivery, a deployed Firestore architecture, legally approved workflows, or a real-data AI model**. The current Arena `COURTLOG_Abstract.md` is safer and more faithful to code than the original main-branch abstract, but external claims about institutional review/proposal still need the written evidence called for in that abstract.

## Prediction-model technical assessment

### Main-branch implementation

The old trainer has no explicit data-provenance or permission boundary, manufactures a binary label from the generated `delay_risk` category, treats nominal case/court categories as ordinal numbers, and randomly splits rows rather than keeping cases or future periods separate. `build_dataset.py` reads the two tracked source CSVs to calculate distributions/durations and creates `delay_risk` from rules using the same elapsed-time/adjournment/case-type information later fed to the model. Thus the old model is primarily learning a synthetic rule—not an observed future court outcome. Running that old pipeline would not satisfy “actually works.”

### Arena-branch improvements

The Arena trainer now requires an explicit dataset, binary target and provenance; rejects the known mixed legacy CSV being called synthetic; fits imputation/scaling/one-hot encoding inside the model pipeline; excludes case ID from features; evaluates against a prior baseline with ROC-AUC, average precision, Brier score and threshold metrics; and records model provenance/target metadata. The synthetic demo generator is deterministic and reads no repository case data. The demo target is no qualifying hearing-log `Heard`/`Adjourned` event or judgment delivery in the next 30 days; inference calculates event recency from those hearing/judgment records, not QR scans or internal/admin changes. Synthetic artifacts are blocked outside demo mode. The API reports whether an estimate came from `synthetic_demo_pipeline`, another trained pipeline, legacy artifact or heuristic.

One remaining safety gap: the top-level `build_dataset.py` is unchanged in Arena and still reads the tracked real-derived source CSVs when invoked; it has no documented-permission guard and creates rule-generated labels. I did not run it. Do not run it or use its output until data permission is documented—and even then, those generated labels are not observed future outcomes and cannot validate the predictor.

During this review I also corrected the grouped timestamp holdout: it now holds out cases first observed at/after the cutoff, keeps training cases wholly before it, and excludes case histories that cross the boundary. A fictional regression fixture verifies disjoint case IDs and strict train-before-test dates. This is an **evaluation-code improvement**, not a trained model or evidence of accuracy on court data.

### Why a valid real-court predictor is not available yet

- No artifact trained on court outcomes is tracked or present at the repository's standard `data/` path. The optional synthetic model and dataset are generated under ignored `.local/`, not tracked. Without a configured model, the app uses its deterministic fallback: `0.10 + 0.12 × adjournment_count + 0.0005 × days_since_filing` (plus a fixed case-type adjustment for one label), capped to a range. Those constants are not fitted or calibrated probabilities.
- The real-world outcome and horizon remain unapproved. For the software demo only, the delegated default is a 30-day window with no recorded `Heard`/`Adjourned` hearing or judgment delivery; QR and internal/admin activity are excluded. This is not an approved legal or court-performance measure. A high-risk category, four adjournments, a delay to judgment, and no new event over a future window remain distinct targets and must not be interchanged.
- The tracked training CSV is rule-labeled and calibrated from real-derived distributions with unresolved permission. The repository's data-availability note says the 4,696 appeal data does not provide the necessary delay outcomes. The 66-case sample and other source files do not, on current documented evidence, provide the permissioned longitudinal snapshots and future labels required for a prospective predictor.
- The demo feature set now includes event recency, but actual outcome records, an approved real-world target/horizon and a data dictionary are still required before selecting real rows, resolving censoring, preventing leakage, or interpreting a real-case probability.

## Safe next design for a model that can be tested honestly

For the software demonstration, the delegated default has now been fixed at: **at each snapshot, predict whether no `Heard`/`Adjourned` hearing-log event or judgment delivery is recorded in the next 30 days**. This avoids silently turning the existing four-adjournment or 90-day prompts into law. It is trained/evaluated on generated fiction only. Before a domain model can be fitted, the team still needs a real-world target approved by the appropriate Law/operations owners and a permitted, de-identified dataset. Alternatively, predicting time-to-judgment would require a survival/time-to-event approach that handles pending cases as right-censored; the legal/operations owner must define that outcome and cohort.

The data contract should contain a pseudonymous case-group ID, snapshot timestamp, only features known at that snapshot (case type/court, prior hearing/adjournment history, service state if available, days since filing/last event), and the observed future outcome plus follow-up/censoring information. It should exclude party names, suit numbers, contact details and any fields recorded only after the prediction time. Evaluation should use a locked future period and case-level separation, compare against a prevalence and simple-rule baseline, and report class prevalence, precision/recall, PR-AUC, Brier/calibration and uncertainty—not accuracy alone. Any operational use should begin in shadow mode with human review; the score must not decide hearings, custody, enforcement or judicial outcomes.

## Work completed in this review and remaining gate

- Compared the main-branch source documents with Arena code/status and recorded where the original claims are supported, partial, contradictory or unverified.
- Hardened the grouped time-split implementation; added a deterministic synthetic data generator, explicit 30-day target/provenance metadata, event-recency inference, UI disclosures, and regression tests. Full local backend suite: **88 passed** with 10 SciPy L-BFGS deprecation warnings; frontend regression suite passed. A reproducible 1,500-row synthetic holdout (seed `20261014`) reported ROC AUC 0.745 and average precision 0.736, compared with a 0.495 prior-baseline average precision; these are generator-specific software checks only. Data/model stay under ignored `.local/`. No repository case-data CSV was read and no real-court outcome artifact was produced.
- **To proceed to an actual domain model, the team must confirm:** (1) the intended outcome and forecast horizon, and who approves it; (2) whether written permission exists for the specific de-identified, timestamped case data and where it can be provided securely; and (3) whether pending/censored cases and existing active cases are in the supplied data.

Until those inputs are supplied, the accurate status is: **a reproducible synthetic demo model/pipeline is available; prediction of actual court outcomes has not been trained or validated; the normal runtime remains heuristic unless the disposable demo artifact is explicitly configured.**
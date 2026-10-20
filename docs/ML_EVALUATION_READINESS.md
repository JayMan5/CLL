# Delay-risk and duration-model evaluation: readiness and scope

**Updated:** 20 October 2026<br>
**Status:** a reproducible **synthetic 30-day classifier** and a separate **synthetic duration-regression experiment** are available; predictive validity for real court outcomes remains **not established**.

## Selected 30-day demo target

The demo predicts whether **no qualifying progress is recorded in the 30 days after a case snapshot**:

- Positive label (`no_recorded_progress_30d = 1`): neither a hearing-log event with outcome `Heard` or `Adjourned` nor a judgment delivery is simulated during the following 30 days.
- Negative label (`0`): at least one of those events is simulated in the 30-day window.
- QR scans and internal/administrative changes do not count as progress.

This is a clearly labeled operational software-demo definition, not a legal deadline, legal rule, approved court-performance measure, or label observed from court records. The generator uses invented features and a fictional waiting-time process; it reads no repository case-data rows, application database, or external outcome data. The user selected synthetic/demo-only data and delegated unresolved model defaults; this 30-day horizon is the chosen demo default. It does not settle the outcome/horizon that would be suitable for real court use.

## Data-use boundary

The repository contains a legacy training file, `data/courtlog_delay_dataset.csv`, whose metadata describes synthetic delay features calibrated from real-derived court distributions. The top-level legacy `build_dataset.py` still reads `data/real_scn_cases_sample.csv` and `data/scn_appeal_cases_data.csv` if invoked; it has no permission-reference gate and emits rule-generated labels. Do not run that builder without documented data permission, and do not treat its output as observed outcomes. Permission to use those sources for this project has not been established. **This model work did not open those CSV rows, run the legacy builder, or train/evaluate on those files.**

The reproducible demo generator is `scripts/generate_synthetic_demo_data.py`. Its default 1,500 fictional rows include both `no_recorded_progress_30d` and `synthetic_days_to_next_progress`; rows and their provenance/codebook sidecar are written beneath ignored `.local/courtlog-synthetic-demo/`. The binary classifier artifact and the separate regression artifact plus metadata are also kept there and are not committed. The fixed random seed makes these software demonstrations reproducible. The application artifact loader permits the binary `synthetic_demo` model only when `DEMO_MODE=true`; the duration artifact is available only through its separate fictional-input endpoint/form in local demo mode and is never applied to application case records.

## Features and inference behavior

The versioned Logistic Regression pipeline uses case type, court, recorded case-level adjournment count, filing age, and `days_since_last_event`. Numeric imputation/scaling and categorical imputation/one-hot encoding are fitted inside the scikit-learn pipeline; unseen categories are ignored safely.

At inference, `days_since_last_event` is derived from the latest qualifying date in the case's recorded hearing log (`Heard` or `Adjourned`) or `judgment_delivery_at`. QR scans and unrelated/internal administration are ignored. If no qualifying event exists, an explicitly supplied historical snapshot value is used; otherwise filing age is the fallback. The batch prediction response includes this feature value for the explanation view.

Predictions report `synthetic_demo_pipeline` only when a provenance-checked synthetic artifact is loaded **and** its target-column name and full target-definition metadata match this exact 30-day demo contract. Other synthetic artifacts receive a generic `synthetic_pipeline` source and do not inherit this target explanation. Without an artifact, the app uses its existing deterministic heuristic and reports `heuristic`; a heuristic score is **not** a trained or validated 30-day probability. Legacy and other pipeline sources are also labelled separately.

## Training and evaluation safeguards

- The trainer requires an explicit CSV path, binary `0/1` target, and provenance (`synthetic_demo` or `permissioned_real`). An optional plain-language target definition is stored with the artifact. It never derives the target from a risk category.
- Case IDs are group metadata, never a feature. The demo uses a forward-time holdout of later-starting case cohorts: cases first observed at/after the timestamp cutoff form the test partition, cases ending before it train the model, and any case history crossing the cutoff is excluded. Case groups are disjoint and test timestamps are later than training timestamps.
- Evaluation reports held-out ROC AUC, average precision, Brier score, precision/recall and confusion matrix at the existing 0.70 prototype threshold, along with a prior baseline. That threshold was not changed or validated.
- A reported split on this generated dataset is a software-pipeline check only. It does not measure performance on real cases, cases already active before a cutoff, or future court activity.
- Permissioned real-data training still requires a documented permission reference, case-level grouping, forward-time evaluation, approved target/horizon, data-protection review and an independently reviewed data contract.

## Separate synthetic duration experiment

A companion experiment in `backend/train_duration_model.py` estimates **fictional days from `snapshot_at` until the next simulated qualifying progress event**. In this generator, a qualifying event is a `Heard`/`Adjourned` hearing-log event or judgment delivery. This target is deliberately distinct from the binary 30-day no-progress classifier and from total time to judgment/case conclusion. The duration is generated by an invented exponential waiting-time process; it is not an observed or legally meaningful court duration.

The 66-row sample was considered only as a **schema/template reference**, not as training data. Generated rows use invented `SYNTHETIC-DEMO-*` identifiers for case grouping; no real IDs, titles, risk labels, `Year Decided`, or `Years to Conclusion` values are copied. `case_id` and `snapshot_at` are split metadata, not predictors. The fixed predictors are `adjournment_count`, `days_since_filing`, `days_since_last_event`, `case_type`, and `court`; the first three are numeric and the categories are one-hot encoded. The dataset also keeps the original 30-day target so the existing classifier contract is unchanged.

The duration trainer requires the generator-produced metadata sidecar to identify `synthetic_demo` provenance and the exact target definition, and refuses a non-synthetic provenance or alternate target. It keeps each case group wholly in a train or test cohort and holds out later-starting cases. It reports mean absolute error (MAE), median absolute error, RMSE and R-squared against a training-median `DummyRegressor` baseline. It fits a final model on all synthetic rows after the holdout evaluation. In local `DEMO_MODE=true`, the Deputy Chief Registrar's Experimental Risk workspace offers a fictional-input form and automatically estimates only the four explicitly tagged duration-demo fixtures in the scoped-case list. The duration artifact receives only its approved five features—not IDs, case titles, actual court values, or party data—and estimates are recalculated on refresh rather than persisted. Neither form nor list integration estimates duration for actual case records or supports operational deployment.

On 20 October 2026, the default 1,500-row dataset (seed `20261014`) produced a 1,199/301 train/test split at `2025-12-04T00:00:00Z`, with disjoint case groups and no crossing groups. On the held-out fictional rows, the Random Forest regressor achieved MAE **38.49 days**, median absolute error **26.99 days**, RMSE **54.51 days**, and R-squared **0.144**. The median baseline achieved MAE **39.90 days**, median absolute error **23.51 days**, RMSE **62.97 days**, and R-squared **-0.143**. The improvement over that simple baseline is modest and says nothing about actual courts; the broad errors reflect the arbitrary synthetic process and its long-tailed durations. These numbers are software smoke-test metrics only.

Reproduce the separate regression run after generating the shared fictional dataset:

```bash
.venv/bin/python -m backend.train_duration_model \
  --dataset .local/courtlog-synthetic-demo/no_progress_30d.csv \
  --output-dir .local/courtlog-synthetic-demo/duration-model
```

The target is fully observed/uncensored by construction. A real duration model must define an approved endpoint (for example, next recorded progress versus case conclusion), use documented permissioned longitudinal data, and handle unresolved cases as right-censored observations through an appropriate time-to-event design. Do not reuse `Years to Conclusion` from the 66-row sample without specific permission and a separate approved target design; it is neither the existing binary target nor evidence of model generalization.

### Reproduce the synthetic demo

```bash
.venv/bin/python scripts/generate_synthetic_demo_data.py --cases 1500 --seed 20261014
.venv/bin/python -m backend.train_model \
  --dataset .local/courtlog-synthetic-demo/no_progress_30d.csv \
  --target-column no_recorded_progress_30d \
  --target-definition "1 when neither a Heard/Adjourned hearing-log event nor a judgment delivery is simulated within 30 days after snapshot_at; 0 when one is simulated in that window. QR scans and internal/admin changes are not progress. This is a fictional software-demo outcome, not a legal deadline or a court-derived label." \
  --data-provenance synthetic_demo \
  --group-column case_id \
  --time-column snapshot_at \
  --output-dir .local/courtlog-synthetic-demo/model
```

### One reproducible generated-data holdout (14 October 2026)

This is **not predictive-accuracy evidence for actual court cases**. For 1,500 generated snapshots (seed `20261014`), the 1,199-row training cohort ended before the held-out 301-row case cohort, whose first snapshot was `2025-12-04T00:00:00Z`; no case crossed the boundary. On those fictional rows, ROC AUC was **0.745**, average precision **0.736**, and Brier score **0.207**. The prior baseline had average precision **0.495** and Brier score **0.250**. At the existing 0.70 threshold, recall was **0.235** and precision **0.833**. These values mostly describe recovery of the generator's invented waiting-time mechanism. They must not be quoted as model performance on courts or used to justify the threshold.

The local artifact loader/inference smoke check loaded the generated model only with demo mode enabled, confirmed the `synthetic_demo` provenance and target metadata, derived event recency from fictional hearing records, and returned source `synthetic_demo_pipeline`. The sample score was a synthetic fixture result, not a court prediction.

## Remaining evidence required before any real predictive use

1. A Law/operations-approved, measurable real-world outcome and horizon. The synthetic 30-day definition above does not constitute that approval; do not infer or change legal rules to create labels.
2. Written permission for the exact records and a data-protection review. Do not use real case/party records until that permission is documented.
3. A versioned data dictionary and provenance trail; pseudonymous case grouping; only fields known at prediction time; a leakage and censoring review.
4. A locked future-period evaluation on permitted observed outcomes, with case-level separation, simple operational baselines, class-specific precision/recall, PR performance, calibration, uncertainty and subgroup review where sample sizes permit.
5. Prospective shadow-mode monitoring, drift/error review, human oversight, rollback, and a clear display of score source and limitations.

A high score on rule-generated synthetic rows is only a software smoke test. No model can be guaranteed to work “perfectly.” Scores must not decide hearings, custody, enforcement or judicial outcomes.

## Verification performed

The demo-specific backend tests verify deterministic fictional generation, both targets, the exact target definitions, strict future case-cohort evaluation, artifact provenance, unseen categories, recency derivation and exclusion of QR/admin events. Seven dedicated duration-model tests cover target consistency, disjoint forward case/time holdout, censoring disclosure, baseline metrics, nonnegative prediction, synthetic-provenance enforcement and artifact metadata. Additional API/UI tests enforce demo-mode and Deputy Chief Registrar restrictions, validate the artifact metadata and fictional input categories, reject case IDs, and verify the UI submits only synthetic features without persistence. The generated dataset and both trained artifacts remain under ignored `.local/`; repository case-data rows and the legacy builder were not used. Run the full backend and frontend checks listed in `README.md` before relying on this code change.

# Delay-risk model evaluation: readiness and scope

**Reviewed:** 3 October 2026  
**Status:** software pipeline improved and synthetic-only tests pass; predictive validity is **not established**.

## Data-use boundary

The repository contains a legacy training file, `data/courtlog_delay_dataset.csv`, whose metadata describes synthetic delay features calibrated from real-derived court distributions. The seed script also references court-record/SCN-distribution files. Permission to use those sources for this project has not been established. **This review did not train or evaluate on those files.** The training command no longer selects a default dataset, so running it cannot silently consume the legacy file.

Until specific written permission is recorded, use only fully fictional data generated for software tests. No real case record, identifier, label, or distribution was used in the synthetic pipeline tests below.

## What changed in the training/inference path

- Replaced `LabelEncoder` ordinal values for `case_type` and `court` with a scikit-learn `Pipeline`: numeric imputation/scaling and categorical imputation/one-hot encoding with `handle_unknown="ignore"`. The preprocessing is fitted on the training partition, not the full dataset.
- The trainer now requires an explicit CSV path, target column, and provenance (`synthetic_demo` or `permissioned_real`). It accepts an observed binary `0/1` target; it no longer derives a target from the generated `delay_risk == High` category.
- Case IDs are grouping metadata, never a model feature. The default holdout uses stratified, case-grouped folds; an optional snapshot-time split holds out later case cohorts. Permissioned real-data training requires a permission reference and a forward-time column.
- Evaluation reports held-out ROC AUC, average precision, Brier score, precision/recall and a confusion matrix at the existing 0.70 display threshold, plus a prior baseline. The threshold was not changed or validated by this work.
- Optional model artifacts carry a format version, data-provenance label, training timestamp, feature/target schema, threshold and evaluation summary, but not the CSV path or case rows. `COURTLOG_MODEL_DIR` controls the protected artifact directory. A `synthetic_demo` artifact is rejected outside `DEMO_MODE`; unverified legacy artifacts are demo-only; a purported real-data artifact must include permission and forward-time evaluation metadata.
- Predictions identify their source (`trained_pipeline`, `legacy_model`, `heuristic`, or `heuristic_after_model_error`). If a loaded model errors, the app reports the deterministic fallback source instead of silently substituting a plausible-looking 0.50 score.

Example only for a future **authorized** dataset—do not run until permission is documented and the data contract is reviewed:

```sh
.venv/bin/python -m backend.train_model \
  --dataset /secure/path/permissioned_snapshots.csv \
  --target-column observed_future_outcome \
  --data-provenance permissioned_real \
  --permission-reference INTERNAL-APPROVAL-REFERENCE \
  --time-column snapshot_at \
  --group-column case_id \
  --output-dir /secure/path/model-artifacts
```

For synthetic software checks only, the test suite creates fictional rows in memory and verifies grouped/time splitting, unknown-category handling, artifact metadata, source reporting and metric calculation. The resulting metrics are intentionally not presented as evidence of court-delay prediction accuracy.

## Remaining evidence required for reliability claims

1. A Law/operations-approved, measurable prediction target and horizon (for example, an observed administrative outcome after a specified snapshot date). Do not infer or alter a legal rule to create a label.
2. Written permission for the specific training/validation records and a data-protection review. No real records are included in this evaluation.
3. A versioned data dictionary and provenance trail; remove direct identifiers and exclude fields only known after the prediction time.
4. A locked forward-time holdout, case-level leakage audit, comparison with simple operational baselines, class-specific precision/recall, PR performance, calibration, confidence intervals, and subgroup review where sample size permits.
5. Prospective shadow-mode monitoring, drift/error review, human oversight, rollback, and a clear display of estimate source and limitations.

A high score on rule-generated synthetic rows is only a software smoke test. No model can be guaranteed to work “perfectly,” and these scores must not decide hearings, custody, enforcement, or judicial outcomes.

## Verification performed

```text
.venv/bin/python -m pytest tests/test_model_training.py backend/test_api.py tests/test_security.py -q
72 passed
```

These tests use isolated databases and fictional in-memory/temporary rows. They do not load the repository's legacy training CSV, court sample files, or tracked application database.

"""Train and evaluate a delay-risk pipeline from an explicitly selected dataset.

This module deliberately has no default data path: the legacy tracked training CSV
contains real-derived court distributions and must not be used without permission.
For permitted real data, supply a documented permission reference and a snapshot-time
column so evaluation is forward-looking. Synthetic-only runs verify the software
pipeline; they do not establish real-world predictive performance.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LEGACY_MIXED_DATASET_PATH = DATA_DIR / "courtlog_delay_dataset.csv"
MODEL_DIR = Path(os.getenv("COURTLOG_MODEL_DIR", str(DATA_DIR)))
MODEL_PATH = MODEL_DIR / "delay_model.joblib"
MODEL_METADATA_PATH = MODEL_DIR / "delay_model_metadata.json"

NUMERIC_FEATURES = ["adjournment_count", "days_since_filing"]
CATEGORICAL_FEATURES = ["case_type", "court"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
DEFAULT_GROUP_COLUMN = "case_id"
EXISTING_FLAG_THRESHOLD = 0.70
MODEL_FORMAT_VERSION = 2


def build_pipeline() -> Pipeline:
    """Build preprocessing inside the estimator so encoders fit on training folds only."""
    numeric = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    categorical = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    preprocessing = ColumnTransformer([
        ("numeric", numeric, NUMERIC_FEATURES),
        ("categorical", categorical, CATEGORICAL_FEATURES),
    ])
    return Pipeline([
        ("preprocessing", preprocessing),
        ("classifier", LogisticRegression(max_iter=2000, random_state=42)),
    ])


def _normalise_target(values: pd.Series, target_column: str) -> pd.Series:
    target = pd.to_numeric(values, errors="coerce")
    if target.isna().any() or not set(target.unique()).issubset({0, 1}):
        raise ValueError(f"Target '{target_column}' must contain only observed binary 0/1 labels")
    target = target.astype(int)
    if target.nunique() != 2:
        raise ValueError(f"Target '{target_column}' must contain both classes")
    return target


def _split_indices(
    frame: pd.DataFrame,
    target: pd.Series,
    *,
    group_column: Optional[str],
    time_column: Optional[str],
    test_size: float,
    random_state: int,
) -> tuple[np.ndarray, np.ndarray, Optional[str]]:
    """Hold out whole cases; when timestamps exist, hold out later case cohorts."""
    indices = np.arange(len(frame))
    if time_column:
        if time_column not in frame.columns:
            raise ValueError(f"Time column '{time_column}' is missing")
        times = pd.to_datetime(frame[time_column], errors="coerce", utc=True)
        if times.isna().any():
            raise ValueError(f"Time column '{time_column}' must contain valid timestamps")
        if group_column:
            if group_column not in frame.columns:
                raise ValueError(f"Group column '{group_column}' is missing")
            if frame[group_column].isna().any() or frame[group_column].astype(str).str.strip().eq("").any():
                raise ValueError(f"Group column '{group_column}' must be populated for every row")
            case_times = pd.DataFrame({"group": frame[group_column], "time": times}).groupby("group")["time"].max()
            ordered = case_times.sort_values()
            split_at = max(1, int(np.floor(len(ordered) * (1 - test_size))))
            split_at = min(split_at, len(ordered) - 1)
            cutoff = ordered.iloc[split_at]
            test_groups = set(ordered[ordered >= cutoff].index)
            test_mask = frame[group_column].isin(test_groups).to_numpy()
            split_name = f"forward_time_by_{group_column}:{cutoff.isoformat()}"
        else:
            ordered_times = times.sort_values()
            split_at = max(1, int(np.floor(len(ordered_times) * (1 - test_size))))
            split_at = min(split_at, len(ordered_times) - 1)
            cutoff = ordered_times.iloc[split_at]
            test_mask = (times >= cutoff).to_numpy()
            split_name = f"forward_time:{cutoff.isoformat()}"
        train_idx, test_idx = indices[~test_mask], indices[test_mask]
    elif group_column:
        if group_column not in frame.columns:
            raise ValueError(f"Group column '{group_column}' is missing")
        groups = frame[group_column]
        if groups.isna().any() or groups.astype(str).str.strip().eq("").any():
            raise ValueError(f"Group column '{group_column}' must be populated for every row")
        group_counts = pd.DataFrame({"group": groups, "target": target}).groupby("target")["group"].nunique()
        if len(group_counts) != 2 or group_counts.min() < 5:
            raise ValueError("Grouped evaluation needs at least five distinct cases in each target class")
        splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=random_state)
        train_idx, test_idx = next(splitter.split(frame, target, groups=groups))
        split_name = f"stratified_group_holdout_5fold_by_{group_column}"
    else:
        train_idx, test_idx = train_test_split(
            indices, test_size=test_size, random_state=random_state, stratify=target,
        )
        split_name = "stratified_random_holdout_no_case_group"

    if len(train_idx) == 0 or len(test_idx) == 0:
        raise ValueError("The requested holdout split produced an empty train or test set")
    if target.iloc[train_idx].nunique() != 2 or target.iloc[test_idx].nunique() != 2:
        raise ValueError("Both target classes must be represented in train and held-out test partitions")
    return np.asarray(train_idx), np.asarray(test_idx), split_name


def _binary_metrics(y_true: pd.Series, probabilities: np.ndarray) -> dict[str, Any]:
    predictions = (probabilities >= EXISTING_FLAG_THRESHOLD).astype(int)
    return {
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "average_precision": float(average_precision_score(y_true, probabilities)),
        "brier_score": float(brier_score_loss(y_true, probabilities)),
        "accuracy_at_0_70": float(accuracy_score(y_true, predictions)),
        "precision_at_0_70": float(precision_score(y_true, predictions, zero_division=0)),
        "recall_at_0_70": float(recall_score(y_true, predictions, zero_division=0)),
        "confusion_matrix_at_0_70": confusion_matrix(y_true, predictions, labels=[0, 1]).tolist(),
    }


def train_and_evaluate(
    frame: pd.DataFrame,
    *,
    target_column: str,
    data_provenance: str,
    permission_reference: Optional[str] = None,
    group_column: Optional[str] = DEFAULT_GROUP_COLUMN,
    time_column: Optional[str] = None,
    test_size: float = 0.20,
    random_state: int = 42,
) -> tuple[Pipeline, dict[str, Any]]:
    """Evaluate a model using a held-out case cohort; no file is read or written here."""
    if data_provenance not in {"synthetic_demo", "permissioned_real"}:
        raise ValueError("data_provenance must be synthetic_demo or permissioned_real")
    if data_provenance == "permissioned_real":
        if not permission_reference or not permission_reference.strip():
            raise ValueError("A permission reference is required for real court data")
        if not time_column:
            raise ValueError("Permissioned real-data evaluation requires a forward time column")
        if not group_column:
            raise ValueError("Permissioned real-data evaluation requires a case-group column")
    if target_column in FEATURES:
        raise ValueError("The target must be a future observed outcome, not one of the model features")
    if group_column in FEATURES or group_column == target_column:
        raise ValueError("The case-group column must be an identifier, not a model feature or target")
    if time_column == target_column:
        raise ValueError("The snapshot-time column cannot be the outcome target")
    if time_column in FEATURES:
        raise ValueError("The snapshot-time column cannot also be a model feature")
    if not 0 < test_size < 0.5:
        raise ValueError("test_size must be greater than 0 and less than 0.5")
    required = set(FEATURES + [target_column])
    if group_column:
        required.add(group_column)
    if time_column:
        required.add(time_column)
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Training data is missing required columns: {', '.join(missing)}")
    if len(frame) < 20:
        raise ValueError("At least 20 rows are required for a demonstrative holdout; real evaluation needs a justified sample size")

    data = frame.copy()
    target = _normalise_target(data[target_column], target_column)
    # Coerce numeric inputs into missing values so train-fold imputers handle them;
    # never encode categories as artificial ordinal numbers.
    for column in NUMERIC_FEATURES:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    for column in CATEGORICAL_FEATURES:
        data[column] = data[column].astype("string").replace("", pd.NA)

    train_idx, test_idx, split_name = _split_indices(
        data, target, group_column=group_column, time_column=time_column,
        test_size=test_size, random_state=random_state,
    )
    X = data[FEATURES]
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = target.iloc[train_idx], target.iloc[test_idx]

    estimator = build_pipeline()
    estimator.fit(X_train, y_train)
    probabilities = estimator.predict_proba(X_test)[:, 1]

    baseline = DummyClassifier(strategy="prior")
    baseline.fit(X_train, y_train)
    baseline_probabilities = baseline.predict_proba(X_test)[:, 1]
    metrics = {
        "evaluation_scope": "software/model-pipeline evaluation only; not real-world validation",
        "data_provenance": data_provenance,
        "split": split_name,
        "target_column": target_column,
        "feature_columns": FEATURES,
        "train_rows": int(len(train_idx)),
        "test_rows": int(len(test_idx)),
        "train_positive_rate": float(y_train.mean()),
        "test_positive_rate": float(y_test.mean()),
        "positive_threshold": EXISTING_FLAG_THRESHOLD,
        "model": _binary_metrics(y_test, probabilities),
        "prior_baseline": {
            "average_precision": float(average_precision_score(y_test, baseline_probabilities)),
            "brier_score": float(brier_score_loss(y_test, baseline_probabilities)),
        },
        "limitations": [
            "Synthetic/rule-generated labels cannot establish predictive performance on actual court outcomes.",
            "The 0.70 flag threshold is retained from the existing prototype; these metrics do not justify that threshold.",
            "Real-world acceptance requires a defined outcome horizon, permitted timestamped data, leakage review, subgroup analysis, calibration review, and prospective validation.",
        ],
    }
    # The reported metrics remain from the untouched holdout. After that evaluation,
    # refit a deployable artifact on every permitted row.
    final_estimator = build_pipeline()
    final_estimator.fit(X, target)
    return final_estimator, metrics


def train_file(
    dataset_path: Path,
    *,
    target_column: str,
    data_provenance: str,
    permission_reference: Optional[str],
    group_column: Optional[str],
    time_column: Optional[str],
    output_dir: Optional[Path],
) -> dict[str, Any]:
    if (
        Path(dataset_path).resolve() == LEGACY_MIXED_DATASET_PATH.resolve()
        and data_provenance != "permissioned_real"
    ):
        raise ValueError(
            "The legacy tracked dataset includes real-derived court distributions; "
            "do not label it synthetic or train without documented permission and forward-time evaluation"
        )
    frame = pd.read_csv(dataset_path)
    estimator, metrics = train_and_evaluate(
        frame,
        target_column=target_column,
        data_provenance=data_provenance,
        permission_reference=permission_reference,
        group_column=group_column,
        time_column=time_column,
    )
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        model_path = output_dir / MODEL_PATH.name
        metadata_path = output_dir / MODEL_METADATA_PATH.name
        joblib.dump(estimator, model_path)
        metadata = {
            "format_version": MODEL_FORMAT_VERSION,
            "trained_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "data_provenance": data_provenance,
            "permission_reference_present": bool(permission_reference),
            "feature_columns": FEATURES,
            "target_column": target_column,
            "threshold": EXISTING_FLAG_THRESHOLD,
            "evaluation": metrics,
            "scikit_learn_version": sklearn.__version__,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        metrics["model_artifact"] = str(model_path)
        metrics["model_metadata"] = str(metadata_path)
    return metrics


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="Explicit permitted/synthetic CSV path; there is no default training dataset")
    parser.add_argument("--target-column", required=True, help="Observed binary 0/1 outcome column; labels are never derived from a risk score")
    parser.add_argument("--data-provenance", required=True, choices=["synthetic_demo", "permissioned_real"])
    parser.add_argument("--permission-reference", help="Required authorization reference for permissioned real records")
    parser.add_argument("--group-column", default=DEFAULT_GROUP_COLUMN, help="Case-group column held out as whole cases; pass an empty value to disable")
    parser.add_argument("--time-column", help="Snapshot timestamp; required for permissioned real-data evaluation")
    parser.add_argument("--output-dir", type=Path, help="Optional artifact directory; omit to evaluate without saving a model")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    group_column = args.group_column.strip() or None
    try:
        metrics = train_file(
            args.dataset,
            target_column=args.target_column,
            data_provenance=args.data_provenance,
            permission_reference=args.permission_reference,
            group_column=group_column,
            time_column=args.time_column,
            output_dir=args.output_dir,
        )
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(f"Training/evaluation stopped safely: {exc}") from exc
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

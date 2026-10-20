"""Train a synthetic-only regression demo for time to next recorded progress.

This is a separate companion to the 30-day binary delay-risk model. It predicts
fictional days until the next qualifying event from fictional snapshots. It must
not be used to train on or claim accuracy for real court outcomes.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, median_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from backend.model_contract import (
    SYNTHETIC_DURATION_TARGET_COLUMN,
    SYNTHETIC_DURATION_TARGET_DEFINITION,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = ROOT / ".local" / "courtlog-synthetic-demo" / "no_progress_30d.csv"
DEFAULT_OUTPUT_DIR = ROOT / ".local" / "courtlog-synthetic-demo" / "duration-model"
MODEL_FILENAME = "duration_model.joblib"
METADATA_FILENAME = "duration_model_metadata.json"
MODEL_FORMAT_VERSION = 1

NUMERIC_FEATURES = ["adjournment_count", "days_since_filing", "days_since_last_event"]
CATEGORICAL_FEATURES = ["case_type", "court"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
DEFAULT_GROUP_COLUMN = "case_id"
DEFAULT_TIME_COLUMN = "snapshot_at"


def build_pipeline() -> Pipeline:
    """Fit preprocessing only on the training cohort, then estimate duration."""
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median"))])
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
        ("regressor", RandomForestRegressor(
            n_estimators=250,
            min_samples_leaf=5,
            max_features=0.9,
            random_state=42,
            n_jobs=1,
        )),
    ])


def _forward_time_case_split(
    frame: pd.DataFrame,
    *,
    group_column: str,
    time_column: str,
    test_size: float,
) -> tuple[np.ndarray, np.ndarray, str]:
    """Hold out later-starting cases and keep each case wholly in one partition."""
    if not 0 < test_size < 0.5:
        raise ValueError("test_size must be greater than 0 and less than 0.5")
    missing = {group_column, time_column}.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing split metadata columns: {', '.join(sorted(missing))}")

    groups = frame[group_column].astype("string")
    if groups.isna().any() or groups.str.strip().eq("").any():
        raise ValueError("Case-group identifiers must be populated")
    times = pd.to_datetime(frame[time_column], errors="coerce", utc=True)
    if times.isna().any():
        raise ValueError("Snapshot timestamps must all be valid")

    grouped = pd.DataFrame({"group": groups, "time": times}).groupby("group")["time"]
    starts = grouped.min().sort_values()
    ends = grouped.max()
    if len(starts) < 20:
        raise ValueError("Synthetic duration evaluation needs at least 20 distinct case groups")

    split_at = max(1, int(np.floor(len(starts) * (1 - test_size))))
    split_at = min(split_at, len(starts) - 1)
    cutoff = starts.iloc[split_at]
    test_groups = set(starts[starts >= cutoff].index)
    train_groups = set(ends[ends < cutoff].index)
    crossing_groups = set(starts.index) - train_groups - test_groups

    group_values = groups.astype(str)
    train_mask = group_values.isin(train_groups).to_numpy()
    test_mask = (group_values.isin(test_groups) & (times >= cutoff)).to_numpy()
    train_indices = np.flatnonzero(train_mask)
    test_indices = np.flatnonzero(test_mask)
    if len(train_indices) < 20 or len(test_indices) < 5:
        raise ValueError("The forward-time case holdout is too small for a useful software check")

    split_name = (
        f"forward_time_new_cases_by_{group_column}:{cutoff.isoformat()}:"
        f"excluded_crossing_cases={len(crossing_groups)}"
    )
    return train_indices, test_indices, split_name


def _duration_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    predicted = np.maximum(0.0, np.asarray(predicted, dtype=float))
    actual = np.asarray(actual, dtype=float)
    rmse = float(np.sqrt(np.mean(np.square(actual - predicted))))
    return {
        "mae_days": float(mean_absolute_error(actual, predicted)),
        "median_absolute_error_days": float(median_absolute_error(actual, predicted)),
        "rmse_days": rmse,
        "r2": float(r2_score(actual, predicted)),
    }


def train_and_evaluate(
    frame: pd.DataFrame,
    *,
    target_column: str = SYNTHETIC_DURATION_TARGET_COLUMN,
    data_provenance: str = "synthetic_demo",
    group_column: str = DEFAULT_GROUP_COLUMN,
    time_column: str = DEFAULT_TIME_COLUMN,
    test_size: float = 0.20,
) -> tuple[Pipeline, dict[str, Any]]:
    """Evaluate on a later, disjoint synthetic case cohort and refit all rows."""
    if data_provenance != "synthetic_demo":
        raise ValueError("This duration-demo trainer accepts synthetic_demo data only")
    if target_column != SYNTHETIC_DURATION_TARGET_COLUMN:
        raise ValueError("Only the documented synthetic duration target is accepted")

    required = set(FEATURES + [target_column, group_column, time_column])
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Training data is missing required columns: {', '.join(missing)}")
    target = pd.to_numeric(frame[target_column], errors="coerce")
    if target.isna().any() or not np.isfinite(target.to_numpy()).all():
        raise ValueError("Synthetic duration target must contain finite numeric day values")
    if (target < 0).any() or target.nunique() < 2:
        raise ValueError("Synthetic duration target must vary and cannot contain negative days")

    train_indices, test_indices, split_name = _forward_time_case_split(
        frame, group_column=group_column, time_column=time_column, test_size=test_size,
    )
    features = frame[FEATURES].copy()
    for column in NUMERIC_FEATURES:
        features[column] = pd.to_numeric(features[column], errors="coerce")
    for column in CATEGORICAL_FEATURES:
        features[column] = features[column].astype("string").replace("", pd.NA)

    train_features = features.iloc[train_indices]
    test_features = features.iloc[test_indices]
    train_target = target.iloc[train_indices]
    test_target = target.iloc[test_indices]

    evaluation_model = build_pipeline()
    evaluation_model.fit(train_features, train_target)
    model_predictions = evaluation_model.predict(test_features)

    baseline = DummyRegressor(strategy="median")
    baseline.fit(train_features, train_target)
    baseline_predictions = baseline.predict(test_features)

    train_groups = set(frame.iloc[train_indices][group_column].astype(str))
    test_groups = set(frame.iloc[test_indices][group_column].astype(str))
    if train_groups.intersection(test_groups):
        raise RuntimeError("Case leakage detected between training and test cohorts")

    metrics = {
        "evaluation_scope": "synthetic-only pipeline smoke test; not real-world validation",
        "data_provenance": "synthetic_demo",
        "target_column": target_column,
        "target_definition": SYNTHETIC_DURATION_TARGET_DEFINITION,
        "feature_columns": FEATURES,
        "split": split_name,
        "train_rows": int(len(train_indices)),
        "test_rows": int(len(test_indices)),
        "train_case_groups": len(train_groups),
        "test_case_groups": len(test_groups),
        "case_groups_disjoint": True,
        "test_target_median_days": float(test_target.median()),
        "model": _duration_metrics(test_target.to_numpy(), model_predictions),
        "median_baseline": _duration_metrics(test_target.to_numpy(), baseline_predictions),
        "limitations": [
            "Durations and features are generated by an invented process; metrics do not estimate performance on real cases.",
            "The target is days to the next simulated qualifying progress event, not total time to judgment or case conclusion.",
            "The synthetic rows are uncensored; real pending cases require a censoring-aware time-to-event design.",
        ],
    }

    final_model = build_pipeline()
    final_model.fit(features, target)
    return final_model, metrics


def train_file(
    dataset_path: Path,
    *,
    output_dir: Optional[Path] = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    """Train only from a generator-produced synthetic CSV and its metadata sidecar."""
    dataset_path = Path(dataset_path)
    metadata_path = dataset_path.with_suffix(".metadata.json")
    if not metadata_path.is_file():
        raise ValueError("Synthetic duration training requires a generator metadata sidecar")
    generation_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(generation_metadata, dict) or (
        generation_metadata.get("data_provenance") != "synthetic_demo"
        or generation_metadata.get("generator") != "scripts/generate_synthetic_demo_data.py"
        or generation_metadata.get("duration_target_column") != SYNTHETIC_DURATION_TARGET_COLUMN
        or generation_metadata.get("duration_target_definition") != SYNTHETIC_DURATION_TARGET_DEFINITION
    ):
        raise ValueError("Input metadata is not the approved synthetic duration-demo contract")

    frame = pd.read_csv(dataset_path)
    if generation_metadata.get("case_count") != len(frame):
        raise ValueError("Dataset row count does not match its synthetic generator metadata")
    model, metrics = train_and_evaluate(frame)
    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        model_path = output_dir / MODEL_FILENAME
        metadata_output_path = output_dir / METADATA_FILENAME
        joblib.dump(model, model_path)
        model_metadata = {
            "format_version": MODEL_FORMAT_VERSION,
            "model_type": "synthetic_duration_regression",
            "trained_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "data_provenance": "synthetic_demo",
            "feature_columns": FEATURES,
            "target_column": SYNTHETIC_DURATION_TARGET_COLUMN,
            "target_definition": SYNTHETIC_DURATION_TARGET_DEFINITION,
            "evaluation": metrics,
            "scikit_learn_version": sklearn.__version__,
        }
        metadata_output_path.write_text(json.dumps(model_metadata, indent=2), encoding="utf-8")
        metrics["model_artifact"] = str(model_path)
        metrics["model_metadata"] = str(metadata_output_path)
    return metrics


def predict_days_to_next_progress(model: Pipeline, snapshot: Mapping[str, Any]) -> float:
    """Return a non-negative synthetic-demo duration estimate for one feature row."""
    features = pd.DataFrame([{column: snapshot.get(column) for column in FEATURES}])
    for column in NUMERIC_FEATURES:
        features[column] = pd.to_numeric(features[column], errors="coerce")
    for column in CATEGORICAL_FEATURES:
        features[column] = features[column].astype("string").replace("", pd.NA)
    prediction = float(model.predict(features)[0])
    return round(max(0.0, prediction), 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    try:
        result = train_file(args.dataset, output_dir=args.output_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Synthetic duration training stopped safely: {exc}") from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

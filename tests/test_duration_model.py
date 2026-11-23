"""Tests for the separate synthetic-only time-to-next-progress regression demo."""

import json
from datetime import datetime, timedelta, timezone

import joblib
import pandas as pd
import pytest

from backend.model_contract import (
    SYNTHETIC_DEMO_TARGET_COLUMN,
    SYNTHETIC_DURATION_TARGET_COLUMN,
    SYNTHETIC_DURATION_TARGET_DEFINITION,
)
from backend.train_duration_model import (
    FEATURES,
    _forward_time_case_split,
    predict_days_to_next_progress,
    train_and_evaluate,
    train_file,
)
from scripts.generate_synthetic_demo_data import generate_synthetic_cases, write_synthetic_dataset


def test_synthetic_generator_adds_duration_target_without_changing_binary_contract():
    rows = generate_synthetic_cases(case_count=300, seed=20261014)
    assert rows == generate_synthetic_cases(case_count=300, seed=20261014)
    assert SYNTHETIC_DEMO_TARGET_COLUMN in rows[0]
    assert SYNTHETIC_DURATION_TARGET_COLUMN in rows[0]
    assert {row[SYNTHETIC_DEMO_TARGET_COLUMN] for row in rows} == {0, 1}
    for row in rows:
        assert row[SYNTHETIC_DURATION_TARGET_COLUMN] >= 0
        assert row[SYNTHETIC_DEMO_TARGET_COLUMN] == int(
            row[SYNTHETIC_DURATION_TARGET_COLUMN] > 30
        )


def test_duration_pipeline_uses_disjoint_forward_case_holdout_and_reports_baseline_metrics():
    frame = pd.DataFrame(generate_synthetic_cases(case_count=500, seed=20261014))
    model, metrics = train_and_evaluate(frame)

    assert metrics["data_provenance"] == "synthetic_demo"
    assert metrics["target_column"] == SYNTHETIC_DURATION_TARGET_COLUMN
    assert metrics["target_definition"] == SYNTHETIC_DURATION_TARGET_DEFINITION
    assert metrics["split"].startswith("forward_time_new_cases_by_case_id:")
    assert metrics["case_groups_disjoint"] is True
    assert metrics["train_case_groups"] + metrics["test_case_groups"] == len(frame)
    assert metrics["train_rows"] + metrics["test_rows"] == len(frame)
    assert metrics["evaluation_scope"] == "synthetic-only pipeline smoke test; not real-world validation"
    assert set(metrics["model"]) == {"mae_days", "median_absolute_error_days", "rmse_days", "r2"}
    assert metrics["model"]["mae_days"] >= 0
    assert metrics["median_baseline"]["mae_days"] >= 0
    assert any("uncensored" in item for item in metrics["limitations"])

    prediction = predict_days_to_next_progress(model, {
        "adjournment_count": 2,
        "days_since_filing": 350,
        "days_since_last_event": 45,
        "case_type": "Previously unseen fictional case type",
        "court": "Previously unseen synthetic court",
    })
    assert prediction >= 0


def test_forward_time_duration_split_excludes_case_histories_crossing_cutoff():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for case_number in range(22):
        case_id = f"SYNTHETIC-CASE-{case_number:02d}"
        first_snapshot = start + timedelta(days=case_number * 10)
        last_offset = 20 if case_number == 15 else 2
        for timestamp in (first_snapshot, first_snapshot + timedelta(days=last_offset)):
            rows.append({"case_id": case_id, "snapshot_at": timestamp.isoformat()})
    frame = pd.DataFrame(rows)

    train_indices, test_indices, split_name = _forward_time_case_split(
        frame,
        group_column="case_id",
        time_column="snapshot_at",
        test_size=0.20,
    )
    train = frame.iloc[train_indices]
    test = frame.iloc[test_indices]
    train_groups = set(train["case_id"])
    test_groups = set(test["case_id"])

    assert "excluded_crossing_cases=1" in split_name
    assert train_groups.isdisjoint(test_groups)
    assert "SYNTHETIC-CASE-15" not in train_groups | test_groups
    assert pd.to_datetime(train["snapshot_at"], utc=True).max() < pd.to_datetime(
        test["snapshot_at"], utc=True
    ).min()


def test_train_file_requires_generator_provenance_and_writes_labeled_artifact(tmp_path):
    dataset = tmp_path / "synthetic-duration.csv"
    generation_metadata = write_synthetic_dataset(dataset, case_count=500, seed=20261014)
    assert generation_metadata["duration_target_column"] == SYNTHETIC_DURATION_TARGET_COLUMN
    assert generation_metadata["duration_target_definition"] == SYNTHETIC_DURATION_TARGET_DEFINITION
    assert "Title" in generation_metadata["template_schema_mapping"]
    assert "real outcomes" in generation_metadata["simulation_note"]

    artifact_dir = tmp_path / "duration-artifacts"
    metrics = train_file(dataset, output_dir=artifact_dir)
    artifact_path = artifact_dir / "duration_model.joblib"
    metadata_path = artifact_dir / "duration_model_metadata.json"
    artifact_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert artifact_path.exists()
    assert artifact_metadata["model_type"] == "synthetic_duration_regression"
    assert artifact_metadata["data_provenance"] == "synthetic_demo"
    assert artifact_metadata["target_column"] == SYNTHETIC_DURATION_TARGET_COLUMN
    assert metrics["model_artifact"] == str(artifact_path)
    restored_model = joblib.load(artifact_path)
    assert predict_days_to_next_progress(restored_model, {
        "adjournment_count": 1,
        "days_since_filing": 200,
        "days_since_last_event": 10,
        "case_type": "Fictional Civil Claim",
        "court": "Synthetic Court A",
    }) >= 0


def test_duration_training_rejects_non_synthetic_provenance_or_target():
    frame = pd.DataFrame(generate_synthetic_cases(case_count=100, seed=11))
    with pytest.raises(ValueError, match="synthetic_demo data only"):
        train_and_evaluate(frame, data_provenance="permissioned_real")
    with pytest.raises(ValueError, match="documented synthetic duration target"):
        train_and_evaluate(frame, target_column=SYNTHETIC_DEMO_TARGET_COLUMN)


def test_train_file_rejects_missing_or_non_synthetic_metadata(tmp_path):
    dataset = tmp_path / "not-approved.csv"
    pd.DataFrame(generate_synthetic_cases(case_count=40, seed=12)).to_csv(dataset, index=False)
    with pytest.raises(ValueError, match="metadata sidecar"):
        train_file(dataset, output_dir=None)

    dataset.with_suffix(".metadata.json").write_text(json.dumps({
        "data_provenance": "permissioned_real",
        "generator": "scripts/generate_synthetic_demo_data.py",
        "duration_target_column": SYNTHETIC_DURATION_TARGET_COLUMN,
        "duration_target_definition": SYNTHETIC_DURATION_TARGET_DEFINITION,
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="not the approved synthetic duration-demo contract"):
        train_file(dataset, output_dir=None)

    generation_metadata = write_synthetic_dataset(dataset, case_count=40, seed=12)
    generation_metadata["case_count"] = 41
    dataset.with_suffix(".metadata.json").write_text(
        json.dumps(generation_metadata), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="row count does not match"):
        train_file(dataset, output_dir=None)


def test_duration_features_exclude_case_identifier_timestamp_and_both_targets():
    assert set(FEATURES) == {
        "adjournment_count",
        "days_since_filing",
        "days_since_last_event",
        "case_type",
        "court",
    }
    assert "case_id" not in FEATURES
    assert "snapshot_at" not in FEATURES
    assert SYNTHETIC_DURATION_TARGET_COLUMN not in FEATURES
    assert SYNTHETIC_DEMO_TARGET_COLUMN not in FEATURES

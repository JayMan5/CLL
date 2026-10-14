"""Synthetic-only checks for the versioned delay-risk training pipeline."""

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from backend.train_model import (
    LEGACY_MIXED_DATASET_PATH,
    MODEL_METADATA_PATH,
    MODEL_PATH,
    _split_indices,
    train_and_evaluate,
    train_file,
)


def synthetic_cases(count=120):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        adjournments = index % 9
        days_since_filing = (index * 83) % 1600
        rows.append({
            "case_id": f"DEMO/CASE-{index:04d}",
            "snapshot_at": (start + timedelta(days=index)).isoformat(),
            "adjournment_count": adjournments,
            "days_since_filing": days_since_filing,
            "case_type": ["Fictional Civil", "Fictional Criminal", "Fictional Commercial"][index % 3],
            "court": ["Demo Court A", "Demo Court B", "Demo Court C"][index % 3],
            # Explicitly synthetic target for pipeline tests only—not a court outcome.
            "demo_target": int(adjournments >= 4 or days_since_filing >= 800),
        })
    return pd.DataFrame(rows)


def test_pipeline_uses_grouped_holdout_one_hot_encoding_and_comparison_metrics():
    frame = synthetic_cases()
    pipeline, metrics = train_and_evaluate(
        frame,
        target_column="demo_target",
        data_provenance="synthetic_demo",
    )

    assert metrics["split"] == "stratified_group_holdout_5fold_by_case_id"
    assert metrics["train_rows"] + metrics["test_rows"] == len(frame)
    assert metrics["model"]["roc_auc"] >= 0.0
    assert metrics["model"]["average_precision"] >= 0.0
    assert metrics["model"]["brier_score"] >= 0.0
    assert metrics["prior_baseline"]["brier_score"] >= 0.0
    assert "not real-world validation" in metrics["evaluation_scope"]

    # Categories not present in the synthetic training folds remain valid inputs.
    probability = pipeline.predict_proba(pd.DataFrame([{
        "adjournment_count": 2,
        "days_since_filing": 150,
        "case_type": "New Fictional Category",
        "court": "New Fictional Court",
    }]))[0, 1]
    assert 0.0 <= probability <= 1.0


def test_forward_time_holdout_keeps_case_groups_separate():
    frame = synthetic_cases()
    _, metrics = train_and_evaluate(
        frame,
        target_column="demo_target",
        data_provenance="synthetic_demo",
        time_column="snapshot_at",
    )
    assert metrics["split"].startswith("forward_time_new_cases_by_case_id:")
    assert metrics["train_rows"] < 0.9 * len(frame)
    assert metrics["test_rows"] > 0


def test_forward_time_grouped_holdout_is_strict_and_excludes_crossing_cases():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    targets = []
    for case_number in range(22):
        case_id = f"DEMO/TIME-{case_number:02d}"
        first_snapshot = start + timedelta(days=case_number * 10)
        last_offset = 20 if case_number == 15 else 2
        for timestamp in (first_snapshot, first_snapshot + timedelta(days=last_offset)):
            rows.append({"case_id": case_id, "snapshot_at": timestamp.isoformat()})
            targets.append(case_number % 2)
    frame = pd.DataFrame(rows)
    target = pd.Series(targets)

    train_indices, test_indices, split_name = _split_indices(
        frame,
        target,
        group_column="case_id",
        time_column="snapshot_at",
        test_size=0.20,
        random_state=42,
    )

    training = frame.iloc[train_indices]
    held_out = frame.iloc[test_indices]
    train_cases = set(training["case_id"])
    test_cases = set(held_out["case_id"])
    training_times = pd.to_datetime(training["snapshot_at"], utc=True)
    held_out_times = pd.to_datetime(held_out["snapshot_at"], utc=True)

    assert split_name.startswith("forward_time_new_cases_by_case_id:")
    assert "excluded_crossing_cases=1" in split_name
    assert train_cases.isdisjoint(test_cases)
    assert training_times.max() < held_out_times.min()
    assert "DEMO/TIME-15" not in (train_cases | test_cases)
    assert set(target.iloc[train_indices]) == {0, 1}
    assert set(target.iloc[test_indices]) == {0, 1}


def test_permissioned_real_training_requires_reference_and_forward_time_column():
    frame = synthetic_cases()
    with pytest.raises(ValueError, match="permission reference"):
        train_and_evaluate(
            frame,
            target_column="demo_target",
            data_provenance="permissioned_real",
        )
    with pytest.raises(ValueError, match="forward time column"):
        train_and_evaluate(
            frame,
            target_column="demo_target",
            data_provenance="permissioned_real",
            permission_reference="FICTIONAL-APPROVAL-REFERENCE",
        )
    with pytest.raises(ValueError, match="case-group column"):
        train_and_evaluate(
            frame,
            target_column="demo_target",
            data_provenance="permissioned_real",
            permission_reference="FICTIONAL-APPROVAL-REFERENCE",
            group_column=None,
            time_column="snapshot_at",
        )


def test_legacy_mixed_dataset_is_not_silently_treated_as_synthetic():
    # The guard runs before read_csv; this test never loads the tracked dataset.
    with pytest.raises(ValueError, match="real-derived court distributions"):
        train_file(
            LEGACY_MIXED_DATASET_PATH,
            target_column="delay_risk",
            data_provenance="synthetic_demo",
            permission_reference=None,
            group_column="case_id",
            time_column=None,
            output_dir=None,
        )


def test_target_must_be_explicit_binary_observed_labels():

    frame = synthetic_cases()
    frame["demo_target"] = frame["demo_target"].map({0: "Low", 1: "High"})
    with pytest.raises(ValueError, match="binary 0/1 labels"):
        train_and_evaluate(
            frame,
            target_column="demo_target",
            data_provenance="synthetic_demo",
        )


def test_saved_pipeline_metadata_contains_provenance_without_dataset_path(tmp_path):
    dataset = tmp_path / "fictional.csv"
    synthetic_cases().to_csv(dataset, index=False)
    metrics = train_file(
        dataset,
        target_column="demo_target",
        data_provenance="synthetic_demo",
        permission_reference=None,
        group_column="case_id",
        time_column=None,
        output_dir=tmp_path / "artifacts",
    )
    metadata_path = tmp_path / "artifacts" / MODEL_METADATA_PATH.name
    model_path = tmp_path / "artifacts" / MODEL_PATH.name
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert model_path.exists()
    assert metadata["format_version"] == 2
    assert metadata["data_provenance"] == "synthetic_demo"
    assert "fictional.csv" not in json.dumps(metadata)
    assert "FICTIONAL/CASE-" not in json.dumps(metadata)
    assert "evaluation" in metadata
    assert "model_metadata" in metrics

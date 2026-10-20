"""Generate fictional case snapshots for CourtLOG's synthetic model demonstrations.

The output includes a 30-day no-progress classification label and a companion
synthetic duration target. This generator uses only Python's standard library; it
does not read repository case data, application databases, or external outcomes.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.model_contract import (
    SYNTHETIC_DEMO_TARGET_COLUMN,
    SYNTHETIC_DEMO_TARGET_DEFINITION,
    SYNTHETIC_DURATION_TARGET_COLUMN,
    SYNTHETIC_DURATION_TARGET_DEFINITION,
    SYNTHETIC_DURATION_CASE_TYPES,
    SYNTHETIC_DURATION_COURTS,
)

DEFAULT_OUTPUT = ROOT / ".local" / "courtlog-synthetic-demo" / "no_progress_30d.csv"
TARGET_COLUMN = SYNTHETIC_DEMO_TARGET_COLUMN
TARGET_DEFINITION = SYNTHETIC_DEMO_TARGET_DEFINITION
DURATION_TARGET_COLUMN = SYNTHETIC_DURATION_TARGET_COLUMN
DURATION_TARGET_DEFINITION = SYNTHETIC_DURATION_TARGET_DEFINITION

CASE_TYPES = SYNTHETIC_DURATION_CASE_TYPES
COURTS = SYNTHETIC_DURATION_COURTS
CASE_TYPE_DELAY_FACTOR = {
    "Fictional Civil Claim": 0.95,
    "Fictional Land Matter": 1.20,
    "Fictional Criminal Appeal": 0.85,
    "Fictional Commercial Appeal": 1.10,
}
COURT_DELAY_FACTOR = {
    "Synthetic Court A": 0.90,
    "Synthetic Court B": 1.00,
    "Synthetic Court C": 1.10,
    "Synthetic Court D": 1.20,
}


def generate_synthetic_cases(case_count: int = 1500, seed: int = 20261014) -> list[dict[str, Any]]:
    """Return deterministic, wholly fictional point-in-time rows and demo labels."""
    if case_count < 40:
        raise ValueError("Generate at least 40 fictional cases for a meaningful software holdout")
    if seed < 0:
        raise ValueError("seed must be non-negative")

    rng = random.Random(seed)
    first_snapshot_day = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows: list[dict[str, Any]] = []
    for index in range(case_count):
        case_id = f"SYNTHETIC-DEMO-{index + 1:06d}"
        snapshot_at = first_snapshot_day + timedelta(days=rng.randrange(0, 900))
        days_since_filing = rng.randint(30, 1800)
        if rng.random() < 0.12:
            # No earlier qualifying activity is represented; the filing date is
            # the recency fallback used by the inference feature builder.
            days_since_last_event = days_since_filing
        else:
            days_since_last_event = rng.randint(0, min(days_since_filing, 720))
        adjournment_count = min(14, int(rng.expovariate(1 / 3.0)))
        case_type = rng.choice(CASE_TYPES)
        court = rng.choice(COURTS)

        # Explicitly invented waiting-time mechanism: the features modulate a
        # fictional exponential time-to-progress, with per-row random variation.
        # This generated duration is an outcome for synthetic demonstrations,
        # never a model feature or an observed court duration.
        mean_wait_days = (
            10.0
            + 0.025 * days_since_filing
            + 0.035 * days_since_last_event
            + 1.0 * adjournment_count
        )
        mean_wait_days *= CASE_TYPE_DELAY_FACTOR[case_type]
        mean_wait_days *= COURT_DELAY_FACTOR[court]
        mean_wait_days *= rng.uniform(0.75, 1.25)
        fictional_days_to_next_progress = rng.expovariate(1 / mean_wait_days)
        recorded_demo_duration = fictional_days_to_next_progress
        # Preserve the existing binary label's exact raw-duration threshold.
        no_progress = int(fictional_days_to_next_progress > 30)

        rows.append({
            # Synthetic identifier is used for case-level holdout only.
            "case_id": case_id,
            "snapshot_at": snapshot_at.isoformat().replace("+00:00", "Z"),
            "adjournment_count": adjournment_count,
            "days_since_filing": days_since_filing,
            "days_since_last_event": days_since_last_event,
            "case_type": case_type,
            "court": court,
            DURATION_TARGET_COLUMN: recorded_demo_duration,
            TARGET_COLUMN: no_progress,
        })
    return rows


def write_synthetic_dataset(
    output_path: Path,
    *,
    case_count: int = 1500,
    seed: int = 20261014,
) -> dict[str, Any]:
    """Write the synthetic CSV and a provenance/codebook sidecar."""
    rows = generate_synthetic_cases(case_count=case_count, seed=seed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(rows[0])
    with output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    positive_count = sum(row[TARGET_COLUMN] for row in rows)
    metadata = {
        "data_provenance": "synthetic_demo",
        "generator": "scripts/generate_synthetic_demo_data.py",
        "seed": seed,
        "case_count": case_count,
        "snapshot_date_range": {
            "first": min(row["snapshot_at"] for row in rows),
            "last": max(row["snapshot_at"] for row in rows),
        },
        "target_column": TARGET_COLUMN,
        "target_definition": TARGET_DEFINITION,
        "positive_count": positive_count,
        "negative_count": case_count - positive_count,
        "duration_target_column": DURATION_TARGET_COLUMN,
        "duration_target_definition": DURATION_TARGET_DEFINITION,
        "features": [
            "adjournment_count",
            "days_since_filing",
            "days_since_last_event",
            "case_type",
            "court",
        ],
        "template_schema_mapping": {
            "Case Ref": "generated case_id used only for grouping, never as a feature",
            "Title": "omitted; no real titles or party details are generated",
            "Court": "fictional Synthetic Court labels",
            "Case Type": "fictional case-type labels",
            "Year Filed": "represented as days_since_filing at snapshot_at",
            "Year Decided / Years to Conclusion / Risk Level": "not copied or used; targets are generated independently",
            "Additional model fields": ["snapshot_at", "adjournment_count", "days_since_last_event"],
        },
        "simulation_note": (
            "All case identifiers, snapshots, features, event timing, durations and labels are generated. "
            "Only the source file's column layout was used as a schema reference. "
            "No repository case-data rows, identifiers, titles, real outcomes or court durations are read or used."
        ),

    }
    metadata_path = output_path.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=1500, help="Number of fictional case snapshots (minimum 40)")
    parser.add_argument("--seed", type=int, default=20261014, help="Deterministic random seed")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="CSV path; companion metadata is written beside it")
    args = parser.parse_args()
    try:
        metadata = write_synthetic_dataset(args.output, case_count=args.cases, seed=args.seed)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Synthetic demo data generation stopped: {exc}") from exc
    print(json.dumps({
        "dataset": str(args.output),
        "metadata": str(args.output.with_suffix('.metadata.json')),
        **metadata,
    }, indent=2))


if __name__ == "__main__":
    main()

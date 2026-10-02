#!/usr/bin/env python3
"""Seed a fresh, isolated local demo DB with deterministic fictional cases.

This script deliberately does not read any CSV, model dataset, or tracked DB.
It refuses to write outside the repository's ignored .local/ directory and
requires DEMO_MODE=true so the seeded users cannot be mistaken for live users.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCAL_DATA_DIR = REPOSITORY_ROOT / ".local"
TRACKED_DATABASE = (REPOSITORY_ROOT / "data" / "courtlog.db").resolve()

# Load only this checkout's local environment; never silently use a caller's cwd.
load_dotenv(REPOSITORY_ROOT / ".env")
sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.database import SQLiteDatabase, format_date  # noqa: E402

DEMO_USERS = {
    "usr_sheriff_01": ("Sheriff", "FHC Abuja Court 4", "Criminal"),
    "usr_clerk_01": ("Clerk", "FHC Abuja Court 4", "Criminal"),
    "usr_dcr_01": ("DCR", "FHC Abuja", "Criminal"),
    "usr_cr_01": ("Chief Registrar", "All Courts", "All Divisions"),
    "usr_judge_01": ("Judge", "FHC Abuja Court 4", "Criminal"),
}


def _stamp(reference: datetime, *, days: int = 0, hours: int = 0) -> str:
    return format_date(reference - timedelta(days=days, hours=hours))


def _base_case(
    reference: datetime,
    case_id: str,
    *,
    title: str,
    filing_days_ago: int,
    risk_score: float,
    adjournments: int = 0,
    judgment_status: str = "Pending",
    scan_days_ago: int | None = 1,
) -> dict[str, Any]:
    scans = []
    if scan_days_ago is not None:
        scans.append({
            "location": "Fictional Registry Desk A",
            "timestamp": _stamp(reference, days=scan_days_ago),
            "staff_id": "usr_sheriff_01",
        })
    return {
        "case_id": case_id,
        "case_title": title,
        "case_type": "Criminal",
        "court": "FHC Abuja Court 4",
        "assigned_division": "Criminal",
        "assigned_judge_id": "usr_judge_01",
        "assigned_sheriff_id": "usr_sheriff_01",
        "filing_date": _stamp(reference, days=filing_days_ago),
        "adjournment_count": adjournments,
        "days_since_filing": filing_days_ago,
        "judgment_status": judgment_status,
        "delay_risk_score": risk_score,
        "risk_flag": risk_score >= 0.70,
        "dcr_approval_required": False,
        "dcr_approval_requested_at": None,
        "dcr_approval_history": [],
        "dcr_acknowledged_at": None,
        "dcr_acknowledged_by": None,
        "dcr_acknowledgement_note": None,
        "dcr_auto_escalated": False,
        "dcr_escalated_at": None,
        "dcr_approval_resolved_at": None,
        "dcr_override_reason": None,
        "adjournment_blocked": False,
        "party_contact": {},
        "scan_events": scans,
        "hearing_log": [],
        "execution_log": [],
        "documents": [],
        "custody_history": [],
        "file_missing": False,
        "file_missing_report": None,
        "file_missing_history": [],
        "custody_alert": False,
        "enforcement_non_compliant": False,
        "demo_fixture": True,
        "data_notice": "Entirely fictional demonstration record; not real court data.",
    }


def build_demo_cases(as_of: datetime) -> list[dict[str, Any]]:
    """Return fixed, role-scoped scenarios anchored to a caller-chosen date."""
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    reference = as_of.astimezone(timezone.utc).replace(microsecond=0)

    active = _base_case(
        reference, "DEMO/2026/001", title="Fictional Applicant A v Fictional Respondent A",
        filing_days_ago=3, risk_score=0.18, scan_days_ago=1,
    )
    moderate_idle = _base_case(
        reference, "DEMO/2026/002", title="Fictional Applicant B v Fictional Respondent B",
        filing_days_ago=24, risk_score=0.52, adjournments=2, scan_days_ago=8,
    )
    moderate_idle["custody_alert"] = True

    high_risk = _base_case(
        reference, "DEMO/2026/003", title="Fictional Applicant C v Fictional Respondent C",
        filing_days_ago=48, risk_score=0.86, adjournments=3, scan_days_ago=1,
    )
    high_risk["hearing_log"] = [{
        "date": _stamp(reference, days=4),
        "outcome": "Adjourned",
        "reason_code": "Counsel Absent",
        "next_date": (reference + timedelta(days=14)).date().isoformat(),
        "actor_user_id": "usr_clerk_01",
    }]

    missing = _base_case(
        reference, "DEMO/2026/004", title="Fictional Applicant D v Fictional Respondent D",
        filing_days_ago=32, risk_score=0.42, adjournments=1, scan_days_ago=10,
    )
    missing["file_missing"] = True
    missing["file_missing_report"] = {
        "reported_by": "usr_sheriff_01",
        "reported_at": _stamp(reference, days=2),
        "last_known_location": "Fictional Registry Desk B",
        "notes": "Synthetic scenario for demonstration only.",
        "resolved": False,
        "resolved_by": None,
        "resolved_at": None,
    }
    missing["file_missing_history"] = [{
        "action": "reported_missing",
        "actor_user_id": "usr_sheriff_01",
        "timestamp": _stamp(reference, days=2),
        "last_known_location": "Fictional Registry Desk B",
        "notes": "Synthetic scenario for demonstration only.",
    }]

    found = _base_case(
        reference, "DEMO/2026/005", title="Fictional Applicant E v Fictional Respondent E",
        filing_days_ago=40, risk_score=0.31, adjournments=1, scan_days_ago=1,
    )
    found["file_missing_report"] = {
        "reported_by": "usr_sheriff_01",
        "reported_at": _stamp(reference, days=6),
        "last_known_location": "Fictional Courtroom Store",
        "notes": "Synthetic scenario for demonstration only.",
        "resolved": True,
        "resolved_by": "usr_sheriff_01",
        "resolved_at": _stamp(reference, days=5),
        "found_location": "Fictional Registry Desk A",
        "resolution_reason": "Synthetic recovery scenario.",
    }
    found["file_missing_history"] = [
        {
            "action": "reported_missing",
            "actor_user_id": "usr_sheriff_01",
            "timestamp": _stamp(reference, days=6),
            "last_known_location": "Fictional Courtroom Store",
            "notes": "Synthetic scenario for demonstration only.",
        },
        {
            "action": "found",
            "actor_user_id": "usr_sheriff_01",
            "timestamp": _stamp(reference, days=5),
            "found_location": "Fictional Registry Desk A",
            "reason": "Synthetic recovery scenario.",
        },
    ]

    dcr_review = _base_case(
        reference, "DEMO/2026/006", title="Fictional Applicant F v Fictional Respondent F",
        filing_days_ago=75, risk_score=0.64, adjournments=4, scan_days_ago=1,
    )
    dcr_review.update({
        "dcr_approval_required": True,
        "dcr_approval_requested_at": _stamp(reference, hours=26),
        "dcr_auto_escalated": True,
        "dcr_escalated_at": _stamp(reference),
        "adjournment_blocked": True,
        "dcr_approval_history": [
            {
                "action": "requested",
                "occurred_at": _stamp(reference, hours=26),
                "actor_user_id": "usr_clerk_01",
                "reason_code": "Counsel Absent",
                "existing_adjournment_count": 4,
                "note": "Synthetic demonstration state; application workflow only.",
            },
            {
                "action": "escalated",
                "occurred_at": _stamp(reference),
                "actor_user_id": None,
                "note": "In-app prototype escalation only; no external notification was sent.",
            },
        ],
    })

    overdue_delivery = _base_case(
        reference, "DEMO/2026/007", title="Fictional Applicant G v Fictional Respondent G",
        filing_days_ago=210, risk_score=0.77, adjournments=2,
        judgment_status="Delivered", scan_days_ago=1,
    )
    overdue_delivery["execution_log"] = [{
        "action": "Judgment Delivered",
        "date": _stamp(reference, days=100),
        "actor_user_id": "usr_judge_01",
        "notes": "Synthetic example for the configured prototype review prompt.",
    }]
    overdue_delivery["enforcement_non_compliant"] = True

    executed = _base_case(
        reference, "DEMO/2026/008", title="Fictional Applicant H v Fictional Respondent H",
        filing_days_ago=120, risk_score=0.29, adjournments=1,
        judgment_status="Executed", scan_days_ago=1,
    )
    executed["execution_log"] = [
        {
            "action": "Judgment Delivered",
            "date": _stamp(reference, days=60),
            "actor_user_id": "usr_judge_01",
            "notes": "Synthetic example only.",
        },
        {
            "action": "Writ Lodged",
            "date": _stamp(reference, days=40),
            "actor_user_id": "usr_clerk_01",
            "notes": "Synthetic example only.",
        },
        {
            "action": "Execution Completed",
            "date": _stamp(reference, days=20),
            "actor_user_id": "usr_sheriff_01",
            "notes": "Synthetic example only.",
        },
    ]

    return [active, moderate_idle, high_risk, missing, found, dcr_review, overdue_delivery, executed]


def resolve_demo_database_path() -> Path:
    """Resolve the explicitly selected local DB, refusing tracked or external paths."""
    raw_path = os.getenv("COURTLOG_DB_PATH", "").strip()
    if not raw_path:
        raise RuntimeError("Set COURTLOG_DB_PATH to a disposable database path under .local/.")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = REPOSITORY_ROOT / path
    if LOCAL_DATA_DIR.is_symlink():
        raise RuntimeError("Refusing to seed: the ignored .local/ directory must not be a symlink.")
    resolved = path.resolve()
    local_root = LOCAL_DATA_DIR.resolve()
    if resolved == TRACKED_DATABASE or not resolved.is_relative_to(local_root):
        raise RuntimeError("Refusing to seed: COURTLOG_DB_PATH must be inside this checkout's ignored .local/ directory, never data/courtlog.db.")
    return resolved


def seed_demo_cases(database: SQLiteDatabase, *, as_of: datetime, overwrite_fixtures: bool = False) -> list[dict[str, Any]]:
    """Write the known fictional fixtures after validating demo accounts and DB contents."""
    if os.getenv("DEMO_MODE", "false").strip().lower() != "true":
        raise RuntimeError("Refusing to seed: set DEMO_MODE=true for a disposable local demo only.")

    for user_id, expected in DEMO_USERS.items():
        user = database.get_user(user_id)
        actual = (user.get("role"), user.get("court"), user.get("division")) if user else None
        if (not user or user.get("disabled") or user.get("demo_only") is not True or actual != expected):
            raise RuntimeError(f"Expected active fictional demo account {user_id} with its documented scope; no cases were written.")

    cases = build_demo_cases(as_of)
    fixture_ids = {case["case_id"] for case in cases}
    existing = database.list_cases()
    if any(not case.get("demo_fixture") for case in existing):
        raise RuntimeError("Refusing to mix sample fixtures with other records. Use a fresh disposable .local/ database.")
    if any(case.get("case_id") in fixture_ids for case in existing) and not overwrite_fixtures:
        raise RuntimeError("Demo fixtures already exist. Pass --overwrite-fixtures only if you intend to reset these sample records.")

    for case in cases:
        database.save_case(case["case_id"], case)
    return cases


def _parse_as_of(value: str) -> datetime:
    try:
        chosen = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--as-of must be an ISO date such as 2026-10-02") from exc
    return datetime.combine(chosen, time(hour=12), tzinfo=timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of", type=_parse_as_of,
        default=datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0),
        help="UTC date to anchor the fixed scenarios (default: today's UTC date)",
    )
    parser.add_argument(
        "--overwrite-fixtures", action="store_true",
        help="replace only records marked demo_fixture in the isolated .local/ database",
    )
    args = parser.parse_args()

    if os.getenv("DEMO_MODE", "false").strip().lower() != "true":
        raise SystemExit("Set DEMO_MODE=true in the disposable local .env before running this demo-only script.")
    db_path = resolve_demo_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # SQLiteDatabase prefers COURTLOG_DB_PATH over its argument; pin it to the
    # already-validated absolute path so a different caller cwd cannot redirect it.
    os.environ["COURTLOG_DB_PATH"] = str(db_path)
    database = SQLiteDatabase(str(db_path))
    try:
        cases = seed_demo_cases(database, as_of=args.as_of, overwrite_fixtures=args.overwrite_fixtures)
    finally:
        database.conn.close()

    print(f"Seeded {len(cases)} fully fictional demo cases into {db_path}.")
    print("No CSV, model dataset, tracked court database, or real court record was read.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

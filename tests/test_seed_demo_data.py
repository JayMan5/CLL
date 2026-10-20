"""Tests for the demo-only synthetic seed tool; never open the tracked database."""

from collections import Counter
from datetime import datetime, timezone
import re

import pytest

from backend.database import SQLiteDatabase
import scripts.seed_demo_data as seed_tool
from scripts.seed_demo_data import (
    DEMO_USERS,
    TRACKED_DATABASE,
    build_demo_cases,
    resolve_demo_database_path,
    seed_demo_cases,
)


def test_demo_scenarios_are_deterministic_fictional_and_scope_matched():
    as_of = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    first = build_demo_cases(as_of)
    second = build_demo_cases(as_of)

    assert first == second
    workflow_cases = [case for case in first if not case.get("duration_demo_fixture")]
    duration_cases = [case for case in first if case.get("duration_demo_fixture")]
    assert len(first) == 12
    assert len({case["case_id"] for case in first}) == 12
    assert len(workflow_cases) == 8
    assert len(duration_cases) == 4
    assert all(re.fullmatch(r"DEMO/2026/\d{3}", case["case_id"]) for case in workflow_cases)
    assert all(re.fullmatch(r"SYNTHETIC-DURATION-DEMO/2026/\d{3}", case["case_id"]) for case in duration_cases)
    assert all(case["demo_fixture"] is True for case in first)
    assert all("fictional" in case["data_notice"].lower() for case in first)
    assert set(case["case_type"] for case in workflow_cases) == {
        "Land Dispute", "Criminal", "Civil Debt", "Family", "Admiralty", "Intellectual Property",
    }
    assert Counter(case["case_type"] for case in workflow_cases) == {
        "Civil Debt": 2, "Land Dispute": 2, "Criminal": 1,
        "Family": 1, "Admiralty": 1, "Intellectual Property": 1,
    }
    assert {case["case_type"] for case in duration_cases} == {
        "Fictional Civil Claim", "Fictional Land Matter",
        "Fictional Criminal Appeal", "Fictional Commercial Appeal",
    }
    assert {case["duration_demo_court"] for case in duration_cases} == {
        "Synthetic Court A", "Synthetic Court B", "Synthetic Court C", "Synthetic Court D",
    }
    assert all(case["data_provenance"] == "synthetic_demo" for case in duration_cases)
    assert all(case["duration_demo_fixture"] is True for case in duration_cases)
    assert all(case["court"] == "FHC Abuja Court 4" for case in first)
    assert all(30 <= case["days_since_filing"] <= 1800 for case in duration_cases)
    assert all(case["hearing_log"][0]["outcome"] in {"Heard", "Adjourned"} for case in duration_cases)
    assert all(
        case["assigned_division"] == ("Criminal" if "criminal" in case["case_type"].casefold() else "Civil")
        for case in first
    )
    assert all(case["assigned_sheriff_id"] == "usr_sheriff_01" for case in first)
    assert all(case["assigned_judge_id"] == "usr_judge_01" for case in first)
    assert all("phone" not in " ".join(case.keys()).lower() for case in first)
    assert all("party_contact" not in case or not case["party_contact"] for case in first)

    scores = [case["delay_risk_score"] for case in first]
    assert min(scores) < 0.30
    assert any(0.30 <= score < 0.70 for score in scores)
    assert max(scores) >= 0.70
    assert any(case["judgment_status"] == "Pending" for case in first)
    assert any(case["judgment_status"] == "Delivered" for case in first)
    assert any(case["judgment_status"] == "Executed" for case in first)

    by_id = {case["case_id"]: case for case in first}
    assert by_id["DEMO/2026/004"]["file_missing_report"]["resolved"] is False
    assert by_id["DEMO/2026/005"]["file_missing_report"]["resolved"] is True
    assert by_id["DEMO/2026/006"]["dcr_approval_required"] is True
    assert by_id["DEMO/2026/007"]["enforcement_non_compliant"] is True
    assert by_id["DEMO/2026/008"]["judgment_status"] == "Executed"

    assert set(DEMO_USERS) == {
        "usr_sheriff_01", "usr_clerk_01", "usr_dcr_01", "usr_cr_01", "usr_judge_01",
    }


def test_demo_seed_requires_demo_accounts_and_refuses_existing_non_demo_cases(tmp_path, monkeypatch):
    database_path = tmp_path / "fictional-demo.sqlite"
    monkeypatch.setenv("COURTLOG_DB_PATH", str(database_path))
    monkeypatch.setenv("DEMO_MODE", "true")
    database = SQLiteDatabase()
    as_of = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    try:
        seeded = seed_demo_cases(database, as_of=as_of)
        assert len(seeded) == 12
        assert len(database.list_cases()) == 12

        with pytest.raises(RuntimeError, match="already exist"):
            seed_demo_cases(database, as_of=as_of)

        reset = seed_demo_cases(database, as_of=as_of, overwrite_fixtures=True)
        assert reset == seeded
        assert len(database.list_cases()) == 12

        database.save_case("REAL/RECORD/DO-NOT-OVERWRITE", {"case_id": "REAL/RECORD/DO-NOT-OVERWRITE"})
        with pytest.raises(RuntimeError, match="mix sample fixtures"):
            seed_demo_cases(database, as_of=as_of, overwrite_fixtures=True)
    finally:
        database.conn.close()


def test_seeded_scenarios_are_visible_with_their_intended_demo_role_scopes(tmp_path, monkeypatch):
    from backend import main

    database_path = tmp_path / "fictional-scoped-demo.sqlite"
    monkeypatch.setenv("COURTLOG_DB_PATH", str(database_path))
    monkeypatch.setenv("DEMO_MODE", "true")
    database = SQLiteDatabase()
    try:
        cases = seed_demo_cases(
            database,
            as_of=datetime(2026, 10, 2, 12, tzinfo=timezone.utc),
        )
        monkeypatch.setattr(main, "db", database)
        all_case_ids = {case["case_id"] for case in cases}
        expected_visible_case_ids = {
            "usr_sheriff_01": all_case_ids,  # Explicit assignments extend across divisions.
            "usr_clerk_01": {"DEMO/2026/003", "SYNTHETIC-DURATION-DEMO/2026/003"},  # Criminal Filing Clerk sees Criminal division only.
            "usr_dcr_01": all_case_ids,
            "usr_cr_01": all_case_ids,
            "usr_judge_01": all_case_ids,  # Every fictional case is assigned to this demo judge.
        }
        for user_id, expected_ids in expected_visible_case_ids.items():
            visible_ids = {
                case["case_id"] for case in cases
                if main.can_access_case(case, {"user_id": user_id})
            }
            assert visible_ids == expected_ids, user_id
    finally:
        database.conn.close()


def test_demo_database_path_is_confined_to_ignored_local_directory(monkeypatch):
    monkeypatch.setenv("COURTLOG_DB_PATH", str(TRACKED_DATABASE))
    with pytest.raises(RuntimeError, match="never data/courtlog.db"):
        resolve_demo_database_path()

    monkeypatch.setenv("COURTLOG_DB_PATH", "/tmp/outside-demo.sqlite")
    with pytest.raises(RuntimeError, match="ignored .local"):
        resolve_demo_database_path()

    safe_path = ".local/demo/fictional.sqlite"
    monkeypatch.setenv("COURTLOG_DB_PATH", safe_path)
    assert resolve_demo_database_path() == seed_tool.REPOSITORY_ROOT / safe_path


def test_demo_database_path_rejects_a_symlinked_local_directory(tmp_path, monkeypatch):
    outside_directory = tmp_path / "outside"
    outside_directory.mkdir()
    local_link = tmp_path / ".local"
    local_link.symlink_to(outside_directory, target_is_directory=True)
    monkeypatch.setattr(seed_tool, "LOCAL_DATA_DIR", local_link)
    monkeypatch.setenv("COURTLOG_DB_PATH", str(local_link / "demo.sqlite3"))

    with pytest.raises(RuntimeError, match="must not be a symlink"):
        resolve_demo_database_path()

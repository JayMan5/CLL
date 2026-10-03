"""Authenticated workflow smoke tests using an isolated, fictional SQLite database."""
import os
import secrets
import hashlib
import json
import joblib
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Configure isolation before importing the app. Another test module may import the
# app first; both test modules then share that already-isolated temporary DB.
_runtime = tempfile.TemporaryDirectory(prefix="courtlog-api-tests-")
if "backend.main" not in sys.modules:
    os.environ["COURTLOG_DB_PATH"] = str(Path(_runtime.name) / "courtlog.db")
    os.environ["JWT_PRIVATE_KEY_PATH"] = str(Path(_runtime.name) / "private.pem")
    os.environ["JWT_PUBLIC_KEY_PATH"] = str(Path(_runtime.name) / "public.pem")
    os.environ["DEMO_MODE"] = "false"
os.environ["COOKIE_SECURE"] = "false"  # TestClient uses HTTP only in this test process.

from fastapi.testclient import TestClient
from backend import main
from backend.auth import create_access_token, REFRESH_TOKEN_EXPIRE_DAYS
from backend.database import get_password_hash
from backend.train_model import train_and_evaluate
import pandas as pd

# A local TestClient database never reads or writes the committed application DB.
main.COOKIE_SECURE = False
client = TestClient(main.app)

_USERS = {
    "smoke_sheriff": ("smoke.sheriff", "Sheriff", "Smoke Test Court", "Criminal"),
    "smoke_clerk": ("smoke.clerk", "Clerk", "Smoke Test Court", "Criminal"),
    "smoke_dcr": ("smoke.dcr", "DCR", "Smoke Test Court", "Criminal"),
    "smoke_cr": ("smoke.cr", "Chief Registrar", "All Courts", "All Divisions"),
    "smoke_judge": ("smoke.judge", "Judge", "Smoke Test Court", "Criminal"),
}
for user_id, (username, role, court, division) in _USERS.items():
    main.db.save_user(user_id, {
        "user_id": user_id,
        "username": username,
        "password": get_password_hash("Smoke-Test-Password-2026!"),
        "name": f"Fictional {role}",
        "role": role,
        "badge": "Automated test account",
        "court": court,
        "division": division,
        "disabled": False,
    })


def auth_headers(user_id):
    user = main.db.get_user(user_id)
    session_id = secrets.token_urlsafe(32)
    refresh_id = secrets.token_urlsafe(32)
    expires_at = int((datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp())
    main.db.create_auth_session(session_id, user_id, refresh_id, expires_at)
    claims = {"sub": user_id, "role": user["role"], "sid": session_id}
    access = create_access_token(claims)
    return {"Authorization": f"Bearer {access}"}


def add_case(suffix, *, court="Smoke Test Court", assigned_sheriff_id="smoke_sheriff", **overrides):
    case_id = f"API/{secrets.token_hex(4)}/{suffix}"
    case = {
        "case_id": case_id,
        "case_title": f"Fictional claimant v fictional respondent ({suffix})",
        "case_type": "Civil",
        "court": court,
        "assigned_division": "Criminal",
        "assigned_judge_id": "smoke_judge",
        "assigned_sheriff_id": assigned_sheriff_id,
        "custody_history": [],
        "filing_date": "2026-09-01T00:00:00Z",
        "days_since_filing": 30,
        "adjournment_count": 0,
        "judgment_status": "Pending",
        "delay_risk_score": 0.2,
        "risk_flag": False,
        "custody_alert": False,
        "enforcement_non_compliant": False,
        "scan_events": [],
        "hearing_log": [],
        "execution_log": [],
        "documents": [],
    }
    case.update(overrides)
    main.db.save_case(case_id, case)
    return case


def test_installable_pwa_shell_manifest_and_root_scoped_service_worker_are_served():
    root = client.get("/")
    assert root.status_code == 200
    assert '/static/manifest.webmanifest' in root.text
    manifest = client.get("/static/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.json()["start_url"] == "/"
    worker = client.get("/service-worker.js")
    assert worker.status_code == 200
    assert worker.headers["Service-Worker-Allowed"] == "/"
    assert worker.headers["Cache-Control"] == "no-cache"
    assert "does not queue custody scans" in worker.text
    for asset in [
        "/static/c2-pwa.bundle.js",
        "/static/tailwind.css",
        "/static/chart.bundle.js",
        "/static/vendor/fontawesome/css/all.min.css",
        "/static/vendor/fonts/outfit/files/outfit-latin-wght-normal.woff2",
    ]:
        assert client.get(asset).status_code == 200, f"static asset must be served locally: {asset}"


def test_case_directory_requires_authentication_and_respects_court_scope():
    visible = add_case("VISIBLE")
    hidden = add_case("FOREIGN", court="Other Fictional Court")

    assert client.get("/api/cases").status_code == 401
    response = client.get("/api/cases", headers=auth_headers("smoke_clerk"))
    assert response.status_code == 200
    visible_ids = {case["case_id"] for case in response.json()}
    assert visible["case_id"] in visible_ids
    assert hidden["case_id"] not in visible_ids
    assert client.get(f"/api/cases/{hidden['case_id']}", headers=auth_headers("smoke_clerk")).status_code == 403


def test_scan_records_authenticated_actor_and_needs_no_typed_staff_id():
    case = add_case("SCAN", custody_alert=True)
    response = client.post("/api/scan", headers=auth_headers("smoke_sheriff"), json={
        "case_id": case["case_id"], "location": "Fictional Registry Desk",
    })
    assert response.status_code == 200
    updated = response.json()
    assert updated["custody_alert"] is False
    assert updated["scan_events"][-1]["location"] == "Fictional Registry Desk"
    assert updated["scan_events"][-1]["staff_id"] == "smoke_sheriff"


def test_qr_token_is_opaque_hashed_and_server_checks_current_sheriff_scope():
    case = add_case("OPAQUE-QR")
    issue_url = f"/api/cases/{case['case_id']}/qr-label"
    assert client.post(issue_url, headers=auth_headers("smoke_sheriff")).status_code == 403
    issued = client.post(issue_url, headers=auth_headers("smoke_clerk"))
    assert issued.status_code == 201
    qr_payload = issued.json()["qr_payload"]
    assert re.fullmatch(r"courtlog:v1:[A-Za-z0-9_-]{43}", qr_payload)
    assert case["case_id"] not in qr_payload
    assert case["case_title"] not in qr_payload
    assert "Cache-Control" in issued.headers and "no-store" in issued.headers["Cache-Control"]

    token_hash = hashlib.sha256(qr_payload.encode("utf-8")).hexdigest()
    stored = main.db.conn.execute(
        "SELECT token_hash, case_id, issued_by FROM case_qr_tokens WHERE token_hash = ?",
        (token_hash,),
    ).fetchone()
    assert stored == (token_hash, case["case_id"], "smoke_clerk")
    assert qr_payload not in str(stored), "the raw QR token is never persisted"

    scan_request = {"qr_payload": qr_payload, "location": "Fictional QR Desk", "staff_id": "forged-client-id"}
    assert client.post("/api/scan/qr", json=scan_request).status_code == 401
    assert client.post("/api/scan/qr", headers=auth_headers("smoke_clerk"), json=scan_request).status_code == 403

    main.db.save_user("smoke_sheriff_unassigned", {
        "user_id": "smoke_sheriff_unassigned", "username": "smoke.sheriff.unassigned",
        "password": get_password_hash("Smoke-Test-Password-2026!"),
        "name": "Fictional Unassigned Sheriff", "role": "Sheriff", "badge": "Automated test account",
        "court": "Smoke Test Court", "division": "Criminal", "disabled": False,
    })
    denied = client.post(
        "/api/scan/qr", headers=auth_headers("smoke_sheriff_unassigned"), json=scan_request,
    )
    assert denied.status_code == 403
    main.db.save_user("smoke_sheriff_other_court", {
        "user_id": "smoke_sheriff_other_court", "username": "smoke.sheriff.other.court",
        "password": get_password_hash("Smoke-Test-Password-2026!"),
        "name": "Fictional Out-of-Court Sheriff", "role": "Sheriff", "badge": "Automated test account",
        "court": "Other Fictional Court", "division": "Criminal", "disabled": False,
    })
    out_of_court = client.post(
        "/api/scan/qr", headers=auth_headers("smoke_sheriff_other_court"), json=scan_request,
    )
    assert out_of_court.status_code == 403

    unknown = client.post("/api/scan/qr", headers=auth_headers("smoke_sheriff"), json={
        "qr_payload": "courtlog:v1:" + "z" * 43, "location": "Fictional QR Desk",
    })
    assert unknown.status_code == 404

    accepted = client.post("/api/scan/qr", headers=auth_headers("smoke_sheriff"), json=scan_request)
    assert accepted.status_code == 200
    updated = accepted.json()
    assert updated["scan_events"][-1]["staff_id"] == "smoke_sheriff"
    assert updated["scan_events"][-1]["location"] == "Fictional QR Desk"
    events = [event for event in main.db.list_audit_events(100) if event["entity_id"] == case["case_id"]]
    qr_event = next(event for event in events if event["action"] == "case.qr_label.issue")
    assert qr_event["actor_user_id"] == "smoke_clerk"
    assert all(qr_payload not in str(event) for event in events)
    assert any(event["action"] == "case.scan" and event["metadata"].get("source") == "qr" for event in events)


def test_existing_qr_label_does_not_bypass_sheriff_handover():
    case = add_case("QR-HANDOVER")
    next_id = "smoke_sheriff_qr_next"
    main.db.save_user(next_id, {
        "user_id": next_id, "username": f"smoke.sheriff.qr.{secrets.token_hex(3)}",
        "password": get_password_hash("Smoke-Test-Password-2026!"),
        "name": "Fictional Receiving Sheriff", "role": "Sheriff", "badge": "Automated test account",
        "court": "Smoke Test Court", "division": "Criminal", "disabled": False,
    })
    issued = client.post(
        f"/api/cases/{case['case_id']}/qr-label", headers=auth_headers("smoke_clerk"),
    )
    assert issued.status_code == 201
    payload = {"qr_payload": issued.json()["qr_payload"], "location": "Fictional Handover Desk"}

    handover = client.post(f"/api/cases/{case['case_id']}/handover", headers=auth_headers("smoke_sheriff"), json={
        "to_sheriff_id": next_id, "location": "Fictional Handover Desk", "reason": "Automated test handover",
    })
    assert handover.status_code == 200
    assert client.post("/api/scan/qr", headers=auth_headers("smoke_sheriff"), json=payload).status_code == 403
    accepted = client.post("/api/scan/qr", headers=auth_headers(next_id), json=payload)
    assert accepted.status_code == 200
    assert accepted.json()["scan_events"][-1]["staff_id"] == next_id


def test_missing_file_state_is_separate_durable_and_resolved_with_reasoned_history():
    recent_scan = main.format_date(datetime.now(timezone.utc))
    case = add_case(
        "MISSING-WORKFLOW",
        filing_date=recent_scan,
        scan_events=[{"location": "Fictional Registry Desk", "timestamp": recent_scan, "staff_id": "smoke_sheriff"}],
        custody_alert=False,
        risk_flag=False,
    )
    report_url = f"/api/cases/{case['case_id']}/report-missing"
    report = client.post(report_url, headers=auth_headers("smoke_sheriff"), json={
        "last_known_location": "Fictional Registry Rack", "notes": "Fictional test record",
    })
    assert report.status_code == 200
    reported = report.json()
    assert reported["file_missing"] is True
    assert reported["custody_alert"] is False, "missing-file state is not the idle-custody clock"
    assert reported["risk_flag"] is False, "missing-file state is not an ML delay-risk override"
    assert reported["file_missing_history"][-1]["action"] == "reported_missing"
    assert reported["file_missing_history"][-1]["actor_user_id"] == "smoke_sheriff"
    check_in = client.post("/api/scan", headers=auth_headers("smoke_sheriff"), json={
        "case_id": case["case_id"], "location": "Fictional re-check-in after report",
    })
    assert check_in.status_code == 200
    assert check_in.json()["file_missing"] is True, "custody check-ins do not resolve a missing-file report"
    assert client.post(report_url, headers=auth_headers("smoke_sheriff"), json={
        "last_known_location": "Another fictional rack", "notes": "Duplicate report",
    }).status_code == 409

    active_alerts = client.get(f"/api/cases/{case['case_id']}/alerts", headers=auth_headers("smoke_sheriff"))
    assert any(item["type"] == "FILE_MISSING" for item in active_alerts.json()["alerts"])
    main.run_compliance_checks_sync()
    after_sweep = main.db.get_case(case["case_id"])
    assert after_sweep["file_missing"] is True
    assert after_sweep["custody_alert"] is False
    assert any(item["type"] == "FILE_MISSING" for item in client.get(
        f"/api/cases/{case['case_id']}/alerts", headers=auth_headers("smoke_sheriff")
    ).json()["alerts"])

    found_url = f"/api/cases/{case['case_id']}/found"
    found_body = {"found_location": "Fictional Registry Desk A", "reason": "Verified physical file recovery"}
    assert client.post(found_url, headers=auth_headers("smoke_clerk"), json=found_body).status_code == 403
    found = client.post(found_url, headers=auth_headers("smoke_sheriff"), json=found_body)
    assert found.status_code == 200
    resolved = found.json()
    assert resolved["file_missing"] is False
    assert resolved["file_missing_report"]["resolved"] is True
    assert resolved["file_missing_report"]["resolved_by"] == "smoke_sheriff"
    assert resolved["file_missing_report"]["found_location"] == found_body["found_location"]
    assert resolved["file_missing_report"]["resolution_reason"] == found_body["reason"]
    history = resolved["file_missing_history"]
    assert [event["action"] for event in history] == ["reported_missing", "found"]
    assert history[-1]["actor_user_id"] == "smoke_sheriff"
    assert history[-1]["reason"] == found_body["reason"]
    assert client.post(found_url, headers=auth_headers("smoke_sheriff"), json=found_body).status_code == 409

    audit = [event for event in main.db.list_audit_events(100) if event["entity_id"] == case["case_id"]]
    found_event = next(event for event in audit if event["action"] == "case.file_missing.found")
    assert found_event["actor_user_id"] == "smoke_sheriff"
    assert found_event["reason"] == found_body["reason"]
    assert not any(item["type"] == "FILE_MISSING" for item in client.get(
        f"/api/cases/{case['case_id']}/alerts", headers=auth_headers("smoke_sheriff")
    ).json()["alerts"])
    main.run_compliance_checks_sync()
    assert main.db.get_case(case["case_id"])["file_missing"] is False


def test_hearing_route_records_workflow_and_live_mode_sends_no_whatsapp_without_consent():
    case = add_case("HEARING")
    response = client.post(f"/api/cases/{case['case_id']}/hearings", headers=auth_headers("smoke_clerk"), json={
        "outcome": "Adjourned", "reason_code": "Fictional test reason", "next_date": "2026-10-22",
    })
    assert response.status_code == 200
    updated = response.json()
    assert updated["adjournment_count"] == 1
    assert updated["hearing_log"][-1]["outcome"] == "Adjourned"
    assert updated["hearing_log"][-1]["reason_code"] == "Fictional test reason"
    logs = client.get("/api/whatsapp/logs", headers=auth_headers("smoke_cr"))
    assert logs.status_code == 200
    assert not any(item.get("case_id") == case["case_id"] for item in logs.json())
    events = [event for event in main.db.list_audit_events(100) if event["entity_id"] == case["case_id"]]
    assert any(event["action"] == "case.hearing.record" and event["actor_user_id"] == "smoke_clerk" for event in events)


def test_dcr_review_acknowledgement_and_escalation_are_durable_and_separate_from_ml_risk(monkeypatch):
    now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(main, "get_current_time", lambda: now)
    case = add_case(
        "DCR-LIFECYCLE",
        filing_date=main.format_date(now),
        scan_events=[{"location": "Fictional Desk", "timestamp": main.format_date(now), "staff_id": "smoke_sheriff"}],
        adjournment_count=4,
        risk_flag=False,
        delay_risk_score=0.3,
        custody_alert=False,
        red_flag_notified_at="2026-09-01T00:00:00Z",
        auto_escalated=True,
    )
    blocked = client.post(f"/api/cases/{case['case_id']}/hearings", headers=auth_headers("smoke_clerk"), json={
        "outcome": "Adjourned", "reason_code": "Fictional review reason", "next_date": "2026-10-22",
    })
    assert blocked.status_code == 400
    pending = main.db.get_case(case["case_id"])
    assert pending["dcr_approval_required"] is True
    assert pending["adjournment_blocked"] is True
    assert pending["risk_flag"] is False, "an application review block must not force the experimental ML flag"
    assert pending["dcr_approval_requested_at"] == main.format_date(now)
    assert [event["action"] for event in pending["dcr_approval_history"]] == ["requested"]

    ack_url = f"/api/cases/{case['case_id']}/dcr-acknowledge"
    assert client.post(ack_url, headers=auth_headers("smoke_clerk"), json={"note": "Not authorized"}).status_code == 403
    acknowledged = client.post(ack_url, headers=auth_headers("smoke_dcr"), json={"note": "Fictional queue review started"})
    assert acknowledged.status_code == 200
    ack_case = acknowledged.json()
    assert ack_case["dcr_approval_required"] is True
    assert ack_case["adjournment_blocked"] is True, "acknowledgement is not an approval or unblock"
    assert ack_case["risk_flag"] is False
    assert ack_case["dcr_acknowledged_by"] == "smoke_dcr"
    assert [event["action"] for event in ack_case["dcr_approval_history"]] == ["requested", "acknowledged"]

    # A sweep at exactly 24 hours does not cross the existing >24-hour threshold.
    monkeypatch.setattr(main, "get_current_time", lambda: now + timedelta(hours=24))
    main.run_compliance_checks_sync()
    at_threshold = main.db.get_case(case["case_id"])
    assert at_threshold["dcr_auto_escalated"] is False
    assert at_threshold["auto_escalated"] is True, "legacy state is not rewritten by the independent ML-risk sweep"
    assert at_threshold["risk_flag"] is False
    assert at_threshold["custody_alert"] is False

    # The in-app escalation is based on the DCR request clock and persists across ML changes.
    escalated_at = now + timedelta(hours=24, seconds=1)
    monkeypatch.setattr(main, "get_current_time", lambda: escalated_at)
    main.run_compliance_checks_sync()
    escalated = main.db.get_case(case["case_id"])
    assert escalated["dcr_auto_escalated"] is True
    assert escalated["dcr_escalated_at"] == main.format_date(escalated_at)
    assert escalated["risk_flag"] is False
    assert [event["action"] for event in escalated["dcr_approval_history"]] == [
        "requested", "acknowledged", "escalated",
    ]

    main.db.update_case(case["case_id"], {"risk_flag": True, "delay_risk_score": 0.95})
    monkeypatch.setattr(main, "get_current_time", lambda: escalated_at + timedelta(minutes=1))
    main.run_compliance_checks_sync()
    assert main.db.get_case(case["case_id"])["dcr_auto_escalated"] is True
    main.db.update_case(case["case_id"], {"risk_flag": False})
    monkeypatch.setattr(main, "get_current_time", lambda: escalated_at + timedelta(minutes=2))
    main.run_compliance_checks_sync()
    risk_cleared = main.db.get_case(case["case_id"])
    assert risk_cleared["dcr_auto_escalated"] is True
    assert risk_cleared["dcr_escalated_at"] == main.format_date(escalated_at)
    assert risk_cleared["risk_flag"] is False

    approved = client.post(
        f"/api/cases/{case['case_id']}/dcr-override",
        headers=auth_headers("smoke_dcr"),
        json={"exceptional_reason": "Fictional test decision reason"},
    )
    assert approved.status_code == 200
    resolved = approved.json()
    assert resolved["dcr_approval_required"] is False
    assert resolved["adjournment_blocked"] is False
    assert resolved["dcr_auto_escalated"] is False
    assert resolved["dcr_escalated_at"] == main.format_date(escalated_at), "resolution preserves escalation history"
    assert resolved["risk_flag"] is False
    assert resolved["dcr_approval_history"][-1]["action"] == "approved"
    assert resolved["dcr_approval_history"][-1]["actor_user_id"] == "smoke_dcr"
    audit = [event for event in main.db.list_audit_events(100) if event["entity_id"] == case["case_id"]]
    assert {event["action"] for event in audit} >= {"case.dcr_review.acknowledge", "case.dcr_override"}


def test_legacy_dcr_escalation_clock_is_initialized_without_using_ml_timestamp(monkeypatch):
    now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(main, "get_current_time", lambda: now)
    case = add_case(
        "LEGACY-DCR-CLOCK",
        dcr_approval_required=True,
        adjournment_blocked=True,
        dcr_auto_escalated=False,
        red_flag_notified_at="2026-09-01T00:00:00Z",
        risk_flag=False,
    )
    main.run_compliance_checks_sync()
    migrated = main.db.get_case(case["case_id"])
    assert migrated["dcr_approval_requested_at"] == main.format_date(now)
    assert migrated["dcr_auto_escalated"] is False, "legacy ML timestamps do not count as DCR request time"
    assert migrated["dcr_approval_history"][-1]["action"] == "request_timestamp_initialized"


def test_judge_alerts_are_scoped_and_labeled_as_operational_prompts(monkeypatch):
    now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(main, "get_current_time", lambda: now)
    assigned = add_case(
        "JUDGE-ALERTS",
        hearing_log=[{"date": main.format_date(now), "outcome": "Adjourned", "next_date": main.format_date(now + timedelta(hours=12))}],
        adjournment_count=4,
        risk_flag=True,
        delay_risk_score=0.91,
    )
    outside = add_case(
        "JUDGE-ALERTS-OUTSIDE",
        assigned_judge_id="another_judge",
        hearing_log=[{"date": main.format_date(now), "outcome": "Adjourned", "next_date": main.format_date(now + timedelta(hours=4))}],
        adjournment_count=4,
        risk_flag=True,
    )
    assert client.get("/api/judge/alerts", headers=auth_headers("smoke_clerk")).status_code == 403
    response = client.get("/api/judge/alerts", headers=auth_headers("smoke_judge"))
    assert response.status_code == 200
    data = response.json()
    this_case_alerts = [item for item in data["alerts"] if item["case_id"] == assigned["case_id"]]
    assert {item["type"] for item in this_case_alerts} == {
        "HEARING_24HR", "ADJOURNMENT_REVIEW", "EXPERIMENTAL_DELAY_RISK",
    }
    assert not any(item["case_id"] == outside["case_id"] for item in data["alerts"])
    assert all("ACJA Sec 396" not in item["message"] for item in this_case_alerts)
    assert all("violates" not in item["message"].lower() for item in this_case_alerts)
    assert data["total_alerts"] == len(data["alerts"])


def test_prediction_is_authenticated_scoped_and_persisted():
    case = add_case("PREDICT")
    response = client.post(f"/api/cases/{case['case_id']}/predict", headers=auth_headers("smoke_clerk"))
    assert response.status_code == 200
    prediction = response.json()
    assert 0.0 <= prediction["delay_risk_score"] <= 1.0
    assert prediction["prediction_source"] in {
        "trained_pipeline", "legacy_model", "heuristic", "heuristic_after_model_error",
    }
    assert prediction["case_id"] == case["case_id"]
    stored = client.get(f"/api/cases/{case['case_id']}", headers=auth_headers("smoke_clerk"))
    assert stored.status_code == 200
    assert stored.json()["delay_risk_score"] == prediction["delay_risk_score"]
    assert stored.json()["prediction_source"] == prediction["prediction_source"]


def test_versioned_pipeline_handles_unseen_demo_categories_and_reports_heuristic_model_errors(monkeypatch):
    rows = []
    for index in range(100):
        adjournments = index % 8
        days = (index * 71) % 1200
        rows.append({
            "case_id": f"FICTIONAL/MODEL-{index}",
            "adjournment_count": adjournments,
            "days_since_filing": days,
            "case_type": "Fictional Civil" if index % 2 else "Fictional Criminal",
            "court": "Demo Court A" if index % 3 else "Demo Court B",
            "target": int(adjournments >= 4 or days >= 700),
        })
    pipeline, _metrics = train_and_evaluate(
        pd.DataFrame(rows), target_column="target", data_provenance="synthetic_demo",
    )
    monkeypatch.setattr(main, "model", pipeline)
    monkeypatch.setattr(main, "encoders", None)
    monkeypatch.setattr(main, "model_metadata", {"format_version": 2})

    estimate = main.run_model_inference({
        "adjournment_count": 2,
        "days_since_filing": 220,
        "case_type": "Previously Unseen Fictional Type",
        "court": "Previously Unseen Fictional Court",
    })
    assert estimate["prediction_source"] == "trained_pipeline"
    assert 0.0 <= estimate["delay_risk_score"] <= 1.0

    class BrokenModel:
        def predict_proba(self, _features):
            raise RuntimeError("synthetic inference error")

    monkeypatch.setattr(main, "model", BrokenModel())
    fallback = main.run_model_inference({
        "adjournment_count": 4, "days_since_filing": 1000, "case_type": "Fictional Civil",
    })
    assert fallback["prediction_source"] == "heuristic_after_model_error"
    assert fallback["delay_risk_score"] == 0.99


def test_model_artifact_loader_enforces_demo_and_permission_provenance(tmp_path):
    model_path = tmp_path / "delay_model.joblib"
    encoders_path = tmp_path / "label_encoders.joblib"
    metadata_path = tmp_path / "delay_model_metadata.json"
    joblib.dump({"fictional": "model"}, model_path)
    metadata_path.write_text(json.dumps({
        "format_version": 2,
        "data_provenance": "synthetic_demo",
        "evaluation": {"split": "stratified_group_holdout_5fold_by_case_id"},
    }), encoding="utf-8")

    assert main.load_delay_model_artifacts(
        str(model_path), str(encoders_path), str(metadata_path), demo_mode=False,
    ) == (None, None, None)
    loaded, encoders, metadata = main.load_delay_model_artifacts(
        str(model_path), str(encoders_path), str(metadata_path), demo_mode=True,
    )
    assert loaded == {"fictional": "model"}
    assert encoders is None
    assert metadata["data_provenance"] == "synthetic_demo"

    metadata_path.write_text(json.dumps({
        "format_version": 2,
        "data_provenance": "permissioned_real",
        "permission_reference_present": True,
        "evaluation": {"split": "stratified_group_holdout_5fold_by_case_id"},
    }), encoding="utf-8")
    assert main.load_delay_model_artifacts(
        str(model_path), str(encoders_path), str(metadata_path), demo_mode=False,
    ) == (None, None, None)
    metadata_path.write_text(json.dumps({
        "format_version": 2,
        "data_provenance": "permissioned_real",
        "permission_reference_present": True,
        "evaluation": {"split": "forward_time_by_case_id:2025-01-01T00:00:00+00:00"},
    }), encoding="utf-8")
    loaded, encoders, metadata = main.load_delay_model_artifacts(
        str(model_path), str(encoders_path), str(metadata_path), demo_mode=False,
    )
    assert loaded == {"fictional": "model"}
    assert encoders is None
    assert metadata["data_provenance"] == "permissioned_real"

    metadata_path.unlink()
    joblib.dump({"fictional": "legacy encoders"}, encoders_path)
    assert main.load_delay_model_artifacts(
        str(model_path), str(encoders_path), str(metadata_path), demo_mode=False,
    ) == (None, None, None)
    assert main.load_delay_model_artifacts(
        str(model_path), str(encoders_path), str(metadata_path), demo_mode=True,
    )[1] == {"fictional": "legacy encoders"}


def test_execution_uses_authenticated_actor_and_completes_delivered_case():


    case = add_case("EXECUTION", judgment_status="Delivered")
    response = client.post(f"/api/cases/{case['case_id']}/execution", headers=auth_headers("smoke_sheriff"), json={
        "action": "Writ of Fi Fa Completed", "sheriff_id": "forged-client-id",
    })
    assert response.status_code == 200
    updated = response.json()
    assert updated["judgment_status"] == "Executed"
    assert updated["execution_log"][-1]["sheriff_id"] == "smoke_sheriff"
    events = [event for event in main.db.list_audit_events(100) if event["entity_id"] == case["case_id"]]
    assert any(event["action"] == "case.execution.record" and event["actor_user_id"] == "smoke_sheriff" for event in events)


def test_case_creation_and_user_management_enforce_roles():
    payload = {
        "case_id": f"API/{secrets.token_hex(4)}/CREATED",
        "case_type": "Civil",
        "court": "Smoke Test Court",
        "counsel_phone": "+2348031234567",
        "litigant_phone": "+2348037654321",
    }
    assert client.post("/api/cases", headers=auth_headers("smoke_sheriff"), json=payload).status_code == 403
    created_case = client.post("/api/cases", headers=auth_headers("smoke_clerk"), json=payload)
    assert created_case.status_code == 201
    assert created_case.json()["assigned_judge_id"] is None

    new_user = {
        "username": f"smoke.new.{secrets.token_hex(3)}",
        "initial_password": "Temporary-Smoke-Password-2026!",
        "name": "Fictional newly provisioned user",
        "role": "Clerk",
        "badge": "Automated test account",
        "court": "Smoke Test Court",
        "division": "Criminal",
    }
    assert client.post("/api/users", headers=auth_headers("smoke_clerk"), json=new_user).status_code == 403
    created_user = client.post("/api/users", headers=auth_headers("smoke_cr"), json=new_user)
    assert created_user.status_code == 201
    assert created_user.json()["must_change_password"] is True
    assert "password" not in created_user.json()


def test_cron_and_exports_require_authorized_roles_and_scope():
    case = add_case("REPORT", party_contact={"counsel_phone": "+2348012345678", "litigant_phone": "+2348098765432"})
    assert client.post("/api/cron").status_code == 401
    assert client.post("/api/cron", headers=auth_headers("smoke_clerk")).status_code == 403
    sweep = client.post("/api/cron", headers=auth_headers("smoke_cr"))
    assert sweep.status_code == 200
    assert "execution_review_prompts" in sweep.json()["stats"]
    assert "non_compliant_enforcements" not in sweep.json()["stats"]

    report = client.get("/api/export/prototype-summary", headers=auth_headers("smoke_dcr"))
    assert report.status_code == 200
    payload = report.json()
    report_ids = {item["case_id"] for item in payload["case_summaries"]}
    assert case["case_id"] in report_ids
    assert "not an official NJC/NCMS submission" in payload["intended_use"]
    assert "speedy_trial_compliance_score" not in payload["summary"]
    assert "audited_cases" not in payload, "reports omit full case documents and party contact details"
    assert "+2348012345678" not in str(payload) and "+2348098765432" not in str(payload)
    weekly = client.get("/api/export/dcr-weekly", headers=auth_headers("smoke_dcr"))
    assert weekly.status_code == 200
    assert "division_compliance_score" not in weekly.json()["summary"]
    assert "experimental_delay_risk_flags" in weekly.json()["summary"]
    assert client.get("/api/export/prototype-summary").status_code == 401

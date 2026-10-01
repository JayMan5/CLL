"""Authenticated workflow smoke tests using an isolated, fictional SQLite database."""
import os
import secrets
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


def test_hearing_route_records_workflow_and_live_mode_sends_no_simulated_webhook():
    case = add_case("HEARING")
    response = client.post(f"/api/cases/{case['case_id']}/hearings", headers=auth_headers("smoke_clerk"), json={
        "outcome": "Adjourned", "reason_code": "Fictional test reason", "next_date": "2026-10-22",
    })
    assert response.status_code == 200
    updated = response.json()
    assert updated["adjournment_count"] == 1
    assert updated["hearing_log"][-1]["outcome"] == "Adjourned"
    assert updated["hearing_log"][-1]["reason_code"] == "Fictional test reason"
    assert client.get("/api/whatsapp/logs", headers=auth_headers("smoke_cr")).status_code == 404
    events = [event for event in main.db.list_audit_events(100) if event["entity_id"] == case["case_id"]]
    assert any(event["action"] == "case.hearing.record" and event["actor_user_id"] == "smoke_clerk" for event in events)


def test_prediction_is_authenticated_scoped_and_persisted():
    case = add_case("PREDICT")
    response = client.post(f"/api/cases/{case['case_id']}/predict", headers=auth_headers("smoke_clerk"))
    assert response.status_code == 200
    prediction = response.json()
    assert 0.0 <= prediction["delay_risk_score"] <= 1.0
    assert prediction["case_id"] == case["case_id"]
    stored = client.get(f"/api/cases/{case['case_id']}", headers=auth_headers("smoke_clerk"))
    assert stored.status_code == 200
    assert stored.json()["delay_risk_score"] == prediction["delay_risk_score"]


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
    case = add_case("REPORT")
    assert client.post("/api/cron").status_code == 401
    assert client.post("/api/cron", headers=auth_headers("smoke_clerk")).status_code == 403
    assert client.post("/api/cron", headers=auth_headers("smoke_cr")).status_code == 200

    report = client.get("/api/export/njc", headers=auth_headers("smoke_dcr"))
    assert report.status_code == 200
    report_ids = {item["case_id"] for item in report.json()["audited_cases"]}
    assert case["case_id"] in report_ids
    assert client.get("/api/export/njc").status_code == 401

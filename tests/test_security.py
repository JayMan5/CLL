"""Security regression tests: never import the app against the committed database."""
import os
import tempfile
import json
import sqlite3
import secrets
import hashlib
import hmac
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import requests

_runtime = tempfile.TemporaryDirectory()
os.environ['COURTLOG_DB_PATH'] = str(Path(_runtime.name) / 'test.db')
os.environ['JWT_PRIVATE_KEY_PATH'] = str(Path(_runtime.name) / 'private.pem')
os.environ['JWT_PUBLIC_KEY_PATH'] = str(Path(_runtime.name) / 'public.pem')
os.environ['DEMO_MODE'] = 'false'
os.environ['COOKIE_SECURE'] = 'false'  # TestClient uses HTTP; production must set this true.

from fastapi.testclient import TestClient
import pytest
from backend import main
from backend.auth import create_access_token, create_refresh_token, REFRESH_TOKEN_EXPIRE_DAYS
from backend.database import SQLiteDatabase, get_password_hash, verify_password
from backend.whatsapp import (
    hash_phone as hash_whatsapp_phone,
    mask_phone as mask_whatsapp_phone,
    normalize_whatsapp_phone,
    create_manual_test_message,
    deliver_whatsapp_message,
    send_adjournment_broadcast,
)

# TestClient uses HTTP; production configuration remains secure by default.
main.COOKIE_SECURE = False

# Explicit fictional fixtures; production startup never receives these default credentials.
_TEST_USERS = [
    ('usr_sheriff_01', 'sheriff', 'Sheriff', 'FHC Abuja Court 4', 'Criminal', '123'),
    ('usr_clerk_01', 'clerk', 'Clerk', 'FHC Abuja Court 4', 'Criminal', '123'),
    ('usr_dcr_01', 'dcr', 'DCR', 'FHC Abuja', 'Criminal', '123'),
    ('usr_cr_01', 'cr', 'Chief Registrar', 'All Courts', 'All Divisions', '12345'),
    ('usr_judge_01', 'judge', 'Judge', 'FHC Abuja Court 4', 'Criminal', '123'),
]
for user_id, username, role, court, division, password in _TEST_USERS:
    main.db.save_user(user_id, {
        'user_id':user_id, 'username':username, 'password':get_password_hash(password),
        'name':f'Test {role}', 'role':role, 'badge':'Fictional Test Account',
        'court':court, 'division':division,
    })

client = TestClient(main.app)

def issue_session(uid):
    user = main.db.get_user(uid)
    sid = secrets.token_urlsafe(32)
    jti = secrets.token_urlsafe(32)
    expires = int((datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp())
    main.db.create_auth_session(sid, uid, jti, expires)
    claims = {'sub': uid, 'role': user['role'], 'sid': sid}
    access = create_access_token(claims)
    refresh = create_refresh_token({**claims, 'jti': jti})
    return {'Authorization': 'Bearer ' + access}, refresh

def headers(uid):
    return issue_session(uid)[0]

def fixture_case(cid, court='FHC Abuja Court 4'):
    case = {'case_id': cid, 'court': court, 'assigned_division': 'Criminal',
            'assigned_judge_id': 'usr_judge_01', 'assigned_sheriff_id': 'usr_sheriff_01',
            'filing_date': '2026-10-01T00:00:00Z', 'judgment_status': 'Pending',
            'scan_events': [], 'hearing_log': [], 'execution_log': [], 'adjournment_count': 0}
    main.db.save_case(cid, case)
    return case

def test_exposed_routes_require_authentication():
    fixture_case('SEC/1')
    for method, path in [('get', '/api/users'), ('get', '/api/audit/events'),
                         ('get', '/api/cases/SEC/1'),
                         ('post', '/api/cases/SEC/1/predict'), ('post', '/api/cron'),
                         ('get', '/api/whatsapp/logs')]:
        assert getattr(client, method)(path).status_code == 401
    assert client.post('/api/whatsapp/webhook-simulator', json={}).status_code == 404

def test_user_hashes_never_returned():
    assert client.get('/api/users', headers=headers('usr_clerk_01')).status_code == 403
    result = client.get('/api/users', headers=headers('usr_cr_01'))
    assert result.status_code == 200
    assert all('password' not in user for user in result.json())

def test_cross_court_read_and_write_denied():
    fixture_case('SEC/OTHER', 'Other Court')
    h = headers('usr_clerk_01')
    assert client.get('/api/cases/SEC/OTHER', headers=h).status_code == 403
    assert client.post('/api/scan', headers=h, json={'case_id':'SEC/OTHER', 'location':'Desk', 'staff_id':'forged'}).status_code == 403
    assert client.post('/api/cases/SEC/OTHER/predict', headers=h).status_code == 403
    assert all(c['case_id'] != 'SEC/OTHER' for c in client.get('/api/predict/batch', headers=h).json())

    # A stale/mis-scoped explicit Sheriff assignment does not bypass the court boundary.
    sheriff_headers = headers('usr_sheriff_01')
    assert client.get('/api/cases/SEC/OTHER', headers=sheriff_headers).status_code == 403
    assert all(c['case_id'] != 'SEC/OTHER' for c in client.get('/api/cases', headers=sheriff_headers).json())

def test_dcr_cannot_reassign_a_case_outside_their_division():
    case = fixture_case('SEC/DCR-REASSIGN')
    response = client.post(
        '/api/cases/SEC/DCR-REASSIGN/reassign', headers=headers('usr_dcr_01'),
        json={'new_division':'Civil', 'reason':'Attempted cross-division move'},
    )
    assert response.status_code == 403
    assert main.db.get_case(case['case_id'])['assigned_division'] == 'Criminal'


def test_judge_case_reads_and_alerts_are_court_scoped():
    case = fixture_case('SEC/JUDGE-SCOPE', 'Other Court')
    case['assigned_judge_id'] = 'usr_judge_01'  # stale or malformed cross-court assignment
    case['risk_flag'] = True
    main.db.save_case(case['case_id'], case)
    main.db.save_user('usr_judge_other', {
        'user_id':'usr_judge_other', 'username':'judge.other', 'password':get_password_hash('123'),
        'name':'Other Court Judge', 'role':'Judge', 'badge':'Fictional Test Account',
        'court':'Other Court', 'division':'Criminal',
    })

    current_judge_headers = headers('usr_judge_01')
    assert client.get(f"/api/cases/{case['case_id']}", headers=current_judge_headers).status_code == 403
    alerts = client.get('/api/judge/alerts', headers=current_judge_headers)
    assert alerts.status_code == 200
    assert all(item.get('case_id') != case['case_id'] for item in alerts.json()['alerts'])

    registrar_headers = headers('usr_cr_01')
    wrong_court = client.post(
        f"/api/cases/{case['case_id']}/assign-judge", headers=registrar_headers,
        json={'judge_id':'usr_judge_01', 'reason':'Wrong court'},
    )
    assert wrong_court.status_code == 422
    assert main.db.get_case(case['case_id'])['assigned_judge_id'] == 'usr_judge_01'

    assigned = client.post(
        f"/api/cases/{case['case_id']}/assign-judge", headers=registrar_headers,
        json={'judge_id':'usr_judge_other', 'reason':'Correct court'},
    )
    assert assigned.status_code == 200
    assert client.get(f"/api/cases/{case['case_id']}", headers=current_judge_headers).status_code == 403
    other_judge_headers = headers('usr_judge_other')
    assert client.get(f"/api/cases/{case['case_id']}", headers=other_judge_headers).status_code == 200
    other_alerts = client.get('/api/judge/alerts', headers=other_judge_headers)
    assert any(item.get('case_id') == case['case_id'] for item in other_alerts.json()['alerts'])


def test_scan_identity_comes_from_token():
    fixture_case('SEC/SCAN')
    response = client.post('/api/scan', headers=headers('usr_sheriff_01'),
                           json={'case_id':'SEC/SCAN', 'location':'Desk'})
    assert response.status_code == 200
    assert response.json()['scan_events'][-1]['staff_id'] == 'usr_sheriff_01'


def test_registry_assigns_case_to_court_sheriff_and_receipt_uses_session_identity():
    case = fixture_case('SEC/SHERIFF-ASSIGNMENT')
    case['assigned_sheriff_id'] = None
    case['custody_history'] = []
    main.db.save_case(case['case_id'], case)

    sheriff_headers = headers('usr_sheriff_01')
    assert client.get('/api/cases/SEC/SHERIFF-ASSIGNMENT', headers=sheriff_headers).status_code == 403
    assert all(item['case_id'] != case['case_id'] for item in client.get('/api/cases', headers=sheriff_headers).json())

    clerk_headers = headers('usr_clerk_01')
    candidates = client.get('/api/cases/SEC/SHERIFF-ASSIGNMENT/sheriffs', headers=clerk_headers)
    assert candidates.status_code == 200
    assert [item['user_id'] for item in candidates.json()] == ['usr_sheriff_01']
    assert all('password' not in item for item in candidates.json())

    assigned = client.post(
        '/api/cases/SEC/SHERIFF-ASSIGNMENT/assign-sheriff', headers=clerk_headers,
        json={'sheriff_id':'usr_sheriff_01', 'reason':'Registry dispatch'},
    )
    assert assigned.status_code == 200
    body = assigned.json()
    assert body['assigned_sheriff_id'] == 'usr_sheriff_01'
    assert body['custody_history'][-1]['action'] == 'assigned'
    assert body['custody_history'][-1]['actor_user_id'] == 'usr_clerk_01'
    assert body['custody_history'][-1]['reason'] == 'Registry dispatch'
    assert client.get('/api/cases/SEC/SHERIFF-ASSIGNMENT', headers=sheriff_headers).status_code == 200

    receipt = client.post(
        '/api/scan', headers=sheriff_headers,
        json={'case_id':case['case_id'], 'location':'Registry Desk', 'staff_id':'forged-client-id'},
    )
    assert receipt.status_code == 200
    assert receipt.json()['scan_events'][-1]['staff_id'] == 'usr_sheriff_01'

    audit = [event for event in main.db.list_audit_events(100) if event['entity_id'] == case['case_id']]
    assert any(event['action'] == 'case.sheriff.assign' and event['actor_user_id'] == 'usr_clerk_01' for event in audit)
    assert any(event['action'] == 'case.scan' and event['actor_user_id'] == 'usr_sheriff_01' for event in audit)


def test_sheriff_assignment_is_court_scoped_and_handover_revokes_previous_custody():
    case = fixture_case('SEC/SHERIFF-HANDOVER')
    case['custody_history'] = []
    main.db.save_case(case['case_id'], case)
    main.db.save_user('usr_sheriff_02', {
        'user_id':'usr_sheriff_02', 'username':'sheriff.two', 'password':get_password_hash('123'),
        'name':'Test Sheriff Two', 'role':'Sheriff', 'badge':'Fictional Test Account',
        'court':'FHC Abuja Court 4', 'division':'Criminal',
    })
    main.db.save_user('usr_sheriff_other', {
        'user_id':'usr_sheriff_other', 'username':'sheriff.other', 'password':get_password_hash('123'),
        'name':'Out-of-court Sheriff', 'role':'Sheriff', 'badge':'Fictional Test Account',
        'court':'Other Court', 'division':'Criminal',
    })

    clerk_headers = headers('usr_clerk_01')
    candidates = client.get('/api/cases/SEC/SHERIFF-HANDOVER/sheriffs', headers=clerk_headers)
    assert candidates.status_code == 200
    candidate_ids = {item['user_id'] for item in candidates.json()}
    assert candidate_ids == {'usr_sheriff_02'}
    invalid_assignment = client.post(
        '/api/cases/SEC/SHERIFF-HANDOVER/assign-sheriff', headers=clerk_headers,
        json={'sheriff_id':'usr_sheriff_other', 'reason':'Wrong court'},
    )
    assert invalid_assignment.status_code == 422
    assert main.db.get_case(case['case_id'])['assigned_sheriff_id'] == 'usr_sheriff_01'

    handover = client.post(
        '/api/cases/SEC/SHERIFF-HANDOVER/handover', headers=headers('usr_sheriff_01'),
        json={
            'to_sheriff_id':'usr_sheriff_02', 'location':'Registry Desk',
            'reason':'End of duty', 'from_sheriff_id':'usr_sheriff_other',
        },
    )
    assert handover.status_code == 200
    body = handover.json()
    assert body['assigned_sheriff_id'] == 'usr_sheriff_02'
    assert body['custody_history'][-1] == {
        'action':'handover', 'from_sheriff_id':'usr_sheriff_01',
        'to_sheriff_id':'usr_sheriff_02', 'actor_user_id':'usr_sheriff_01',
        'timestamp':body['custody_history'][-1]['timestamp'],
        'location':'Registry Desk', 'reason':'End of duty',
    }
    assert client.get('/api/cases/SEC/SHERIFF-HANDOVER', headers=headers('usr_sheriff_01')).status_code == 403
    new_sheriff_headers = headers('usr_sheriff_02')
    assert client.get('/api/cases/SEC/SHERIFF-HANDOVER', headers=new_sheriff_headers).status_code == 200
    assert any(item['case_id'] == case['case_id'] for item in client.get('/api/cases', headers=new_sheriff_headers).json())
    audit = [event for event in main.db.list_audit_events(100) if event['entity_id'] == case['case_id']]
    assert any(event['action'] == 'case.sheriff.handover' and event['actor_user_id'] == 'usr_sheriff_01' for event in audit)


def test_deleted_account_cannot_use_or_refresh_token():
    user = {'user_id':'usr_deleted', 'role':'Clerk', 'court':'FHC Abuja Court 4'}
    main.db.save_user(user['user_id'], user)
    h, refresh = issue_session(user['user_id'])
    main.db.delete_user(user['user_id'])
    assert client.get('/api/cases', headers=h).status_code == 401
    with TestClient(main.app) as refresh_client:
        refresh_client.cookies.set(main.REFRESH_COOKIE_NAME, refresh, path=main.REFRESH_COOKIE_PATH)
        assert refresh_client.post('/api/refresh').status_code == 401

def test_admin_self_deletion_denied():
    assert client.delete('/api/users/usr_cr_01', headers=headers('usr_cr_01')).status_code == 409

def test_dcr_export_is_scoped():
    fixture_case('SEC/CIVIL')['assigned_division'] = 'Civil'
    case = main.db.get_case('SEC/CIVIL'); case['assigned_division'] = 'Civil'
    main.db.save_case('SEC/CIVIL', case)
    response = client.get('/api/export/prototype-summary', headers=headers('usr_dcr_01'))
    assert response.status_code == 200
    payload = response.json()
    assert payload['scope'] == 'Criminal'
    assert 'SEC/CIVIL' not in {item['case_id'] for item in payload['case_summaries']}
    assert 'audited_cases' not in payload

    dcr = main.db.get_user('usr_dcr_01')
    original_division = dcr['division']
    try:
        dcr['division'] = 'All Divisions'
        main.db.save_user('usr_dcr_01', dcr)
        assert client.get('/api/export/dcr-weekly', headers=headers('usr_dcr_01')).status_code == 403
        assert client.get('/api/export/prototype-summary', headers=headers('usr_dcr_01')).status_code == 403
    finally:
        dcr['division'] = original_division
        main.db.save_user('usr_dcr_01', dcr)

def test_hostile_case_identifiers_rejected():
    h = headers('usr_cr_01')
    for cid in ('../../tmp/escape', "X');alert(1)//", '<img>', 'A//B'):
        response = client.post('/api/cases', headers=h, json={
            'case_id': cid, 'case_type':'Criminal', 'court':'FHC Abuja Court 4',
            'counsel_phone':'+2348000000001', 'litigant_phone':'+2348000000002'})
        assert response.status_code == 422


def test_login_uses_httponly_refresh_cookie_and_logout_revokes_access():
    with TestClient(main.app) as session_client:
        login = session_client.post('/api/login', json={'username':'cr', 'password':'12345'})
        assert login.status_code == 200
        assert 'refresh_token' not in login.json()
        access = login.json()['access_token']
        cookie = login.cookies.get(main.REFRESH_COOKIE_NAME)
        assert cookie
        set_cookie = login.headers.get('set-cookie', '').lower()
        assert 'httponly' in set_cookie and 'samesite=strict' in set_cookie and 'path=/api' in set_cookie
        assert 'secure' not in set_cookie

        assert session_client.get('/api/users', headers={'Authorization': f'Bearer {access}'}).status_code == 200
        refresh = session_client.post('/api/refresh')
        assert refresh.status_code == 200
        assert refresh.json()['access_token']
        assert 'refresh_token' not in refresh.json()

        logout = session_client.post('/api/logout')
        assert logout.status_code == 200
        assert 'max-age=0' in logout.headers.get('set-cookie', '').lower()
        assert session_client.get('/api/users', headers={'Authorization': f'Bearer {access}'}).status_code == 401
        assert session_client.get('/api/users', headers={'Authorization': f"Bearer {refresh.json()['access_token']}"}).status_code == 401
        assert session_client.post('/api/refresh').status_code == 401
        auth_events = [
            e for e in main.db.list_audit_events(100)
            if e['actor_user_id'] == 'usr_cr_01' and e['action'] in {'auth.login.success', 'auth.logout'}
        ]
        assert {e['action'] for e in auth_events} >= {'auth.login.success', 'auth.logout'}
        assert all(len(e['entity_id']) == 64 for e in auth_events)


def test_disabled_user_cannot_login():
    user = {
        'user_id':'usr_disabled', 'username':'disabled', 'password':get_password_hash('Temporary-Password-1!'),
        'role':'Clerk', 'court':'FHC Abuja Court 4', 'division':'Criminal', 'disabled':True,
    }
    main.db.save_user(user['user_id'], user)
    response = client.post('/api/login', json={'username':'disabled', 'password':'Temporary-Password-1!'})
    assert response.status_code == 401
    disabled_headers, _ = issue_session(user['user_id'])
    assert client.get('/api/cases', headers=disabled_headers).status_code == 401
    user['disabled'] = False
    main.db.save_user(user['user_id'], user)
    assert client.get('/api/cases', headers=disabled_headers).status_code == 401


def test_admin_creates_unique_account_and_initial_password_is_mandatory():
    with TestClient(main.app) as account_client:
        admin_headers = headers('usr_cr_01')
        payload = {
            'username':'new.clerk', 'initial_password':'Temporary-Password-1!',
            'name':'New Registry Clerk', 'role':'Clerk', 'badge':'Registry Staff',
            'court':'FHC Abuja Court 4', 'division':'Criminal',
        }
        assert account_client.post('/api/users', headers=admin_headers, json={**payload, 'role':'Root'}).status_code == 422
        assert account_client.post('/api/users', headers=admin_headers, json={**payload, 'initial_password':'short'}).status_code == 422
        assert account_client.post('/api/users', headers=admin_headers, json={**payload, 'court':'All Courts'}).status_code == 422
        created = account_client.post('/api/users', headers=admin_headers, json=payload)
        assert created.status_code == 201
        profile = created.json()
        assert profile['username'] == 'new.clerk'
        assert profile['must_change_password'] is True
        assert 'password' not in profile and 'initial_password' not in profile

        duplicate = account_client.post('/api/users', headers=admin_headers, json={**payload, 'username':'NEW.CLERK'})
        assert duplicate.status_code == 409

        login = account_client.post('/api/login', json={'username':'new.clerk', 'password':payload['initial_password']})
        assert login.status_code == 200
        access = login.json()['access_token']
        assert login.json()['user']['must_change_password'] is True
        auth_header = {'Authorization': f'Bearer {access}'}
        blocked = account_client.get('/api/cases', headers=auth_header)
        assert blocked.status_code == 403
        assert blocked.headers.get('X-Password-Change-Required') == 'true'

        changed = account_client.post('/api/users/me/password', headers=auth_header, json={
            'current_password':payload['initial_password'], 'new_password':'Better-Password-2!'
        })
        assert changed.status_code == 200
        assert changed.json()['relogin_required'] is True
        assert account_client.get('/api/cases', headers=auth_header).status_code == 401
        assert account_client.post('/api/login', json={'username':'new.clerk', 'password':payload['initial_password']}).status_code == 401

        relogin = account_client.post('/api/login', json={'username':'new.clerk', 'password':'Better-Password-2!'})
        assert relogin.status_code == 200
        assert relogin.json()['user']['must_change_password'] is False
        relogin_headers = {'Authorization': f"Bearer {relogin.json()['access_token']}"}
        assert account_client.get('/api/cases', headers=relogin_headers).status_code == 200

        reset_password = 'Reset-Temporary-3!'
        reset = account_client.post(
            f"/api/users/{profile['user_id']}/reset-password", headers=admin_headers,
            json={'temporary_password':reset_password},
        )
        assert reset.status_code == 200
        assert account_client.get('/api/cases', headers=relogin_headers).status_code == 401
        assert account_client.post('/api/login', json={'username':'new.clerk', 'password':'Better-Password-2!'}).status_code == 401
        reset_login = account_client.post('/api/login', json={'username':'new.clerk', 'password':reset_password})
        assert reset_login.status_code == 200
        assert reset_login.json()['user']['must_change_password'] is True
        assert account_client.get('/api/cases', headers={'Authorization': f"Bearer {reset_login.json()['access_token']}"}).status_code == 403


def test_legacy_user_table_migrates_username_index_and_session_store(tmp_path, monkeypatch):
    legacy_path = tmp_path / 'legacy.db'
    connection = sqlite3.connect(legacy_path)
    connection.execute('CREATE TABLE users (user_id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    connection.execute('INSERT INTO users (user_id, data) VALUES (?, ?)', (
        'legacy_user', json.dumps({'user_id':'legacy_user', 'username':'Legacy.User', 'password':'hash', 'role':'Clerk'}),
    ))
    connection.commit()
    connection.close()

    monkeypatch.setenv('COURTLOG_DB_PATH', str(legacy_path))
    migrated = SQLiteDatabase()
    assert migrated.get_user('legacy_user')['username'] == 'Legacy.User'
    migrated_tables = {
        row[0] for row in migrated.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {'auth_sessions', 'auth_login_attempts', 'audit_events'} <= migrated_tables
    with pytest.raises(sqlite3.IntegrityError):
        migrated.save_user('duplicate_user', {'user_id':'duplicate_user', 'username':'legacy.user', 'role':'Clerk'})
    migrated.conn.close()


def test_refresh_cookie_secure_flag_can_be_enabled(monkeypatch):
    monkeypatch.setattr(main, 'COOKIE_SECURE', True)
    response = main.Response()
    main._set_refresh_cookie(response, 'test-token')
    cookie_headers = [value.decode().lower() for name, value in response.raw_headers if name.lower() == b'set-cookie']
    assert any('httponly' in value and 'secure' in value and 'samesite=strict' in value for value in cookie_headers)


def test_live_bootstrap_is_env_driven_and_demo_accounts_are_disabled(tmp_path, monkeypatch):
    database_path = tmp_path / 'demo-then-live.db'
    monkeypatch.setenv('COURTLOG_DB_PATH', str(database_path))
    monkeypatch.setenv('DEMO_MODE', 'true')
    demo_db = SQLiteDatabase()
    demo_users = demo_db.list_users()
    assert len(demo_users) == 5
    assert all(user.get('demo_only') and not user.get('disabled') for user in demo_users)
    demo_db.conn.close()

    monkeypatch.setenv('DEMO_MODE', 'false')
    monkeypatch.delenv('COURTLOG_BOOTSTRAP_USERNAME', raising=False)
    monkeypatch.delenv('COURTLOG_BOOTSTRAP_PASSWORD', raising=False)
    live_db = SQLiteDatabase()
    assert all(user.get('disabled') for user in live_db.list_users())
    live_db.conn.close()

    monkeypatch.setenv('COURTLOG_BOOTSTRAP_USERNAME', 'secure.admin')
    monkeypatch.setenv('COURTLOG_BOOTSTRAP_PASSWORD', 'Long-Bootstrap-Password-4!')
    provisioned_db = SQLiteDatabase()
    accounts = provisioned_db.list_users()
    bootstrap = next(user for user in accounts if user.get('username') == 'secure.admin')
    assert bootstrap['role'] == 'Chief Registrar'
    assert bootstrap['must_change_password'] is True
    assert verify_password('Long-Bootstrap-Password-4!', bootstrap['password'])
    assert all(user.get('disabled') for user in accounts if user.get('demo_only'))
    provisioned_db.conn.close()


def test_live_mode_does_not_send_whatsapp_without_database_or_configuration():
    assert client.get('/api/config').json() == {'demo_mode':False}
    with patch('backend.whatsapp.requests.post') as send:
        result = send_adjournment_broadcast('SEC/NO-SEND', '2026-10-02', 'Test only')
        send.assert_not_called()
    assert result['status'] == 'disabled'
    assert client.get('/api/whatsapp/logs', headers=headers('usr_cr_01')).status_code == 200
    assert client.get('/api/whatsapp/logs', headers=headers('usr_clerk_01')).status_code == 403
    assert client.get('/api/whatsapp/status', headers=headers('usr_clerk_01')).status_code == 403


def test_demo_simulator_requires_configured_secret(monkeypatch):
    monkeypatch.setattr(main, 'DEMO_MODE_ENABLED', True)
    monkeypatch.setenv('SIMULATOR_SECRET', 'demo-secret-123')
    assert client.post('/api/whatsapp/webhook-simulator', json={}).status_code == 401
    denied = client.post('/api/whatsapp/webhook-simulator', headers={'X-Simulator-Secret':'wrong'}, json={})
    assert denied.status_code == 401
    accepted = client.post('/api/whatsapp/webhook-simulator', headers={'X-Simulator-Secret':'demo-secret-123'}, json={'simulated_text':'TEST'})
    assert accepted.status_code == 200
    logs = client.get('/api/whatsapp/logs', headers=headers('usr_cr_01'))
    assert logs.status_code == 200
    assert logs.json()[0]['status'] == 'simulated_webhook'
    assert 'payload' not in logs.json()[0]
    main.whatsapp_logs.clear()


def configure_whatsapp_cloud(monkeypatch, *, demo=False, enabled=True):
    values = {
        'DEMO_MODE': 'true' if demo else 'false',
        'WHATSAPP_ENABLED': 'true' if enabled else 'false',
        'WHATSAPP_ACCESS_TOKEN': 'fake-test-token-not-a-secret',
        'WHATSAPP_PHONE_NUMBER_ID': '123456789012345',
        'WHATSAPP_API_VERSION': 'v26.0',
        'WHATSAPP_TEMPLATE_NAME': 'courtlog_schedule_notice',
        'WHATSAPP_TEMPLATE_LANGUAGE': 'en',
        'WHATSAPP_APP_SECRET': 'fake-meta-app-secret-for-tests',
        'WHATSAPP_WEBHOOK_VERIFY_TOKEN': 'test-webhook-verify-token',
        'WHATSAPP_CONSENT_HASH_KEY': 'test-consent-hash-key-' + ('x' * 48),
        'WHATSAPP_CONSENT_NOTICE_VERSION': 'courtlog-test-v1',
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize(('phone', 'expected'), [
    ('+2348031234567', '+2348031234567'),
    ('0803 123 4567', '+2348031234567'),
    ('2348031234567', '+2348031234567'),
    ('00 44 20 7946 0123', '+442079460123'),
])
def test_whatsapp_phone_normalizer_accepts_valid_e164_forms(phone, expected):
    assert normalize_whatsapp_phone(phone) == expected


@pytest.mark.parametrize('phone', [
    '+234803abc567',
    'call 08031234567',
    '+2348031234567/99',
    '+2348031234567 ext 2',
    '   ',
])
def test_whatsapp_phone_normalizer_rejects_letters_and_unsupported_characters(phone):
    with pytest.raises(ValueError):
        normalize_whatsapp_phone(phone)


def record_opt_in(phone, *, evidence='CONSENT-TEST-01'):
    response = client.post('/api/whatsapp/preferences', headers=headers('usr_cr_01'), json={
        'phone': phone,
        'status': 'opted_in',
        'consent_source': 'test recipient written permission',
        'evidence_reference': evidence,
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_whatsapp_preferences_require_consent_and_do_not_return_raw_phone(monkeypatch):
    configure_whatsapp_cloud(monkeypatch, enabled=False)
    phone = '+2348031234567'
    response = client.post('/api/whatsapp/preferences', headers=headers('usr_cr_01'), json={
        'phone': phone, 'status': 'opted_in', 'consent_source': 'signed form',
        'evidence_reference': 'FICTIONAL-CONSENT-01',
    })
    assert response.status_code == 200, response.text
    assert phone not in response.text
    assert response.json()['recipient'] == mask_whatsapp_phone(phone)
    preference = main.db.get_whatsapp_preference(hash_whatsapp_phone(phone))
    assert preference['status'] == 'opted_in'
    assert preference['evidence_reference'] == 'FICTIONAL-CONSENT-01'

    missing_evidence = client.post('/api/whatsapp/preferences', headers=headers('usr_cr_01'), json={
        'phone': phone, 'status': 'opted_in', 'consent_source': 'signed form',
    })
    assert missing_evidence.status_code == 422
    forbidden = client.post('/api/whatsapp/preferences', headers=headers('usr_clerk_01'), json={
        'phone': phone, 'status': 'opted_out', 'consent_source': 'recipient request',
    })
    assert forbidden.status_code == 403

    opted_out = client.post('/api/whatsapp/preferences', headers=headers('usr_cr_01'), json={
        'phone': phone, 'status': 'opted_out', 'consent_source': 'recipient request',
    })
    assert opted_out.status_code == 200
    assert main.db.get_whatsapp_preference(hash_whatsapp_phone(phone))['status'] == 'opted_out'
    assert phone not in json.dumps(main.db.list_audit_events(50))


def test_whatsapp_adjournment_sends_only_generic_template_to_opted_in_party_once(monkeypatch):
    configure_whatsapp_cloud(monkeypatch)
    case_id = 'SEC/WA-CLOUD-ONE'
    phone_counsel = '+2348031234567'
    phone_litigant = '+2348037654321'
    case = fixture_case(case_id)
    case['party_contact'] = {'counsel_phone': phone_counsel, 'litigant_phone': phone_litigant}
    main.db.save_case(case_id, case)
    record_opt_in(phone_counsel, evidence='FICTIONAL-CONSENT-COUNSEL')

    class FakeMetaResponse:
        status_code = 200
        def json(self):
            return {'messages': [{'id': 'wamid.COURTLOG-TEST-001'}]}

    with patch('backend.whatsapp.requests.post', return_value=FakeMetaResponse()) as send:
        response = client.post(
            f'/api/cases/{case_id}/hearings', headers=headers('usr_clerk_01'),
            json={'outcome':'Adjourned', 'reason_code':'Counsel Absent', 'next_date':'2026-10-20'},
        )
        assert response.status_code == 200, response.text
        assert send.call_count == 1
        request = send.call_args.kwargs
        assert request['timeout'] == (5, 20)
        assert request['allow_redirects'] is False
        payload = request['json']
        assert payload['messaging_product'] == 'whatsapp'
        assert payload['to'] == phone_counsel
        assert payload['type'] == 'template'
        assert payload['template'] == {'name':'courtlog_schedule_notice', 'language':{'code':'en'}}
        serialized_payload = json.dumps(payload)
        for private_value in (case_id, '2026-10-20', 'Counsel Absent', phone_litigant):
            assert private_value not in serialized_payload

        event_id = response.json()['hearing_log'][-1]['event_id']
        # The same hearing event is deduplicated, and the non-consenting litigant stays suppressed.
        send_adjournment_broadcast(
            case_id, '2026-10-20', 'Counsel Absent', event_id=event_id, database=main.db,
        )
        assert send.call_count == 1

    messages = {message['recipient_role']: message for message in main.db.list_whatsapp_messages(100)
                if message['case_id'] == case_id and message['trigger_type'] == 'adjournment'}
    assert messages['counsel']['status'] == 'accepted'
    assert messages['counsel']['provider_message_id'] == 'wamid.COURTLOG-TEST-001'
    assert messages['litigant']['status'] == 'suppressed_no_consent'
    assert phone_counsel not in json.dumps(messages)
    assert phone_litigant not in json.dumps(messages)
    raw_rows = main.db.conn.execute(
        'SELECT recipient_hash, recipient_masked FROM whatsapp_messages WHERE case_id = ?', (case_id,)
    ).fetchall()
    assert all(phone_counsel not in str(row) and phone_litigant not in str(row) for row in raw_rows)


def test_whatsapp_signed_webhook_updates_status_and_honours_stop(monkeypatch):
    configure_whatsapp_cloud(monkeypatch)
    case_id = 'SEC/WA-WEBHOOK'
    phone = '+2348030009876'
    case = fixture_case(case_id)
    case['party_contact'] = {'counsel_phone': phone, 'litigant_phone': '+2348030009877'}
    main.db.save_case(case_id, case)
    record_opt_in(phone, evidence='FICTIONAL-WEBHOOK-CONSENT')

    class FakeMetaResponse:
        status_code = 200
        def json(self):
            return {'messages': [{'id': 'wamid.COURTLOG-WEBHOOK'}]}

    with patch('backend.whatsapp.requests.post', return_value=FakeMetaResponse()) as send:
        queued = client.post('/api/whatsapp/test-send', headers=headers('usr_cr_01'), json={
            'case_id': case_id, 'recipient_role': 'counsel',
        })
        assert queued.status_code == 202, queued.text
        assert phone not in queued.text
        assert send.call_count == 1

    verify = client.get('/api/whatsapp/webhook', params={
        'hub.mode':'subscribe', 'hub.verify_token':'test-webhook-verify-token', 'hub.challenge':'challenge-42',
    })
    assert verify.status_code == 200
    assert verify.text == 'challenge-42'

    payload = {'entry':[{'changes':[{'value':{
        'statuses':[{'id':'wamid.COURTLOG-WEBHOOK', 'status':'delivered'}],
        'messages':[{'from':'2348030009876', 'type':'text', 'text':{'body':'STOP'}}],
    }}]}]}
    raw = json.dumps(payload, separators=(',', ':')).encode()
    signature = 'sha256=' + hmac.new(b'fake-meta-app-secret-for-tests', raw, hashlib.sha256).hexdigest()
    callback = client.post('/api/whatsapp/webhook', content=raw, headers={
        'Content-Type':'application/json', 'X-Hub-Signature-256':signature,
    })
    assert callback.status_code == 200, callback.text
    assert main.db.get_whatsapp_message(queued.json()['message_id'])['status'] == 'delivered'
    assert main.db.get_whatsapp_preference(hash_whatsapp_phone(phone))['status'] == 'opted_out'

    # Invalid signatures are rejected, and a delayed earlier status cannot roll back delivery.
    assert client.post('/api/whatsapp/webhook', content=raw, headers={
        'Content-Type':'application/json', 'X-Hub-Signature-256':'sha256=bad',
    }).status_code == 401
    late_sent = {'entry':[{'changes':[{'value':{'statuses':[
        {'id':'wamid.COURTLOG-WEBHOOK', 'status':'sent'}
    ]}}]}]}
    raw_late = json.dumps(late_sent, separators=(',', ':')).encode()
    late_signature = 'sha256=' + hmac.new(b'fake-meta-app-secret-for-tests', raw_late, hashlib.sha256).hexdigest()
    assert client.post('/api/whatsapp/webhook', content=raw_late, headers={
        'Content-Type':'application/json', 'X-Hub-Signature-256':late_signature,
    }).status_code == 200
    assert main.db.get_whatsapp_message(queued.json()['message_id'])['status'] == 'delivered'
    assert client.post('/api/whatsapp/test-send', headers=headers('usr_cr_01'), json={
        'case_id': case_id, 'recipient_role': 'counsel',
    }).status_code == 409


def test_whatsapp_uncertain_timeout_is_persisted_and_not_automatically_retried(monkeypatch):
    configure_whatsapp_cloud(monkeypatch)
    case_id = 'SEC/WA-UNKNOWN'
    phone = '+2348030008765'
    case = fixture_case(case_id)
    case['party_contact'] = {'counsel_phone': phone}
    main.db.save_case(case_id, case)
    record_opt_in(phone, evidence='FICTIONAL-CONSENT-UNKNOWN')

    with patch('backend.whatsapp.requests.post', side_effect=requests.Timeout('synthetic timeout')) as send:
        first = send_adjournment_broadcast(
            case_id, event_id='fictional-timeout-event-1', database=main.db,
        )
        second = send_adjournment_broadcast(
            case_id, event_id='fictional-timeout-event-1', database=main.db,
        )

    assert first['message_statuses'] == ['unknown']
    assert second['message_statuses'] == ['unknown']
    assert send.call_count == 1
    stored = [message for message in main.db.list_whatsapp_messages(100) if message['case_id'] == case_id]
    assert len(stored) == 1
    assert stored[0]['status'] == 'unknown'
    assert stored[0]['error_code'] == 'provider_outcome_unknown'
    assert phone not in json.dumps(stored)


def test_whatsapp_concurrent_delivery_claim_calls_provider_once(monkeypatch):
    configure_whatsapp_cloud(monkeypatch)
    case_id = 'SEC/WA-CONCURRENT'
    phone = '+2348030008766'
    case = fixture_case(case_id)
    case['party_contact'] = {'counsel_phone': phone}
    main.db.save_case(case_id, case)
    record_opt_in(phone, evidence='FICTIONAL-CONSENT-CONCURRENT')
    message, inserted = create_manual_test_message(main.db, case_id, 'counsel')
    assert inserted is True
    assert message['status'] == 'queued'

    class FakeMetaResponse:
        status_code = 200

        def json(self):
            return {'messages': [{'id': 'wamid.COURTLOG-CONCURRENCY-TEST'}]}

    provider_started = threading.Event()

    def slow_provider_response(*args, **kwargs):
        provider_started.set()
        time.sleep(0.05)
        return FakeMetaResponse()

    with patch('backend.whatsapp.requests.post', side_effect=slow_provider_response) as send:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda _index: deliver_whatsapp_message(main.db, message['message_id']),
                range(8),
            ))

    assert provider_started.is_set()
    assert send.call_count == 1
    assert {result['status'] for result in results}.issubset({'sending', 'accepted'})
    stored = main.db.get_whatsapp_message(message['message_id'])
    assert stored['status'] == 'accepted'
    assert stored['attempt_count'] == 1


def test_compliance_sweep_boundaries_for_7_day_custody_24_hour_review_and_90_day_prompt(monkeypatch):
    now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(main, 'get_current_time', lambda: now)

    def iso(value):
        return value.isoformat().replace('+00:00', 'Z')

    cases = {
        'SEC/BOUNDARY-7-EXACT': {
            'filing_date': iso(now - timedelta(days=7)),
            'judgment_status': 'Pending', 'scan_events': [],
        },
        'SEC/BOUNDARY-7-BEFORE': {
            'filing_date': iso(now - timedelta(days=7) + timedelta(seconds=1)),
            'judgment_status': 'Pending', 'scan_events': [],
        },
        'SEC/BOUNDARY-7-AFTER': {
            'filing_date': iso(now - timedelta(days=7, seconds=1)),
            'judgment_status': 'Pending', 'scan_events': [],
        },
        'SEC/BOUNDARY-24-BEFORE': {
            'filing_date': iso(now - timedelta(days=1)),
            'judgment_status': 'Pending', 'scan_events': [],
            'dcr_approval_required': True,
            'dcr_approval_requested_at': iso(now - timedelta(hours=23, minutes=59, seconds=59)),
        },
        'SEC/BOUNDARY-24-EXACT': {
            'filing_date': iso(now - timedelta(days=1)),
            'judgment_status': 'Pending', 'scan_events': [],
            'dcr_approval_required': True,
            'dcr_approval_requested_at': iso(now - timedelta(hours=24)),
        },
        'SEC/BOUNDARY-24-AFTER': {
            'filing_date': iso(now - timedelta(days=1)),
            'judgment_status': 'Pending', 'scan_events': [],
            'dcr_approval_required': True,
            'dcr_approval_requested_at': iso(now - timedelta(hours=24, seconds=1)),
        },
        'SEC/BOUNDARY-90-BEFORE': {
            'filing_date': iso(now - timedelta(days=200)),
            'judgment_status': 'Delivered', 'scan_events': [],
            'execution_log': [{'action': 'Judgment Delivered', 'date': iso(now - timedelta(days=89))}],
        },
        'SEC/BOUNDARY-90-EXACT': {
            'filing_date': iso(now - timedelta(days=200)),
            'judgment_status': 'Delivered', 'scan_events': [],
            'execution_log': [{'action': 'Judgment Delivered', 'date': iso(now - timedelta(days=90))}],
        },
        'SEC/BOUNDARY-90-AFTER': {
            'filing_date': iso(now - timedelta(days=200)),
            'judgment_status': 'Delivered', 'scan_events': [],
            'execution_log': [{'action': 'Judgment Delivered', 'date': iso(now - timedelta(days=91))}],
        },
    }
    for case_id, case in cases.items():
        main.db.save_case(case_id, {'case_id': case_id, **case})

    main.run_compliance_checks_sync()

    assert main.db.get_case('SEC/BOUNDARY-7-BEFORE')['custody_alert'] is False
    assert main.db.get_case('SEC/BOUNDARY-7-EXACT')['custody_alert'] is True
    assert main.db.get_case('SEC/BOUNDARY-7-AFTER')['custody_alert'] is True
    assert main.db.get_case('SEC/BOUNDARY-24-BEFORE').get('dcr_auto_escalated', False) is False
    assert main.db.get_case('SEC/BOUNDARY-24-EXACT').get('dcr_auto_escalated', False) is False
    assert main.db.get_case('SEC/BOUNDARY-24-AFTER')['dcr_auto_escalated'] is True
    assert main.db.get_case('SEC/BOUNDARY-90-BEFORE')['enforcement_non_compliant'] is False
    assert main.db.get_case('SEC/BOUNDARY-90-EXACT')['enforcement_non_compliant'] is False
    assert main.db.get_case('SEC/BOUNDARY-90-AFTER')['enforcement_non_compliant'] is True


def test_demo_mode_never_sends_real_whatsapp_even_with_cloud_credentials(monkeypatch):
    configure_whatsapp_cloud(monkeypatch, demo=True, enabled=True)
    case_id = 'SEC/WA-DEMO'
    phone = '+2348031112222'
    case = fixture_case(case_id)
    case['party_contact'] = {'counsel_phone': phone, 'litigant_phone': '+2348031113333'}
    main.db.save_case(case_id, case)
    record_opt_in(phone, evidence='FICTIONAL-DEMO-CONSENT')
    with patch('backend.whatsapp.requests.post') as send:
        response = client.post('/api/whatsapp/test-send', headers=headers('usr_cr_01'), json={
            'case_id': case_id, 'recipient_role': 'counsel',
        })
        send.assert_not_called()
    assert response.status_code == 202
    assert response.json()['status'] == 'simulated'
    assert client.get('/api/whatsapp/status', headers=headers('usr_cr_01')).json()['mode'] == 'demo_simulation'


def test_case_identifiers_are_validated_on_path_routes():
    h = headers('usr_cr_01')
    for path in (
        '/api/cases/SEC/A..B',
        '/api/cases/SEC/A..B/alerts',
        '/api/cases/SEC/A..B/documents',
    ):
        response = client.get(path, headers=h) if path.endswith(('A..B', 'alerts')) else client.post(
            path, headers=h,
            json={'document_type':'Motion', 'title':'Motion', 'filename':'motion.pdf'},
        )
        assert response.status_code == 422, (path, response.status_code, response.text)


def test_document_metadata_rejects_paths_and_does_not_claim_file_storage():
    fixture_case('SEC/DOC')
    h = headers('usr_clerk_01')
    endpoint = '/api/cases/SEC/DOC/documents'
    payload = {'document_type':'Motion', 'title':'Motion for Bail', 'filename':'motion.pdf'}

    for filename in ('../escape.pdf', r'..\\escape.pdf', 'motion..pdf'):
        response = client.post(endpoint, headers=h, json={**payload, 'filename':filename})
        assert response.status_code == 422

    recorded = client.post(endpoint, headers=h, json=payload)
    assert recorded.status_code == 200
    document = recorded.json()['documents'][-1]
    assert document['storage_path'] is None
    assert document['storage_status'] == 'metadata_only'


def test_case_creation_normalizes_nigerian_phones_and_rejects_invalid_values():
    h = headers('usr_clerk_01')
    payload = {
        'case_id':'FHC/ABJ/CR/200/2026', 'case_type':'Criminal',
        'court':'FHC Abuja Court 4', 'counsel_phone':'0803 123 4567',
        'litigant_phone':'0811-111-1111',
    }
    created = client.post('/api/cases', headers=h, json=payload)
    assert created.status_code == 201, created.text
    contacts = created.json()['party_contact']
    assert contacts['counsel_phone'] == '+2348031234567'
    assert contacts['litigant_phone'] == '+2348111111111'

    invalid_phone = client.post('/api/cases', headers=h, json={
        **payload, 'case_id':'FHC/ABJ/CR/201/2026', 'counsel_phone':'not a phone',
    })
    assert invalid_phone.status_code == 422
    too_long = client.post('/api/cases', headers=h, json={
        **payload, 'case_id':'FHC/ABJ/CR/202/2026', 'case_type':'C' * 81,
    })
    assert too_long.status_code == 422


def test_hearing_dates_are_iso_valid_and_adjournments_require_a_date():
    fixture_case('SEC/DATE')
    h = headers('usr_clerk_01')
    endpoint = '/api/cases/SEC/DATE/hearings'

    for next_date in ('2026-02-30', 'not-a-date', ''):
        response = client.post(endpoint, headers=h, json={
            'outcome':'Adjourned', 'reason_code':'Counsel Absent', 'next_date':next_date,
        })
        assert response.status_code == 422

    valid = client.post(endpoint, headers=h, json={
        'outcome':'Adjourned', 'reason_code':'Counsel Absent', 'next_date':'2026-10-02',
    })
    assert valid.status_code == 200, valid.text
    assert valid.json()['hearing_log'][-1]['next_date'] == '2026-10-02'

    fixture_case('SEC/HEARD')
    heard = client.post('/api/cases/SEC/HEARD/hearings', headers=h, json={
        'outcome':'Heard', 'reason_code':'None', 'next_date':'',
    })
    assert heard.status_code == 200, heard.text
    assert heard.json()['hearing_log'][-1]['next_date'] == ''


def test_security_headers_and_production_docs_configuration():
    response = client.get('/api/config')
    assert response.status_code == 200
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    assert response.headers['Permissions-Policy'] == 'camera=(self), geolocation=(), microphone=()'
    assert response.headers['Cross-Origin-Opener-Policy'] == 'same-origin'
    assert main.app.docs_url is None
    assert main.app.redoc_url is None
    assert main.app.openapi_url is None
    assert client.get('/docs').status_code == 404
    assert client.get('/openapi.json').status_code == 404


def test_required_text_inputs_reject_whitespace_only_values():
    fixture_case('SEC/BLANK')
    clerk_headers = headers('usr_clerk_01')
    scan = client.post('/api/scan', headers=clerk_headers, json={
        'case_id':'SEC/BLANK', 'location':'   ', 'staff_id':'usr_clerk_01',
    })
    assert scan.status_code == 422

    hearing = client.post('/api/cases/SEC/BLANK/hearings', headers=clerk_headers, json={
        'outcome':'Adjourned', 'reason_code':'   ', 'next_date':'2026-10-02',
    })
    assert hearing.status_code == 422

    document = client.post('/api/cases/SEC/BLANK/documents', headers=clerk_headers, json={
        'document_type':'Motion', 'title':'   ', 'filename':'motion.pdf',
    })
    assert document.status_code == 422
    assert client.post('/api/login', json={'username':'   ', 'password':'password'}).status_code == 422


def test_cors_does_not_reflect_unconfigured_origins():
    preflight = client.options('/api/config', headers={
        'Origin':'https://evil.example',
        'Access-Control-Request-Method':'GET',
    })
    assert 'access-control-allow-origin' not in preflight.headers


def test_login_endpoint_limits_failed_attempts_per_username_and_client(monkeypatch):
    monkeypatch.setattr(main, 'LOGIN_RATE_LIMIT_PER_USERNAME_IP', 2)
    with TestClient(main.app, client=('198.51.100.41', 43100)) as limited_client:
        payload = {'username':'throttle-regression-user', 'password':'wrong-password'}
        assert limited_client.post('/api/login', json=payload).status_code == 401
        assert limited_client.post('/api/login', json=payload).status_code == 401
        blocked = limited_client.post('/api/login', json=payload)
        assert blocked.status_code == 429
        assert blocked.json()['detail'] == 'Too many login attempts. Try again later.'
        assert int(blocked.headers['Retry-After']) >= 1
        assert blocked.headers['Cache-Control'] == 'no-store'
        # A different username from the same address is not account-locked.
        assert limited_client.post('/api/login', json={
            'username':'another-throttle-user', 'password':'wrong-password'
        }).status_code == 401


def test_login_rate_limit_window_and_success_reservation_release():
    principal_key = 'a' * 64
    client_key = 'b' * 64
    first, delay = main.db.reserve_login_attempt(principal_key, client_key, 200_000, 60, 2, 10)
    second, delay = main.db.reserve_login_attempt(principal_key, client_key, 200_001, 60, 2, 10)
    assert first and second and delay == 0

    blocked, delay = main.db.reserve_login_attempt(principal_key, client_key, 200_002, 60, 2, 10)
    assert blocked is None and delay == 58

    # A correct credential removes its reservation and doesn't count as failure.
    main.db.complete_login_attempt(second)
    next_attempt, delay = main.db.reserve_login_attempt(principal_key, client_key, 200_003, 60, 2, 10)
    assert next_attempt and delay == 0

    # Reservations naturally expire after the rolling window.
    after_expiry, delay = main.db.reserve_login_attempt(principal_key, client_key, 200_061, 60, 2, 10)
    assert after_expiry and delay == 0
    for attempt_id in (first, next_attempt, after_expiry):
        main.db.complete_login_attempt(attempt_id)


def test_hearing_outcome_rejects_values_outside_current_ui_choices():
    fixture_case('SEC/ENUM')
    response = client.post(
        '/api/cases/SEC/ENUM/hearings', headers=headers('usr_clerk_01'),
        json={'outcome':'Unknown Workflow State', 'reason_code':'Other'},
    )
    assert response.status_code == 422


def test_successful_login_clears_its_rate_limit_reservation(monkeypatch):
    monkeypatch.setattr(main, 'LOGIN_RATE_LIMIT_PER_USERNAME_IP', 2)
    with TestClient(main.app, client=('198.51.100.42', 43101)) as limited_client:
        assert limited_client.post('/api/login', json={
            'username':'cr', 'password':'12345'
        }).status_code == 200
        for _ in range(2):
            failed = limited_client.post('/api/login', json={
                'username':'cr', 'password':'incorrect-password'
            })
            assert failed.status_code == 401
            assert failed.headers['Cache-Control'] == 'no-store'
        assert limited_client.post('/api/login', json={
            'username':'cr', 'password':'incorrect-password'
        }).status_code == 429


def test_login_rate_limit_reservations_are_atomic_under_concurrency():
    principal_key = 'c' * 64
    client_key = 'd' * 64
    def reserve(_):
        return main.db.reserve_login_attempt(principal_key, client_key, 400_000, 60, 3, 100)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(reserve, range(16)))
    allowed = [attempt_id for attempt_id, _ in results if attempt_id]
    blocked = [(attempt_id, delay) for attempt_id, delay in results if not attempt_id]
    assert len(allowed) == 3
    assert len(blocked) == 13
    assert all(delay >= 1 for _, delay in blocked)
    for attempt_id in allowed:
        main.db.complete_login_attempt(attempt_id)


def test_audit_log_attributes_case_creation_and_is_chief_registrar_only():
    payload = {
        'case_id':'SEC/AUDIT-CREATE', 'case_type':'Criminal',
        'court':'FHC Abuja Court 4', 'counsel_phone':'+2348031234567',
        'litigant_phone':'+2348037654321',
    }
    created = client.post('/api/cases', headers=headers('usr_clerk_01'), json=payload)
    assert created.status_code == 201
    assert client.get('/api/audit/events', headers=headers('usr_clerk_01')).status_code == 403

    admin_headers = headers('usr_cr_01')
    response = client.get('/api/audit/events?limit=200', headers=admin_headers)
    assert response.status_code == 200
    assert client.get('/api/audit/events?limit=501', headers=admin_headers).status_code == 422
    event = next(e for e in response.json() if e['action'] == 'case.create' and e['entity_id'] == payload['case_id'])
    assert event['actor_user_id'] == 'usr_clerk_01'
    assert event['entity_type'] == 'case'
    assert event['occurred_at']
    assert '+2348031234567' not in json.dumps(event)
    assert '+2348037654321' not in json.dumps(event)

    with pytest.raises(sqlite3.IntegrityError):
        main.db.conn.execute("UPDATE audit_events SET reason = 'tampered' WHERE event_id = ?", (event['event_id'],))
    main.db.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        main.db.conn.execute("DELETE FROM audit_events WHERE event_id = ?", (event['event_id'],))
    main.db.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        main.db.conn.execute(
            "INSERT OR REPLACE INTO audit_events "
            "(event_id, occurred_at, actor_user_id, action, entity_type, entity_id, reason, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event['event_id'], event['occurred_at'], event['actor_user_id'], event['action'],
             event['entity_type'], event['entity_id'], 'replacement', json.dumps(event['metadata'])),
        )
    main.db.conn.rollback()
    assert any(e['event_id'] == event['event_id'] for e in main.db.list_audit_events(200))


def test_audit_records_hearing_and_override_actor_time_and_reason():
    fixture_case('SEC/AUDIT-HEARING')
    hearing = client.post(
        '/api/cases/SEC/AUDIT-HEARING/hearings', headers=headers('usr_clerk_01'),
        json={'outcome':'Adjourned', 'reason_code':'Counsel Absent', 'next_date':'2026-10-20'},
    )
    assert hearing.status_code == 200

    fixture_case('SEC/AUDIT-OVERRIDE')
    main.db.update_case('SEC/AUDIT-OVERRIDE', {
        'dcr_approval_required': True, 'adjournment_blocked': True,
    })
    override_reason = 'Urgent exceptional registry reason 482'
    override = client.post(
        '/api/cases/SEC/AUDIT-OVERRIDE/dcr-override', headers=headers('usr_dcr_01'),
        json={'exceptional_reason':override_reason},
    )
    assert override.status_code == 200

    events = main.db.list_audit_events(200)
    hearing_event = next(e for e in events if e['action'] == 'case.hearing.record' and e['entity_id'] == 'SEC/AUDIT-HEARING')
    assert hearing_event['actor_user_id'] == 'usr_clerk_01'
    assert hearing_event['reason'] == 'Counsel Absent'
    assert hearing_event['metadata']['outcome'] == 'Adjourned'
    assert hearing_event['occurred_at']

    override_event = next(e for e in events if e['action'] == 'case.dcr_override' and e['entity_id'] == 'SEC/AUDIT-OVERRIDE')
    assert override_event['actor_user_id'] == 'usr_dcr_01'
    assert override_event['reason'] == override_reason
    assert override_event['occurred_at']


def test_user_password_audit_events_exclude_credentials():
    target_id = 'usr_audit_password_target'
    main.db.save_user(target_id, {
        'user_id':target_id, 'username':'audit-target',
        'password':get_password_hash('Initial-Password-41!'),
        'role':'Clerk', 'court':'FHC Abuja Court 4', 'division':'Criminal',
        'disabled':False,
    })
    temporary = 'Temporary-Password-42!'
    response = client.post(
        f'/api/users/{target_id}/reset-password', headers=headers('usr_cr_01'),
        json={'temporary_password':temporary},
    )
    assert response.status_code == 200
    event = next(
        e for e in main.db.list_audit_events(200)
        if e['action'] == 'user.password.reset' and e['entity_id'] == target_id
    )
    serialized = json.dumps(event)
    assert event['actor_user_id'] == 'usr_cr_01'
    assert temporary not in serialized
    assert 'Initial-Password-41!' not in serialized

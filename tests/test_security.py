"""Security regression tests: never import the app against the committed database."""
import os
import tempfile
import json
import sqlite3
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
from backend.database import SQLiteDatabase, get_password_hash

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
    for method, path in [('get', '/api/users'), ('get', '/api/cases/SEC/1'),
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

def test_scan_identity_comes_from_token():
    fixture_case('SEC/SCAN')
    response = client.post('/api/scan', headers=headers('usr_sheriff_01'),
                           json={'case_id':'SEC/SCAN', 'location':'Desk', 'staff_id':'usr_cr_01'})
    assert response.status_code == 200
    assert response.json()['scan_events'][-1]['staff_id'] == 'usr_sheriff_01'

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
    response = client.get('/api/export/njc', headers=headers('usr_dcr_01'))
    assert response.status_code == 200
    assert all(c['assigned_division'] == 'Criminal' for c in response.json()['audited_cases'])

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
    assert 'auth_sessions' in {
        row[0] for row in migrated.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    with pytest.raises(sqlite3.IntegrityError):
        migrated.save_user('duplicate_user', {'user_id':'duplicate_user', 'username':'legacy.user', 'role':'Clerk'})
    migrated.conn.close()


def test_refresh_cookie_secure_flag_can_be_enabled(monkeypatch):
    monkeypatch.setattr(main, 'COOKIE_SECURE', True)
    response = main.Response()
    main._set_refresh_cookie(response, 'test-token')
    cookie_headers = [value.decode().lower() for name, value in response.raw_headers if name.lower() == b'set-cookie']
    assert any('httponly' in value and 'secure' in value and 'samesite=strict' in value for value in cookie_headers)

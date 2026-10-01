"""Security regression tests: never import the app against the committed database."""
import os
import tempfile
from pathlib import Path

_runtime = tempfile.TemporaryDirectory()
os.environ['COURTLOG_DB_PATH'] = str(Path(_runtime.name) / 'test.db')
os.environ['JWT_PRIVATE_KEY_PATH'] = str(Path(_runtime.name) / 'private.pem')
os.environ['JWT_PUBLIC_KEY_PATH'] = str(Path(_runtime.name) / 'public.pem')
os.environ['DEMO_MODE'] = 'false'

from fastapi.testclient import TestClient
from backend import main
from backend.auth import create_access_token, create_refresh_token

client = TestClient(main.app)

def headers(uid):
    user = main.db.get_user(uid)
    return {'Authorization': 'Bearer ' + create_access_token({'sub': uid, 'role': user['role']})}

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
    h = headers(user['user_id'])
    refresh = create_refresh_token({'sub':user['user_id'], 'role':'Clerk'})
    main.db.delete_user(user['user_id'])
    assert client.get('/api/cases', headers=h).status_code == 401
    assert client.post('/api/refresh', json={'refresh_token':refresh}).status_code == 401

def test_admin_self_deletion_denied():
    assert client.delete('/api/users/usr_cr_01', headers=headers('usr_cr_01')).status_code == 409

def test_dcr_export_is_scoped():
    fixture_case('SEC/CIVIL')['assigned_division'] = 'Civil'
    case = main.db.get_case('SEC/CIVIL'); case['assigned_division'] = 'Civil'
    main.db.save_case('SEC/CIVIL', case)
    response = client.get('/api/export/njc', headers=headers('usr_dcr_01'))
    assert response.status_code == 200
    assert all(c['assigned_division'] == 'Criminal' for c in response.json()['audited_cases'])

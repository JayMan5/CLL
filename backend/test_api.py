import os
import sys
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

# Ensure backend folder is in path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from backend.main import app

class TestCourtLogAPI(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        
        # Intercept real network POSTs to the WhatsApp webhook simulator and route them through TestClient
        import requests
        cls.original_post = requests.post
        
        def mock_post(url, *args, **kwargs):
            if "webhook-simulator" in url:
                # Redirect the requests call to our mock client in-memory
                return cls.client.post("/api/whatsapp/webhook-simulator", json=kwargs.get("json"))
            return cls.original_post(url, *args, **kwargs)
            
        cls.post_patcher = patch('backend.whatsapp.requests.post', side_effect=mock_post)
        cls.post_patcher.start()
        
        # Clear any stored logs in simulator
        cls.client.get("/api/whatsapp/logs")

    @classmethod
    def tearDownClass(cls):
        cls.post_patcher.stop()
        
    def test_01_get_cases(self):
        """Verify that case directory can be listed and contains seed records."""
        response = self.client.get("/api/cases")
        self.assertEqual(response.status_code, 200)
        cases = response.json()
        self.assertGreaterEqual(len(cases), 5)
        # Verify specific seed cases are present
        case_ids = [c["case_id"] for c in cases]
        self.assertIn("CR-104-2025", case_ids)
        self.assertIn("LD-554-2024", case_ids)

    def test_02_qr_scan_flow(self):
        """Verify incoming QR barcode scans append events and reset flags."""
        # Check FM-121-2026 (starts with custody_alert=True because no scans in last 7 days)
        response_before = self.client.get("/api/cases/FM-121-2026")
        self.assertEqual(response_before.status_code, 200)
        
        # Post scan event
        payload = {
            "case_id": "FM-121-2026",
            "location": "Courtroom 2 File Rack",
            "staff_id": "ST-999"
        }
        response_scan = self.client.post("/api/scan", json=payload)
        self.assertEqual(response_scan.status_code, 200)
        
        updated_case = response_scan.json()
        self.assertFalse(updated_case["custody_alert"])  # Reset alert state
        
        # Verify event appended
        self.assertGreater(len(updated_case["scan_events"]), 0)
        latest_scan = updated_case["scan_events"][-1]
        self.assertEqual(latest_scan["location"], "Courtroom 2 File Rack")
        self.assertEqual(latest_scan["staff_id"], "ST-999")

    def test_03_adjournment_logging_and_whatsapp_broadcast(self):
        """Verify courtroom logging increments count and triggers WhatsApp POST."""
        case_id = "AD-009-2025"
        
        # Get count before
        response_before = self.client.get(f"/api/cases/{case_id}")
        count_before = response_before.json()["adjournment_count"]
        
        # Log adjournment
        payload = {
            "outcome": "Adjourned",
            "reason_code": "Witness Unavailable",
            "next_date": "2026-08-10T10:00:00Z"
        }
        response_hearing = self.client.post(f"/api/cases/{case_id}/hearings", json=payload)
        self.assertEqual(response_hearing.status_code, 200)
        
        updated_case = response_hearing.json()
        self.assertEqual(updated_case["adjournment_count"], count_before + 1)
        
        # Verify hearing log contains entry
        latest_hearing = updated_case["hearing_log"][-1]
        self.assertEqual(latest_hearing["outcome"], "Adjourned")
        self.assertEqual(latest_hearing["reason_code"], "Witness Unavailable")
        
        # Verify WhatsApp simulation webhook endpoint intercepted the broadcast
        response_wa = self.client.get("/api/whatsapp/logs")
        self.assertEqual(response_wa.status_code, 200)
        logs = response_wa.json()
        
        self.assertGreater(len(logs), 0)
        latest_broadcast = logs[0]["payload"]
        
        # Verify template parameters compiled correctly
        self.assertEqual(latest_broadcast["template"]["name"], "court_adjournment_alert")
        params = latest_broadcast["template"]["components"][0]["parameters"]
        self.assertEqual(params[0]["text"], case_id)
        self.assertEqual(params[1]["text"], "2026-08-10T10:00:00Z")
        self.assertEqual(params[2]["text"], "Witness Unavailable")
        
        # Verify exact requested text structure
        expected_text = f"SUIT NO: {case_id} adjourned to 2026-08-10T10:00:00Z. Reason: Witness Unavailable. File routing back to Registry."
        self.assertEqual(latest_broadcast["simulated_text"], expected_text)

    def test_04_ml_prediction_endpoint(self):
        """Verify on-demand predictive risk modeling triggers flag update."""
        case_id = "LD-554-2024"
        
        response_predict = self.client.post(f"/api/cases/{case_id}/predict")
        self.assertEqual(response_predict.status_code, 200)
        
        result = response_predict.json()
        self.assertIn("delay_risk_score", result)
        self.assertIn("risk_flag", result)
        
        # Check if DB has been updated
        response_case = self.client.get(f"/api/cases/{case_id}")
        case = response_case.json()
        self.assertEqual(case["delay_risk_score"], result["delay_risk_score"])
        self.assertEqual(case["risk_flag"], result["risk_flag"])

    def test_05_execution_compliance_rules(self):
        """Verify 7-day custody scanner warnings and 90-day enforcement warnings are flagged."""
        # Trigger full background cron sweep
        response_cron = self.client.post("/api/cron")
        self.assertEqual(response_cron.status_code, 200)
        
        # We know from seed data:
        # Case CV-302-2025 has judgment_status == 'Delivered', and it has been over 90 days with no subsequent sheriff writ entries.
        # It must be flagged as Enforcement Non-Compliant.
        response_cv = self.client.get("/api/cases/CV-302-2025")
        self.assertTrue(response_cv.json()["enforcement_non_compliant"])
        
        # Case AD-009-2025 has judgment_status == 'Delivered' and has a Writ filed within 90 days. It should NOT be flagged.
        response_ad = self.client.get("/api/cases/AD-009-2025")
        self.assertFalse(response_ad.json()["enforcement_non_compliant"])
        
        # Register a sheriff execution action on CV-302-2025 that completes enforcement
        exec_payload = {
            "action": "Writ of Fi Fa Completed",
            "sheriff_id": "SH-011"
        }
        response_exec = self.client.post("/api/cases/CV-302-2025/execution", json=exec_payload)
        self.assertEqual(response_exec.status_code, 200)
        
        updated_cv = response_exec.json()
        self.assertEqual(updated_cv["judgment_status"], "Executed")
        self.assertFalse(updated_cv["enforcement_non_compliant"])  # resolved

    def test_06_rbac_permissions(self):
        """Verify 5-Level RBAC permission restrictions across roles."""
        # 1. Sheriff attempting to create a case -> 403 Forbidden
        headers_sheriff = {"X-User-Role": "Sheriff", "X-User-Id": "usr_sheriff_01"}
        payload_case = {
            "case_id": "ILLEGAL-01",
            "case_type": "Criminal",
            "court": "FHC Abuja Court 4",
            "counsel_phone": "+2348000000000",
            "litigant_phone": "+2348111111111"
        }
        res_sheriff = self.client.post("/api/cases", json=payload_case, headers=headers_sheriff)
        self.assertEqual(res_sheriff.status_code, 403)

        # 2. Clerk creating a case -> 201 Created
        headers_clerk = {"X-User-Role": "Clerk", "X-User-Id": "usr_clerk_01"}
        payload_valid = {
            "case_id": "VALID-CR-99",
            "case_type": "Criminal",
            "court": "FHC Abuja Court 4",
            "counsel_phone": "+2348000000000",
            "litigant_phone": "+2348111111111"
        }
        res_clerk = self.client.post("/api/cases", json=payload_valid, headers=headers_clerk)
        self.assertEqual(res_clerk.status_code, 201)

        # 3. Clerk attempting to create a user -> 403 Forbidden
        payload_user = {
            "name": "New Clerk Test",
            "role": "Clerk",
            "badge": "Test Badge",
            "court": "FHC Abuja Court 4",
            "division": "Criminal"
        }
        res_user_forbidden = self.client.post("/api/users", json=payload_user, headers=headers_clerk)
        self.assertEqual(res_user_forbidden.status_code, 403)

        # 4. Chief Registrar creating a user -> 201 Created
        headers_cr = {"X-User-Role": "Chief Registrar", "X-User-Id": "usr_cr_01"}
        res_user_ok = self.client.post("/api/users", json=payload_user, headers=headers_cr)
        self.assertEqual(res_user_ok.status_code, 201)

    def test_07_5th_adjournment_dcr_block_and_override(self):
        """Verify 5th adjournment hard block and DCR override unblocking flow."""
        # Case CR-104-2025 starts at 4 adjournments
        case_id = "CR-104-2025"
        headers_clerk = {"X-User-Role": "Clerk", "X-User-Id": "usr_clerk_01"}
        
        # Log 5th adjournment as Clerk -> Must be BLOCKED with 400 Bad Request
        payload_5th = {
            "outcome": "Adjourned",
            "reason_code": "Counsel Absent",
            "next_date": "2026-09-01T10:00:00Z"
        }
        res_5th = self.client.post(f"/api/cases/{case_id}/hearings", json=payload_5th, headers=headers_clerk)
        self.assertEqual(res_5th.status_code, 400)
        self.assertIn("5th Adjournment BLOCKED", res_5th.json()["detail"])

        # Attempt override as Clerk -> 403 Forbidden
        res_override_clerk = self.client.post(
            f"/api/cases/{case_id}/dcr-override",
            json={"exceptional_reason": "Medical Emergency"},
            headers=headers_clerk
        )
        self.assertEqual(res_override_clerk.status_code, 403)

        # Override as DCR -> 200 OK
        headers_dcr = {"X-User-Role": "DCR", "X-User-Id": "usr_dcr_01"}
        res_override_dcr = self.client.post(
            f"/api/cases/{case_id}/dcr-override",
            json={"exceptional_reason": "State Prosecutor in Appeal Court Hearing"},
            headers=headers_dcr
        )
        self.assertEqual(res_override_dcr.status_code, 200)
        self.assertEqual(res_override_dcr.json()["dcr_override_reason"], "State Prosecutor in Appeal Court Hearing")

        # Now log 5th adjournment again as Clerk -> 200 OK
        res_5th_retry = self.client.post(f"/api/cases/{case_id}/hearings", json=payload_5th, headers=headers_clerk)
        self.assertEqual(res_5th_retry.status_code, 200)
        self.assertEqual(res_5th_retry.json()["adjournment_count"], 5)

    def test_08_njc_export(self):
        """Verify 1-click NJC compliance report generation."""
        headers_cr = {"X-User-Role": "Chief Registrar", "X-User-Id": "usr_cr_01"}
        res_njc = self.client.get("/api/export/njc", headers=headers_cr)
        self.assertEqual(res_njc.status_code, 200)
        
        report = res_njc.json()
        self.assertIn("report_title", report)
        self.assertIn("speedy_trial_compliance_score", report["summary"])
        self.assertGreater(len(report["audited_cases"]), 0)

    def test_09_developer_login(self):
        """Verify authentication for developer account (dev / 12345) and failure cases."""
        # Valid dev login
        res_dev = self.client.post("/api/login", json={"username": "dev", "password": "12345"})
        self.assertEqual(res_dev.status_code, 200)
        self.assertEqual(res_dev.json()["user"]["username"], "dev")
        self.assertEqual(res_dev.json()["user"]["role"], "Chief Registrar")

        # Invalid password -> 401 Unauthorized
        res_bad_pass = self.client.post("/api/login", json={"username": "dev", "password": "wrongpassword"})
        self.assertEqual(res_bad_pass.status_code, 401)

        # Invalid username -> 401 Unauthorized
        res_bad_user = self.client.post("/api/login", json={"username": "unknown", "password": "123"})
        self.assertEqual(res_bad_user.status_code, 401)

if __name__ == "__main__":
    unittest.main()


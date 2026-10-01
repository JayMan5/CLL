import csv
import json
import random
from datetime import datetime, timedelta
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
REAL_CSV = os.path.join(DATA_DIR, "real_scn_cases_sample.csv")
APP_DB_JSON = os.path.join(DATA_DIR, "cases.json")

def generate_mock_history(year_filed, year_decided, status):
    # Mock some dates
    filing_date = datetime(year=int(year_filed), month=random.randint(1, 12), day=random.randint(1, 28))
    
    # Calculate days since filing (relative to our simulation date of July 2026)
    sim_date = datetime(2026, 7, 18)
    days_since_filing = (sim_date - filing_date).days
    if days_since_filing < 0:
        days_since_filing = 10
    
    adjournments = random.randint(1, 6)
    
    scan_events = [
        {"location": "Registry Desk A", "timestamp": (filing_date + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"), "staff_id": "ST-002"},
        {"location": "Court Clerk Office 4", "timestamp": (filing_date + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"), "staff_id": "ST-044"}
    ]
    
    if random.random() < 0.2:
        # File currently missing / un-scanned for over 7 days
        scan_events.append({"location": "Judge Chambers 4", "timestamp": (sim_date - timedelta(days=random.randint(8, 20))).strftime("%Y-%m-%dT%H:%M:%SZ"), "staff_id": "ST-012"})
    else:
        # Recently scanned
        scan_events.append({"location": "Registry Desk A", "timestamp": (sim_date - timedelta(days=random.randint(1, 5))).strftime("%Y-%m-%dT%H:%M:%SZ"), "staff_id": "ST-002"})

    hearing_log = []
    current_date = filing_date + timedelta(days=30)
    for i in range(adjournments):
        hearing_log.append({
            "date": current_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "outcome": "Adjourned",
            "reason_code": random.choice(["No Service", "Counsel Absent", "Witness Unavailable", "Judge Absent"]),
            "next_date": (current_date + timedelta(days=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
        })
        current_date += timedelta(days=45)
        
    return filing_date, days_since_filing, adjournments, scan_events, hearing_log

def main():
    if not os.path.exists(REAL_CSV):
        print(f"File {REAL_CSV} not found!")
        return
        
    cases = {}
    with open(REAL_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            case_id = row.get("Case Ref")
            if not case_id:
                continue
            
            # Clean case ID for dict key
            key = case_id.replace("/", "-").strip()
            
            case_type = row.get("Case Type", "Civil")
            if "Criminal" in case_type:
                major_type = "Criminal"
            elif "Election" in case_type:
                major_type = "Election Petition"
            elif "Land" in case_type:
                major_type = "Land Dispute"
            else:
                major_type = "Civil"
                
            status = "Pending" if row.get("Years to Conclusion") == "Pending" else "Judgment Delivered"
            
            filing_date, days_since, adjournments, scans, hearings = generate_mock_history(
                row.get("Year Filed", "2020"), 
                row.get("Year Decided", "2025"), 
                status
            )
            
            delay_risk = 0.85 if adjournments >= 4 else (0.4 if adjournments >= 2 else 0.1)
            
            case_obj = {
                "case_id": case_id,
                "case_title": row.get("Title", "Unknown Parties"),
                "case_type": major_type,
                "sub_type": case_type,
                "court": row.get("Court", "Supreme Court"),
                "assigned_division": major_type,
                "assigned_judge_id": "usr_judge_01",
                "filing_date": filing_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "adjournment_count": adjournments,
                "days_since_filing": days_since,
                "judgment_status": status,
                "delay_risk_score": delay_risk,
                "risk_flag": delay_risk > 0.7,
                "dcr_approval_required": adjournments >= 5,
                "dcr_override_reason": None,
                "adjournment_blocked": adjournments >= 5,
                "party_contact": {
                    "counsel_phone": "+23480" + str(random.randint(10000000, 99999999)),
                    "litigant_phone": "+23481" + str(random.randint(10000000, 99999999))
                },
                "scan_events": scans,
                "hearing_log": hearings,
                "execution_log": [],
                "documents": [],
                "file_missing_report": None,
                "red_flag_notified_at": None,
                "auto_escalated": False
            }
            cases[key] = case_obj
            
    # Save to cases.json
    with open(APP_DB_JSON, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)
        
    print(f"Successfully seeded {len(cases)} cases to {APP_DB_JSON}")

if __name__ == "__main__":
    main()

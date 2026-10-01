"""
seed_db.py - Seed the SQLite database with real Nigerian court case data.

Data sources:
- real_scn_cases_sample.csv: 66 real cases from NigeriaLII and LawPavilion
- scn_appeal_cases_data.csv: 4,696 SCN appeal cases for distribution enrichment

Run: python -m backend.seed_db
"""

import csv
import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from backend.database import get_db_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("courtlog.seed")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
REAL_CASES_CSV = os.path.join(DATA_DIR, "real_scn_cases_sample.csv")
SCN_APPEALS_CSV = os.path.join(DATA_DIR, "scn_appeal_cases_data.csv")

COURT_MAP = {
    "SC": "Supreme Court of Nigeria",
    "CA": "Court of Appeal",
    "FHC": "Federal High Court",
}

ZONES = ["South-West", "South-South", "South-East", "FCT", "North-West", "North-Central", "North-East"]
ZONE_PROBS = [0.37, 0.23, 0.14, 0.09, 0.09, 0.06, 0.02]

REASON_CODES = [
    "Counsel Absent", "No Service", "Witness Unavailable", "Judge Absent",
    "Court Congestion", "Pending Ruling", "Application for Adjournment", "Case Transfer",
]
REASON_WEIGHTS = [0.25, 0.20, 0.15, 0.12, 0.10, 0.08, 0.06, 0.04]

SCAN_LOCATIONS = [
    "Registry Filing Counter", "Registry Desk A", "Registry Desk B",
    "Court Clerk Office", "Judge Chambers", "Courtroom File Rack",
    "Enforcement Unit", "Records Archive",
]

STAFF_IDS = ["ST-002", "ST-003", "ST-005", "ST-010", "ST-012", "ST-044", "ST-081", "ST-090"]


def _load_scn_distributions() -> Dict[str, List[int]]:
    """Load real party/witness count distributions from SCN appeal data."""
    distributions: Dict[str, List[int]] = {"party_counts": [], "witness_counts": []}
    if not os.path.exists(SCN_APPEALS_CSV):
        logger.warning("SCN appeals CSV not found, using defaults")
        return distributions

    with open(SCN_APPEALS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                complainants = int(row.get("no_complainant", 1) or 1)
                appellants = int(row.get("no_appealant", 1) or 1)
                distributions["party_counts"].append(complainants + appellants)
                public_w = int(row.get("no_public_witness", 0) or 0)
                eye_w = int(row.get("no_eye_witness", 0) or 0)
                defense_w = int(row.get("no_defense_witness", 0) or 0)
                distributions["witness_counts"].append(public_w + eye_w + defense_w)
            except (ValueError, TypeError):
                continue

    logger.info(f"Loaded distributions from {len(distributions['party_counts'])} SCN records")
    return distributions


def _map_court(raw_court: str) -> str:
    """Map court code to full name."""
    code = raw_court.strip().upper()
    for key, name in COURT_MAP.items():
        if code.startswith(key):
            return name
    return raw_court


def _classify_case_type(raw_type: str) -> str:
    """Map detailed case type to major category."""
    t = raw_type.lower()
    if any(kw in t for kw in ("criminal", "terrorism", "fraud", "corruption", "murder", "robbery", "theft")):
        return "Criminal"
    if "election" in t:
        return "Election Petition"
    if any(kw in t for kw in ("land", "trespass", "property")):
        return "Land/Property"
    if any(kw in t for kw in ("banking", "garnishee", "contract", "commercial", "company")):
        return "Commercial"
    if any(kw in t for kw in ("family", "matrimonial", "probate")):
        return "Family/Probate"
    if any(kw in t for kw in ("constitutional", "fundamental", "human rights")):
        return "Constitutional/Fundamental Rights"
    if any(kw in t for kw in ("admiralty", "mining", "oil")):
        return "Admiralty"
    return "Civil"


def _risk_score_from_years(years_str: str) -> float:
    """Calculate delay risk score from real Years to Conclusion data."""
    if years_str == "Pending" or not years_str:
        return round(random.uniform(0.65, 0.80), 2)
    try:
        years = int(years_str)
    except ValueError:
        return 0.50
    if years <= 1:
        return round(random.uniform(0.05, 0.20), 2)
    elif years <= 3:
        return round(random.uniform(0.20, 0.45), 2)
    elif years <= 5:
        return round(random.uniform(0.45, 0.70), 2)
    elif years <= 10:
        return round(random.uniform(0.70, 0.90), 2)
    else:
        return round(random.uniform(0.90, 0.99), 2)


def _generate_hearings(
    filing_date: datetime,
    judgment_date: datetime | None,
    years_str: str,
) -> Tuple[List[Dict[str, Any]], int]:
    """Generate realistic hearing log from real case duration data."""
    hearing_log: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    if years_str == "Pending" or not years_str:
        num_hearings = random.randint(1, 4)
        end_date = now
    else:
        try:
            years = int(years_str)
        except ValueError:
            years = 3
        num_hearings = max(1, min(years * random.randint(2, 4), 20))
        end_date = judgment_date or (filing_date + timedelta(days=years * 365))

    adjournment_count = 0
    current_date = filing_date + timedelta(days=random.randint(30, 90))

    for i in range(num_hearings):
        if current_date >= end_date:
            break
        is_last = (i == num_hearings - 1) and judgment_date is not None
        if is_last:
            outcome = "Heard"
            reason = "None"
        elif random.random() < 0.70:
            outcome = "Adjourned"
            reason = random.choices(REASON_CODES, weights=REASON_WEIGHTS, k=1)[0]
            adjournment_count += 1
        else:
            outcome = "Heard"
            reason = "None"

        next_date = current_date + timedelta(days=random.randint(30, 120))
        hearing_log.append({
            "date": current_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "outcome": outcome,
            "reason_code": reason,
            "next_date": next_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        current_date = next_date

    return hearing_log, adjournment_count


def _generate_scans(filing_date: datetime, judgment_date: datetime | None) -> List[Dict[str, Any]]:
    """Generate realistic file scan events."""
    scans: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    end_date = judgment_date or now

    scans.append({
        "location": "Registry Filing Counter",
        "timestamp": (filing_date + timedelta(hours=random.randint(1, 4))).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "staff_id": random.choice(STAFF_IDS),
    })

    num_scans = random.randint(2, 5)
    total_days = max(1, (end_date - filing_date).days)
    for _ in range(num_scans):
        offset = random.randint(1, total_days)
        scan_date = filing_date + timedelta(days=offset)
        if scan_date > now:
            scan_date = now - timedelta(days=random.randint(1, 30))
        scans.append({
            "location": random.choice(SCAN_LOCATIONS[1:]),
            "timestamp": scan_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "staff_id": random.choice(STAFF_IDS),
        })

    scans.sort(key=lambda x: x["timestamp"])
    return scans


def seed_cases(db: Any) -> int:
    """Seed the database with real case data."""
    if not os.path.exists(REAL_CASES_CSV):
        logger.error(f"Real cases CSV not found at {REAL_CASES_CSV}")
        return 0

    distributions = _load_scn_distributions()
    now = datetime.now(timezone.utc)
    count = 0

    with open(REAL_CASES_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            case_ref = row.get("Case Ref", "").strip()
            if not case_ref:
                continue

            year_filed_str = row.get("Year Filed", "2020")
            year_decided_str = row.get("Year Decided", "")
            years_to_conclusion = row.get("Years to Conclusion", "")
            risk_level = row.get("Risk Level", "Medium")

            try:
                year_filed = int(year_filed_str)
            except (ValueError, TypeError):
                year_filed = 2020

            filing_date = datetime(
                year=year_filed, month=random.randint(1, 12),
                day=random.randint(1, 28), tzinfo=timezone.utc,
            )

            judgment_date = None
            judgment_status = "Pending"
            if year_decided_str and years_to_conclusion != "Pending":
                try:
                    year_decided = int(year_decided_str)
                    judgment_date = datetime(
                        year=year_decided, month=random.randint(1, 12),
                        day=random.randint(1, 28), tzinfo=timezone.utc,
                    )
                    judgment_status = "Delivered"
                except (ValueError, TypeError):
                    pass

            days_since_filing = max(0, (now - filing_date).days)
            risk_score = _risk_score_from_years(years_to_conclusion)
            risk_flag = risk_level in ("High", "Medium") and risk_score > 0.60

            raw_type = row.get("Case Type", "Civil")
            case_type = _classify_case_type(raw_type)
            court = _map_court(row.get("Court", "SC"))
            zone = random.choices(ZONES, weights=ZONE_PROBS, k=1)[0]

            num_parties = 2
            if distributions["party_counts"]:
                num_parties = random.choice(distributions["party_counts"])

            hearing_log, adj_count = _generate_hearings(filing_date, judgment_date, years_to_conclusion)
            scan_events = _generate_scans(filing_date, judgment_date)

            execution_log: List[Dict[str, Any]] = []
            if judgment_status == "Delivered" and judgment_date:
                execution_log.append({
                    "action": "Delivered",
                    "date": judgment_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "sheriff_id": random.choice(STAFF_IDS),
                })
                if random.random() < 0.30:
                    enforce_date = judgment_date + timedelta(days=random.randint(5, 60))
                    execution_log.append({
                        "action": random.choice(["Writ of Fi Fa Filed", "Garnishee Order Filed"]),
                        "date": enforce_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "sheriff_id": f"SH-{random.randint(1, 50):03d}",
                    })

            case_data = {
                "case_id": case_ref,
                "case_title": row.get("Title", "Unknown Parties"),
                "case_type": case_type,
                "sub_type": raw_type,
                "court": court,
                "zone": zone,
                "assigned_division": case_type,
                "assigned_judge_id": "usr_judge_01",
                "filing_date": filing_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "judgment_date": judgment_date.strftime("%Y-%m-%dT%H:%M:%SZ") if judgment_date else None,
                "years_to_conclusion": years_to_conclusion,
                "adjournment_count": adj_count,
                "days_since_filing": days_since_filing,
                "judgment_status": judgment_status,
                "delay_risk_score": risk_score,
                "risk_flag": risk_flag,
                "risk_level": risk_level,
                "reform_era": row.get("Reform Era", "pre-ACJA"),
                "source_citation": row.get("Source", ""),
                "num_parties": num_parties,
                "dcr_approval_required": adj_count >= 5,
                "dcr_override_reason": None,
                "adjournment_blocked": adj_count >= 5,
                "custody_alert": False,
                "enforcement_non_compliant": False,
                "party_contact": {
                    "counsel_phone": f"+23480{random.randint(10000000, 99999999)}",
                    "litigant_phone": f"+23481{random.randint(10000000, 99999999)}",
                },
                "scan_events": scan_events,
                "hearing_log": hearing_log,
                "execution_log": execution_log,
                "documents": [],
                "file_missing_report": None,
                "red_flag_notified_at": None,
                "auto_escalated": False,
            }

            db.save_case(case_ref, case_data)
            count += 1
            logger.info(f"Seeded: {case_ref} ({case_type} | {court} | {risk_level})")

    return count


def main() -> None:
    """Seed the database with real case data."""
    logger.info("Starting CourtLOG database seed with real case data...")
    db = get_db_client()

    existing = db.list_cases()
    if existing:
        logger.warning(f"Database has {len(existing)} cases. Clearing and re-seeding...")
        if hasattr(db, "_clear_cases"):
            db._clear_cases()
        else:
            logger.error("Cannot clear cases. Delete data/courtlog.db and re-run.")
            return

    count = seed_cases(db)
    logger.info(f"Seed complete: {count} real cases loaded.")

    cases = db.list_cases()
    users = db.list_users()
    logger.info(f"Verification: {len(cases)} cases, {len(users)} users.")


if __name__ == "__main__":
    main()

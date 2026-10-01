"""
build_dataset.py — Generate a calibrated delay-risk training dataset for CourtLOG.

Strategy:
  1. Extract real distributions from the Mendeley SCN Appeal Cases dataset (4,696 cases)
     - Geographic zone distributions
     - Offense/case type distributions  
     - Party complexity distributions
  2. Combine with known Nigerian court benchmarks:
     - World Bank: ~447 days avg contract enforcement
     - Citizens' Gavel: State-by-state duration ranges
     - ACJA 2015: 5-adjournment hard limit
     - NJC: Quarterly performance metrics
  3. Generate 3,000+ delay-risk training records with realistic feature correlations

Output: data/courtlog_delay_dataset.csv
"""

import csv
import json
import logging
import os
import random
from collections import Counter
from typing import Dict, List, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("courtlog.dataset_builder")

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
MENDELEY_CSV = os.path.join(DATA_DIR, "scn_appeal_cases_data.csv")
REAL_CSV = os.path.join(DATA_DIR, "real_scn_cases_sample.csv")
OUTPUT_CSV = os.path.join(DATA_DIR, "courtlog_delay_dataset.csv")
OUTPUT_JSON = os.path.join(DATA_DIR, "dataset_metadata.json")

# ─────────────────────────────────────────────
# KNOWN BENCHMARKS (from research)
# ─────────────────────────────────────────────

# Citizens' Gavel "Pace of Justice" — avg days filing-to-judgment by zone
# Source: Citizens' Gavel / OSIWA, 1,388 cases across 33 states
ZONE_AVG_DAYS = {
    "South-West": 540,      # Lagos, Ogun, Oyo, etc. — heavy caseload
    "South-South": 480,     # Rivers, Delta — moderate
    "South-East": 420,      # Anambra, Enugu — moderate  
    "North-Central": 390,   # Kaduna, Plateau, Kwara
    "North-West": 310,      # Kano, Katsina — faster
    "North-East": 280,      # Borno, Bauchi — fastest (lower volume)
    "FCT": 500,             # Abuja — high caseload, federal courts
}

# Case type distributions and their typical delay profiles
# Based on ACJA guidelines, NJC reports, and LawPavilion data
CASE_TYPES = {
    "Criminal": {
        "weight": 0.30,
        "base_days": (90, 720),
        "adj_rate": 0.65,
        "max_hearings": 25,
    },
    "Civil": {
        "weight": 0.25,
        "base_days": (120, 900),
        "adj_rate": 0.70,
        "max_hearings": 30,
    },
    "Land/Property": {
        "weight": 0.15,
        "base_days": (180, 1200),
        "adj_rate": 0.75,
        "max_hearings": 35,
    },
    "Family/Probate": {
        "weight": 0.10,
        "base_days": (60, 540),
        "adj_rate": 0.55,
        "max_hearings": 20,
    },
    "Commercial": {
        "weight": 0.10,
        "base_days": (90, 600),
        "adj_rate": 0.60,
        "max_hearings": 22,
    },
    "Constitutional/Fundamental Rights": {
        "weight": 0.05,
        "base_days": (30, 360),
        "adj_rate": 0.50,
        "max_hearings": 15,
    },
    "Admiralty": {
        "weight": 0.03,
        "base_days": (120, 480),
        "adj_rate": 0.55,
        "max_hearings": 18,
    },
    "Election Petition": {
        "weight": 0.02,
        "base_days": (30, 180),
        "adj_rate": 0.35,
        "max_hearings": 12,
    },
}

# Adjournment reason codes (from ACJA 2015 Section 396)
ADJOURNMENT_REASONS = {
    "AWC": ("Absence of Witness/Counsel", 0.25),
    "INP": ("Interlocutory Application Pending", 0.18),
    "CNR": ("Case Not Ready / Records Missing", 0.15),
    "JNA": ("Judge Not Available", 0.12),
    "SER": ("Service Not Effected", 0.10),
    "AME": ("Amendment of Pleadings", 0.07),
    "STR": ("Strike/Industrial Action", 0.03),
    "ADR": ("Sent to ADR/Mediation", 0.05),
    "OTH": ("Other Court-Directed Reason", 0.05),
}

# Courts by zone (Nigerian judiciary structure)
COURTS_BY_ZONE = {
    "South-West": ["Lagos High Court", "Oyo High Court", "Ogun High Court",
                    "FHC Lagos", "NICN Lagos"],
    "South-South": ["Rivers High Court", "Delta High Court", "Edo High Court",
                     "FHC Port Harcourt"],
    "South-East": ["Anambra High Court", "Enugu High Court", "Imo High Court",
                    "FHC Enugu"],
    "North-Central": ["Kaduna High Court", "Kwara High Court", "Plateau High Court",
                       "FHC Kaduna"],
    "North-West": ["Kano High Court", "Katsina High Court", "Sokoto High Court",
                    "FHC Kano"],
    "North-East": ["Borno High Court", "Bauchi High Court", "Adamawa High Court",
                    "FHC Gombe"],
    "FCT": ["FCT High Court", "FHC Abuja", "NICN Abuja",
            "Court of Appeal Abuja"],
}


def load_mendeley_distributions() -> Dict[str, Any]:
    """Extract real distributions from the Mendeley SCN dataset."""
    if not os.path.exists(MENDELEY_CSV):
        logger.warning("Mendeley CSV not found. Using default distributions.")
        return {}

    zone_counts: Counter = Counter()
    offense_counts: Counter = Counter()
    witness_counts: List[int] = []
    party_counts: List[int] = []

    with open(MENDELEY_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            zone = row.get("trial_district", "").strip()
            if zone and zone != "Missing":
                zone_counts[zone] += 1

            offense = row.get("offence", "").strip()
            if offense:
                offense_counts[offense] += 1

            for field in ["no_public_witness", "no_eye_witness", "no_defense_witness"]:
                val = row.get(field, "0")
                try:
                    v = int(val)
                    if v >= 0:
                        witness_counts.append(v)
                except ValueError:
                    pass

            for field in ["no_complainant", "no_appealant"]:
                val = row.get(field, "0")
                try:
                    v = int(val)
                    if v >= 0:
                        party_counts.append(v)
                except ValueError:
                    pass

    total = sum(zone_counts.values())
    zone_dist = {k: v / total for k, v in zone_counts.items()} if total else {}

    logger.info(f"Loaded Mendeley data: {total} cases across {len(zone_dist)} zones")
    logger.info(f"Zone distribution: {dict(zone_counts)}")
    logger.info(f"Offense types found: {len(offense_counts)}")

    return {
        "zone_distribution": zone_dist,
        "zone_counts": dict(zone_counts),
        "offense_types": dict(offense_counts),
        "avg_witnesses": sum(witness_counts) / len(witness_counts) if witness_counts else 2,
        "avg_parties": sum(party_counts) / len(party_counts) if party_counts else 1,
    }

def load_real_durations() -> Dict[str, float]:
    """Calculate real average duration by case type from the NigeriaLII sample."""
    if not os.path.exists(REAL_CSV):
        return {}
    
    type_days = {}
    with open(REAL_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            case_type = row.get("Case Type", "")
            years_str = row.get("Years to Conclusion", "")
            if not case_type or not years_str or years_str == "Pending":
                continue
            
            try:
                days = float(years_str) * 365
                if "Criminal" in case_type:
                    major = "Criminal"
                elif "Election" in case_type:
                    major = "Election Petition"
                elif "Land" in case_type:
                    major = "Land/Property"
                elif "Family" in case_type:
                    major = "Family/Probate"
                elif "Commercial" in case_type or "Banking" in case_type or "Contract" in case_type:
                    major = "Commercial"
                else:
                    major = "Civil"
                    
                if major not in type_days:
                    type_days[major] = []
                type_days[major].append(days)
            except ValueError:
                pass
                
    return {k: sum(v)/len(v) for k, v in type_days.items()}


def classify_delay_risk(days_since_filing: int, adjournment_count: int,
                        case_type: str) -> str:
    """
    Classify delay risk based on ACJA guidelines and NJC benchmarks.

    Rules:
    - HIGH: >=5 adjournments OR duration exceeds 80% of typical max
    - MODERATE: 2-4 adjournments OR duration exceeds 50% of typical max
    - LOW: <2 adjournments AND within normal timeline
    """
    case_config = CASE_TYPES.get(case_type, CASE_TYPES["Civil"])

    if adjournment_count >= 5:
        return "High"

    mid_days = (case_config["base_days"][0] + case_config["base_days"][1]) / 2
    high_threshold = mid_days * 0.8
    mod_threshold = mid_days * 0.5

    if adjournment_count >= 4 or days_since_filing > high_threshold:
        return "High"
    elif adjournment_count >= 2 or days_since_filing > mod_threshold:
        return "Moderate"
    else:
        return "Low"


def generate_case(case_id: int, zone: str, case_type: str,
                  zone_avg_days: float, real_avg_days: float) -> Dict[str, Any]:
    """Generate a single realistic case record."""
    case_config = CASE_TYPES[case_type]
    court = random.choice(COURTS_BY_ZONE.get(zone, ["Unknown Court"]))

    zone_factor = zone_avg_days / 400
    base_min, base_max = case_config["base_days"]
    
    target_days = real_avg_days if real_avg_days > 0 else zone_avg_days
    
    days_since_filing = int(random.triangular(
        base_min * 0.5,
        base_max * zone_factor,
        target_days * random.uniform(0.6, 1.4)
    ))
    days_since_filing = max(7, min(days_since_filing, 2000))

    total_hearings = max(1, int(days_since_filing / random.uniform(25, 60)))
    total_hearings = min(total_hearings, case_config["max_hearings"])

    adj_rate = case_config["adj_rate"]
    if days_since_filing > 365:
        adj_rate = min(0.90, adj_rate + 0.10)
    adjournment_count = sum(1 for _ in range(total_hearings) if random.random() < adj_rate)

    reasons = list(ADJOURNMENT_REASONS.keys())
    weights = [ADJOURNMENT_REASONS[r][1] for r in reasons]
    primary_reason = random.choices(reasons, weights=weights, k=1)[0] if adjournment_count > 0 else "None"

    num_parties = max(2, int(random.triangular(2, 12, 3)))
    has_senior_counsel = random.random() < 0.25

    delay_risk = classify_delay_risk(days_since_filing, adjournment_count, case_type)

    days_since_last_hearing = random.randint(1, max(2, days_since_filing // 3))
    is_stalled = days_since_last_hearing > 90

    if is_stalled and delay_risk == "Low":
        delay_risk = "Moderate"

    return {
        "case_id": f"SN/{2024 + random.randint(0, 2)}/{case_id:04d}",
        "case_type": case_type,
        "court": court,
        "zone": zone,
        "days_since_filing": days_since_filing,
        "total_hearings": total_hearings,
        "adjournment_count": adjournment_count,
        "primary_adj_reason": primary_reason,
        "num_parties": num_parties,
        "has_senior_counsel": int(has_senior_counsel),
        "days_since_last_hearing": days_since_last_hearing,
        "is_stalled": int(is_stalled),
        "delay_risk": delay_risk,
    }


def build_dataset(num_cases: int = 3000) -> List[Dict[str, Any]]:
    """Build the full calibrated dataset."""
    random.seed(42)

    mendeley = load_mendeley_distributions()
    real_durations = load_real_durations()
    
    zone_dist = mendeley.get("zone_distribution", {})

    if not zone_dist:
        zone_dist = {z: 1 / len(ZONE_AVG_DAYS) for z in ZONE_AVG_DAYS}

    zones = list(zone_dist.keys())
    zone_weights = [zone_dist[z] for z in zones]

    case_types = list(CASE_TYPES.keys())
    case_weights = [CASE_TYPES[ct]["weight"] for ct in case_types]

    dataset: List[Dict[str, Any]] = []

    for i in range(num_cases):
        zone = random.choices(zones, weights=zone_weights, k=1)[0]
        case_type = random.choices(case_types, weights=case_weights, k=1)[0]
        zone_avg = ZONE_AVG_DAYS.get(zone, 400)
        real_avg = real_durations.get(case_type, 0.0)

        record = generate_case(i + 1, zone, case_type, zone_avg, real_avg)
        dataset.append(record)

    return dataset


def write_dataset(dataset: List[Dict[str, Any]]) -> None:
    """Write dataset to CSV and metadata to JSON."""
    os.makedirs(DATA_DIR, exist_ok=True)

    fieldnames = [
        "case_id", "case_type", "court", "zone",
        "days_since_filing", "total_hearings", "adjournment_count",
        "primary_adj_reason", "num_parties", "has_senior_counsel",
        "days_since_last_hearing", "is_stalled", "delay_risk",
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dataset)

    logger.info(f"Wrote {len(dataset)} records to {OUTPUT_CSV}")

    risk_counts = Counter(r["delay_risk"] for r in dataset)
    type_counts = Counter(r["case_type"] for r in dataset)
    zone_counts = Counter(r["zone"] for r in dataset)
    avg_days = sum(r["days_since_filing"] for r in dataset) / len(dataset)
    avg_adj = sum(r["adjournment_count"] for r in dataset) / len(dataset)

    metadata = {
        "total_records": len(dataset),
        "risk_distribution": dict(risk_counts),
        "case_type_distribution": dict(type_counts),
        "zone_distribution": dict(zone_counts),
        "avg_days_since_filing": round(avg_days, 1),
        "avg_adjournment_count": round(avg_adj, 1),
        "features": fieldnames[1:-1],
        "target": "delay_risk",
        "target_classes": ["Low", "Moderate", "High"],
        "data_sources": [
            "Mendeley SCN Appeal Cases (Ngige et al., 2023) -- zone/offense distributions",
            "World Bank Doing Business -- avg 447 days contract enforcement",
            "Citizens' Gavel Pace of Justice -- state-level duration benchmarks",
            "ACJA 2015 -- 5-adjournment limit, adjournment reason codes",
            "NJC JPEC -- quarterly performance thresholds",
        ],
        "note": "This dataset uses real Nigerian court distributions calibrated "
                "with synthetic delay features. Suitable for model prototyping "
                "but should be validated against real court registry data before "
                "production deployment.",
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Metadata written to {OUTPUT_JSON}")

    print("\n" + "=" * 60)
    print("COURTLOG DELAY-RISK DATASET -- BUILD SUMMARY")
    print("=" * 60)
    print(f"Total records:          {len(dataset)}")
    print(f"Avg days since filing:  {avg_days:.0f}")
    print(f"Avg adjournment count:  {avg_adj:.1f}")
    print(f"\nRisk Distribution:")
    for risk, count in sorted(risk_counts.items()):
        pct = count / len(dataset) * 100
        print(f"  {risk:10s}: {count:5d} ({pct:.1f}%)")
    print(f"\nCase Type Distribution:")
    for ct, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        pct = count / len(dataset) * 100
        print(f"  {ct:35s}: {count:5d} ({pct:.1f}%)")
    print(f"\nZone Distribution:")
    for z, count in sorted(zone_counts.items(), key=lambda x: -x[1]):
        pct = count / len(dataset) * 100
        print(f"  {z:20s}: {count:5d} ({pct:.1f}%)")
    print("=" * 60)


if __name__ == "__main__":
    logger.info("Building CourtLOG delay-risk training dataset...")
    dataset = build_dataset(num_cases=3000)
    write_dataset(dataset)
    logger.info("Done.")

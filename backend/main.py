import os
import joblib
import logging
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Body, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from backend.database import get_db_client, parse_date, format_date, verify_password
from backend.whatsapp import send_adjournment_broadcast
from backend.auth import create_access_token, create_refresh_token, verify_token, get_current_user

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("courtlog.main")

# Initialize FastAPI
app = FastAPI(title="COURTLOG 2.0 API", description="Court File Tracking & Delay Compliance System API")

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables
db = get_db_client()

def can_access_case(case: Dict[str, Any], auth: Dict[str, str]) -> bool:
    """Fail closed; use the current stored profile, never client-supplied scope."""
    user = db.get_user(auth["user_id"])
    if not user or user.get("disabled"):
        return False
    role = user.get("role")
    if role == "Chief Registrar":
        return True
    if role == "Judge":
        return case.get("assigned_judge_id") == user["user_id"]
    if role == "DCR":
        return bool(user.get("division")) and case.get("assigned_division") == user["division"]
    if role == "Clerk":
        return bool(user.get("court")) and case.get("court") == user["court"]
    if role == "Sheriff":
        scans = case.get("scan_events", [])
        missing = case.get("file_missing_report") or {}
        return (case.get("assigned_sheriff_id") == user["user_id"]
                or bool(scans and scans[-1].get("staff_id") == user["user_id"])
                or missing.get("reported_by") == user["user_id"])
    return False


def authorize_case(case: Dict[str, Any], auth: Dict[str, str]) -> None:
    if not can_access_case(case, auth):
        raise HTTPException(status_code=403, detail="Case is outside your assigned scope")


def scoped_cases(auth: Dict[str, str]) -> List[Dict[str, Any]]:
    return [case for case in db.list_cases() if can_access_case(case, auth)]


# In-memory storage for the simulated WhatsApp broadcasts log
whatsapp_logs = []

# Paths for ML Model loading
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MODEL_PATH = os.path.join(DATA_DIR, "delay_model.joblib")
ENCODERS_PATH = os.path.join(DATA_DIR, "label_encoders.joblib")

# Load ML model and encoders at module level
model = None
encoders = None
if os.path.exists(MODEL_PATH) and os.path.exists(ENCODERS_PATH):
    try:
        model = joblib.load(MODEL_PATH)
        encoders = joblib.load(ENCODERS_PATH)
        logger.info("ML Delay model and encoders loaded successfully at module level.")
    except Exception as e:
        logger.error(f"Error loading ML model/encoders: {e}")
else:
    logger.warning("ML Model/encoders not found. Please train the model first by running train_model.py.")

# Use real current time instead of frozen simulation time
def get_current_time():
    """Returns the current UTC time for all compliance calculations."""
    return datetime.now(timezone.utc)

@app.on_event("startup")
def startup_event():
    logger.info("Starting up CourtLog 2.0 Backend...")
    # Run initial compliance sweep
    run_compliance_checks_sync()

# Helper Pydantic Models for Input Validation
class ScanRequest(BaseModel):
    case_id: str
    location: str
    staff_id: str

class HearingRequest(BaseModel):
    outcome: str  # "Heard" or "Adjourned"
    reason_code: Optional[str] = "None"
    next_date: str  # ISO8601 string

class ExecutionRequest(BaseModel):
    action: str  # "Writ of Fi Fa Filed", "Garnishee Order Filed", etc.
    sheriff_id: str

class CaseCreateRequest(BaseModel):
    case_id: str
    case_type: str
    court: str
    counsel_phone: str
    litigant_phone: str

class DCROverrideRequest(BaseModel):
    exceptional_reason: str

class LoginRequest(BaseModel):
    username: str
    password: str

class ReassignRequest(BaseModel):
    new_division: Optional[str] = None
    new_court: Optional[str] = None
    reason: str

class AssignJudgeRequest(BaseModel):
    judge_id: str
    reason: Optional[str] = "Balloting assignment"

class FileMissingRequest(BaseModel):
    last_known_location: str
    notes: Optional[str] = ""

class DocumentUploadRequest(BaseModel):
    document_type: str  # "Ruling", "Motion", "Exhibit", "Affidavit", etc.
    title: str
    filename: str
    notes: Optional[str] = ""

class UserCreateRequest(BaseModel):
    name: str
    role: str  # Sheriff, Clerk, DCR, Chief Registrar, Judge
    badge: str
    court: str
    division: str
# get_current_user is imported from backend.auth and used as a FastAPI Depends()
# It validates Bearer tokens and returns {"user_id": ..., "role": ...}

@app.post("/api/login")
def login(req: LoginRequest):
    """Authenticate user and return JWT tokens."""
    users = db.list_users()
    username_lower = req.username.strip().lower()
    
    for user in users:
        u_name = str(user.get("username", "")).strip().lower()
        u_pass = str(user.get("password", ""))
        if u_name == username_lower and verify_password(req.password, u_pass):
            logger.info(f"User {u_name} authenticated successfully.")
            # Build JWT claims
            token_data = {
                "sub": user["user_id"],
                "role": user.get("role", "Clerk"),
                "username": user.get("username", ""),
            }
            access_token = create_access_token(token_data)
            refresh_token = create_refresh_token(token_data)
            # Return user info without password hash
            safe_user = {k: v for k, v in user.items() if k != "password"}
            return {
                "status": "success",
                "message": "Authentication successful",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "user": safe_user,
            }
            
    raise HTTPException(status_code=401, detail="Invalid username or password.")


@app.post("/api/refresh")
def refresh_token_endpoint(body: Dict[str, str] = Body(...)):
    """Exchange a valid refresh token for a new access token."""
    token = body.get("refresh_token", "")
    if not token:
        raise HTTPException(status_code=400, detail="refresh_token is required")
    
    payload = verify_token(token)  # Raises 401 if invalid/expired
    
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=400, detail="Not a refresh token")
    
    user = db.get_user(payload.get("sub", ""))
    if not user or user.get("disabled"):
        raise HTTPException(status_code=401, detail="Account is no longer active")
    new_token_data = {
        "sub": payload["sub"],
        "role": user["role"],
        "username": payload.get("username", ""),
    }
    new_access_token = create_access_token(new_token_data)
    return {
        "access_token": new_access_token,
        "token_type": "bearer",
    }

# ----------------- COMPLIANCE SWEEP LOGIC -----------------
def run_compliance_checks_sync():
    """
    Synchronously updates all dynamic metrics for cases:
    1. Days since filing based on get_current_time() (July 18, 2026).
    2. Custody alert flag (True if no scan events in the last 7 consecutive days).
    3. Enforcement non-compliant flag (True if judgment_status == 'Delivered' and 
       no subsequent enforcement entry in execution_log within 90 days of judgment delivery).
    """
    cases = db.list_cases()
    logger.info(f"Running compliance sweep on {len(cases)} cases...")
    
    for case in cases:
        case_id = case["case_id"]
        updates = {}
        
        # 1. Update days since filing
        filing_dt = parse_date(case["filing_date"])
        days_elapsed = (get_current_time() - filing_dt).days
        updates["days_since_filing"] = max(0, days_elapsed)
        
        # 2. Custody Alert Flag (Module 1)
        # If pending case file has not had a new scan event in the last 7 consecutive days, set custody_alert = True
        if case.get("judgment_status") == "Pending":
            scans = case.get("scan_events", [])
            if scans:
                # Find the latest scan event
                latest_scan = max(scans, key=lambda x: parse_date(x["timestamp"]))
                scan_dt = parse_date(latest_scan["timestamp"])
                days_since_scan = (get_current_time() - scan_dt).days
                updates["custody_alert"] = days_since_scan >= 7
            else:
                # Never scanned, check relative to filing date
                days_since_filing = (get_current_time() - filing_dt).days
                updates["custody_alert"] = days_since_filing >= 7
        else:
            # Not pending, no custody tracking needed
            updates["custody_alert"] = False
            
        # 3. Enforcement Tracker & 90-day Compliance (Module 4)
        # If judgment_status == "Delivered" and no entry added to execution_log within 90 days,
        # flag as "Enforcement Non-Compliant".
        if case.get("judgment_status") == "Delivered":
            exec_logs = case.get("execution_log", [])
            
            # Find the judgment delivery date.
            # In our schema, we locate either the first event in execution_log (which seeds list as "Judgment Delivered"),
            # or fallback to the last Heard date in hearing_log, or the case's filing date.
            judgment_delivery_dt = None
            
            # Look in execution_log for "Judgment Delivered" action
            for log in exec_logs:
                if "Delivered" in log.get("action", ""):
                    judgment_delivery_dt = parse_date(log["date"])
                    break
            
            # Fallback 1: Last hearing log where case was heard (which presumably led to judgment)
            if not judgment_delivery_dt:
                heard_hearings = [h for h in case.get("hearing_log", []) if h.get("outcome") == "Heard"]
                if heard_hearings:
                    latest_heard = max(heard_hearings, key=lambda x: parse_date(x["date"]))
                    judgment_delivery_dt = parse_date(latest_heard["date"])
            
            # Fallback 2: Filing date
            if not judgment_delivery_dt:
                judgment_delivery_dt = filing_dt
                
            # Now check for enforcement entries added within 90 days of judgment delivery date.
            # An enforcement entry is any event in execution_log OTHER than the judgment delivery event itself.
            enforcement_actions = [
                log for log in exec_logs 
                if "Delivered" not in log.get("action", "")
            ]
            
            if enforcement_actions:
                # Find the earliest enforcement action
                earliest_enforcement = min(enforcement_actions, key=lambda x: parse_date(x["date"]))
                enforce_dt = parse_date(earliest_enforcement["date"])
                days_to_enforce = (enforce_dt - judgment_delivery_dt).days
                
                # Non-compliant if enforcement occurred AFTER 90 days
                updates["enforcement_non_compliant"] = days_to_enforce > 90
            else:
                # No enforcement action has been taken yet.
                # Check if 90 days have already elapsed since the judgment was delivered.
                days_since_delivery = (get_current_time() - judgment_delivery_dt).days
                updates["enforcement_non_compliant"] = days_since_delivery > 90
        else:
            # If status is not "Delivered", it is compliant or pending
            updates["enforcement_non_compliant"] = False
            
        # 4. RED Flag Tracking & Auto-Escalation
        if case.get("risk_flag"):
            # Set notification timestamp if not already set
            if not case.get("red_flag_notified_at"):
                updates["red_flag_notified_at"] = format_date(get_current_time())
        else:
            updates["red_flag_notified_at"] = None
            updates["auto_escalated"] = False
            
        # 5. DCR 5th Adjournment Auto-Escalation (24h SLA)
        # If DCR approval is required, track time since red flag (which is set when blocked)
        if case.get("dcr_approval_required"):
            notified_time = case.get("red_flag_notified_at") or updates.get("red_flag_notified_at")
            if notified_time:
                notified_dt = parse_date(notified_time)
                hours_blocked = (get_current_time() - notified_dt).total_seconds() / 3600
                if hours_blocked > 24 and not case.get("auto_escalated"):
                    updates["auto_escalated"] = True
                    logger.warning(f"AUTO-ESCALATION: Case {case_id} blocked for >24h without DCR approval. Escalating to Chief Registrar.")
            
        # Write updates back to database
        db.update_case(case_id, updates)

# ----------------- INFERENCE HELPER -----------------
def run_model_inference(case_data: Dict[str, Any]) -> Dict[str, Any]:
    """Runs ML model inference to compute delay probability and sets the risk_flag."""
    global model, encoders
    if model is None or encoders is None:
        # Fallback to simple deterministic heuristics if model is not loaded
        logger.warning("ML Model not loaded. Running heuristic risk score calculation.")
        adjournment_count = int(case_data.get("adjournment_count", 0))
        days_since_filing = int(case_data.get("days_since_filing", 0))
        
        # Simple heuristic
        score = min(0.99, 0.10 + (adjournment_count * 0.12) + (days_since_filing * 0.0005))
        if case_data.get("case_type") == "Land Dispute":
            score += 0.15
        score = min(0.99, max(0.01, float(score)))
        
        return {
            "delay_risk_score": round(score, 3),
            "risk_flag": score > 0.70
        }
        
    try:
        # Prepare inputs
        adjournment_count = int(case_data.get("adjournment_count", 0))
        days_since_filing = int(case_data.get("days_since_filing", 0))
        case_type = case_data.get("case_type", "Civil Debt")
        court = case_data.get("court", "FHC Abuja Court 2")
        
        # Transform categorical with label encoding, handling unseen classes gracefully
        if case_type in encoders["case_type_classes"]:
            case_type_encoded = encoders["case_type"].transform([case_type])[0]
        else:
            case_type_encoded = 0  # fallback index
            
        if court in encoders["court_classes"]:
            court_encoded = encoders["court"].transform([court])[0]
        else:
            court_encoded = 0  # fallback index
            
        # Run model prediction
        import pandas as pd
        features = pd.DataFrame([{
            "adjournment_count": adjournment_count,
            "days_since_filing": days_since_filing,
            "case_type_encoded": case_type_encoded,
            "court_encoded": court_encoded
        }])
        probability = model.predict_proba(features)[0][1]  # Prob of stalled (class 1)
        
        return {
            "delay_risk_score": round(float(probability), 3),
            "risk_flag": bool(probability > 0.70)
        }
    except Exception as e:
        logger.error(f"Error running model inference: {e}")
        return {
            "delay_risk_score": 0.50,
            "risk_flag": False
        }


# ----------------- ENDPOINTS -----------------

# ----------------- USER MANAGEMENT ENDPOINTS -----------------

@app.get("/api/users", response_model=List[Dict[str, Any]])
def list_users(auth: Dict[str, str] = Depends(get_current_user)):
    """Lists all user accounts across the 5-level access hierarchy."""
    if auth["role"] != "Chief Registrar":
        raise HTTPException(status_code=403, detail="User management requires Chief Registrar authority")
    return [{k: v for k, v in user.items() if k != "password"} for user in db.list_users()]

@app.post("/api/users", status_code=201)
def create_user(req: UserCreateRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Creates a new user profile. Restricted to Chief Registrar."""
    if auth["role"] != "Chief Registrar":
        raise HTTPException(status_code=403, detail="Permission Denied: User management requires Chief Registrar authority.")
        
    user_id = f"usr_{req.role.lower().replace(' ', '_')}_{int(datetime.now().timestamp())}"
    new_user = {
        "user_id": user_id,
        "name": req.name,
        "role": req.role,
        "badge": req.badge,
        "court": req.court,
        "division": req.division
    }
    db.save_user(user_id, new_user)
    return new_user

@app.delete("/api/users/{user_id}")
def delete_user(user_id: str, auth: Dict[str, str] = Depends(get_current_user)):
    """Deletes a user account. Restricted to Chief Registrar."""
    if auth["role"] != "Chief Registrar":
        raise HTTPException(status_code=403, detail="Permission Denied: User management requires Chief Registrar authority.")
    if not db.get_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    if user_id == auth["user_id"]:
        raise HTTPException(status_code=409, detail="Cannot delete your own account")
    target = db.get_user(user_id)
    if target.get("role") == "Chief Registrar" and sum(u.get("role") == "Chief Registrar" and not u.get("disabled") for u in db.list_users()) <= 1:
        raise HTTPException(status_code=409, detail="Cannot delete the last active Chief Registrar")
    db.delete_user(user_id)
    return {"status": "success", "message": f"User {user_id} deleted."}


# ----------------- CASE & COMPLIANCE ENDPOINTS -----------------

@app.get("/api/cases", response_model=List[Dict[str, Any]])
def get_all_cases(auth: Dict[str, str] = Depends(get_current_user)):
    """Lists cases in the database filtered by role scope per 5-Level Hierarchy."""
    return scoped_cases(auth)


@app.post("/api/cases", status_code=201)
def create_case(req: CaseCreateRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Creates a new case file. Restricted to Clerks and Chief Registrar."""
    if auth["role"] not in ["Clerk", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Case creation is restricted to Court Clerks and Chief Registrar.")
        
    if auth["role"] == "Clerk":
        profile = db.get_user(auth["user_id"])
        if req.court != profile.get("court"):
            raise HTTPException(status_code=403, detail="Clerks may register cases only in their assigned court")

    if db.get_case(req.case_id):
        raise HTTPException(status_code=400, detail="Case ID already exists")
        
    new_case = {
        "case_id": req.case_id,
        "case_type": req.case_type,
        "court": req.court,
        "assigned_division": "Criminal" if "Criminal" in req.case_type else "Civil",
        "assigned_judge_id": "usr_judge_01",
        "filing_date": format_date(get_current_time()),
        "adjournment_count": 0,
        "days_since_filing": 0,
        "judgment_status": "Pending",
        "delay_risk_score": 0.1,
        "risk_flag": False,
        "dcr_approval_required": False,
        "dcr_override_reason": None,
        "adjournment_blocked": False,
        "party_contact": {
            "counsel_phone": req.counsel_phone,
            "litigant_phone": req.litigant_phone
        },
        "scan_events": [
            {
                "location": "Registry Desk A",
                "timestamp": format_date(get_current_time()),
                "staff_id": auth["user_id"]
            }
        ],
        "hearing_log": [],
        "execution_log": [],
        "custody_alert": False,
        "enforcement_non_compliant": False
    }
    
    # Calculate ML prediction initially
    pred = run_model_inference(new_case)
    new_case["delay_risk_score"] = pred["delay_risk_score"]
    new_case["risk_flag"] = pred["risk_flag"]
    
    db.save_case(req.case_id, new_case)
    return new_case

@app.post("/api/scan", response_model=Dict[str, Any])
def record_scan_event(req: ScanRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """
    Module 1: QR Chain of Custody.
    Scans physical file. Restricted to Sheriff, Clerk, or Chief Registrar.
    """
    if auth["role"] not in ["Sheriff", "Clerk", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: QR file scanning is restricted to Sheriff and Registry Staff.")
        
    case = db.get_case(req.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
        
    scan_event = {
        "location": req.location,
        "timestamp": format_date(get_current_time()),
        "staff_id": auth["user_id"]
    }
    
    # Append the event and clear custody alert
    updates = {
        "scan_events": [scan_event],
        "custody_alert": False
    }
    
    db.update_case(req.case_id, updates)
    
    case = db.get_case(req.case_id)
    filing_dt = parse_date(case["filing_date"])
    case["days_since_filing"] = max(0, (get_current_time() - filing_dt).days)
    
    pred = run_model_inference(case)
    
    db.update_case(req.case_id, {
        "days_since_filing": case["days_since_filing"],
        "delay_risk_score": pred["delay_risk_score"],
        "risk_flag": pred["risk_flag"]
    })
    
    return db.get_case(req.case_id)

@app.post("/api/cases/{case_id:path}/hearings", response_model=Dict[str, Any])
def log_hearing_outcome(case_id: str, req: HearingRequest, background_tasks: BackgroundTasks, auth: Dict[str, str] = Depends(get_current_user)):
    """
    Module 2: Hearing Compliance Engine.
    Enforces 5th Adjournment DCR Hard Block rule under ACJA/ACJL compliance.
    """
    if auth["role"] not in ["Clerk", "Judge", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Hearing log entry is restricted to Clerks and Judges.")

    # Judge can ONLY deliver rulings — not log adjournments (Clerks do 90% of work)
    if auth["role"] == "Judge" and req.outcome == "Adjourned":
        raise HTTPException(status_code=403, detail="Permission Denied: Judges do not log adjournments. Clerks handle hearing data entry. Judges may only deliver rulings.")
    if auth["role"] == "Judge" and req.outcome == "Heard" and req.reason_code not in ["Judgment Delivered", "Ruling Delivered"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Judges may only deliver final rulings/judgments through this system.")
        
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
        
    current_adj_count = case.get("adjournment_count", 0)
    
    # ----------------- 5TH ADJOURNMENT HARD BLOCK ENFORCEMENT -----------------
    if req.outcome == "Adjourned":
        if current_adj_count >= 4 and not case.get("dcr_override_reason"):
            # Mark case as requiring DCR approval and blocked
            db.update_case(case_id, {
                "dcr_approval_required": True,
                "adjournment_blocked": True,
                "risk_flag": True
            })
            raise HTTPException(
                status_code=400,
                detail="5th Adjournment BLOCKED by System under ACJA/ACJL Section 396 compliance rules. Requires Deputy Chief Registrar (DCR) approval with exceptional reason."
            )
            
    hearing_event = {
        "date": format_date(get_current_time()),
        "outcome": req.outcome,
        "reason_code": req.reason_code if req.outcome == "Adjourned" else "None",
        "next_date": req.next_date
    }
    
    updates = {
        "hearing_log": [hearing_event]
    }
    
    if req.outcome == "Adjourned":
        updates["adjournment_count"] = current_adj_count + 1
        
        background_tasks.add_task(
            send_adjournment_broadcast,
            case_id=case_id,
            next_date=req.next_date,
            reason_code=req.reason_code,
            group_id="registry-group-104"
        )
    elif req.outcome == "Heard" and req.reason_code in ["Judgment Delivered", "Ruling Delivered"]:
        updates["judgment_status"] = "Delivered"
        delivery_event = {
            "action": "Judgment Delivered",
            "date": format_date(get_current_time()),
            "sheriff_id": auth["user_id"]
        }
        updates["execution_log"] = [delivery_event]
        
    db.update_case(case_id, updates)
    
    case = db.get_case(case_id)
    filing_dt = parse_date(case["filing_date"])
    case["days_since_filing"] = max(0, (get_current_time() - filing_dt).days)
    
    pred = run_model_inference(case)
    
    db.update_case(case_id, {
        "days_since_filing": case["days_since_filing"],
        "delay_risk_score": pred["delay_risk_score"],
        "risk_flag": pred["risk_flag"]
    })
    
    return db.get_case(case_id)

@app.post("/api/cases/{case_id:path}/dcr-override", response_model=Dict[str, Any])
def override_dcr_adjournment(case_id: str, req: DCROverrideRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """
    Module 3: DCR 5th Adjournment Approval & Override.
    Allows DCR to upload exceptional reasons to unblock cases.
    """
    if auth["role"] not in ["DCR", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: 5th Adjournment override requires Deputy Chief Registrar (DCR) or Chief Registrar role.")
        
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
        
    updates = {
        "dcr_approval_required": False,
        "dcr_override_reason": req.exceptional_reason,
        "adjournment_blocked": False
    }
    
    db.update_case(case_id, updates)
    return db.get_case(case_id)

# ----------------- NEW ENDPOINTS: RBAC FEATURE COMPLETION -----------------

@app.post("/api/cases/{case_id:path}/report-missing", response_model=Dict[str, Any])
def report_file_missing(case_id: str, req: FileMissingRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """
    Sheriff-only: Report a case file as physically missing.
    Records who reported it, when, and last known location.
    """
    if auth["role"] not in ["Sheriff", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Only Sheriffs (Physical File Custodians) can report missing files.")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)

    missing_report = {
        "reported_by": auth["user_id"],
        "reported_at": format_date(get_current_time()),
        "last_known_location": req.last_known_location,
        "notes": req.notes,
        "resolved": False
    }

    db.update_case(case_id, {
        "file_missing_report": missing_report,
        "custody_alert": True,
        "risk_flag": True
    })

    logger.warning(f"FILE MISSING REPORT: Case {case_id} reported missing by {auth['user_id']} — last seen at {req.last_known_location}")
    return db.get_case(case_id)


@app.post("/api/cases/{case_id:path}/assign-judge", response_model=Dict[str, Any])
def assign_judge_to_case(case_id: str, req: AssignJudgeRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """
    CR-only: Assign or reassign a judge to a case (balloting).
    """
    if auth["role"] != "Chief Registrar":
        raise HTTPException(status_code=403, detail="Permission Denied: Judge assignment (balloting) requires Chief Registrar authority.")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)

    # Verify the judge exists
    judge = db.get_user(req.judge_id)
    if not judge or judge.get("role") != "Judge":
        raise HTTPException(status_code=400, detail=f"User {req.judge_id} is not a valid Judge account.")

    db.update_case(case_id, {
        "assigned_judge_id": req.judge_id,
    })

    logger.info(f"CASE ASSIGNMENT: {case_id} assigned to Judge {req.judge_id} by {auth['user_id']} — Reason: {req.reason}")
    return db.get_case(case_id)


@app.post("/api/cases/{case_id:path}/reassign", response_model=Dict[str, Any])
def reassign_case(case_id: str, req: ReassignRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """
    DCR/CR: Reassign a case to a different division or court.
    DCR can reassign within their division; CR can reassign anywhere.
    """
    if auth["role"] not in ["DCR", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Case reassignment requires DCR or Chief Registrar role.")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)

    updates = {}
    if req.new_division:
        updates["assigned_division"] = req.new_division
    if req.new_court:
        updates["court"] = req.new_court

    if not updates:
        raise HTTPException(status_code=400, detail="Must specify new_division or new_court for reassignment.")

    db.update_case(case_id, updates)

    logger.info(f"CASE REASSIGNMENT: {case_id} reassigned by {auth['user_id']} ({auth['role']}) — Reason: {req.reason}")
    return db.get_case(case_id)


@app.get("/api/export/dcr-weekly")
def export_dcr_weekly_report(auth: Dict[str, str] = Depends(get_current_user)):
    """
    DCR/CR: Generate weekly division performance report.
    Shows delay cases, pending overrides, and compliance score for the DCR's division.
    """
    if auth["role"] not in ["DCR", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Weekly report requires DCR or Chief Registrar authority.")

    user_profile = db.get_user(auth["user_id"])
    division = user_profile.get("division", "All Divisions") if user_profile else "All Divisions"

    cases = db.list_cases()

    # Filter by division (unless CR seeing all)
    if division and division != "All Divisions":
        division_cases = [c for c in cases if c.get("assigned_division") == division]
    else:
        division_cases = cases

    total = len(division_cases)
    stalled = [c for c in division_cases if c.get("risk_flag")]
    pending_overrides = [c for c in division_cases if c.get("dcr_approval_required")]
    blocked = [c for c in division_cases if c.get("adjournment_blocked")]
    missing_files = [c for c in division_cases if c.get("file_missing_report") and not c["file_missing_report"].get("resolved")]
    compliance_score = round(max(0, (1 - (len(stalled) / max(1, total))) * 100), 1)

    return {
        "report_title": f"DCR Weekly Division Report — {division}",
        "division": division,
        "generated_by": auth["user_id"],
        "export_date": format_date(get_current_time()),
        "summary": {
            "total_cases_in_division": total,
            "stalled_delay_cases": len(stalled),
            "pending_5th_adj_overrides": len(pending_overrides),
            "blocked_cases": len(blocked),
            "missing_file_reports": len(missing_files),
            "division_compliance_score": f"{compliance_score}%"
        },
        "stalled_case_ids": [c["case_id"] for c in stalled],
        "pending_override_ids": [c["case_id"] for c in pending_overrides],
        "missing_file_ids": [c["case_id"] for c in missing_files],
    }


@app.post("/api/cases/{case_id:path}/documents", response_model=Dict[str, Any])
def upload_document(case_id: str, req: DocumentUploadRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """
    Clerk/CR: Upload a document record (Ruling, Motion, Exhibit, Affidavit).
    Stores metadata; actual file goes to data/documents/{case_id}/.
    """
    if auth["role"] not in ["Clerk", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Document upload is restricted to Clerks and the Chief Registrar.")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)

    # Ensure documents directory exists
    docs_dir = os.path.join(DATA_DIR, "documents", case_id)
    os.makedirs(docs_dir, exist_ok=True)

    doc_record = {
        "document_type": req.document_type,
        "title": req.title,
        "filename": req.filename,
        "uploaded_by": auth["user_id"],
        "uploaded_at": format_date(get_current_time()),
        "notes": req.notes,
        "storage_path": os.path.join("data", "documents", case_id, req.filename)
    }

    db.update_case(case_id, {
        "documents": [doc_record]
    })

    logger.info(f"DOCUMENT UPLOADED: {req.document_type} '{req.title}' for case {case_id} by {auth['user_id']}")
    return db.get_case(case_id)


@app.get("/api/cases/{case_id:path}/alerts", response_model=Dict[str, Any])
def get_case_alerts(case_id: str, auth: Dict[str, str] = Depends(get_current_user)):
    """
    Returns active alerts for a specific case (24hr hearing alerts, RED flags, etc.).
    Used by Judge docket to show upcoming hearing warnings.
    """
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)

    alerts = []

    # Check for upcoming hearings within 24 hours
    hearing_log = case.get("hearing_log", [])
    if hearing_log:
        latest = hearing_log[-1]
        next_date_str = latest.get("next_date", "")
        if next_date_str:
            try:
                next_dt = parse_date(next_date_str)
                hours_until = (next_dt - get_current_time()).total_seconds() / 3600
                if 0 < hours_until <= 24:
                    alerts.append({
                        "type": "HEARING_24HR",
                        "message": f"Hearing in {int(hours_until)} hours — Case {case_id}",
                        "severity": "warning"
                    })
            except (ValueError, TypeError):
                pass

    # ACJA violation alert
    if case.get("adjournment_count", 0) >= 4:
        alerts.append({
            "type": "ACJA_VIOLATION",
            "message": f"Case {case_id} at {case.get('adjournment_count', 0)} adjournments — violates ACJA Sec 396",
            "severity": "critical"
        })

    # RED flag
    if case.get("risk_flag"):
        alerts.append({
            "type": "RED_FLAG",
            "message": f"Case {case_id} flagged HIGH delay risk ({(case.get('delay_risk_score', 0) * 100):.0f}%)",
            "severity": "critical"
        })

    # Missing file
    if case.get("file_missing_report") and not case["file_missing_report"].get("resolved"):
        alerts.append({
            "type": "FILE_MISSING",
            "message": f"Case {case_id} file reported missing — last seen: {case['file_missing_report'].get('last_known_location', 'Unknown')}",
            "severity": "critical"
        })

    return {"case_id": case_id, "alerts": alerts, "alert_count": len(alerts)}


@app.get("/api/cases/{case_id:path}", response_model=Dict[str, Any])
def get_case(case_id: str, auth: Dict[str, str] = Depends(get_current_user)):
    """Retrieves a single case document by ID."""
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
    return case


@app.get("/api/judge/alerts", response_model=Dict[str, Any])
def get_judge_alerts(auth: Dict[str, str] = Depends(get_current_user)):
    """
    Judge/CR: Get all alerts across the judge's assigned docket.
    Returns 24hr hearing warnings and ACJA violation alerts.
    """
    if auth["role"] not in ["Judge", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Judge alerts are restricted to Judges and Chief Registrar.")

    all_cases = db.list_cases()
    user_id = auth["user_id"]

    if auth["role"] == "Judge":
        docket = [c for c in all_cases if c.get("assigned_judge_id") == user_id]
    else:
        docket = all_cases

    alerts = []
    for case in docket:
        case_id = case["case_id"]

        # 24hr hearing check
        hearing_log = case.get("hearing_log", [])
        if hearing_log:
            latest = hearing_log[-1]
            next_date_str = latest.get("next_date", "")
            if next_date_str:
                try:
                    next_dt = parse_date(next_date_str)
                    hours_until = (next_dt - get_current_time()).total_seconds() / 3600
                    if 0 < hours_until <= 24:
                        alerts.append({
                            "case_id": case_id,
                            "type": "HEARING_24HR",
                            "message": f"Hearing in {int(hours_until)}hrs",
                            "severity": "warning"
                        })
                except (ValueError, TypeError):
                    pass

        # ACJA violation
        if case.get("adjournment_count", 0) >= 4:
            alerts.append({
                "case_id": case_id,
                "type": "ACJA_VIOLATION",
                "message": f"{case.get('adjournment_count')} adjournments — ACJA Sec 396",
                "severity": "critical"
            })

        # RED flag
        if case.get("risk_flag"):
            alerts.append({
                "case_id": case_id,
                "type": "RED_FLAG",
                "message": f"High delay risk ({(case.get('delay_risk_score', 0) * 100):.0f}%)",
                "severity": "critical"
            })

    return {
        "judge_id": user_id,
        "total_alerts": len(alerts),
        "alerts": alerts
    }

@app.get("/api/export/njc")
def export_njc_report(auth: Dict[str, str] = Depends(get_current_user)):
    """
    Module 4: 1-Click NJC Monthly Delay Compliance Exporter.
    Generates structured JSON report for the National Judicial Council (NJC) / NCMS.
    """
    if auth["role"] not in ["Chief Registrar", "DCR"]:
        raise HTTPException(status_code=403, detail="Permission Denied: NJC Export requires Chief Registrar or DCR authority.")
        
    cases = scoped_cases(auth)
    total_cases = len(cases)
    stalled_cases = [c for c in cases if c.get("risk_flag")]
    delays_count = len(stalled_cases)
    compliance_score = round(max(0, (1 - (delays_count / max(1, total_cases))) * 100), 1)
    
    return {
        "report_title": "National Judicial Council (NJC) Monthly Delay Compliance Report",
        "jurisdiction": "Federal High Court / High Court Division",
        "export_date": format_date(get_current_time()),
        "generated_by": auth["user_id"],
        "user_role": auth["role"],
        "summary": {
            "total_active_dockets": total_cases,
            "stalled_cases_flagged": delays_count,
            "speedy_trial_compliance_score": f"{compliance_score}%",
            "pending_dcr_overrides": sum(1 for c in cases if c.get("dcr_approval_required")),
            "enforcement_breaches": sum(1 for c in cases if c.get("enforcement_non_compliant"))
        },
        "audited_cases": cases
    }


@app.post("/api/cases/{case_id:path}/predict", response_model=Dict[str, Any])
def predict_case_risk(case_id: str, auth: Dict[str, str] = Depends(get_current_user)):
    """
    Module 3: Run delay-risk prediction on-demand for a case.
    Returns and saves updated delay_risk_score and risk_flag.
    """
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
        
    filing_dt = parse_date(case["filing_date"])
    case["days_since_filing"] = max(0, (get_current_time() - filing_dt).days)
    
    pred = run_model_inference(case)
    
    db.update_case(case_id, {
        "days_since_filing": case["days_since_filing"],
        "delay_risk_score": pred["delay_risk_score"],
        "risk_flag": pred["risk_flag"]
    })
    
    return {
        "case_id": case_id,
        "delay_risk_score": pred["delay_risk_score"],
        "risk_flag": pred["risk_flag"]
    }

@app.get("/api/predict/batch", response_model=List[Dict[str, Any]])
def batch_predict_all_cases(auth: Dict[str, str] = Depends(get_current_user)):
    """
    Module 3: Batch delay-risk prediction.
    Re-runs the ML model on all active (non-executed) cases and returns
    them sorted by risk score descending. Also persists updated scores.
    """
    all_cases = scoped_cases(auth)
    results = []
    for case in all_cases:
        if case.get("judgment_status") == "Executed":
            continue
        filing_dt = parse_date(case["filing_date"])
        case["days_since_filing"] = max(0, (get_current_time() - filing_dt).days)
        pred = run_model_inference(case)
        db.update_case(case["case_id"], {
            "days_since_filing": case["days_since_filing"],
            "delay_risk_score": pred["delay_risk_score"],
            "risk_flag": pred["risk_flag"]
        })
        results.append({
            "case_id": case["case_id"],
            "case_title": case.get("case_title", case["case_id"]),
            "case_type": case.get("case_type", "Unknown"),
            "court": case.get("court", "Unknown"),
            "adjournment_count": case.get("adjournment_count", 0),
            "days_since_filing": case["days_since_filing"],
            "delay_risk_score": pred["delay_risk_score"],
            "risk_flag": pred["risk_flag"],
            "judgment_status": case.get("judgment_status", "Pending"),
            "assigned_judge_id": case.get("assigned_judge_id", ""),
            "filing_date": case.get("filing_date", "")
        })
    results.sort(key=lambda x: x["delay_risk_score"], reverse=True)
    return results

@app.post("/api/cases/{case_id:path}/execution", response_model=Dict[str, Any])
def add_execution_action(case_id: str, req: ExecutionRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """
    Module 4: Execution Tracker.
    Appends sheriff action to execution log. Restricted to Sheriff and Chief Registrar.
    """
    if auth["role"] not in ["Sheriff", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Post-judgment execution actions are restricted to Sheriffs and the Chief Registrar.")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
        
    action_event = {
        "action": req.action,
        "date": format_date(get_current_time()),
        "sheriff_id": auth["user_id"]
    }
    
    updates = {
        "execution_log": [action_event]
    }
    
    # If this action completes the enforcement, update status to "Executed"
    if req.action in ["Garnishee Order Executed", "Writ of Fi Fa Completed", "Enforcement Completed"]:
        updates["judgment_status"] = "Executed"
        updates["enforcement_non_compliant"] = False
        
    db.update_case(case_id, updates)
    
    # Re-run compliance updates
    run_compliance_checks_sync()
    
    return db.get_case(case_id)

@app.post("/api/cron", response_model=Dict[str, Any])
def run_cron_compliance_sweep(auth: Dict[str, str] = Depends(get_current_user)):
    """
    Simulated daily background sweep endpoint.
    Recalculates custody flags, days_since_filing, and enforcement alerts.
    """
    if auth["role"] != "Chief Registrar":
        raise HTTPException(status_code=403, detail="Compliance sweep requires Chief Registrar authority")
    run_compliance_checks_sync()
    cases = db.list_cases()
    
    stats = {
        "total_cases": len(cases),
        "custody_alerts": sum(1 for c in cases if c.get("custody_alert")),
        "non_compliant_enforcements": sum(1 for c in cases if c.get("enforcement_non_compliant")),
        "high_risk_delay_cases": sum(1 for c in cases if c.get("risk_flag"))
    }
    
    return {
        "status": "success",
        "timestamp": format_date(get_current_time()),
        "stats": stats
    }

# ----------------- SIMULATED WHATSAPP INGESTION -----------------

@app.post("/api/whatsapp/webhook-simulator")
def whatsapp_webhook_simulator(payload: Dict[str, Any] = Body(...), x_simulator_secret: Optional[str] = Header(None)):
    """
    Simulates receiving the WhatsApp webhook request.
    Stores payloads in-memory so the dashboard can pull and display the live broadcast logs.
    """
    import secrets
    secret = os.getenv("SIMULATOR_SECRET", "")
    if os.getenv("DEMO_MODE", "false").lower() != "true":
        raise HTTPException(status_code=404, detail="Simulator disabled")
    if not secret or not secrets.compare_digest(x_simulator_secret or "", secret):
        raise HTTPException(status_code=401, detail="Invalid simulator credentials")
    event = {
        "received_at": format_date(get_current_time()),
        "payload": payload
    }
    whatsapp_logs.insert(0, event)
    # Keep only the last 30 messages
    if len(whatsapp_logs) > 30:
        whatsapp_logs.pop()
    
    logger.info("Simulated WhatsApp event accepted")
    return {"status": "accepted", "message_id": f"msg_{int(datetime.now().timestamp())}"}

@app.get("/api/whatsapp/logs")
def get_whatsapp_broadcast_logs(auth: Dict[str, str] = Depends(get_current_user)):
    """Returns the history of sent simulated WhatsApp notifications."""
    if auth["role"] != "Chief Registrar":
        raise HTTPException(status_code=403, detail="Broadcast logs require Chief Registrar authority")
    return whatsapp_logs

# ----------------- SERVE STATIC FRONTEND FILES -----------------
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

@app.get("/")
def serve_dashboard():
    """Serves the dashboard home index.html directly on root URL."""
    index_path = _FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    raise HTTPException(status_code=404, detail="Frontend index.html file not found")

# Mount frontend assets on a sub-path so it doesn't swallow API routes
app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR)), name="frontend")


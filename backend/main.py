import os
import joblib
import logging
import re
import secrets
import hashlib
import json
import sqlite3
import uuid
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Annotated, Literal
from fastapi import FastAPI, HTTPException, BackgroundTasks, Body, Header, Depends, Response, Cookie, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator

load_dotenv()

from backend.database import get_db_client, parse_date, format_date, verify_password, get_password_hash
from backend.whatsapp import (
    create_manual_test_message,
    deliver_whatsapp_message,
    get_public_status as get_whatsapp_public_status,
    hash_phone as hash_whatsapp_phone,
    mask_phone as mask_whatsapp_phone,
    normalize_whatsapp_phone,
    send_adjournment_broadcast,
    verify_webhook_signature,
    webhook_verification_token,
)
from backend.auth import (
    REFRESH_TOKEN_EXPIRE_DAYS, create_access_token,
    create_refresh_token, verify_token, get_current_user,
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("courtlog.main")

# Expose interactive API docs only in explicitly enabled demo mode.
DEMO_MODE_ENABLED = os.getenv("DEMO_MODE", "false").strip().lower() == "true"

# Initialize FastAPI
app = FastAPI(
    title="COURTLOG 2.0 API",
    description="Court File Tracking & Registry Workflow Prototype API",
    docs_url="/docs" if DEMO_MODE_ENABLED else None,
    redoc_url="/redoc" if DEMO_MODE_ENABLED else None,
    openapi_url="/openapi.json" if DEMO_MODE_ENABLED else None,
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=(), microphone=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    return response


# Session cookies are host-only, HttpOnly and SameSite-restricted.
REFRESH_COOKIE_NAME = "courtlog_refresh"
REFRESH_COOKIE_PATH = "/api"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").strip().lower() in {"1", "true", "yes", "on"}


def _positive_env_int(name: str, default: int) -> int:
    value = os.getenv(name, str(default))
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if parsed < 1:
        raise RuntimeError(f"{name} must be a positive integer")
    return parsed


LOGIN_RATE_LIMIT_WINDOW_SECONDS = _positive_env_int("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 900)
LOGIN_RATE_LIMIT_PER_USERNAME_IP = _positive_env_int("LOGIN_RATE_LIMIT_PER_USERNAME_IP", 5)
LOGIN_RATE_LIMIT_PER_IP = _positive_env_int("LOGIN_RATE_LIMIT_PER_IP", 25)


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME, value=token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True, secure=COOKIE_SECURE, samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH,
        httponly=True, secure=COOKIE_SECURE, samesite="strict",
    )


def _safe_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in user.items() if key != "password"}


def _audit_session_reference(session_id: str) -> str:
    """Avoid copying bearer-adjacent session identifiers into audit records."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def _record_audit_event(
    actor_user_id: Optional[str], action: str, entity_type: str,
    entity_id: str, reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        return db.append_audit_event(
            actor_user_id=actor_user_id, action=action,
            entity_type=entity_type, entity_id=str(entity_id),
            reason=reason, metadata=metadata,
        )
    except Exception as exc:
        logger.exception("Audit event append failed for %s on %s", action, entity_type)
        raise HTTPException(
            status_code=503,
            detail="The operation may have been applied, but its audit record could not be saved. Verify before retrying.",
        ) from exc


# Global variables
db = get_db_client()
# Keep unknown-user login checks close to the cost of a real bcrypt verification.
DUMMY_PASSWORD_HASH = get_password_hash(secrets.token_urlsafe(32))

def case_file_is_missing(case: Dict[str, Any]) -> bool:
    """Use the open report as the source of truth, with a flag-only fallback for legacy data."""
    report = case.get("file_missing_report")
    if isinstance(report, dict) and report:
        return not bool(report.get("resolved"))
    return case.get("file_missing") is True


def can_access_case(case: Dict[str, Any], auth: Dict[str, str]) -> bool:
    """Fail closed; use the current stored profile, never client-supplied scope."""
    user = db.get_user(auth["user_id"])
    if not user or user.get("disabled"):
        return False
    role = user.get("role")
    if role == "Chief Registrar":
        return True
    if role == "Judge":
        return (bool(user.get("court"))
                and case.get("assigned_judge_id") == user["user_id"]
                and case.get("court") == user["court"])
    if role == "DCR":
        return bool(user.get("division")) and case.get("assigned_division") == user["division"]
    if role == "Clerk":
        return bool(user.get("court")) and case.get("court") == user["court"]
    if role == "Sheriff":
        if not user.get("court") or case.get("court") != user["court"]:
            return False
        # Once custody has an explicit assignee, that assignment is authoritative:
        # old scan history or a prior missing-file report must not preserve access
        # after a handover. Legacy cases without an assignment retain their existing
        # last-scan / missing-report scope until the registry assigns a custodian.
        assigned_sheriff_id = case.get("assigned_sheriff_id")
        if assigned_sheriff_id:
            return assigned_sheriff_id == user["user_id"]
        scans = case.get("scan_events", [])
        missing = case.get("file_missing_report") or {}
        return (bool(scans and scans[-1].get("staff_id") == user["user_id"])
                or (not missing.get("resolved") and missing.get("reported_by") == user["user_id"]))
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

# Nigerian case references can contain suit-number separators, but never path
# traversal segments or characters that could become markup in the UI.
def _validate_case_identifier(value: str) -> str:
    if ".." in value or "//" in value or value.endswith("/"):
        raise ValueError("Invalid case identifier")
    return value


CaseIdentifier = Annotated[
    str,
    Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_()./-]*$"),
    AfterValidator(_validate_case_identifier),
]

QR_PAYLOAD_PREFIX = "courtlog:v1:"
QR_PAYLOAD_PATTERN = re.compile(r"^courtlog:v1:[A-Za-z0-9_-]{43}$")


def _normalize_nigerian_phone(value: str) -> str:
    normalized = re.sub(r"[\s().-]", "", value)
    if normalized.startswith("00"):
        normalized = "+" + normalized[2:]
    elif normalized.startswith("0"):
        normalized = "+234" + normalized[1:]
    elif normalized.startswith("234"):
        normalized = "+" + normalized

    if not re.fullmatch(r"\+234[1-9]\d{6,9}", normalized):
        raise ValueError("Enter a valid Nigerian phone number, such as +2348031234567")
    return normalized


# Helper Pydantic Models for Input Validation
class ScanRequest(BaseModel):
    case_id: CaseIdentifier
    location: str = Field(min_length=1, max_length=160, pattern=r"\S")

    @field_validator("location")
    @classmethod
    def trim_scan_location(cls, value):
        return value.strip()


class QRScanRequest(BaseModel):
    qr_payload: str = Field(min_length=1, max_length=128, pattern=r"\S")
    location: str = Field(min_length=1, max_length=160, pattern=r"\S")

    @field_validator("qr_payload", "location")
    @classmethod
    def trim_qr_scan_fields(cls, value):
        return value.strip()


class SheriffAssignmentRequest(BaseModel):
    sheriff_id: str = Field(min_length=1, max_length=64, pattern=r"\S")
    reason: str = Field(min_length=1, max_length=500, pattern=r"\S")

    @field_validator("sheriff_id", "reason")
    @classmethod
    def trim_assignment_fields(cls, value):
        return value.strip()


class SheriffHandoverRequest(BaseModel):
    to_sheriff_id: str = Field(min_length=1, max_length=64, pattern=r"\S")
    location: str = Field(min_length=1, max_length=160, pattern=r"\S")
    reason: str = Field(min_length=1, max_length=500, pattern=r"\S")

    @field_validator("to_sheriff_id", "location", "reason")
    @classmethod
    def trim_handover_fields(cls, value):
        return value.strip()


class HearingRequest(BaseModel):
    # These are the two current UI outcomes, not a statutory hearing policy.
    # Legal reason codes and workflow rules remain subject to Law Lead review.
    outcome: Literal["Heard", "Adjourned"]
    reason_code: Optional[str] = Field(default="None", max_length=100)
    next_date: Optional[datetime] = None

    @field_validator("next_date", mode="before")
    @classmethod
    def parse_iso_date(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("next_date must be a valid ISO 8601 date or datetime") from exc
        else:
            raise ValueError("next_date must be a valid ISO 8601 date or datetime")
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    @field_validator("outcome", mode="before")
    @classmethod
    def trim_hearing_outcome(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("reason_code")
    @classmethod
    def trim_hearing_reason(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("reason_code cannot be blank")
        return value

    @model_validator(mode="after")
    def adjournment_requires_date(self):
        if self.outcome == "Adjourned" and self.next_date is None:
            raise ValueError("next_date is required when outcome is Adjourned")
        return self


class ExecutionRequest(BaseModel):
    action: str = Field(min_length=3, max_length=300, pattern=r"\S")
    sheriff_id: str = Field(min_length=1, max_length=64, pattern=r"\S")

    @field_validator("action", "sheriff_id")
    @classmethod
    def trim_execution_fields(cls, value):
        return value.strip()


class CaseCreateRequest(BaseModel):
    case_id: CaseIdentifier
    case_type: str = Field(min_length=1, max_length=80, pattern=r"\S")
    court: str = Field(min_length=1, max_length=120, pattern=r"\S")
    counsel_phone: str = Field(min_length=8, max_length=32)
    litigant_phone: str = Field(min_length=8, max_length=32)

    @field_validator("case_type", "court")
    @classmethod
    def trim_case_fields(cls, value):
        return value.strip()

    @field_validator("counsel_phone", "litigant_phone")
    @classmethod
    def normalize_nigerian_phones(cls, value):
        return _normalize_nigerian_phone(value)


class WhatsAppPreferenceRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=32)
    status: Literal["opted_in", "opted_out"]
    consent_source: str = Field(min_length=2, max_length=120, pattern=r"\S")
    evidence_reference: Optional[str] = Field(default=None, max_length=200)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value):
        return normalize_whatsapp_phone(value)

    @field_validator("consent_source", "evidence_reference")
    @classmethod
    def trim_preference_fields(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be blank")
        return value

    @model_validator(mode="after")
    def opt_in_requires_evidence(self):
        if self.status == "opted_in" and not self.evidence_reference:
            raise ValueError("An evidence_reference is required when recording an opt-in")
        return self


class WhatsAppTestSendRequest(BaseModel):
    case_id: CaseIdentifier
    recipient_role: Literal["counsel", "litigant"]


class DCROverrideRequest(BaseModel):
    exceptional_reason: str = Field(min_length=1, max_length=2000, pattern=r"\S")

    @field_validator("exceptional_reason")
    @classmethod
    def trim_exceptional_reason(cls, value):
        return value.strip()


class DCRReviewAcknowledgementRequest(BaseModel):
    note: str = Field(min_length=1, max_length=1000, pattern=r"\S")

    @field_validator("note")
    @classmethod
    def trim_acknowledgement_note(cls, value):
        return value.strip()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=72)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Username cannot be blank")
        return value

    @field_validator("password")
    @classmethod
    def validate_bcrypt_password_size(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be no more than 72 UTF-8 bytes")
        return value


class ReassignRequest(BaseModel):
    new_division: Optional[str] = Field(default=None, max_length=120)
    new_court: Optional[str] = Field(default=None, max_length=120)
    reason: str = Field(min_length=1, max_length=1000, pattern=r"\S")

    @field_validator("new_division", "new_court", "reason")
    @classmethod
    def trim_reassignment_fields(cls, value):
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_reassignment_target(self):
        if not self.new_division and not self.new_court:
            raise ValueError("Provide a new division or court")
        return self


class AssignJudgeRequest(BaseModel):
    judge_id: str = Field(min_length=1, max_length=64, pattern=r"\S")
    reason: Optional[str] = Field(default="Balloting assignment", max_length=500)

    @field_validator("judge_id")
    @classmethod
    def trim_judge_id(cls, value):
        return value.strip()

    @field_validator("reason")
    @classmethod
    def trim_assignment_reason(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("reason cannot be blank")
        return value


class FileMissingRequest(BaseModel):
    last_known_location: str = Field(min_length=1, max_length=160, pattern=r"\S")
    notes: Optional[str] = Field(default="", max_length=1000)

    @field_validator("last_known_location", "notes")
    @classmethod
    def trim_missing_file_fields(cls, value):
        return value.strip() if value is not None else None


class FileFoundRequest(BaseModel):
    found_location: str = Field(min_length=1, max_length=160, pattern=r"\S")
    reason: str = Field(min_length=1, max_length=500, pattern=r"\S")

    @field_validator("found_location", "reason")
    @classmethod
    def trim_found_file_fields(cls, value):
        return value.strip()


class DocumentUploadRequest(BaseModel):
    document_type: str = Field(min_length=1, max_length=40, pattern=r"\S")
    title: str = Field(min_length=1, max_length=200, pattern=r"\S")
    filename: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9 _().-]*$")
    notes: Optional[str] = Field(default="", max_length=1000)

    @field_validator("document_type", "title", "filename", "notes")
    @classmethod
    def trim_document_fields(cls, value):
        return value.strip() if value is not None else None

    @field_validator("filename")
    @classmethod
    def reject_path_components(cls, value):
        if value in {".", ".."} or ".." in value:
            raise ValueError("Filename must be a plain filename, not a path")
        return value

class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    initial_password: str = Field(min_length=12, max_length=72)
    name: str = Field(min_length=2, max_length=120)
    role: Literal["Sheriff", "Clerk", "DCR", "Chief Registrar", "Judge"]
    badge: str = Field(min_length=2, max_length=120)
    court: str = Field(min_length=2, max_length=120)
    division: str = Field(min_length=2, max_length=120)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower()

    @field_validator("initial_password")
    @classmethod
    def validate_bcrypt_password_size(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be no more than 72 UTF-8 bytes")
        return value

    @field_validator("name", "badge", "court", "division")
    @classmethod
    def trim_user_fields(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be blank")
        return value


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=12, max_length=72)

    @field_validator("current_password", "new_password")
    @classmethod
    def validate_password_size(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be no more than 72 UTF-8 bytes")
        return value


class PasswordResetRequest(BaseModel):
    temporary_password: str = Field(min_length=12, max_length=72)

    @field_validator("temporary_password")
    @classmethod
    def validate_temporary_password_size(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be no more than 72 UTF-8 bytes")
        return value
# get_current_user is imported from backend.auth and used as a FastAPI Depends()
# It validates Bearer tokens and returns {"user_id": ..., "role": ...}

@app.get("/api/config")
def client_config():
    """Expose only non-sensitive switches needed to render demo-only controls safely."""
    return {"demo_mode": DEMO_MODE_ENABLED}


@app.post("/api/login")
def login(req: LoginRequest, response: Response, request: Request):
    """Authenticate, rate-limit failures, and issue a server-revocable session."""
    response.headers["Cache-Control"] = "no-store"
    username_lower = req.username.strip().casefold()
    client_address = request.client.host if request.client else "unknown"

    # Store pseudonymous rate-limit keys, not usernames or raw client addresses.
    principal_key = hashlib.sha256(f"{username_lower}\0{client_address}".encode("utf-8")).hexdigest()
    client_key = hashlib.sha256(client_address.encode("utf-8")).hexdigest()
    attempt_id, retry_after = db.reserve_login_attempt(
        principal_key=principal_key,
        client_key=client_key,
        now=int(datetime.now(timezone.utc).timestamp()),
        window_seconds=LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        principal_limit=LOGIN_RATE_LIMIT_PER_USERNAME_IP,
        client_limit=LOGIN_RATE_LIMIT_PER_IP,
    )
    if attempt_id is None:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
        )

    users = db.list_users()
    user = next(
        (candidate for candidate in users
         if str(candidate.get("username", "")).strip().casefold() == username_lower),
        None,
    )
    stored_hash = str(user.get("password", "")) if user else ""
    password_hash = stored_hash if stored_hash.startswith(("$2a$", "$2b$", "$2y$")) else DUMMY_PASSWORD_HASH
    try:
        password_matches = verify_password(req.password, password_hash)
    except (ValueError, TypeError):
        password_matches = False

    if user and stored_hash and stored_hash == password_hash and password_matches and not user.get("disabled"):
        user_id = user["user_id"]
        role = user.get("role", "Clerk")
        session_id = secrets.token_urlsafe(32)
        refresh_jti = secrets.token_urlsafe(32)
        expires_at = int((datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp())
        db.create_auth_session(session_id, user_id, refresh_jti, expires_at)

        token_data = {
            "sub": user_id, "role": role,
            "username": user.get("username", ""), "sid": session_id,
        }
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token({**token_data, "jti": refresh_jti})
        _set_refresh_cookie(response, refresh_token)
        db.complete_login_attempt(attempt_id)
        _record_audit_event(user_id, "auth.login.success", "session", _audit_session_reference(session_id))

        logger.info("User authenticated successfully: %s", user_id)
        return {
            "status": "success",
            "message": "Authentication successful",
            "access_token": access_token,
            "token_type": "bearer",
            "user": _safe_user(user),
        }

    raise HTTPException(
        status_code=401,
        detail="Invalid username or password.",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/refresh")
def refresh_token_endpoint(
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias=REFRESH_COOKIE_NAME),
):
    """Validate the HttpOnly refresh cookie and issue a new short-lived access token."""
    response.headers["Cache-Control"] = "no-store"
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh session is missing")

    payload = verify_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh session")

    user_id = payload.get("sub")
    session_id = payload.get("sid")
    old_jti = payload.get("jti")
    user = db.get_user(user_id or "")
    if not user or user.get("disabled"):
        if user_id:
            db.revoke_user_sessions(user_id)
        raise HTTPException(status_code=401, detail="Account is no longer active")
    if not session_id or not old_jti:
        raise HTTPException(status_code=401, detail="Refresh session is invalid")

    if not db.is_refresh_session_active(session_id, user_id, old_jti):
        raise HTTPException(status_code=401, detail="Refresh session is no longer active")

    token_data = {
        "sub": user_id, "role": user["role"],
        "username": user.get("username", ""), "sid": session_id,
    }
    access_token = create_access_token(token_data)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": _safe_user(user),
    }


@app.post("/api/logout")
def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias=REFRESH_COOKIE_NAME),
):
    """Revoke the browser session server-side and clear its refresh cookie."""
    response.headers["Cache-Control"] = "no-store"
    payload = None
    if refresh_token:
        try:
            payload = verify_token(refresh_token)
        except HTTPException:
            # Logout should still clear an expired or malformed cookie.
            payload = None
    if payload and payload.get("type") == "refresh" and payload.get("sid") and payload.get("sub"):
        session_id = payload["sid"]
        user_id = payload["sub"]
        if db.revoke_auth_session(session_id, user_id):
            _record_audit_event(user_id, "auth.logout", "session", _audit_session_reference(session_id))
    _clear_refresh_cookie(response)
    return {"status": "success", "message": "Session ended"}


# ----------------- COMPLIANCE SWEEP LOGIC -----------------
def run_compliance_checks_sync():
    """
    Synchronously updates all dynamic metrics for cases:
    1. Days since filing based on the current UTC clock.
    2. Idle custody alert flag (True if no scan events in the last 7 consecutive days).
    3. Preserve the separate missing-file flag until an authorised found action.
    4. Configured 90-day execution-review prompt stored in a legacy case field.
       It is not a legal compliance determination; the policy basis remains under review.
    """
    cases = db.list_cases()
    logger.info(f"Running prototype workflow checks on {len(cases)} cases...")
    
    for case in cases:
        case_id = case["case_id"]
        updates = {}
        
        # 1. Update days since filing
        filing_dt = parse_date(case["filing_date"])
        days_elapsed = (get_current_time() - filing_dt).days
        updates["days_since_filing"] = max(0, days_elapsed)
        
        # 2. Idle Custody Alert Flag (Module 1); this never clears file_missing.
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
            
        # 3. Configured 90-day execution-review prompt (Module 4).
        # The legacy case field below is retained for data compatibility; it is
        # not a legal finding, and its policy basis remains under review.
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
                
                # Record a prototype review prompt if execution occurred after 90 days.
                updates["enforcement_non_compliant"] = days_to_enforce > 90
            else:
                # No execution action has been recorded; check the configured
                # application clock without treating it as a statutory finding.
                days_since_delivery = (get_current_time() - judgment_delivery_dt).days
                updates["enforcement_non_compliant"] = days_since_delivery > 90
        else:
            # No 90-day execution-review prompt applies before judgment delivery.
            updates["enforcement_non_compliant"] = False
            
        # 4. ML delay-risk notification metadata is independent of custody,
        # adjournment-review, missing-file, and enforcement state.
        now = get_current_time()
        if case.get("risk_flag"):
            if not case.get("red_flag_notified_at"):
                updates["red_flag_notified_at"] = format_date(now)
        else:
            updates["red_flag_notified_at"] = None
            # Keep the ambiguous legacy auto_escalated value untouched. DCR
            # escalation now uses its own durable fields and clock.

        # 5. DCR review escalation is timed only from the DCR request timestamp,
        # never from the independent ML-risk notification clock. A pending legacy
        # record without a request time starts its new clock when first observed.
        if case.get("dcr_approval_required"):
            requested_at = case.get("dcr_approval_requested_at")
            if not requested_at:
                requested_at = format_date(now)
                updates["dcr_approval_requested_at"] = requested_at
                updates["dcr_approval_history"] = [{
                    "action": "request_timestamp_initialized",
                    "occurred_at": requested_at,
                    "actor_user_id": None,
                    "note": "Legacy pending review had no request timestamp; clock initialized on first sweep.",
                }]

            requested_dt = parse_date(requested_at)
            hours_pending = (now - requested_dt).total_seconds() / 3600
            if hours_pending > 24 and not case.get("dcr_auto_escalated"):
                escalated_at = format_date(now)
                updates["dcr_auto_escalated"] = True
                updates["dcr_escalated_at"] = escalated_at
                updates["dcr_approval_history"] = updates.get("dcr_approval_history", []) + [{
                    "action": "escalated",
                    "occurred_at": escalated_at,
                    "actor_user_id": None,
                    "note": "In-app escalation recorded after more than 24 hours; no external notification was sent.",
                }]
                logger.warning(
                    "DCR review escalation recorded for case %s after >24h; "
                    "this records in-app state only and sends no external notification.",
                    case_id,
                )

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

@app.get("/api/audit/events", response_model=List[Dict[str, Any]])
def get_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    auth: Dict[str, str] = Depends(get_current_user),
):
    """Chief Registrar-only access to the latest append-only operational events."""
    if auth["role"] != "Chief Registrar":
        raise HTTPException(status_code=403, detail="Audit review requires Chief Registrar authority")
    return db.list_audit_events(limit)


@app.post("/api/users", status_code=201)
def create_user(req: UserCreateRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Create a named account with a temporary password that must be changed at first login."""
    if auth["role"] != "Chief Registrar":
        raise HTTPException(status_code=403, detail="User management requires Chief Registrar authority")
    if req.role == "Chief Registrar" and (req.court.casefold() != "all courts" or req.division.casefold() != "all divisions"):
        raise HTTPException(status_code=422, detail="Chief Registrars must be assigned to All Courts and All Divisions")
    if req.role != "Chief Registrar" and req.court.casefold() == "all courts":
        raise HTTPException(status_code=422, detail="Only Chief Registrars may be assigned to All Courts")
    if req.role != "Chief Registrar" and req.division.casefold() == "all divisions":
        raise HTTPException(status_code=422, detail="Only Chief Registrars may be assigned to All Divisions")
    if any(str(user.get("username", "")).strip().casefold() == req.username.casefold() for user in db.list_users()):
        raise HTTPException(status_code=409, detail="Username is already in use")

    user_id = f"usr_{uuid.uuid4().hex}"
    new_user = {
        "user_id": user_id,
        "username": req.username,
        "password": get_password_hash(req.initial_password),
        "name": req.name,
        "role": req.role,
        "badge": req.badge,
        "court": req.court,
        "division": req.division,
        "must_change_password": True,
        "disabled": False,
    }
    try:
        db.save_user(user_id, new_user)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Username is already in use")
    _record_audit_event(
        auth["user_id"], "user.create", "user", user_id,
        metadata={"role": req.role},
    )
    return _safe_user(new_user)


@app.post("/api/users/me/password")
def change_my_password(req: PasswordChangeRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Change the authenticated user's password and revoke every active session."""
    user = db.get_user(auth["user_id"])
    if not user or user.get("disabled"):
        raise HTTPException(status_code=401, detail="Account is no longer active")
    if not verify_password(req.current_password, str(user.get("password", ""))):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if verify_password(req.new_password, str(user.get("password", ""))):
        raise HTTPException(status_code=400, detail="New password must differ from the current password")

    user["password"] = get_password_hash(req.new_password)
    user["must_change_password"] = False
    db.save_user(user["user_id"], user)
    db.revoke_user_sessions(user["user_id"])
    _record_audit_event(auth["user_id"], "user.password.change", "user", user["user_id"])
    return {"status": "success", "relogin_required": True}


@app.post("/api/users/{user_id}/reset-password")
def reset_user_password(
    user_id: str,
    req: PasswordResetRequest,
    auth: Dict[str, str] = Depends(get_current_user),
):
    """Chief Registrar issues a temporary credential; all target sessions are revoked."""
    if auth["role"] != "Chief Registrar":
        raise HTTPException(status_code=403, detail="Password reset requires Chief Registrar authority")
    if user_id == auth["user_id"]:
        raise HTTPException(status_code=409, detail="Use your own password-change workflow for this account")
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("disabled"):
        raise HTTPException(status_code=409, detail="Disabled accounts cannot be reset")

    user["password"] = get_password_hash(req.temporary_password)
    user["must_change_password"] = True
    db.save_user(user_id, user)
    db.revoke_user_sessions(user_id)
    _record_audit_event(
        auth["user_id"], "user.password.reset", "user", user_id,
        metadata={"must_change_password": True},
    )
    return {"status": "success", "must_change_password": True}


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
    if not db.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    _record_audit_event(
        auth["user_id"], "user.delete", "user", user_id,
        metadata={"role": target.get("role")},
    )
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
        # Judicial assignment is an explicit Chief Registrar action; do not bind
        # every new case to a hard-coded demo Judge or grant cross-court visibility.
        "assigned_judge_id": None,
        "assigned_sheriff_id": None,
        "custody_history": [],
        "filing_date": format_date(get_current_time()),
        "adjournment_count": 0,
        "days_since_filing": 0,
        "judgment_status": "Pending",
        "delay_risk_score": 0.1,
        "risk_flag": False,
        "dcr_approval_required": False,
        "dcr_approval_requested_at": None,
        "dcr_approval_history": [],
        "dcr_acknowledged_at": None,
        "dcr_acknowledged_by": None,
        "dcr_acknowledgement_note": None,
        "dcr_auto_escalated": False,
        "dcr_escalated_at": None,
        "dcr_approval_resolved_at": None,
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
        "file_missing": False,
        "file_missing_report": None,
        "file_missing_history": [],
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
    _record_audit_event(
        auth["user_id"], "case.create", "case", req.case_id,
        metadata={"case_type": req.case_type, "court": req.court},
    )
    return new_case

def _record_case_scan(
    case_id: str,
    location: str,
    auth: Dict[str, str],
    source: str,
    require_current_assignment: bool = False,
) -> Dict[str, Any]:
    """Append a custody scan with identity and time derived on the server."""
    scan_event = {
        "location": location,
        "timestamp": format_date(get_current_time()),
        "staff_id": auth["user_id"],
    }
    if require_current_assignment:
        if not db.append_scan_if_assigned(case_id, auth["user_id"], scan_event):
            raise HTTPException(status_code=403, detail="The current Sheriff assignment changed; refresh and verify custody before retrying")
    else:
        db.update_case(case_id, {"scan_events": [scan_event], "custody_alert": False})

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    filing_dt = parse_date(case["filing_date"])
    case["days_since_filing"] = max(0, (get_current_time() - filing_dt).days)
    prediction = run_model_inference(case)
    db.update_case(case_id, {
        "days_since_filing": case["days_since_filing"],
        "delay_risk_score": prediction["delay_risk_score"],
        "risk_flag": prediction["risk_flag"],
    })
    _record_audit_event(
        auth["user_id"], "case.scan", "case", case_id,
        metadata={"location": location, "source": source},
    )
    return db.get_case(case_id)


@app.post("/api/scan", response_model=Dict[str, Any])
def record_scan_event(req: ScanRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Manual case-selection fallback for Sheriff and registry staff."""
    if auth["role"] not in ["Sheriff", "Clerk", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: custody scanning is restricted to Sheriff and Registry Staff.")

    case = db.get_case(req.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
    return _record_case_scan(req.case_id, req.location, auth, "manual")


@app.post("/api/scan/qr", response_model=Dict[str, Any])
def record_qr_scan_event(req: QRScanRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Resolve an opaque QR token, then enforce the current Sheriff assignment."""
    if auth.get("role") != "Sheriff":
        raise HTTPException(status_code=403, detail="QR check-in is restricted to the assigned Sheriff")
    if not QR_PAYLOAD_PATTERN.fullmatch(req.qr_payload):
        raise HTTPException(status_code=422, detail="QR label format is not recognized")

    token_hash = hashlib.sha256(req.qr_payload.encode("utf-8")).hexdigest()
    case_id = db.resolve_case_qr_token(token_hash)
    if not case_id:
        raise HTTPException(status_code=404, detail="QR label is not recognized")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="QR label is not recognized")
    authorize_case(case, auth)
    if case.get("assigned_sheriff_id") != auth["user_id"]:
        raise HTTPException(status_code=403, detail="Only the currently assigned Sheriff may check in this QR label")
    return _record_case_scan(case_id, req.location, auth, "qr", require_current_assignment=True)


@app.post("/api/cases/{case_id:path}/qr-label", status_code=201)
def issue_case_qr_label(
    case_id: CaseIdentifier,
    response: Response,
    auth: Dict[str, str] = Depends(get_current_user),
):
    """Issue a random, opaque label token; it is never a substitute for authorization."""
    if auth.get("role") not in ["Clerk", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Only registry staff may issue QR labels")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)

    qr_payload = QR_PAYLOAD_PREFIX + secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(qr_payload.encode("utf-8")).hexdigest()
    try:
        db.create_case_qr_token(
            token_hash=token_hash,
            case_id=case_id,
            issued_by=auth["user_id"],
            created_at=format_date(get_current_time()),
        )
    except Exception as exc:
        logger.exception("QR label issuance failed for case %s", case_id)
        raise HTTPException(status_code=503, detail="QR label could not be issued; please retry") from exc

    _record_audit_event(
        auth["user_id"], "case.qr_label.issue", "case", case_id,
        metadata={"format": "courtlog:v1"},
    )
    response.headers["Cache-Control"] = "no-store"
    return {"qr_payload": qr_payload, "format": "courtlog:v1"}


@app.post("/api/cases/{case_id:path}/hearings", response_model=Dict[str, Any])
def log_hearing_outcome(case_id: CaseIdentifier, req: HearingRequest, background_tasks: BackgroundTasks, auth: Dict[str, str] = Depends(get_current_user)):
    """Record hearing outcomes and apply the unchanged prototype review trigger.

    The configured case-level threshold is not a statutory determination or a
    per-party count; confirm any policy change with the Law Lead before rollout.
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
    
    # ----------------- CONFIGURED ADJOURNMENT REVIEW GATE -----------------
    # Keep this existing application threshold unchanged pending Law Lead review.
    # It is not a determination of statutory compliance or a per-party count.
    if req.outcome == "Adjourned":
        if current_adj_count >= 4 and not case.get("dcr_override_reason"):
            now_value = format_date(get_current_time())
            dcr_updates = {
                "dcr_approval_required": True,
                "adjournment_blocked": True,
            }
            if not case.get("dcr_approval_required"):
                dcr_updates.update({
                    "dcr_approval_requested_at": now_value,
                    "dcr_acknowledged_at": None,
                    "dcr_acknowledged_by": None,
                    "dcr_acknowledgement_note": None,
                    "dcr_auto_escalated": False,
                    "dcr_escalated_at": None,
                    "dcr_approval_resolved_at": None,
                })
                dcr_updates["dcr_approval_history"] = [{
                    "action": "requested",
                    "occurred_at": now_value,
                    "actor_user_id": auth["user_id"],
                    "reason_code": req.reason_code,
                    "existing_adjournment_count": current_adj_count,
                }]
            elif not case.get("dcr_approval_requested_at"):
                dcr_updates["dcr_approval_requested_at"] = now_value
                dcr_updates["dcr_approval_history"] = [{
                    "action": "request_timestamp_initialized",
                    "occurred_at": now_value,
                    "actor_user_id": auth["user_id"],
                    "reason_code": req.reason_code,
                    "note": "Pending review did not have a request timestamp; initialized on a blocked attempt.",
                }]

            db.update_case(case_id, dcr_updates)
            _record_audit_event(
                auth["user_id"], "case.hearing.blocked", "case", case_id,
                reason=req.reason_code,
                metadata={"outcome": req.outcome, "existing_adjournment_count": current_adj_count},
            )
            raise HTTPException(
                status_code=400,
                detail="Adjournment not recorded: the current application review threshold is reached and DCR/Chief Registrar review is pending.",
            )
            
    if req.next_date is None:
        next_date_value = ""
    elif req.next_date.time() == datetime.min.time() and req.next_date.microsecond == 0:
        # Keep the existing date-only frontend format for <input type="date">.
        next_date_value = req.next_date.date().isoformat()
    else:
        next_date_value = format_date(req.next_date)

    hearing_event = {
        "event_id": uuid.uuid4().hex,
        "date": format_date(get_current_time()),
        "outcome": req.outcome,
        "reason_code": req.reason_code if req.outcome == "Adjourned" else "None",
        "next_date": next_date_value
    }
    
    updates = {
        "hearing_log": [hearing_event]
    }
    
    if req.outcome == "Adjourned":
        updates["adjournment_count"] = current_adj_count + 1
        
        background_tasks.add_task(
            send_adjournment_broadcast,
            case_id=case_id,
            next_date=next_date_value,
            reason_code=req.reason_code,
            event_id=hearing_event["event_id"],
            database=db,
            actor_user_id=auth["user_id"],
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
    _record_audit_event(
        auth["user_id"], "case.hearing.record", "case", case_id,
        reason=req.reason_code if req.reason_code != "None" else None,
        metadata={"outcome": req.outcome, "next_date": next_date_value},
    )
    return db.get_case(case_id)

@app.post("/api/cases/{case_id:path}/dcr-override", response_model=Dict[str, Any])
def override_dcr_adjournment(case_id: CaseIdentifier, req: DCROverrideRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Record a reasoned DCR/Chief Registrar decision on a pending review."""
    if auth["role"] not in ["DCR", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: DCR or Chief Registrar role required.")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
    if not case.get("dcr_approval_required"):
        raise HTTPException(status_code=409, detail="No pending DCR review exists for this case")

    now_value = format_date(get_current_time())
    db.update_case(case_id, {
        "dcr_approval_required": False,
        "dcr_override_reason": req.exceptional_reason,
        "adjournment_blocked": False,
        "dcr_auto_escalated": False,
        "dcr_approval_resolved_at": now_value,
        "dcr_approval_history": [{
            "action": "approved",
            "occurred_at": now_value,
            "actor_user_id": auth["user_id"],
            "reason": req.exceptional_reason,
        }],
    })
    _record_audit_event(
        auth["user_id"], "case.dcr_override", "case", case_id,
        reason=req.exceptional_reason,
    )
    return db.get_case(case_id)


@app.post("/api/cases/{case_id:path}/dcr-acknowledge", response_model=Dict[str, Any])
def acknowledge_dcr_review(
    case_id: CaseIdentifier,
    req: DCRReviewAcknowledgementRequest,
    auth: Dict[str, str] = Depends(get_current_user),
):
    """Acknowledge a pending review without approving it or unblocking the case."""
    if auth["role"] not in ["DCR", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: DCR or Chief Registrar role required.")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
    if not case.get("dcr_approval_required"):
        raise HTTPException(status_code=409, detail="No pending DCR review exists for this case")

    now_value = format_date(get_current_time())
    db.update_case(case_id, {
        "dcr_acknowledged_at": now_value,
        "dcr_acknowledged_by": auth["user_id"],
        "dcr_acknowledgement_note": req.note,
        "dcr_approval_history": [{
            "action": "acknowledged",
            "occurred_at": now_value,
            "actor_user_id": auth["user_id"],
            "note": req.note,
        }],
    })
    _record_audit_event(
        auth["user_id"], "case.dcr_review.acknowledge", "case", case_id,
        reason=req.note,
    )
    return db.get_case(case_id)

# ----------------- NEW ENDPOINTS: RBAC FEATURE COMPLETION -----------------

@app.post("/api/cases/{case_id:path}/report-missing", response_model=Dict[str, Any])
def report_file_missing(case_id: CaseIdentifier, req: FileMissingRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Report a physical file as missing without changing idle or ML-risk flags."""
    if auth["role"] not in ["Sheriff", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Only Sheriffs and the Chief Registrar can report missing files.")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
    if case_file_is_missing(case):
        raise HTTPException(status_code=409, detail="This case already has an open missing-file report")

    now = format_date(get_current_time())
    missing_report = {
        "reported_by": auth["user_id"],
        "reported_at": now,
        "last_known_location": req.last_known_location,
        "notes": req.notes,
        "resolved": False,
        "resolved_by": None,
        "resolved_at": None,
    }
    history_event = {
        "action": "reported_missing",
        "actor_user_id": auth["user_id"],
        "timestamp": now,
        "last_known_location": req.last_known_location,
        "notes": req.notes,
    }

    db.update_case(case_id, {
        "file_missing": True,
        "file_missing_report": missing_report,
        "file_missing_history": [history_event],
    })
    _record_audit_event(
        auth["user_id"], "case.file_missing.report", "case", case_id,
        metadata={"last_known_location": req.last_known_location},
    )

    logger.warning(f"FILE MISSING REPORT: Case {case_id} reported missing by {auth['user_id']} — last seen at {req.last_known_location}")
    return db.get_case(case_id)


@app.post("/api/cases/{case_id:path}/found", response_model=Dict[str, Any])
def record_file_found(case_id: CaseIdentifier, req: FileFoundRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Record an authorised recovery and resolve the open missing-file alert."""
    if auth.get("role") not in ["Sheriff", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: File recovery must be recorded by a Sheriff or Chief Registrar.")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
    if not case_file_is_missing(case):
        raise HTTPException(status_code=409, detail="There is no open missing-file report to resolve")

    report = dict(case.get("file_missing_report") or {})
    now = format_date(get_current_time())
    report.update({
        "resolved": True,
        "resolved_by": auth["user_id"],
        "resolved_at": now,
        "found_location": req.found_location,
        "resolution_reason": req.reason,
    })
    history_event = {
        "action": "found",
        "actor_user_id": auth["user_id"],
        "timestamp": now,
        "found_location": req.found_location,
        "reason": req.reason,
    }
    db.update_case(case_id, {
        "file_missing": False,
        "file_missing_report": report,
        "file_missing_history": [history_event],
    })
    _record_audit_event(
        auth["user_id"], "case.file_missing.found", "case", case_id,
        reason=req.reason,
        metadata={"found_location": req.found_location},
    )
    return db.get_case(case_id)


def _active_sheriff_for_case(case: Dict[str, Any], sheriff_id: str) -> Dict[str, Any]:
    """Resolve a current, active Sheriff assigned to the case's exact court."""
    sheriff = db.get_user(sheriff_id)
    if (not case.get("court") or not sheriff or sheriff.get("disabled")
            or sheriff.get("role") != "Sheriff"
            or sheriff.get("court") != case.get("court")):
        raise HTTPException(
            status_code=422,
            detail="Selected Sheriff is not active or is assigned to a different court",
        )
    return sheriff


@app.get("/api/cases/{case_id:path}/sheriffs", response_model=List[Dict[str, str]])
def list_case_sheriffs(case_id: CaseIdentifier, auth: Dict[str, str] = Depends(get_current_user)):
    """Return only active Sheriff accounts for this case's court."""
    if auth["role"] not in ["Clerk", "Chief Registrar", "Sheriff"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Sheriff custody is managed by registry staff and the assigned Sheriff.")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
    if auth["role"] == "Sheriff" and case.get("assigned_sheriff_id") != auth["user_id"]:
        raise HTTPException(status_code=403, detail="Only the assigned Sheriff may view handover recipients")

    current_sheriff_id = case.get("assigned_sheriff_id")
    sheriffs = [
        {
            "user_id": user["user_id"],
            "name": user.get("name") or user.get("username") or user["user_id"],
            "badge": user.get("badge") or "",
        }
        for user in db.list_users()
        if case.get("court")
        and user.get("role") == "Sheriff"
        and not user.get("disabled")
        and user.get("court") == case.get("court")
        and user.get("user_id") != current_sheriff_id
    ]
    return sorted(sheriffs, key=lambda item: (item["name"].casefold(), item["user_id"]))


@app.post("/api/cases/{case_id:path}/assign-sheriff", response_model=Dict[str, Any])
def assign_sheriff_to_case(case_id: CaseIdentifier, req: SheriffAssignmentRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Assign physical file custody to an active Sheriff in the same court."""
    if auth["role"] not in ["Clerk", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Sheriff assignment is restricted to registry staff")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
    _active_sheriff_for_case(case, req.sheriff_id)

    previous_sheriff_id = case.get("assigned_sheriff_id")
    if previous_sheriff_id == req.sheriff_id:
        raise HTTPException(status_code=409, detail="That Sheriff is already assigned to this case")

    now = format_date(get_current_time())
    custody_event = {
        "action": "reassigned" if previous_sheriff_id else "assigned",
        "from_sheriff_id": previous_sheriff_id,
        "to_sheriff_id": req.sheriff_id,
        "actor_user_id": auth["user_id"],
        "timestamp": now,
        "reason": req.reason,
    }
    db.update_case(case_id, {
        "assigned_sheriff_id": req.sheriff_id,
        "assigned_sheriff_at": now,
        "custody_history": [custody_event],
    })
    _record_audit_event(
        auth["user_id"],
        "case.sheriff.reassign" if previous_sheriff_id else "case.sheriff.assign",
        "case", case_id, reason=req.reason,
        metadata={"from_sheriff_id": previous_sheriff_id, "to_sheriff_id": req.sheriff_id},
    )
    return db.get_case(case_id)


@app.post("/api/cases/{case_id:path}/handover", response_model=Dict[str, Any])
def handover_case_custody(case_id: CaseIdentifier, req: SheriffHandoverRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Record a custody handover initiated by the currently assigned Sheriff."""
    if auth["role"] != "Sheriff":
        raise HTTPException(status_code=403, detail="Permission Denied: Custody handover must be initiated by the assigned Sheriff")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
    if case.get("assigned_sheriff_id") != auth["user_id"]:
        raise HTTPException(status_code=403, detail="Only the assigned Sheriff may hand over this file")
    _active_sheriff_for_case(case, req.to_sheriff_id)
    if req.to_sheriff_id == auth["user_id"]:
        raise HTTPException(status_code=409, detail="A Sheriff cannot hand a file over to themself")

    now = format_date(get_current_time())
    custody_event = {
        "action": "handover",
        "from_sheriff_id": auth["user_id"],
        "to_sheriff_id": req.to_sheriff_id,
        "actor_user_id": auth["user_id"],
        "timestamp": now,
        "location": req.location,
        "reason": req.reason,
    }
    db.update_case(case_id, {
        "assigned_sheriff_id": req.to_sheriff_id,
        "assigned_sheriff_at": now,
        "custody_history": [custody_event],
    })
    _record_audit_event(
        auth["user_id"], "case.sheriff.handover", "case", case_id,
        reason=req.reason,
        metadata={
            "from_sheriff_id": auth["user_id"],
            "to_sheriff_id": req.to_sheriff_id,
            "location": req.location,
        },
    )
    return db.get_case(case_id)


@app.post("/api/cases/{case_id:path}/assign-judge", response_model=Dict[str, Any])
def assign_judge_to_case(case_id: CaseIdentifier, req: AssignJudgeRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """
    CR-only: Assign or reassign a judge to a case (balloting).
    """
    if auth["role"] != "Chief Registrar":
        raise HTTPException(status_code=403, detail="Permission Denied: Judge assignment (balloting) requires Chief Registrar authority.")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)

    # Balloting targets must be active Judges of this exact court.
    judge = db.get_user(req.judge_id)
    if not judge or judge.get("disabled") or judge.get("role") != "Judge":
        raise HTTPException(status_code=422, detail="Selected account is not an active Judge")
    if not case.get("court") or judge.get("court") != case.get("court"):
        raise HTTPException(status_code=422, detail="Selected Judge is assigned to a different court")

    db.update_case(case_id, {
        "assigned_judge_id": req.judge_id,
    })
    _record_audit_event(
        auth["user_id"], "case.judge.assign", "case", case_id,
        reason=req.reason,
        metadata={"judge_id": req.judge_id},
    )

    logger.info(f"CASE ASSIGNMENT: {case_id} assigned to Judge {req.judge_id} by {auth['user_id']} — Reason: {req.reason}")
    return db.get_case(case_id)


@app.post("/api/cases/{case_id:path}/reassign", response_model=Dict[str, Any])
def reassign_case(case_id: CaseIdentifier, req: ReassignRequest, auth: Dict[str, str] = Depends(get_current_user)):
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
    if auth["role"] == "DCR":
        profile = db.get_user(auth["user_id"])
        if req.new_division and req.new_division != (profile or {}).get("division"):
            raise HTTPException(status_code=403, detail="DCR cannot move a case outside their assigned division")

    updates = {}
    if req.new_division:
        updates["assigned_division"] = req.new_division
    if req.new_court:
        updates["court"] = req.new_court

    if not updates:
        raise HTTPException(status_code=400, detail="Must specify new_division or new_court for reassignment.")

    db.update_case(case_id, updates)
    _record_audit_event(
        auth["user_id"], "case.reassign", "case", case_id,
        reason=req.reason,
        metadata=updates,
    )

    logger.info(f"CASE REASSIGNMENT: {case_id} reassigned by {auth['user_id']} ({auth['role']}) — Reason: {req.reason}")
    return db.get_case(case_id)


@app.get("/api/export/dcr-weekly")
def export_dcr_weekly_report(auth: Dict[str, str] = Depends(get_current_user)):
    """DCR/CR: Generate a division-scoped prototype workflow summary."""
    if auth["role"] not in ["DCR", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Weekly report requires DCR or Chief Registrar authority.")

    user_profile = db.get_user(auth["user_id"])
    if auth["role"] == "DCR":
        division = (user_profile or {}).get("division")
        if not division or division == "All Divisions":
            raise HTTPException(status_code=403, detail="DCR account has no valid assigned division")
        division_cases = [case for case in db.list_cases() if case.get("assigned_division") == division]
    else:
        division = "All Divisions"
        division_cases = db.list_cases()

    total = len(division_cases)
    risk_flagged = [c for c in division_cases if c.get("risk_flag")]
    pending_reviews = [c for c in division_cases if c.get("dcr_approval_required")]
    blocked = [c for c in division_cases if c.get("adjournment_blocked")]
    missing_files = [c for c in division_cases if case_file_is_missing(c)]
    _record_audit_event(
        auth["user_id"], "report.export.dcr_weekly", "report", division,
        metadata={"case_count": total},
    )

    return {
        "report_title": f"DCR Weekly Workflow Summary (Prototype) — {division}",
        "intended_use": "Internal workflow review only; not a legal compliance certificate.",
        "division": division,
        "generated_by": auth["user_id"],
        "export_date": format_date(get_current_time()),
        "summary": {
            "total_cases_in_division": total,
            "experimental_delay_risk_flags": len(risk_flagged),
            "pending_dcr_reviews": len(pending_reviews),
            "application_blocked_cases": len(blocked),
            "open_missing_file_reports": len(missing_files),
        },
        "experimental_delay_risk_case_ids": [c["case_id"] for c in risk_flagged],
        "pending_review_case_ids": [c["case_id"] for c in pending_reviews],
        "open_missing_file_case_ids": [c["case_id"] for c in missing_files],
    }


@app.post("/api/cases/{case_id:path}/documents", response_model=Dict[str, Any])
def upload_document(case_id: CaseIdentifier, req: DocumentUploadRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Record document metadata only; binary file storage is not implemented yet."""
    if auth["role"] not in ["Clerk", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Document metadata entry is restricted to Clerks and the Chief Registrar.")

    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)

    doc_record = {
        "document_type": req.document_type,
        "title": req.title,
        "filename": req.filename,
        "uploaded_by": auth["user_id"],
        "uploaded_at": format_date(get_current_time()),
        "notes": req.notes,
        "storage_path": None,
        "storage_status": "metadata_only"
    }

    db.update_case(case_id, {
        "documents": [doc_record]
    })
    _record_audit_event(
        auth["user_id"], "case.document.metadata_record", "case", case_id,
        metadata={"document_type": req.document_type},
    )

    logger.info(f"DOCUMENT METADATA RECORDED: {req.document_type} '{req.title}' for case {case_id} by {auth['user_id']}")
    return db.get_case(case_id)


def _build_case_alerts(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build operational prompts without presenting them as legal conclusions."""
    case_id = case["case_id"]
    alerts = []

    hearing_log = case.get("hearing_log", [])
    if hearing_log:
        latest = hearing_log[-1]
        next_date_str = latest.get("next_date", "")
        if next_date_str:
            try:
                hours_until = (parse_date(next_date_str) - get_current_time()).total_seconds() / 3600
                if 0 < hours_until <= 24:
                    alerts.append({
                        "type": "HEARING_24HR",
                        "message": f"Hearing scheduled in {max(1, int(hours_until))} hours.",
                        "severity": "warning",
                    })
            except (ValueError, TypeError):
                pass

    if case.get("adjournment_count", 0) >= 4:
        alerts.append({
            "type": "ADJOURNMENT_REVIEW",
            "message": (
                f"The configured application review threshold is reached at "
                f"{case.get('adjournment_count', 0)} recorded case-level adjournments. "
                "Verify the approved per-party policy; this prompt is not a legal finding."
            ),
            "severity": "warning",
        })

    if case.get("risk_flag"):
        alerts.append({
            "type": "EXPERIMENTAL_DELAY_RISK",
            "message": (
                f"Experimental delay-risk score: "
                f"{(case.get('delay_risk_score', 0) * 100):.0f}%. "
                "Decision support only; not a legal finding."
            ),
            "severity": "info",
        })

    # Missing-file status is independent of idle custody and delay-risk status.
    if case_file_is_missing(case):
        missing_report = case.get("file_missing_report") or {}
        alerts.append({
            "type": "FILE_MISSING",
            "message": f"Physical file reported missing; last known location: {missing_report.get('last_known_location', 'Unknown')}.",
            "severity": "critical",
        })

    return [
        {"case_id": case_id, **alert}
        for alert in alerts
    ]


@app.get("/api/cases/{case_id:path}/alerts", response_model=Dict[str, Any])
def get_case_alerts(case_id: CaseIdentifier, auth: Dict[str, str] = Depends(get_current_user)):
    """Return current operational prompts for a case within the caller's scope."""
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)

    alerts = _build_case_alerts(case)
    return {"case_id": case_id, "alerts": alerts, "alert_count": len(alerts)}


@app.get("/api/cases/{case_id:path}", response_model=Dict[str, Any])
def get_case(case_id: CaseIdentifier, auth: Dict[str, str] = Depends(get_current_user)):
    """Retrieves a single case document by ID."""
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case file not found")
    authorize_case(case, auth)
    return case


@app.get("/api/judge/alerts", response_model=Dict[str, Any])
def get_judge_alerts(auth: Dict[str, str] = Depends(get_current_user)):
    """Return operational prompts across the Judge's or Chief Registrar's scoped docket."""
    if auth["role"] not in ["Judge", "Chief Registrar"]:
        raise HTTPException(status_code=403, detail="Permission Denied: Judge alerts are restricted to Judges and Chief Registrar.")

    alerts = [
        alert
        for case in scoped_cases(auth)
        for alert in _build_case_alerts(case)
    ]
    return {
        "judge_id": auth["user_id"],
        "total_alerts": len(alerts),
        "alerts": alerts,
    }

@app.get("/api/export/prototype-summary")
def export_prototype_summary(auth: Dict[str, str] = Depends(get_current_user)):
    """Export a scoped, PII-minimized prototype workflow summary (not an official report)."""
    if auth["role"] not in ["Chief Registrar", "DCR"]:
        raise HTTPException(status_code=403, detail="Permission Denied: prototype summary export requires DCR or Chief Registrar authority.")

    user = db.get_user(auth["user_id"]) or {}
    if auth["role"] == "DCR" and (not user.get("division") or user.get("division") == "All Divisions"):
        raise HTTPException(status_code=403, detail="DCR account has no valid assigned division")

    cases = scoped_cases(auth)
    case_summaries = [{
        "case_id": case["case_id"],
        "judgment_status": case.get("judgment_status"),
        "experimental_delay_risk_score": case.get("delay_risk_score"),
        "experimental_delay_risk_flag": bool(case.get("risk_flag")),
        "idle_custody_prompt": bool(case.get("custody_alert")),
        "open_missing_file_report": case_file_is_missing(case),
        "pending_dcr_review": bool(case.get("dcr_approval_required")),
        "prototype_execution_review_flag": bool(case.get("enforcement_non_compliant")),
    } for case in cases]
    summary = {
        "total_scoped_cases": len(cases),
        "experimental_delay_risk_flags": sum(item["experimental_delay_risk_flag"] for item in case_summaries),
        "idle_custody_prompts": sum(item["idle_custody_prompt"] for item in case_summaries),
        "open_missing_file_reports": sum(item["open_missing_file_report"] for item in case_summaries),
        "pending_dcr_reviews": sum(item["pending_dcr_review"] for item in case_summaries),
        "prototype_execution_review_flags": sum(item["prototype_execution_review_flag"] for item in case_summaries),
    }
    _record_audit_event(
        auth["user_id"], "report.export.prototype_summary", "report", auth["role"],
        metadata={"case_count": len(cases)},
    )

    scope = user.get("division") if auth["role"] == "DCR" else "all cases in Chief Registrar scope"
    return {
        "report_title": "COURTLOG Prototype Workflow Summary",
        "intended_use": "Internal prototype review only; not an official NJC/NCMS submission or legal compliance certificate.",
        "scope": scope,
        "export_date": format_date(get_current_time()),
        "generated_by": auth["user_id"],
        "user_role": auth["role"],
        "summary": summary,
        "case_summaries": case_summaries,
        "limitations": [
            "Experimental delay-risk flags are not proven delay or non-compliance.",
            "Custody, adjournment, missing-file, and execution prompts require human review.",
            "This export omits party contact details and event histories.",
        ],
    }


@app.post("/api/cases/{case_id:path}/predict", response_model=Dict[str, Any])
def predict_case_risk(case_id: CaseIdentifier, auth: Dict[str, str] = Depends(get_current_user)):
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
    _record_audit_event(
        auth["user_id"], "case.predict", "case", case_id,
        metadata={"source": "on_demand"},
    )
    
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
    _record_audit_event(
        auth["user_id"], "case.predict.batch", "case_collection", auth["user_id"],
        metadata={"case_count": len(results)},
    )
    return results

@app.post("/api/cases/{case_id:path}/execution", response_model=Dict[str, Any])
def add_execution_action(case_id: CaseIdentifier, req: ExecutionRequest, auth: Dict[str, str] = Depends(get_current_user)):
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
    _record_audit_event(
        auth["user_id"], "case.execution.record", "case", case_id,
        metadata={"action": req.action},
    )
    
    return db.get_case(case_id)

@app.post("/api/cron", response_model=Dict[str, Any])
def run_cron_compliance_sweep(auth: Dict[str, str] = Depends(get_current_user)):
    """
    Simulated daily workflow sweep endpoint.
    Recalculates custody flags, days_since_filing, and execution-review prompts.
    """
    if auth["role"] != "Chief Registrar":
        raise HTTPException(status_code=403, detail="Workflow sweep requires Chief Registrar authority")
    run_compliance_checks_sync()
    cases = db.list_cases()
    
    stats = {
        "total_cases": len(cases),
        "custody_alerts": sum(1 for c in cases if c.get("custody_alert")),
        "missing_file_alerts": sum(1 for c in cases if case_file_is_missing(c)),
        "execution_review_prompts": sum(1 for c in cases if c.get("enforcement_non_compliant")),
        "high_risk_delay_cases": sum(1 for c in cases if c.get("risk_flag"))
    }
    _record_audit_event(
        auth["user_id"], "compliance.sweep", "case_collection", "all",
        metadata={"case_count": stats["total_cases"]},
    )
    
    return {
        "status": "success",
        "timestamp": format_date(get_current_time()),
        "stats": stats
    }

# ----------------- WHATSAPP CLOUD API, CONSENT, AND DELIVERY STATUS -----------------

_WHATSAPP_OPT_OUT_WORDS = {"stop", "stop all", "unsubscribe", "cancel", "end", "quit", "remove"}


def _require_whatsapp_admin(auth: Dict[str, str]) -> None:
    if auth["role"] != "Chief Registrar":
        raise HTTPException(status_code=403, detail="WhatsApp administration requires Chief Registrar authority")


@app.get("/api/whatsapp/status")
def get_whatsapp_status(response: Response, auth: Dict[str, str] = Depends(get_current_user)):
    _require_whatsapp_admin(auth)
    response.headers["Cache-Control"] = "no-store"
    return get_whatsapp_public_status()


@app.post("/api/whatsapp/preferences")
def record_whatsapp_preference(
    req: WhatsAppPreferenceRequest,
    response: Response,
    auth: Dict[str, str] = Depends(get_current_user),
):
    """Record an already-obtained, explicit opt-in or an operator-recorded opt-out."""
    _require_whatsapp_admin(auth)
    if not get_whatsapp_public_status()["consent_store_ready"]:
        raise HTTPException(status_code=503, detail="WhatsApp consent storage is not configured")
    try:
        phone_hash = hash_whatsapp_phone(req.phone)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="WhatsApp consent storage is not configured") from exc

    recorded_at = format_date(get_current_time())
    notice_version = os.getenv("WHATSAPP_CONSENT_NOTICE_VERSION", "courtlog-demo-v1").strip()[:80] or "courtlog-demo-v1"
    preference = db.set_whatsapp_preference(
        phone_hash=phone_hash,
        status=req.status,
        consent_source=req.consent_source,
        notice_version=notice_version,
        evidence_reference=req.evidence_reference,
        recorded_by=auth["user_id"],
        recorded_at=recorded_at,
    )
    _record_audit_event(
        auth["user_id"], "whatsapp.preference.update", "whatsapp_preference", phone_hash[:24],
        metadata={
            "status": req.status,
            "recipient": mask_whatsapp_phone(req.phone),
            "source": req.consent_source,
            "notice_version": notice_version,
            "evidence_reference": req.evidence_reference,
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "status": preference["status"],
        "recipient": mask_whatsapp_phone(req.phone),
        "recorded_at": preference["recorded_at"],
    }


@app.post("/api/whatsapp/test-send", status_code=202)
def send_whatsapp_test(
    req: WhatsAppTestSendRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    auth: Dict[str, str] = Depends(get_current_user),
):
    """Send the configured generic template to a case contact with active opt-in only."""
    _require_whatsapp_admin(auth)
    try:
        message, inserted = create_manual_test_message(db, req.case_id, req.recipient_role)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=404 if detail == "Case not found" else 422, detail=detail) from exc

    if inserted and message["status"] == "queued":
        background_tasks.add_task(deliver_whatsapp_message, db, message["message_id"])
    _record_audit_event(
        auth["user_id"], "whatsapp.test_send", "case", req.case_id,
        metadata={
            "recipient_role": req.recipient_role,
            "recipient": message["recipient_masked"],
            "status": message["status"],
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "message_id": message["message_id"],
        "status": message["status"],
        "recipient": message["recipient_masked"],
        "template_name": message["template_name"],
    }


@app.get("/api/whatsapp/logs")
def get_whatsapp_broadcast_logs(
    response: Response,
    limit: int = Query(default=100, ge=1, le=100),
    auth: Dict[str, str] = Depends(get_current_user),
):
    """Return privacy-minimized persistent delivery records to the Chief Registrar."""
    _require_whatsapp_admin(auth)
    response.headers["Cache-Control"] = "no-store"
    messages = db.list_whatsapp_messages(limit=limit)
    messages.extend(whatsapp_logs)
    messages.sort(key=lambda item: item.get("created_at", item.get("received_at", "")), reverse=True)
    return messages[:limit]


@app.get("/api/whatsapp/webhook")
def verify_whatsapp_webhook(request: Request):
    """Complete Meta's webhook subscription challenge without exposing the verify token."""
    if not get_whatsapp_public_status()["webhook_ready"]:
        raise HTTPException(status_code=404, detail="WhatsApp webhook is not configured")
    params = request.query_params
    mode = params.get("hub.mode", "")
    provided_token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")
    expected_token = webhook_verification_token()
    if mode != "subscribe" or not expected_token or not secrets.compare_digest(provided_token, expected_token):
        raise HTTPException(status_code=403, detail="Webhook verification failed")
    return Response(content=challenge, media_type="text/plain", headers={"Cache-Control": "no-store"})


@app.post("/api/whatsapp/webhook")
async def receive_whatsapp_webhook(request: Request, x_hub_signature_256: Optional[str] = Header(None)):
    """Verify Meta callbacks, persist status updates, and honour inbound STOP keywords."""
    if not get_whatsapp_public_status()["webhook_ready"]:
        raise HTTPException(status_code=404, detail="WhatsApp webhook is not configured")
    raw_body = await request.body()
    if not verify_webhook_signature(raw_body, x_hub_signature_256 or ""):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook JSON")

    occurred_at = format_date(get_current_time())
    for entry in payload.get("entry", []) if isinstance(payload.get("entry", []), list) else []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes", []) if isinstance(entry.get("changes", []), list) else []:
            if not isinstance(change, dict):
                continue
            value = change.get("value", {})
            if not isinstance(value, dict):
                continue

            statuses = value.get("statuses", [])
            for item in statuses if isinstance(statuses, list) else []:
                if not isinstance(item, dict):
                    continue
                provider_id = item.get("id")
                message_status = item.get("status")
                if not isinstance(provider_id, str) or message_status not in {"sent", "delivered", "read", "failed"}:
                    continue
                provider_error = None
                errors = item.get("errors", [])
                if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                    raw_code = errors[0].get("code")
                    provider_error = str(raw_code)[:80] if raw_code is not None else "provider_failure"
                db.update_whatsapp_delivery_status(
                    provider_id,
                    message_status,
                    occurred_at,
                    error_code=provider_error,
                    error_message="Provider reported message failure." if message_status == "failed" else None,
                )

            inbound = value.get("messages", [])
            for item in inbound if isinstance(inbound, list) else []:
                if not isinstance(item, dict):
                    continue
                message_type = item.get("type")
                text = ""
                if message_type == "text" and isinstance(item.get("text"), dict):
                    text = str(item["text"].get("body", ""))
                elif message_type == "interactive" and isinstance(item.get("interactive"), dict):
                    interactive = item["interactive"]
                    reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
                    if isinstance(reply, dict):
                        text = str(reply.get("title", "") or reply.get("id", ""))
                if text.strip().casefold() not in _WHATSAPP_OPT_OUT_WORDS:
                    continue

                sender = item.get("from")
                if not isinstance(sender, str):
                    continue
                if not get_whatsapp_public_status()["consent_store_ready"]:
                    raise HTTPException(status_code=503, detail="WhatsApp consent storage is not configured")
                try:
                    sender_phone = normalize_whatsapp_phone(sender)
                    sender_hash = hash_whatsapp_phone(sender_phone)
                except ValueError as exc:
                    logger.warning("Ignored an invalid WhatsApp opt-out sender address")
                    continue
                previous = db.get_whatsapp_preference(sender_hash)
                db.set_whatsapp_preference(
                    phone_hash=sender_hash,
                    status="opted_out",
                    consent_source="inbound_opt_out_keyword",
                    notice_version=os.getenv("WHATSAPP_CONSENT_NOTICE_VERSION", "courtlog-demo-v1")[:80],
                    evidence_reference=None,
                    recorded_by=None,
                    recorded_at=occurred_at,
                )
                if not previous or previous.get("status") != "opted_out":
                    _record_audit_event(
                        None, "whatsapp.opt_out", "whatsapp_preference", sender_hash[:24],
                        reason="Inbound WhatsApp opt-out keyword",
                        metadata={"status": "opted_out", "recipient": mask_whatsapp_phone(sender_phone), "source": "webhook"},
                    )

    return {"status": "accepted"}


@app.post("/api/whatsapp/webhook-simulator")
def whatsapp_webhook_simulator(payload: Dict[str, Any] = Body(...), x_simulator_secret: Optional[str] = Header(None)):
    """Accept a redacted simulator event in demo mode; this endpoint never calls Meta."""
    secret = os.getenv("SIMULATOR_SECRET", "")
    if not DEMO_MODE_ENABLED:
        raise HTTPException(status_code=404, detail="Simulator disabled")
    if not secret or not secrets.compare_digest(x_simulator_secret or "", secret):
        raise HTTPException(status_code=401, detail="Invalid simulator credentials")
    event = {
        "message_id": f"sim_{uuid.uuid4().hex}",
        "case_id": None,
        "recipient_role": None,
        "recipient_masked": "not recorded",
        "template_name": "simulator",
        "trigger_type": "simulator_webhook",
        "status": "simulated_webhook",
        "created_at": format_date(get_current_time()),
        "updated_at": format_date(get_current_time()),
    }
    whatsapp_logs.insert(0, event)
    del whatsapp_logs[30:]
    logger.info("Redacted simulated WhatsApp event accepted")
    return {"status": "accepted", "message_id": event["message_id"]}

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

@app.get("/service-worker.js", include_in_schema=False)
def serve_service_worker():
    """Expose the worker at origin root so its scope can cover the installed app."""
    worker_path = _FRONTEND_DIR / "service-worker.js"
    if not worker_path.exists():
        raise HTTPException(status_code=404, detail="Service worker not found")
    return FileResponse(
        str(worker_path),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


# Mount frontend assets on a sub-path so it doesn't swallow API routes
app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR)), name="frontend")


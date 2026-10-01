"""
database.py — SQLite-backed database for CourtLOG.

Stores cases and users as JSON blobs in a single SQLite file.
Maintains the same interface as the original MockDatabase/FirestoreDatabase
so main.py requires minimal changes.
"""

import json
import logging
import os
import re
import sqlite3
import uuid
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import bcrypt

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("courtlog.database")


# ---- Password utilities (imported by main.py) ----

def get_password_hash(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# ---- Date utilities (imported by main.py) ----

def parse_date(date_str: str) -> datetime:
    """Parse an ISO-8601 date string into a timezone-aware datetime."""
    date_str = date_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        dt = datetime.strptime(date_str[:19], "%Y-%m-%dT%H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)


def format_date(dt: datetime) -> str:
    """Format a datetime into an ISO-8601 string with Z suffix."""
    return dt.isoformat().replace("+00:00", "Z")


# ---- Seed users (5-Level Access Hierarchy) ----

SEED_USERS = [
    {
        "user_id": "usr_sheriff_01",
        "name": "Level 1: Sheriff",
        "username": "sheriff",
        "password": get_password_hash("123"),
        "role": "Sheriff",
        "badge": "Physical File Custodian",
        "court": "FHC Abuja Court 4",
        "division": "Criminal",
    },
    {
        "user_id": "usr_clerk_01",
        "name": "Level 2: Clerk",
        "username": "clerk",
        "password": get_password_hash("123"),
        "role": "Clerk",
        "badge": "Data Entry & Event Logger",
        "court": "FHC Abuja Court 4",
        "division": "Criminal",
    },
    {
        "user_id": "usr_dcr_01",
        "name": "Level 3: Deputy Chief Registrar (DCR)",
        "username": "dcr",
        "password": get_password_hash("123"),
        "role": "DCR",
        "badge": "Division Supervisor",
        "court": "FHC Abuja",
        "division": "Criminal",
    },
    {
        "user_id": "usr_cr_01",
        "name": "Level 4: Chief Registrar (CR)",
        "username": "cr",
        "password": get_password_hash("12345"),
        "role": "Chief Registrar",
        "badge": "Court Administrator & Compliance Officer",
        "court": "All Courts",
        "division": "All Divisions",
    },
    {
        "user_id": "usr_judge_01",
        "name": "Level 5: Judge",
        "username": "judge",
        "password": get_password_hash("123"),
        "role": "Judge",
        "badge": "Decision Maker & Accountability Owner",
        "court": "FHC Abuja Court 4",
        "division": "Criminal",
    },
]


# ---- Database Interface ----

class BaseDatabase:
    """Abstract interface for database operations."""

    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def save_case(self, case_id: str, case_data: Dict[str, Any]) -> None:
        raise NotImplementedError

    def update_case(self, case_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def list_cases(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def list_users(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def save_user(self, user_id: str, user_data: Dict[str, Any]) -> None:
        raise NotImplementedError

    def delete_user(self, user_id: str) -> bool:
        raise NotImplementedError

    def create_auth_session(self, session_id: str, user_id: str, refresh_jti: str, expires_at: int) -> None:
        raise NotImplementedError

    def is_auth_session_active(self, session_id: str, user_id: str) -> bool:
        raise NotImplementedError

    def is_refresh_session_active(self, session_id: str, user_id: str, refresh_jti: str) -> bool:
        raise NotImplementedError

    def revoke_auth_session(self, session_id: str, user_id: str) -> bool:
        raise NotImplementedError

    def revoke_user_sessions(self, user_id: str) -> int:
        raise NotImplementedError

    def reserve_login_attempt(
        self, principal_key: str, client_key: str, now: int,
        window_seconds: int, principal_limit: int, client_limit: int,
    ) -> tuple[Optional[str], int]:
        """Reserve an attempt or return its retry delay; keys must be pseudonymous."""
        raise NotImplementedError

    def complete_login_attempt(self, attempt_id: str) -> None:
        """Remove a successful login reservation so only failures consume quota."""
        raise NotImplementedError

    def create_case_qr_token(
        self, token_hash: str, case_id: str, issued_by: str, created_at: str,
    ) -> None:
        raise NotImplementedError

    def resolve_case_qr_token(self, token_hash: str) -> Optional[str]:
        raise NotImplementedError

    def append_scan_if_assigned(
        self, case_id: str, sheriff_id: str, scan_event: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def append_audit_event(
        self, actor_user_id: Optional[str], action: str, entity_type: str,
        entity_id: str, reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def list_audit_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        raise NotImplementedError


# ---- SQLite Implementation ----

class SQLiteDatabase(BaseDatabase):
    """SQLite database storing cases and users as JSON blobs.

    Thread-safe via a threading.Lock on all write operations.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(__file__), "..", "data", "courtlog.db"
            )
        self.db_path = os.path.abspath(os.getenv("COURTLOG_DB_PATH", db_path))
        self._lock = threading.Lock()

        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        logger.info(f"Initializing SQLite database at: {self.db_path}")

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        # Ensure DELETE triggers also fire for conflict-replacement attempts.
        self.conn.execute("PRAGMA recursive_triggers = ON")
        self._create_tables()
        self._seed_users_if_empty()

    def _create_tables(self) -> None:
        """Create tables if they don't exist."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )
            """)
            user_columns = {row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()}
            if "username" not in user_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
            # Backfill the indexed username from the existing JSON user records.
            for user_id, data in cursor.execute("SELECT user_id, data FROM users").fetchall():
                username = json.loads(data).get("username")
                if username:
                    cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (str(username).strip().lower(), user_id))
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username ON users(username COLLATE NOCASE) WHERE username IS NOT NULL")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    refresh_jti TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    revoked_at INTEGER
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auth_login_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    principal_key TEXT NOT NULL,
                    client_key TEXT NOT NULL,
                    attempted_at INTEGER NOT NULL
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_login_attempts_principal_client_time "
                "ON auth_login_attempts(principal_key, client_key, attempted_at)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_login_attempts_client_time "
                "ON auth_login_attempts(client_key, attempted_at)"
            )
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    occurred_at TEXT NOT NULL,
                    actor_user_id TEXT,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    reason TEXT,
                    metadata TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS case_qr_tokens (
                    token_hash TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    issued_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_case_qr_tokens_case_id "
                "ON case_qr_tokens(case_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_events_time "
                "ON audit_events(occurred_at DESC, event_id DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_events_actor_time "
                "ON audit_events(actor_user_id, occurred_at DESC)"
            )
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_update
                BEFORE UPDATE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit_events is append-only');
                END;
            """)
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_audit_events_no_delete
                BEFORE DELETE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit_events is append-only');
                END;
            """)
            self.conn.commit()

    def _seed_users_if_empty(self) -> None:
        """Seed demo accounts only in demo mode, or provision a one-time CR from env."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        demo_mode = os.getenv("DEMO_MODE", "false").strip().lower() == "true"
        demo_ids = {user["user_id"] for user in SEED_USERS}

        if demo_mode:
            if count == 0:
                logger.warning("DEMO_MODE is enabled: installing fictional demo users with demo-only credentials")
                with self._lock:
                    for seed in SEED_USERS:
                        user = {**seed, "demo_only": True, "disabled": False, "must_change_password": False}
                        self.conn.execute(
                            "INSERT INTO users (user_id, username, data) VALUES (?, ?, ?)",
                            (user["user_id"], user.get("username", "").strip().lower() or None, json.dumps(user)),
                        )
                    self.conn.commit()
                logger.info("Seeded %s demo users.", len(SEED_USERS))
                return
            for user in self.list_users():
                if user.get("user_id") in demo_ids or user.get("demo_only"):
                    if user.get("demo_only") is not True or user.get("disabled", False):
                        user["demo_only"] = True
                        user["disabled"] = False
                        self.save_user(user["user_id"], user)
            return

        # Demo fixtures that pre-date explicit mode controls must never stay usable in live mode.
        for user in self.list_users():
            if user.get("user_id") in demo_ids or user.get("demo_only"):
                if user.get("demo_only") is not True or not user.get("disabled", False):
                    user["demo_only"] = True
                    user["disabled"] = True
                    self.save_user(user["user_id"], user)

        active_cr = any(
            user.get("role") == "Chief Registrar" and not user.get("disabled")
            for user in self.list_users()
        )
        if active_cr:
            logger.info("Live mode: demo seed accounts are disabled")
            return

        username = os.getenv("COURTLOG_BOOTSTRAP_USERNAME", "").strip().lower()
        password = os.getenv("COURTLOG_BOOTSTRAP_PASSWORD", "")
        if not username and not password:
            logger.warning("No active Chief Registrar account. Set COURTLOG_BOOTSTRAP_USERNAME/PASSWORD or explicitly enable DEMO_MODE.")
            return
        if not username or not password:
            raise RuntimeError("Both COURTLOG_BOOTSTRAP_USERNAME and COURTLOG_BOOTSTRAP_PASSWORD are required")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,31}", username):
            raise RuntimeError("COURTLOG_BOOTSTRAP_USERNAME must be 3-32 lowercase letters, digits, '.', '_' or '-'")
        if len(password) < 12 or len(password.encode("utf-8")) > 72:
            raise RuntimeError("COURTLOG_BOOTSTRAP_PASSWORD must be at least 12 characters and at most 72 UTF-8 bytes")
        if any(str(user.get("username", "")).strip().casefold() == username.casefold() for user in self.list_users()):
            raise RuntimeError("COURTLOG_BOOTSTRAP_USERNAME already exists; choose another username or recover the existing Chief Registrar")

        user = {
            "user_id": f"usr_cr_bootstrap_{uuid.uuid4().hex}",
            "username": username,
            "password": get_password_hash(password),
            "name": os.getenv("COURTLOG_BOOTSTRAP_NAME", "Initial Chief Registrar").strip() or "Initial Chief Registrar",
            "role": "Chief Registrar",
            "badge": "Initial Court Administrator",
            "court": "All Courts",
            "division": "All Divisions",
            "disabled": False,
            "must_change_password": True,
        }
        self.save_user(user["user_id"], user)
        logger.warning("Created one-time bootstrap Chief Registrar account '%s'; change its password at first sign-in.", username)

    # ---- Case operations ----

    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single case by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT data FROM cases WHERE case_id = ?", (case_id,))
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None

    def save_case(self, case_id: str, case_data: Dict[str, Any]) -> None:
        """Insert or fully replace a case."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO cases (case_id, data) VALUES (?, ?)",
                (case_id, json.dumps(case_data)),
            )
            self.conn.commit()

    def update_case(self, case_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a case — list fields are appended, scalars are overwritten."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT data FROM cases WHERE case_id = ?", (case_id,))
            row = cursor.fetchone()
            if not row:
                return None

            case_data = json.loads(row[0])
            list_fields = {
                "scan_events", "hearing_log", "execution_log", "documents",
                "custody_history", "file_missing_history", "dcr_approval_history",
            }

            for key, value in updates.items():
                if key in list_fields and isinstance(value, list):
                    if key not in case_data or not isinstance(case_data[key], list):
                        case_data[key] = []
                    case_data[key].extend(value)
                else:
                    case_data[key] = value

            cursor.execute(
                "UPDATE cases SET data = ? WHERE case_id = ?",
                (json.dumps(case_data), case_id),
            )
            self.conn.commit()
            return case_data

    def list_cases(self) -> List[Dict[str, Any]]:
        """Return all cases."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT data FROM cases")
        return [json.loads(row[0]) for row in cursor.fetchall()]

    def create_case_qr_token(
        self, token_hash: str, case_id: str, issued_by: str, created_at: str,
    ) -> None:
        """Persist only a one-way hash of the opaque printed QR token."""
        with self._lock:
            self.conn.execute(
                "INSERT INTO case_qr_tokens (token_hash, case_id, issued_by, created_at) "
                "VALUES (?, ?, ?, ?)",
                (token_hash, case_id, issued_by, created_at),
            )
            self.conn.commit()

    def resolve_case_qr_token(self, token_hash: str) -> Optional[str]:
        """Resolve an opaque QR token to a case ID; callers must authorize anew."""
        with self._lock:
            cursor = self.conn.execute(
                "SELECT case_id FROM case_qr_tokens WHERE token_hash = ?",
                (token_hash,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def append_scan_if_assigned(
        self, case_id: str, sheriff_id: str, scan_event: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Atomically confirm current Sheriff custody and append a QR scan event."""
        with self._lock:
            cursor = self.conn.cursor()
            try:
                cursor.execute("BEGIN IMMEDIATE")
                cursor.execute("SELECT data FROM cases WHERE case_id = ?", (case_id,))
                row = cursor.fetchone()
                if not row:
                    self.conn.rollback()
                    return None
                case_data = json.loads(row[0])
                if case_data.get("assigned_sheriff_id") != sheriff_id:
                    self.conn.rollback()
                    return None
                scans = case_data.get("scan_events")
                if not isinstance(scans, list):
                    scans = []
                scans.append(scan_event)
                case_data["scan_events"] = scans
                case_data["custody_alert"] = False
                cursor.execute(
                    "UPDATE cases SET data = ? WHERE case_id = ?",
                    (json.dumps(case_data), case_id),
                )
                self.conn.commit()
                return case_data
            except Exception:
                self.conn.rollback()
                raise

    # ---- User operations ----

    def list_users(self) -> List[Dict[str, Any]]:
        """Return all users."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT data FROM users")
        return [json.loads(row[0]) for row in cursor.fetchall()]

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single user by user_id."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT data FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None

    def save_user(self, user_id: str, user_data: Dict[str, Any]) -> None:
        """Insert or replace a user."""
        with self._lock:
            cursor = self.conn.cursor()
            username = str(user_data.get("username", "")).strip().lower() or None
            try:
                cursor.execute(
                    "INSERT INTO users (user_id, username, data) VALUES (?, ?, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET username = excluded.username, data = excluded.data",
                    (user_id, username, json.dumps(user_data)),
                )
                self.conn.commit()
            except sqlite3.IntegrityError:
                self.conn.rollback()
                raise

    def delete_user(self, user_id: str) -> bool:
        """Delete a user and revoke every session issued to that account."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
            if not cursor.fetchone():
                return False
            now = int(datetime.now(timezone.utc).timestamp())
            cursor.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, user_id),
            )
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            self.conn.commit()
            return True

    # ---- Server-side authentication sessions ----

    def create_auth_session(self, session_id: str, user_id: str, refresh_jti: str, expires_at: int) -> None:
        now = int(datetime.now(timezone.utc).timestamp())
        with self._lock:
            self.conn.execute(
                "INSERT INTO auth_sessions (session_id, user_id, refresh_jti, expires_at, created_at, revoked_at) "
                "VALUES (?, ?, ?, ?, ?, NULL)",
                (session_id, user_id, refresh_jti, expires_at, now),
            )
            self.conn.commit()

    def is_auth_session_active(self, session_id: str, user_id: str) -> bool:
        now = int(datetime.now(timezone.utc).timestamp())
        with self._lock:
            cursor = self.conn.execute(
                "SELECT 1 FROM auth_sessions WHERE session_id = ? AND user_id = ? "
                "AND revoked_at IS NULL AND expires_at > ?",
                (session_id, user_id, now),
            )
            return cursor.fetchone() is not None

    def is_refresh_session_active(self, session_id: str, user_id: str, refresh_jti: str) -> bool:
        now = int(datetime.now(timezone.utc).timestamp())
        with self._lock:
            cursor = self.conn.execute(
                "SELECT 1 FROM auth_sessions WHERE session_id = ? AND user_id = ? "
                "AND refresh_jti = ? AND revoked_at IS NULL AND expires_at > ?",
                (session_id, user_id, refresh_jti, now),
            )
            return cursor.fetchone() is not None

    def revoke_auth_session(self, session_id: str, user_id: str) -> bool:
        now = int(datetime.now(timezone.utc).timestamp())
        with self._lock:
            cursor = self.conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE session_id = ? AND user_id = ? AND revoked_at IS NULL",
                (now, session_id, user_id),
            )
            self.conn.commit()
            return cursor.rowcount == 1

    def revoke_user_sessions(self, user_id: str) -> int:
        now = int(datetime.now(timezone.utc).timestamp())
        with self._lock:
            cursor = self.conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, user_id),
            )
            self.conn.commit()
            return cursor.rowcount

    def reserve_login_attempt(
        self, principal_key: str, client_key: str, now: int,
        window_seconds: int, principal_limit: int, client_limit: int,
    ) -> tuple[Optional[str], int]:
        """Atomically reserve a login attempt within principal and client windows.

        Only failed attempts remain in this table: a successful request deletes its
        reservation. Values supplied as keys are one-way hashes; raw usernames and
        client addresses are never written to the rate-limit table.
        """
        if window_seconds < 1 or principal_limit < 1 or client_limit < 1:
            raise ValueError("Login rate-limit settings must be positive")
        cutoff = now - window_seconds
        with self._lock:
            cursor = self.conn.cursor()
            try:
                # BEGIN IMMEDIATE serializes the count-and-reserve operation across
                # threads and SQLite workers sharing this database file.
                cursor.execute("BEGIN IMMEDIATE")
                cursor.execute(
                    "DELETE FROM auth_login_attempts WHERE attempted_at <= ?", (cutoff,)
                )

                cursor.execute(
                    "SELECT COUNT(*), MIN(attempted_at) FROM auth_login_attempts "
                    "WHERE principal_key = ? AND client_key = ? AND attempted_at > ?",
                    (principal_key, client_key, cutoff),
                )
                principal_count, principal_oldest = cursor.fetchone()
                cursor.execute(
                    "SELECT COUNT(*), MIN(attempted_at) FROM auth_login_attempts "
                    "WHERE client_key = ? AND attempted_at > ?",
                    (client_key, cutoff),
                )
                client_count, client_oldest = cursor.fetchone()

                retry_delays = []
                if principal_count >= principal_limit:
                    retry_delays.append(window_seconds - (now - principal_oldest))
                if client_count >= client_limit:
                    retry_delays.append(window_seconds - (now - client_oldest))
                if retry_delays:
                    self.conn.commit()
                    return None, max(1, max(retry_delays))

                attempt_id = uuid.uuid4().hex
                cursor.execute(
                    "INSERT INTO auth_login_attempts "
                    "(attempt_id, principal_key, client_key, attempted_at) VALUES (?, ?, ?, ?)",
                    (attempt_id, principal_key, client_key, now),
                )
                self.conn.commit()
                return attempt_id, 0
            except Exception:
                self.conn.rollback()
                raise

    def complete_login_attempt(self, attempt_id: str) -> None:
        """Remove a successful attempt reservation so it does not count as a failure."""
        with self._lock:
            self.conn.execute(
                "DELETE FROM auth_login_attempts WHERE attempt_id = ?", (attempt_id,)
            )
            self.conn.commit()

    def append_audit_event(
        self, actor_user_id: Optional[str], action: str, entity_type: str,
        entity_id: str, reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Append a minimal, server-attributed event; never update/delete existing events."""
        if not action or len(action) > 100:
            raise ValueError("Audit action must contain 1-100 characters")
        if not entity_type or len(entity_type) > 80:
            raise ValueError("Audit entity_type must contain 1-80 characters")
        if not entity_id or len(entity_id) > 256:
            raise ValueError("Audit entity_id must contain 1-256 characters")
        if reason is not None and len(reason) > 2000:
            raise ValueError("Audit reason must not exceed 2000 characters")
        metadata_json = json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True)
        if len(metadata_json.encode("utf-8")) > 4096:
            raise ValueError("Audit metadata must not exceed 4096 bytes")

        event = {
            "event_id": uuid.uuid4().hex,
            "occurred_at": format_date(datetime.now(timezone.utc)),
            "actor_user_id": actor_user_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "reason": reason,
            "metadata": metadata or {},
        }
        with self._lock:
            self.conn.execute(
                "INSERT INTO audit_events "
                "(event_id, occurred_at, actor_user_id, action, entity_type, entity_id, reason, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event["event_id"], event["occurred_at"], actor_user_id,
                    action, entity_type, entity_id, reason, metadata_json,
                ),
            )
            self.conn.commit()
        return event

    def list_audit_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent audit records; callers are responsible for authorization."""
        if not 1 <= limit <= 500:
            raise ValueError("Audit event limit must be between 1 and 500")
        with self._lock:
            rows = self.conn.execute(
                "SELECT event_id, occurred_at, actor_user_id, action, entity_type, entity_id, reason, metadata "
                "FROM audit_events ORDER BY occurred_at DESC, event_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "event_id": row[0], "occurred_at": row[1], "actor_user_id": row[2],
                "action": row[3], "entity_type": row[4], "entity_id": row[5],
                "reason": row[6], "metadata": json.loads(row[7]),
            }
            for row in rows
        ]

    # ---- Maintenance ----

    def _clear_cases(self) -> None:
        """Delete all cases and their opaque labels. Used by seed_db.py for re-seeding."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM case_qr_tokens")
            cursor.execute("DELETE FROM cases")
            self.conn.commit()
            logger.info("All cases and QR labels cleared from database.")


# ---- Factory ----

def get_db_client() -> BaseDatabase:
    """Return the appropriate database client.

    If firebase_creds.json exists in the project root, Firestore would be used.
    Otherwise falls back to SQLite (the default for local/Docker deployment).
    """
    creds_path = os.path.join(os.path.dirname(__file__), "..", "firebase_creds.json")
    if os.path.exists(creds_path):
        logger.info("Firebase credentials found — Firestore support available but not implemented.")
        # FirestoreDatabase could be imported and returned here in the future.

    logger.info("Using SQLite database.")
    return SQLiteDatabase()

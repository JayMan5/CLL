"""
database.py — SQLite-backed database for CourtLOG.

Stores cases and users as JSON blobs in a single SQLite file.
Maintains the same interface as the original MockDatabase/FirestoreDatabase
so main.py requires minimal changes.
"""

import json
import logging
import os
import sqlite3
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
            self.conn.commit()

    def _seed_users_if_empty(self) -> None:
        """Insert seed users if the users table is empty."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        if count == 0:
            logger.info("Users table empty — seeding default users...")
            with self._lock:
                for user in SEED_USERS:
                    cursor.execute(
                        "INSERT INTO users (user_id, data) VALUES (?, ?)",
                        (user["user_id"], json.dumps(user)),
                    )
                self.conn.commit()
            logger.info(f"Seeded {len(SEED_USERS)} users.")

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
            list_fields = {"scan_events", "hearing_log", "execution_log", "documents"}

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
            cursor.execute(
                "INSERT OR REPLACE INTO users (user_id, data) VALUES (?, ?)",
                (user_id, json.dumps(user_data)),
            )
            self.conn.commit()

    def delete_user(self, user_id: str) -> bool:
        """Delete a user by user_id. Returns True if deleted, False if not found."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
            if not cursor.fetchone():
                return False
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            self.conn.commit()
            return True

    # ---- Maintenance ----

    def _clear_cases(self) -> None:
        """Delete all cases. Used by seed_db.py for re-seeding."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM cases")
            self.conn.commit()
            logger.info("All cases cleared from database.")


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

"""
auth.py - JWT authentication for CourtLOG.

Uses RS256 (asymmetric) JWT tokens. Keys are auto-generated on first run
if not found at the configured paths.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

load_dotenv()

logger = logging.getLogger("courtlog.auth")

ALGORITHM = "RS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Key file paths (relative to project root)
_project_root = Path(__file__).resolve().parent.parent
PRIVATE_KEY_PATH = Path(os.environ.get(
    "JWT_PRIVATE_KEY_PATH",
    str(_project_root / "private_key.pem"),
))
PUBLIC_KEY_PATH = Path(os.environ.get(
    "JWT_PUBLIC_KEY_PATH",
    str(_project_root / "public_key.pem"),
))


def _generate_keys() -> None:
    """Generate RS256 key pair if they don't exist."""
    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return

    logger.info("JWT keys not found — generating RS256 key pair...")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Write private key
    PRIVATE_KEY_PATH.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    # Write public key
    public_key = private_key.public_key()
    PUBLIC_KEY_PATH.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    logger.info(f"Keys generated: {PRIVATE_KEY_PATH}, {PUBLIC_KEY_PATH}")


def _load_keys() -> tuple:
    """Load private and public keys from PEM files."""
    _generate_keys()
    private_key = PRIVATE_KEY_PATH.read_text()
    public_key = PUBLIC_KEY_PATH.read_text()
    return private_key, public_key


# Load keys at module level
_private_key, _public_key = _load_keys()

# OAuth2 scheme for FastAPI's automatic token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login", auto_error=False)


def create_access_token(data: Dict[str, Any]) -> str:
    """Create a short-lived access token (30 min default)."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, _private_key, algorithm=ALGORITHM)


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create a long-lived refresh token (7 days default)."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, _private_key, algorithm=ALGORITHM)


def verify_token(token: str) -> Dict[str, Any]:
    """Decode and verify a JWT token. Raises on failure."""
    try:
        payload = jwt.decode(token, _public_key, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(request: Request, token: Optional[str] = Depends(oauth2_scheme)) -> Dict[str, str]:
    """FastAPI dependency that extracts user info from a valid Bearer token.

    Returns a dict with 'user_id' and 'role' keys — same shape as
    the old get_auth_context() so main.py needs minimal changes.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(token)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — use an access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    role = payload.get("role")

    if not user_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from backend import main
    user = main.db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Account is no longer active")
    if user.get("disabled"):
        main.db.revoke_user_sessions(user_id)
        raise HTTPException(status_code=401, detail="Account is no longer active")

    session_id = payload.get("sid")
    if not session_id or not main.db.is_auth_session_active(session_id, user_id):
        raise HTTPException(status_code=401, detail="Session is no longer active")

    if user.get("must_change_password") and request.url.path != "/api/users/me/password":
        raise HTTPException(
            status_code=403,
            detail="Initial password change required",
            headers={"X-Password-Change-Required": "true"},
        )

    return {"user_id": user_id, "role": user["role"]}

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from sigillum.config import get_settings

_ITERATIONS = 310_000


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 10:
        raise ValueError("Passwords must contain at least 10 characters.")
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt_b64, digest_b64 = encoded.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        iteration_count = int(iterations)
        if iteration_count < 100_000 or iteration_count > 2_000_000:
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(digest_b64, validate=True)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iteration_count)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, AttributeError):
        return False


def create_access_token(user_id: str, role: str, tenant_id: str, session_id: str | None = None) -> str:
    """Create a short-lived token with a revocable server-side session identifier.

    Role and tenant are retained as informational legacy claims only. API
    authorization always re-reads the active membership from the database.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "tenant_id": tenant_id,
        "jti": session_id or str(uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])


def create_file_grant_token(
    *,
    user_id: str,
    session_id: str,
    membership_id: str,
    tenant_id: str,
    brand_id: str,
    brand_record_id: str,
    version_id: str,
) -> str:
    """Create a short-lived download grant bound to a live user session and brand."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": "file_download",
        "sub": user_id,
        "session_id": session_id,
        "membership_id": membership_id,
        "tenant_id": tenant_id,
        "brand_id": brand_id,
        "brand_record_id": brand_record_id,
        "version_id": version_id,
        "jti": str(uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.file_grant_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")

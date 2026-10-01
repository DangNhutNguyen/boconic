import hashlib
import hmac
import os
import secrets
from typing import Tuple

def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with 100,000 iterations and a secure random salt."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return f"pbkdf2_sha256$100000${salt.hex()}${key.hex()}"

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against stored PBKDF2 hash."""
    try:
        parts = hashed.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected_key = bytes.fromhex(parts[3])
        computed_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(expected_key, computed_key)
    except Exception:
        return False

def generate_session_token() -> str:
    """Generate high-entropy session token."""
    return secrets.token_urlsafe(32)

def generate_csrf_token() -> str:
    """Generate random CSRF token."""
    return secrets.token_hex(24)

def generate_public_alias() -> str:
    """Generate friendly public alias, e.g. 'User #A81F'."""
    suffix = secrets.token_hex(2).upper()
    return f"User #{suffix}"

def generate_public_copy_code() -> str:
    """Generate random public code for a physical book copy, e.g. 'BOC-9A4F'."""
    suffix = secrets.token_hex(3).upper()
    return f"BOC-{suffix}"

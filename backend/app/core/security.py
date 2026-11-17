from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import hashlib
import os

import jwt
try:
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher
    password_hash_engine = PasswordHash((Argon2Hasher(),))
except Exception:
    password_hash_engine = None

from .config import get_settings

settings = get_settings()


def hash_password(password: str) -> str:
    if password_hash_engine:
        try:
            return password_hash_engine.hash(password)
        except Exception:
            pass
    # Secure PBKDF2-HMAC-SHA256 fallback
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return f"pbkdf2_sha256${salt.hex()}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password.startswith("pbkdf2_sha256$"):
        try:
            _, salt_hex, key_hex = hashed_password.split("$")
            salt = bytes.fromhex(salt_hex)
            expected_key = bytes.fromhex(key_hex)
            test_key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 100000)
            return test_key == expected_key
        except Exception:
            return False

    if password_hash_engine:
        try:
            return password_hash_engine.verify(plain_password, hashed_password)
        except Exception:
            return False

    return False


def create_access_token(
    subject: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if extra_claims:
        to_encode.update(extra_claims)

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None

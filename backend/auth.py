
import os
from datetime import datetime, timedelta
from typing import Optional
import logging

from jose import jwt
import bcrypt
import hashlib

# Config
SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Warn if using default secret key
if SECRET_KEY == "dev-secret":
    logging.warning(
        "Using default JWT_SECRET='dev-secret'. This is insecure for production. "
        "Set the JWT_SECRET environment variable to a secure random value."
    )


def _prehash(password: str) -> bytes:
    """Pre-hash long passwords with SHA256 before bcrypt to avoid the 72-byte limit."""
    if isinstance(password, str):
        password = password.encode("utf-8")
    return hashlib.sha256(password).digest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # hashed_password is the bcrypt result (utf-8 string)
    try:
        ph = _prehash(plain_password)
        return bcrypt.checkpw(ph, hashed_password.encode("utf-8"))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    ph = _prehash(password)
    hashed = bcrypt.hashpw(ph, bcrypt.gensalt())
    return hashed.decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    # Will raise jose.JWTError subclasses on failure
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload

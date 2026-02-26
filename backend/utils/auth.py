import os
from datetime import datetime, timedelta, timezone
from typing import Optional
import logging

from jose import JWTError, jwt
import bcrypt
import hashlib

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
from models import User

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Config
SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    error_msg = (
        "CRITICAL: JWT_SECRET environment variable is not set. "
        "This is required for production. Generate a secure key using: "
        "python -c 'import secrets; print(secrets.token_urlsafe(32))'"
    )
    logger.error(error_msg)
    raise ValueError(error_msg)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
PASSWORD_RESET_EXPIRE_MINUTES = 15

# Validate token expiry settings
if ACCESS_TOKEN_EXPIRE_MINUTES < 5:
    logger.warning(f"ACCESS_TOKEN_EXPIRE_MINUTES is set to {ACCESS_TOKEN_EXPIRE_MINUTES}, which is very short")
elif ACCESS_TOKEN_EXPIRE_MINUTES > 1440:  # 24 hours
    logger.warning(f"ACCESS_TOKEN_EXPIRE_MINUTES is set to {ACCESS_TOKEN_EXPIRE_MINUTES}, which is quite long for security")


def _prehash(password: str) -> bytes:
    """Pre-hash long passwords with SHA256 before bcrypt to avoid the 72-byte limit."""
    if isinstance(password, str):
        password = password.encode("utf-8")
    return hashlib.sha256(password).digest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.
    
    Args:
        plain_password: The plain text password to verify
        hashed_password: The bcrypt hashed password (utf-8 string)
    
    Returns:
        bool: True if password matches, False otherwise
    """
    try:
        ph = _prehash(plain_password)
        return bcrypt.checkpw(ph, hashed_password.encode("utf-8"))
    except Exception as e:
        logger.warning(f"Password verification failed: {str(e)}")
        return False


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt with SHA256 pre-hashing.
    
    Args:
        password: The plain text password to hash
    
    Returns:
        str: The bcrypt hashed password
    """
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    
    ph = _prehash(password)
    # Use cost factor of 12 for production (higher is more secure but slower)
    hashed = bcrypt.hashpw(ph, bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: The data to encode in the token (typically {'sub': user_email})
        expires_delta: Optional custom expiration time
    
    Returns:
        str: The encoded JWT token
    """
    if not data or "sub" not in data:
        raise ValueError("Token data must include 'sub' (subject) field")
    
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": now,
        "nbf": now  # Not before - token is not valid before this time
    })
    
    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        logger.error(f"Failed to create access token: {str(e)}")
        raise


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.
    
    Args:
        token: The JWT token string to decode
    
    Returns:
        dict: The decoded token payload
    
    Raises:
        JWTError: If token is invalid or expired
    """
    try:
        # jwt.decode will automatically validate exp, iat, and nbf claims
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"Token decode failed: {str(e)}")
        raise


def create_password_reset_token(email: str) -> str:
    """
    Create a short-lived JWT for password reset.

    The token contains a 'purpose' claim to prevent cross-use with login tokens.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES)
    payload = {
        "sub": email,
        "purpose": "password-reset",
        "exp": expire,
        "iat": now,
        "nbf": now,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_password_reset_token(token: str) -> dict:
    """
    Decode a password-reset JWT and verify its purpose claim.

    Returns the full payload dict (contains 'sub', 'iat', etc.).
    Raises JWTError or ValueError on failure.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        logger.warning(f"Reset token decode failed: {str(e)}")
        raise

    if payload.get("purpose") != "password-reset":
        raise ValueError("Token is not a valid password-reset token")

    if not payload.get("sub"):
        raise ValueError("Token missing subject")

    return payload


# HTTP Bearer security scheme
security = HTTPBearer(auto_error=True)

async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: AsyncSession = Depends(get_db),
) -> User:
    """
    Resolve the currently authenticated user from the Bearer token.
    
    This dependency is used to protect routes that require authentication.
    The JWT token must contain a 'sub' field with the user's email.
    
    Args:
        credentials: The HTTP Bearer credentials containing the JWT token
        db: The database session
    
    Returns:
        User: The authenticated user object
    
    Raises:
        HTTPException: If authentication fails for any reason
    """
    token = credentials.credentials
    
    # Validate token format
    if not token or len(token) < 10:
        logger.warning("Received invalid token format")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
        email: Optional[str] = payload.get("sub")
        
        if not email:
            logger.warning("Token missing 'sub' claim")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # Validate email format (basic check)
        if "@" not in email or len(email) < 3:
            logger.warning(f"Invalid email format in token: {email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: malformed subject",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
    except JWTError as e:
        logger.warning(f"JWT validation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during token validation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Query user from database
    try:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        
        if user is None:
            logger.warning(f"User not found for email: {email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Optional: Add additional checks here (e.g., is_active, is_verified)
        # if hasattr(user, 'is_active') and not user.is_active:
        #     logger.warning(f"Inactive user attempted access: {email}")
        #     raise HTTPException(
        #         status_code=status.HTTP_403_FORBIDDEN,
        #         detail="User account is inactive",
        #     )
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database error during user lookup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error",
        )

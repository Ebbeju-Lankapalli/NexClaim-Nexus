"""
NexClaim Security Module.

Handles JWT token creation/verification, password hashing,
OTP generation, CAPTCHA, and role-based access control.
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt
from sqlalchemy.orm import Session

from app.shared.backend.config import settings
from app.shared.backend.database import get_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError as exc:
        logger.warning("JWT decode error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------------
# OTP
# ---------------------------------------------------------------------------

OTP_LENGTH = 6


def generate_otp() -> str:
    """Generate a secure 6-digit numeric OTP."""
    return "".join(str(secrets.randbelow(10)) for _ in range(OTP_LENGTH))


# ---------------------------------------------------------------------------
# Math CAPTCHA
# ---------------------------------------------------------------------------

def generate_math_captcha() -> dict:
    """Generate a simple math CAPTCHA challenge."""
    a = secrets.randbelow(20) + 1
    b = secrets.randbelow(20) + 1
    return {"question": f"What is {a} + {b}?", "answer": a + b}


# ---------------------------------------------------------------------------
# HTTP Bearer dependency
# ---------------------------------------------------------------------------

security_scheme = HTTPBearer()


def get_current_user_payload(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    """FastAPI dependency: decode JWT and return payload."""
    return decode_access_token(credentials.credentials)


def require_role(*allowed_roles: str):
    """FastAPI dependency factory: enforce role-based access control."""

    def role_checker(
        payload: dict = Depends(get_current_user_payload),
        db: Session = Depends(get_db),
    ) -> dict:
        role = payload.get("role")
        if role not in allowed_roles:
            logger.warning(
                "Unauthorized access attempt. Required: %s, Got: %s",
                allowed_roles,
                role,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(allowed_roles)}",
            )
        return payload

    return role_checker


def validate_password_strength(password: str) -> bool:
    """Validate password meets minimum strength requirements."""
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "@$!%*?&_-#" for c in password)
    return len(password) >= 8 and has_upper and has_lower and has_digit and has_special

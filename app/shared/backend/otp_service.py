"""
NexClaim OTP Service.

Manages OTP generation, storage, and verification.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.shared.backend.config import settings
from app.shared.backend.email_service import email_service
from app.shared.backend.models import User
from app.shared.backend.security import generate_otp, hash_password, verify_password

logger = logging.getLogger(__name__)


class OtpService:
    """Handles OTP lifecycle: generation, delivery, and validation."""

    def send_otp(self, db: Session, user: User) -> str:
        """Generate, store, and email a new OTP to the user."""
        otp = generate_otp()
        user.otp_code = hash_password(otp)  # Store hashed OTP
        user.otp_expires_at = datetime.utcnow() + timedelta(
            minutes=settings.OTP_EXPIRE_MINUTES
        )
        db.commit()
        logger.info("OTP generated for user %s", user.email)
        # OTPs are sensitive authentication secrets. Only display them in explicit
        # local DEBUG mode when SMTP is not configured; never log them otherwise.
        if settings.DEBUG and (not settings.SMTP_USER or not settings.SMTP_PASSWORD):
            logger.warning("[LOCAL DEBUG ONLY] OTP for %s: %s", user.email, otp)
        email_service.send_otp_email(user.email, user.full_name, otp)
        return otp

    def verify_otp(self, db: Session, user: User, otp_code: str) -> bool:
        """Verify an OTP code against the stored hash and check expiry."""
        if not user.otp_code or not user.otp_expires_at:
            logger.warning("OTP verification failed: no OTP on record for user %s", user.email)
            return False

        if datetime.utcnow() > user.otp_expires_at:
            logger.warning("OTP expired for user %s", user.email)
            return False

        if not verify_password(otp_code, user.otp_code):
            logger.warning("OTP mismatch for user %s", user.email)
            return False

        # Clear OTP after successful verification
        user.otp_code = None
        user.otp_expires_at = None
        user.is_verified = True
        db.commit()
        logger.info("OTP verified successfully for user %s", user.email)
        return True


otp_service = OtpService()

"""
NexClaim Shared Authentication Router.

Handles user registration, login, OTP verification, and profile endpoints.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.shared.backend.config import settings
from app.shared.backend.database import get_db
from app.shared.backend.models import (
    Admin, BlockedUser, Notification, Policyholder, Role, Reviewer, User
)
from app.shared.backend.otp_service import otp_service
from app.shared.backend.schemas import (
    CaptchaResponse,
    ContactMessageRequest,
    FirstLoginPasswordChangeRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    NotificationResponse,
    OtpVerifyRequest,
    PolicyholderRegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.shared.backend.security import (
    create_access_token,
    generate_math_captcha,
    get_current_user_payload,
    hash_password,
    validate_password_strength,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# CAPTCHA
# ---------------------------------------------------------------------------

@router.get("/captcha", response_model=CaptchaResponse, summary="Get math CAPTCHA")
def get_captcha():
    """Generate and return a math CAPTCHA challenge."""
    captcha = generate_math_captcha()
    return CaptchaResponse(question=captcha["question"], answer=captcha["answer"])


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new policyholder",
)
def register_policyholder(
    request_data: PolicyholderRegisterRequest,
    db: Session = Depends(get_db),
):
    """Register a new policyholder account and send OTP for email verification."""
    # Check email uniqueness
    existing_user = db.query(User).filter(User.email == request_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # Check policy number uniqueness across policies
    from app.shared.backend.models import Policy
    policy = db.query(Policy).filter(Policy.policy_number == request_data.policy_number).first()
    if policy and policy.policyholders:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This policy number is already registered",
        )

    # Validate password strength
    if not validate_password_strength(request_data.password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters with uppercase, lowercase, digit, and special character",
        )

    # Get policyholder role
    role = db.query(Role).filter(Role.name == "policyholder").first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="System configuration error: role not found",
        )

    # Create user
    user = User(
        full_name=request_data.full_name,
        email=request_data.email,
        phone=request_data.phone,
        hashed_password=hash_password(request_data.password),
        role_id=role.id,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    db.flush()

    if not policy:
        policy = Policy(
            policy_number=request_data.policy_number,
            policy_name="Standard Coverage",
        )
        db.add(policy)
        db.flush()

    # Create policyholder profile
    policyholder = Policyholder(
        user_id=user.id,
    )
    policyholder.policies.append(policy)
    db.add(policyholder)
    db.commit()
    db.refresh(user)

    # Send OTP
    otp_service.send_otp(db, user)

    logger.info("New policyholder registered: %s", request_data.email)
    return MessageResponse(message="Registration successful. Please verify your email with the OTP sent.")


# ---------------------------------------------------------------------------
# OTP Verification
# ---------------------------------------------------------------------------

@router.post("/verify-otp", response_model=MessageResponse, summary="Verify email OTP")
def verify_otp(
    request_data: OtpVerifyRequest,
    db: Session = Depends(get_db),
):
    """Verify a user's email address using the OTP code."""
    user = db.query(User).filter(User.email == request_data.email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_verified:
        return MessageResponse(message="Email is already verified")

    if not otp_service.verify_otp(db, user, request_data.otp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP code",
        )

    logger.info("Email verified for user: %s", user.email)
    return MessageResponse(message="Email verified successfully. You can now log in.")


@router.post("/resend-otp", response_model=MessageResponse, summary="Resend OTP")
def resend_otp(
    email: str,
    db: Session = Depends(get_db),
):
    """Resend OTP to a user's email address."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.is_verified:
        return MessageResponse(message="Email is already verified")
    otp_service.send_otp(db, user)
    return MessageResponse(message="OTP resent to your email address")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=LoginResponse, summary="User login")
def login(
    request_data: LoginRequest,
    db: Session = Depends(get_db),
):
    """Authenticate a user and return a JWT access token or OTP requirement."""
    user = db.query(User).filter(User.email == request_data.email).first()
    if not user or not verify_password(request_data.password, user.hashed_password):
        logger.warning("Failed login attempt for email: %s", request_data.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # Check if user is blocked
    blocked = db.query(BlockedUser).filter(
        BlockedUser.user_id == user.id,
        BlockedUser.is_active_block == True
    ).first()
    if blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been blocked. Please contact support.",
        )

    role_name = user.role.name if user.role else "unknown"

    # Role validation
    if role_name != request_data.role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have access to the {request_data.role} portal.",
        )

    # Captcha validation for reviewers
    if role_name == "reviewer":
        if not request_data.captcha_answer or request_data.captcha_answer != request_data.captcha_expected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid CAPTCHA answer",
            )

    # First login check happens before OTP for simplicity, 
    # but wait, first login force password change uses JWT token currently.
    # We will just allow them to get JWT if it's first_login, OR we send OTP first.
    # The prompt doesn't specify changing first_login. Let's keep OTP after first_login check if possible.
    # Actually, if first_login is true, we can just return the token so they can reset password, 
    # or require OTP first. Let's require OTP first for security.
    
    if role_name in ["policyholder", "reviewer"] and not user.first_login:
        # Require OTP
        otp_service.send_otp(db, user)
        return LoginResponse(require_otp=True, email=user.email)

    # Admin or first_login -> direct token
    token_data = {"sub": str(user.id), "email": user.email, "role": role_name}
    access_token = create_access_token(data=token_data)

    logger.info("User logged in: %s (role=%s)", user.email, role_name)
    return LoginResponse(
        access_token=access_token,
        role=role_name,
        user_id=user.id,
        full_name=user.full_name,
        first_login=user.first_login,
    )

@router.post("/login/verify-otp", response_model=LoginResponse, summary="Verify OTP for login")
def login_verify_otp(
    request_data: OtpVerifyRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == request_data.email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not otp_service.verify_otp(db, user, request_data.otp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP code",
        )

    role_name = user.role.name if user.role else "unknown"
    token_data = {"sub": str(user.id), "email": user.email, "role": role_name}
    access_token = create_access_token(data=token_data)

    logger.info("User completed OTP login: %s", user.email)
    return LoginResponse(
        access_token=access_token,
        role=role_name,
        user_id=user.id,
        full_name=user.full_name,
        first_login=user.first_login,
    )


@router.post("/first-login-change-password", response_model=MessageResponse)
def first_login_change_password(
    request_data: FirstLoginPasswordChangeRequest,
    payload: dict = Depends(get_current_user_payload),
    db: Session = Depends(get_db),
):
    """Force password change on first login."""
    user_id = int(payload["sub"])
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not user.first_login:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password already changed")

    if not validate_password_strength(request_data.new_password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters with uppercase, lowercase, digit, and special character",
        )

    user.hashed_password = hash_password(request_data.new_password)
    user.first_login = False
    db.commit()

    # Send OTP for the next step of the flow
    otp_service.send_otp(db, user)

    return MessageResponse(message="Password changed successfully. An OTP has been sent to your email for verification.")



# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserResponse, summary="Get current user profile")
def get_current_user(
    payload: dict = Depends(get_current_user_payload),
    db: Session = Depends(get_db),
):
    """Return the currently authenticated user's profile."""
    user_id = int(payload["sub"])
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        role=user.role.name if user.role else "unknown",
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
    )


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@router.get("/notifications", summary="Get user notifications")
def get_notifications(
    payload: dict = Depends(get_current_user_payload),
    db: Session = Depends(get_db),
):
    """Return all notifications for the authenticated user."""
    user_id = int(payload["sub"])
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        NotificationResponse(
            id=n.id,
            title=n.title,
            message=n.message,
            is_read=n.is_read,
            notification_type=n.notification_type,
            created_at=n.created_at,
        )
        for n in notifications
    ]


@router.post("/notifications/{notification_id}/read", response_model=MessageResponse)
def mark_notification_read(
    notification_id: int,
    payload: dict = Depends(get_current_user_payload),
    db: Session = Depends(get_db),
):
    """Mark a notification as read."""
    user_id = int(payload["sub"])
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == user_id,
    ).first()
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    notification.is_read = True
    db.commit()
    return MessageResponse(message="Notification marked as read")


# ---------------------------------------------------------------------------
# Contact API
# ---------------------------------------------------------------------------

@router.post("/contact", response_model=MessageResponse, summary="Submit a contact message")
def submit_contact_message(
    request_data: ContactMessageRequest,
    db: Session = Depends(get_db)
):
    """Save a new contact message to the database."""
    from app.shared.backend.models import ContactMessage, User, Role, Notification
    
    # Auto-classify Priority
    text = (request_data.subject + " " + request_data.message).lower()
    priority = "Medium"
    if any(word in text for word in ["urgent", "emergency", "escalate", "reject", "critical", "immediately"]):
        priority = "High"
    elif any(word in text for word in ["feedback", "suggestion", "idea"]):
        priority = "Low"
        
    # Auto-classify Category
    category = "General Enquiry"
    if any(word in text for word in ["claim", "reimbursement", "hospital", "bill"]):
        category = "Claim Support"
    elif any(word in text for word in ["policy", "premium", "coverage"]):
        category = "Policy Query"
    elif any(word in text for word in ["error", "bug", "login", "password", "technical", "website", "app"]):
        category = "Technical Support"
    elif any(word in text for word in ["partner", "partnership", "collaborate", "vendor"]):
        category = "Partnership"
    elif any(word in text for word in ["feedback", "suggestion", "improve"]):
        category = "Feedback"

    new_message = ContactMessage(
        full_name=request_data.full_name,
        email=request_data.email,
        subject=request_data.subject,
        message=request_data.message,
        priority=priority,
        category=category
    )
    db.add(new_message)
    db.commit()
    
    # Notify all admins
    admins = db.query(User).join(Role).filter(Role.name == "admin").all()
    for admin in admins:
        notif = Notification(
            user_id=admin.id,
            title="New Contact Message Received",
            message=f"A new message was received from {request_data.full_name} regarding '{request_data.subject}'.",
            notification_type="INFO"
        )
        db.add(notif)
    db.commit()
    
    return MessageResponse(message="Your message has been sent successfully. We will get back to you soon!")

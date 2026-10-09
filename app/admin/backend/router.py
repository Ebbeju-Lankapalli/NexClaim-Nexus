"""
NexClaim Admin Router.

Handles policy document management (with OCR ingestion),
reviewer management, user blocking, escalated claim review,
and analytics dashboard.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.shared.backend.config import settings
from app.shared.backend.database import get_db
from app.shared.backend.models import (
    Admin, AdminDecision, BlockedUser, Claim, ContactMessage, EscalatedClaim,
    ExtractedField, OcrResult, Policy, Policyholder, Reviewer, Role, User
)
from app.shared.backend.notification_service import notification_service
from app.shared.backend.schemas import (
    AdminDecisionRequest,
    BlockUserRequest,
    ContactMessageResponse,
    CreateReviewerRequest,
    CreatePolicyholderRequest,
    MessageResponse,
    PolicyCreateRequest,
    PolicyUpdateRequest,
    ResetPasswordRequest,
    UpdatePolicyholderRequest,
)
from app.shared.backend.security import (
    get_current_user_payload, hash_password, require_role, validate_password_strength
)
from app.ai.ocr.ocr import ocr_processor
from app.ai.extraction.extraction import extractor_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Admin"])

POLICY_UPLOAD_DIR = "app/uploads/policy_repository"
ALLOWED_MIME_TYPES = {
    "application/pdf", "image/jpeg", "image/jpg", "image/png", "image/tiff",
}


def _get_admin(db: Session, payload: dict) -> Admin:
    """Retrieve admin profile for the authenticated admin user."""
    user_id = int(payload["sub"])
    admin = db.query(Admin).filter(Admin.user_id == user_id).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin profile not found",
        )
    return admin


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard", summary="Admin analytics dashboard")
def get_dashboard(
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Return system-wide analytics for admin dashboard."""
    total_claims = db.query(Claim).count()
    total_users = db.query(User).count()
    total_reviewers = db.query(Reviewer).count()
    total_policies = db.query(Policy).count()
    approved = db.query(Claim).filter(Claim.status.in_(["APPROVED", "FINAL_APPROVED"])).count()
    rejected = db.query(Claim).filter(Claim.status.in_(["REJECTED", "FINAL_REJECTED"])).count()
    escalated = db.query(Claim).filter(Claim.status.in_(["ESCALATED", "ADMIN_REVIEW"])).count()
    pending = db.query(Claim).filter(Claim.status.in_(["SUBMITTED", "UNDER_REVIEW", "AI_PROCESSING"])).count()
    approval_rate = round((approved / total_claims * 100), 1) if total_claims > 0 else 0.0
    escalation_rate = round((escalated / total_claims * 100), 1) if total_claims > 0 else 0.0

    recent_claims = (
        db.query(Claim)
        .order_by(Claim.created_at.desc())
        .limit(5)
        .all()
    )

    return {
        "total_claims": total_claims,
        "total_users": total_users,
        "total_reviewers": total_reviewers,
        "total_policies": total_policies,
        "approved_claims": approved,
        "rejected_claims": rejected,
        "escalated_claims": escalated,
        "pending_claims": pending,
        "approval_rate": approval_rate,
        "escalation_rate": escalation_rate,
        "recent_activities": [
            {
                "claim_id": c.id,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in recent_claims
        ],
    }


from app.shared.backend.upload_service import upload_service

# ---------------------------------------------------------------------------
# Policy Repository
# ---------------------------------------------------------------------------

@router.post("/policies/upload", status_code=status.HTTP_201_CREATED, summary="Upload and OCR a policy document")
async def upload_policy_document(
    file: UploadFile = File(...),
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Upload a policy document and extract all fields via OCR automatically.
    """
    admin = _get_admin(db, payload)

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}",
        )

    # Check size
    file_size = getattr(file, 'size', None)
    if file_size is None:
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        file.file.seek(0)
    
    if file_size > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds max size of {settings.MAX_FILE_SIZE_MB}MB",
        )
        
    # Upload to Cloudinary
    logger.info("Uploading policy document to Cloudinary...")
    secure_url, public_id = await upload_service.upload_file(file, folder="nexclaim/policies")
    
    if not secure_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload document to Cloudinary",
        )

    logger.info("Policy uploaded: %s, running OCR...", secure_url)

    # Run OCR on policy document URL
    raw_text, ocr_quality = ocr_processor.extract_text_from_file(secure_url)
    logger.info("Policy OCR complete: %d chars, quality=%.2f", len(raw_text), ocr_quality)

    # Extract structured fields from OCR text
    extracted = extractor_engine.extract(raw_text)
    logger.info("Policy extraction complete: %s", extracted)

    # Parse key extracted fields
    policy_num_val = extracted.get("policy_number", {}).get("value")
    if not policy_num_val:
        policy_num_val = f"AUTO_{uuid.uuid4().hex[:8].upper()}"
        
    policy_name_val = extracted.get("policy_name", {}).get("value", policy_num_val)
    cov_limit_val = extracted.get("coverage_limit", {}).get("value", 0.0)
    wait_period_raw = extracted.get("waiting_period_days", {}).get("value", 0)

    try:
        cov_limit_val = float(cov_limit_val)
    except (ValueError, TypeError):
        cov_limit_val = 0.0
        
    wait_period_val = 0
    if isinstance(wait_period_raw, str):
        wait_period_raw_lower = wait_period_raw.lower()
        import re
        m = re.search(r"(\d+)", wait_period_raw_lower)
        if m:
            val = int(m.group(1))
            if "month" in wait_period_raw_lower:
                val *= 30
            elif "year" in wait_period_raw_lower:
                val *= 365
            wait_period_val = val
    elif isinstance(wait_period_raw, int):
        wait_period_val = wait_period_raw

    # Check for duplicate policy number
    existing = db.query(Policy).filter(Policy.policy_number == policy_num_val).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Policy with number '{policy_num_val}' already exists",
        )

    file_path = secure_url

    # Create policy record in DB
    policy = Policy(
        policy_number=policy_num_val,
        policy_name=policy_name_val,
        coverage_limit=cov_limit_val,
        waiting_period_days=wait_period_val,
        raw_ocr_text=raw_text,
        extracted_fields_json=json.dumps(extracted),
        ocr_quality_score=ocr_quality,
        file_path=file_path,
        admin_id=admin.id,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)

    return {
        "message": "Policy document uploaded and processed successfully",
        "policy_id": policy.id,
        "policy_number": policy_num_val,
        "ocr_quality_score": round(ocr_quality * 100, 1),
        "extracted_fields": extracted,
        "coverage_limit": cov_limit_val,
        "waiting_period_days": wait_period_val,
    }
@router.post("/policies/manual", status_code=status.HTTP_201_CREATED, summary="Create policy manually")
def create_policy_manual(
    policy_data: PolicyCreateRequest,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Create a policy record manually without document upload."""
    admin = _get_admin(db, payload)
    existing = db.query(Policy).filter(Policy.policy_number == policy_data.policy_number).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Policy '{policy_data.policy_number}' already exists",
        )
    policy = Policy(
        policy_number=policy_data.policy_number,
        policy_name=policy_data.policy_name,
        insurer_name=policy_data.insurer_name,
        coverage_limit=policy_data.coverage_limit,
        covered_diseases=json.dumps(policy_data.covered_diseases),
        waiting_period_days=policy_data.waiting_period_days,
        premium_paid_until=policy_data.premium_paid_until,
        is_active=policy_data.is_active,
        admin_id=admin.id,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return {"message": "Policy created", "policy_id": policy.id}


@router.get("/policies", summary="List all policies")
def list_policies(
    page: int = 1,
    page_size: int = 10,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Return paginated list of all policies."""
    total = db.query(Policy).count()
    policies = (
        db.query(Policy)
        .order_by(Policy.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "id": p.id,
                "policy_number": p.policy_number,
                "policy_name": p.policy_name,
                "insurer_name": p.insurer_name,
                "coverage_limit": p.coverage_limit,
                "covered_diseases": p.covered_diseases_list,
                "waiting_period_days": p.waiting_period_days,
                "premium_paid_until": p.premium_paid_until.isoformat() if p.premium_paid_until else None,
                "is_active": p.is_active,
                "ocr_quality_score": p.ocr_quality_score,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in policies
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/policies/{policy_id}/document", summary="Get policy PDF document")
def get_policy_document(
    policy_id: int,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Return the raw PDF document for the policy."""
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy or not policy.file_path:
        raise HTTPException(status_code=404, detail="Policy document not found")
    
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=policy.file_path)


@router.get("/policies/{policy_id}", summary="Get policy details")
def get_policy(
    policy_id: int,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Return full policy details including extracted OCR fields."""
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return {
        "id": policy.id,
        "policy_number": policy.policy_number,
        "policy_name": policy.policy_name,
        "insurer_name": policy.insurer_name,
        "coverage_limit": policy.coverage_limit,
        "covered_diseases": policy.covered_diseases_list,
        "waiting_period_days": policy.waiting_period_days,
        "premium_paid_until": policy.premium_paid_until.isoformat() if policy.premium_paid_until else None,
        "is_active": policy.is_active,
        "ocr_quality_score": policy.ocr_quality_score,
        "raw_ocr_text": policy.raw_ocr_text,
        "extracted_fields": policy.extracted_fields,
        "file_path": policy.file_path,
        "created_at": policy.created_at.isoformat() if policy.created_at else None,
    }


@router.put("/policies/{policy_id}", response_model=MessageResponse, summary="Update policy")
def update_policy(
    policy_id: int,
    update_data: PolicyUpdateRequest,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Update a policy record."""
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")

    if update_data.policy_name is not None:
        policy.policy_name = update_data.policy_name
    if update_data.insurer_name is not None:
        policy.insurer_name = update_data.insurer_name
    if update_data.coverage_limit is not None:
        policy.coverage_limit = update_data.coverage_limit
    if update_data.covered_diseases is not None:
        policy.covered_diseases = json.dumps(update_data.covered_diseases)
    if update_data.waiting_period_days is not None:
        policy.waiting_period_days = update_data.waiting_period_days
    if update_data.premium_paid_until is not None:
        policy.premium_paid_until = update_data.premium_paid_until
    if update_data.is_active is not None:
        policy.is_active = update_data.is_active

    db.commit()
    logger.info("Policy #%d updated", policy_id)
    return MessageResponse(message="Policy updated successfully")


@router.delete("/policies/{policy_id}", response_model=MessageResponse, summary="Delete policy")
def delete_policy(
    policy_id: int,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Permanently delete a policy record."""
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    db.delete(policy)
    db.commit()
    logger.info("Policy #%d deleted", policy_id)
    return MessageResponse(message="Policy deleted successfully")


@router.patch("/policies/{policy_id}/activate", response_model=MessageResponse)
def activate_policy(
    policy_id: int,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Activate a policy."""
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    policy.is_active = True
    db.commit()
    return MessageResponse(message="Policy activated")


@router.patch("/policies/{policy_id}/deactivate", response_model=MessageResponse)
def deactivate_policy(
    policy_id: int,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Deactivate a policy."""
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    policy.is_active = False
    db.commit()
    return MessageResponse(message="Policy deactivated")


# ---------------------------------------------------------------------------
# User Creation Helpers
# ---------------------------------------------------------------------------

import string
import secrets
from app.shared.backend.email_service import EmailService

email_service = EmailService()

def _generate_temp_password(length=12):
    """Generate a complex temporary password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pwd = ''.join(secrets.choice(alphabet) for i in range(length))
        if (any(c.islower() for c in pwd) and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd) and any(c in "!@#$%^&*" for c in pwd)):
            return pwd

# ---------------------------------------------------------------------------
# Reviewer Management
# ---------------------------------------------------------------------------

@router.post("/reviewers", status_code=status.HTTP_201_CREATED, summary="Create reviewer account")
def create_reviewer(
    reviewer_data: CreateReviewerRequest,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    request: Request = None,
):
    """Create a new reviewer account and send welcome email."""
    password = reviewer_data.password or _generate_temp_password()
    
    if not validate_password_strength(password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 chars with uppercase, lowercase, digit, and special char",
        )
    existing = db.query(User).filter(User.email == reviewer_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    reviewer_role = db.query(Role).filter(Role.name == "reviewer").first()
    if not reviewer_role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Reviewer role not found in system",
        )
    user = User(
        full_name=reviewer_data.full_name,
        email=reviewer_data.email,
        phone=reviewer_data.phone,
        hashed_password=hash_password(password),
        role_id=reviewer_role.id,
        is_active=True,
        is_verified=True,  # Admin-created, no OTP needed for initial verification
        first_login=True,
    )
    db.add(user)
    db.flush()
    reviewer = Reviewer(
        user_id=user.id,
        employee_id=reviewer_data.employee_id,
        department=reviewer_data.department,
        is_active=True,
    )
    db.add(reviewer)
    db.commit()
    
    # Send welcome email
    login_url = str(request.base_url) if request else "http://localhost:8000/"
    email_service.send_welcome_email(
        to_email=user.email,
        full_name=user.full_name,
        temp_password=password,
        login_url=login_url
    )
    
    logger.info("Reviewer account created by admin: %s", reviewer_data.email)
    return {"message": "Reviewer account created successfully", "reviewer_id": reviewer.id}

@router.put("/policyholders/{user_id}", response_model=MessageResponse, summary="Update policyholder details")
def update_policyholder(
    user_id: int,
    update_data: UpdatePolicyholderRequest,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Update policyholder details and linked policies."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    ph = getattr(user, 'policyholder', None)
    if not ph:
        raise HTTPException(status_code=400, detail="User is not a policyholder")

    if update_data.full_name is not None:
        user.full_name = update_data.full_name
    if update_data.phone is not None:
        user.phone = update_data.phone

    if update_data.policy_number is not None:
        # We replace existing linked policies with this new one for simplicity
        policy = db.query(Policy).filter(Policy.policy_number == update_data.policy_number).first()
        if not policy:
            raise HTTPException(status_code=404, detail=f"Policy number '{update_data.policy_number}' not found.")
        ph.policies = [policy]

    db.commit()
    return MessageResponse(message="Policyholder updated successfully")

@router.post("/policyholders", status_code=status.HTTP_201_CREATED, summary="Create policyholder account")
def create_policyholder(
    ph_data: CreatePolicyholderRequest,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    request: Request = None,
):
    """Create a new policyholder account and send welcome email."""
    password = ph_data.password or _generate_temp_password()
    
    if not validate_password_strength(password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 chars with uppercase, lowercase, digit, and special char",
        )
    existing = db.query(User).filter(User.email == ph_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    ph_role = db.query(Role).filter(Role.name == "policyholder").first()
    if not ph_role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Policyholder role not found in system",
        )
    user = User(
        full_name=ph_data.full_name,
        email=ph_data.email,
        phone=ph_data.phone,
        hashed_password=hash_password(password),
        role_id=ph_role.id,
        is_active=True,
        is_verified=True,
        first_login=True,
    )
    db.add(user)
    db.flush()
    policyholder = Policyholder(
        user_id=user.id,
    )
    
    if ph_data.policy_number:
        policy = db.query(Policy).filter(Policy.policy_number == ph_data.policy_number).first()
        if not policy:
            # Rollback user creation if policy is invalid
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Policy number '{ph_data.policy_number}' not found. Policyholder not created."
            )
        policyholder.policies.append(policy)

    db.add(policyholder)
    db.commit()
    
    # Send welcome email
    login_url = str(request.base_url) if request else "http://localhost:8000/"
    email_service.send_welcome_email(
        to_email=user.email,
        full_name=user.full_name,
        temp_password=password,
        login_url=login_url
    )
    
    logger.info("Policyholder account created by admin: %s", ph_data.email)
    return {"message": "Policyholder account created successfully", "policyholder_id": policyholder.id}


@router.get("/reviewers", summary="List all reviewers")
def list_reviewers(
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Return all reviewer accounts."""
    reviewers = db.query(Reviewer).all()
    return [
        {
            "id": r.id,
            "full_name": r.user.full_name if r.user else None,
            "email": r.user.email if r.user else None,
            "employee_id": r.employee_id,
            "department": r.department,
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reviewers
    ]


@router.patch("/reviewers/{reviewer_id}/disable", response_model=MessageResponse)
def disable_reviewer(
    reviewer_id: int,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Disable a reviewer account."""
    reviewer = db.query(Reviewer).filter(Reviewer.id == reviewer_id).first()
    if not reviewer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reviewer not found")
    reviewer.is_active = False
    if reviewer.user:
        reviewer.user.is_active = False
    db.commit()
    return MessageResponse(message="Reviewer disabled")


@router.patch("/reviewers/{reviewer_id}/enable", response_model=MessageResponse)
def enable_reviewer(
    reviewer_id: int,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Enable a reviewer account."""
    reviewer = db.query(Reviewer).filter(Reviewer.id == reviewer_id).first()
    if not reviewer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reviewer not found")
    reviewer.is_active = True
    if reviewer.user:
        reviewer.user.is_active = True
    db.commit()
    return MessageResponse(message="Reviewer enabled")


@router.patch("/reviewers/{reviewer_id}/reset-password", response_model=MessageResponse)
def reset_reviewer_password(
    reviewer_id: int,
    reset_data: ResetPasswordRequest,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Reset a reviewer's password."""
    if not validate_password_strength(reset_data.new_password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password does not meet strength requirements",
        )
    reviewer = db.query(Reviewer).filter(Reviewer.id == reviewer_id).first()
    if not reviewer or not reviewer.user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reviewer not found")
    reviewer.user.hashed_password = hash_password(reset_data.new_password)
    db.commit()
    return MessageResponse(message="Reviewer password reset successfully")


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------

@router.get("/users", summary="List all users")
def list_users(
    page: int = 1,
    page_size: int = 20,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Return paginated list of all users."""
    total = db.query(User).count()
    users = (
        db.query(User)
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "phone": u.phone,
                "role": u.role.name if u.role else None,
                "is_active": u.is_active,
                "is_verified": u.is_verified,
                "is_blocked": u.blocked_record.is_active_block if u.blocked_record else False,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "policies": [p.policy_number for p in u.policyholder.policies] if getattr(u, 'policyholder', None) else []
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/users/{user_id}/block", response_model=MessageResponse)
def block_user(
    user_id: int,
    block_data: BlockUserRequest,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Block a user from logging in."""
    admin = _get_admin(db, payload)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing_block = db.query(BlockedUser).filter(
        BlockedUser.user_id == user_id,
        BlockedUser.is_active_block == True,
    ).first()
    if existing_block:
        return MessageResponse(message="User is already blocked")

    block_record = BlockedUser(
        user_id=user_id,
        blocked_by_admin_id=admin.id,
        reason=block_data.reason,
        is_active_block=True,
    )
    db.add(block_record)
    db.commit()
    logger.info("User #%d blocked by admin #%d", user_id, admin.id)
    return MessageResponse(message="User blocked successfully")


@router.post("/users/{user_id}/unblock", response_model=MessageResponse)
def unblock_user(
    user_id: int,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Unblock a previously blocked user."""
    block_record = db.query(BlockedUser).filter(
        BlockedUser.user_id == user_id,
        BlockedUser.is_active_block == True,
    ).first()
    if not block_record:
        return MessageResponse(message="User is not blocked")
    block_record.is_active_block = False
    block_record.unblocked_at = datetime.utcnow()
    db.commit()
    logger.info("User #%d unblocked", user_id)
    return MessageResponse(message="User unblocked successfully")


# ---------------------------------------------------------------------------
# Escalated Claims
# ---------------------------------------------------------------------------

@router.get("/escalated-claims", summary="List escalated claims")
def list_escalated_claims(
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Return all claims currently in ADMIN_REVIEW status."""
    claims = (
        db.query(Claim)
        .filter(Claim.status == "ADMIN_REVIEW")
        .order_by(Claim.updated_at.desc())
        .all()
    )
    return [
        {
            "id": c.id,
            "status": c.status,
            "diagnosis": c.diagnosis,
            "hospital_name": c.hospital_name,
            "claim_amount": c.claim_amount,
            "risk_level": c.risk_score.risk_level if c.risk_score else None,
            "confidence_score": c.recommendation.confidence_score if c.recommendation else None,
            "recommendation": c.recommendation.action if c.recommendation else None,
            "reviewer_comments": c.reviewer_decision.comments if c.reviewer_decision else None,
            "escalated_at": c.escalated_claim.escalated_at.isoformat() if c.escalated_claim else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in claims
    ]


@router.get("/escalated-claims/{claim_id}", summary="Get escalated claim details")
def get_escalated_claim(
    claim_id: int,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Return full details for an escalated claim including AI outputs."""
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    result = {
        "id": claim.id,
        "status": claim.status,
        "diagnosis": claim.diagnosis,
        "hospital_name": claim.hospital_name,
        "admission_date": claim.admission_date.isoformat() if claim.admission_date else None,
        "discharge_date": claim.discharge_date.isoformat() if claim.discharge_date else None,
        "claim_amount": claim.claim_amount,
        "notes": claim.notes,
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
        "documents": [
            {"id": d.id, "doc_type": d.doc_type, "original_filename": d.original_filename}
            for d in claim.documents
        ],
        "validation": None,
        "risk_score": None,
        "recommendation": None,
        "reviewer_decision": None,
        "pre_assessment_brief": None
    }
    
    if claim.ai_extraction_json:
        try:
            brief = json.loads(claim.ai_extraction_json)
            result["brief_data"] = brief
            result["validation"] = brief.get("validation_results", [])
            result["recommendation"] = brief.get("executive_summary", {})
            result["risk_score"] = brief.get("risk_assessment", {})
            result["pre_assessment_brief"] = json.dumps(brief, indent=2)
        except json.JSONDecodeError:
            pass

    if claim.reviewer_decision:
        rd = claim.reviewer_decision
        reviewer_name = rd.reviewer.user.full_name if rd.reviewer and rd.reviewer.user else "Unknown Reviewer"
        result["reviewer_decision"] = {
            "decision": rd.decision,
            "comments": rd.comments,
            "reviewer_name": reviewer_name,
            "decided_at": rd.decided_at.isoformat() if rd.decided_at else None,
        }
    return result


@router.post("/escalated-claims/{claim_id}/decision", response_model=MessageResponse)
def admin_final_decision(
    claim_id: int,
    decision_request: AdminDecisionRequest,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Record admin's final decision on an escalated claim."""
    admin = _get_admin(db, payload)
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    if claim.status != "ADMIN_REVIEW":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Claim is in status '{claim.status}', not ADMIN_REVIEW",
        )

    decision_record = db.query(AdminDecision).filter(AdminDecision.claim_id == claim_id).first()
    if decision_record:
        decision_record.admin_id = admin.id
        decision_record.decision = decision_request.decision
        decision_record.comments = decision_request.comments
    else:
        decision_record = AdminDecision(
            claim_id=claim_id,
            admin_id=admin.id,
            decision=decision_request.decision,
            comments=decision_request.comments,
        )
        db.add(decision_record)

    claim.status = decision_request.decision
    db.commit()

    # Notify policyholder
    if claim.policyholder and claim.policyholder.user:
        friendly_status = "APPROVED" if "APPROVED" in decision_request.decision else "REJECTED"
        notification_service.notify_claim_status(
            db=db,
            user=claim.policyholder.user,
            claim_id=claim_id,
            status=decision_request.decision,
            message=f"Your escalated claim #{claim_id} has received a final decision: {friendly_status}",
            reviewer_comments=decision_request.comments,
            notification_type="SUCCESS" if "APPROVED" in decision_request.decision else "ERROR",
        )

    logger.info(
        "Admin final decision: claim #%d, decision=%s, admin=%d",
        claim_id, decision_request.decision, admin.id
    )
    return MessageResponse(message=f"Final decision '{decision_request.decision}' recorded")


# ---------------------------------------------------------------------------
# All Claims (Admin View)
# ---------------------------------------------------------------------------

@router.get("/claims", summary="Admin: list all claims")
def list_all_claims(
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Return paginated list of all claims with optional status filter."""
    query = db.query(Claim)
    if status_filter:
        query = query.filter(Claim.status == status_filter)
    total = query.count()
    claims = (
        query.order_by(Claim.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "id": c.id,
                "status": c.status,
                "diagnosis": c.diagnosis,
                "hospital_name": c.hospital_name,
                "claim_amount": c.claim_amount,
                "risk_level": c.risk_score.risk_level if c.risk_score else None,
                "policyholder_name": c.policyholder.user.full_name if c.policyholder and c.policyholder.user else "Unknown",
                "reviewer_name": c.reviewer_decision.reviewer.user.full_name if c.reviewer_decision and c.reviewer_decision.reviewer and c.reviewer_decision.reviewer.user else "Pending",
                "reviewer_decision": c.reviewer_decision.decision if c.reviewer_decision else "Pending",
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in claims
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/claims/{claim_id}", summary="Admin: Get full claim details")
def admin_get_claim(
    claim_id: int,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Return full details for a claim including AI outputs and decisions."""
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    result = {
        "id": claim.id,
        "status": claim.status,
        "diagnosis": claim.diagnosis,
        "hospital_name": claim.hospital_name,
        "admission_date": claim.admission_date.isoformat() if claim.admission_date else None,
        "discharge_date": claim.discharge_date.isoformat() if claim.discharge_date else None,
        "claim_amount": claim.claim_amount,
        "policyholder_name": claim.policyholder.user.full_name if claim.policyholder and claim.policyholder.user else "Unknown",
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
        "documents": [
            {"id": d.id, "doc_type": d.doc_type, "original_filename": d.original_filename}
            for d in claim.documents
        ],
        "validation": None,
        "risk_score": None,
        "recommendation": None,
        "reviewer_decision": None,
        "pre_assessment_brief": None
    }
    
    if claim.ai_extraction_json:
        try:
            brief = json.loads(claim.ai_extraction_json)
            result["brief_data"] = brief
            result["validation"] = brief.get("validation_results", [])
            result["recommendation"] = brief.get("executive_summary", {})
            result["risk_score"] = brief.get("risk_assessment", {})
            result["pre_assessment_brief"] = json.dumps(brief, indent=2)
        except json.JSONDecodeError:
            pass

    if claim.reviewer_decision:
        rd = claim.reviewer_decision
        reviewer_name = rd.reviewer.user.full_name if rd.reviewer and rd.reviewer.user else "Unknown Reviewer"
        result["reviewer_decision"] = {
            "decision": rd.decision,
            "comments": rd.comments,
            "reviewer_name": reviewer_name,
            "decided_at": rd.decided_at.isoformat() if rd.decided_at else None,
        }
    return result


@router.post("/claims/{claim_id}/override", response_model=MessageResponse)
def admin_override_decision(
    claim_id: int,
    decision_request: AdminDecisionRequest,
    payload: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Override a claim's status, ignoring reviewer decision."""
    admin = _get_admin(db, payload)
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    decision_record = db.query(AdminDecision).filter(AdminDecision.claim_id == claim_id).first()
    if decision_record:
        decision_record.admin_id = admin.id
        decision_record.decision = decision_request.decision
        decision_record.comments = decision_request.comments or decision_record.comments
    else:
        decision_record = AdminDecision(
            claim_id=claim_id,
            admin_id=admin.id,
            decision=decision_request.decision,
            comments=decision_request.comments or "Admin forcefully overridden decision.",
        )
        db.add(decision_record)

    claim.status = decision_request.decision
    db.commit()

    # Notify policyholder
    if claim.policyholder and claim.policyholder.user:
        friendly_status = "APPROVED" if "APPROVED" in decision_request.decision else "REJECTED"
        notification_service.notify_claim_status(
            db=db,
            user=claim.policyholder.user,
            claim_id=claim_id,
            status=decision_request.decision,
            message=f"Your claim #{claim_id} has been overridden and received a final decision: {friendly_status}",
            reviewer_comments=decision_request.comments or "Admin forceful override.",
            notification_type="SUCCESS" if "APPROVED" in decision_request.decision else "ERROR",
        )

    logger.info("Admin override decision: claim #%d, decision=%s, admin=%d", claim_id, decision_request.decision, admin.id)
    return MessageResponse(message=f"Claim forcefully overridden to '{decision_request.decision}'")


# ---------------------------------------------------------------------------
# Contact Messages Management
# ---------------------------------------------------------------------------

from app.shared.backend.schemas import ContactMessageUpdateRequest
from sqlalchemy import or_, desc, asc

@router.get("/contact-messages/stats", summary="Get contact message statistics")
def get_contact_message_stats(
    db: Session = Depends(get_db),
    payload: dict = Depends(require_role("admin"))
):
    from datetime import datetime, timedelta
    today = datetime.utcnow().date()
    
    total = db.query(ContactMessage).count()
    unread = db.query(ContactMessage).filter(ContactMessage.is_read == False).count()
    resolved = db.query(ContactMessage).filter(ContactMessage.status == "Resolved").count()
    
    today_count = db.query(ContactMessage).filter(
        ContactMessage.created_at >= datetime(today.year, today.month, today.day)
    ).count()
    
    # Category Stats
    claim_support = db.query(ContactMessage).filter(ContactMessage.category == "Claim Support").count()
    tech_support = db.query(ContactMessage).filter(ContactMessage.category == "Technical Support").count()
    policy_queries = db.query(ContactMessage).filter(ContactMessage.category == "Policy Query").count()
    partnership = db.query(ContactMessage).filter(ContactMessage.category == "Partnership").count()
    feedback = db.query(ContactMessage).filter(ContactMessage.category == "Feedback").count()
    
    return {
        "total": total,
        "unread": unread,
        "resolved": resolved,
        "today": today_count,
        "categories": {
            "claim": claim_support,
            "technical": tech_support,
            "policy": policy_queries,
            "partnership": partnership,
            "feedback": feedback
        }
    }

@router.get("/contact-messages", response_model=list[ContactMessageResponse], summary="List all contact messages")
def get_contact_messages(
    db: Session = Depends(get_db),
    payload: dict = Depends(require_role("admin"))
):
    """Retrieve all contact messages."""
    messages = db.query(ContactMessage).order_by(ContactMessage.created_at.desc()).all()
    return messages

@router.patch("/contact-messages/{message_id}", response_model=ContactMessageResponse, summary="Update contact message")
def update_contact_message(
    message_id: int,
    request_data: ContactMessageUpdateRequest,
    db: Session = Depends(get_db),
    payload: dict = Depends(require_role("admin"))
):
    message = db.query(ContactMessage).filter(ContactMessage.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
        
    if request_data.status is not None:
        message.status = request_data.status
    if request_data.priority is not None:
        message.priority = request_data.priority
    if request_data.category is not None:
        message.category = request_data.category
    if request_data.admin_notes is not None:
        message.admin_notes = request_data.admin_notes
    if request_data.is_read is not None:
        message.is_read = request_data.is_read
        
    db.commit()
    db.refresh(message)
    return message

@router.delete("/contact-messages/{message_id}", summary="Delete contact message")
def delete_contact_message(
    message_id: int,
    db: Session = Depends(get_db),
    payload: dict = Depends(require_role("admin"))
):
    from app.shared.backend.models import ContactMessage
    message = db.query(ContactMessage).filter(ContactMessage.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    db.delete(message)
    db.commit()
    return {"message": "Contact message deleted successfully."}

@router.get("/contact-messages/export", summary="Export contact messages as CSV")
def export_contact_messages(
    db: Session = Depends(get_db),
    payload: dict = Depends(require_role("admin"))
):
    import io
    import csv
    from fastapi.responses import StreamingResponse
    
    messages = db.query(ContactMessage).order_by(ContactMessage.created_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Email", "Subject", "Message", "Date", "Status", "Priority", "Category", "Admin Notes"])
    
    for msg in messages:
        writer.writerow([
            msg.id,
            msg.full_name,
            msg.email,
            msg.subject,
            msg.message,
            msg.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            msg.status,
            msg.priority or "Medium",
            msg.category or "General Enquiry",
            msg.admin_notes or ""
        ])
        
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=contact_messages.csv"
    return response

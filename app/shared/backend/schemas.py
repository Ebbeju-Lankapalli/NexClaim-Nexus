"""
NexClaim Pydantic Schemas.

Defines all request and response models for API endpoints.
"""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Auth / User Schemas
# ---------------------------------------------------------------------------




class PolicyholderRegisterRequest(BaseModel):
    """Registration request for a new policyholder."""
    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=20)
    policy_number: str = Field(..., min_length=5, max_length=100)
    policy_pin: str = Field(..., min_length=4, max_length=20)
    password: str = Field(..., min_length=8)
    captcha_answer: int
    captcha_expected: int

    @field_validator("captcha_answer")
    @classmethod
    def validate_captcha(cls, v: int, info) -> int:
        expected = info.data.get("captcha_expected")
        if expected is not None and v != expected:
            raise ValueError("CAPTCHA answer is incorrect")
        return v

class LoginRequest(BaseModel):
    """Login request with email, password, role, and optional captcha."""
    email: EmailStr
    password: str
    role: str = Field(default="policyholder")
    captcha_answer: Optional[str] = None
    captcha_expected: Optional[str] = None

class LoginResponse(BaseModel):
    """Login response returning either a token or requiring OTP."""
    require_otp: bool = False
    email: Optional[str] = None
    access_token: Optional[str] = None
    token_type: str = "bearer"
    role: Optional[str] = None
    user_id: Optional[int] = None
    full_name: Optional[str] = None
    first_login: Optional[bool] = None

class OtpVerifyRequest(BaseModel):
    """OTP verification request."""
    email: EmailStr
    otp_code: str = Field(..., min_length=6, max_length=6)


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: int
    full_name: str
    first_login: bool = False


class UserResponse(BaseModel):
    """Public user profile response."""
    id: int
    full_name: str
    email: str
    phone: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CaptchaResponse(BaseModel):
    """Math CAPTCHA challenge."""
    question: str
    answer: int  # Returned for dev/testing; in prod, validate server-side


# ---------------------------------------------------------------------------
# Policy Schemas
# ---------------------------------------------------------------------------

class PolicyCreateRequest(BaseModel):
    """Manual policy creation request (fields overridden by OCR if doc uploaded)."""
    policy_number: str = Field(..., min_length=5, max_length=100)
    policy_name: str = Field(..., min_length=2, max_length=255)
    insurer_name: Optional[str] = None
    coverage_limit: float = Field(..., ge=0)
    covered_diseases: List[str] = Field(default_factory=list)
    waiting_period_days: int = Field(default=0, ge=0)
    premium_paid_until: Optional[datetime] = None
    is_active: bool = True


class PolicyUpdateRequest(BaseModel):
    """Policy update request."""
    policy_name: Optional[str] = None
    insurer_name: Optional[str] = None
    coverage_limit: Optional[float] = Field(default=None, ge=0)
    covered_diseases: Optional[List[str]] = None
    waiting_period_days: Optional[int] = Field(default=None, ge=0)
    premium_paid_until: Optional[datetime] = None
    is_active: Optional[bool] = None


class PolicyResponse(BaseModel):
    """Policy record response."""
    id: int
    policy_number: str
    policy_name: str
    insurer_name: Optional[str] = None
    coverage_limit: float
    covered_diseases: List[str] = []
    waiting_period_days: int
    premium_paid_until: Optional[datetime] = None
    is_active: bool
    ocr_quality_score: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Claim Schemas
# ---------------------------------------------------------------------------

class ClaimSubmitRequest(BaseModel):
    """Claim submission metadata (documents uploaded separately)."""
    notes: Optional[str] = Field(default=None, max_length=1000)


class ClaimStatusUpdate(BaseModel):
    """Internal claim status update."""
    status: str


class ClaimDocumentResponse(BaseModel):
    """Uploaded claim document info."""
    id: int
    doc_type: str
    original_filename: str
    file_size_bytes: int
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class ClaimResponse(BaseModel):
    """Full claim record response."""
    id: int
    status: str
    diagnosis: Optional[str] = None
    hospital_name: Optional[str] = None
    admission_date: Optional[datetime] = None
    discharge_date: Optional[datetime] = None
    claim_amount: float
    extracted_policy_number: Optional[str] = None
    extracted_patient_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    documents: List[ClaimDocumentResponse] = []

    model_config = {"from_attributes": True}


class ValidationResultResponse(BaseModel):
    """Policy validation result response."""
    is_policy_active: bool
    is_premium_paid: bool
    is_disease_covered: bool
    is_within_limit: bool
    is_waiting_period_met: bool
    report_json: str

    model_config = {"from_attributes": True}


class RiskScoreResponse(BaseModel):
    """Risk score response."""
    risk_level: str
    probability: float
    features_json: str

    model_config = {"from_attributes": True}


class RecommendationResponse(BaseModel):
    """AI recommendation response."""
    action: str
    confidence_score: float
    reasons_json: str
    explanation: Optional[str] = None
    pre_assessment_brief: Optional[str] = None

    model_config = {"from_attributes": True}


class ClaimFullDetailResponse(BaseModel):
    """Complete claim details for reviewer/admin."""
    claim: ClaimResponse
    validation: Optional[ValidationResultResponse] = None
    risk_score: Optional[RiskScoreResponse] = None
    recommendation: Optional[RecommendationResponse] = None
    reviewer_decision: Optional[dict] = None
    admin_decision: Optional[dict] = None


# ---------------------------------------------------------------------------
# Reviewer Decision Schemas
# ---------------------------------------------------------------------------

class ReviewerDecisionRequest(BaseModel):
    """Reviewer approve/reject/escalate request."""
    decision: str = Field(..., pattern="^(APPROVED|REJECTED|ESCALATED)$")
    comments: Optional[str] = Field(default=None, max_length=2000)


class AdminDecisionRequest(BaseModel):
    """Admin final decision request for escalated claims."""
    decision: str = Field(..., pattern="^(FINAL_APPROVED|FINAL_REJECTED)$")
    comments: Optional[str] = Field(default=None, max_length=2000)


class FirstLoginPasswordChangeRequest(BaseModel):
    """Force password change request on first login."""
    new_password: str = Field(..., min_length=8)

# ---------------------------------------------------------------------------
# Admin Management Schemas
# ---------------------------------------------------------------------------

class CreateReviewerRequest(BaseModel):
    """Admin request to create a new reviewer account."""
    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=20)
    employee_id: Optional[str] = Field(default=None, max_length=50)
    department: Optional[str] = Field(default=None, max_length=100)
    password: Optional[str] = None # Admin can specify or system generates


class CreatePolicyholderRequest(BaseModel):
    """Admin request to create a new policyholder account."""
    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=20)
    password: Optional[str] = None # Admin can specify or system generates
    policy_number: Optional[str] = None # Admin can link a policy at creation


class UpdatePolicyholderRequest(BaseModel):
    """Admin request to update an existing policyholder."""
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    phone: Optional[str] = Field(default=None, min_length=10, max_length=20)
    policy_number: Optional[str] = None



class ResetPasswordRequest(BaseModel):
    """Admin request to reset a user's password."""
    new_password: str = Field(..., min_length=8)


class BlockUserRequest(BaseModel):
    """Admin request to block a user."""
    reason: Optional[str] = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# Notification Schemas
# ---------------------------------------------------------------------------

class NotificationResponse(BaseModel):
    """Notification record response."""
    id: int
    title: str
    message: str
    is_read: bool
    notification_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Generic / Utility Schemas
# ---------------------------------------------------------------------------

class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True


class PaginatedResponse(BaseModel):
    """Paginated list response wrapper."""
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------------------------------------------------------------------------
# Contact Messages
# ---------------------------------------------------------------------------

class ContactMessageRequest(BaseModel):
    full_name: str
    email: EmailStr
    subject: str
    message: str


class ContactMessageResponse(ContactMessageRequest):
    id: int
    is_read: bool
    status: str
    priority: Optional[str] = None
    category: Optional[str] = None
    admin_notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ContactMessageUpdateRequest(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    admin_notes: Optional[str] = None
    is_read: Optional[bool] = None


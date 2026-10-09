"""
NexClaim SQLAlchemy ORM Models.

Defines the complete relational database schema with proper
foreign-key relationships, indexes, and constraints.
"""

import json
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, Index, Table
)
from sqlalchemy.orm import relationship

from app.shared.backend.database import Base


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------

class Role(Base):
    """System roles: policyholder, reviewer, admin."""

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)

    users = relationship("User", back_populates="role")


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base):
    """Core user account shared by all roles."""

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_email", "email"),
    )

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(20), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    first_login = Column(Boolean, default=True)
    otp_code = Column(String(10), nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    role = relationship("Role", back_populates="users")
    policyholder = relationship("Policyholder", back_populates="user", uselist=False)
    reviewer = relationship("Reviewer", back_populates="user", uselist=False)
    admin = relationship("Admin", back_populates="user", uselist=False)
    notifications = relationship("Notification", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")
    blocked_record = relationship("BlockedUser", back_populates="user", uselist=False)


# ---------------------------------------------------------------------------
# Policyholder & Policies Relationship
# ---------------------------------------------------------------------------

policyholder_policies = Table(
    'policyholder_policies',
    Base.metadata,
    Column('policyholder_id', Integer, ForeignKey('policyholders.id', ondelete='CASCADE'), primary_key=True),
    Column('policy_id', Integer, ForeignKey('policies.id', ondelete='CASCADE'), primary_key=True)
)

# ---------------------------------------------------------------------------
# Policyholder
# ---------------------------------------------------------------------------

class Policyholder(Base):
    """Policyholder profile linked to a User account."""

    __tablename__ = "policyholders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="policyholder")
    claims = relationship("Claim", back_populates="policyholder")
    policies = relationship("Policy", secondary=policyholder_policies, back_populates="policyholders")


# ---------------------------------------------------------------------------
# Reviewer
# ---------------------------------------------------------------------------

class Reviewer(Base):
    """Reviewer profile — created only by Admin."""

    __tablename__ = "reviewers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    employee_id = Column(String(50), unique=True, nullable=True)
    department = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="reviewer")
    decisions = relationship("ReviewerDecision", back_populates="reviewer")
    escalated_claims = relationship("EscalatedClaim", back_populates="reviewer")


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class Admin(Base):
    """Admin profile."""

    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="admin")
    policies = relationship("Policy", back_populates="created_by_admin")
    decisions = relationship("AdminDecision", back_populates="admin")
    blocked_users = relationship("BlockedUser", back_populates="blocked_by_admin")


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

class Policy(Base):
    """
    Insurance policy document.

    When admin uploads a policy PDF/image, OCR is run once and all
    extracted fields are stored here for fast claim validation.
    """

    __tablename__ = "policies"

    id = Column(Integer, primary_key=True, index=True)
    policy_number = Column(String(100), unique=True, nullable=False)
    policy_name = Column(String(255), nullable=False)
    insurer_name = Column(String(255), nullable=True)
    coverage_limit = Column(Float, default=0.0)
    # JSON list of covered disease names
    covered_diseases = Column(Text, default="[]")  # JSON
    waiting_period_days = Column(Integer, default=0)
    premium_paid_until = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    # Raw OCR text extracted from policy document
    raw_ocr_text = Column(Text, nullable=True)
    # All extracted fields as JSON
    extracted_fields_json = Column(Text, default="{}")
    file_path = Column(String(500), nullable=True)
    ocr_quality_score = Column(Float, default=0.0)
    admin_id = Column(Integer, ForeignKey("admins.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by_admin = relationship("Admin", back_populates="policies")
    claims = relationship("Claim", back_populates="policy")
    policyholders = relationship("Policyholder", secondary=policyholder_policies, back_populates="policies")

    @property
    def covered_diseases_list(self) -> list:
        """Return covered diseases as a Python list."""
        try:
            return json.loads(self.covered_diseases or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    @property
    def extracted_fields(self) -> dict:
        """Return extracted fields as a Python dict."""
        try:
            return json.loads(self.extracted_fields_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------

class Claim(Base):
    """Insurance claim submitted by a policyholder."""

    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, index=True)
    claim_number = Column(String(50), unique=True, index=True, nullable=True)  # CLM-2026-00001
    policyholder_id = Column(Integer, ForeignKey("policyholders.id"), nullable=False)
    policy_id = Column(Integer, ForeignKey("policies.id"), nullable=True)
    status = Column(String(50), default="SUBMITTED")  # SUBMITTED, AI_PROCESSING, UNDER_REVIEW, APPROVED, REJECTED, ESCALATED, ADMIN_REVIEW
    diagnosis = Column(String(255), nullable=True)
    hospital_name = Column(String(255), nullable=True)
    admission_date = Column(DateTime, nullable=True)
    discharge_date = Column(DateTime, nullable=True)
    claim_amount = Column(Float, default=0.0)
    extracted_policy_number = Column(String(100), nullable=True)
    extracted_patient_name = Column(String(150), nullable=True)
    ai_extraction_json = Column(Text, default="{}")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    policyholder = relationship("Policyholder", back_populates="claims")
    policy = relationship("Policy", back_populates="claims")
    documents = relationship("ClaimDocument", back_populates="claim")
    ocr_results = relationship("OcrResult", back_populates="claim")
    validation_result = relationship("ValidationResult", back_populates="claim", uselist=False)
    risk_score = relationship("RiskScore", back_populates="claim", uselist=False)
    recommendation = relationship("Recommendation", back_populates="claim", uselist=False)
    reviewer_decision = relationship("ReviewerDecision", back_populates="claim", uselist=False)
    admin_decision = relationship("AdminDecision", back_populates="claim", uselist=False)
    escalated_claim = relationship("EscalatedClaim", back_populates="claim", uselist=False)


# ---------------------------------------------------------------------------
# Claim Document
# ---------------------------------------------------------------------------

class ClaimDocument(Base):
    """Uploaded document associated with a claim."""

    __tablename__ = "claim_documents"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    doc_type = Column(String(100), nullable=False)  # HOSPITAL_BILL, DISCHARGE_SUMMARY, PRESCRIPTION, etc.
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    mime_type = Column(String(100), nullable=True)
    file_size_bytes = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    claim = relationship("Claim", back_populates="documents")
    ocr_result = relationship("OcrResult", back_populates="document", uselist=False)


# ---------------------------------------------------------------------------
# OCR Result
# ---------------------------------------------------------------------------

class OcrResult(Base):
    """Raw OCR output for a claim document or policy document."""

    __tablename__ = "ocr_results"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=True)
    document_id = Column(Integer, ForeignKey("claim_documents.id"), nullable=True)
    source_type = Column(String(50), nullable=False)  # "policy" or "claim_document"
    raw_text = Column(Text, nullable=True)
    ocr_quality_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    claim = relationship("Claim", back_populates="ocr_results")
    document = relationship("ClaimDocument", back_populates="ocr_result")
    extracted_fields = relationship("ExtractedField", back_populates="ocr_result")


# ---------------------------------------------------------------------------
# Extracted Field
# ---------------------------------------------------------------------------

class ExtractedField(Base):
    """Individual field extracted from an OCR result."""

    __tablename__ = "extracted_fields"

    id = Column(Integer, primary_key=True, index=True)
    ocr_result_id = Column(Integer, ForeignKey("ocr_results.id"), nullable=False)
    field_name = Column(String(100), nullable=False)
    field_value = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)

    ocr_result = relationship("OcrResult", back_populates="extracted_fields")


# ---------------------------------------------------------------------------
# Validation Result
# ---------------------------------------------------------------------------

class ValidationResult(Base):
    """Policy validation outcome for a claim."""

    __tablename__ = "validation_results"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), unique=True, nullable=False)
    is_policy_active = Column(Boolean, default=False)
    is_premium_paid = Column(Boolean, default=False)
    is_disease_covered = Column(Boolean, default=False)
    is_within_limit = Column(Boolean, default=False)
    is_waiting_period_met = Column(Boolean, default=False)
    report_json = Column(Text, default="{}")  # Full detailed report
    created_at = Column(DateTime, default=datetime.utcnow)

    claim = relationship("Claim", back_populates="validation_result")


# ---------------------------------------------------------------------------
# Risk Score
# ---------------------------------------------------------------------------

class RiskScore(Base):
    """Logistic regression risk assessment for a claim."""

    __tablename__ = "risk_scores"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), unique=True, nullable=False)
    risk_level = Column(String(20), nullable=False)  # LOW, MEDIUM, HIGH
    probability = Column(Float, default=0.0)
    features_json = Column(Text, default="{}")  # Feature vector used
    created_at = Column(DateTime, default=datetime.utcnow)

    claim = relationship("Claim", back_populates="risk_score")


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------

class Recommendation(Base):
    """AI recommendation for a claim (APPROVE / REJECT / ESCALATE)."""

    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), unique=True, nullable=False)
    action = Column(String(50), nullable=False)  # APPROVE_RECOMMENDATION, REJECT_RECOMMENDATION, ESCALATE
    confidence_score = Column(Float, default=0.0)
    reasons_json = Column(Text, default="[]")  # JSON list of reason strings
    explanation = Column(Text, nullable=True)
    pre_assessment_brief = Column(Text, nullable=True)  # Full reviewer-ready brief
    created_at = Column(DateTime, default=datetime.utcnow)

    claim = relationship("Claim", back_populates="recommendation")


# ---------------------------------------------------------------------------
# Reviewer Decision
# ---------------------------------------------------------------------------

class ReviewerDecision(Base):
    """Decision recorded by a reviewer for a claim."""

    __tablename__ = "reviewer_decisions"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), unique=True, nullable=False)
    reviewer_id = Column(Integer, ForeignKey("reviewers.id"), nullable=False)
    decision = Column(String(50), nullable=False)  # APPROVED, REJECTED, ESCALATED
    comments = Column(Text, nullable=True)
    decided_at = Column(DateTime, default=datetime.utcnow)

    claim = relationship("Claim", back_populates="reviewer_decision")
    reviewer = relationship("Reviewer", back_populates="decisions")


# ---------------------------------------------------------------------------
# Admin Decision
# ---------------------------------------------------------------------------

class AdminDecision(Base):
    """Final decision recorded by admin for escalated claims."""

    __tablename__ = "admin_decisions"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), unique=True, nullable=False)
    admin_id = Column(Integer, ForeignKey("admins.id"), nullable=False)
    decision = Column(String(50), nullable=False)  # FINAL_APPROVED, FINAL_REJECTED
    comments = Column(Text, nullable=True)
    decided_at = Column(DateTime, default=datetime.utcnow)

    claim = relationship("Claim", back_populates="admin_decision")
    admin = relationship("Admin", back_populates="decisions")


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------

class Notification(Base):
    """In-app and email notification for users."""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    notification_type = Column(String(50), default="INFO")  # INFO, SUCCESS, WARNING, ERROR
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

class AuditLog(Base):
    """Immutable audit trail for all significant user actions."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    resource = Column(String(100), nullable=True)
    details_json = Column(Text, default="{}")
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audit_logs")


# ---------------------------------------------------------------------------
# Blocked User
# ---------------------------------------------------------------------------

class BlockedUser(Base):
    """Record of users blocked by an admin."""

    __tablename__ = "blocked_users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    blocked_by_admin_id = Column(Integer, ForeignKey("admins.id"), nullable=True)
    reason = Column(Text, nullable=True)
    blocked_at = Column(DateTime, default=datetime.utcnow)
    unblocked_at = Column(DateTime, nullable=True)
    is_active_block = Column(Boolean, default=True)

    user = relationship("User", back_populates="blocked_record")
    blocked_by_admin = relationship("Admin", back_populates="blocked_users")


# ---------------------------------------------------------------------------
# Escalated Claim
# ---------------------------------------------------------------------------

class EscalatedClaim(Base):
    """Record of a claim escalated from reviewer to admin."""

    __tablename__ = "escalated_claims"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), unique=True, nullable=False)
    reviewer_id = Column(Integer, ForeignKey("reviewers.id"), nullable=False)
    reason = Column(Text, nullable=True)
    escalated_at = Column(DateTime, default=datetime.utcnow)

    claim = relationship("Claim", back_populates="escalated_claim")
    reviewer = relationship("Reviewer", back_populates="escalated_claims")


# ---------------------------------------------------------------------------
# Contact Message
# ---------------------------------------------------------------------------

class ContactMessage(Base):
    """Message submitted from the Contact Us page."""

    __tablename__ = "contact_messages"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(50), default="NEW")
    priority = Column(String(50), default="Medium")
    category = Column(String(50), default="General Enquiry")
    admin_notes = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

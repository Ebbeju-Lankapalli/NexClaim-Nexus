"""
NexClaim Policyholder Router.

Handles claim submission (with file uploads and AI processing),
claim tracking, and result viewing for authenticated policyholders.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session

from app.shared.backend.config import settings
from app.shared.backend.database import get_db
from app.shared.backend.models import (
    Admin, Claim, ClaimDocument, EscalatedClaim, ExtractedField,
    Notification, OcrResult, Policy, Policyholder, Recommendation,
    ReviewerDecision, RiskScore, Reviewer, User, ValidationResult,
)
from app.shared.backend.notification_service import notification_service
from app.shared.backend.upload_service import upload_service
from app.shared.backend.schemas import (
    ClaimFullDetailResponse, ClaimResponse, MessageResponse, RecommendationResponse,
    RiskScoreResponse, ValidationResultResponse,
)
from app.shared.backend.security import get_current_user_payload, require_role
from app.ai.ocr.ocr import ocr_processor
from app.ai.pipeline import ai_pipeline
from app.ai.policy_validation.policy_validation import policy_validator
from app.ai.risk_scoring.risk_scoring import risk_scorer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/policyholder", tags=["Policyholder"])

UPLOAD_DIR = "app/uploads/claims"
VALID_DOC_TYPES = {
    "hospital_bill", "discharge_summary", "prescription",
    "medical_report", "claim_form", "other"
}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg", "image/jpg", "image/png", "image/tiff",
}


def _get_policyholder(db: Session, payload: dict) -> Policyholder:
    """Retrieve policyholder profile for the authenticated user."""
    user_id = int(payload["sub"])
    policyholder = db.query(Policyholder).filter(Policyholder.user_id == user_id).first()
    if not policyholder:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Policyholder profile not found",
        )
    return policyholder


def _validate_upload_file(file: UploadFile) -> None:
    """Validate uploaded file MIME type and size."""
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{file.content_type}' is not allowed. Accepted: PDF, JPEG, PNG, TIFF",
        )



def _run_ai_pipeline(
    db: Session, claim: Claim, documents: List[ClaimDocument]
) -> None:
    """Execute the complete AI processing pipeline for a claim."""
    claim.status = "AI_PROCESSING"
    db.commit()

    file_paths = [doc.file_path for doc in documents]
    
    # Step 1: Extraction
    extracted_data = ai_pipeline.extract(file_paths)
    
    # Save extraction json temporarily
    extracted_data["submitted_docs"] = [doc.doc_type for doc in documents]
    claim.ai_extraction_json = json.dumps(extracted_data)
    
    claim_data = extracted_data.get("claim_data", {})
    hospital_data = extracted_data.get("hospital_data", {})
    policy_data = extracted_data.get("policy_data", {})
    financial_data = extracted_data.get("financial_data", {})
    
    if "patient_name" in claim_data:
        claim.extracted_patient_name = claim_data["patient_name"].get("value")
    if "diagnosis" in claim_data:
        claim.diagnosis = claim_data["diagnosis"].get("value")
    if "hospital_name" in hospital_data:
        claim.hospital_name = hospital_data["hospital_name"].get("value")
    from datetime import datetime
    def safe_parse_date(date_str):
        if not date_str or not isinstance(date_str, str):
            return None
        # Try some common formats or just return None if messy OCR
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%B %d, %Y', '%m/%d/%Y'):
            try:
                return datetime.strptime(date_str.strip()[:10], fmt)
            except ValueError:
                pass
        return None

    if "admission_date" in hospital_data:
        claim.admission_date = safe_parse_date(hospital_data["admission_date"].get("value"))
    if "discharge_date" in hospital_data:
        claim.discharge_date = safe_parse_date(hospital_data["discharge_date"].get("value"))
    if "claim_amount" in financial_data:
        try:
            claim.claim_amount = float(financial_data["claim_amount"].get("value", 0.0))
        except (ValueError, TypeError):
            claim.claim_amount = 0.0
    if "policy_number" in policy_data:
        claim.extracted_policy_number = policy_data["policy_number"].get("value")

    db.commit()

    # Step 2: Find Policy
    policy = None
    if claim.extracted_policy_number:
        policy = db.query(Policy).filter(Policy.policy_number == claim.extracted_policy_number).first()
    if not policy and claim.policyholder:
        ph = claim.policyholder
        if ph.policies:
            policy = ph.policies[0]
    
    if policy:
        claim.policy_id = policy.id
        db.commit()

    # Step 3: Run Full Assessment (Validation, Risk, Confidence, Explainability)
    dss_brief = ai_pipeline.assess(claim, extracted_data, policy, required_docs_count=2)
    
    # Store the complete Pre-Assessment Brief in ai_extraction_json
    claim.ai_extraction_json = json.dumps(dss_brief)
    
    # Also populate legacy SQL tables for Dashboard UI compatibility
    engine_output = dss_brief.get("engine_output", {})
    legacy_val = {r["rule"]: r["status"] for r in engine_output.get("validation_results", [])}
    
    # Delete existing records to allow re-runs
    db.query(ValidationResult).filter(ValidationResult.claim_id == claim.id).delete()
    db.query(RiskScore).filter(RiskScore.claim_id == claim.id).delete()
    db.query(Recommendation).filter(Recommendation.claim_id == claim.id).delete()
    
    validation_record = ValidationResult(
        claim_id=claim.id,
        is_policy_active=legacy_val.get("policy_active") == "PASS",
        is_premium_paid=legacy_val.get("premium_status") == "PASS",
        is_disease_covered=legacy_val.get("disease_coverage") == "PASS",
        is_within_limit=legacy_val.get("coverage_amount") == "PASS",
        is_waiting_period_met=legacy_val.get("waiting_period") == "PASS",
        report_json=json.dumps(engine_output.get("validation_results", []))
    )
    db.add(validation_record)
    
    risk_data = dss_brief.get("risk_assessment", {})
    risk_score = RiskScore(
        claim_id=claim.id,
        probability=risk_data.get("probability", 0.0),
        features_json=json.dumps(risk_data.get("risk_factors", [])),
        risk_level=risk_data.get("category", "UNKNOWN")
    )
    db.add(risk_score)
    
    rec_data = dss_brief.get("executive_summary", {})
    action_val = rec_data.get("recommendation", "ESCALATE")
    recommendation = Recommendation(
        claim_id=claim.id,
        action=action_val,
        reasons_json=json.dumps(rec_data.get("primary_reasons", [])),
        confidence_score=rec_data.get("confidence_score", 0.0)
    )
    db.add(recommendation)
    
    # Finalize status
    if action_val == "APPROVE_RECOMMENDATION":
        claim.status = "APPROVED"
    elif action_val == "REJECT_RECOMMENDATION":
        claim.status = "REJECTED"
    else:
        claim.status = "UNDER_REVIEW"
        
    db.commit()
    logger.info("AI pipeline complete for claim #%d: action=%s", claim.id, action_val)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard", summary="Policyholder dashboard summary")
def get_dashboard(
    payload: dict = Depends(require_role("policyholder")),
    db: Session = Depends(get_db),
):
    """Return dashboard summary for authenticated policyholder."""
    policyholder = _get_policyholder(db, payload)
    claims = db.query(Claim).filter(Claim.policyholder_id == policyholder.id).all()
    status_counts = {}
    for claim in claims:
        status_counts[claim.status] = status_counts.get(claim.status, 0) + 1
    notifications = (
        db.query(Notification)
        .filter(
            Notification.user_id == policyholder.user_id,
            Notification.is_read == False,
        )
        .count()
    )
    recent_claims_db = (
        db.query(Claim)
        .filter(Claim.policyholder_id == policyholder.id)
        .order_by(Claim.created_at.desc())
        .limit(5)
        .all()
    )

    def _get_reason(c: Claim) -> str:
        if c.admin_decision and c.admin_decision.comments:
            return c.admin_decision.comments
        if c.reviewer_decision and c.reviewer_decision.comments:
            return c.reviewer_decision.comments
        
        if c.status == "APPROVED":
            return "Your claim has been successfully approved."
        elif c.status == "REJECTED":
            if c.recommendation:
                try:
                    reasons = json.loads(c.recommendation.reasons_json or "[]")
                    for reason in reasons:
                        if "missing" in reason.lower():
                            return reason
                except: pass
            return "Claim rejected. Please contact support."
        else:
            return "Your claim is currently under manual review."

    recent_claims = [{
        "id": c.id,
        "status": c.status,
        "diagnosis": c.diagnosis,
        "claim_amount": c.claim_amount,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "reason": _get_reason(c)
    } for c in recent_claims_db]

    return {
        "total_claims": len(claims),
        "status_breakdown": status_counts,
        "unread_notifications": notifications,
        "policies": [p.policy_number for p in policyholder.policies] if policyholder.policies else [],
        "under_review": status_counts.get("UNDER_REVIEW", 0) + status_counts.get("AI_PROCESSING", 0),
        "approved": status_counts.get("APPROVED", 0),
        "rejected": status_counts.get("REJECTED", 0),
        "escalated": status_counts.get("ESCALATED", 0) + status_counts.get("ADMIN_REVIEW", 0),
        "recent_claims": recent_claims
    }


# ---------------------------------------------------------------------------
# Submit Claim
# ---------------------------------------------------------------------------

@router.post("/claims/submit", status_code=status.HTTP_201_CREATED, summary="Submit a new claim")
async def submit_claim(
    notes: Optional[str] = Form(default=None),
    files: List[UploadFile] = File(...),
    doc_types: str = Form(...),  # JSON array of doc type strings
    payload: dict = Depends(require_role("policyholder")),
    db: Session = Depends(get_db),
):
    """
    Submit a new insurance claim with uploaded documents.
    Triggers the full AI processing pipeline asynchronously.
    """
    policyholder = _get_policyholder(db, payload)
    doc_type_list = json.loads(doc_types) if doc_types else ["other"] * len(files)

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one document must be uploaded",
        )

    # Validate files
    for file in files:
        _validate_upload_file(file)

    # Create claim record
    claim = Claim(
        policyholder_id=policyholder.id,
        status="SUBMITTED",
        notes=notes,
    )
    db.add(claim)
    db.flush()

    # Save documents
    saved_docs = []
    for i, file in enumerate(files):
        doc_type = doc_type_list[i] if i < len(doc_type_list) else "other"
        
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
            
        secure_url, public_id = await upload_service.upload_file(file, folder="nexclaim/claims")
        if not secure_url:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload to Cloudinary failed")

        doc = ClaimDocument(
            claim_id=claim.id,
            doc_type=doc_type,
            original_filename=file.filename or "document",
            stored_filename=public_id or f"claim_{claim.id}_{uuid.uuid4().hex[:8]}",
            file_path=secure_url,
            mime_type=file.content_type,
            file_size_bytes=file_size,
        )
        db.add(doc)
        saved_docs.append(doc)

    db.commit()
    db.refresh(claim)

    # Notify policyholder
    policyholder_user = db.query(User).filter(User.id == policyholder.user_id).first()
    if policyholder_user:
        notification_service.notify_claim_status(
            db=db,
            user=policyholder_user,
            claim_id=claim.id,
            status="SUBMITTED",
            message="Your claim has been submitted successfully and is now being processed by our AI system.",
        )

    # Run AI pipeline
    try:
        _run_ai_pipeline(db, claim, saved_docs)
        # Notify reviewers
        reviewers = db.query(Reviewer).filter(Reviewer.is_active == True).all()
        for reviewer in reviewers:
            reviewer_user = db.query(User).filter(User.id == reviewer.user_id).first()
            if reviewer_user:
                notification_service.notify_reviewer(
                    db=db,
                    reviewer_user=reviewer_user,
                    claim_id=claim.id,
                    action=f"A new claim #{claim.id} has been submitted and is ready for your review.",
                )
    except Exception as exc:
        logger.error("AI pipeline failed for claim #%d: %s", claim.id, exc)
        claim.status = "SUBMITTED"  # Keep as submitted if AI fails
        db.commit()

    return {"message": "Claim submitted successfully", "claim_id": claim.id, "status": claim.status}


# ---------------------------------------------------------------------------
# List Claims
# ---------------------------------------------------------------------------

@router.get("/claims", summary="List all claims for the policyholder")
def list_claims(
    page: int = 1,
    page_size: int = 10,
    payload: dict = Depends(require_role("policyholder")),
    db: Session = Depends(get_db),
):
    """Return paginated list of claims for the authenticated policyholder."""
    policyholder = _get_policyholder(db, payload)
    total = db.query(Claim).filter(Claim.policyholder_id == policyholder.id).count()
    claims = (
        db.query(Claim)
        .filter(Claim.policyholder_id == policyholder.id)
        .order_by(Claim.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    def _get_reason(c: Claim) -> str:
        if c.admin_decision and c.admin_decision.comments:
            return c.admin_decision.comments
        if c.reviewer_decision and c.reviewer_decision.comments:
            return c.reviewer_decision.comments
        
        if c.status == "APPROVED":
            return "Your claim has been successfully approved."
        elif c.status == "REJECTED":
            if c.recommendation:
                try:
                    reasons = json.loads(c.recommendation.reasons_json or "[]")
                    for reason in reasons:
                        if "missing" in reason.lower():
                            return reason
                except: pass
            return "Claim rejected. Please contact support."
        else:
            return "Your claim is currently under manual review."

    return {
        "items": [
            {
                "id": c.id,
                "status": c.status,
                "diagnosis": c.diagnosis,
                "hospital_name": c.hospital_name,
                "claim_amount": c.claim_amount,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "reason": _get_reason(c)
            }
            for c in claims
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# Claim Detail
# ---------------------------------------------------------------------------

@router.get("/claims/{claim_id}", summary="Get claim details")
def get_claim_detail(
    claim_id: int,
    payload: dict = Depends(require_role("policyholder")),
    db: Session = Depends(get_db),
):
    """Return full details for a specific claim including AI results."""
    policyholder = _get_policyholder(db, payload)
    claim = db.query(Claim).filter(
        Claim.id == claim_id,
        Claim.policyholder_id == policyholder.id,
    ).first()
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
        "extracted_policy_number": claim.extracted_policy_number,
        "extracted_patient_name": claim.extracted_patient_name,
        "notes": claim.notes,
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
        "documents": [
            {
                "id": d.id,
                "doc_type": d.doc_type,
                "original_filename": d.original_filename,
                "file_size_bytes": d.file_size_bytes,
            }
            for d in claim.documents
        ],
        "validation": None,
        "risk_score": None,
        "recommendation": None,
        "reviewer_comments": None,
    }

    if claim.recommendation:
        rec = claim.recommendation
        
        # Scrub internal reasons for policyholder
        raw_reasons = json.loads(rec.reasons_json or "[]")
        filtered_reasons = []
        if claim.status == "APPROVED":
            filtered_reasons = ["Your claim has been successfully approved."]
        elif claim.status == "REJECTED":
            filtered_reasons = [r for r in raw_reasons if "missing these documents" in r.lower()]
            if not filtered_reasons:
                filtered_reasons = ["Claim rejected. Please contact support."]
        else:
            filtered_reasons = ["Your claim is currently under manual review."]
            
        result["recommendation"] = {
            "action": claim.status,
            "confidence_score": 0.0,
            "reasons": filtered_reasons,
            "explanation": "Your claim is being processed according to standard procedures.",
        }

    if claim.reviewer_decision:
        result["reviewer_comments"] = claim.reviewer_decision.comments
        result["reviewer_decision"] = claim.reviewer_decision.decision

    if claim.admin_decision:
        result["admin_decision"] = claim.admin_decision.decision
        result["admin_comments"] = claim.admin_decision.comments

    # Add extracted data from ai_extraction_json
    extracted_data = {}
    if claim.ai_extraction_json:
        try:
            brief = json.loads(claim.ai_extraction_json)
            extracted_data = brief.get("extracted_data", {})
        except Exception:
            pass
    result["extracted_data"] = extracted_data

    return result


@router.get("/claims/{claim_id}/timeline", summary="Get claim status timeline")
def get_claim_timeline(
    claim_id: int,
    payload: dict = Depends(require_role("policyholder")),
    db: Session = Depends(get_db),
):
    """Return the status timeline for a claim."""
    policyholder = _get_policyholder(db, payload)
    claim = db.query(Claim).filter(
        Claim.id == claim_id,
        Claim.policyholder_id == policyholder.id,
    ).first()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    timeline = []
    
    # Stage 1: Submitted
    timeline.append({
        "status": "SUBMITTED",
        "label": "Claim Submitted",
        "completed": True,
        "active": claim.status == "SUBMITTED",
        "comment": f"Claim submitted on {claim.created_at.strftime('%Y-%m-%d')}." if claim.created_at else "Claim submitted."
    })
    
    # Stage 2: AI Evaluated
    ai_completed = claim.status != "SUBMITTED"
    ai_comment = "Pending AI Evaluation."
    missing_docs_flag = False
    if ai_completed:
        if claim.recommendation:
            reasons = json.loads(claim.recommendation.reasons_json or "[]")
            missing_reason = next((r for r in reasons if "missing these documents" in r.lower()), None)
            if missing_reason:
                ai_comment = missing_reason
                missing_docs_flag = True
            else:
                ai_comment = "All required documents were successfully verified."
        else:
            ai_comment = "AI Evaluation completed."
            
    timeline.append({
        "status": "AI_EVALUATED",
        "label": "AI Document Evaluation",
        "completed": ai_completed,
        "active": claim.status == "AI_PROCESSING",
        "comment": ai_comment
    })
    
    # Stage 3: Human Review
    human_completed = claim.status in ["APPROVED", "REJECTED"]
    human_active = claim.status in ["UNDER_REVIEW", "ESCALATED", "ADMIN_REVIEW"]
    human_comment = "Pending manual human review."
    
    if claim.status == "REJECTED" and missing_docs_flag:
        human_completed = False
        human_active = False
        human_comment = "Skipped due to missing required documents."
    else:
        if human_completed:
            if claim.admin_decision and claim.admin_decision.comments:
                human_comment = f"Admin: {claim.admin_decision.comments}"
            elif claim.reviewer_decision and claim.reviewer_decision.comments:
                human_comment = f"Reviewer: {claim.reviewer_decision.comments}"
            else:
                human_comment = "Human review completed."
        elif human_active:
            human_comment = "Claim is currently under manual review by an agent."
            
    timeline.append({
        "status": "HUMAN_REVIEW",
        "label": "Human Review",
        "completed": human_completed,
        "active": human_active,
        "comment": human_comment
    })
    
    # Stage 4: Final Decision
    final_completed = claim.status in ["APPROVED", "REJECTED"]
    final_label = "Final Decision"
    if claim.status == "APPROVED":
        final_label = "Accepted"
    elif claim.status == "REJECTED":
        final_label = "Rejected"
        
    final_comment = ""
    if claim.status == "APPROVED":
        final_comment = "Claim was successfully accepted."
    elif claim.status == "REJECTED":
        final_comment = "Claim was rejected."
    else:
        final_comment = "Pending final decision."
        
    timeline.append({
        "status": "FINAL_DECISION",
        "label": final_label,
        "completed": final_completed,
        "active": final_completed,
        "comment": final_comment
    })

    return {"claim_id": claim_id, "current_status": claim.status, "timeline": timeline}


@router.get("/profile", summary="Get policyholder profile")
def get_profile(
    payload: dict = Depends(require_role("policyholder")),
    db: Session = Depends(get_db),
):
    """Retrieve aggregated policyholder profile for dashboard."""
    ph = _get_policyholder(db, payload)
    user = ph.user
    
    claims = ph.claims
    total_claims = len(claims)
    approved_claims = sum(1 for c in claims if c.status == "FINAL_APPROVED")
    rejected_claims = sum(1 for c in claims if c.status == "FINAL_REJECTED")
    pending_claims = total_claims - approved_claims - rejected_claims

    latest_claims_list = sorted(claims, key=lambda c: c.created_at, reverse=True)[:5]
    timeline_data = [{
        "id": c.id,
        "claim_number": c.claim_number or f"CLM-{c.id}",
        "status": c.status,
        "amount": c.claim_amount,
        "date": c.created_at.isoformat() if c.created_at else None
    } for c in latest_claims_list]

    has_active_policy = any(p.is_active for p in ph.policies)
    health_score = 100
    if not has_active_policy:
        health_score -= 50
    health_score -= (rejected_claims * 10)
    health_score = max(0, min(100, health_score))

    policies_data = []
    total_limit = 0
    total_used = 0

    for p in ph.policies:
        used_coverage = sum(c.claim_amount for c in claims if c.policy_id == p.id and c.status == "FINAL_APPROVED")
        total_limit += p.coverage_limit
        total_used += used_coverage
        policies_data.append({
            "id": p.id,
            "policy_number": p.policy_number,
            "policy_name": p.policy_name,
            "insurer_name": p.insurer_name,
            "coverage_limit": p.coverage_limit,
            "coverage_used": used_coverage,
            "remaining_coverage": p.coverage_limit - used_coverage,
            "is_active": p.is_active
        })

    documents_data = []
    for p in ph.policies:
        if p.file_path:
            documents_data.append({
                "id": p.id,
                "type": "Policy Document",
                "name": f"{p.policy_name} Document",
                "date": p.created_at.isoformat() if p.created_at else None,
                "is_policy": True
            })
    for c in claims:
        for doc in c.documents:
            documents_data.append({
                "id": doc.id,
                "type": doc.doc_type,
                "name": doc.original_filename,
                "date": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                "is_policy": False,
                "claim_id": c.id
            })

    notifs = sorted(user.notifications, key=lambda n: n.created_at, reverse=True)[:5]
    notif_data = [{
        "title": n.title,
        "message": n.message,
        "type": n.notification_type,
        "date": n.created_at.isoformat() if n.created_at else None
    } for n in notifs]

    return {
        "user": {
            "full_name": user.full_name,
            "email": user.email,
            "phone": user.phone,
            "is_verified": user.is_verified,
            "created_at": user.created_at.isoformat() if user.created_at else None
        },
        "stats": {
            "total_claims": total_claims,
            "approved_claims": approved_claims,
            "rejected_claims": rejected_claims,
            "pending_claims": pending_claims,
            "health_score": health_score
        },
        "coverage": {
            "total_limit": total_limit,
            "total_used": total_used,
            "total_remaining": total_limit - total_used
        },
        "policies": policies_data,
        "latest_claims": timeline_data,
        "documents": sorted(documents_data, key=lambda x: x["date"] or "", reverse=True)[:10],
        "notifications": notif_data
    }

@router.get("/claims/{claim_id}/documents/{doc_id}", summary="Download claim document")
def download_claim_document(
    claim_id: int,
    doc_id: int,
    token: str = Query(..., description="JWT token for authentication"),
    db: Session = Depends(get_db),
):
    from app.shared.backend.security import decode_access_token
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        
    if payload.get("role") != "policyholder":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    ph = _get_policyholder(db, payload)
    
    # Check if claim belongs to this policyholder
    claim = db.query(Claim).filter(Claim.id == claim_id, Claim.policyholder_id == ph.id).first()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
        
    doc = next((d for d in claim.documents if d.id == doc_id), None)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        
    if not doc.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found on server")
        
    if doc.file_path.startswith("http://") or doc.file_path.startswith("https://"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(doc.file_path)
        
    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found on server")
        
    return FileResponse(path=doc.file_path, filename=doc.original_filename)


@router.get("/policies/{policy_id}/document", summary="Download policy document")
def download_policy_document(
    policy_id: int,
    token: str = Query(..., description="JWT token for authentication"),
    db: Session = Depends(get_db),
):
    """Download the policy document if it belongs to the policyholder."""
    from app.shared.backend.security import decode_access_token
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        
    if payload.get("role") != "policyholder":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    ph = _get_policyholder(db, payload)
    
    # Check if policy is linked to this policyholder
    policy = next((p for p in ph.policies if p.id == policy_id), None)
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found or not linked to your account.")
        
    if not policy.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy document file not found on server.")
        
    if policy.file_path.startswith("http://") or policy.file_path.startswith("https://"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(policy.file_path)
        
    if not os.path.exists(policy.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy document file not found on server.")
        
    # Return file response
    filename = os.path.basename(policy.file_path)
    return FileResponse(path=policy.file_path, filename=filename)

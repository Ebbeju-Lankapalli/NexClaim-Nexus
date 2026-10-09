"""
NexClaim Reviewer Router.

Handles claim review queue, claim detail inspection with AI outputs,
and decision recording (Approve, Reject, Escalate).
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.shared.backend.database import get_db
from app.shared.backend.models import (
    Admin, Claim, EscalatedClaim, Notification, Reviewer, ReviewerDecision, User
)
from app.shared.backend.notification_service import notification_service
from app.shared.backend.schemas import MessageResponse, ReviewerDecisionRequest
from app.shared.backend.security import get_current_user_payload, require_role

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reviewer", tags=["Reviewer"])


def _get_reviewer(db: Session, payload: dict) -> Reviewer:
    """Get reviewer profile from authenticated user payload."""
    user_id = int(payload["sub"])
    reviewer = db.query(Reviewer).filter(Reviewer.user_id == user_id).first()
    if not reviewer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer profile not found",
        )
    return reviewer


@router.get("/dashboard", summary="Reviewer dashboard summary")
def get_dashboard(
    payload: dict = Depends(require_role("reviewer")),
    db: Session = Depends(get_db),
):
    """Return dashboard metrics for the authenticated reviewer."""
    reviewer = _get_reviewer(db, payload)

    pending = db.query(Claim).filter(Claim.status == "UNDER_REVIEW").count()
    reviewed = (
        db.query(ReviewerDecision)
        .filter(ReviewerDecision.reviewer_id == reviewer.id)
        .count()
    )
    escalated = db.query(Claim).filter(Claim.status == "ESCALATED").count()
    total_claims = db.query(Claim).count()

    return {
        "pending_claims": pending,
        "reviewed_by_me": reviewed,
        "escalated_claims": escalated,
        "total_claims": total_claims,
    }


@router.get("/claims", summary="List claims for review")
def list_review_queue(
    status_filter: str = "UNDER_REVIEW",
    page: int = 1,
    page_size: int = 10,
    payload: dict = Depends(require_role("reviewer")),
    db: Session = Depends(get_db),
):
    """Return paginated list of claims with the specified status."""
    query = db.query(Claim)
    if status_filter != "all":
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
                "extracted_patient_name": c.extracted_patient_name or c.policyholder.user.full_name,
                "risk_level": c.risk_score.risk_level if c.risk_score else None,
                "confidence_score": c.recommendation.confidence_score if c.recommendation else None,
                "recommendation": c.recommendation.action if c.recommendation else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in claims
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/claims/{claim_id}", summary="Get full claim details for review")
def get_claim_for_review(
    claim_id: int,
    payload: dict = Depends(require_role("reviewer")),
    db: Session = Depends(get_db),
):
    """Return complete claim details including AI brief for reviewer inspection."""
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    policyholder_info = None
    if claim.policyholder and claim.policyholder.user:
        u = claim.policyholder.user
        policyholder_info = {
            "full_name": u.full_name,
            "email": u.email,
            "phone": u.phone,
            "policy_number": claim.policy.policy_number if claim.policy else None,
        }

    result = {
        "id": claim.id,
        "status": claim.status,
        "policyholder": policyholder_info,
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
    }

    if claim.ai_extraction_json:
        try:
            brief = json.loads(claim.ai_extraction_json)
            result["brief_data"] = brief
            result["validation"] = brief.get("validation_results", [])
            result["recommendation"] = brief.get("executive_summary", {})
            result["risk_score"] = brief.get("risk_assessment", {})
            result["pre_assessment_brief"] = json.dumps(brief, indent=2) # Fallback formatting for the raw box
        except json.JSONDecodeError:
            pass

    return result


@router.get("/claims/{claim_id}/documents/{doc_id}/view", summary="View an uploaded claim document")
def get_claim_document(
    claim_id: int,
    doc_id: int,
    payload: dict = Depends(require_role("reviewer")),
    db: Session = Depends(get_db),
):
    """Return the raw file for an uploaded claim document."""
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
        
    document = None
    for doc in claim.documents:
        if doc.id == doc_id:
            document = doc
            break
            
    if not document or not document.file_path:
        raise HTTPException(status_code=404, detail="Document not found")
        
    if document.file_path.startswith("http://") or document.file_path.startswith("https://"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(document.file_path)

    import os
    if not os.path.exists(document.file_path):
        raise HTTPException(status_code=404, detail="File missing on disk")
        
    return FileResponse(document.file_path)


@router.post("/claims/{claim_id}/decision", response_model=MessageResponse, summary="Submit reviewer decision")
def submit_decision(
    claim_id: int,
    decision_request: ReviewerDecisionRequest,
    payload: dict = Depends(require_role("reviewer")),
    db: Session = Depends(get_db),
):
    """Record a reviewer decision (APPROVED, REJECTED, or ESCALATED) for a claim."""
    reviewer = _get_reviewer(db, payload)
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    if claim.status not in ("UNDER_REVIEW", "SUBMITTED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Claim is in status '{claim.status}' and cannot be reviewed",
        )

    # Check for existing decision
    existing = db.query(ReviewerDecision).filter(
        ReviewerDecision.claim_id == claim_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A decision has already been recorded for this claim",
        )

    decision_record = ReviewerDecision(
        claim_id=claim_id,
        reviewer_id=reviewer.id,
        decision=decision_request.decision,
        comments=decision_request.comments,
    )
    db.add(decision_record)

    # Update claim status
    status_map = {
        "APPROVED": "APPROVED",
        "REJECTED": "REJECTED",
        "ESCALATED": "ESCALATED",
    }
    claim.status = status_map.get(decision_request.decision, "UNDER_REVIEW")

    # If escalated, create escalated claim record
    if decision_request.decision == "ESCALATED":
        escalated = EscalatedClaim(
            claim_id=claim_id,
            reviewer_id=reviewer.id,
            reason=decision_request.comments,
        )
        db.add(escalated)
        claim.status = "ADMIN_REVIEW"

    db.commit()

    # Notify policyholder
    if claim.policyholder and claim.policyholder.user:
        notification_service.notify_claim_status(
            db=db,
            user=claim.policyholder.user,
            claim_id=claim_id,
            status=claim.status,
            message=f"Your claim #{claim_id} has been reviewed. Decision: {decision_request.decision}",
            reviewer_comments=decision_request.comments,
            notification_type="SUCCESS" if decision_request.decision == "APPROVED" else "WARNING",
        )

    # Notify admins if escalated
    if decision_request.decision == "ESCALATED":
        admins = db.query(Admin).all()
        for admin in admins:
            admin_user = db.query(User).filter(User.id == admin.user_id).first()
            if admin_user:
                notification_service.notify_admin(
                    db=db,
                    admin_user=admin_user,
                    claim_id=claim_id,
                    message=f"Claim #{claim_id} has been escalated by reviewer for your review.",
                )

    logger.info(
        "Reviewer decision recorded: claim #%d, decision=%s, reviewer=%d",
        claim_id, decision_request.decision, reviewer.id
    )
    return MessageResponse(message=f"Decision '{decision_request.decision}' recorded successfully")

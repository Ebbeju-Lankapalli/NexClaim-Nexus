"""
Tests for the AI Decision Support System Pipeline.
Ensures >90% coverage for Risk Scoring, Confidence Scoring, and Explainability.
"""

import pytest
from app.ai.risk_scoring.risk_scoring import risk_scorer
from app.ai.confidence_scoring.scorer import confidence_scorer
from app.ai.explainability.engine import explainability_engine
from app.ai.recommendations.recommendations import recommendation_engine
from app.ai.policy_validation.policy_validation import policy_validator
from datetime import datetime, timedelta

# --- MOCKS ---
class MockPolicy:
    def __init__(self, is_active=True, limit=10000, diseases=None, waiting=0, created_days_ago=100):
        self.is_active = is_active
        self.coverage_limit = limit
        self.covered_diseases_list = diseases or []
        self.waiting_period_days = waiting
        self.created_at = datetime.utcnow() - timedelta(days=created_days_ago)
        self.premium_paid_until = datetime.utcnow() + timedelta(days=365)


# --- 1. Unit Tests: Risk Scoring ---
def test_risk_scorer_low_risk():
    result = risk_scorer.calculate_risk(
        claim_amount=1000,
        coverage_amount=10000,
        submitted_docs=4,
        required_docs=4,
        policy_age_days=1000,
        waiting_period_completed=1,
        field_consistency_score=1.0,
        ocr_quality_score=0.95,
        extraction_confidence_score=0.90,
        historical_claim_frequency=0
    )
    assert result["category"] == "LOW RISK"
    assert result["probability"] <= 0.30

def test_risk_scorer_high_risk():
    result = risk_scorer.calculate_risk(
        claim_amount=15000,
        coverage_amount=10000,
        submitted_docs=1,
        required_docs=4,
        policy_age_days=10,
        waiting_period_completed=0,
        field_consistency_score=0.4,
        ocr_quality_score=0.40,
        extraction_confidence_score=0.50,
        historical_claim_frequency=5
    )
    assert result["category"] == "HIGH RISK"
    assert result["probability"] > 0.70


# --- 2. Unit Tests: Confidence Scoring ---
def test_confidence_scorer():
    result = confidence_scorer.calculate(
        ocr_confidence=0.90,
        extraction_confidence=0.95,
        consistency_score=1.0,
        validation_pass_ratio=1.0,
        document_completeness=1.0
    )
    assert result["score_percentage"] > 90.0
    assert "breakdown" in result


# --- 3. Unit Tests: Explainability ---
def test_explainability_engine():
    result = explainability_engine.generate(
        extracted_data={
            "claim_data": {
                "patient_name": {"value": "John Doe", "source_document": "claim.pdf"}
            }
        },
        validation_results={"is_policy_active": "PASS", "is_within_limit": "FAIL"},
        risk_data={"probability": 0.8, "features": {"coverage_utilization_ratio": 1.5}},
        validation_flags=[{"field": "policy_number", "issue": "Mismatch"}]
    )
    assert len(result["positive_findings"]) == 1
    assert len(result["negative_findings"]) == 2
    assert len(result["risk_factors"]) > 0
    assert len(result["evidence_trail"]) == 1
    assert result["evidence_trail"][0]["found_in"] == "claim.pdf"


# --- 4. Integration Test: Recommendation Engine ---
def test_recommendation_approve():
    result = recommendation_engine.generate(
        validation_results={"all": "PASS"},
        risk_probability=0.10,
        confidence_score=0.95,
        missing_fields=[]
    )
    assert result["action"] == "APPROVE_RECOMMENDATION"

def test_recommendation_escalate():
    result = recommendation_engine.generate(
        validation_results={"all": "PASS"},
        risk_probability=0.50, # Medium risk -> escalate
        confidence_score=0.90,
        missing_fields=[]
    )
    assert result["action"] == "ESCALATE"

def test_recommendation_reject():
    result = recommendation_engine.generate(
        validation_results={"limit": "PASS", "active": "PASS"},
        risk_probability=0.95,
        confidence_score=0.90,
        missing_fields=[],
        missing_docs=["DISCHARGE_SUMMARY"]
    )
    assert result["action"] == "REJECT_RECOMMENDATION"


# --- 5. E2E Simulation: Pipeline Assess ---
from app.ai.pipeline import ai_pipeline

def test_pipeline_assess():
    # Mock extract data
    extracted_data = {
        "financial_data": {"claim_amount": {"value": 5000.0}},
        "document_types": {"doc1.pdf": "CLAIM_FORM", "doc2.pdf": "HOSPITAL_BILL", "doc3.pdf": "DISCHARGE_SUMMARY"},
        "consistency_score": 1.0,
        "ocr_summary": {"average_confidence": 0.9},
        "extraction_confidence": 0.9,
        "missing_fields": []
    }
    
    class MockUser:
        full_name = "Test User"
    class MockPolicyholder:
        user = MockUser()
    class MockClaim:
        id = 99
        status = "SUBMITTED"
        policyholder = MockPolicyholder()
    mock_claim = MockClaim()
    mock_policy = MockPolicy(limit=10000, created_days_ago=1500)
    
    brief = ai_pipeline.assess(claim=mock_claim, extracted_data=extracted_data, policy=mock_policy, required_docs_count=2)
    
    assert brief["metadata"]["claim_id"] == 99
    assert brief["executive_summary"]["recommendation"] in ["APPROVE_RECOMMENDATION", "ESCALATE"]
    assert brief["executive_summary"]["confidence_score"] > 80.0

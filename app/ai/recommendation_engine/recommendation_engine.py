"""
NexClaim Recommendation Engine.

Hybrid approach combining business rules with risk score to determine
a final recommendation: APPROVE, REJECT, or ESCALATE.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Recommendation action constants
ACTION_APPROVE = "APPROVE_RECOMMENDATION"
ACTION_REJECT = "REJECT_RECOMMENDATION"
ACTION_ESCALATE = "ESCALATE"


class RecommendationEngine:
    """Generates a claim recommendation from validation and risk data."""

    def recommend(
        self,
        validation: dict,
        risk_level: str,
        risk_probability: float,
        confidence_score: float,
    ) -> dict:
        """
        Generate a claim recommendation.

        Business rules:
        - Any hard-reject condition (policy inactive, premium unpaid) → REJECT
        - High risk probability → ESCALATE for human review
        - Disease not covered → REJECT
        - All validations pass, low/medium risk → APPROVE
        - Low confidence score → ESCALATE

        Returns:
            dict with action, reasons, and explanation
        """
        reasons = []
        action = ACTION_APPROVE

        # Hard reject rules
        if not validation.get("is_policy_active"):
            reasons.append("Policy is inactive or expired")
            action = ACTION_REJECT

        if not validation.get("is_premium_paid"):
            reasons.append("Policy premium has lapsed")
            action = ACTION_REJECT

        if not validation.get("is_disease_covered"):
            reasons.append("Diagnosed condition is not covered under this policy")
            action = ACTION_REJECT

        if not validation.get("is_within_limit"):
            reasons.append("Claim amount exceeds the policy coverage limit")
            if action == ACTION_APPROVE:
                action = ACTION_ESCALATE

        if not validation.get("is_waiting_period_met"):
            reasons.append("Policy waiting period has not been completed")
            action = ACTION_REJECT

        # Risk-based escalation (only if not already rejected)
        if action != ACTION_REJECT:
            if risk_level == "HIGH" or risk_probability >= 0.70:
                reasons.append(f"High risk score detected (probability: {risk_probability:.1%})")
                action = ACTION_ESCALATE
            elif confidence_score < 0.50:
                reasons.append(f"Low confidence score ({confidence_score:.1%}) — requires human review")
                action = ACTION_ESCALATE

        if action == ACTION_APPROVE and not reasons:
            reasons.append("All policy validations passed")
            reasons.append(f"Risk level is {risk_level} with probability {risk_probability:.1%}")
            reasons.append(f"Confidence score: {confidence_score:.1%}")

        logger.info(
            "Recommendation: %s | Risk: %s (%.2f) | Confidence: %.2f",
            action, risk_level, risk_probability, confidence_score
        )

        return {
            "action": action,
            "reasons": reasons,
        }


recommendation_engine = RecommendationEngine()

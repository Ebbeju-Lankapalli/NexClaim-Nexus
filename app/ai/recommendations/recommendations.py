"""
DSS Recommendation Engine.
Evaluates Policy Validation, Risk Score, Confidence, and Document Completeness
to generate a final Decision Support Recommendation.
"""

from typing import Dict, Any, List

class RecommendationEngine:
    def generate(
        self,
        validation_results: Dict[str, str],
        risk_probability: float,
        confidence_score: float,
        missing_fields: List[str],
        missing_docs: List[str] = None
    ) -> Dict[str, Any]:
        
        missing_docs = missing_docs or []
        reasons = []
        action = "ESCALATE" # Default to human review
        
        # Determine critical failures
        critical_fails = sum(1 for status in validation_results.values() if status == "FAIL")
        warnings = sum(1 for status in validation_results.values() if status == "WARNING")
        
        # 1. Reject Condition: IF AND ONLY IF required documents are missing
        if missing_docs:
            action = "REJECT_RECOMMENDATION"
            formatted_docs = [doc.replace("_", " ").title() for doc in missing_docs]
            reasons.append(f"Rejected because it is missing these documents: {', '.join(formatted_docs)}.")
            return {"action": action, "reasons": reasons}
            
        # 2. Escalate Condition
        if critical_fails > 0 or warnings > 0 or risk_probability > 0.30 or confidence_score < 0.80 or missing_fields:
            action = "ESCALATE"
            if critical_fails > 0:
                reasons.append(f"Contains {critical_fails} critical policy validation failure(s) requiring manual review.")
            if warnings > 0:
                reasons.append(f"Contains {warnings} validation warnings.")
            if risk_probability > 0.30:
                reasons.append(f"Risk profile ({round(risk_probability*100)}%) requires review.")
            if confidence_score < 0.80:
                reasons.append(f"System confidence ({round(confidence_score*100)}%) indicating potential ambiguities.")
            if missing_fields:
                reasons.append(f"Missing essential extracted fields: {', '.join(missing_fields)}.")
                
        # 3. Approve Condition
        else:
            action = "APPROVE_RECOMMENDATION"
            reasons.append("All policy checks passed.")
            reasons.append("Low risk profile.")
            reasons.append(f"High extraction confidence ({round(confidence_score*100)}%).")
            reasons.append("All required documentation is complete.")
            
        # Fallback if no specific reason appended
        if not reasons:
            reasons.append("Requires human review due to complex overlapping factors.")
            
        return {
            "action": action,
            "reasons": reasons
        }

recommendation_engine = RecommendationEngine()

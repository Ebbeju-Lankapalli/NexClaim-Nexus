"""
Pre-Assessment Brief Generator.
Synthesizes all AI engine outputs into a structured Reviewer-Ready Brief.
"""

from typing import Dict, Any

class BriefGenerator:
    def generate(
        self,
        claim: Any,
        engine_output: Dict[str, Any],
        extracted_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        
        # Format the comprehensive output
        brief = {
            "metadata": {
                "claim_id": claim.id if claim else 0,
                "status": "AI_PRE_ASSESSMENT_COMPLETE",
                "recommendation": engine_output.get("recommendation", "")
            },
            "executive_summary": {
                "recommendation": engine_output.get("recommendation", ""),
                "primary_reasons": engine_output.get("explainability", {}).get("failed_reasons", []),
                "confidence_score": engine_output.get("confidence_score", 0.0),
                "risk_category": self._get_risk_category(engine_output.get("risk_score", 0.0))
            },
            "claim_overview": {
                "patient_name": extracted_data.get("claim_data", {}).get("patient_name", {}).get("value", "Unknown"),
                "diagnosis": extracted_data.get("claim_data", {}).get("diagnosis", {}).get("value", "Unknown"),
                "hospital_name": extracted_data.get("hospital_data", {}).get("hospital_name", {}).get("value", "Unknown"),
                "claim_amount": extracted_data.get("financial_data", {}).get("claim_amount", {}).get("value", 0.0)
            },
            "validation_results": engine_output.get("validation_results", []),
            "risk_assessment": {
                "probability": engine_output.get("risk_score", 0.0),
                "category": self._get_risk_category(engine_output.get("risk_score", 0.0)),
                "risk_factors": engine_output.get("explainability", {}).get("risk_factors", [])
            },
            "explainability": {
                "positive_findings": [r["reason"] for r in engine_output.get("validation_results", []) if r["status"] == "PASS"],
                "negative_findings": engine_output.get("explainability", {}).get("failed_reasons", []) + engine_output.get("explainability", {}).get("warning_reasons", []),
                "evidence_trail": []
            },
            "missing_information": extracted_data.get("missing_fields", []),
            "reviewer_action_suggestions": self._generate_suggestions(engine_output.get("recommendation", ""))
        }
        
        return brief
        
    def _get_risk_category(self, score: float) -> str:
        if score >= 0.7: return "HIGH"
        if score >= 0.3: return "MEDIUM"
        return "LOW"
        
    def _generate_suggestions(self, action: str) -> list:
        if action == "APPROVE_RECOMMENDATION":
            return ["Review summary and proceed to payment authorization."]
        elif action == "ESCALATE":
            return [
                "Review the highlighted Negative Findings and Risk Factors.",
                "Cross-check missing information with the policyholder.",
                "Verify OCR Evidence Trail for potential extraction errors."
            ]
        elif action == "REJECT_RECOMMENDATION":
            return [
                "Draft rejection letter citing the specific Negative Findings.",
                "Verify critical failure points in the Evidence Trail before final rejection."
            ]
        return ["Conduct manual review."]

brief_generator = BriefGenerator()

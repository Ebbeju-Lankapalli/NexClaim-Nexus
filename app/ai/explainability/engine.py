"""
Explainability Engine.
Synthesizes validation results, risk scores, and extraction evidence into
human-readable findings (Positive, Negative, Risk Factors, Evidence Trail).
"""

from typing import Dict, Any, List

class ExplainabilityEngine:
    def generate(
        self,
        extracted_data: Dict[str, Any],
        validation_results: Dict[str, str],
        risk_data: Dict[str, Any],
        validation_flags: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate structured explainability data.
        """
        positive_findings = []
        negative_findings = []
        risk_factors = []
        evidence_trail = []
        
        # 1. Validation Findings
        for check, status in validation_results.items():
            check_name = check.replace("is_", "").replace("_", " ").title()
            if status == "PASS":
                positive_findings.append(f"{check_name} successfully verified.")
            elif status == "FAIL":
                negative_findings.append(f"{check_name} failed verification.")
            elif status == "WARNING":
                negative_findings.append(f"Warning regarding {check_name}.")
                
        # 2. Inconsistencies
        for flag in validation_flags:
            field = flag.get("field", "")
            issue = flag.get("issue", "Mismatch")
            negative_findings.append(f"Inconsistency in {field}: {issue}")
            
        # 3. Risk Factors
        if risk_data.get("probability", 0.0) > 0.3:
            # Add top features contributing to risk
            features = risk_data.get("features", {})
            if features.get("coverage_utilization_ratio", 0) > 0.8:
                risk_factors.append("High coverage utilization ratio (over 80%).")
            if features.get("document_completeness_score", 1.0) < 0.7:
                risk_factors.append("Incomplete documentation submitted.")
            if features.get("ocr_quality_score", 1.0) < 0.6:
                risk_factors.append("Low OCR confidence may mask fraudulent tampering.")
            if features.get("field_consistency_score", 1.0) < 1.0:
                risk_factors.append("Cross-document field inconsistencies detected.")
                
        if not risk_factors and risk_data.get("probability", 0.0) <= 0.3:
            risk_factors.append("No significant risk factors identified.")
            
        # 4. Evidence Trail
        # Loop through extracted data and trace back
        for category in ["claim_data", "policy_data", "hospital_data", "financial_data"]:
            cat_data = extracted_data.get(category, {})
            for field, meta in cat_data.items():
                if isinstance(meta, dict) and "source_document" in meta:
                    evidence_trail.append({
                        "field": field.replace("_", " ").title(),
                        "value": meta.get("value"),
                        "found_in": meta.get("source_document"),
                        "confidence": f"{int(meta.get('confidence', 0.0) * 100)}%",
                        "method": meta.get("extraction_method", "Unknown")
                    })
                    
        return {
            "positive_findings": positive_findings,
            "negative_findings": negative_findings,
            "risk_factors": risk_factors,
            "evidence_trail": evidence_trail
        }

explainability_engine = ExplainabilityEngine()

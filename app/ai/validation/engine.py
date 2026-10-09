import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
try:
    from thefuzz import fuzz
except ImportError:
    fuzz = None

logger = logging.getLogger(__name__)

class ValidationEngine:
    def __init__(self):
        pass

    def add_result(self, output: Dict[str, Any], rule: str, status: str, reason: str = ""):
        res = {
            "rule": rule,
            "status": status,
            "reason": reason
        }
        output["validation_results"].append(res)
        if status == "FAIL":
            output["failed_rules"].append(res)
        elif status == "WARNING":
            output["warning_rules"].append(res)

    def validate(self, extracted_data: Dict[str, Any], policy: Any, claim: Any, submitted_docs: List[str]) -> Dict[str, Any]:
        output = {
            "validation_results": [],
            "failed_rules": [],
            "warning_rules": [],
            "confidence_score": 0.0,
            "risk_score": 0.0,
            "fraud_indicators": [],
            "recommendation": "",
            "explainability": {},
            "source_documents": submitted_docs
        }
        
        # Helper extraction
        claim_amount = float(extracted_data.get("financial_data", {}).get("claim_amount", {}).get("value", 0.0))
        diagnosis = extracted_data.get("financial_data", {}).get("diagnosis", {}).get("value", "")
        if not diagnosis:
            diagnosis = extracted_data.get("claim_data", {}).get("diagnosis", {}).get("value", "")
        admission_date_str = extracted_data.get("hospital_data", {}).get("admission_date", {}).get("value", None)
        discharge_date_str = extracted_data.get("hospital_data", {}).get("discharge_date", {}).get("value", None)
        patient_name = extracted_data.get("claim_data", {}).get("patient_name", {}).get("value", "")
        hospital_name = extracted_data.get("hospital_data", {}).get("hospital_name", {}).get("value", "")
        
        # 1. POLICY VALIDATION
        # Existence
        if not policy:
            self.add_result(output, "policy_existence", "FAIL", "Policy number not found")
        else:
            self.add_result(output, "policy_existence", "PASS", "Policy found")
            
            # Active Check
            if not policy.is_active:
                self.add_result(output, "policy_active", "FAIL", "Policy is inactive or suspended")
            else:
                self.add_result(output, "policy_active", "PASS", "Policy is active")
                
            # Premium Status
            if policy.premium_paid_until and datetime.utcnow() > policy.premium_paid_until:
                self.add_result(output, "premium_status", "FAIL", "Premium overdue")
            else:
                self.add_result(output, "premium_status", "PASS", "Premium status is PAID")
                
            # Holder Match
            registered_name = claim.policyholder.user.full_name if (claim and claim.policyholder and claim.policyholder.user) else ""
            if not patient_name or not registered_name:
                self.add_result(output, "policy_holder_verification", "WARNING", "Could not verify names properly")
            elif fuzz:
                score = fuzz.ratio(patient_name.lower(), registered_name.lower())
                if score > 90:
                    self.add_result(output, "policy_holder_verification", "PASS", "Exact match")
                elif score > 60:
                    self.add_result(output, "policy_holder_verification", "WARNING", "Minor spelling difference")
                else:
                    self.add_result(output, "policy_holder_verification", "FAIL", "Significant mismatch in patient name")
                    output["fraud_indicators"].append("multiple_identity_mismatches")
                    
        # 2. COVERAGE VALIDATION
        if policy:
            covered_diseases = policy.covered_diseases_list if hasattr(policy, "covered_diseases_list") else []
            if diagnosis:
                matched = False
                if covered_diseases:
                    for d in covered_diseases:
                        if diagnosis.lower() in d.lower() or d.lower() in diagnosis.lower():
                            matched = True
                            break
                    if matched:
                        self.add_result(output, "disease_coverage", "PASS", "Disease is covered")
                    else:
                        self.add_result(output, "disease_coverage", "FAIL", f"Disease '{diagnosis}' not covered by policy")
                else:
                    self.add_result(output, "disease_coverage", "PASS", "No specific exclusions listed")
            else:
                self.add_result(output, "disease_coverage", "WARNING", "Diagnosis missing from claim documents")
                
            # Amount
            if claim_amount > policy.coverage_limit:
                self.add_result(output, "coverage_amount", "FAIL", "Coverage exceeded")
                output["fraud_indicators"].append("coverage_exceeded")
            elif claim_amount > (policy.coverage_limit * 0.8):
                self.add_result(output, "coverage_amount", "WARNING", "Coverage utilization > 80%")
            else:
                self.add_result(output, "coverage_amount", "PASS", "Below 80% utilization")
                
        # 3. WAITING PERIOD VALIDATION
        if policy and admission_date_str:
            try:
                for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
                    try:
                        adm_dt = datetime.strptime(admission_date_str, fmt)
                        days_active = (adm_dt - policy.created_at).days
                        wp_req = policy.waiting_period_days
                        if days_active >= wp_req:
                            self.add_result(output, "waiting_period", "PASS", "Waiting period completed")
                        else:
                            self.add_result(output, "waiting_period", "FAIL", f"Waiting period not completed (Active {days_active} days, Req {wp_req} days)")
                            output["fraud_indicators"].append("waiting_period_violation")
                        break
                    except ValueError:
                        continue
            except Exception:
                self.add_result(output, "waiting_period", "WARNING", "Failed to parse admission date")
                
        # 4. CLAIM DATA VALIDATION
        if claim_amount <= 0:
            self.add_result(output, "claim_amount", "FAIL", "Zero or negative amount")
        else:
            self.add_result(output, "claim_amount", "PASS", "Valid positive amount")
            if claim_amount > 500000:
                output["fraud_indicators"].append("high_claim_amount")
                
        if admission_date_str and discharge_date_str:
            self.add_result(output, "admission_discharge_timeline", "PASS", "Valid hospitalization timeline assumed")
            
        # 5. IDENTITY VALIDATION
        if hospital_name:
            self.add_result(output, "hospital_validation", "PASS", "Hospital Name Present")
        else:
            self.add_result(output, "hospital_validation", "WARNING", "Hospital Name Missing")
            
        # 6. DOCUMENT VALIDATION
        mandatory = ["CLAIM_FORM", "HOSPITAL_BILL", "DISCHARGE_SUMMARY"]
        missing_docs = [m for m in mandatory if m not in submitted_docs]
        if missing_docs:
            self.add_result(output, "mandatory_documents", "FAIL", f"Missing mandatory documents: {', '.join(missing_docs)}")
            output["fraud_indicators"].append("missing_mandatory_documents")
        else:
            self.add_result(output, "mandatory_documents", "PASS", "All mandatory documents present")
            
        # 7. OCR VALIDATION
        ocr_conf = extracted_data.get("ocr_summary", {}).get("average_confidence", 0.0)
        if ocr_conf >= 0.85:
            self.add_result(output, "ocr_confidence", "PASS", f"Confidence {ocr_conf*100:.1f}% >= 85%")
        elif ocr_conf >= 0.70:
            self.add_result(output, "ocr_confidence", "WARNING", f"Confidence {ocr_conf*100:.1f}% between 70% and 84%")
        else:
            self.add_result(output, "ocr_confidence", "FAIL", f"Confidence {ocr_conf*100:.1f}% below 70%")
            output["fraud_indicators"].append("excessive_ocr_corrections")
            
        # 8. CROSS DOCUMENT CONSISTENCY
        cons_score = extracted_data.get("consistency_score", 1.0)
        if cons_score >= 0.9:
            self.add_result(output, "cross_document_consistency", "PASS", "Documents are consistent")
        elif cons_score >= 0.7:
            self.add_result(output, "cross_document_consistency", "WARNING", "Minor discrepancies found")
        else:
            self.add_result(output, "cross_document_consistency", "FAIL", "Major conflicting information found")
            
        # 9. FRAUD RISK INDICATORS & SCORE
        num_indicators = len(output["fraud_indicators"])
        if num_indicators >= 3:
            output["risk_score"] = 0.85
        elif num_indicators == 2:
            output["risk_score"] = 0.60
        elif num_indicators == 1:
            output["risk_score"] = 0.35
        else:
            output["risk_score"] = 0.10
            
        # 10. CONFIDENCE SCORE CALCULATION
        ext_conf = extracted_data.get("extraction_confidence", 0.0)
        doc_completeness = 1.0 if not missing_docs else min(1.0, len(submitted_docs) / len(mandatory))
        
        policy_checks = [r for r in output["validation_results"] if r["rule"] in ["policy_existence", "policy_active", "premium_status"]]
        if policy_checks:
            pol_success = sum(1 for r in policy_checks if r["status"] == "PASS") / len(policy_checks)
        else:
            pol_success = 0.0
            
        final_confidence = (
            (ocr_conf * 0.25) +
            (ext_conf * 0.25) +
            (doc_completeness * 0.20) +
            (cons_score * 0.20) +
            (pol_success * 0.10)
        )
        final_confidence = min(1.0, final_confidence)
        output["confidence_score"] = round(final_confidence * 100, 2)
        
        # 11. RECOMMENDATION RULES
        has_critical_fails = any(r["rule"] in ["policy_existence", "policy_active", "disease_coverage", "coverage_amount", "waiting_period"] for r in output["failed_rules"])
        
        if missing_docs:
            output["recommendation"] = "REJECT_RECOMMENDATION"
        else:
            output["recommendation"] = "ESCALATE"
            
        # 12. EXPLAINABILITY
        output["explainability"] = {
            "failed_reasons": [r["reason"] for r in output["failed_rules"]],
            "warning_reasons": [r["reason"] for r in output["warning_rules"]],
            "risk_factors": list(set(output["fraud_indicators"])),
            "recommendation_reason": "Generated automatically based on rule failures/warnings." if (has_critical_fails or output["warning_rules"]) else "All validations passed."
        }
        
        return output

validation_engine = ValidationEngine()

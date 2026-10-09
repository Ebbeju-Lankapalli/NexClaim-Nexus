"""
NexClaim Policy Validation Module.

Validates claim data against stored policy records.
Outputs PASS, FAIL, or WARNING statuses required for the DSS Engine.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class PolicyValidator:
    def validate(
        self,
        policy,
        claim_amount: float,
        diagnosis: Optional[str],
        admission_date: Optional[datetime],
        documents_submitted: list
    ) -> Dict[str, Any]:
        """
        Perform validation returning PASS/FAIL/WARNING.
        """
        results = {}

        # 1. Policy active status
        if policy and policy.is_active:
            results["is_policy_active"] = "PASS"
        elif policy:
            results["is_policy_active"] = "FAIL"
        else:
            results["is_policy_active"] = "FAIL"
            return results  # Stop if no policy found

        # 2. Premium payment status
        if not policy.premium_paid_until or datetime.utcnow() <= policy.premium_paid_until:
            results["is_premium_paid"] = "PASS"
        else:
            results["is_premium_paid"] = "FAIL"

        # 3. Coverage limit
        if policy.coverage_limit <= 0:
            results["is_within_limit"] = "PASS"
        elif claim_amount <= policy.coverage_limit:
            results["is_within_limit"] = "PASS"
        elif claim_amount > policy.coverage_limit * 1.5:
            results["is_within_limit"] = "FAIL"
        else:
            results["is_within_limit"] = "WARNING"

        # 4. Disease coverage
        if not diagnosis:
            results["is_disease_covered"] = "WARNING"
        else:
            covered = policy.covered_diseases_list
            if not covered:
                results["is_disease_covered"] = "PASS"
            else:
                diagnosis_lower = diagnosis.lower().strip()
                if any(disease.lower() in diagnosis_lower or diagnosis_lower in disease.lower() for disease in covered):
                    results["is_disease_covered"] = "PASS"
                else:
                    results["is_disease_covered"] = "FAIL"

        # 5. Waiting period
        if policy.waiting_period_days <= 0:
            results["is_waiting_period_met"] = "PASS"
        elif not admission_date or not policy.created_at:
            results["is_waiting_period_met"] = "WARNING"
        else:
            days_since = (admission_date - policy.created_at).days
            if days_since >= policy.waiting_period_days:
                results["is_waiting_period_met"] = "PASS"
            else:
                results["is_waiting_period_met"] = "FAIL"
                
        # 6. Document Completeness
        mandatory_docs = ["CLAIM_FORM", "HOSPITAL_BILL"]
        missing = [d for d in mandatory_docs if d not in documents_submitted]
        if not missing:
            results["are_documents_complete"] = "PASS"
        elif len(missing) == len(mandatory_docs):
            results["are_documents_complete"] = "FAIL"
        else:
            results["are_documents_complete"] = "WARNING"

        # Calculate a simple pass ratio for Confidence Scoring
        total = len(results)
        passed = sum(1 for v in results.values() if v == "PASS")
        pass_ratio = passed / total if total > 0 else 0.0

        return {
            "statuses": results,
            "pass_ratio": pass_ratio
        }

policy_validator = PolicyValidator()

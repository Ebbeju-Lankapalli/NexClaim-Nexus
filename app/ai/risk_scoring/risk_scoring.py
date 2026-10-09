"""
Risk Scoring Engine.
Uses a Logistic Regression model to assess claim risk based on extracted features.
Model is dynamically trained on realistic synthetic data for the DSS MVP.
"""

import logging
import numpy as np
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger(__name__)

class RiskScorer:
    def __init__(self):
        self.model = LogisticRegression(random_state=42, class_weight='balanced')
        self._train_mock_model()
        
    def _train_mock_model(self):
        """
        Train the model with synthetic data simulating real insurance patterns.
        Features order:
        1. coverage_utilization_ratio (0.0 - 2.0+)
        2. document_completeness (0.0 - 1.0)
        3. policy_age_days (0 - 5000)
        4. waiting_period_completed (0 or 1)
        5. field_consistency (0.0 - 1.0)
        6. ocr_quality (0.0 - 1.0)
        7. extraction_confidence (0.0 - 1.0)
        8. historical_frequency (0 - 10)
        """
        # Feature Matrix (X) and Labels (y) (0 = Low Risk, 1 = High Risk)
        # We define intuitive rules for the synthetic data:
        X = [
            # Low Risk Profiles
            [0.1, 1.0, 1500, 1, 1.0, 0.95, 0.90, 0],  # Perfect claim
            [0.3, 1.0, 800, 1, 0.9, 0.85, 0.88, 1],   # Normal claim
            [0.5, 0.9, 1200, 1, 1.0, 0.90, 0.92, 0],  # Half utilization
            [0.2, 1.0, 300, 1, 0.9, 0.90, 0.85, 0],   # Young policy but solid
            
            # High Risk Profiles
            [0.95, 0.5, 30, 0, 0.4, 0.40, 0.50, 4],   # Very new, incomplete, mismatched, frequent
            [1.2, 0.7, 150, 1, 0.6, 0.65, 0.60, 2],   # Over limit, inconsistent
            [0.8, 1.0, 45, 0, 0.9, 0.80, 0.80, 0],    # Under waiting period
            [0.99, 0.8, 400, 1, 0.2, 0.85, 0.55, 3],  # Severe inconsistencies
        ]
        
        y = [0, 0, 0, 0, 1, 1, 1, 1]
        
        self.model.fit(X, y)

    def calculate_risk(
        self,
        claim_amount: float,
        coverage_amount: float,
        submitted_docs: int,
        required_docs: int,
        policy_age_days: int,
        waiting_period_completed: int,
        field_consistency_score: float,
        ocr_quality_score: float,
        extraction_confidence_score: float,
        historical_claim_frequency: int
    ) -> dict:
        
        # Calculate derived features safely
        coverage_ratio = claim_amount / coverage_amount if coverage_amount > 0 else 1.0
        doc_completeness = submitted_docs / required_docs if required_docs > 0 else 1.0
        
        # Cap ratios for model stability
        coverage_ratio = min(coverage_ratio, 2.0)
        doc_completeness = min(doc_completeness, 1.0)
        
        features = [
            coverage_ratio,
            doc_completeness,
            policy_age_days,
            waiting_period_completed,
            field_consistency_score,
            ocr_quality_score,
            extraction_confidence_score,
            historical_claim_frequency
        ]
        
        # Predict probability of class 1 (High Risk)
        X_input = np.array([features])
        prob = self.model.predict_proba(X_input)[0][1]
        
        # Determine band
        if prob <= 0.30:
            category = "LOW RISK"
        elif prob <= 0.70:
            category = "MEDIUM RISK"
        else:
            category = "HIGH RISK"
            
        return {
            "probability": round(prob, 4),
            "category": category,
            "features": {
                "coverage_utilization_ratio": round(coverage_ratio, 2),
                "document_completeness_score": round(doc_completeness, 2),
                "policy_age_days": policy_age_days,
                "waiting_period_completed": waiting_period_completed,
                "field_consistency_score": round(field_consistency_score, 2),
                "ocr_quality_score": round(ocr_quality_score, 2),
                "extraction_confidence_score": round(extraction_confidence_score, 2),
                "historical_claim_frequency": historical_claim_frequency
            }
        }

risk_scorer = RiskScorer()

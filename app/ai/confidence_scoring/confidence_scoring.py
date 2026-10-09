"""
NexClaim Confidence Scoring Module.

Computes an overall confidence score (0-100%) based on OCR quality,
extraction completeness, and policy match quality.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Weight allocations (must sum to 1.0)
WEIGHT_OCR_QUALITY = 0.30
WEIGHT_EXTRACTION_COMPLETENESS = 0.35
WEIGHT_POLICY_MATCH = 0.20
WEIGHT_VALIDATION_PASS_RATE = 0.15

REQUIRED_CLAIM_FIELDS = [
    "policy_number",
    "patient_name",
    "hospital_name",
    "diagnosis",
    "admission_date",
    "discharge_date",
    "claim_amount",
]


class ConfidenceScorer:
    """Calculates overall claim processing confidence score."""

    def score(
        self,
        ocr_quality_scores: list[float],
        extracted_fields: dict,
        policy_found: bool,
        validation: dict,
    ) -> float:
        """
        Compute confidence score as a weighted average.

        Args:
            ocr_quality_scores: List of quality scores from each document
            extracted_fields: Dict of extracted field values
            policy_found: Whether a matching policy was found in DB
            validation: Validation result dict

        Returns:
            Confidence score between 0.0 and 1.0
        """
        ocr_quality = self._average_ocr_quality(ocr_quality_scores)
        extraction_completeness = self._compute_extraction_completeness(extracted_fields)
        policy_match = 1.0 if policy_found else 0.0
        validation_pass_rate = self._compute_validation_pass_rate(validation)

        confidence = (
            WEIGHT_OCR_QUALITY * ocr_quality
            + WEIGHT_EXTRACTION_COMPLETENESS * extraction_completeness
            + WEIGHT_POLICY_MATCH * policy_match
            + WEIGHT_VALIDATION_PASS_RATE * validation_pass_rate
        )

        confidence = max(0.0, min(1.0, confidence))

        logger.info(
            "Confidence scoring: ocr=%.2f, extraction=%.2f, policy_match=%.2f, validation=%.2f → final=%.2f",
            ocr_quality,
            extraction_completeness,
            policy_match,
            validation_pass_rate,
            confidence,
        )

        return round(confidence, 4)

    @staticmethod
    def _average_ocr_quality(scores: list[float]) -> float:
        """Average OCR quality scores across documents."""
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    @staticmethod
    def _compute_extraction_completeness(fields: dict) -> float:
        """Compute extraction completeness based on required fields present."""
        if not fields:
            return 0.0
        filled = sum(
            1 for field in REQUIRED_CLAIM_FIELDS
            if fields.get(field) not in (None, "", 0, 0.0)
        )
        return filled / len(REQUIRED_CLAIM_FIELDS)

    @staticmethod
    def _compute_validation_pass_rate(validation: dict) -> float:
        """Compute the fraction of validation checks that passed."""
        checks = [
            "is_policy_active",
            "is_premium_paid",
            "is_disease_covered",
            "is_within_limit",
            "is_waiting_period_met",
        ]
        if not validation:
            return 0.0
        passed = sum(1 for c in checks if validation.get(c, False))
        return passed / len(checks)


confidence_scorer = ConfidenceScorer()

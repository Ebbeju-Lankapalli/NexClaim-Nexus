"""
Confidence Scoring Engine.
Calculates a unified confidence score based on OCR, extraction, validation, and completeness metrics.
"""

from typing import Dict, Any

class ConfidenceScorer:
    def __init__(self):
        # Weights for the formula
        self.weights = {
            "ocr_quality": 0.25,
            "extraction_quality": 0.25,
            "consistency": 0.20,
            "validation_success": 0.20,
            "completeness": 0.10
        }

    def calculate(
        self,
        ocr_confidence: float,
        extraction_confidence: float,
        consistency_score: float,
        validation_pass_ratio: float,
        document_completeness: float
    ) -> Dict[str, Any]:
        """
        Calculate the overall confidence score based on evidence factors.
        All input values should be normalized floats between 0.0 and 1.0.
        """
        ocr_component = ocr_confidence * self.weights["ocr_quality"]
        extraction_component = extraction_confidence * self.weights["extraction_quality"]
        consistency_component = consistency_score * self.weights["consistency"]
        validation_component = validation_pass_ratio * self.weights["validation_success"]
        completeness_component = document_completeness * self.weights["completeness"]
        
        total_score = (
            ocr_component +
            extraction_component +
            consistency_component +
            validation_component +
            completeness_component
        )
        
        # Ensure it's between 0 and 1
        total_score = max(0.0, min(1.0, total_score))
        
        percentage = round(total_score * 100, 2)
        
        explanation = {
            "score_percentage": percentage,
            "breakdown": {
                "ocr_quality": {
                    "value": round(ocr_confidence * 100, 2),
                    "weight": f"{int(self.weights['ocr_quality'] * 100)}%",
                    "contribution": round(ocr_component * 100, 2)
                },
                "extraction_quality": {
                    "value": round(extraction_confidence * 100, 2),
                    "weight": f"{int(self.weights['extraction_quality'] * 100)}%",
                    "contribution": round(extraction_component * 100, 2)
                },
                "consistency": {
                    "value": round(consistency_score * 100, 2),
                    "weight": f"{int(self.weights['consistency'] * 100)}%",
                    "contribution": round(consistency_component * 100, 2)
                },
                "validation_success": {
                    "value": round(validation_pass_ratio * 100, 2),
                    "weight": f"{int(self.weights['validation_success'] * 100)}%",
                    "contribution": round(validation_component * 100, 2)
                },
                "document_completeness": {
                    "value": round(document_completeness * 100, 2),
                    "weight": f"{int(self.weights['completeness'] * 100)}%",
                    "contribution": round(completeness_component * 100, 2)
                }
            }
        }
        
        return explanation

confidence_scorer = ConfidenceScorer()

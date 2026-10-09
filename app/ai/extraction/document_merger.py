"""
Document Merger.
Consolidates extracted fields from multiple documents into a single set of 'best' values.
"""

from typing import Dict, Any
from app.ai.document_classifier.document_types import DocumentClass

class DocumentMerger:
    def __init__(self):
        # Lower index = higher priority
        self.doc_priority = [
            DocumentClass.POLICY_DOCUMENT,
            DocumentClass.CLAIM_FORM,
            DocumentClass.DISCHARGE_SUMMARY,
            DocumentClass.HOSPITAL_BILL,
            DocumentClass.MEDICAL_REPORT,
            DocumentClass.LAB_REPORT,
            DocumentClass.PRESCRIPTION,
            DocumentClass.UNKNOWN
        ]

    def _get_priority(self, doc_class: str) -> int:
        try:
            enum_class = DocumentClass(doc_class)
            return self.doc_priority.index(enum_class)
        except ValueError:
            return 99

    def merge(self, multi_doc_extractions: Dict[str, Dict[str, Any]], doc_classes: Dict[str, str]) -> Dict[str, Any]:
        """
        Merge values choosing Highest Confidence first, then Document Priority.
        """
        consolidated = {}
        
        # Organize by field
        field_candidates = {}
        for filename, extractions in multi_doc_extractions.items():
            doc_class = doc_classes.get(filename, "UNKNOWN")
            for field_name, field_data in extractions.items():
                if field_name not in field_candidates:
                    field_candidates[field_name] = []
                
                field_candidates[field_name].append({
                    "value": field_data["value"],
                    "confidence": field_data.get("confidence", 0.0),
                    "document": filename,
                    "doc_class": doc_class,
                    "method": field_data.get("method", "unknown")
                })
                
        # Select best candidate for each field
        for field_name, candidates in field_candidates.items():
            if not candidates:
                continue
                
            # Sort by confidence (descending), then by priority (ascending)
            candidates.sort(key=lambda c: (-c["confidence"], self._get_priority(c["doc_class"])))
            
            best_candidate = candidates[0]
            
            # Format explainability output
            consolidated[field_name] = {
                "value": best_candidate["value"],
                "confidence": best_candidate["confidence"],
                "source_document": best_candidate["document"],
                "extraction_method": best_candidate["method"]
            }
            
        return consolidated

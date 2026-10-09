"""
Intelligent Document Classifier.
Classifies documents based on filenames and OCR keyword heuristics.
"""

import logging
import re
from pathlib import Path
from .document_types import DocumentClass

logger = logging.getLogger(__name__)

class DocumentClassifier:
    
    KEYWORD_MAPPING = {
        DocumentClass.POLICY_DOCUMENT: [
            r"\bpolicy\s*(number|schedule|document)\b",
            r"\bcoverage\s*(limit|details)\b",
            r"\bwaiting\s*period\b",
            r"\bexclusions\b",
            r"\bsum\s*insured\b",
            r"\bpremium\s*receipt\b"
        ],
        DocumentClass.CLAIM_FORM: [
            r"\bclaim\s*form\b",
            r"\bpart\s*[ab]\b",
            r"\bdeclaration\s*by\s*the\s*insured\b",
            r"\bdetails\s*of\s*primary\s*insured\b",
            r"\bclaimant\s*details\b"
        ],
        DocumentClass.HOSPITAL_BILL: [
            r"\b(hospital\s*)?invoice\b",
            r"\bamount\s*payable\b",
            r"\btotal\s*charges\b",
            r"\bnet\s*amount\b",
            r"\bbill\s*no\b",
            r"\bpharmacy\s*bill\b",
            r"\broom\s*rent\b"
        ],
        DocumentClass.DISCHARGE_SUMMARY: [
            r"\bdischarge\s*summary\b",
            r"\badmission\s*date\b",
            r"\bdischarge\s*date\b",
            r"\bcourse\s*in\s*hospital\b",
            r"\bcondition\s*at\s*discharge\b",
            r"\bchief\s*complaints?\b"
        ],
        DocumentClass.PRESCRIPTION: [
            r"\bprescription\b",
            r"\brx\b",
            r"\bmedicine\s*name\b",
            r"\bdosage\b",
            r"\btab(let)?s?\b",
            r"\bcap(sule)?s?\b"
        ],
        DocumentClass.MEDICAL_REPORT: [
            r"\bmedical\s*report\b",
            r"\bclinical\s*notes\b",
            r"\bconsultation\s*report\b"
        ],
        DocumentClass.LAB_REPORT: [
            r"\blab(oratory)?\s*report\b",
            r"\bpathology\b",
            r"\btest\s*result\b",
            r"\bhaemoglobin\b",
            r"\bblood\s*test\b"
        ]
    }

    def __init__(self):
        self.compiled_rules = {
            doc_class: [re.compile(p, re.IGNORECASE) for p in patterns]
            for doc_class, patterns in self.KEYWORD_MAPPING.items()
        }

    def classify_by_filename(self, filename: str) -> DocumentClass:
        """Attempt quick classification via filename."""
        name = filename.lower()
        if "policy" in name: return DocumentClass.POLICY_DOCUMENT
        if "claim" in name and "form" in name: return DocumentClass.CLAIM_FORM
        if "bill" in name or "invoice" in name: return DocumentClass.HOSPITAL_BILL
        if "discharge" in name: return DocumentClass.DISCHARGE_SUMMARY
        if "prescription" in name or "rx" in name: return DocumentClass.PRESCRIPTION
        if "report" in name and "lab" in name: return DocumentClass.LAB_REPORT
        if "report" in name: return DocumentClass.MEDICAL_REPORT
        return DocumentClass.UNKNOWN

    def classify_by_text(self, text: str) -> DocumentClass:
        """Classify by scanning text for heuristic keywords."""
        if not text:
            return DocumentClass.UNKNOWN
            
        scores = {doc_class: 0 for doc_class in DocumentClass}
        
        # Increase score based on regex matches
        for doc_class, patterns in self.compiled_rules.items():
            for pattern in patterns:
                matches = pattern.findall(text)
                scores[doc_class] += len(matches)

        # Find the class with the maximum score
        best_class = max(scores, key=scores.get)
        if scores[best_class] > 0:
            logger.info("Classified as %s with score %d", best_class.value, scores[best_class])
            return best_class
            
        return DocumentClass.UNKNOWN

    def classify(self, filename: str, text: str) -> DocumentClass:
        """Combine filename and text hints to classify the document."""
        # Prioritize text if available
        text_class = self.classify_by_text(text)
        if text_class != DocumentClass.UNKNOWN:
            return text_class
            
        return self.classify_by_filename(filename)

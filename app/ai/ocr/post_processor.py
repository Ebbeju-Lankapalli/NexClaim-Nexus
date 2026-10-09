"""
OCR Post-Processor for artifact correction and spell checking.
"""

import logging
import re
try:
    from spellchecker import SpellChecker
except ImportError:
    SpellChecker = None

logger = logging.getLogger(__name__)

class OCRPostProcessor:
    def __init__(self):
        self.spell = SpellChecker() if SpellChecker else None
        
        # Common OCR artifact replacements (dictionary mapping)
        self.artifact_replacements = {
            "CLAlM": "CLAIM",
            "P0LICY": "POLICY",
            "HOSP1TAL": "HOSPITAL",
            "D1SCHARGE": "DISCHARGE",
            "B1LL": "BILL",
            "PREM1UM": "PREMIUM",
            "lNVOICE": "INVOICE",
            "0CR": "OCR"
        }
        
        # If spellchecker is available, add domain specific words
        if self.spell:
            self.spell.word_frequency.load_words([
                "policy", "claim", "hospital", "discharge", "prescription",
                "diagnosis", "admission", "invoice", "reimbursement", "insurer",
                "deductible", "copay", "outpatient", "inpatient", "surgery"
            ])

    def clean_text(self, text: str) -> str:
        """Apply deterministic artifact corrections and basic normalization."""
        if not text:
            return text
            
        # Replace common exact word artifacts
        words = text.split()
        cleaned_words = []
        for w in words:
            # Check exact match stripped of punctuation
            clean_w = re.sub(r'[^\w\s]', '', w)
            if clean_w in self.artifact_replacements:
                w = w.replace(clean_w, self.artifact_replacements[clean_w])
            cleaned_words.append(w)
            
        return " ".join(cleaned_words)

    def process(self, text: str) -> str:
        """Run the full post-processing pipeline on OCR text."""
        # Step 1: Clean known artifacts
        cleaned_text = self.clean_text(text)
        
        # Step 2: Spell correction (if available and needed)
        # Note: Spell correction on entire OCR dumps can be dangerous as it might mangle names or IDs.
        # It's better used selectively or lightly. Here we apply it only to words that are purely alphabetic.
        if self.spell and False: # Disabled full text spell check by default to avoid corrupting names/IDs
            words = cleaned_text.split()
            corrected_words = []
            for w in words:
                if w.isalpha() and w.islower() and len(w) > 3:
                    # Only correct lowercase words that are misspelled
                    if w not in self.spell:
                        corr = self.spell.correction(w)
                        if corr:
                            w = corr
                corrected_words.append(w)
            cleaned_text = " ".join(corrected_words)
            
        return cleaned_text

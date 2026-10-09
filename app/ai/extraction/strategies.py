"""
Multi-Strategy Extraction Engine.
"""

import re
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.ai.extraction.field_registry import ExtractionField, FieldType

try:
    from thefuzz import fuzz
except ImportError:
    fuzz = None

try:
    import spacy
    try:
        nlp = spacy.load("en_core_web_sm")
    except Exception:
        import subprocess
        import sys
        try:
            # Automatically download the model if not present
            subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
            nlp = spacy.load("en_core_web_sm")
        except Exception:
            nlp = None
except ImportError:
    spacy = None
    nlp = None

logger = logging.getLogger(__name__)


class ExtractionStrategy(ABC):
    @abstractmethod
    def extract(self, text: str, field: ExtractionField) -> Optional[Dict[str, Any]]:
        """
        Returns a dict with 'value' and 'confidence' if found, else None.
        """
        pass

    def clean_value(self, value: str, field: ExtractionField) -> Any:
        if field.field_type == FieldType.AMOUNT:
            # We want the FIRST valid number after removing list prefixes
            clean_str = re.sub(r'^[\d\w]{1,2}[\.\)]\s*', '', value.strip())
            matches = re.findall(r'([\d,]+\.?\d*)', clean_str)
            for m in matches:
                m_clean = m.replace(",", "")
                if m_clean.endswith("."):
                    m_clean = m_clean[:-1]
                try:
                    num = float(m_clean)
                    return num
                except ValueError:
                    pass
            return 0.0
            
        val = value.strip()
        if field.field_type == FieldType.STRING:
            # 1. Stop at double spaces (often indicates column gaps in PDFs)
            val = re.split(r'\s{2,}', val)[0]
            
            # 2. Stop at the next likely field key or common stop words (even without colons)
            stop_words = r'(?:Address|Age|Gender|Sex|DOB|Date|Contact|Phone|Email|Mobile|Policy No|Claim No|Door No|Patient No)'
            match_next_field = re.search(r'\s+([A-Za-z][a-zA-Z\s]{2,20}[:\-]\s|' + stop_words + r'\b)', val, flags=re.IGNORECASE)
            if match_next_field:
                val = val[:match_next_field.start()].strip()
                
            # Hard limit for names (rarely exceed 4 words)
            if val and field.name in ["patient_name", "doctor_name"]:
                words = val.split()
                if len(words) > 4:
                    val = " ".join(words[:4])
                    
        return val.strip()


class RegexStrategy(ExtractionStrategy):
    def extract(self, text: str, field: ExtractionField) -> Optional[Dict[str, Any]]:
        if not field.regex_patterns:
            return None
            
        for pattern in field.regex_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                val = match.group(1).strip().rstrip(",.; ")
                return {
                    "value": self.clean_value(val, field),
                    "confidence": 0.95,  # Regex exact matches get high confidence
                    "method": "regex"
                }
        return None


class SpacyStrategy(ExtractionStrategy):
    def extract(self, text: str, field: ExtractionField) -> Optional[Dict[str, Any]]:
        if not nlp:
            return None
            
        doc = nlp(text)
        
        # Map field to expected NER labels
        target_labels = []
        if field.name in ["patient_name", "doctor_name"]:
            target_labels = ["PERSON"]
        elif field.name in ["hospital_name", "insurer_name"]:
            target_labels = ["ORG"]
        elif field.field_type == FieldType.AMOUNT:
            target_labels = ["MONEY", "CARDINAL"]
        elif field.field_type == FieldType.DATE:
            target_labels = ["DATE"]
            
        if not target_labels:
            return None
            
        # Very naive implementation: Find the first entity matching the label 
        # that occurs near a synonym keyword.
        best_ent = None
        min_dist = 9999
        
        for ent in doc.ents:
            if ent.label_ in target_labels:
                # Filter out list indices and small numbers for AMOUNT
                if field.field_type == FieldType.AMOUNT:
                    clean_str = ent.text.replace(",", "").replace(".", "").replace("$", "").replace("Rs", "").strip()
                    if clean_str.isdigit() and len(clean_str) <= 2:
                        continue
                        
                # Find distance to closest synonym
                for syn in field.synonyms:
                    # simple string index distance
                    syn_idx = text.lower().find(syn.lower())
                    if syn_idx != -1:
                        dist = abs(ent.start_char - syn_idx)
                        if dist < min_dist and dist < 100:  # Must be within 100 chars
                            min_dist = dist
                            best_ent = ent.text
                            
        if best_ent:
            # Confidence decreases as distance increases, but start higher to beat keyword fallback
            confidence = max(0.60, 0.95 - (min_dist / 400.0))
            return {
                "value": self.clean_value(best_ent, field),
                "confidence": round(confidence, 2),
                "method": "spacy_ner"
            }
            
        return None


class KeywordStrategy(ExtractionStrategy):
    def extract(self, text: str, field: ExtractionField) -> Optional[Dict[str, Any]]:
        if not fuzz:
            return None
            
        lines = text.split('\n')
        best_match = None
        best_score = 0
        best_line = ""
        
        for line in lines:
            if len(line) < 5: continue
            
            for syn in field.synonyms:
                # fuzz.partial_ratio checks if syn is a substring of line (fuzzy)
                score = fuzz.partial_ratio(syn.lower(), line.lower())
                if score > best_score and score > 85:
                    best_score = score
                    best_line = line
                    
        if best_score > 85:
            # Find the best synonym in the line to bound the extraction
            best_syn = None
            best_syn_idx = -1
            for syn in field.synonyms:
                idx = best_line.lower().find(syn.lower())
                if idx != -1:
                    if best_syn_idx == -1 or idx < best_syn_idx:
                        best_syn_idx = idx
                        best_syn = syn
            
            val = ""
            if best_syn:
                # Text immediately following the synonym
                after_syn = best_line[best_syn_idx + len(best_syn):]
                # Check for an immediate delimiter like ':' or '-'
                match = re.search(r'^[^a-zA-Z0-9]*[:\-]', after_syn)
                if match:
                    val = after_syn[match.end():].strip()
                else:
                    val = after_syn.strip()
            else:
                parts = re.split(r'[:\-]', best_line, maxsplit=1)
                if len(parts) > 1:
                    val = parts[1].strip()
                else:
                    val = best_line.strip()
                    
            # If val is unexpectedly long, cap it
            val = val[:100]
                    
            if val:
                return {
                    "value": self.clean_value(val, field),
                    "confidence": round(best_score / 100.0 * 0.8, 2), # Cap at 0.8 for keyword strategy
                    "method": "fuzzy_keyword"
                }
        return None

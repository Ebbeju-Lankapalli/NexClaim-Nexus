"""
NexClaim Information Extraction Module.

Refactored to orchestrate dynamic multi-strategy extraction
(Regex, SpaCy NER, Keyword/Fuzzy matching) based on a unified Field Registry.
"""

import logging
from typing import Dict, Any

from app.ai.extraction.field_registry import FIELD_REGISTRY
from app.ai.extraction.strategies import RegexStrategy, SpacyStrategy, KeywordStrategy

logger = logging.getLogger(__name__)

class ExtractorEngine:
    def __init__(self):
        self.strategies = [
            RegexStrategy(),
            SpacyStrategy(),
            KeywordStrategy()
        ]

    def extract(self, text: str) -> Dict[str, Dict[str, Any]]:
        """
        Runs all extraction strategies on the provided text for all registered fields.
        Returns a dictionary of extracted fields with explainability metadata.
        """
        results = {}
        
        if not text:
            return results

        for field_name, field_def in FIELD_REGISTRY.items():
            best_result = None
            best_confidence = 0.0
            
            for strategy in self.strategies:
                try:
                    result = strategy.extract(text, field_def)
                    if result and result.get("confidence", 0.0) > best_confidence:
                        best_confidence = result["confidence"]
                        best_result = result
                except Exception as e:
                    logger.warning("Strategy %s failed for field %s: %s", type(strategy).__name__, field_name, e)
                    
            if best_result:
                results[field_name] = best_result
                
        return results

# Singleton instance
extractor_engine = ExtractorEngine()

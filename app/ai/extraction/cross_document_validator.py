"""
Cross Document Validator.
Compares extracted fields across multiple documents to identify inconsistencies.
"""

from typing import Dict, List, Any

class CrossDocumentValidator:
    def validate(self, multi_doc_extractions: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        multi_doc_extractions: {
            "claim_form.pdf": {
                "policy_number": {"value": "123", "confidence": 0.9, ...},
                ...
            },
            "policy.pdf": {
                "policy_number": {"value": "123", "confidence": 0.95, ...},
                ...
            }
        }
        Returns a list of validation flags (inconsistencies).
        """
        flags = []
        
        # Invert the mapping: field_name -> [(filename, value_dict), ...]
        field_sources = {}
        for filename, extractions in multi_doc_extractions.items():
            for field_name, field_data in extractions.items():
                if field_name not in field_sources:
                    field_sources[field_name] = []
                field_sources[field_name].append({
                    "filename": filename,
                    "data": field_data
                })
                
        # Compare values
        for field_name, sources in field_sources.items():
            if len(sources) <= 1:
                continue # Nothing to compare
                
            # Normalize and check equality
            first_val = str(sources[0]["data"]["value"]).strip().lower()
            mismatch_found = False
            
            for source in sources[1:]:
                current_val = str(source["data"]["value"]).strip().lower()
                
                # Special handling for floats/amounts to allow minor rounding differences
                if isinstance(sources[0]["data"]["value"], float) and isinstance(source["data"]["value"], float):
                    if abs(sources[0]["data"]["value"] - source["data"]["value"]) > 1.0:
                        mismatch_found = True
                        break
                elif current_val != first_val:
                    mismatch_found = True
                    break
                    
            if mismatch_found:
                flags.append({
                    "field": field_name,
                    "issue": "Cross-document mismatch",
                    "sources": [
                        {"document": s["filename"], "value": s["data"]["value"]}
                        for s in sources
                    ]
                })
                
        return flags

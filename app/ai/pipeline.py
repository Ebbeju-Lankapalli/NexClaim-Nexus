"""
Master Multi-Document AI Processing Pipeline.
Orchestrates Classification, OCR, Extraction, Validation, Risk, and Brief Generation.
"""

import time
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from datetime import datetime
from app.ai.document_classifier.classifier import DocumentClassifier
from app.ai.ocr.ocr import ocr_processor
from app.ai.extraction.extraction import extractor_engine
from app.ai.extraction.cross_document_validator import CrossDocumentValidator
from app.ai.extraction.document_merger import DocumentMerger

from app.ai.validation.engine import validation_engine
from app.ai.pre_assessment_brief.generator import brief_generator

logger = logging.getLogger(__name__)

class MultiDocumentPipeline:
    def __init__(self):
        self.classifier = DocumentClassifier()
        self.cross_validator = CrossDocumentValidator()
        self.merger = DocumentMerger()

    def extract(self, file_paths: List[str]) -> Dict[str, Any]:
        """Step 1: OCR and Extraction"""
        start_time = time.time()
        
        results = {
            "documents_processed": [],
            "document_types": {},
            "ocr_summary": {
                "pages_processed": 0,
                "average_confidence": 0.0
            },
            "claim_data": {},
            "policy_data": {},
            "hospital_data": {},
            "financial_data": {},
            "missing_fields": [],
            "validation_flags": [],
            "processing_time": 0.0,
            "raw_extractions": {}
        }
        
        multi_doc_extractions = {}
        total_ocr_conf = 0.0
        
        for file_path in file_paths:
            is_url = file_path.startswith("http://") or file_path.startswith("https://")
            
            if not is_url:
                path = Path(file_path)
                if not path.exists():
                    logger.warning(f"File {file_path} not found.")
                    continue
                filename = path.name
            else:
                filename = file_path.split("/")[-1]
                
            results["documents_processed"].append(filename)
            
            # OCR
            text, ocr_conf = ocr_processor.extract_text_from_file(file_path)
            results["ocr_summary"]["pages_processed"] += 1
            total_ocr_conf += ocr_conf
            
            # Classify
            doc_class = self.classifier.classify(filename, text)
            results["document_types"][filename] = doc_class.value
            
            # Extract
            extracted_fields = extractor_engine.extract(text)
            if extracted_fields:
                multi_doc_extractions[filename] = extracted_fields
                
        num_docs = len(results["documents_processed"])
        if num_docs > 0:
            results["ocr_summary"]["average_confidence"] = round(total_ocr_conf / num_docs, 2)
            
        # Cross-Document Validation
        results["validation_flags"] = self.cross_validator.validate(multi_doc_extractions)
        
        # Merge Documents
        consolidated = self.merger.merge(multi_doc_extractions, results["document_types"])
        
        # Calculate extraction average confidence
        total_ext_conf = 0.0
        for f, meta in consolidated.items():
            total_ext_conf += meta.get("confidence", 0.0)
        results["extraction_confidence"] = total_ext_conf / len(consolidated) if consolidated else 0.0
        
        # Calculate field consistency score (percentage of fields without flags)
        flagged_fields = set(flag.get("field") for flag in results["validation_flags"])
        consistent_fields = len(consolidated) - len(flagged_fields)
        results["consistency_score"] = consistent_fields / len(consolidated) if consolidated else 1.0
        
        # Categorize
        for field_name, field_metadata in consolidated.items():
            if field_name in ["patient_name", "age", "gender"]:
                results["claim_data"][field_name] = field_metadata
            elif field_name in ["policy_number", "insurer_name", "coverage_limit"]:
                results["policy_data"][field_name] = field_metadata
            elif field_name in ["hospital_name", "doctor_name", "admission_date", "discharge_date"]:
                results["hospital_data"][field_name] = field_metadata
            elif field_name in ["claim_amount", "invoice_number", "diagnosis"]:
                results["financial_data"][field_name] = field_metadata
            else:
                results["claim_data"][field_name] = field_metadata
                
        # Missing
        required_fields = ["patient_name", "policy_number", "hospital_name", "claim_amount", "diagnosis"]
        results["missing_fields"] = [f for f in required_fields if f not in consolidated]
        
        results["processing_time"] = round(time.time() - start_time, 2)
        return results

    def assess(self, claim: Any, extracted_data: Dict[str, Any], policy: Optional[Any], required_docs_count: int = 2) -> Dict[str, Any]:
        """Step 2: Unified DSS Validation, Risk, and Recommendation"""
        
        submitted_docs = list(extracted_data.get("document_types", {}).values())
        
        # 1. Run Unified Validation Engine
        engine_output = validation_engine.validate(
            extracted_data=extracted_data,
            policy=policy,
            claim=claim,
            submitted_docs=submitted_docs
        )
        
        # 2. Final Brief Generation
        brief = brief_generator.generate(
            claim=claim,
            engine_output=engine_output,
            extracted_data=extracted_data
        )
        
        # We append the raw engine output to the brief so we have access to it downstream
        brief["engine_output"] = engine_output
        
        return brief

ai_pipeline = MultiDocumentPipeline()

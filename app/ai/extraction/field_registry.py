"""
Field Registry for AI Extraction.
Defines all the fields to extract from insurance documents, their expected types,
and synonyms/keywords for dynamic extraction strategies.
"""

from enum import Enum
from typing import Dict, List, Any

class FieldType(Enum):
    STRING = "string"
    AMOUNT = "amount"
    DATE = "date"
    LIST = "list"

class ExtractionField:
    def __init__(self, name: str, field_type: FieldType, synonyms: List[str], regex_patterns: List[str] = None):
        self.name = name
        self.field_type = field_type
        self.synonyms = synonyms
        self.regex_patterns = regex_patterns or []

# ---------------------------------------------------------------------------
# Global Field Registry
# ---------------------------------------------------------------------------

FIELD_REGISTRY = {
    # Patient Information
    "patient_name": ExtractionField(
        name="patient_name",
        field_type=FieldType.STRING,
        synonyms=["patient name", "insured name", "policyholder name", "member name", "name of patient", "name of insured", "name of primary insured", "primary insured name", "client name", "customer name", "proposer name", "name"],
        regex_patterns=[
            r"(?:patient|insured|member|client|customer|proposer)?\s*name\s*[:\-]?\s*([A-Za-z \.]{3,60})",
            r"(?:name\s*of\s*(?:(?:primary\s*)?insured|patient|member|client))\s*[:\-]?\s*([A-Za-z \.]{3,60})"
        ]
    ),
    "age": ExtractionField(
        name="age",
        field_type=FieldType.STRING,
        synonyms=["age", "patient age", "dob", "date of birth", "current age", "years old"],
        regex_patterns=[r"\bage\s*[:\-]?\s*(\d{1,3})\s*(?:yrs|years)?\b"]
    ),
    "gender": ExtractionField(
        name="gender",
        field_type=FieldType.STRING,
        synonyms=["gender", "sex", "m/f"],
        regex_patterns=[r"\b(?:gender|sex)\s*[:\-]?\s*(Male|Female|M|F)\b"]
    ),
    
    # Policy Information
    "policy_number": ExtractionField(
        name="policy_number",
        field_type=FieldType.STRING,
        synonyms=["policy number", "policy id", "policy ref", "insurance number", "member id", "pol no", "certificate number", "cert no", "contract number", "plan number", "agreement number", "uin"],
        regex_patterns=[
            r"(?:policy|certificate|contract|plan)\s*(?:number|no\.?|id|ref|#)[^\w\d\n]*([A-Z0-9\-/]{5,30})",
            r"\bUIN[^\w\d\n]*([A-Z0-9\-/]{5,30})",
            r"\bPOL\s*[:\-]?\s*([A-Z0-9\-]{5,20})\b"
        ]
    ),
    "insurer_name": ExtractionField(
        name="insurer_name",
        field_type=FieldType.STRING,
        synonyms=["insurer name", "insurance company", "issued by", "underwritten by", "company name", "insurance provider", "health insurance company", "carrier"],
        regex_patterns=[r"(?:insurer|insurance\s*company|issued\s*by|underwritten\s*by|company\s*name|provider|carrier)\s*[:\-]?\s*([A-Za-z0-9\s\.&'-]{3,80})"]
    ),
    "coverage_limit": ExtractionField(
        name="coverage_limit",
        field_type=FieldType.AMOUNT,
        synonyms=["sum insured", "coverage limit", "maximum benefit", "sum assured", "cover amount", "limit", "base sum insured", "total sum insured", "limit of coverage", "limit of liability", "max cover", "annual limit", "policy limit", "sum_insured"],
        regex_patterns=[
            r"(?:sum\s*insured|sum\s*assured|coverage\s*limit|maximum\s*benefit|cover\s*amount|policy\s*limit|annual\s*limit|limit\s*of\s*coverage)[^\d\n]*([\d,]+(?:\.\d{1,2})?)",
            r"(?:base|total)?\s*sum\s*insured\s*[:\-]?\s*(?:rs\.?|inr|\$|₹)?\s*([\d,]+(?:\.\d{1,2})?)"
        ]
    ),
    
    # Hospital Information
    "hospital_name": ExtractionField(
        name="hospital_name",
        field_type=FieldType.STRING,
        synonyms=["hospital name", "name of hospital", "facility name", "provider name", "treated at", "admitted to", "clinic name", "medical center", "nursing home", "healthcare facility", "institution"],
        regex_patterns=[
            r"(?:hospital|clinic|facility|provider|institution)\s*name\s*[:\-]?\s*([A-Za-z0-9\s\.,&'-]{3,80})",
            r"(?:treated\s*at|admitted\s*to|hospital)\s*[:\-]?\s*([A-Za-z0-9\s\.,&'-]{3,80})"
        ]
    ),
    "doctor_name": ExtractionField(
        name="doctor_name",
        field_type=FieldType.STRING,
        synonyms=["doctor name", "treating doctor", "physician", "consultant", "surgeon", "attending physician", "medical practitioner", "medical officer"],
        regex_patterns=[r"(?:doctor|dr\.?|physician|consultant|surgeon|practitioner)\s*[:\-]?\s*([A-Za-z \.]{3,60})"]
    ),
    "admission_date": ExtractionField(
        name="admission_date",
        field_type=FieldType.DATE,
        synonyms=["admission date", "date of admission", "admitted on", "doa", "admitted", "admission dt"],
        regex_patterns=[r"(?:admission\s*date|date\s*of\s*admission|admitted\s*on|doa|admitted)\s*[:\-]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})"]
    ),
    "discharge_date": ExtractionField(
        name="discharge_date",
        field_type=FieldType.DATE,
        synonyms=["discharge date", "date of discharge", "discharged on", "dod", "discharged", "discharge dt"],
        regex_patterns=[r"(?:discharge\s*date|date\s*of\s*discharge|discharged\s*on|dod|discharged)\s*[:\-]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})"]
    ),
    
    # Claim Information
    "claim_amount": ExtractionField(
        name="claim_amount",
        field_type=FieldType.AMOUNT,
        synonyms=["claim amount", "amount claimed", "total claimed", "reimbursement amount", "requested amount", "total charges", "total bill", "net amount", "total bill amount", "invoice amount", "receipt amount", "claimed sum", "requested sum"],
        regex_patterns=[
            r"(?:claim|total|billed|invoice|receipt)\s*(?:amount|bill|charges|cost)\s*[:\-]?\s*(?:rs\.?|inr|\$|₹)?\s*([\d,]+(?:\.\d{1,2})?)",
            r"(?:amount\s*claimed|grand\s*total|net\s*amount|amount\s*payable)\s*[:\-]?\s*(?:rs\.?|inr|\$|₹)?\s*([\d,]+(?:\.\d{1,2})?)"
        ]
    ),
    "diagnosis": ExtractionField(
        name="diagnosis",
        field_type=FieldType.STRING,
        synonyms=["diagnosis", "disease", "ailment", "condition", "icd", "illness", "disorder", "principal diagnosis", "primary diagnosis", "provisional diagnosis", "final diagnosis", "nature of illness", "chief complaint"],
        regex_patterns=[
            r"(?:diagnosis|disease|ailment|condition|icd|illness|disorder|complaint)\s*[:\-]?\s*([A-Za-z0-9\s\.,()-]{3,100})",
            r"(?:principal|primary|provisional|final)\s*diagnosis\s*[:\-]?\s*([A-Za-z0-9\s\.,()-]{3,100})"
        ]
    ),
    "invoice_number": ExtractionField(
        name="invoice_number",
        field_type=FieldType.STRING,
        synonyms=["invoice no", "bill no", "receipt no", "invoice #", "bill #"],
        regex_patterns=[
            r"(?:invoice|bill|receipt)\s*(?:no\.?|number|#)\s*[:\-]?\s*([A-Za-z0-9\-/]{3,20})"
        ]
    ),
    "policy_name": ExtractionField(
        name="policy_name",
        field_type=FieldType.STRING,
        synonyms=["product name", "policy name", "plan name", "type of policy", "insurance plan", "product"],
        regex_patterns=[
            r"(?:product|policy|plan)\s*name\s*[:\-]?\s*([A-Za-z0-9\s\-\(\)]+?)(?:\sUIN|\sPolicy Number|\sPlan|\sNo|$)"
        ]
    ),
    "waiting_period_days": ExtractionField(
        name="waiting_period_days",
        field_type=FieldType.STRING,
        synonyms=["waiting period", "initial waiting period", "specified disease waiting period", "pre-existing disease waiting period"],
        regex_patterns=[
            r"waiting\s*period[^\d\n]*([\d]+\s*(?:months?|days?|years?))",
            r"([\d]+\s*(?:months?|days?|years?))\s*waiting\s*period"
        ]
    )
}

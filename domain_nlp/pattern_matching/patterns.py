"""
Domain-specific regex patterns for structured data extraction.
"""

# Medical domain patterns
MEDICAL_PATTERNS = {
    "icd10_code": {
        "pattern": r'\b([A-Z]\d{2}(?:\.\d{1,4})?)\b',
        "description": "ICD-10 diagnosis code",
        "examples": ["J45.0", "E11.9", "M79.3"],
        "validation": r'^[A-Z]\d{2}(\.\d{1,4})?$',
        "priority": "high"
    },
    "icd9_code": {
        "pattern": r'\b(\d{3}(?:\.\d{1,2})?)\b',
        "description": "ICD-9 diagnosis code",
        "examples": ["250.00", "401.9", "786.2"],
        "validation": r'^\d{3}(\.\d{1,2})?$',
        "priority": "medium"
    },
    "cpt_code": {
        "pattern": r'\b((?:99\d{3}|[1-9]\d{4})[A-Z]?)\b',
        "description": "CPT procedure code",
        "examples": ["99213", "43239", "70553"],
        "priority": "high"
    },
    "ndc_code": {
        "pattern": r'\b(\d{4,5}-\d{3,4}-\d{1,2}|\d{11})\b',
        "description": "National Drug Code",
        "examples": ["0002-1433-01", "00002143301"],
        "priority": "high"
    },
    "dosage": {
        "pattern": r'\b(\d+(?:\.\d+)?)\s*(mg|g|ml|mL|mcg|µg|units?|IU|mEq)\b',
        "description": "Drug dosage with units",
        "examples": ["10 mg", "500 mcg", "2.5 ml"],
        "priority": "high"
    },
    "frequency": {
        "pattern": r'\b((?:once|twice|three times|four times|[1-4]x?)\s+(?:daily|a day|per day|weekly|monthly)|(?:q\.?\s*\d+\s*h(?:ours?)?|qd|bid|tid|qid|prn|qhs|ac|pc))\b',
        "description": "Medication frequency",
        "examples": ["twice daily", "q.8h", "bid", "prn"],
        "priority": "high",
        "case_insensitive": True
    },
    "route": {
        "pattern": r'\b(IV|IM|PO|SQ|SC|PR|topical|oral|sublingual|transdermal|inhaled|intrathecal|epidural)\b',
        "description": "Route of administration",
        "examples": ["IV", "PO", "topical"],
        "priority": "medium",
        "case_insensitive": True
    },
    "vital_sign": {
        "pattern": r'\b(?:BP|HR|RR|SpO2|Temp|O2\s+sat)[:=\s]+(\d+(?:[/\.]\d+)?(?:\s*(?:%|bpm|mmHg|°[FC]))?)\b',
        "description": "Vital sign measurement",
        "examples": ["BP 120/80", "HR 72 bpm", "SpO2 98%"],
        "priority": "medium"
    },
    "lab_value": {
        "pattern": r'\b([A-Za-z]+)[:=\s]+(\d+(?:\.\d+)?)\s*(mg/dL|g/dL|mEq/L|mmol/L|U/L|ng/mL|pg/mL|%|x10\^9/L)\b',
        "description": "Laboratory test result",
        "examples": ["Glucose: 95 mg/dL", "Hemoglobin 14.2 g/dL"],
        "priority": "medium"
    }
}

# Legal domain patterns
LEGAL_PATTERNS = {
    "usc_citation": {
        "pattern": r'\b(\d+)\s+U\.?S\.?C\.?\s+(?:§|section|sec\.?)\s*(\d+[a-z]?(?:\([a-z\d]+\))?)\b',
        "description": "United States Code citation",
        "examples": ["18 U.S.C. § 1001", "42 U.S.C. section 1983"],
        "priority": "high",
        "case_insensitive": True
    },
    "cfr_citation": {
        "pattern": r'\b(\d+)\s+C\.?F\.?R\.?\s+(?:§|section|sec\.?|part)?\s*(\d+(?:\.\d+)?)\b',
        "description": "Code of Federal Regulations citation",
        "examples": ["29 C.F.R. § 1910.134", "21 CFR part 11"],
        "priority": "high",
        "case_insensitive": True
    },
    "case_citation": {
        "pattern": r'\b([A-Z][a-zA-Z\s\'-]+)\s+v\.?\s+([A-Z][a-zA-Z\s\'-]+),?\s+(\d+)\s+([A-Z][a-zA-Z\.\s]+)\s+(\d+)(?:\s+\((\d{4})\))?\b',
        "description": "Case law citation",
        "examples": ["Brown v. Board of Education, 347 U.S. 483 (1954)", "Miranda v. Arizona, 384 U.S. 436"],
        "priority": "high"
    },
    "federal_register": {
        "pattern": r'\b(\d+)\s+Fed\.?\s*Reg\.?\s+(\d+(?:,\d+)?)\b',
        "description": "Federal Register citation",
        "examples": ["85 Fed. Reg. 12345", "88 FR 50123"],
        "priority": "medium"
    },
    "public_law": {
        "pattern": r'\bPub(?:lic)?\.?\s*L(?:aw)?\.?\s+No\.?\s*(\d+-\d+)\b',
        "description": "Public Law number",
        "examples": ["Pub. L. No. 116-136", "Public Law 117-2"],
        "priority": "high",
        "case_insensitive": True
    },
    "statute_section": {
        "pattern": r'\b(?:§|section|sec\.?)\s*(\d+[a-z]?(?:\([a-z\d]+\))*)\b',
        "description": "Generic statute section reference",
        "examples": ["§ 101(a)(3)", "section 230"],
        "priority": "medium",
        "case_insensitive": True
    },
    "court_name": {
        "pattern": r'\b((?:Supreme Court|Circuit Court|District Court|Court of Appeals|Bankruptcy Court|Tax Court)(?:\s+(?:of|for)\s+[A-Za-z\s]+)?)\b',
        "description": "Federal court name",
        "examples": ["Supreme Court of the United States", "District Court for the Southern District of New York"],
        "priority": "medium"
    },
    "legal_date": {
        "pattern": r'\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\b',
        "description": "Legal document date",
        "examples": ["January 6, 2021", "03/15/2024"],
        "priority": "low"
    }
}

# Financial domain patterns
FINANCIAL_PATTERNS = {
    "ticker_symbol": {
        "pattern": r'\b([A-Z]{1,5})\b(?=\s+(?:stock|shares|ticker|NYSE|NASDAQ|price)|\$\d)',
        "description": "Stock ticker symbol",
        "examples": ["AAPL stock", "MSFT shares"],
        "priority": "high"
    },
    "stock_exchange": {
        "pattern": r'\b(NYSE|NASDAQ|AMEX|LSE|TSX|ASX|HKEX|TSE|BSE|NSE)\b',
        "description": "Stock exchange name",
        "examples": ["NYSE", "NASDAQ"],
        "priority": "medium"
    },
    "currency_amount": {
        "pattern": r'(?:\$|USD|EUR|GBP|JPY|CAD|AUD|CHF)\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:million|billion|trillion|M|B|T)?',
        "description": "Currency amount with symbol",
        "examples": ["$1,234.56", "EUR 500 million", "$2.5B"],
        "priority": "high"
    },
    "percentage": {
        "pattern": r'\b(\d+(?:\.\d+)?)\s*%\b',
        "description": "Percentage value",
        "examples": ["5.25%", "100%", "0.5%"],
        "priority": "medium"
    },
    "fiscal_year": {
        "pattern": r'\bFY\s*(?:\')?(\d{2}(?:\d{2})?)\b',
        "description": "Fiscal year reference",
        "examples": ["FY'23", "FY2024", "FY 21"],
        "priority": "medium"
    },
    "quarter": {
        "pattern": r'\b(Q[1-4])\s*(?:\')?(\d{2}(?:\d{2})?)\b',
        "description": "Fiscal quarter",
        "examples": ["Q1 2024", "Q4'23"],
        "priority": "medium"
    },
    "earnings_metric": {
        "pattern": r'\b(EPS|P/E|EBITDA|ROE|ROI|ROA|CAGR|YoY|QoQ|MoM)\b',
        "description": "Financial metric acronym",
        "examples": ["EPS", "P/E ratio", "EBITDA margin"],
        "priority": "medium"
    },
    "cusip": {
        "pattern": r'\b([0-9A-Z]{9})\b',
        "description": "CUSIP security identifier",
        "examples": ["037833100", "594918104"],
        "priority": "low",
        "validation": r'^[0-9A-Z]{9}$'
    },
    "isin": {
        "pattern": r'\b([A-Z]{2}[A-Z0-9]{9}\d)\b',
        "description": "International Securities Identification Number",
        "examples": ["US0378331005", "GB00B03MLX29"],
        "priority": "low"
    }
}

# General patterns applicable across domains
GENERAL_PATTERNS = {
    "email": {
        "pattern": r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b',
        "description": "Email address",
        "priority": "medium"
    },
    "phone_us": {
        "pattern": r'\b(?:\+?1[-.\s]?)?(?:\([0-9]{3}\)|[0-9]{3})[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
        "description": "US phone number",
        "priority": "medium"
    },
    "url": {
        "pattern": r'\bhttps?://[^\s<>"{}|\\^`\[\]]+\b',
        "description": "URL",
        "priority": "low"
    },
    "date_iso": {
        "pattern": r'\b(\d{4}-\d{2}-\d{2})\b',
        "description": "ISO date format",
        "priority": "low"
    }
}

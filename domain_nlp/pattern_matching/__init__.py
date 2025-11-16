"""
Pattern Matching Library for Structured Data Extraction

Extracts domain-specific structured entities using regex patterns:
- Medical: ICD codes, CPT codes, dosages
- Legal: Statute citations, case citations, CFR references
- Financial: Ticker symbols, monetary values
"""

from .matcher import DomainPatternMatcher, StructuredEntity, PatternRule
from .patterns import MEDICAL_PATTERNS, LEGAL_PATTERNS, FINANCIAL_PATTERNS

__all__ = [
    "DomainPatternMatcher",
    "StructuredEntity",
    "PatternRule",
    "MEDICAL_PATTERNS",
    "LEGAL_PATTERNS",
    "FINANCIAL_PATTERNS"
]

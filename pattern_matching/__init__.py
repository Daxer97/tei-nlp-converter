"""
Pattern Matching Module

This module provides pattern-based extraction of structured data that
NER models might miss, such as:
- Medical codes (ICD-10, CPT)
- Legal citations (USC, case law, CFR)
- Dosages and routes of administration
- Measurements and lab values

The pattern matching system is context-aware and includes validation
and normalization capabilities.

Quick Start:
    from pattern_matching import DomainPatternMatcher

    # Initialize and configure
    matcher = DomainPatternMatcher()
    matcher.initialize(domains=["medical", "legal"])

    # Extract patterns
    matches = matcher.extract_patterns(text)

    # Auto-detect domain
    matches = matcher.extract_with_auto_domain(text)
"""

# Base classes and enums
from .base import (
    PatternType,
    Priority,
    Pattern,
    PatternMatch,
    ValidationResult,
    PatternMatcher,
    ContextAwarePatternMatcher
)

# Domain-specific matchers
from .medical import MedicalPatternMatcher
from .legal import LegalPatternMatcher

# Registry and high-level interface
from .registry import (
    PatternMatcherRegistry,
    RegistryStats,
    get_global_registry,
    reset_global_registry
)

from .domain_matcher import DomainPatternMatcher

__all__ = [
    # Base classes
    "PatternType",
    "Priority",
    "Pattern",
    "PatternMatch",
    "ValidationResult",
    "PatternMatcher",
    "ContextAwarePatternMatcher",

    # Domain matchers
    "MedicalPatternMatcher",
    "LegalPatternMatcher",

    # Registry
    "PatternMatcherRegistry",
    "RegistryStats",
    "get_global_registry",
    "reset_global_registry",

    # High-level interface
    "DomainPatternMatcher",
]

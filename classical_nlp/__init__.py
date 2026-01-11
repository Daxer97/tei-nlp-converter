"""
Classical NLP Module for Latin and Ancient Greek Text Processing

This module provides specialized NLP processing for classical languages,
with a focus on:
- Latin (particularly Virgil's works and botanical texts)
- Ancient Greek

Features:
- Automatic language detection
- Multiple NLP model support (LatinCy, CLTK)
- Specialized TEI generation with botanical annotations
- Occurrence search with multiple modes
- HTML report generation with word clouds
"""

from .language_detector import ClassicalLanguageDetector, detect_classical_language
from .models import (
    ClassicalNLPProvider,
    LatinCyProvider,
    CLTKLatinProvider,
    CLTKGreekProvider,
    get_provider_for_language,
    get_available_models
)
from .tei import (
    ClassicalTEIGenerator,
    LatinTEIGenerator,
    GreekTEIGenerator,
    create_tei_generator
)
from .search import (
    OccurrenceSearcher,
    SearchConfig,
    SearchResult,
    SearchMode
)
from .export import (
    HTMLReportGenerator,
    generate_occurrence_report
)

__version__ = "1.0.0"
__all__ = [
    # Language Detection
    "ClassicalLanguageDetector",
    "detect_classical_language",
    # NLP Providers
    "ClassicalNLPProvider",
    "LatinCyProvider",
    "CLTKLatinProvider",
    "CLTKGreekProvider",
    "get_provider_for_language",
    "get_available_models",
    # TEI Generation
    "ClassicalTEIGenerator",
    "LatinTEIGenerator",
    "GreekTEIGenerator",
    "create_tei_generator",
    # Search
    "OccurrenceSearcher",
    "SearchConfig",
    "SearchResult",
    "SearchMode",
    # Export
    "HTMLReportGenerator",
    "generate_occurrence_report",
]

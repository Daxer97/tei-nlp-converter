"""
Classical NLP Model Providers

Provides unified interface for different NLP models:
- LatinCy (spaCy-based Latin model)
- CLTK Latin (Classical Language Toolkit)
- CLTK Greek (Classical Language Toolkit for Ancient Greek)
"""

from .base import ClassicalNLPProvider, ClassicalProcessingResult, BotanicalTerm
from .latincy_provider import LatinCyProvider
from .cltk_provider import CLTKLatinProvider, CLTKGreekProvider
from .registry import get_provider_for_language, get_available_models, ModelRegistry

__all__ = [
    "ClassicalNLPProvider",
    "ClassicalProcessingResult",
    "BotanicalTerm",
    "LatinCyProvider",
    "CLTKLatinProvider",
    "CLTKGreekProvider",
    "get_provider_for_language",
    "get_available_models",
    "ModelRegistry",
]

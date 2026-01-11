"""
TEI Generators for Classical Languages

Provides specialized TEI XML generation for:
- Latin texts (with botanical annotations for Virgil project)
- Ancient Greek texts (with dialect annotations)
"""

from .base import ClassicalTEIGenerator
from .latin_tei import LatinTEIGenerator
from .greek_tei import GreekTEIGenerator
from .factory import create_tei_generator, TEIGeneratorFactory

__all__ = [
    "ClassicalTEIGenerator",
    "LatinTEIGenerator",
    "GreekTEIGenerator",
    "create_tei_generator",
    "TEIGeneratorFactory",
]

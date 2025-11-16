"""
Dynamic NLP Processing Pipeline

Orchestrates:
- Multi-model entity extraction with ensemble merging
- Knowledge base enrichment with fallback chains
- Pattern matching for structured data
- Self-optimization based on performance metrics
"""

from .dynamic_pipeline import DynamicNLPPipeline, EnrichedDocument
from .ensemble import EnsembleMerger

__all__ = [
    "DynamicNLPPipeline",
    "EnrichedDocument",
    "EnsembleMerger"
]

"""
Domain-Specific NLP Architecture

A production-grade, dynamically scalable NLP system with:
- Provider-agnostic model registry
- Streaming knowledge base integration
- Self-optimizing pipeline with ensemble merging
- Hot-swappable components
"""

__version__ = "1.0.0"

from .model_providers.base import NERModelProvider, ModelMetadata, ModelCapabilities
from .knowledge_bases.base import KnowledgeBaseProvider, KBMetadata, KBEntity
from .pipeline.dynamic_pipeline import DynamicNLPPipeline
from .config.loader import ConfigurationLoader

__all__ = [
    "NERModelProvider",
    "ModelMetadata",
    "ModelCapabilities",
    "KnowledgeBaseProvider",
    "KBMetadata",
    "KBEntity",
    "DynamicNLPPipeline",
    "ConfigurationLoader"
]

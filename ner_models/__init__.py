"""
Dynamic NER Model Management System

This module provides infrastructure for:
- Dynamic model discovery and loading
- Provider-agnostic model registry
- Model performance tracking
- Hot-swapping capabilities
"""

from ner_models.base import (
    NERModel,
    ModelMetadata,
    ModelCapabilities,
    ModelPerformanceMetrics,
    Entity
)
from ner_models.registry import ModelProviderRegistry, NERModelProvider
from ner_models.catalog import ModelCatalog

__all__ = [
    'NERModel',
    'ModelMetadata',
    'ModelCapabilities',
    'ModelPerformanceMetrics',
    'Entity',
    'ModelProviderRegistry',
    'NERModelProvider',
    'ModelCatalog'
]

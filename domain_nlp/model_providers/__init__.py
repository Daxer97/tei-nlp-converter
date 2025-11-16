"""
Model Provider Registry

Supports dynamic discovery and loading of NER models from:
- SpaCy (local and hub models)
- Hugging Face Hub
- Custom/self-trained models
"""

from .base import NERModelProvider, ModelMetadata, ModelCapabilities, NERModel
from .registry import ModelProviderRegistry
from .spacy_provider import SpacyModelProvider
from .huggingface_provider import HuggingFaceProvider

__all__ = [
    "NERModelProvider",
    "ModelMetadata",
    "ModelCapabilities",
    "NERModel",
    "ModelProviderRegistry",
    "SpacyModelProvider",
    "HuggingFaceProvider"
]

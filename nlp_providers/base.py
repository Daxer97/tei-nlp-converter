"""
Base abstract interface for NLP providers
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

class ProviderStatus(Enum):
    """Provider availability status"""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"

@dataclass
class ProviderCapabilities:
    """Capabilities supported by an NLP provider"""
    entities: bool = True
    sentences: bool = True
    tokens: bool = True
    pos_tags: bool = True
    dependencies: bool = True
    lemmas: bool = True
    noun_chunks: bool = True
    sentiment: bool = False
    embeddings: bool = False
    language_detection: bool = False
    syntax_analysis: bool = True
    entity_sentiment: bool = False
    classification: bool = False

@dataclass
class ProcessingOptions:
    """Standardized processing options"""
    include_entities: bool = True
    include_sentences: bool = True
    include_tokens: bool = True
    include_pos: bool = True
    include_dependencies: bool = True
    include_lemmas: bool = True
    include_noun_chunks: bool = True
    include_sentiment: bool = False
    include_embeddings: bool = False
    language: str = "en"
    encoding_type: str = "UTF8"  # For Google Cloud NLP

class NLPProvider(ABC):
    """Abstract base class for NLP providers"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.capabilities = self.get_capabilities()
        self._status = ProviderStatus.UNKNOWN
    
    @abstractmethod
    def get_name(self) -> str:
        """Get provider name"""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Get provider capabilities"""
        pass
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the provider"""
        pass
    
    @abstractmethod
    async def process(self, text: str, options: ProcessingOptions) -> Dict[str, Any]:
        """
        Process text and return standardized NLP results
        
        Returns standardized format:
        {
            "sentences": [...],
            "entities": [...],
            "tokens": [...],
            "dependencies": [...],
            "noun_chunks": [...],
            "language": "en",
            "metadata": {...}
        }
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> ProviderStatus:
        """Check provider health/availability"""
        pass
    
    async def close(self):
        """Cleanup resources"""
        pass
    
    def validate_options(self, options: ProcessingOptions) -> ProcessingOptions:
        """Validate and adjust options based on capabilities"""
        validated = ProcessingOptions()
        
        # Only include options that the provider supports
        validated.include_entities = options.include_entities and self.capabilities.entities
        validated.include_sentences = options.include_sentences and self.capabilities.sentences
        validated.include_tokens = options.include_tokens and self.capabilities.tokens
        validated.include_pos = options.include_pos and self.capabilities.pos_tags
        validated.include_dependencies = options.include_dependencies and self.capabilities.dependencies
        validated.include_lemmas = options.include_lemmas and self.capabilities.lemmas
        validated.include_noun_chunks = options.include_noun_chunks and self.capabilities.noun_chunks
        validated.include_sentiment = options.include_sentiment and self.capabilities.sentiment
        validated.include_embeddings = options.include_embeddings and self.capabilities.embeddings
        validated.language = options.language
        validated.encoding_type = options.encoding_type
        
        return validated
    
    def normalize_entity_type(self, provider_type: str) -> str:
        """Normalize entity types across providers"""
        # Standard mapping for common entity types
        mappings = {
            # Google Cloud NLP types
            "PERSON": "PERSON",
            "LOCATION": "LOC",
            "ORGANIZATION": "ORG",
            "EVENT": "EVENT",
            "WORK_OF_ART": "WORK_OF_ART",
            "CONSUMER_GOOD": "PRODUCT",
            "OTHER": "OTHER",
            "UNKNOWN": "OTHER",
            "NUMBER": "CARDINAL",
            "DATE": "DATE",
            "TIME": "TIME",
            "PRICE": "MONEY",
            "PHONE_NUMBER": "PHONE",
            "ADDRESS": "ADDRESS",
            # SpaCy types (already standard)
            "PER": "PERSON",
            "GPE": "LOC",
            "FAC": "FAC",
            "NORP": "NORP",
            "PRODUCT": "PRODUCT",
            "LANGUAGE": "LANGUAGE",
            "LAW": "LAW",
            "MONEY": "MONEY",
            "CARDINAL": "CARDINAL",
            "ORDINAL": "ORDINAL",
            "QUANTITY": "QUANTITY",
            "PERCENT": "PERCENT",
            # Add more mappings as needed
        }

        return mappings.get(provider_type.upper(), provider_type.upper())

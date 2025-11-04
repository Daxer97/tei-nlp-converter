"""
Base classes and interfaces for NER models
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class EntityType(Enum):
    """Common entity types across domains"""
    # General
    PERSON = "PERSON"
    LOCATION = "LOCATION"
    ORGANIZATION = "ORGANIZATION"
    DATE = "DATE"
    TIME = "TIME"
    MONEY = "MONEY"

    # Medical
    DISEASE = "DISEASE"
    DRUG = "DRUG"
    MEDICATION = "MEDICATION"
    CHEMICAL = "CHEMICAL"
    PROCEDURE = "PROCEDURE"
    ANATOMY = "ANATOMY"
    DOSAGE = "DOSAGE"

    # Legal
    STATUTE = "STATUTE"
    CASE_CITATION = "CASE_CITATION"
    LEGAL_ENTITY = "LEGAL_ENTITY"
    COURT = "COURT"
    LAW = "LAW"

    # Scientific
    GENE = "GENE"
    PROTEIN = "PROTEIN"
    SPECIES = "SPECIES"

    # Structured Data
    ICD_CODE = "ICD_CODE"
    CPT_CODE = "CPT_CODE"
    PHONE_NUMBER = "PHONE_NUMBER"
    EMAIL = "EMAIL"


@dataclass
class Entity:
    """Represents an extracted entity"""
    text: str
    type: str
    start: int
    end: int
    confidence: float
    model_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'text': self.text,
            'type': self.type,
            'start': self.start,
            'end': self.end,
            'confidence': self.confidence,
            'model_id': self.model_id,
            'metadata': self.metadata
        }


@dataclass
class ModelCapabilities:
    """Describes what a model can extract"""
    entity_types: List[str]
    supports_confidence_scores: bool = True
    supports_multiword_entities: bool = True
    supports_nested_entities: bool = False
    supports_entity_linking: bool = False
    max_text_length: Optional[int] = None
    languages: List[str] = field(default_factory=lambda: ['en'])

    def to_dict(self) -> Dict[str, Any]:
        return {
            'entity_types': self.entity_types,
            'supports_confidence_scores': self.supports_confidence_scores,
            'supports_multiword_entities': self.supports_multiword_entities,
            'supports_nested_entities': self.supports_nested_entities,
            'supports_entity_linking': self.supports_entity_linking,
            'max_text_length': self.max_text_length,
            'languages': self.languages
        }


@dataclass
class ModelPerformanceMetrics:
    """Performance metrics for a model"""
    f1_score: float
    precision: float
    recall: float
    latency_ms: float
    throughput_docs_per_sec: Optional[float] = None
    memory_mb: Optional[float] = None
    last_evaluated: Optional[datetime] = None
    evaluation_dataset: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'f1_score': self.f1_score,
            'precision': self.precision,
            'recall': self.recall,
            'latency_ms': self.latency_ms,
            'throughput_docs_per_sec': self.throughput_docs_per_sec,
            'memory_mb': self.memory_mb,
            'last_evaluated': self.last_evaluated.isoformat() if self.last_evaluated else None,
            'evaluation_dataset': self.evaluation_dataset
        }


@dataclass
class ModelMetadata:
    """Metadata about a model"""
    model_id: str
    provider: str
    version: str
    domain: str
    capabilities: ModelCapabilities
    performance: ModelPerformanceMetrics
    source_url: str
    trusted: bool = False
    requires_kb: List[str] = field(default_factory=list)
    description: Optional[str] = None
    license: Optional[str] = None
    model_size_mb: Optional[float] = None
    signature: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'model_id': self.model_id,
            'provider': self.provider,
            'version': self.version,
            'domain': self.domain,
            'capabilities': self.capabilities.to_dict(),
            'performance': self.performance.to_dict(),
            'source_url': self.source_url,
            'trusted': self.trusted,
            'requires_kb': self.requires_kb,
            'description': self.description,
            'license': self.license,
            'model_size_mb': self.model_size_mb,
            'signature': self.signature,
            'created_at': self.created_at.isoformat()
        }


class NERModel(ABC):
    """Abstract base class for NER models"""

    def __init__(self, model_id: str, version: str, metadata: Optional[ModelMetadata] = None):
        self.model_id = model_id
        self.version = version
        self.metadata = metadata
        self._loaded = False

    @abstractmethod
    async def load(self) -> bool:
        """Load the model into memory"""
        pass

    @abstractmethod
    async def extract_entities(self, text: str) -> List[Entity]:
        """Extract entities from text"""
        pass

    @abstractmethod
    async def extract_entities_batch(self, texts: List[str]) -> List[List[Entity]]:
        """Extract entities from multiple texts"""
        pass

    @abstractmethod
    def get_capabilities(self) -> ModelCapabilities:
        """Get model capabilities"""
        pass

    @abstractmethod
    async def unload(self) -> bool:
        """Unload model from memory"""
        pass

    def is_loaded(self) -> bool:
        """Check if model is loaded"""
        return self._loaded

    def cleanup(self):
        """Cleanup resources"""
        pass


@dataclass
class SelectionCriteria:
    """Criteria for selecting optimal models"""
    min_f1_score: float = 0.70
    max_latency_ms: float = 200
    preferred_providers: List[str] = field(default_factory=list)
    entity_types: List[str] = field(default_factory=list)
    min_models: int = 1
    max_models: int = 3
    require_trusted: bool = True
    max_model_size_mb: Optional[float] = None
    languages: List[str] = field(default_factory=lambda: ['en'])


@dataclass
class EnrichedEntity(Entity):
    """Entity with knowledge base enrichment"""
    kb_id: Optional[str] = None
    kb_entity_id: Optional[str] = None
    kb_metadata: Dict[str, Any] = field(default_factory=dict)
    relationships: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'kb_id': self.kb_id,
            'kb_entity_id': self.kb_entity_id,
            'kb_metadata': self.kb_metadata,
            'relationships': self.relationships
        })
        return base

"""
Abstract base interfaces for NER model providers.

This module defines the contracts that all model providers must implement,
ensuring provider-agnostic model loading and entity extraction.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from enum import Enum


class ModelStatus(str, Enum):
    """Status of a loaded model"""
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"
    UNLOADED = "unloaded"


@dataclass
class Entity:
    """Represents an extracted named entity"""
    text: str
    type: str
    start: int
    end: int
    confidence: float = 1.0
    model_id: Optional[str] = None
    sources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "type": self.type,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence,
            "model_id": self.model_id,
            "sources": self.sources,
            "metadata": self.metadata
        }


@dataclass
class ModelCapabilities:
    """Describes what a model can do"""
    entity_types: Set[str] = field(default_factory=set)
    supports_batch: bool = False
    supports_context: bool = False
    max_sequence_length: int = 512
    languages: Set[str] = field(default_factory=lambda: {"en"})
    additional_features: Dict[str, bool] = field(default_factory=dict)


@dataclass
class ModelPerformance:
    """Performance metrics for a model"""
    f1_score: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    latency_ms: float = 0.0
    throughput_docs_per_sec: float = 0.0
    memory_mb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "f1": self.f1_score,
            "precision": self.precision,
            "recall": self.recall,
            "latency_ms": self.latency_ms,
            "throughput": self.throughput_docs_per_sec,
            "memory_mb": self.memory_mb
        }


@dataclass
class ModelMetadata:
    """Complete metadata for a discoverable model"""
    model_id: str
    provider: str
    version: str
    domain: str = "general"
    entity_types: Set[str] = field(default_factory=set)
    performance: ModelPerformance = field(default_factory=ModelPerformance)
    source_url: str = ""
    trusted: bool = False
    requires_kb: List[str] = field(default_factory=list)
    description: str = ""
    size_mb: float = 0.0
    license: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    tags: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "version": self.version,
            "domain": self.domain,
            "entity_types": list(self.entity_types),
            "performance": self.performance.to_dict(),
            "source_url": self.source_url,
            "trusted": self.trusted,
            "requires_kb": self.requires_kb,
            "description": self.description,
            "size_mb": self.size_mb,
            "license": self.license,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "tags": list(self.tags)
        }


class NERModel(ABC):
    """Abstract base class for loaded NER models"""

    def __init__(self, model_id: str, version: str, domain: str = "general"):
        self.model_id = model_id
        self.version = version
        self.domain = domain
        self.status = ModelStatus.LOADING
        self.load_time: Optional[datetime] = None
        self.capabilities: Optional[ModelCapabilities] = None
        self._performance_history: List[Dict[str, Any]] = []

    @abstractmethod
    async def extract_entities(self, text: str) -> List[Entity]:
        """Extract named entities from text"""
        pass

    @abstractmethod
    async def extract_entities_batch(self, texts: List[str]) -> List[List[Entity]]:
        """Extract entities from multiple texts"""
        pass

    @abstractmethod
    def get_capabilities(self) -> ModelCapabilities:
        """Return model capabilities"""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Release model resources"""
        pass

    def record_performance(self, latency_ms: float, entity_count: int) -> None:
        """Record performance metric"""
        self._performance_history.append({
            "timestamp": datetime.now().isoformat(),
            "latency_ms": latency_ms,
            "entity_count": entity_count
        })
        # Keep last 1000 records
        if len(self._performance_history) > 1000:
            self._performance_history = self._performance_history[-1000:]

    def get_avg_latency(self) -> float:
        """Get average latency from recent predictions"""
        if not self._performance_history:
            return 0.0
        return sum(p["latency_ms"] for p in self._performance_history) / len(self._performance_history)


class NERModelProvider(ABC):
    """Abstract base class for all NER model providers"""

    @abstractmethod
    def list_available_models(self, domain: Optional[str] = None) -> List[ModelMetadata]:
        """
        Discover available models from this provider.

        Args:
            domain: Optional domain filter (e.g., "medical", "legal")

        Returns:
            List of available model metadata
        """
        pass

    @abstractmethod
    async def load_model(self, model_id: str, version: str = "latest") -> NERModel:
        """
        Load a specific model version.

        Args:
            model_id: Unique model identifier
            version: Model version (default "latest")

        Returns:
            Loaded NER model instance
        """
        pass

    @abstractmethod
    def get_model_capabilities(self, model_id: str) -> ModelCapabilities:
        """
        Get capabilities of a specific model.

        Args:
            model_id: Unique model identifier

        Returns:
            Model capabilities descriptor
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return provider name"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is available"""
        pass

    def supports_domain(self, domain: str) -> bool:
        """Check if provider has models for a domain"""
        models = self.list_available_models(domain=domain)
        return len(models) > 0


@dataclass
class SelectionCriteria:
    """Criteria for selecting optimal models"""
    min_f1_score: float = 0.70
    max_latency_ms: float = 500.0
    preferred_providers: List[str] = field(default_factory=list)
    entity_types: Set[str] = field(default_factory=set)
    ensemble_strategy: str = "majority_vote"
    min_models: int = 1
    max_models: int = 3
    prefer_trusted: bool = True
    max_memory_mb: float = 8000.0

    def matches(self, model: ModelMetadata) -> bool:
        """Check if model meets criteria"""
        if model.performance.f1_score < self.min_f1_score:
            return False
        if model.performance.latency_ms > self.max_latency_ms:
            return False
        if self.prefer_trusted and not model.trusted:
            return False
        if self.entity_types and not self.entity_types.issubset(model.entity_types):
            return False
        if model.size_mb > self.max_memory_mb:
            return False
        return True

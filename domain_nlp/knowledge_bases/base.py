"""
Abstract base interfaces for knowledge base providers.

This module defines contracts for KB providers that support:
- Entity streaming and batch loading
- Entity lookup with enrichment
- Relationship traversal
- Incremental synchronization
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, AsyncIterator, Set
from datetime import datetime
from enum import Enum


class SyncFrequency(str, Enum):
    """KB synchronization frequency"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class CacheStrategy(str, Enum):
    """Caching strategy for KB data"""
    AGGRESSIVE = "aggressive"  # Cache everything
    MODERATE = "moderate"      # Cache frequently accessed
    MINIMAL = "minimal"        # Cache only lookups
    NONE = "none"             # No caching


@dataclass
class KBRelationship:
    """Represents a relationship between KB entities"""
    source_id: str
    target_id: str
    relationship_type: str
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship_type": self.relationship_type,
            "confidence": self.confidence,
            "metadata": self.metadata
        }


@dataclass
class KBEntity:
    """Represents an entity from a knowledge base"""
    kb_id: str                    # Source KB identifier
    entity_id: str                # Unique ID within KB
    text: str                     # Canonical text/name
    entity_type: str              # Entity type (DRUG, DISEASE, etc.)
    synonyms: List[str] = field(default_factory=list)
    definition: str = ""
    relationships: List[KBRelationship] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source_url: str = ""
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kb_id": self.kb_id,
            "entity_id": self.entity_id,
            "text": self.text,
            "entity_type": self.entity_type,
            "synonyms": self.synonyms,
            "definition": self.definition,
            "relationships": [r.to_dict() for r in self.relationships],
            "metadata": self.metadata,
            "confidence": self.confidence,
            "source_url": self.source_url,
            "last_updated": self.last_updated.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KBEntity":
        """Create KBEntity from dictionary"""
        relationships = [
            KBRelationship(**r) for r in data.get("relationships", [])
        ]
        last_updated = data.get("last_updated", datetime.now())
        if isinstance(last_updated, str):
            last_updated = datetime.fromisoformat(last_updated)

        return cls(
            kb_id=data["kb_id"],
            entity_id=data["entity_id"],
            text=data["text"],
            entity_type=data["entity_type"],
            synonyms=data.get("synonyms", []),
            definition=data.get("definition", ""),
            relationships=relationships,
            metadata=data.get("metadata", {}),
            confidence=data.get("confidence", 1.0),
            source_url=data.get("source_url", ""),
            last_updated=last_updated
        )


@dataclass
class KBMetadata:
    """Complete metadata for a knowledge base"""
    kb_id: str
    provider: str
    domain: str
    version: str
    stream_url: str = ""
    api_key_required: bool = False
    entity_types: Set[str] = field(default_factory=set)
    update_frequency: SyncFrequency = SyncFrequency.WEEKLY
    trusted: bool = False
    cache_strategy: CacheStrategy = CacheStrategy.MODERATE
    fallback: List[str] = field(default_factory=list)
    description: str = ""
    entity_count: int = 0
    last_sync: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kb_id": self.kb_id,
            "provider": self.provider,
            "domain": self.domain,
            "version": self.version,
            "stream_url": self.stream_url,
            "api_key_required": self.api_key_required,
            "entity_types": list(self.entity_types),
            "update_frequency": self.update_frequency.value,
            "trusted": self.trusted,
            "cache_strategy": self.cache_strategy.value,
            "fallback": self.fallback,
            "description": self.description,
            "entity_count": self.entity_count,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class EnrichedEntity:
    """Entity enriched with knowledge base data"""
    text: str
    entity_type: str
    start: int
    end: int
    confidence: float = 1.0
    model_id: Optional[str] = None
    kb_entity: Optional[KBEntity] = None
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "entity_type": self.entity_type,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence,
            "model_id": self.model_id,
            "kb_entity": self.kb_entity.to_dict() if self.kb_entity else None,
            "sources": self.sources
        }

    @property
    def is_enriched(self) -> bool:
        """Check if entity has KB enrichment"""
        return self.kb_entity is not None

    @property
    def kb_id(self) -> Optional[str]:
        """Get KB entity ID if enriched"""
        return self.kb_entity.entity_id if self.kb_entity else None


class KnowledgeBaseProvider(ABC):
    """Abstract base class for all knowledge base providers"""

    @abstractmethod
    async def stream_entities(
        self,
        entity_type: str,
        batch_size: int = 1000,
        since: Optional[datetime] = None
    ) -> AsyncIterator[List[KBEntity]]:
        """
        Stream entity data in batches.

        Args:
            entity_type: Type of entities to stream
            batch_size: Number of entities per batch
            since: Only return entities updated after this time (for incremental sync)

        Yields:
            Batches of KB entities
        """
        pass

    @abstractmethod
    async def lookup_entity(
        self,
        entity_text: str,
        entity_type: Optional[str] = None
    ) -> Optional[KBEntity]:
        """
        Lookup a specific entity.

        Args:
            entity_text: Text to search for
            entity_type: Optional type filter

        Returns:
            KB entity if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_relationships(self, entity_id: str) -> List[KBRelationship]:
        """
        Get relationships for an entity.

        Args:
            entity_id: Entity identifier

        Returns:
            List of relationships
        """
        pass

    @abstractmethod
    async def get_metadata(self, entity_id: str) -> Dict[str, Any]:
        """
        Get enrichment metadata for entity.

        Args:
            entity_id: Entity identifier

        Returns:
            Metadata dictionary
        """
        pass

    @abstractmethod
    def get_kb_metadata(self) -> KBMetadata:
        """Return knowledge base metadata"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if KB is available"""
        pass

    @abstractmethod
    def get_supported_entity_types(self) -> Set[str]:
        """Return entity types this KB supports"""
        pass

    async def search_entities(
        self,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 10
    ) -> List[KBEntity]:
        """
        Search for entities matching query.

        Args:
            query: Search query
            entity_type: Optional type filter
            limit: Maximum results

        Returns:
            List of matching entities
        """
        # Default implementation uses lookup
        result = await self.lookup_entity(query, entity_type)
        return [result] if result else []

    async def get_entity_by_id(self, entity_id: str) -> Optional[KBEntity]:
        """
        Get entity directly by ID.

        Args:
            entity_id: Entity identifier

        Returns:
            KB entity if found
        """
        # Default implementation - subclasses should override
        return None

    def normalize_text(self, text: str) -> str:
        """Normalize text for consistent matching"""
        return text.strip().lower()


@dataclass
class KBSelectionCriteria:
    """Criteria for selecting knowledge bases"""
    required_kbs: List[str] = field(default_factory=list)
    optional_kbs: List[str] = field(default_factory=list)
    fallback_chain: List[str] = field(default_factory=list)
    cache_strategy: CacheStrategy = CacheStrategy.MODERATE
    sync_frequency: SyncFrequency = SyncFrequency.WEEKLY
    prefer_trusted: bool = True
    entity_types: Set[str] = field(default_factory=set)

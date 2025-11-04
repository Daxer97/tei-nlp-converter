"""
Base classes and interfaces for Knowledge Base providers
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, AsyncIterator
from datetime import datetime
from enum import Enum


class RelationType(Enum):
    """Types of relationships between entities"""
    IS_A = "is_a"
    PART_OF = "part_of"
    TREATS = "treats"
    CAUSES = "causes"
    ASSOCIATED_WITH = "associated_with"
    SYNONYM = "synonym"
    RELATED_TO = "related_to"
    CITED_BY = "cited_by"
    REFERENCES = "references"


@dataclass
class Relationship:
    """Represents a relationship between entities"""
    source_id: str
    target_id: str
    relation_type: RelationType
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'source_id': self.source_id,
            'target_id': self.target_id,
            'relation_type': self.relation_type.value,
            'confidence': self.confidence,
            'metadata': self.metadata
        }


@dataclass
class KBEntity:
    """Represents an entity in a knowledge base"""
    kb_id: str
    entity_id: str
    entity_type: str
    canonical_name: str
    aliases: List[str] = field(default_factory=list)
    definition: Optional[str] = None
    semantic_types: List[str] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'kb_id': self.kb_id,
            'entity_id': self.entity_id,
            'entity_type': self.entity_type,
            'canonical_name': self.canonical_name,
            'aliases': self.aliases,
            'definition': self.definition,
            'semantic_types': self.semantic_types,
            'relationships': [r.to_dict() for r in self.relationships],
            'metadata': self.metadata,
            'last_updated': self.last_updated.isoformat()
        }


@dataclass
class KBCapabilities:
    """Describes capabilities of a knowledge base"""
    entity_types: List[str]
    supports_relationships: bool = True
    supports_semantic_types: bool = True
    supports_synonyms: bool = True
    supports_definitions: bool = True
    supports_hierarchies: bool = True
    update_frequency: str = "monthly"  # daily, weekly, monthly, quarterly
    total_entities: Optional[int] = None
    languages: List[str] = field(default_factory=lambda: ['en'])

    def to_dict(self) -> Dict[str, Any]:
        return {
            'entity_types': self.entity_types,
            'supports_relationships': self.supports_relationships,
            'supports_semantic_types': self.supports_semantic_types,
            'supports_synonyms': self.supports_synonyms,
            'supports_definitions': self.supports_definitions,
            'supports_hierarchies': self.supports_hierarchies,
            'update_frequency': self.update_frequency,
            'total_entities': self.total_entities,
            'languages': self.languages
        }


@dataclass
class KBMetadata:
    """Metadata about a knowledge base"""
    kb_id: str
    provider: str
    version: str
    domain: str
    capabilities: KBCapabilities
    stream_url: str
    api_key_required: bool = False
    trusted: bool = False
    description: Optional[str] = None
    license: Optional[str] = None
    cache_strategy: str = "moderate"  # aggressive, moderate, minimal
    sync_frequency: str = "weekly"
    last_sync: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'kb_id': self.kb_id,
            'provider': self.provider,
            'version': self.version,
            'domain': self.domain,
            'capabilities': self.capabilities.to_dict(),
            'stream_url': self.stream_url,
            'api_key_required': self.api_key_required,
            'trusted': self.trusted,
            'description': self.description,
            'license': self.license,
            'cache_strategy': self.cache_strategy,
            'sync_frequency': self.sync_frequency,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'created_at': self.created_at.isoformat()
        }


class KnowledgeBaseProvider(ABC):
    """Base interface for all knowledge base providers"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.kb_id = None
        self.capabilities = None

    @abstractmethod
    def get_kb_id(self) -> str:
        """Get knowledge base identifier"""
        pass

    @abstractmethod
    def get_capabilities(self) -> KBCapabilities:
        """Get KB capabilities"""
        pass

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the KB provider"""
        pass

    @abstractmethod
    async def stream_entities(
        self,
        entity_type: Optional[str] = None,
        batch_size: int = 1000,
        since: Optional[datetime] = None
    ) -> AsyncIterator[List[KBEntity]]:
        """
        Stream entity data in batches

        Args:
            entity_type: Filter by entity type
            batch_size: Number of entities per batch
            since: Only stream entities updated since this timestamp

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
        Lookup a specific entity

        Args:
            entity_text: Text to lookup
            entity_type: Optional entity type filter

        Returns:
            KB entity or None if not found
        """
        pass

    @abstractmethod
    async def get_relationships(self, entity_id: str) -> List[Relationship]:
        """
        Get relationships for an entity

        Args:
            entity_id: Entity identifier

        Returns:
            List of relationships
        """
        pass

    @abstractmethod
    async def get_metadata(self, entity_id: str) -> Dict[str, Any]:
        """
        Get enrichment metadata for entity

        Args:
            entity_id: Entity identifier

        Returns:
            Metadata dictionary
        """
        pass

    async def close(self):
        """Cleanup resources"""
        pass


@dataclass
class KBSyncConfig:
    """Configuration for KB synchronization"""
    kb_id: str
    sync_frequency: str  # daily, weekly, monthly
    batch_size: int = 1000
    enabled: bool = True
    last_sync: Optional[datetime] = None
    incremental: bool = True  # Use incremental updates vs full refresh

    def to_dict(self) -> Dict[str, Any]:
        return {
            'kb_id': self.kb_id,
            'sync_frequency': self.sync_frequency,
            'batch_size': self.batch_size,
            'enabled': self.enabled,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'incremental': self.incremental
        }


@dataclass
class KBLookupResult:
    """Result of a KB lookup operation"""
    found: bool
    entity: Optional[KBEntity] = None
    cache_hit: bool = False
    cache_tier: Optional[str] = None  # memory, redis, database
    lookup_time_ms: float = 0.0
    kb_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'found': self.found,
            'entity': self.entity.to_dict() if self.entity else None,
            'cache_hit': self.cache_hit,
            'cache_tier': self.cache_tier,
            'lookup_time_ms': self.lookup_time_ms,
            'kb_id': self.kb_id
        }

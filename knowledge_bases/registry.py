"""
Knowledge Base Provider Registry System

Manages dynamic discovery, registration, and access to knowledge base providers.
"""
from typing import Dict, List, Optional, AsyncIterator
import asyncio
from datetime import datetime
from knowledge_bases.base import (
    KnowledgeBaseProvider,
    KBEntity,
    KBMetadata,
    KBCapabilities,
    KBSyncConfig,
    KBLookupResult,
    Relationship
)
from logger import get_logger

logger = get_logger(__name__)


class KnowledgeBaseRegistry:
    """Central registry for all knowledge base providers"""

    def __init__(self):
        self.providers: Dict[str, KnowledgeBaseProvider] = {}
        self.metadata_catalog: Dict[str, KBMetadata] = {}
        self._lock = asyncio.Lock()

    def register_provider(self, provider: KnowledgeBaseProvider, metadata: KBMetadata):
        """
        Register a new KB provider

        Args:
            provider: KB provider instance
            metadata: KB metadata
        """
        kb_id = provider.get_kb_id()
        self.providers[kb_id] = provider
        self.metadata_catalog[kb_id] = metadata
        logger.info(f"Registered KB provider: {kb_id}")

    def unregister_provider(self, kb_id: str):
        """
        Unregister a KB provider

        Args:
            kb_id: Knowledge base identifier
        """
        if kb_id in self.providers:
            del self.providers[kb_id]
            del self.metadata_catalog[kb_id]
            logger.info(f"Unregistered KB provider: {kb_id}")

    def get_provider(self, kb_id: str) -> Optional[KnowledgeBaseProvider]:
        """
        Get a registered provider

        Args:
            kb_id: Knowledge base identifier

        Returns:
            Provider instance or None
        """
        return self.providers.get(kb_id)

    def get_metadata(self, kb_id: str) -> Optional[KBMetadata]:
        """
        Get KB metadata

        Args:
            kb_id: Knowledge base identifier

        Returns:
            KB metadata or None
        """
        return self.metadata_catalog.get(kb_id)

    def list_providers(self) -> List[str]:
        """List all registered KB providers"""
        return list(self.providers.keys())

    def discover_kbs(self, domain: Optional[str] = None) -> List[KBMetadata]:
        """
        Discover available KBs, optionally filtered by domain

        Args:
            domain: Optional domain filter

        Returns:
            List of KB metadata
        """
        if domain:
            return [
                metadata for metadata in self.metadata_catalog.values()
                if metadata.domain == domain
            ]

        return list(self.metadata_catalog.values())

    async def lookup_entity(
        self,
        entity_text: str,
        kb_chain: List[str],
        entity_type: Optional[str] = None
    ) -> KBLookupResult:
        """
        Lookup entity across fallback chain

        Args:
            entity_text: Text to lookup
            kb_chain: List of KB IDs to try in order
            entity_type: Optional entity type filter

        Returns:
            Lookup result with entity if found
        """
        start_time = asyncio.get_event_loop().time()

        for kb_id in kb_chain:
            provider = self.get_provider(kb_id)
            if not provider:
                logger.warning(f"KB provider not found: {kb_id}")
                continue

            try:
                entity = await provider.lookup_entity(entity_text, entity_type)

                if entity:
                    lookup_time = (asyncio.get_event_loop().time() - start_time) * 1000

                    return KBLookupResult(
                        found=True,
                        entity=entity,
                        cache_hit=False,  # This would be determined by cache layer
                        lookup_time_ms=lookup_time,
                        kb_id=kb_id
                    )

            except Exception as e:
                logger.error(f"Error looking up entity in {kb_id}: {e}")
                continue

        # Not found in any KB
        lookup_time = (asyncio.get_event_loop().time() - start_time) * 1000

        return KBLookupResult(
            found=False,
            lookup_time_ms=lookup_time
        )

    async def stream_kb(
        self,
        kb_id: str,
        entity_type: Optional[str] = None,
        batch_size: int = 1000,
        since: Optional[datetime] = None
    ) -> AsyncIterator[List[KBEntity]]:
        """
        Stream entities from a KB

        Args:
            kb_id: Knowledge base identifier
            entity_type: Optional entity type filter
            batch_size: Batch size for streaming
            since: Only stream entities updated since this timestamp

        Yields:
            Batches of entities
        """
        provider = self.get_provider(kb_id)
        if not provider:
            logger.error(f"KB provider not found: {kb_id}")
            return

        try:
            async for batch in provider.stream_entities(entity_type, batch_size, since):
                yield batch

        except Exception as e:
            logger.error(f"Error streaming from {kb_id}: {e}")

    async def get_relationships(
        self,
        entity_id: str,
        kb_id: str
    ) -> List[Relationship]:
        """
        Get relationships for an entity

        Args:
            entity_id: Entity identifier
            kb_id: Knowledge base identifier

        Returns:
            List of relationships
        """
        provider = self.get_provider(kb_id)
        if not provider:
            logger.error(f"KB provider not found: {kb_id}")
            return []

        try:
            return await provider.get_relationships(entity_id)

        except Exception as e:
            logger.error(f"Error getting relationships from {kb_id}: {e}")
            return []

    def get_sync_config(self, kb_id: str) -> Optional[KBSyncConfig]:
        """
        Get synchronization configuration for a KB

        Args:
            kb_id: Knowledge base identifier

        Returns:
            Sync configuration or None
        """
        metadata = self.get_metadata(kb_id)
        if not metadata:
            return None

        return KBSyncConfig(
            kb_id=kb_id,
            sync_frequency=metadata.sync_frequency,
            batch_size=1000,
            enabled=True,
            last_sync=metadata.last_sync,
            incremental=True
        )

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get registry statistics

        Returns:
            Dictionary with statistics
        """
        return {
            'total_kbs': len(self.providers),
            'kb_ids': list(self.providers.keys()),
            'domains': list(set(m.domain for m in self.metadata_catalog.values())),
            'trusted_kbs': sum(1 for m in self.metadata_catalog.values() if m.trusted),
            'api_key_required': sum(1 for m in self.metadata_catalog.values() if m.api_key_required)
        }

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Check health of all KB providers

        Returns:
            Dictionary mapping KB IDs to health status
        """
        results = {}

        for kb_id, provider in self.providers.items():
            try:
                # Try to initialize as health check
                healthy = await provider.initialize()
                results[kb_id] = healthy
                logger.debug(f"KB {kb_id} health check: {'OK' if healthy else 'FAILED'}")

            except Exception as e:
                logger.error(f"KB {kb_id} health check failed: {e}")
                results[kb_id] = False

        return results

    async def cleanup_all(self):
        """Cleanup all providers"""
        for kb_id, provider in self.providers.items():
            try:
                await provider.close()
                logger.info(f"Cleaned up KB provider: {kb_id}")

            except Exception as e:
                logger.error(f"Error cleaning up KB provider {kb_id}: {e}")


# Global registry instance
_global_kb_registry: Optional[KnowledgeBaseRegistry] = None
_kb_registry_lock = asyncio.Lock()


async def get_global_kb_registry() -> KnowledgeBaseRegistry:
    """Get or create the global KB provider registry"""
    global _global_kb_registry

    if _global_kb_registry is None:
        async with _kb_registry_lock:
            if _global_kb_registry is None:
                _global_kb_registry = KnowledgeBaseRegistry()
                logger.info("Initialized global KB provider registry")

    return _global_kb_registry


async def initialize_kb_providers(config: Optional[Dict[str, Any]] = None):
    """
    Initialize and register all available KB providers

    Args:
        config: Configuration dictionary with KB provider settings
    """
    registry = await get_global_kb_registry()
    config = config or {}

    # Import and register medical KB providers
    if config.get('enable_medical_kbs', True):
        try:
            from knowledge_bases.providers.umls_provider import UMLSProvider, get_umls_metadata
            from knowledge_bases.providers.rxnorm_provider import RxNormProvider, get_rxnorm_metadata

            # UMLS
            if config.get('umls_api_key'):
                umls_config = {'api_key': config['umls_api_key']}
                umls_provider = UMLSProvider(umls_config)
                umls_metadata = get_umls_metadata()
                registry.register_provider(umls_provider, umls_metadata)

            # RxNorm
            rxnorm_provider = RxNormProvider({})
            rxnorm_metadata = get_rxnorm_metadata()
            registry.register_provider(rxnorm_provider, rxnorm_metadata)

        except ImportError as e:
            logger.warning(f"Could not load medical KB providers: {e}")

    # Import and register legal KB providers
    if config.get('enable_legal_kbs', True):
        try:
            from knowledge_bases.providers.usc_provider import USCProvider, get_usc_metadata
            from knowledge_bases.providers.courtlistener_provider import CourtListenerProvider, get_courtlistener_metadata

            # USC
            usc_provider = USCProvider({})
            usc_metadata = get_usc_metadata()
            registry.register_provider(usc_provider, usc_metadata)

            # CourtListener
            if config.get('courtlistener_api_key'):
                cl_config = {'api_key': config['courtlistener_api_key']}
                cl_provider = CourtListenerProvider(cl_config)
                cl_metadata = get_courtlistener_metadata()
                registry.register_provider(cl_provider, cl_metadata)

        except ImportError as e:
            logger.warning(f"Could not load legal KB providers: {e}")

    logger.info(f"Initialized {len(registry.list_providers())} KB providers")

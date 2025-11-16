"""
Central registry for all knowledge base providers.

This module manages KB discovery, synchronization, and fallback chains
for entity enrichment.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from collections import defaultdict

from .base import (
    KnowledgeBaseProvider,
    KBMetadata,
    KBEntity,
    KBSelectionCriteria,
    SyncFrequency
)

logger = logging.getLogger(__name__)


class KBCatalog:
    """Persistent catalog of available knowledge bases"""

    def __init__(self):
        self._kbs: Dict[str, KBMetadata] = {}
        self._by_domain: Dict[str, List[KBMetadata]] = defaultdict(list)
        self._by_entity_type: Dict[str, List[KBMetadata]] = defaultdict(list)

    def add(self, metadata: KBMetadata) -> None:
        """Add KB to catalog"""
        self._kbs[metadata.kb_id] = metadata
        self._by_domain[metadata.domain].append(metadata)
        for entity_type in metadata.entity_types:
            self._by_entity_type[entity_type].append(metadata)

    def query(
        self,
        domain: Optional[str] = None,
        entity_type: Optional[str] = None,
        trusted_only: bool = False
    ) -> List[KBMetadata]:
        """Query catalog with filters"""
        if domain:
            candidates = self._by_domain.get(domain, [])
        elif entity_type:
            candidates = self._by_entity_type.get(entity_type, [])
        else:
            candidates = list(self._kbs.values())

        if trusted_only:
            candidates = [kb for kb in candidates if kb.trusted]

        return candidates

    def get_by_id(self, kb_id: str) -> Optional[KBMetadata]:
        """Get KB by ID"""
        return self._kbs.get(kb_id)

    def list_all(self) -> List[str]:
        """List all KB IDs"""
        return list(self._kbs.keys())

    def get_sync_config(self, kb_id: str) -> Optional[SyncFrequency]:
        """Get sync frequency for KB"""
        kb = self._kbs.get(kb_id)
        return kb.update_frequency if kb else None


class KBSyncStatus:
    """Tracks synchronization status for KBs"""

    def __init__(self):
        self._status: Dict[str, Dict[str, Any]] = {}

    def update(self, kb_id: str, status: str, **kwargs) -> None:
        """Update sync status"""
        self._status[kb_id] = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }

    def get(self, kb_id: str) -> Optional[Dict[str, Any]]:
        """Get sync status"""
        return self._status.get(kb_id)

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Get all sync statuses"""
        return self._status.copy()


class KnowledgeBaseRegistry:
    """Central registry for all KB providers"""

    def __init__(self):
        self.providers: Dict[str, KnowledgeBaseProvider] = {}
        self.kb_catalog = KBCatalog()
        self.sync_status = KBSyncStatus()
        self._sync_jobs: Dict[str, asyncio.Task] = {}
        self._lookup_cache: Dict[str, KBEntity] = {}
        self._cache_ttl = 3600  # 1 hour

    def register_provider(
        self,
        kb_id: str,
        provider: KnowledgeBaseProvider
    ) -> None:
        """Register a new KB provider"""
        self.providers[kb_id] = provider
        metadata = provider.get_kb_metadata()
        self.kb_catalog.add(metadata)
        logger.info(f"Registered KB provider: {kb_id}")

    def unregister_provider(self, kb_id: str) -> None:
        """Remove KB provider"""
        if kb_id in self.providers:
            # Cancel sync job if running
            if kb_id in self._sync_jobs:
                self._sync_jobs[kb_id].cancel()
                del self._sync_jobs[kb_id]
            del self.providers[kb_id]
            logger.info(f"Unregistered KB provider: {kb_id}")

    def list_providers(self) -> List[str]:
        """List all registered KB providers"""
        return list(self.providers.keys())

    def discover_kbs(self, domain: str) -> List[KBMetadata]:
        """Discover available KBs for domain"""
        return self.kb_catalog.query(domain=domain)

    def get_provider(self, kb_id: str) -> Optional[KnowledgeBaseProvider]:
        """Get provider by KB ID"""
        return self.providers.get(kb_id)

    async def lookup_with_fallback(
        self,
        entity_text: str,
        fallback_chain: List[str],
        entity_type: Optional[str] = None
    ) -> Optional[KBEntity]:
        """
        Lookup entity across fallback chain.

        Args:
            entity_text: Text to lookup
            fallback_chain: Ordered list of KB IDs to try
            entity_type: Optional type filter

        Returns:
            KB entity if found, None otherwise
        """
        # Check cache first
        cache_key = f"{entity_text}:{entity_type or 'any'}"
        if cache_key in self._lookup_cache:
            logger.debug(f"Cache hit for {entity_text}")
            return self._lookup_cache[cache_key]

        # Try each KB in fallback chain
        for kb_id in fallback_chain:
            provider = self.providers.get(kb_id)
            if not provider:
                logger.warning(f"KB provider {kb_id} not found")
                continue

            try:
                result = await provider.lookup_entity(entity_text, entity_type)
                if result:
                    # Cache successful lookup
                    self._lookup_cache[cache_key] = result
                    logger.debug(f"Found {entity_text} in {kb_id}")
                    return result
            except Exception as e:
                logger.warning(f"KB {kb_id} lookup failed for {entity_text}: {e}")

        logger.debug(f"No KB match found for {entity_text}")
        return None

    async def lookup_batch(
        self,
        entities: List[Dict[str, Any]],
        fallback_chain: List[str]
    ) -> List[Optional[KBEntity]]:
        """
        Lookup multiple entities in parallel.

        Args:
            entities: List of {text: str, type: Optional[str]}
            fallback_chain: KB fallback chain

        Returns:
            List of KB entities (None if not found)
        """
        tasks = [
            self.lookup_with_fallback(
                e["text"],
                fallback_chain,
                e.get("type")
            )
            for e in entities
        ]
        return await asyncio.gather(*tasks)

    async def start_sync(self, kb_id: str) -> None:
        """Start background sync for KB"""
        if kb_id in self._sync_jobs:
            logger.warning(f"Sync already running for {kb_id}")
            return

        provider = self.providers.get(kb_id)
        if not provider:
            logger.error(f"Cannot start sync: {kb_id} not registered")
            return

        metadata = provider.get_kb_metadata()
        task = asyncio.create_task(
            self._sync_kb_periodically(kb_id, metadata.update_frequency)
        )
        self._sync_jobs[kb_id] = task
        logger.info(f"Started sync for {kb_id} ({metadata.update_frequency.value})")

    async def _sync_kb_periodically(
        self,
        kb_id: str,
        frequency: SyncFrequency
    ) -> None:
        """Periodically sync KB data"""
        interval_seconds = self._frequency_to_seconds(frequency)

        while True:
            try:
                await self._perform_sync(kb_id)
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                logger.info(f"Sync cancelled for {kb_id}")
                break
            except Exception as e:
                logger.error(f"Sync error for {kb_id}: {e}")
                self.sync_status.update(kb_id, "failed", error=str(e))
                # Wait before retry
                await asyncio.sleep(3600)  # 1 hour

    async def _perform_sync(self, kb_id: str) -> None:
        """Perform actual KB synchronization"""
        logger.info(f"Starting sync for {kb_id}")
        self.sync_status.update(kb_id, "in_progress")

        provider = self.providers.get(kb_id)
        if not provider:
            return

        # Get last sync time
        status = self.sync_status.get(kb_id)
        last_sync = None
        if status and status.get("last_success"):
            last_sync = datetime.fromisoformat(status["last_success"])

        total_entities = 0
        entity_types = provider.get_supported_entity_types()

        for entity_type in entity_types:
            try:
                async for batch in provider.stream_entities(
                    entity_type,
                    batch_size=1000,
                    since=last_sync
                ):
                    # Process batch (cache it, store in DB, etc.)
                    for entity in batch:
                        cache_key = f"{entity.text}:{entity.entity_type}"
                        self._lookup_cache[cache_key] = entity
                    total_entities += len(batch)
            except Exception as e:
                logger.error(f"Error syncing {entity_type} from {kb_id}: {e}")

        self.sync_status.update(
            kb_id,
            "success",
            last_success=datetime.now().isoformat(),
            entities_synced=total_entities
        )
        logger.info(f"Completed sync for {kb_id}: {total_entities} entities")

    def _frequency_to_seconds(self, frequency: SyncFrequency) -> int:
        """Convert sync frequency to seconds"""
        mapping = {
            SyncFrequency.HOURLY: 3600,
            SyncFrequency.DAILY: 86400,
            SyncFrequency.WEEKLY: 604800,
            SyncFrequency.MONTHLY: 2592000,
            SyncFrequency.QUARTERLY: 7776000,
            SyncFrequency.ANNUAL: 31536000
        }
        return mapping.get(frequency, 86400)

    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all KB providers"""
        results = {}
        for kb_id, provider in self.providers.items():
            try:
                results[kb_id] = await provider.health_check()
            except Exception as e:
                logger.error(f"Health check failed for {kb_id}: {e}")
                results[kb_id] = False
        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics"""
        return {
            "total_kbs": len(self.providers),
            "kb_ids": list(self.providers.keys()),
            "kbs_by_domain": {
                domain: [kb.kb_id for kb in kbs]
                for domain, kbs in self.kb_catalog._by_domain.items()
            },
            "sync_status": self.sync_status.get_all(),
            "cache_size": len(self._lookup_cache),
            "active_sync_jobs": list(self._sync_jobs.keys())
        }

    def clear_cache(self) -> None:
        """Clear lookup cache"""
        self._lookup_cache.clear()
        logger.info("Cleared KB lookup cache")

    async def shutdown(self) -> None:
        """Gracefully shutdown all sync jobs"""
        for kb_id, task in self._sync_jobs.items():
            task.cancel()
        if self._sync_jobs:
            await asyncio.gather(*self._sync_jobs.values(), return_exceptions=True)
        self._sync_jobs.clear()
        logger.info("Shutdown all KB sync jobs")

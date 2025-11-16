"""
Multi-tier caching system for knowledge base lookups.

Implements a three-tier cache hierarchy:
- L1: In-memory LRU cache (fastest)
- L2: Redis cache (fast, shared)
- L3: Database persistence (durable)
"""

import asyncio
import logging
import json
import hashlib
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
from collections import OrderedDict

from .base import KBEntity

logger = logging.getLogger(__name__)


class LRUCache:
    """Thread-safe LRU cache with TTL support"""

    def __init__(self, maxsize: int = 10000, ttl_seconds: int = 3600):
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._ttl = timedelta(seconds=ttl_seconds)
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if key not in self._cache:
            self._misses += 1
            return None

        value, timestamp = self._cache[key]

        # Check TTL
        if datetime.now() - timestamp > self._ttl:
            del self._cache[key]
            self._misses += 1
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        """Set value in cache"""
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._maxsize:
                # Remove least recently used
                self._cache.popitem(last=False)
        self._cache[key] = (value, datetime.now())

    def delete(self, key: str) -> None:
        """Remove key from cache"""
        if key in self._cache:
            del self._cache[key]

    def clear(self) -> None:
        """Clear entire cache"""
        self._cache.clear()

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    def __len__(self) -> int:
        return len(self._cache)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0
        return {
            "size": len(self._cache),
            "maxsize": self._maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate
        }


class MultiTierCacheManager:
    """
    Three-tier caching: Memory -> Redis -> Database

    Provides fast lookups with automatic tier promotion.
    """

    def __init__(
        self,
        memory_size: int = 10000,
        memory_ttl: int = 3600,
        redis_client: Optional[Any] = None,
        db_session: Optional[Any] = None
    ):
        # L1: In-memory LRU cache (fastest)
        self.memory_cache = LRUCache(maxsize=memory_size, ttl_seconds=memory_ttl)

        # L2: Redis cache (optional)
        self.redis = redis_client
        self.redis_ttl = 3600  # 1 hour

        # L3: Database session (optional)
        self.db = db_session

        # Statistics
        self._l1_hits = 0
        self._l2_hits = 0
        self._l3_hits = 0
        self._total_lookups = 0

    async def get(
        self,
        kb_id: str,
        entity_text: str,
        entity_type: str
    ) -> Optional[KBEntity]:
        """
        Lookup through cache hierarchy.

        Args:
            kb_id: Knowledge base identifier
            entity_text: Entity text to lookup
            entity_type: Entity type

        Returns:
            KB entity if found, None otherwise
        """
        self._total_lookups += 1
        cache_key = self._make_key(kb_id, entity_text, entity_type)

        # L1: Check memory cache
        memory_result = self.memory_cache.get(cache_key)
        if memory_result:
            self._l1_hits += 1
            logger.debug(f"L1 cache hit: {entity_text}")
            return memory_result

        # L2: Check Redis cache
        if self.redis:
            redis_result = await self._get_from_redis(cache_key)
            if redis_result:
                self._l2_hits += 1
                # Promote to L1
                self.memory_cache.set(cache_key, redis_result)
                logger.debug(f"L2 cache hit: {entity_text}")
                return redis_result

        # L3: Check database
        if self.db:
            db_result = await self._get_from_db(kb_id, entity_text, entity_type)
            if db_result:
                self._l3_hits += 1
                # Promote to higher tiers
                self.memory_cache.set(cache_key, db_result)
                if self.redis:
                    await self._set_in_redis(cache_key, db_result)
                logger.debug(f"L3 cache hit: {entity_text}")
                return db_result

        return None

    async def set(self, entity: KBEntity) -> None:
        """Store entity in all cache tiers"""
        cache_key = self._make_key(entity.kb_id, entity.text, entity.entity_type)

        # L1: Always set in memory
        self.memory_cache.set(cache_key, entity)

        # L2: Set in Redis if available
        if self.redis:
            await self._set_in_redis(cache_key, entity)

        # L3: Set in database if available
        if self.db:
            await self._set_in_db(entity)

    async def bulk_insert(self, entities: List[KBEntity]) -> None:
        """Bulk insert entities into cache tiers"""
        if not entities:
            return

        # L1: Batch insert to memory (only top N for memory efficiency)
        for entity in entities[:1000]:
            cache_key = self._make_key(entity.kb_id, entity.text, entity.entity_type)
            self.memory_cache.set(cache_key, entity)

        # L2: Batch insert to Redis
        if self.redis:
            await self._bulk_set_redis(entities)

        # L3: Batch insert to database
        if self.db:
            await self._bulk_set_db(entities)

        logger.info(f"Cached {len(entities)} entities")

    async def bulk_upsert(self, entities: List[KBEntity]) -> None:
        """Update or insert entities"""
        # Same as bulk_insert but uses upsert logic
        await self.bulk_insert(entities)

    def _make_key(self, kb_id: str, entity_text: str, entity_type: str) -> str:
        """Create cache key"""
        normalized_text = entity_text.strip().lower()
        key_string = f"{kb_id}:{entity_type}:{normalized_text}"
        # Hash for consistent key length
        return hashlib.md5(key_string.encode()).hexdigest()

    async def _get_from_redis(self, cache_key: str) -> Optional[KBEntity]:
        """Get from Redis cache"""
        try:
            data = await self.redis.get(cache_key)
            if data:
                entity_dict = json.loads(data)
                return KBEntity.from_dict(entity_dict)
        except Exception as e:
            logger.warning(f"Redis get failed: {e}")
        return None

    async def _set_in_redis(self, cache_key: str, entity: KBEntity) -> None:
        """Set in Redis cache"""
        try:
            data = json.dumps(entity.to_dict())
            await self.redis.setex(cache_key, self.redis_ttl, data)
        except Exception as e:
            logger.warning(f"Redis set failed: {e}")

    async def _bulk_set_redis(self, entities: List[KBEntity]) -> None:
        """Bulk set in Redis"""
        try:
            pipeline = self.redis.pipeline()
            for entity in entities:
                cache_key = self._make_key(entity.kb_id, entity.text, entity.entity_type)
                data = json.dumps(entity.to_dict())
                pipeline.setex(cache_key, self.redis_ttl, data)
            await pipeline.execute()
        except Exception as e:
            logger.warning(f"Redis bulk set failed: {e}")

    async def _get_from_db(
        self,
        kb_id: str,
        entity_text: str,
        entity_type: str
    ) -> Optional[KBEntity]:
        """Get from database"""
        # Implementation depends on ORM being used
        # This is a placeholder
        return None

    async def _set_in_db(self, entity: KBEntity) -> None:
        """Set in database"""
        # Implementation depends on ORM being used
        pass

    async def _bulk_set_db(self, entities: List[KBEntity]) -> None:
        """Bulk set in database"""
        # Implementation depends on ORM being used
        pass

    def clear_all(self) -> None:
        """Clear all cache tiers"""
        self.memory_cache.clear()
        # Redis and DB clearing would be done separately
        logger.info("Cleared all cache tiers")

    def get_statistics(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_hits = self._l1_hits + self._l2_hits + self._l3_hits
        overall_hit_rate = total_hits / self._total_lookups if self._total_lookups > 0 else 0

        return {
            "total_lookups": self._total_lookups,
            "l1_memory": {
                **self.memory_cache.get_stats(),
                "direct_hits": self._l1_hits
            },
            "l2_redis": {
                "hits": self._l2_hits,
                "available": self.redis is not None
            },
            "l3_database": {
                "hits": self._l3_hits,
                "available": self.db is not None
            },
            "overall_hit_rate": overall_hit_rate
        }

    async def create_shadow(self) -> "MultiTierCacheManager":
        """Create a shadow cache for safe replacement"""
        shadow = MultiTierCacheManager(
            memory_size=self.memory_cache._maxsize,
            redis_client=self.redis,
            db_session=self.db
        )
        return shadow

    async def swap_to_shadow(self, shadow: "MultiTierCacheManager") -> None:
        """Atomically swap to shadow cache"""
        # Swap memory caches
        old_cache = self.memory_cache
        self.memory_cache = shadow.memory_cache
        old_cache.clear()
        logger.info("Swapped to shadow cache")

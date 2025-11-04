"""
Multi-Tier Caching System for Knowledge Bases

Implements a three-tier caching hierarchy:
1. L1: In-memory LRU cache (fastest, limited size)
2. L2: Redis cache (fast, shared across instances)
3. L3: PostgreSQL (persistent, searchable)
"""
from typing import Optional, List, Dict, Any
import asyncio
import pickle
import json
from datetime import datetime
from collections import OrderedDict

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False

from knowledge_bases.base import KBEntity, KBLookupResult
from logger import get_logger

logger = get_logger(__name__)


class LRUCache:
    """Thread-safe LRU cache implementation"""

    def __init__(self, maxsize: int = 10000):
        self.maxsize = maxsize
        self.cache: OrderedDict = OrderedDict()
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        async with self._lock:
            if key in self.cache:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                self.hits += 1
                return self.cache[key]

            self.misses += 1
            return None

    async def set(self, key: str, value: Any):
        """Set value in cache"""
        async with self._lock:
            if key in self.cache:
                # Update existing
                self.cache.move_to_end(key)
                self.cache[key] = value
            else:
                # Add new
                self.cache[key] = value

                # Remove oldest if over capacity
                if len(self.cache) > self.maxsize:
                    self.cache.popitem(last=False)

    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        async with self._lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False

    async def clear(self):
        """Clear entire cache"""
        async with self._lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0.0

        return {
            'size': len(self.cache),
            'maxsize': self.maxsize,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate
        }


class MultiTierCacheManager:
    """
    Three-tier caching system:
    Memory (L1) -> Redis (L2) -> PostgreSQL (L3)
    """

    def __init__(
        self,
        memory_maxsize: int = 10000,
        redis_url: Optional[str] = None,
        postgres_url: Optional[str] = None
    ):
        # L1: Memory cache
        self.memory_cache = LRUCache(maxsize=memory_maxsize)

        # L2: Redis cache
        self.redis_enabled = REDIS_AVAILABLE and redis_url is not None
        self.redis: Optional[aioredis.Redis] = None
        self.redis_url = redis_url
        self.redis_ttl = 3600  # 1 hour

        # L3: PostgreSQL cache
        self.postgres_enabled = ASYNCPG_AVAILABLE and postgres_url is not None
        self.postgres_pool = None
        self.postgres_url = postgres_url

        # Statistics
        self.stats = {
            'memory_hits': 0,
            'redis_hits': 0,
            'postgres_hits': 0,
            'misses': 0
        }

    async def initialize(self):
        """Initialize cache layers"""
        # Initialize Redis
        if self.redis_enabled and not self.redis:
            try:
                self.redis = await aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=False,
                    max_connections=50
                )
                logger.info("Redis cache initialized")

            except Exception as e:
                logger.error(f"Failed to initialize Redis: {e}")
                self.redis_enabled = False

        # Initialize PostgreSQL
        if self.postgres_enabled and not self.postgres_pool:
            try:
                self.postgres_pool = await asyncpg.create_pool(
                    self.postgres_url,
                    min_size=5,
                    max_size=20
                )
                logger.info("PostgreSQL cache initialized")

                # Create cache table if it doesn't exist
                await self._create_cache_table()

            except Exception as e:
                logger.error(f"Failed to initialize PostgreSQL: {e}")
                self.postgres_enabled = False

    async def _create_cache_table(self):
        """Create KB entity cache table in PostgreSQL"""
        if not self.postgres_pool:
            return

        async with self.postgres_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS kb_entity_cache (
                    id BIGSERIAL PRIMARY KEY,
                    cache_key TEXT NOT NULL UNIQUE,
                    kb_id TEXT NOT NULL,
                    entity_text TEXT NOT NULL,
                    entity_type TEXT,
                    entity_data JSONB NOT NULL,
                    cached_at TIMESTAMP DEFAULT NOW(),
                    INDEX idx_kb_lookup (kb_id, entity_text, entity_type)
                );

                CREATE INDEX IF NOT EXISTS idx_kb_entity_text ON kb_entity_cache(entity_text);
                CREATE INDEX IF NOT EXISTS idx_kb_id ON kb_entity_cache(kb_id);
            """)

    def _make_cache_key(self, kb_id: str, entity_text: str, entity_type: Optional[str]) -> str:
        """Generate cache key"""
        if entity_type:
            return f"{kb_id}:{entity_type}:{entity_text.lower()}"
        return f"{kb_id}:{entity_text.lower()}"

    async def get(
        self,
        kb_id: str,
        entity_text: str,
        entity_type: Optional[str] = None
    ) -> KBLookupResult:
        """
        Lookup through cache hierarchy

        Args:
            kb_id: Knowledge base identifier
            entity_text: Entity text to lookup
            entity_type: Optional entity type

        Returns:
            Lookup result with entity if found
        """
        start_time = asyncio.get_event_loop().time()
        cache_key = self._make_cache_key(kb_id, entity_text, entity_type)

        # L1: Check memory cache
        cached = await self.memory_cache.get(cache_key)
        if cached:
            lookup_time = (asyncio.get_event_loop().time() - start_time) * 1000
            self.stats['memory_hits'] += 1

            return KBLookupResult(
                found=True,
                entity=cached,
                cache_hit=True,
                cache_tier='memory',
                lookup_time_ms=lookup_time,
                kb_id=kb_id
            )

        # L2: Check Redis
        if self.redis_enabled and self.redis:
            try:
                redis_data = await self.redis.get(cache_key)
                if redis_data:
                    entity = pickle.loads(redis_data)
                    lookup_time = (asyncio.get_event_loop().time() - start_time) * 1000
                    self.stats['redis_hits'] += 1

                    # Promote to L1
                    await self.memory_cache.set(cache_key, entity)

                    return KBLookupResult(
                        found=True,
                        entity=entity,
                        cache_hit=True,
                        cache_tier='redis',
                        lookup_time_ms=lookup_time,
                        kb_id=kb_id
                    )

            except Exception as e:
                logger.error(f"Redis lookup error: {e}")

        # L3: Check PostgreSQL
        if self.postgres_enabled and self.postgres_pool:
            try:
                async with self.postgres_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        """
                        SELECT entity_data FROM kb_entity_cache
                        WHERE cache_key = $1
                        """,
                        cache_key
                    )

                    if row:
                        entity_data = row['entity_data']
                        entity = self._deserialize_entity(entity_data)
                        lookup_time = (asyncio.get_event_loop().time() - start_time) * 1000
                        self.stats['postgres_hits'] += 1

                        # Promote to higher tiers
                        if self.redis_enabled and self.redis:
                            try:
                                await self.redis.setex(
                                    cache_key,
                                    self.redis_ttl,
                                    pickle.dumps(entity)
                                )
                            except Exception as e:
                                logger.error(f"Redis set error: {e}")

                        await self.memory_cache.set(cache_key, entity)

                        return KBLookupResult(
                            found=True,
                            entity=entity,
                            cache_hit=True,
                            cache_tier='postgres',
                            lookup_time_ms=lookup_time,
                            kb_id=kb_id
                        )

            except Exception as e:
                logger.error(f"PostgreSQL lookup error: {e}")

        # Not found in any cache tier
        lookup_time = (asyncio.get_event_loop().time() - start_time) * 1000
        self.stats['misses'] += 1

        return KBLookupResult(
            found=False,
            cache_hit=False,
            lookup_time_ms=lookup_time,
            kb_id=kb_id
        )

    async def set(
        self,
        kb_id: str,
        entity_text: str,
        entity: KBEntity,
        entity_type: Optional[str] = None
    ):
        """
        Store entity in all cache tiers

        Args:
            kb_id: Knowledge base identifier
            entity_text: Entity text
            entity: Entity to cache
            entity_type: Optional entity type
        """
        cache_key = self._make_cache_key(kb_id, entity_text, entity_type)

        # Store in L1 (memory)
        await self.memory_cache.set(cache_key, entity)

        # Store in L2 (Redis)
        if self.redis_enabled and self.redis:
            try:
                await self.redis.setex(
                    cache_key,
                    self.redis_ttl,
                    pickle.dumps(entity)
                )
            except Exception as e:
                logger.error(f"Redis set error: {e}")

        # Store in L3 (PostgreSQL)
        if self.postgres_enabled and self.postgres_pool:
            try:
                async with self.postgres_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO kb_entity_cache (cache_key, kb_id, entity_text, entity_type, entity_data)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (cache_key) DO UPDATE
                        SET entity_data = EXCLUDED.entity_data,
                            cached_at = NOW()
                        """,
                        cache_key,
                        kb_id,
                        entity_text,
                        entity_type,
                        json.dumps(entity.to_dict())
                    )

            except Exception as e:
                logger.error(f"PostgreSQL set error: {e}")

    async def bulk_insert(self, entities: List[KBEntity]):
        """
        Bulk insert entities into cache

        Args:
            entities: List of entities to cache
        """
        if not entities:
            return

        # Insert into L3 (PostgreSQL) in bulk
        if self.postgres_enabled and self.postgres_pool:
            try:
                async with self.postgres_pool.acquire() as conn:
                    records = []
                    for entity in entities:
                        cache_key = self._make_cache_key(
                            entity.kb_id,
                            entity.canonical_name,
                            entity.entity_type
                        )

                        records.append((
                            cache_key,
                            entity.kb_id,
                            entity.canonical_name,
                            entity.entity_type,
                            json.dumps(entity.to_dict())
                        ))

                        # Also add to aliases
                        for alias in entity.aliases:
                            alias_key = self._make_cache_key(
                                entity.kb_id,
                                alias,
                                entity.entity_type
                            )
                            records.append((
                                alias_key,
                                entity.kb_id,
                                alias,
                                entity.entity_type,
                                json.dumps(entity.to_dict())
                            ))

                    if records:
                        await conn.executemany(
                            """
                            INSERT INTO kb_entity_cache (cache_key, kb_id, entity_text, entity_type, entity_data)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (cache_key) DO UPDATE
                            SET entity_data = EXCLUDED.entity_data,
                                cached_at = NOW()
                            """,
                            records
                        )

                        logger.debug(f"Bulk inserted {len(records)} entities into cache")

            except Exception as e:
                logger.error(f"Bulk insert error: {e}")

        # Optionally warm Redis cache with high-value entities
        if self.redis_enabled and self.redis and len(entities) <= 1000:
            try:
                pipe = self.redis.pipeline()
                for entity in entities[:1000]:  # Limit to top 1000
                    cache_key = self._make_cache_key(
                        entity.kb_id,
                        entity.canonical_name,
                        entity.entity_type
                    )
                    pipe.setex(cache_key, self.redis_ttl, pickle.dumps(entity))

                await pipe.execute()

            except Exception as e:
                logger.error(f"Redis bulk insert error: {e}")

    def _deserialize_entity(self, entity_data: Dict[str, Any]) -> KBEntity:
        """Deserialize entity from JSON"""
        from knowledge_bases.base import Relationship, RelationType

        # Deserialize relationships
        relationships = []
        for rel_data in entity_data.get('relationships', []):
            rel = Relationship(
                source_id=rel_data['source_id'],
                target_id=rel_data['target_id'],
                relation_type=RelationType(rel_data['relation_type']),
                confidence=rel_data.get('confidence', 1.0),
                metadata=rel_data.get('metadata', {})
            )
            relationships.append(rel)

        # Deserialize entity
        entity = KBEntity(
            kb_id=entity_data['kb_id'],
            entity_id=entity_data['entity_id'],
            entity_type=entity_data['entity_type'],
            canonical_name=entity_data['canonical_name'],
            aliases=entity_data.get('aliases', []),
            definition=entity_data.get('definition'),
            semantic_types=entity_data.get('semantic_types', []),
            relationships=relationships,
            metadata=entity_data.get('metadata', {}),
            last_updated=datetime.fromisoformat(entity_data['last_updated']) if 'last_updated' in entity_data else datetime.now()
        )

        return entity

    async def clear_all(self):
        """Clear all cache tiers"""
        # Clear memory
        await self.memory_cache.clear()

        # Clear Redis
        if self.redis_enabled and self.redis:
            try:
                # Note: This clears ALL keys in the Redis database
                # In production, you might want to use key patterns
                await self.redis.flushdb()
                logger.info("Cleared Redis cache")

            except Exception as e:
                logger.error(f"Error clearing Redis: {e}")

        # Clear PostgreSQL
        if self.postgres_enabled and self.postgres_pool:
            try:
                async with self.postgres_pool.acquire() as conn:
                    await conn.execute("TRUNCATE TABLE kb_entity_cache")
                logger.info("Cleared PostgreSQL cache")

            except Exception as e:
                logger.error(f"Error clearing PostgreSQL cache: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """Get cache statistics"""
        memory_stats = self.memory_cache.get_stats()

        total_hits = (
            self.stats['memory_hits'] +
            self.stats['redis_hits'] +
            self.stats['postgres_hits']
        )
        total_requests = total_hits + self.stats['misses']
        overall_hit_rate = total_hits / total_requests if total_requests > 0 else 0.0

        return {
            'memory': memory_stats,
            'redis_enabled': self.redis_enabled,
            'postgres_enabled': self.postgres_enabled,
            'tier_hits': {
                'memory': self.stats['memory_hits'],
                'redis': self.stats['redis_hits'],
                'postgres': self.stats['postgres_hits']
            },
            'misses': self.stats['misses'],
            'overall_hit_rate': overall_hit_rate,
            'total_requests': total_requests
        }

    async def close(self):
        """Cleanup resources"""
        if self.redis:
            await self.redis.close()

        if self.postgres_pool:
            await self.postgres_pool.close()

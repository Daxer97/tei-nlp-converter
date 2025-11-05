"""
cache_manager.py - Enhanced caching layer with connection pooling and retry logic

Security: Uses JSON serialization instead of pickle to prevent arbitrary code execution
"""
import tempfile
import json
import hashlib
from typing import Optional, Any, Dict, List, Callable, Union
from datetime import datetime, timedelta
import redis
from redis import ConnectionPool, Redis
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError
from functools import lru_cache, wraps
import time
from logger import get_logger

logger = get_logger(__name__)

class RedisCachePool:
    """Redis connection pool manager with health checks"""
    
    _instance = None
    _pool = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisCachePool, cls).__new__(cls)
        return cls._instance
    
    def get_pool(self, redis_url: str, max_connections: int = 50) -> ConnectionPool:
        """Get or create Redis connection pool"""
        if self._pool is None:
            self._pool = ConnectionPool.from_url(
                redis_url,
                max_connections=max_connections,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            logger.info(f"Redis connection pool created with {max_connections} max connections")
        return self._pool
    
    def close(self):
        """Close the connection pool"""
        if self._pool:
            self._pool.disconnect()
            self._pool = None
            logger.info("Redis connection pool closed")

class CacheManager:
    """
    Enhanced caching layer with connection pooling, retry logic, and fallback
    """
    
    def __init__(self, redis_url: Optional[str] = None, ttl: int = 3600, 
                 max_memory_cache: int = 1000, max_retries: int = 3):
        self.ttl = ttl
        self.max_memory_cache = max_memory_cache
        self.max_retries = max_retries
        self.memory_cache = {}
        self.redis_client = None
        self.redis_available = False
        self.last_redis_check = datetime.utcnow()
        self.redis_check_interval = timedelta(seconds=30)
        
        if redis_url:
            self._initialize_redis(redis_url)
    
    def _initialize_redis(self, redis_url: str):
        """Initialize Redis with connection pooling"""
        try:
            pool_manager = RedisCachePool()
            pool = pool_manager.get_pool(redis_url)
            self.redis_client = Redis(connection_pool=pool, decode_responses=False)
            
            # Test connection
            self.redis_client.ping()
            self.redis_available = True
            logger.info("Redis cache connected with pooling")
            
        except RedisError as e:
            logger.warning(f"Redis connection failed, using memory cache: {str(e)}")
            self.redis_client = None
            self.redis_available = False
    
    def _check_redis_health(self) -> bool:
        """Periodic Redis health check"""
        if not self.redis_client:
            return False
        
        # Don't check too frequently
        if (datetime.utcnow() - self.last_redis_check) < self.redis_check_interval:
            return self.redis_available
        
        try:
            self.redis_client.ping()
            self.redis_available = True
        except RedisError:
            self.redis_available = False
            logger.warning("Redis health check failed")
        
        self.last_redis_check = datetime.utcnow()
        return self.redis_available
    
    def _is_json_serializable(self, obj: Any) -> bool:
        """Check if object is safe for JSON serialization"""
        # Allow only JSON-safe types
        if obj is None:
            return True
        if isinstance(obj, (str, int, float, bool)):
            return True
        if isinstance(obj, (list, tuple)):
            return all(self._is_json_serializable(item) for item in obj)
        if isinstance(obj, dict):
            return all(
                isinstance(k, str) and self._is_json_serializable(v)
                for k, v in obj.items()
            )
        return False

    def _serialize(self, value: Any) -> bytes:
        """Safely serialize value to JSON bytes"""
        if not self._is_json_serializable(value):
            raise ValueError(
                f"Value type {type(value).__name__} is not JSON-serializable. "
                f"Only str, int, float, bool, list, dict, and None are allowed."
            )
        try:
            json_str = json.dumps(value, ensure_ascii=False, default=str)
            return json_str.encode('utf-8')
        except (TypeError, ValueError) as e:
            raise ValueError(f"Failed to serialize value: {e}")

    def _deserialize(self, data: bytes) -> Any:
        """Safely deserialize JSON bytes with validation"""
        try:
            json_str = data.decode('utf-8')
            value = json.loads(json_str)

            # Validate deserialized type
            if not self._is_json_serializable(value):
                logger.error(f"Deserialized value has invalid type: {type(value)}")
                raise ValueError("Invalid cached data type")

            return value
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to deserialize cached value: {e}")
            raise ValueError(f"Corrupted cache entry: {e}")

    def _with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute Redis operation with retry logic"""
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except RedisConnectionError as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.debug(f"Redis operation failed, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    
                    # Try to reconnect
                    if hasattr(self.redis_client, 'connection_pool'):
                        try:
                            self.redis_client.connection_pool.reset()
                        except:
                            pass
            except RedisError as e:
                # Non-connection errors shouldn't retry
                raise e
        
        # All retries exhausted
        logger.error(f"Redis operation failed after {self.max_retries} attempts: {last_exception}")
        self.redis_available = False
        raise last_exception
    
    def _generate_key(self, prefix: str, text: str, domain: str = "") -> str:
        """Generate cache key with proper namespacing"""
        content = f"{prefix}:{domain}:{text}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()
        return f"tei_nlp:{prefix}:{hash_val}"
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache with fallback"""
        # Try Redis first if available
        if self.redis_client and self._check_redis_health():
            try:
                value = self._with_retry(self.redis_client.get, key)
                if value:
                    try:
                        return self._deserialize(value)
                    except ValueError as e:
                        logger.error(f"Failed to deserialize cached value: {e}")
                        # Delete corrupted cache entry
                        self._with_retry(self.redis_client.delete, key)
            except RedisError as e:
                logger.debug(f"Redis get error, falling back to memory: {e}")
        
        # Fall back to memory cache
        if key in self.memory_cache:
            item = self.memory_cache[key]
            if item['expires'] > datetime.utcnow():
                logger.debug(f"Memory cache hit for key: {key[:30]}...")
                return item['value']
            else:
                del self.memory_cache[key]
        
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with fallback"""
        ttl = ttl or self.ttl
        success = False

        # Try Redis first if available
        if self.redis_client and self._check_redis_health():
            try:
                serialized = self._serialize(value)
                self._with_retry(self.redis_client.setex, key, ttl, serialized)
                success = True
                logger.debug(f"Cached to Redis: {key[:30]}...")
            except (RedisError, ValueError) as e:
                logger.debug(f"Redis set error, falling back to memory: {e}")
        
        # Always cache to memory as fallback
        self._set_memory_cache(key, value, ttl)
        
        return success
    
    def _set_memory_cache(self, key: str, value: Any, ttl: int):
        """Set value in memory cache with LRU eviction"""
        # Implement LRU eviction when cache is full
        if len(self.memory_cache) >= self.max_memory_cache:
            # Remove 10% of oldest entries
            num_to_remove = max(1, self.max_memory_cache // 10)
            oldest = sorted(self.memory_cache.items(), 
                          key=lambda x: x[1].get('last_accessed', x[1]['expires']))[:num_to_remove]
            for old_key, _ in oldest:
                del self.memory_cache[old_key]
            logger.debug(f"Evicted {num_to_remove} cache entries")
        
        self.memory_cache[key] = {
            'value': value,
            'expires': datetime.utcnow() + timedelta(seconds=ttl),
            'last_accessed': datetime.utcnow()
        }
    
    def delete(self, key: str) -> bool:
        """Delete value from cache"""
        deleted = False
        
        # Delete from Redis
        if self.redis_client and self._check_redis_health():
            try:
                deleted = bool(self._with_retry(self.redis_client.delete, key))
            except RedisError as e:
                logger.debug(f"Redis delete error: {e}")
        
        # Delete from memory
        if key in self.memory_cache:
            del self.memory_cache[key]
            deleted = True
        
        return deleted
    
    def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching a pattern"""
        count = 0
        
        # Clear from Redis
        if self.redis_client and self._check_redis_health():
            try:
                cursor = 0
                while True:
                    cursor, keys = self._with_retry(
                        self.redis_client.scan, 
                        cursor, 
                        match=pattern, 
                        count=100
                    )
                    if keys:
                        self._with_retry(self.redis_client.delete, *keys)
                        count += len(keys)
                    if cursor == 0:
                        break
            except RedisError as e:
                logger.error(f"Failed to clear pattern {pattern}: {e}")
        
        # Clear from memory
        keys_to_delete = [k for k in self.memory_cache.keys() if pattern.replace('*', '') in k]
        for key in keys_to_delete:
            del self.memory_cache[key]
            count += 1
        
        logger.info(f"Cleared {count} cache entries matching pattern: {pattern}")
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        stats = {
            'memory_cache_size': len(self.memory_cache),
            'memory_cache_max': self.max_memory_cache,
            'redis_available': self.redis_available,
            'ttl': self.ttl
        }
        
        if self.redis_client and self._check_redis_health():
            try:
                info = self._with_retry(self.redis_client.info, 'memory')
                stats.update({
                    'redis_memory_used': info.get('used_memory_human', 'N/A'),
                    'redis_memory_peak': info.get('used_memory_peak_human', 'N/A'),
                    'redis_connected_clients': self._with_retry(self.redis_client.client_list).__len__()
                })
                
                # Get key count
                db_info = self._with_retry(self.redis_client.info, 'keyspace')
                if 'db0' in db_info:
                    stats['redis_keys'] = db_info['db0']['keys']
            except RedisError:
                pass
        
        return stats
    
    def clear_expired(self):
        """Clear expired entries from memory cache"""
        now = datetime.utcnow()
        expired = [k for k, v in self.memory_cache.items() 
                  if v['expires'] <= now]
        
        for key in expired:
            del self.memory_cache[key]
        
        if expired:
            logger.info(f"Cleared {len(expired)} expired memory cache entries")
    
    def warmup(self, keys: List[str], fetch_func: Callable):
        """Warm up cache with frequently accessed data"""
        warmed = 0
        for key in keys:
            if not self.get(key):
                try:
                    value = fetch_func(key)
                    if value:
                        self.set(key, value)
                        warmed += 1
                except Exception as e:
                    logger.debug(f"Failed to warm up key {key}: {e}")
        
        logger.info(f"Cache warmup completed: {warmed}/{len(keys)} keys loaded")
    
    def close(self):
        """Clean up resources"""
        if self.redis_client:
            try:
                self.redis_client.close()
            except:
                pass
        self.memory_cache.clear()

def cache_result(cache_manager: CacheManager, prefix: str = "nlp", 
                 ttl: Optional[int] = None):
    """
    Decorator for caching function results with automatic key generation
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate cache key from function arguments
            cache_key = _generate_cache_key(prefix, func.__name__, args, kwargs)
            
            # Try to get from cache
            cached = cache_manager.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                from metrics import cache_hits
                cache_hits.inc()
                return cached
            
            # Execute function
            from metrics import cache_misses
            cache_misses.inc()
            result = await func(*args, **kwargs)
            
            # Store in cache
            cache_manager.set(cache_key, result, ttl)
            logger.debug(f"Cache miss for {func.__name__}, stored result")
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Generate cache key from function arguments
            cache_key = _generate_cache_key(prefix, func.__name__, args, kwargs)
            
            # Try to get from cache
            cached = cache_manager.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Store in cache
            cache_manager.set(cache_key, result, ttl)
            logger.debug(f"Cache miss for {func.__name__}, stored result")
            
            return result
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator

def _generate_cache_key(prefix: str, func_name: str, args: tuple, kwargs: dict) -> str:
    """Generate a unique cache key from function arguments"""
    # Create a string representation of arguments
    key_parts = [prefix, func_name]
    
    # Add args (skip 'self' if present)
    args_to_use = args[1:] if args and hasattr(args[0], '__class__') else args
    key_parts.append(str(args_to_use))
    
    # Add sorted kwargs
    if kwargs:
        sorted_kwargs = sorted(kwargs.items())
        key_parts.append(str(sorted_kwargs))
    
    # Generate hash
    key_str = ":".join(key_parts)
    return f"{prefix}:{func_name}:{hashlib.md5(key_str.encode()).hexdigest()}"

"""
metrics.py - Application metrics for monitoring
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from functools import wraps
import time

# Metrics definitions
request_count = Counter(
    'tei_nlp_requests_total', 
    'Total requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'tei_nlp_request_duration_seconds',
    'Request duration',
    ['method', 'endpoint']
)

active_tasks = Gauge(
    'tei_nlp_active_tasks',
    'Number of active background tasks'
)

nlp_processing_duration = Histogram(
    'tei_nlp_processing_duration_seconds',
    'NLP processing duration',
    ['source']  # 'local' or 'remote'
)

cache_hits = Counter(
    'tei_nlp_cache_hits_total',
    'Cache hit count'
)

cache_misses = Counter(
    'tei_nlp_cache_misses_total',
    'Cache miss count'
)

circuit_breaker_state = Gauge(
    'tei_nlp_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half-open)',
    ['service']
)

def track_request(method: str, endpoint: str):
    """Decorator to track request metrics"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            status = 200
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = 500
                raise
            finally:
                duration = time.time() - start
                request_count.labels(method, endpoint, status).inc()
                request_duration.labels(method, endpoint).observe(duration)
        return wrapper
    return decorator

def get_metrics():
    """Get Prometheus metrics"""
    return generate_latest()

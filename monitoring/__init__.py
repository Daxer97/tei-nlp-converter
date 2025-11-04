"""
Monitoring Module

Provides comprehensive monitoring, metrics collection, health checks,
auto-discovery, and configuration hot-reload capabilities.

Quick Start:
    from monitoring import MetricsCollector, HealthCheckManager

    # Initialize metrics
    metrics = MetricsCollector()
    metrics.start()

    # Record metrics
    metrics.record_request(
        endpoint="/process",
        duration_ms=150,
        status_code=200
    )

    # Health checks
    health = HealthCheckManager()
    await health.register_check("database", check_database)
    status = await health.get_health_status()
"""

from .metrics import (
    MetricsCollector,
    MetricType,
    Metric,
    MetricsSnapshot
)

from .health import (
    HealthCheckManager,
    HealthStatus,
    HealthCheck,
    ComponentHealth
)

from .discovery import (
    AutoDiscoveryService,
    DiscoverySource,
    DiscoveredComponent
)

from .config_reload import (
    ConfigReloadManager,
    ConfigWatcher,
    ReloadResult
)

__all__ = [
    # Metrics
    "MetricsCollector",
    "MetricType",
    "Metric",
    "MetricsSnapshot",

    # Health checks
    "HealthCheckManager",
    "HealthStatus",
    "HealthCheck",
    "ComponentHealth",

    # Auto-discovery
    "AutoDiscoveryService",
    "DiscoverySource",
    "DiscoveredComponent",

    # Config reload
    "ConfigReloadManager",
    "ConfigWatcher",
    "ReloadResult",
]

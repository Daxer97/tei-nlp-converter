# Monitoring and Observability System

The monitoring system provides comprehensive observability for the NLP pipeline with metrics collection, health checks, auto-discovery, and configuration hot-reload capabilities.

## Table of Contents

- [Overview](#overview)
- [Components](#components)
  - [Metrics Collection](#metrics-collection)
  - [Health Checks](#health-checks)
  - [Auto-Discovery](#auto-discovery)
  - [Config Hot-Reload](#config-hot-reload)
- [Quick Start](#quick-start)
- [Dashboards](#dashboards)
- [Alerts](#alerts)
- [API Reference](#api-reference)
- [Best Practices](#best-practices)

## Overview

The monitoring system tracks all aspects of pipeline operation:

- **Request metrics**: Latency, throughput, error rates
- **Pipeline metrics**: Stage durations, entity counts
- **Component metrics**: Model performance, KB lookups, cache hits
- **System metrics**: CPU, memory, resource usage
- **Health status**: Component health checks
- **Auto-discovery**: New models and KBs
- **Config changes**: Hot-reload tracking

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Monitoring System                      │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Metrics    │  │    Health    │  │    Auto-     │  │
│  │  Collector   │  │    Checks    │  │  Discovery   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│         │                  │                  │          │
│         │                  │                  │          │
│         ▼                  ▼                  ▼          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Prometheus  │  │ Health API   │  │  Registry    │  │
│  │   Export     │  │   /health    │  │   Updates    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │           Config Hot-Reload Manager              │   │
│  │  - Watches config files                          │   │
│  │  - Reloads on change                             │   │
│  │  - Tracks reload history                         │   │
│  └──────────────────────────────────────────────────┘   │
│                                                           │
└─────────────────────────────────────────────────────────┘
         │                                    │
         ▼                                    ▼
  ┌─────────────┐                      ┌─────────────┐
  │  Prometheus │                      │   Grafana   │
  │   Server    │                      │  Dashboard  │
  └─────────────┘                      └─────────────┘
```

## Components

### Metrics Collection

The `MetricsCollector` tracks all pipeline operations with Prometheus-compatible export.

**Features:**
- Counter, gauge, histogram metrics
- Request tracking (latency, status codes)
- Pipeline stage metrics
- Component performance
- KB cache hit rates
- Hot-swap operations
- Automatic aggregation

**Example:**

```python
from monitoring import MetricsCollector

# Initialize
collector = MetricsCollector()
collector.start()

# Record request
collector.record_request(
    endpoint="/process",
    duration_ms=150,
    status_code=200,
    method="POST"
)

# Record pipeline stage
collector.record_stage(
    stage="ner",
    duration_ms=100,
    entity_count=10
)

# Record KB lookup
collector.record_kb_lookup(
    kb_id="umls",
    duration_ms=50,
    cache_hit=True,
    found=True
)

# Get snapshot
snapshot = collector.get_snapshot()
print(f"Throughput: {snapshot.throughput_per_second:.2f} req/s")
print(f"P95 latency: {snapshot.p95_latency_ms:.2f}ms")
print(f"Error rate: {snapshot.error_rate:.2%}")

# Export for Prometheus
prometheus_metrics = collector.export_prometheus()

# Export as JSON
json_metrics = collector.export_json()
```

**Tracked Metrics:**

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Total HTTP requests |
| `http_request_duration_ms` | Histogram | Request latency |
| `http_requests_errors_total` | Counter | HTTP errors |
| `pipeline_stage_duration_ms` | Histogram | Stage duration |
| `pipeline_entities_extracted` | Histogram | Entities per stage |
| `pipeline_stage_errors_total` | Counter | Stage errors |
| `component_duration_ms` | Histogram | Component execution time |
| `kb_lookup_duration_ms` | Histogram | KB lookup time |
| `kb_cache_lookups_total` | Counter | Cache hits/misses |
| `model_prediction_duration_ms` | Histogram | Model prediction time |
| `hot_swap_duration_ms` | Histogram | Hot-swap duration |
| `hot_swaps_total` | Counter | Total hot-swaps |

### Health Checks

The `HealthCheckManager` monitors component health with periodic checks.

**Features:**
- Periodic health checks
- Configurable intervals and timeouts
- Overall system status
- Component-specific status
- Automatic status updates

**Example:**

```python
from monitoring import HealthCheckManager, HealthStatus, ComponentHealth

# Initialize
manager = HealthCheckManager()

# Register health checks
async def check_database():
    try:
        await db.execute("SELECT 1")
        return ComponentHealth(
            component_name="database",
            status=HealthStatus.HEALTHY,
            message="Connection OK"
        )
    except Exception as e:
        return ComponentHealth(
            component_name="database",
            status=HealthStatus.UNHEALTHY,
            message=str(e)
        )

manager.register_check(
    "database",
    check_database,
    interval_seconds=30
)

# Start health checks
await manager.start()

# Get overall status
status = await manager.get_health_status()
print(f"System status: {status['overall_status']}")
print(f"Healthy components: {status['summary']['healthy']}")

# Get specific component status
db_status = manager.get_component_status("database")
print(f"Database: {db_status.status.value}")

# Run check immediately
result = await manager.run_check_now("database")
```

**Health Status Levels:**
- `HEALTHY`: Component functioning normally
- `DEGRADED`: Has issues but functional
- `UNHEALTHY`: Not functioning
- `UNKNOWN`: Status unknown

**Common Health Checks:**
```python
# Database
manager.register_check("database", check_database_health, interval_seconds=30)

# Redis
manager.register_check("redis", check_redis_health, interval_seconds=30)

# External APIs
manager.register_check(
    "umls",
    lambda: check_external_api_health("umls", "https://uts-ws.nlm.nih.gov"),
    interval_seconds=60
)

# Models
manager.register_check(
    "biobert",
    lambda: check_model_health("biobert", biobert_model),
    interval_seconds=300
)

# Knowledge bases
manager.register_check(
    "umls_kb",
    lambda: check_kb_health("umls", umls_provider),
    interval_seconds=60
)
```

### Auto-Discovery

The `AutoDiscoveryService` automatically finds new models and knowledge bases.

**Features:**
- Multiple discovery sources (Hugging Face, spaCy, registries)
- Domain filtering
- Quality filtering (downloads, stars)
- Periodic scanning
- Deduplication

**Example:**

```python
from monitoring import AutoDiscoveryService, DiscoverySource

# Initialize
discovery = AutoDiscoveryService(
    scan_interval_hours=24,
    auto_register=False
)

# Add sources
discovery.add_source(DiscoverySource.HUGGINGFACE, {
    "filter_domains": ["medical", "legal"],
    "min_downloads": 1000,
    "tags": ["ner", "token-classification"]
})

discovery.add_source(DiscoverySource.SPACY, {
    "filter_domains": ["medical"]
})

# Start periodic scanning
await discovery.start()

# Manual discovery
discovered = await discovery.discover()

print(f"Found {len(discovered)} new components:")
for component in discovered:
    print(f"  - {component.name} ({component.source.value})")
    print(f"    Downloads: {component.downloads}")
    print(f"    Domain: {component.domain}")

# Get top discovered by downloads
top_models = discovery.get_top_discovered(limit=10, sort_by="downloads")

# Filter by domain
medical_models = discovery.get_discovered(
    component_type="ner_model",
    domain="medical"
)
```

**Discovery Sources:**
- `HUGGINGFACE`: Hugging Face Model Hub
- `SPACY`: spaCy model registry
- `REGISTRY_FILE`: Local YAML/JSON registry
- `DATABASE`: Internal database
- `GITHUB`: GitHub repositories

**Registry File Format:**
```yaml
# models_registry.yaml
models:
  - id: "biobert"
    name: "BioBERT"
    provider: "huggingface"
    url: "https://huggingface.co/dmis-lab/biobert-base-cased-v1.1"
    domain: "medical"
    capabilities: ["DISEASE", "DRUG", "GENE"]

knowledge_bases:
  - id: "umls"
    name: "UMLS Metathesaurus"
    provider: "nlm"
    url: "https://uts.nlm.nih.gov"
    domain: "medical"
```

### Config Hot-Reload

The `ConfigReloadManager` watches configuration files and reloads them without restarting.

**Features:**
- File change detection (checksum-based)
- Automatic reload
- Validation before applying
- Rollback on failure
- Reload history
- Change tracking

**Example:**

```python
from monitoring import ConfigReloadManager
from pathlib import Path

# Initialize
manager = ConfigReloadManager()

# Register config files
async def reload_pipeline_config(config_path: Path):
    # Load new config
    config = PipelineConfig.from_yaml(config_path)

    # Validate
    if not validate_config(config):
        raise ValueError("Invalid config")

    # Apply
    await pipeline.update_config(config)
    logger.info("Pipeline config reloaded")

manager.register_config(
    Path("config/pipeline/medical.yaml"),
    reload_pipeline_config,
    check_interval_seconds=10
)

# Start watching
await manager.start()

# Config changes are automatically detected and reloaded
# No manual intervention needed!

# Get reload history
history = manager.get_reload_history(limit=10)
for result in history:
    print(f"{result.timestamp}: {result.config_path}")
    print(f"  Status: {result.status.value}")
    if result.changes:
        print(f"  Changes: {len(result.changes)} keys modified")

# Manual reload
result = await manager.reload_now(Path("config/pipeline/medical.yaml"))

# Get stats
stats = manager.get_stats()
print(f"Total reloads: {stats['total_reloads']}")
print(f"Success rate: {stats['success_rate']:.1%}")
```

**Reload Process:**
1. File change detected (checksum changed)
2. Load and parse new config
3. Call reload handler (validates and applies)
4. Track changes
5. Record result in history
6. On error: Log failure, keep old config

## Quick Start

### Installation

```bash
# Install dependencies
pip install prometheus-client aiohttp pyyaml

# Start Prometheus
docker run -d -p 9090:9090 \
  -v $(pwd)/config/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus

# Start Grafana
docker run -d -p 3000:3000 grafana/grafana
```

### Basic Setup

```python
from monitoring import (
    MetricsCollector,
    HealthCheckManager,
    AutoDiscoveryService,
    ConfigReloadManager
)

# Metrics
metrics = MetricsCollector()
metrics.start()

# Health checks
health = HealthCheckManager()
health.register_check("database", check_database, interval_seconds=30)
health.register_check("redis", check_redis, interval_seconds=30)
await health.start()

# Auto-discovery
discovery = AutoDiscoveryService(scan_interval_hours=24)
discovery.add_source(DiscoverySource.HUGGINGFACE, {"filter_domains": ["medical"]})
await discovery.start()

# Config hot-reload
config_manager = ConfigReloadManager()
config_manager.register_config(
    Path("config/pipeline/medical.yaml"),
    reload_pipeline_config
)
await config_manager.start()

# All systems running!
# Metrics available at /metrics
# Health status at /health
```

### FastAPI Integration

```python
from fastapi import FastAPI
from monitoring import get_global_collector, HealthCheckManager

app = FastAPI()

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    collector = get_global_collector()
    return Response(
        content=collector.export_prometheus(),
        media_type="text/plain"
    )

# Health endpoint
@app.get("/health")
async def health():
    manager = get_health_manager()
    status = await manager.get_health_status()
    return status

# Record metrics on requests
@app.middleware("http")
async def metrics_middleware(request, call_next):
    start_time = time.time()

    response = await call_next(request)

    duration_ms = (time.time() - start_time) * 1000
    collector = get_global_collector()
    collector.record_request(
        endpoint=request.url.path,
        duration_ms=duration_ms,
        status_code=response.status_code,
        method=request.method
    )

    return response
```

## Dashboards

### Grafana Setup

1. **Import dashboard:**
   ```bash
   curl -X POST http://localhost:3000/api/dashboards/db \
     -H "Content-Type: application/json" \
     -d @config/monitoring/grafana-dashboard.json
   ```

2. **Access dashboard:**
   - URL: `http://localhost:3000`
   - Login: admin/admin
   - Navigate to "NLP Pipeline Monitoring"

### Key Panels

**Request Metrics:**
- Request rate by endpoint
- P50/P95/P99 latency
- Error rate

**Pipeline Metrics:**
- Stage durations
- Entities extracted per stage
- Stage error rates

**Component Metrics:**
- Model prediction latency
- KB lookup latency
- KB cache hit rate

**System Health:**
- Component health status
- Hot-swap operations
- Resource usage

## Alerts

Alerting rules are defined in `config/monitoring/alerts.yml`.

### Critical Alerts

| Alert | Threshold | Description |
|-------|-----------|-------------|
| `CriticalErrorRate` | >20% for 2m | Very high error rate |
| `ComponentUnhealthy` | 5m | Component is unhealthy |
| `DatabaseConnectionIssues` | 2m | Cannot connect to DB |

### Warning Alerts

| Alert | Threshold | Description |
|-------|-----------|-------------|
| `HighErrorRate` | >5% for 5m | Elevated error rate |
| `HighLatency` | P95 >1s for 10m | High request latency |
| `PipelineStageFailures` | >0.1 errors/sec | Stage failures |
| `HotSwapFailures` | Any failure | Hot-swap failed |
| `ModelPerformanceDegradation` | 2x increase | Model slowing down |

### Info Alerts

| Alert | Threshold | Description |
|-------|-----------|-------------|
| `LowKBCacheHitRate` | <50% for 15m | Poor cache performance |
| `LowThroughput` | <0.1 req/sec for 10m | Low request volume |

## API Reference

### MetricsCollector

```python
class MetricsCollector:
    def start()
    def stop()
    def increment_counter(name, value, labels, help_text)
    def set_gauge(name, value, labels, help_text)
    def observe_histogram(name, value, labels, help_text)
    def record_request(endpoint, duration_ms, status_code, method)
    def record_stage(stage, duration_ms, entity_count, error)
    def record_component_performance(component_type, component_id, duration_ms, success)
    def record_kb_lookup(kb_id, duration_ms, cache_hit, found)
    def record_model_prediction(model_id, duration_ms, entity_count, confidence_avg)
    def record_hot_swap(component_type, component_id, duration_ms, success)
    def get_snapshot() -> MetricsSnapshot
    def export_prometheus() -> str
    def export_json() -> Dict
```

### HealthCheckManager

```python
class HealthCheckManager:
    def register_check(name, check_func, interval_seconds, timeout_seconds, enabled)
    def unregister_check(name)
    async def start()
    async def stop()
    async def run_check_now(name) -> ComponentHealth
    async def get_health_status() -> Dict
    def get_component_status(name) -> ComponentHealth
    def list_checks() -> List[str]
```

### AutoDiscoveryService

```python
class AutoDiscoveryService:
    def add_source(source, config)
    def remove_source(source)
    async def start()
    async def stop()
    async def discover() -> List[DiscoveredComponent]
    def get_discovered(component_type, domain, source) -> List
    def get_top_discovered(limit, sort_by) -> List
```

### ConfigReloadManager

```python
class ConfigReloadManager:
    def register_config(config_path, reload_handler, check_interval_seconds)
    def unregister_config(config_path)
    async def start()
    async def stop()
    async def reload_now(config_path) -> ReloadResult
    def get_reload_history(config_path, limit) -> List[ReloadResult]
    def list_watched_configs() -> List[Path]
```

## Best Practices

### Metrics

1. **Consistent labeling**: Use consistent label names across metrics
2. **Reasonable cardinality**: Avoid high-cardinality labels (user IDs, timestamps)
3. **Histogram buckets**: Choose appropriate buckets for latency metrics
4. **Counter vs gauge**: Use counters for cumulative values, gauges for point-in-time

### Health Checks

1. **Appropriate intervals**: Balance freshness vs overhead (30-60s typical)
2. **Timeout configuration**: Set timeouts shorter than intervals
3. **Graceful degradation**: Mark as degraded rather than unhealthy when possible
4. **Test what matters**: Check actual functionality, not just connectivity

### Auto-Discovery

1. **Quality filters**: Set minimum thresholds (downloads, stars)
2. **Domain filtering**: Filter by relevant domains to reduce noise
3. **Review before registering**: Don't auto-register without review
4. **Regular scans**: Daily or weekly scanning

### Config Hot-Reload

1. **Validation**: Always validate before applying
2. **Rollback**: Implement rollback on validation failure
3. **Change tracking**: Log all configuration changes
4. **Test reload**: Test reload logic before production

## Troubleshooting

### High Memory Usage

**Symptom**: Metrics collector using excessive memory

**Solution**:
- Reduce `history_size` parameter
- Reduce metric cardinality (fewer labels)
- Increase aggregation window

### Health Checks Timing Out

**Symptom**: Health checks frequently timeout

**Solution**:
- Increase `timeout_seconds`
- Increase `interval_seconds`
- Optimize check implementation

### Auto-Discovery Finding Too Many Models

**Symptom**: Discovering hundreds of irrelevant models

**Solution**:
- Add domain filtering
- Increase min_downloads threshold
- Add more specific tags

### Config Reload Failures

**Symptom**: Config changes not being applied

**Solution**:
- Check validation logic
- Review error logs
- Check file permissions
- Verify reload handler

## Next Steps

- See [pipeline/README.md](/pipeline/README.md) for pipeline orchestration
- See [ARCHITECTURE.md](/ARCHITECTURE.md) for overall system design
- Configure alerts for your specific needs
- Create custom Grafana dashboards
- Set up Alertmanager for notifications

# Knowledge Base Integration

This module provides comprehensive knowledge base integration for entity enrichment in domain-specific NLP processing.

## Overview

The knowledge base system enriches extracted entities with authoritative information from specialized databases:

- **Medical**: UMLS, RxNorm, SNOMED CT
- **Legal**: USC, CFR, CourtListener
- **Extensible**: Easy to add new KB providers

## Architecture

### Core Components

1. **KB Provider Registry** (`registry.py`)
   - Manages multiple KB providers
   - Handles fallback chains
   - Tracks KB metadata

2. **KB Providers** (`providers/`)
   - UMLS: Comprehensive medical terminology
   - RxNorm: Drug normalization
   - USC: Federal statutes
   - CourtListener: Case law

3. **Multi-Tier Caching** (`cache.py`)
   - L1: Memory (LRU, <1ms)
   - L2: Redis (1-5ms)
   - L3: PostgreSQL (5-20ms)

4. **Streaming Service** (`streaming.py`)
   - Background KB data streaming
   - Batch processing
   - Progress tracking

5. **Sync Service** (`sync.py`)
   - Scheduled synchronization
   - Incremental updates
   - Status persistence

## Quick Start

### 1. Initialize KB Providers

```python
from knowledge_bases import (
    KnowledgeBaseRegistry,
    MultiTierCacheManager,
    KBStreamingService,
    KBSyncService
)
from knowledge_bases.providers.umls_provider import UMLSProvider, get_umls_metadata
from knowledge_bases.providers.rxnorm_provider import RxNormProvider, get_rxnorm_metadata

# Create registry
kb_registry = KnowledgeBaseRegistry()

# Register medical KB providers
umls_provider = UMLSProvider({'api_key': 'your_umls_api_key'})
await umls_provider.initialize()
kb_registry.register_provider(umls_provider, get_umls_metadata())

rxnorm_provider = RxNormProvider({})
await rxnorm_provider.initialize()
kb_registry.register_provider(rxnorm_provider, get_rxnorm_metadata())
```

### 2. Initialize Caching

```python
# Create cache manager
cache_manager = MultiTierCacheManager(
    memory_maxsize=10000,
    redis_url="redis://localhost:6379",
    postgres_url="postgresql://localhost/tei_nlp"
)

await cache_manager.initialize()
```

### 3. Lookup Entities

```python
# Lookup with fallback chain
result = await kb_registry.lookup_entity(
    entity_text="Morphine",
    kb_chain=["umls", "rxnorm"],
    entity_type="DRUG"
)

if result.found:
    entity = result.entity
    print(f"Canonical Name: {entity.canonical_name}")
    print(f"Entity ID: {entity.entity_id}")
    print(f"Semantic Types: {entity.semantic_types}")
    print(f"Definition: {entity.definition}")
    print(f"Relationships: {len(entity.relationships)}")
    print(f"Cache Hit: {result.cache_hit} (tier: {result.cache_tier})")
```

### 4. Stream KB Data (Background)

```python
# Create streaming service
streaming_service = KBStreamingService(
    kb_registry=kb_registry,
    cache_manager=cache_manager,
    max_concurrent_streams=3
)

# Stream UMLS data in background
task_id = await streaming_service.stream_kb_background(
    kb_id="umls",
    entity_types=["DISEASE", "DRUG"],
    batch_size=1000
)

# Check progress
progress = streaming_service.get_progress(task_id)
print(f"Status: {progress.status}")
print(f"Entities streamed: {progress.entities_streamed}")
```

### 5. Schedule Automatic Syncs

```python
from knowledge_bases.base import KBSyncConfig

# Create sync service
sync_service = KBSyncService(
    kb_registry=kb_registry,
    streaming_service=streaming_service
)

await sync_service.initialize()

# Configure sync for UMLS (quarterly)
umls_config = KBSyncConfig(
    kb_id="umls",
    sync_frequency="quarterly",
    batch_size=1000,
    enabled=True,
    incremental=True
)

sync_service.schedule_sync("umls", umls_config)

# Manual sync if needed
progress = await sync_service.sync_now("umls", incremental=True)
```

## Medical Knowledge Bases

### UMLS (Unified Medical Language System)

**Provider:** `UMLSProvider`
**API:** https://uts.nlm.nih.gov

**Features:**
- 4+ million medical concepts
- Semantic types and relationships
- Multi-lingual support (English, Spanish, French, German, Italian, Japanese, Chinese)
- Cross-vocabulary mappings

**Setup:**
1. Register for UMLS account: https://uts.nlm.nih.gov/uts/signup-login
2. Get API key from your profile
3. Set environment variable: `export UMLS_API_KEY="your_key"`

**Example:**
```python
umls_provider = UMLSProvider({'api_key': os.environ['UMLS_API_KEY']})
await umls_provider.initialize()

# Lookup disease
entity = await umls_provider.lookup_entity("diabetes", "DISEASE")
print(entity.canonical_name)  # "Diabetes Mellitus"
print(entity.entity_id)  # "C0011849" (UMLS CUI)
print(entity.semantic_types)  # ["Disease or Syndrome"]
```

### RxNorm

**Provider:** `RxNormProvider`
**API:** https://rxnav.nlm.nih.gov/REST/

**Features:**
- 150k+ drug concepts
- Brand name to generic mappings
- Drug relationships (ingredients, dose forms)
- Free, no API key required

**Example:**
```python
rxnorm_provider = RxNormProvider({})
await rxnorm_provider.initialize()

# Lookup drug
entity = await rxnorm_provider.lookup_entity("Lipitor", "DRUG")
print(entity.canonical_name)  # "Atorvastatin"
print(entity.entity_id)  # "83367" (RxCUI)
print(entity.aliases)  # ["Lipitor", "Atorvastatin Calcium", ...]
```

### SNOMED CT

**Provider:** `SNOMEDProvider` (implementation in progress)
**License Required:** Yes

**Features:**
- Comprehensive clinical terminology
- Hierarchical relationships
- Used in EHR systems worldwide

## Legal Knowledge Bases

### USC (United States Code)

**Provider:** `USCProvider`
**API:** https://api.govinfo.gov

**Features:**
- Federal statutory law (54 titles)
- Section-level granularity
- Citation parsing
- Free (API key optional but recommended)

**Example:**
```python
usc_provider = USCProvider({'api_key': os.environ.get('GOVINFO_API_KEY')})
await usc_provider.initialize()

# Lookup statute
entity = await usc_provider.lookup_entity("18 U.S.C. § 1001", "STATUTE")
print(entity.canonical_name)  # "18 U.S.C. § 1001"
print(entity.definition)  # "Statements or entries generally"
print(entity.metadata['title_name'])  # "Crimes and Criminal Procedure"
```

### CourtListener

**Provider:** `CourtListenerProvider`
**API:** https://www.courtlistener.com/api/

**Features:**
- 10+ million court opinions
- Federal and state courts
- Case citations
- Free (API key recommended for higher limits)

**Example:**
```python
cl_provider = CourtListenerProvider({'api_key': os.environ.get('COURTLISTENER_API_KEY')})
await cl_provider.initialize()

# Lookup case
entity = await cl_provider.lookup_entity("347 U.S. 483", "CASE_CITATION")
print(entity.canonical_name)  # "Brown v. Board of Education"
print(entity.metadata['date_filed'])  # "1954-05-17"
print(entity.definition)  # Case summary
print(len(entity.relationships))  # Cases citing this case
```

## Caching Strategy

### Three-Tier Architecture

```
Lookup Request
    ↓
┌─────────────────────┐
│  L1: Memory Cache   │  <1ms
│  (10k entities)     │
└─────────────────────┘
    ↓ (miss)
┌─────────────────────┐
│  L2: Redis Cache    │  1-5ms
│  (1hr TTL)          │
└─────────────────────┘
    ↓ (miss)
┌─────────────────────┐
│  L3: PostgreSQL     │  5-20ms
│  (persistent)       │
└─────────────────────┘
    ↓ (miss)
┌─────────────────────┐
│  KB Provider API    │  100-500ms
└─────────────────────┘
```

### Cache Promotion

When an entity is found in L3 or from the API:
1. Store in L3 (PostgreSQL) for persistence
2. Store in L2 (Redis) with TTL
3. Store in L1 (memory) for fast access

### Configuration

```yaml
cache:
  memory:
    max_entities: 10000
    eviction_policy: "lru"

  redis:
    enabled: true
    url: "redis://localhost:6379"
    ttl_seconds: 3600

  postgres:
    enabled: true
    url: "postgresql://localhost/tei_nlp"
```

## Streaming & Synchronization

### Streaming Architecture

Large knowledge bases (millions of entities) are streamed incrementally:

```python
async for batch in provider.stream_entities(entity_type="DRUG", batch_size=1000):
    # Batch of 1000 entities
    await cache_manager.bulk_insert(batch)
```

### Sync Frequencies

- **UMLS**: Quarterly (releases in Feb, May, Aug, Nov)
- **RxNorm**: Monthly
- **USC**: Annual
- **CourtListener**: Weekly (most active)

### Sync Configuration

```python
from knowledge_bases.base import KBSyncConfig

config = KBSyncConfig(
    kb_id="umls",
    sync_frequency="quarterly",  # or "monthly", "weekly", "daily"
    batch_size=1000,
    enabled=True,
    incremental=True  # Only sync changes since last sync
)

sync_service.schedule_sync("umls", config)
```

## Performance Tuning

### Cache Hit Rates

Target: >80% cache hit rate

Monitor with:
```python
stats = cache_manager.get_statistics()
print(f"Overall hit rate: {stats['overall_hit_rate']:.1%}")
print(f"Memory hits: {stats['tier_hits']['memory']}")
print(f"Redis hits: {stats['tier_hits']['redis']}")
print(f"PostgreSQL hits: {stats['tier_hits']['postgres']}")
```

### Concurrent Lookups

Configure max concurrent lookups to avoid overwhelming APIs:

```yaml
performance:
  max_concurrent_lookups: 10
  lookup_timeout_seconds: 5
  retry_failed_lookups: true
  max_retries: 3
```

### Batch Processing

Process multiple entities in parallel:

```python
async def enrich_entities(entities: List[Entity]):
    tasks = [
        kb_registry.lookup_entity(entity.text, ["umls", "rxnorm"], entity.type)
        for entity in entities
    ]

    results = await asyncio.gather(*tasks)
    return results
```

## Error Handling

### Fallback Chains

If lookup fails in one KB, try the next:

```python
result = await kb_registry.lookup_entity(
    entity_text="Morphine",
    kb_chain=["umls", "rxnorm", "snomed"],  # Try in order
    entity_type="DRUG"
)
```

### Retry Logic

Failed lookups are automatically retried with exponential backoff:

```yaml
performance:
  retry_failed_lookups: true
  max_retries: 3
  retry_backoff_seconds: 1
```

## API Rate Limits

### UMLS
- Rate limit: 20 requests/second
- Daily quota: None
- Recommendation: Use caching aggressively

### RxNorm
- Rate limit: 20 requests/second
- No API key required
- Very stable and reliable

### GovInfo (USC)
- Rate limit: Depends on API key tier
- Free tier: 1,000 requests/hour
- Recommendation: Use API key

### CourtListener
- Without API key: 5,000 requests/day
- With API key: 50,000 requests/day
- Recommendation: Register for API key

## Adding New KB Providers

### 1. Implement Provider Interface

```python
from knowledge_bases.base import KnowledgeBaseProvider, KBEntity

class MyKBProvider(KnowledgeBaseProvider):
    def get_kb_id(self) -> str:
        return "my_kb"

    def get_capabilities(self) -> KBCapabilities:
        return KBCapabilities(
            entity_types=["MY_ENTITY_TYPE"],
            supports_relationships=True,
            # ...
        )

    async def initialize(self) -> bool:
        # Setup API connection
        pass

    async def stream_entities(self, entity_type, batch_size, since):
        # Stream entities in batches
        pass

    async def lookup_entity(self, entity_text, entity_type):
        # Lookup single entity
        pass

    async def get_relationships(self, entity_id):
        # Get relationships
        pass

    async def get_metadata(self, entity_id):
        # Get metadata
        pass
```

### 2. Create Metadata Function

```python
def get_my_kb_metadata() -> KBMetadata:
    return KBMetadata(
        kb_id="my_kb",
        provider="MyKBProvider",
        version="1.0",
        domain="my_domain",
        capabilities=KBCapabilities(...),
        stream_url="https://api.mykb.com",
        api_key_required=True,
        trusted=True,
        description="My custom knowledge base",
        cache_strategy="moderate",
        sync_frequency="monthly"
    )
```

### 3. Register Provider

```python
my_provider = MyKBProvider({'api_key': 'xxx'})
await my_provider.initialize()
kb_registry.register_provider(my_provider, get_my_kb_metadata())
```

## Configuration Files

Configuration examples are in `config/knowledge_bases/`:

- `medical.yaml`: Medical KB configuration
- `legal.yaml`: Legal KB configuration

## Database Schema

The KB system uses these tables:

- `kb_registry`: KB provider metadata
- `kb_entity_cache`: L3 cache for entities
- `kb_lookup_log`: Lookup statistics

## Troubleshooting

### Issue: Low cache hit rate

**Solution:**
- Increase memory cache size
- Increase Redis TTL
- Enable background streaming to pre-populate cache

### Issue: Slow lookups

**Solution:**
- Check API rate limits
- Increase concurrent lookup limit
- Verify network connectivity to APIs
- Check Redis/PostgreSQL performance

### Issue: Sync failures

**Solution:**
- Check API credentials
- Verify network connectivity
- Review sync logs
- Adjust batch size (lower if timeouts)

## Examples

See `examples/` directory for complete examples:

- `medical_enrichment.py`: Medical entity enrichment
- `legal_enrichment.py`: Legal document processing
- `custom_kb_provider.py`: Creating custom KB provider

## License

See LICENSE file for details.

## Support

For issues and questions:
- GitHub Issues: https://github.com/your-org/tei-nlp-converter/issues
- Documentation: See ARCHITECTURE.md

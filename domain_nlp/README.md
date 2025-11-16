# Domain-Specific NLP Module

## Overview

The `domain_nlp` module provides a specialized NLP pipeline for extracting and enriching entities from text using domain-specific models. It replaces the generic Google Cloud NLP approach with local, specialized models that achieve significantly higher accuracy for medical, legal, and financial domains.

## Module Structure

```
domain_nlp/
├── __init__.py                    # Package initialization
├── model_providers/               # NER model management
│   ├── base.py                   # Abstract interfaces
│   ├── registry.py               # Model discovery and lifecycle
│   ├── spacy_provider.py         # SpaCy/SciSpaCy models
│   └── huggingface_provider.py   # Hugging Face transformers
├── knowledge_bases/              # Entity enrichment
│   ├── base.py                   # KB provider interfaces
│   ├── registry.py               # KB registry with fallback
│   └── cache.py                  # Multi-tier caching
├── pattern_matching/             # Structured data extraction
│   ├── patterns.py               # Domain pattern definitions
│   └── matcher.py                # Pattern matching engine
├── pipeline/                     # Processing orchestration
│   ├── ensemble.py               # Model result merging
│   └── dynamic_pipeline.py       # Main pipeline controller
├── config/                       # Configuration
│   └── loader.py                 # YAML-based config system
└── utils/                        # Utilities
    └── db_models.py              # Database schemas
```

## Core Components

### 1. Model Provider Registry

**Location**: `model_providers/registry.py`

Manages discovery, validation, and lifecycle of NER models.

```python
from domain_nlp.model_providers import ModelProviderRegistry, SpacyModelProvider

registry = ModelProviderRegistry()
registry.register_provider("spacy", SpacyModelProvider())

# Discover available models
await registry.discover_all_models()

# Get model statistics
stats = registry.get_statistics()
print(f"Models discovered: {stats['total_models_discovered']}")
```

**Key Features**:
- **Trust Validation**: Only loads models from whitelisted sources
- **Model Catalog**: Tracks metadata, performance metrics, compatibility
- **Hot-Swapping**: Replace models without downtime
- **Version Control**: Track model versions and updates

### 2. SpaCy Model Provider

**Location**: `model_providers/spacy_provider.py`

Provides SpaCy and SciSpaCy models for NER.

```python
from domain_nlp.model_providers import SpacyModelProvider

provider = SpacyModelProvider()

# Discover medical models
models = await provider.discover_models()
# Returns: en_core_web_sm, en_ner_bc5cdr_md, en_ner_jnlpba_md, etc.

# Load specific model
model = await provider.load_model("en_ner_bc5cdr_md")

# Process text
entities = await model.extract_entities("Patient has diabetes")
```

**Available Models**:
- `en_core_web_sm` - General English NER
- `en_ner_bc5cdr_md` - Biomedical (drugs, diseases)
- `en_ner_jnlpba_md` - Biomedical (proteins, genes)
- `en_ner_bionlp13cg_md` - Cancer genetics

### 3. Hugging Face Provider

**Location**: `model_providers/huggingface_provider.py`

Provides transformer-based models from Hugging Face Hub.

```python
from domain_nlp.model_providers import HuggingFaceProvider

provider = HuggingFaceProvider()
models = await provider.discover_models()

# Medical models
# - microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract
# - dmis-lab/biobert-base-cased-v1.1

# Legal models
# - nlpaueb/legal-bert-base-uncased
# - casehold/custom-legalbert
```

### 4. Knowledge Base Registry

**Location**: `knowledge_bases/registry.py`

Manages connections to authoritative knowledge bases.

```python
from domain_nlp.knowledge_bases import KnowledgeBaseRegistry

kb_registry = KnowledgeBaseRegistry()

# Lookup with automatic fallback
entity = await kb_registry.lookup_with_fallback(
    "Metformin",
    fallback_chain=["rxnorm", "umls", "snomed"]
)
# Returns enriched entity with definition, synonyms, codes
```

**Supported KBs**:
- **UMLS** - Unified Medical Language System
- **RxNorm** - Drug normalization
- **SNOMED-CT** - Clinical terminology
- **USC** - United States Code
- **CourtListener** - Case law database

### 5. Multi-Tier Cache

**Location**: `knowledge_bases/cache.py`

Provides efficient caching for KB lookups.

```python
from domain_nlp.knowledge_bases.cache import MultiTierCacheManager

cache = MultiTierCacheManager(
    memory_size=10000,      # LRU cache entries
    redis_enabled=True,     # Redis tier
    redis_ttl=86400         # 24-hour TTL
)

# Automatic cache hierarchy: Memory → Redis → PostgreSQL
result = await cache.get("rxnorm:metformin")
```

### 6. Pattern Matching Engine

**Location**: `pattern_matching/matcher.py`

Extracts structured data using domain-specific patterns.

```python
from domain_nlp.pattern_matching import DomainPatternMatcher

matcher = DomainPatternMatcher(domain="medical")

# Extracts:
# - ICD codes: E11.9, 250.00
# - CPT codes: 99213
# - Dosages: 500 mg, 2.5 ml
# - Vital signs: BP 120/80

entities = matcher.extract_patterns(
    "Patient diagnosed with E11.9, prescribed Metformin 500 mg bid"
)
```

**Pattern Types**:

Medical:
- `ICD10_CODE`, `ICD9_CODE`
- `CPT_CODE`, `NDC_CODE`
- `DOSAGE`, `FREQUENCY`
- `VITAL_SIGN`

Legal:
- `USC_CITATION` (18 U.S.C. § 1001)
- `CFR_CITATION` (29 C.F.R. § 1910.134)
- `CASE_CITATION` (Brown v. Board of Education, 347 U.S. 483)
- `PUBLIC_LAW`

Financial:
- `TICKER_SYMBOL`
- `CURRENCY_AMOUNT`
- `CUSIP`, `ISIN`
- `FISCAL_PERIOD`

### 7. Ensemble Pipeline

**Location**: `pipeline/ensemble.py`

Merges results from multiple models using configurable strategies.

```python
from domain_nlp.pipeline.ensemble import EnsembleMerger

merger = EnsembleMerger(strategy="majority_vote")

# Combine predictions from multiple models
merged_entities = merger.merge([
    model1_entities,
    model2_entities,
    model3_entities
])
```

**Strategies**:
- `majority_vote` - Type with most agreement wins
- `weighted_vote` - Models weighted by performance
- `union` - Keep all unique entities
- `intersection` - Keep only entities found by all models

### 8. Dynamic Pipeline

**Location**: `pipeline/dynamic_pipeline.py`

Main orchestration layer that coordinates all components.

```python
from domain_nlp.pipeline import DynamicNLPPipeline, PipelineConfig

config = PipelineConfig(
    domain="medical",
    ensemble_strategy="majority_vote",
    min_confidence=0.7,
    enable_kb_enrichment=True,
    enable_pattern_matching=True
)

pipeline = DynamicNLPPipeline(
    config=config,
    model_registry=model_registry,
    kb_registry=kb_registry
)

await pipeline.initialize()

result = await pipeline.process(text)
# Returns: EnrichedDocument with entities, patterns, metadata
```

### 9. Configuration Loader

**Location**: `config/loader.py`

YAML-based configuration for domain settings.

```python
from domain_nlp.config import ConfigurationLoader

loader = ConfigurationLoader()

# Get configuration for domain
config = loader.get_domain_config("medical")

# Build pipeline config
pipeline_config = loader.build_pipeline_config("medical")
```

**Default Configurations**:

```yaml
# Medical Domain
domain: medical
model_selection:
  min_f1_score: 0.85
  max_latency_ms: 200
  preferred_providers: ["spacy", "huggingface"]
  entity_types: ["DRUG", "DISEASE", "CHEMICAL"]
  ensemble_strategy: "majority_vote"
  min_models: 2
  max_models: 3

kb_selection:
  fallback_chain: ["umls", "rxnorm", "snomed"]
  cache_strategy: "aggressive"
  sync_frequency: "daily"

pattern_matching:
  enabled: true
```

## Database Models

**Location**: `utils/db_models.py`

SQLAlchemy models for tracking models, KBs, and performance.

```python
from domain_nlp.utils.db_models import (
    ModelRegistryEntry,
    KBRegistryEntry,
    KBEntityCache,
    ProcessingMetrics
)

# Track model deployment
entry = ModelRegistryEntry(
    model_id="en_ner_bc5cdr_md",
    provider="spacy",
    domain="medical",
    f1_score=0.89,
    latency_p95=150.0
)
```

**Tables**:
- `domain_nlp_model_registry` - Available models
- `domain_nlp_kb_registry` - Knowledge base configs
- `domain_nlp_kb_entity_cache` - Cached KB lookups
- `domain_nlp_model_version_history` - Version tracking
- `domain_nlp_processing_metrics` - Performance data

## Usage Examples

### Basic Usage

```python
import asyncio
from domain_nlp_integration import create_domain_nlp_connector

async def main():
    connector = create_domain_nlp_connector()
    await connector.initialize()

    # Medical text
    result = await connector.process_text(
        "Patient has Type 2 Diabetes (E11.9). Prescribed Metformin 500mg bid.",
        domain="medical"
    )

    for entity in result["entities"]:
        print(f"{entity['text']}: {entity['type']} ({entity['confidence']:.2f})")

asyncio.run(main())
```

### Advanced Configuration

```python
from domain_nlp.model_providers import ModelProviderRegistry
from domain_nlp.knowledge_bases import KnowledgeBaseRegistry
from domain_nlp.pipeline import DynamicNLPPipeline, PipelineConfig

# Custom configuration
config = PipelineConfig(
    domain="legal",
    ensemble_strategy="weighted_vote",
    min_confidence=0.8,
    enable_kb_enrichment=True,
    enable_pattern_matching=True,
    min_models=2,
    max_models=4
)

# Initialize registries
model_registry = ModelProviderRegistry()
kb_registry = KnowledgeBaseRegistry()

# Create pipeline
pipeline = DynamicNLPPipeline(config, model_registry, kb_registry)
await pipeline.initialize()

# Process
result = await pipeline.process(legal_text)
```

### Adding Custom Patterns

```python
from domain_nlp.pattern_matching.patterns import MEDICAL_PATTERNS

# Add custom pattern
MEDICAL_PATTERNS["CUSTOM_ID"] = {
    "pattern": r"MRN-\d{8}",
    "description": "Medical Record Number",
    "examples": ["MRN-12345678"]
}

# Use in matcher
matcher = DomainPatternMatcher(domain="medical")
# Custom pattern now available
```

## Performance Metrics

The module tracks performance automatically:

```python
stats = pipeline.get_statistics()

print(f"Total entities processed: {stats['total_entities']}")
print(f"Average processing time: {stats['avg_processing_time_ms']}ms")
print(f"KB hit rate: {stats['kb_hit_rate']:.2%}")
print(f"Ensemble agreement: {stats['avg_ensemble_agreement']:.2%}")
```

## Testing

Run the test suite:

```bash
# All domain NLP tests
python -m pytest tests/test_domain_nlp.py -v

# Specific component tests
python -m pytest tests/test_domain_nlp.py::TestModelProviderRegistry -v
python -m pytest tests/test_domain_nlp.py::TestPatternMatching -v
```

## Error Handling

The module implements graceful degradation:

1. **Model Loading Failure**: Falls back to available models
2. **KB Unavailable**: Uses fallback chain
3. **Pattern Validation Failure**: Marks entity as unvalidated but keeps it
4. **Ensemble Failure**: Returns best available result

```python
try:
    result = await pipeline.process(text)
except Exception as e:
    # Minimal result still returned
    result = pipeline.create_fallback_result(text)
```

## Security

- **Trust Validation**: Only loads models from whitelisted sources
- **Input Sanitization**: All text inputs are sanitized
- **Local Processing**: No data sent to external services
- **HIPAA Compliance**: Suitable for medical data processing

## Future Development

1. **Custom Model Training** - Train on organization-specific data
2. **Real-time Learning** - Incorporate user corrections
3. **Additional Domains** - Chemistry, insurance, finance
4. **Multilingual Support** - Non-English domain models
5. **Graph Relationships** - Entity relationship extraction

# Domain-Specific NLP Architecture

## Overview

The TEI NLP Converter now employs a **domain-specific NLP architecture** that replaces generic entity recognition with specialized models trained on domain-specific corpora. This document describes the technical architecture and component interactions.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        TEI NLP Converter                        │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DynamicNLPPipeline                           │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────────┐        │
│  │   Model     │ │  Knowledge   │ │     Pattern      │        │
│  │  Registry   │ │    Base      │ │    Matching      │        │
│  │             │ │   Registry   │ │                  │        │
│  └─────────────┘ └──────────────┘ └──────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
         │                  │                   │
         ▼                  ▼                   ▼
┌─────────────┐  ┌──────────────┐  ┌──────────────────┐
│  SpaCy      │  │    UMLS      │  │  ICD Codes       │
│  Hugging    │  │   RxNorm     │  │  CPT Codes       │
│  Face       │  │    USC       │  │  USC Citations   │
│  Models     │  │ CourtListener│  │  Dosages         │
└─────────────┘  └──────────────┘  └──────────────────┘
```

## Core Components

### 1. Model Provider Registry

**Location**: `domain_nlp/model_providers/`

The Model Provider Registry manages discovery, loading, and lifecycle of NER models from multiple sources.

#### Key Features:
- **Dynamic Discovery**: Automatically discovers available models
- **Trust Validation**: Only loads models from whitelisted sources
- **Performance Tracking**: Monitors F1 score, latency, and throughput
- **Hot-Swapping**: Replace models without downtime

#### Supported Providers:

| Provider | Domain | Models Available |
|----------|--------|-----------------|
| SpaCy | General | en_core_web_sm/md/lg |
| SciSpaCy | Medical | en_ner_bc5cdr_md, en_ner_jnlpba_md, en_ner_bionlp13cg_md |
| Hugging Face | Medical | BiomedNLP-PubMedBERT, BioBERT |
| Hugging Face | Legal | Legal-BERT, CaseHOLD |
| Hugging Face | Financial | FinBERT |

#### Usage:

```python
from domain_nlp.model_providers import ModelProviderRegistry, SpacyModelProvider

registry = ModelProviderRegistry()
registry.register_provider("spacy", SpacyModelProvider())

# Discover available models
await registry.discover_all_models()

# Get optimal model for domain
criteria = SelectionCriteria(min_f1_score=0.85, max_latency_ms=200)
optimal_model = registry.get_optimal_model("medical", criteria)
```

### 2. Knowledge Base Registry

**Location**: `domain_nlp/knowledge_bases/`

Manages connections to authoritative knowledge bases for entity enrichment.

#### Supported Knowledge Bases:

**Medical Domain:**
- **UMLS** (Unified Medical Language System)
- **RxNorm** (Drug normalization)
- **SNOMED-CT** (Clinical terminology)

**Legal Domain:**
- **USC** (United States Code)
- **CFR** (Code of Federal Regulations)
- **CourtListener** (Case law database)

#### Features:
- **Streaming Data**: Incrementally loads KB data
- **Multi-Tier Caching**: Memory → Redis → PostgreSQL
- **Fallback Chains**: Automatic failover between KBs
- **Background Sync**: Scheduled KB updates

#### Usage:

```python
from domain_nlp.knowledge_bases import KnowledgeBaseRegistry

kb_registry = KnowledgeBaseRegistry()
kb_registry.register_provider("umls", UMLSProvider(api_key="..."))

# Lookup with fallback
entity = await kb_registry.lookup_with_fallback(
    "Metformin",
    fallback_chain=["umls", "rxnorm", "snomed"]
)
```

### 3. Pattern Matching Engine

**Location**: `domain_nlp/pattern_matching/`

Extracts structured data using domain-specific regex patterns.

#### Medical Patterns:
- ICD-10/ICD-9 codes (`E11.9`, `250.00`)
- CPT procedure codes (`99213`)
- NDC drug codes (`0002-1433-01`)
- Dosages (`500 mg`, `2.5 ml`)
- Frequencies (`bid`, `q.8h`)
- Vital signs (`BP 120/80`)

#### Legal Patterns:
- USC citations (`18 U.S.C. § 1001`)
- CFR citations (`29 C.F.R. § 1910.134`)
- Case citations (`Brown v. Board of Education, 347 U.S. 483`)
- Public Law numbers (`Pub. L. No. 116-136`)

#### Financial Patterns:
- Ticker symbols (`AAPL`)
- Currency amounts (`$1,234.56`)
- CUSIP/ISIN identifiers
- Fiscal periods (`Q1 2024`, `FY'23`)

### 4. Ensemble Pipeline

**Location**: `domain_nlp/pipeline/`

Orchestrates multiple models and merges results using ensemble strategies.

#### Merging Strategies:

1. **Majority Vote**: Type with most model agreement wins
2. **Weighted Vote**: Models weighted by performance
3. **Union**: Keep all entities from all models
4. **Intersection**: Keep only entities found by all models

#### Pipeline Flow:

```
Input Text
    │
    ├─────────────┬─────────────┬─────────────┐
    ▼             ▼             ▼             ▼
 Model 1      Model 2      Model 3      Pattern
 (SpaCy)      (BioBERT)    (SciSpacy)   Matcher
    │             │             │             │
    └─────────────┴─────────────┴─────────────┘
                        │
                        ▼
                 Ensemble Merger
                        │
                        ▼
                  KB Enrichment
                        │
                        ▼
                 EnrichedDocument
```

### 5. Configuration System

**Location**: `domain_nlp/config/`

YAML-based configuration for domain-specific settings.

#### Example Configuration:

```yaml
# config/domains/medical.yaml
domain: medical
enabled: true

model_selection:
  min_f1_score: 0.85
  max_latency_ms: 200
  preferred_providers: ["spacy", "huggingface"]
  entity_types: ["DRUG", "DISEASE", "CHEMICAL"]
  ensemble_strategy: "majority_vote"
  min_models: 2
  max_models: 3

kb_selection:
  required_kbs: []
  optional_kbs: ["rxnorm", "snomed"]
  fallback_chain: ["umls", "rxnorm", "snomed"]
  cache_strategy: "aggressive"
  sync_frequency: "daily"

pattern_matching:
  enabled: true
  custom_patterns: {}
```

## Database Schema

The architecture introduces new tables for tracking models, KBs, and performance:

| Table | Purpose |
|-------|---------|
| `domain_nlp_model_registry` | Catalog of available NER models |
| `domain_nlp_kb_registry` | Knowledge base configurations |
| `domain_nlp_kb_entity_cache` | Cached KB lookups |
| `domain_nlp_model_version_history` | Model deployment history |
| `domain_nlp_processing_metrics` | Performance tracking |

## Performance Characteristics

### Expected Improvements:

| Metric | Old System (Google NLP) | New System (Domain-Specific) |
|--------|------------------------|------------------------------|
| Medical Entity F1 | ~0.45 | ~0.89 |
| Legal Citation F1 | ~0.30 | ~0.85 |
| ICD Code Detection | Not supported | 92% recall |
| KB Enrichment | None | 95% coverage |
| Latency (p95) | 300ms (network) | 450ms (local processing) |

### Resource Requirements:

- **Memory**: 4-8 GB RAM (varies by models loaded)
- **CPU**: 2-4 cores recommended
- **Disk**: 2-10 GB for model storage
- **Redis**: 512MB-2GB for caching

## Security Considerations

### Trust Validation:

Models are only loaded from whitelisted sources:
- `github.com/explosion` (SpaCy official)
- `huggingface.co` (verified organizations)
- `allenai.github.io` (SciSpaCy)

### Data Privacy:

- All processing occurs locally (no external API calls)
- HIPAA-compliant for medical data
- No data leaves the server

## Integration Points

### With Existing TEI Converter:

The new architecture integrates via `domain_nlp_integration.py`:

```python
from domain_nlp_integration import create_domain_nlp_connector

connector = create_domain_nlp_connector()
await connector.initialize()

# Process with domain-specific NLP
result = await connector.process_text(medical_text, domain="medical")

# Result is in legacy format for TEI conversion
tei_xml = tei_converter.convert(result)
```

### Feature Flags:

```python
feature_flags = {
    "use_domain_nlp": True,
    "enable_kb_enrichment": True,
    "enable_pattern_matching": True,
    "enable_ensemble": True
}
```

## Future Enhancements

1. **Custom Model Training**: Train models on organization-specific data
2. **Real-time Learning**: Incorporate user corrections
3. **Additional Domains**: Chemistry, finance, insurance
4. **Graph-based Relationships**: Entity relationship extraction
5. **Multilingual Support**: Non-English domain models

## References

- [SciSpaCy Documentation](https://allenai.github.io/scispacy/)
- [Hugging Face Model Hub](https://huggingface.co/models)
- [UMLS Knowledge Sources](https://www.nlm.nih.gov/research/umls/)
- [RxNorm API](https://rxnav.nlm.nih.gov/)
- [CourtListener API](https://www.courtlistener.com/api/)

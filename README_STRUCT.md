Here's a clean, presentable file structure for the TEI NLP Converter project with the multi-provider architecture:

```
tei-nlp-converter/
│
├── .env                           # Environment variables (create from .env.example)
├── .env.example                   # Environment template with Google Cloud config
├── .gitignore                     # Git ignore file
├── alembic.ini                    # Database migration config
├── docker-compose.yml             # Docker orchestration with Google credentials
├── Dockerfile                     # Container definition
├── Makefile                       # Build automation
├── nginx.conf                     # Nginx configuration
│
├── README.md                      # Main deployment guide
├── README_HOW_IT_WORKS.md         # Architecture and workflow documentation
├── README_STRUCT.md               # This file - project structure
├── GOOGLE_CLOUD_SETUP.md          # Google Cloud NLP setup guide
├── CUSTOM_SCHEMAS_GUIDE.md        # Complete custom schema guide
├── requirements.txt               # Python dependencies
│
├── app.py                         # Main FastAPI application
├── config.py                      # Configuration management
├── storage.py                     # Database models and operations
├── logger.py                      # Logging configuration
├── security.py                    # Security utilities
├── middleware.py                  # Request middleware
├── metrics.py                     # Prometheus metrics
├── circuit_breaker.py             # Circuit breaker pattern
├── cache_manager.py               # Caching layer
├── nlp_connector.py               # NLP processing orchestrator
├── tei_converter.py               # TEI XML converter with provider-aware strategies
├── ontology_manager.py            # Domain schema manager with provider mappings
├── background_tasks.py            # Async task management
├── secrets_manager.py             # Secrets management
├── validate_schema.py             # Schema validation tool (executable)
│
├── nlp_providers/                 # Multi-provider NLP architecture
│   ├── __init__.py               # Package init
│   ├── base.py                   # Abstract base provider with capabilities
│   ├── registry.py               # Provider registry and health checking
│   ├── spacy_local.py            # SpaCy local implementation
│   ├── google_cloud.py           # Google Cloud NLP with enhanced features
│   └── remote_server.py          # Remote NLP server client
│
├── migrations/                    # Database migrations
│   ├── versions/
│   │   └── 001_initial_schema.py # Initial database schema
│   └── alembic/
│       └── env.py                # Alembic environment
│
├── schemas/                       # Custom TEI schemas directory
│   ├── README.md                 # Schema directory documentation
│   ├── medical.json              # Medical domain schema (example)
│   ├── journalism.json           # Journalism schema (example)
│   └── social-media.json         # Social media schema (example)
│
├── templates/                     # HTML templates
│   └── index.html                # Main web interface with provider status
│
├── static/                        # Static assets
│   ├── style.css                 # Application styles with Google feature styling
│   ├── script.js                 # Client-side JavaScript with entity cards
│   └── favicon.ico               # Site icon
│
├── tests/                         # Test suite
│   ├── __init__.py
│   ├── test_app.py               # Application tests
│   ├── test_nlp.py               # NLP processing tests
│   ├── test_tei.py               # TEI conversion tests
│   ├── test_integration.py       # Integration tests
│   └── test_google_nlp_integration.py  # Google Cloud NLP tests
│
├── kubernetes/                    # Kubernetes deployments
│   └── production-deployment.yaml
│
├── logs/                          # Log files (auto-created)
│   ├── tei_nlp.log               # Application log
│   ├── errors.log                # Error log
│   └── audit.log                 # Audit trail
│
├── data/                          # Data directory (auto-created)
│   └── tei_nlp.db                # SQLite database (dev only)
│
└── ssl/                           # SSL certificates (production)
    ├── cert.pem
    └── key.pem
```

## Project Architecture Overview

### Multi-Provider NLP Architecture

The application supports three NLP providers with intelligent fallback:

**1. Google Cloud NLP** (Cloud-based)
- Entity salience scoring (importance ranking)
- Entity sentiment analysis
- Knowledge Graph integration (Wikipedia, MIDs)
- Rich morphological features
- Text classification
- **Setup Guide**: `GOOGLE_CLOUD_SETUP.md`

**2. SpaCy** (Local)
- Fast local processing
- Rich morphology and dependency parsing
- Privacy-focused (no external API)
- Noun chunk extraction
- **Default provider**, no setup required

**3. Remote NLP Server** (Custom)
- Extensible custom NLP deployment
- Generic processing capabilities
- Configurable endpoint

### Provider-Specific Features

**Dynamic Conversion Strategies:**
- `_google_conversion_strategy()` - Leverages salience, sentiment, KG
- `_spacy_conversion_strategy()` - Emphasizes morphology, dependencies
- `_remote_conversion_strategy()` - Generic processing

**Provider-Aware Entity Mappings:**
- Google-specific: `PHONE_NUMBER`, `ADDRESS`, `CONSUMER_GOOD`, `PRICE`
- SpaCy-specific: `GPE`, `NORP`, `FAC`, `LAW`, `LANGUAGE`
- Domain mappings override provider defaults

**Granularity-Aware Processing:**
- Auto-enables sentiment for Google Cloud NLP
- Auto-disables unsupported features per provider
- Optimizes processing based on provider capabilities

### Custom Schema System

**Built-in Schemas (10):** `default`, `literary`, `historical`, `legal`, `scientific`, `linguistic`, `manuscript`, `dramatic`, `poetry`, `epistolary`

**Custom Schemas:** Add JSON files to `schemas/` directory
- Medical (`medical.json`) - 40+ medical entity types
- Journalism (`journalism.json`) - News-specific entities
- Social Media (`social-media.json`) - Hashtags, mentions, emoji

**Tools:**
- `validate_schema.py` - Validate schema JSON before deployment
- `CUSTOM_SCHEMAS_GUIDE.md` - Complete guide (400+ lines)

### Documentation Structure

| File | Purpose |
|------|---------|
| `README.md` | Proxmox deployment guide |
| `README_HOW_IT_WORKS.md` | Architecture and data flow |
| `README_STRUCT.md` | This file - project structure |
| `GOOGLE_CLOUD_SETUP.md` | Google Cloud NLP setup (400+ lines) |
| `CUSTOM_SCHEMAS_GUIDE.md` | Custom schema guide (400+ lines) |
| `schemas/README.md` | Schema directory quick reference |

# TEI NLP Converter - System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    INTERNET                                         │
│                                        │                                            │
│                              [Users/Browsers/API Clients]                           │
└────────────────────────────────┬───────────────────────────────────────────────────┘
                                 │
                                 │ HTTPS (443)
                                 ↓
                    ┌────────────────────────────┐
                    │   Domain: tei-nlp.com      │
                    │   Public IP: X.X.X.X       │
                    └────────────┬───────────────┘
                                 │
                    ┌────────────┴───────────────┐
                    │    Router/Firewall         │
                    │    Port Forward: 443→443   │
                    │    Port Forward: 80→80     │
                    └────────────┬───────────────┘
                                 │
╔════════════════════════════════╪═══════════════════════════════════════════════════╗
║                                │                                                   ║
║                          PROXMOX HOST (Physical Server)                            ║
║                                │                                                   ║
║  ┌─────────────────────────────┴────────────────────────────────────────────┐     ║
║  │                         Container CT 110 (Ubuntu 22.04)                   │     ║
║  │  Hostname: tei-nlp                                                        │     ║
║  │  Resources: 4GB RAM, 2 CPU Cores, 16GB Disk                              │     ║
║  │  Network: Bridged (vmbr0)                                                 │     ║
║  │                                                                           │     ║
║  │  ┌─────────────────────────────────────────────────────────────────────┐ │     ║
║  │  │                         NGINX (Reverse Proxy)                        │ │     ║
║  │  │  - SSL/TLS Termination (Let's Encrypt)                              │ │     ║
║  │  │  - Static Files: /static/*                                           │ │     ║
║  │  │  - Proxy Pass: → localhost:8080                                      │ │     ║
║  │  └──────────────────────────┬──────────────────────────────────────────┘ │     ║
║  │                              │ HTTP                                       │     ║
║  │                              ↓                                            │     ║
║  │  ┌─────────────────────────────────────────────────────────────────────┐ │     ║
║  │  │                    GUNICORN (WSGI Server)                            │ │     ║
║  │  │  Workers: 4 × Uvicorn                                                │ │     ║
║  │  │  Bind: 127.0.0.1:8080                                                │ │     ║
║  │  │  Service: systemd (tei-nlp.service)                                  │ │     ║
║  │  └──────────────────────────┬──────────────────────────────────────────┘ │     ║
║  │                              │                                            │     ║
║  │                              ↓                                            │     ║
║  │  ┌─────────────────────────────────────────────────────────────────────┐ │     ║
║  │  │                    FASTAPI APPLICATION                               │ │     ║
║  │  │                   (/opt/tei-nlp-converter)                           │ │     ║
║  │  │                                                                      │ │     ║
║  │  │   ┌──────────────┐  ┌─────────────────────┐  ┌──────────────┐       │ │     ║
║  │  │   │   app.py     │  │  NLP Providers      │  │ TEI Convert  │       │ │     ║
║  │  │   │   (Main)     │→ │  - Google Cloud NLP │→ │  - Schemas   │       │ │     ║
║  │  │   │              │  │  - SpaCy (Local)    │  │  - Provider  │       │ │     ║
║  │  │   │              │  │  - Remote Server    │  │    Strategies│       │ │     ║
║  │  │   └──────────────┘  └─────────────────────┘  └──────────────┘       │ │     ║
║  │  │         │                   │                 │                     │ │     ║
║  │  │         ├───────────────────┼─────────────────┤                     │ │     ║
║  │  │         │                   │                 │                     │ │     ║
║  │  │         ↓                   ↓                 ↓                     │ │     ║
║  │  │   ┌──────────────────────────────────────────────────┐             │ │     ║
║  │  │   │            Background Task Queue                  │             │ │     ║
║  │  │   │         (Large text processing async)             │             │ │     ║
║  │  │   └──────────────────────────────────────────────────┘             │ │     ║
║  │  └─────────────┬──────────────┬──────────────┬─────────────────────────┘ │     ║
║  │                │              │              │                           │     ║
║  │                ↓              ↓              ↓                           │     ║
║  │  ┌──────────────────┐ ┌──────────────┐ ┌──────────────────────┐        │     ║
║  │  │   PostgreSQL 14  │ │   Redis 7    │ │   File Storage      │        │     ║
║  │  │                  │ │              │ │                     │        │     ║
║  │  │  Database:       │ │  Cache:      │ │  /opt/tei-nlp/:    │        │     ║
║  │  │  - tei_nlp       │ │  - Results   │ │  - schemas/        │        │     ║
║  │  │                  │ │  - Sessions  │ │  - logs/           │        │     ║
║  │  │  Tables:         │ │              │ │  - static/         │        │     ║
║  │  │  - processed_    │ │  Port: 6379  │ │  - data/           │        │     ║
║  │  │    texts         │ │              │ │                     │        │     ║
║  │  │  - background_   │ │  Max: 512MB  │ │                     │        │     ║
║  │  │    tasks         │ │              │ │                     │        │     ║
║  │  │  - audit_logs    │ │              │ │                     │        │     ║
║  │  │                  │ │              │ │                     │        │     ║
║  │  │  Port: 5432      │ │              │ │                     │        │     ║
║  │  └──────────────────┘ └──────────────┘ └──────────────────────┘        │     ║
║  │                                                                           │     ║
║  │  ┌─────────────────────────────────────────────────────────────────────┐ │     ║
║  │  │                        System Services                               │ │     ║
║  │  │  - UFW Firewall (Ports: 22, 80, 443)                               │ │     ║
║  │  │  - Systemd Services: tei-nlp.service, postgresql, redis            │ │     ║
║  │  │  - Cron Jobs: Health checks, log rotation, data cleanup            │ │     ║
║  │  └─────────────────────────────────────────────────────────────────────┘ │     ║
║  └───────────────────────────────────────────────────────────────────────────┘     ║
║                                                                                     ║
╚═════════════════════════════════════════════════════════════════════════════════════╝

LEGEND:
═══ Physical Host Boundary        → Data Flow Direction
─── Container/Service Boundary    ↓ Request Flow
│   Connection/Communication
```

## Data Flow Sequence

```
1. User Request → Router → Proxmox → CT:443 → Nginx
2. Nginx → Gunicorn:8080 → FastAPI Application
3. FastAPI → NLP Processing → TEI Conversion
4. Data Storage: PostgreSQL (persistent) + Redis (cache)
5. Response: TEI XML → Client
```

## Service Dependencies

```
Application Start Order:
1. postgresql.service
2. redis.service  
3. tei-nlp.service (depends on 1 & 2)
4. nginx.service
```

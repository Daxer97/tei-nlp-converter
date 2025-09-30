Here's a clean, presentable file structure for the TEI NLP Converter project with the multi-provider architecture:

```
tei-nlp-converter/
│
├── .env                           # Environment variables (create from .env.example)
├── .env.example                   # Environment template
├── .gitignore                     # Git ignore file
├── alembic.ini                    # Database migration config
├── docker-compose.yml             # Docker orchestration
├── Dockerfile                     # Container definition
├── Makefile                       # Build automation
├── nginx.conf                     # Nginx configuration
├── README.md                      # Project documentation
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
├── tei_converter.py               # TEI XML converter
├── ontology_manager.py            # Domain schema manager (fix typo!)
├── background_tasks.py            # Async task management
├── secrets_manager.py             # Secrets management
│
├── nlp_providers/                 # NLP provider implementations
│   ├── __init__.py               # Package init
│   ├── base.py                   # Abstract base provider
│   ├── registry.py               # Provider registry
│   ├── spacy_local.py            # SpaCy implementation
│   ├── google_cloud.py           # Google Cloud NLP
│   └── remote_server.py          # Remote NLP server client
│
├── migrations/                    # Database migrations
│   ├── versions/
│   │   └── 001_initial_schema.py # Initial database schema
│   └── alembic/
│       └── env.py                # Alembic environment
│
├── schemas/                       # Custom TEI schemas (JSON)
│   ├── literary.json             # Literary domain schema
│   ├── historical.json          # Historical domain schema
│   ├── legal.json               # Legal domain schema
│   ├── scientific.json          # Scientific domain schema
│   └── [custom].json             # Add your custom schemas here
│
├── templates/                     # HTML templates
│   ├── index.html                # Main web interface
│   └── schema_builder.html       # Schema builder (optional)
│
├── static/                        # Static assets
│   ├── style.css                 # Application styles
│   ├── script.js                 # Client-side JavaScript
│   └── favicon.ico               # Site icon
│
├── tests/                         # Test suite
│   ├── __init__.py
│   ├── test_app.py               # Application tests
│   ├── test_nlp.py               # NLP processing tests
│   ├── test_tei.py               # TEI conversion tests
│   └── test_integration.py       # Integration tests
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
║  │  │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │ │     ║
║  │  │   │   app.py     │  │ NLP Pipeline │  │ TEI Convert  │            │ │     ║
║  │  │   │   (Main)     │→ │  - SpaCy     │→ │  - Schemas   │            │ │     ║
║  │  │   │              │  │  - Google    │  │  - XML Gen   │            │ │     ║
║  │  │   └──────────────┘  └──────────────┘  └──────────────┘            │ │     ║
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

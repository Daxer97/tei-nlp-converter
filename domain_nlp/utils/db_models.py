"""
SQLAlchemy models for model and knowledge base registries.

These tables support:
- Model registry with performance tracking
- Knowledge base registry with sync status
- Entity cache for fast lookups
- Model version history for rollback
"""

from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy import (
    Column,
    String,
    Float,
    Boolean,
    Integer,
    Text,
    DateTime,
    JSON,
    Index,
    UniqueConstraint
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ModelRegistryEntry(Base):
    """Registry entry for an NER model"""

    __tablename__ = "domain_nlp_model_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String(255), nullable=False)
    provider = Column(String(100), nullable=False)
    domain = Column(String(50), nullable=False)
    version = Column(String(50), nullable=False)

    # Entity types this model can extract (JSON array)
    entity_types = Column(JSON, nullable=False, default=list)

    # Performance metrics
    f1_score = Column(Float, default=0.0)
    precision_score = Column(Float, default=0.0)
    recall_score = Column(Float, default=0.0)
    latency_ms = Column(Float, default=0.0)
    throughput = Column(Float, default=0.0)
    memory_mb = Column(Float, default=0.0)

    # Trust and validation
    source_url = Column(Text, default="")
    trusted = Column(Boolean, default=False)
    requires_kb = Column(JSON, default=list)  # List of required KB IDs

    # Metadata
    description = Column(Text, default="")
    size_mb = Column(Float, default=0.0)
    license = Column(String(100), default="")
    tags = Column(JSON, default=list)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_validated = Column(DateTime, nullable=True)
    last_used = Column(DateTime, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("model_id", "version", name="uq_model_version"),
        Index("idx_model_domain", "domain", "trusted"),
        Index("idx_model_performance", "f1_score"),
        Index("idx_model_provider", "provider"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "model_id": self.model_id,
            "provider": self.provider,
            "domain": self.domain,
            "version": self.version,
            "entity_types": self.entity_types,
            "performance": {
                "f1_score": self.f1_score,
                "precision": self.precision_score,
                "recall": self.recall_score,
                "latency_ms": self.latency_ms,
                "throughput": self.throughput,
                "memory_mb": self.memory_mb
            },
            "source_url": self.source_url,
            "trusted": self.trusted,
            "requires_kb": self.requires_kb,
            "description": self.description,
            "size_mb": self.size_mb,
            "license": self.license,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_validated": self.last_validated.isoformat() if self.last_validated else None,
            "is_active": self.is_active
        }


class KBRegistryEntry(Base):
    """Registry entry for a knowledge base"""

    __tablename__ = "domain_nlp_kb_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_id = Column(String(100), unique=True, nullable=False)
    provider = Column(String(100), nullable=False)
    domain = Column(String(50), nullable=False)
    version = Column(String(50), nullable=False)

    # Connection info
    stream_url = Column(Text, default="")
    api_key_required = Column(Boolean, default=False)

    # Entity types supported (JSON array)
    entity_types = Column(JSON, nullable=False, default=list)

    # Sync configuration
    update_frequency = Column(String(50), default="weekly")
    cache_strategy = Column(String(50), default="moderate")
    fallback = Column(JSON, default=list)  # List of fallback KB IDs

    # Trust
    trusted = Column(Boolean, default=False)

    # Metadata
    description = Column(Text, default="")
    entity_count = Column(Integer, default=0)

    # Sync status
    last_sync = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), default="never")
    entities_synced = Column(Integer, default=0)
    sync_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Status
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index("idx_kb_domain", "domain", "trusted"),
        Index("idx_kb_sync", "last_sync"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kb_id": self.kb_id,
            "provider": self.provider,
            "domain": self.domain,
            "version": self.version,
            "stream_url": self.stream_url,
            "api_key_required": self.api_key_required,
            "entity_types": self.entity_types,
            "update_frequency": self.update_frequency,
            "cache_strategy": self.cache_strategy,
            "fallback": self.fallback,
            "trusted": self.trusted,
            "description": self.description,
            "entity_count": self.entity_count,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "last_sync_status": self.last_sync_status,
            "entities_synced": self.entities_synced,
            "is_active": self.is_active
        }


class KBEntityCache(Base):
    """Cache for knowledge base entity lookups"""

    __tablename__ = "domain_nlp_kb_entity_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_id = Column(String(100), nullable=False)
    entity_text = Column(String(500), nullable=False)
    entity_type = Column(String(100), nullable=False)
    kb_entity_id = Column(String(255), nullable=False)

    # Full entity data as JSON
    metadata = Column(JSON, nullable=False, default=dict)

    # Cache management
    cached_at = Column(DateTime, default=datetime.utcnow)
    hit_count = Column(Integer, default=0)
    last_hit = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("kb_id", "entity_text", "entity_type", name="uq_kb_entity"),
        Index("idx_kb_lookup", "kb_id", "entity_text", "entity_type"),
        Index("idx_kb_cache_hits", "hit_count"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kb_id": self.kb_id,
            "entity_text": self.entity_text,
            "entity_type": self.entity_type,
            "kb_entity_id": self.kb_entity_id,
            "metadata": self.metadata,
            "cached_at": self.cached_at.isoformat() if self.cached_at else None,
            "hit_count": self.hit_count,
            "last_hit": self.last_hit.isoformat() if self.last_hit else None
        }


class ModelVersionHistory(Base):
    """Tracks model version deployments for rollback"""

    __tablename__ = "domain_nlp_model_version_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain = Column(String(50), nullable=False)
    model_id = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False)

    # Deployment info
    deployed_at = Column(DateTime, default=datetime.utcnow)
    deployed_by = Column(String(100), default="system")

    # Performance at deployment
    initial_f1_score = Column(Float, nullable=True)
    initial_latency_ms = Column(Float, nullable=True)

    # Status
    status = Column(String(50), default="active")  # active, rolled_back, superseded
    rolled_back_at = Column(DateTime, nullable=True)
    rolled_back_by = Column(String(100), nullable=True)
    rollback_reason = Column(Text, nullable=True)

    # Metadata
    metadata = Column(JSON, default=dict)

    __table_args__ = (
        Index("idx_version_history_domain", "domain", "deployed_at"),
        Index("idx_version_history_status", "status"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "domain": self.domain,
            "model_id": self.model_id,
            "version": self.version,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "deployed_by": self.deployed_by,
            "initial_f1_score": self.initial_f1_score,
            "initial_latency_ms": self.initial_latency_ms,
            "status": self.status,
            "rolled_back_at": self.rolled_back_at.isoformat() if self.rolled_back_at else None,
            "metadata": self.metadata
        }


class ProcessingMetrics(Base):
    """Tracks NLP processing metrics over time"""

    __tablename__ = "domain_nlp_processing_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    domain = Column(String(50), nullable=False)

    # Processing stats
    text_length = Column(Integer, nullable=False)
    entity_count = Column(Integer, nullable=False)
    structured_entity_count = Column(Integer, default=0)

    # Performance
    processing_time_ms = Column(Float, nullable=False)
    kb_hit_rate = Column(Float, default=0.0)
    ensemble_agreement = Column(Float, default=1.0)

    # Models used (JSON array of model IDs)
    models_used = Column(JSON, default=list)

    # Request info
    request_id = Column(String(36), nullable=True)

    __table_args__ = (
        Index("idx_processing_metrics_domain", "domain", "timestamp"),
        Index("idx_processing_metrics_time", "timestamp"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "domain": self.domain,
            "text_length": self.text_length,
            "entity_count": self.entity_count,
            "structured_entity_count": self.structured_entity_count,
            "processing_time_ms": self.processing_time_ms,
            "kb_hit_rate": self.kb_hit_rate,
            "ensemble_agreement": self.ensemble_agreement,
            "models_used": self.models_used,
            "request_id": self.request_id
        }


# SQL for creating tables (for use without migrations)
CREATE_TABLES_SQL = """
-- Model Registry
CREATE TABLE IF NOT EXISTS domain_nlp_model_registry (
    id SERIAL PRIMARY KEY,
    model_id VARCHAR(255) NOT NULL,
    provider VARCHAR(100) NOT NULL,
    domain VARCHAR(50) NOT NULL,
    version VARCHAR(50) NOT NULL,
    entity_types JSONB NOT NULL DEFAULT '[]'::jsonb,
    f1_score FLOAT DEFAULT 0.0,
    precision_score FLOAT DEFAULT 0.0,
    recall_score FLOAT DEFAULT 0.0,
    latency_ms FLOAT DEFAULT 0.0,
    throughput FLOAT DEFAULT 0.0,
    memory_mb FLOAT DEFAULT 0.0,
    source_url TEXT DEFAULT '',
    trusted BOOLEAN DEFAULT false,
    requires_kb JSONB DEFAULT '[]'::jsonb,
    description TEXT DEFAULT '',
    size_mb FLOAT DEFAULT 0.0,
    license VARCHAR(100) DEFAULT '',
    tags JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP DEFAULT NOW(),
    last_validated TIMESTAMP,
    last_used TIMESTAMP,
    is_active BOOLEAN DEFAULT true,
    UNIQUE(model_id, version)
);

CREATE INDEX IF NOT EXISTS idx_model_domain ON domain_nlp_model_registry(domain, trusted);
CREATE INDEX IF NOT EXISTS idx_model_performance ON domain_nlp_model_registry(f1_score DESC);

-- KB Registry
CREATE TABLE IF NOT EXISTS domain_nlp_kb_registry (
    id SERIAL PRIMARY KEY,
    kb_id VARCHAR(100) UNIQUE NOT NULL,
    provider VARCHAR(100) NOT NULL,
    domain VARCHAR(50) NOT NULL,
    version VARCHAR(50) NOT NULL,
    stream_url TEXT DEFAULT '',
    api_key_required BOOLEAN DEFAULT false,
    entity_types JSONB NOT NULL DEFAULT '[]'::jsonb,
    update_frequency VARCHAR(50) DEFAULT 'weekly',
    cache_strategy VARCHAR(50) DEFAULT 'moderate',
    fallback JSONB DEFAULT '[]'::jsonb,
    trusted BOOLEAN DEFAULT false,
    description TEXT DEFAULT '',
    entity_count INTEGER DEFAULT 0,
    last_sync TIMESTAMP,
    last_sync_status VARCHAR(50) DEFAULT 'never',
    entities_synced INTEGER DEFAULT 0,
    sync_error TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_kb_domain ON domain_nlp_kb_registry(domain, trusted);

-- Entity Cache
CREATE TABLE IF NOT EXISTS domain_nlp_kb_entity_cache (
    id SERIAL PRIMARY KEY,
    kb_id VARCHAR(100) NOT NULL,
    entity_text VARCHAR(500) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    kb_entity_id VARCHAR(255) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    cached_at TIMESTAMP DEFAULT NOW(),
    hit_count INTEGER DEFAULT 0,
    last_hit TIMESTAMP,
    UNIQUE(kb_id, entity_text, entity_type)
);

CREATE INDEX IF NOT EXISTS idx_kb_lookup ON domain_nlp_kb_entity_cache(kb_id, entity_text, entity_type);

-- Version History
CREATE TABLE IF NOT EXISTS domain_nlp_model_version_history (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(50) NOT NULL,
    model_id VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL,
    deployed_at TIMESTAMP DEFAULT NOW(),
    deployed_by VARCHAR(100) DEFAULT 'system',
    initial_f1_score FLOAT,
    initial_latency_ms FLOAT,
    status VARCHAR(50) DEFAULT 'active',
    rolled_back_at TIMESTAMP,
    rolled_back_by VARCHAR(100),
    rollback_reason TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_version_history_domain ON domain_nlp_model_version_history(domain, deployed_at DESC);

-- Processing Metrics
CREATE TABLE IF NOT EXISTS domain_nlp_processing_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    domain VARCHAR(50) NOT NULL,
    text_length INTEGER NOT NULL,
    entity_count INTEGER NOT NULL,
    structured_entity_count INTEGER DEFAULT 0,
    processing_time_ms FLOAT NOT NULL,
    kb_hit_rate FLOAT DEFAULT 0.0,
    ensemble_agreement FLOAT DEFAULT 1.0,
    models_used JSONB DEFAULT '[]'::jsonb,
    request_id VARCHAR(36)
);

CREATE INDEX IF NOT EXISTS idx_processing_metrics_domain ON domain_nlp_processing_metrics(domain, timestamp DESC);
"""

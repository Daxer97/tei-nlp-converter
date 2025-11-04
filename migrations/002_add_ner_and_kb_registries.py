"""
Database migration: Add NER Model and Knowledge Base registries

This migration adds tables for:
1. Model registry (tracking available NER models)
2. KB registry (tracking available knowledge bases)
3. KB entity cache (multi-tier caching for KB lookups)
4. Model performance metrics
"""

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, Float,
    DateTime, JSON, Index, CheckConstraint, func, text
)
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class ModelRegistry(Base):
    """Registry of available NER models"""
    __tablename__ = 'model_registry'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    model_id = Column(Text, nullable=False)
    provider = Column(String(100), nullable=False)
    domain = Column(String(50), nullable=False)
    version = Column(Text, nullable=False)
    entity_types = Column(JSON, nullable=False)
    performance_metrics = Column(JSON, nullable=False)
    source_url = Column(Text, nullable=False)
    trusted = Column(Boolean, default=False)
    requires_kb = Column(JSON)
    description = Column(Text)
    license = Column(String(100))
    model_size_mb = Column(Float)
    signature = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    last_validated = Column(DateTime)

    __table_args__ = (
        Index('idx_model_domain', 'domain', 'trusted'),
        Index('idx_model_provider', 'provider', 'domain'),
        Index('idx_model_f1', text("(performance_metrics->>'f1_score')::float DESC")),
        CheckConstraint("model_id != ''", name='model_id_not_empty'),
        {'extend_existing': True}
    )


class KBRegistry(Base):
    """Registry of available knowledge bases"""
    __tablename__ = 'kb_registry'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    kb_id = Column(Text, nullable=False, unique=True)
    provider = Column(String(100), nullable=False)
    domain = Column(String(50), nullable=False)
    version = Column(Text, nullable=False)
    stream_url = Column(Text, nullable=False)
    api_key_required = Column(Boolean, default=False)
    entity_types = Column(JSON, nullable=False)
    update_frequency = Column(String(50))
    trusted = Column(Boolean, default=False)
    cache_strategy = Column(String(50))
    description = Column(Text)
    license = Column(String(100))
    capabilities = Column(JSON)
    last_sync = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index('idx_kb_domain', 'domain', 'trusted'),
        Index('idx_kb_provider', 'provider'),
        {'extend_existing': True}
    )


class KBEntityCache(Base):
    """Cache for KB entity lookups"""
    __tablename__ = 'kb_entity_cache'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    cache_key = Column(Text, nullable=False, unique=True)
    kb_id = Column(Text, nullable=False)
    entity_text = Column(Text, nullable=False)
    entity_type = Column(String(100))
    entity_data = Column(JSON, nullable=False)
    cached_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index('idx_kb_lookup', 'kb_id', 'entity_text', 'entity_type'),
        Index('idx_kb_entity_text', 'entity_text'),
        Index('idx_kb_id', 'kb_id'),
        {'extend_existing': True}
    )


class ModelPerformanceLog(Base):
    """Log of model performance in production"""
    __tablename__ = 'model_performance_log'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    model_id = Column(Text, nullable=False)
    domain = Column(String(50), nullable=False)
    latency_ms = Column(Float, nullable=False)
    entity_count = Column(Integer)
    text_length = Column(Integer)
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    timestamp = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index('idx_perf_model', 'model_id', 'timestamp'),
        Index('idx_perf_domain', 'domain', 'timestamp'),
        {'extend_existing': True}
    )


class KBLookupLog(Base):
    """Log of KB lookup operations"""
    __tablename__ = 'kb_lookup_log'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    kb_id = Column(Text, nullable=False)
    entity_text = Column(Text, nullable=False)
    entity_type = Column(String(100))
    found = Column(Boolean, default=False)
    cache_hit = Column(Boolean, default=False)
    cache_tier = Column(String(20))  # memory, redis, postgres
    lookup_time_ms = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index('idx_kb_lookup_log', 'kb_id', 'timestamp'),
        Index('idx_kb_cache_hit', 'cache_hit', 'cache_tier'),
        {'extend_existing': True}
    )


def upgrade(connection):
    """Apply migration"""
    from sqlalchemy import MetaData

    metadata = MetaData()

    # Create tables
    ModelRegistry.__table__.create(bind=connection, checkfirst=True)
    KBRegistry.__table__.create(bind=connection, checkfirst=True)
    KBEntityCache.__table__.create(bind=connection, checkfirst=True)
    ModelPerformanceLog.__table__.create(bind=connection, checkfirst=True)
    KBLookupLog.__table__.create(bind=connection, checkfirst=True)

    print("Created NER model and KB registry tables")


def downgrade(connection):
    """Rollback migration"""
    connection.execute(text("DROP TABLE IF EXISTS kb_lookup_log CASCADE"))
    connection.execute(text("DROP TABLE IF EXISTS model_performance_log CASCADE"))
    connection.execute(text("DROP TABLE IF EXISTS kb_entity_cache CASCADE"))
    connection.execute(text("DROP TABLE IF EXISTS kb_registry CASCADE"))
    connection.execute(text("DROP TABLE IF EXISTS model_registry CASCADE"))

    print("Dropped NER model and KB registry tables")


if __name__ == "__main__":
    # Can be run standalone for testing
    from sqlalchemy import create_engine
    import os

    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost/tei_nlp")
    engine = create_engine(database_url)

    with engine.connect() as conn:
        upgrade(conn)
        conn.commit()

"""
Knowledge Base Integration System

This module provides infrastructure for:
- Dynamic knowledge base discovery and integration
- Provider-agnostic KB registry
- Streaming KB data
- Multi-tier caching
- Entity linking and enrichment
"""

from knowledge_bases.base import (
    KnowledgeBaseProvider,
    KBEntity,
    KBMetadata,
    Relationship,
    KBCapabilities
)
from knowledge_bases.registry import KnowledgeBaseRegistry
from knowledge_bases.cache import MultiTierCacheManager

__all__ = [
    'KnowledgeBaseProvider',
    'KBEntity',
    'KBMetadata',
    'Relationship',
    'KBCapabilities',
    'KnowledgeBaseRegistry',
    'MultiTierCacheManager'
]

"""
Configuration Management for Domain-Specific NLP

Provides:
- YAML-based domain configuration
- Dynamic configuration reloading
- Trust validation for external resources
"""

from .loader import ConfigurationLoader, DomainConfig

__all__ = [
    "ConfigurationLoader",
    "DomainConfig"
]

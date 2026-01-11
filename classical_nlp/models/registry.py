"""
Model Registry for Classical NLP Providers

Manages available NLP providers and provides factory methods for
creating provider instances based on language and configuration.
"""

from typing import Dict, List, Any, Optional, Type
import logging

from .base import ClassicalNLPProvider, ProviderStatus
from .latincy_provider import LatinCyProvider
from .cltk_provider import CLTKLatinProvider, CLTKGreekProvider

logger = logging.getLogger(__name__)


class ModelRegistry:
    """
    Registry for classical NLP model providers.

    Manages provider registration, discovery, and instantiation.
    """

    # Default provider mapping by language
    _default_providers: Dict[str, Type[ClassicalNLPProvider]] = {
        "latin": LatinCyProvider,
        "la": LatinCyProvider,
        "ancient_greek": CLTKGreekProvider,
        "grc": CLTKGreekProvider,
    }

    # All available providers
    _all_providers: Dict[str, Type[ClassicalNLPProvider]] = {
        "latincy": LatinCyProvider,
        "cltk-latin": CLTKLatinProvider,
        "cltk-greek": CLTKGreekProvider,
    }

    # Provider metadata
    _provider_info: Dict[str, Dict[str, Any]] = {
        "latincy": {
            "name": "LatinCy",
            "description": "spaCy-based model for Latin with lemmatization, POS tagging, and dependency parsing",
            "languages": ["latin", "la"],
            "features": ["lemmatization", "pos_tagging", "morphology", "dependency_parsing", "botanical_detection"],
            "recommended_for": ["general_latin", "virgil", "botanical_texts"]
        },
        "cltk-latin": {
            "name": "CLTK Latin",
            "description": "Classical Language Toolkit for Latin with morphological analysis and metrical scansion",
            "languages": ["latin", "la"],
            "features": ["lemmatization", "pos_tagging", "morphology", "metrical_analysis", "botanical_detection"],
            "recommended_for": ["poetry", "metrical_analysis", "morphological_study"]
        },
        "cltk-greek": {
            "name": "CLTK Greek",
            "description": "Classical Language Toolkit for Ancient Greek with dialect detection",
            "languages": ["ancient_greek", "grc"],
            "features": ["lemmatization", "pos_tagging", "morphology", "dialect_detection", "botanical_detection"],
            "recommended_for": ["ancient_greek_texts", "homeric_greek", "attic_greek"]
        }
    }

    # Cached instances
    _instances: Dict[str, ClassicalNLPProvider] = {}

    @classmethod
    def register_provider(
        cls,
        provider_id: str,
        provider_class: Type[ClassicalNLPProvider],
        info: Dict[str, Any] = None
    ):
        """
        Register a new provider.

        Args:
            provider_id: Unique identifier for the provider
            provider_class: Provider class
            info: Provider metadata
        """
        cls._all_providers[provider_id] = provider_class
        if info:
            cls._provider_info[provider_id] = info
        logger.info(f"Registered provider: {provider_id}")

    @classmethod
    def get_provider(
        cls,
        provider_id: str = None,
        language: str = None,
        config: Dict[str, Any] = None,
        use_cache: bool = True
    ) -> ClassicalNLPProvider:
        """
        Get a provider instance.

        Args:
            provider_id: Specific provider ID (e.g., 'latincy', 'cltk-latin')
            language: Language code to select default provider
            config: Provider configuration
            use_cache: Whether to use cached instances

        Returns:
            ClassicalNLPProvider instance
        """
        # Determine which provider to use
        if provider_id and provider_id in cls._all_providers:
            provider_class = cls._all_providers[provider_id]
            cache_key = provider_id
        elif language and language.lower() in cls._default_providers:
            provider_class = cls._default_providers[language.lower()]
            cache_key = f"default:{language.lower()}"
        else:
            raise ValueError(
                f"No provider found for id='{provider_id}' or language='{language}'. "
                f"Available providers: {list(cls._all_providers.keys())}"
            )

        # Check cache
        if use_cache and cache_key in cls._instances:
            instance = cls._instances[cache_key]
            if instance.status == ProviderStatus.AVAILABLE:
                return instance

        # Create new instance
        instance = provider_class(config)

        if use_cache:
            cls._instances[cache_key] = instance

        return instance

    @classmethod
    def get_providers_for_language(cls, language: str) -> List[str]:
        """
        Get all available providers for a language.

        Args:
            language: Language code

        Returns:
            List of provider IDs
        """
        language = language.lower()
        providers = []

        for provider_id, info in cls._provider_info.items():
            if language in info.get("languages", []):
                providers.append(provider_id)

        return providers

    @classmethod
    def get_provider_info(cls, provider_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata about a provider."""
        return cls._provider_info.get(provider_id)

    @classmethod
    def list_all_providers(cls) -> Dict[str, Dict[str, Any]]:
        """Get information about all available providers."""
        return cls._provider_info.copy()

    @classmethod
    async def initialize_all(cls, config: Dict[str, Any] = None) -> Dict[str, bool]:
        """
        Initialize all providers.

        Args:
            config: Configuration to pass to providers

        Returns:
            Dictionary mapping provider IDs to initialization success
        """
        results = {}

        for provider_id in cls._all_providers:
            try:
                provider = cls.get_provider(provider_id=provider_id, config=config)
                success = await provider.initialize()
                results[provider_id] = success
                logger.info(f"Provider {provider_id} initialized: {success}")
            except Exception as e:
                results[provider_id] = False
                logger.error(f"Failed to initialize provider {provider_id}: {e}")

        return results

    @classmethod
    async def health_check_all(cls) -> Dict[str, bool]:
        """
        Check health of all cached providers.

        Returns:
            Dictionary mapping provider IDs to health status
        """
        results = {}

        for cache_key, provider in cls._instances.items():
            try:
                results[cache_key] = await provider.health_check()
            except Exception as e:
                results[cache_key] = False
                logger.error(f"Health check failed for {cache_key}: {e}")

        return results

    @classmethod
    def clear_cache(cls):
        """Clear all cached provider instances."""
        cls._instances.clear()


def get_provider_for_language(
    language: str,
    provider_id: str = None,
    config: Dict[str, Any] = None
) -> ClassicalNLPProvider:
    """
    Convenience function to get a provider for a language.

    Args:
        language: Language code ('latin', 'ancient_greek', etc.)
        provider_id: Optional specific provider ID
        config: Provider configuration

    Returns:
        ClassicalNLPProvider instance
    """
    return ModelRegistry.get_provider(
        provider_id=provider_id,
        language=language,
        config=config
    )


def get_available_models() -> Dict[str, Any]:
    """
    Get information about all available models.

    Returns:
        Dictionary with model information organized by language
    """
    models = {
        "latin": [],
        "ancient_greek": []
    }

    for provider_id, info in ModelRegistry.list_all_providers().items():
        for lang in info.get("languages", []):
            if lang in ["latin", "la"]:
                models["latin"].append({
                    "id": provider_id,
                    "name": info["name"],
                    "description": info["description"],
                    "features": info.get("features", []),
                    "recommended_for": info.get("recommended_for", [])
                })
            elif lang in ["ancient_greek", "grc"]:
                models["ancient_greek"].append({
                    "id": provider_id,
                    "name": info["name"],
                    "description": info["description"],
                    "features": info.get("features", []),
                    "recommended_for": info.get("recommended_for", [])
                })

    return models

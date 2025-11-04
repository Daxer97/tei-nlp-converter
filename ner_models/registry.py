"""
Model Provider Registry System

Manages dynamic discovery, loading, and management of NER models from multiple providers.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type, Any
import asyncio
from datetime import datetime
import importlib
from ner_models.base import (
    NERModel,
    ModelMetadata,
    ModelCapabilities,
    SelectionCriteria
)
from logger import get_logger

logger = get_logger(__name__)


class NERModelProvider(ABC):
    """Base interface for all NER model providers"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.model_cache: Dict[str, NERModel] = {}

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get provider name"""
        pass

    @abstractmethod
    async def list_available_models(self, domain: Optional[str] = None) -> List[ModelMetadata]:
        """
        Discover available models from this provider

        Args:
            domain: Optional domain filter (e.g., 'medical', 'legal')

        Returns:
            List of model metadata objects
        """
        pass

    @abstractmethod
    async def load_model(self, model_id: str, version: str = "latest") -> NERModel:
        """
        Load a specific model version

        Args:
            model_id: Unique model identifier
            version: Model version (default: "latest")

        Returns:
            Loaded NER model instance
        """
        pass

    @abstractmethod
    def get_model_capabilities(self, model_id: str) -> ModelCapabilities:
        """
        Get capabilities of a model

        Args:
            model_id: Model identifier

        Returns:
            Model capabilities
        """
        pass

    async def unload_model(self, model_id: str) -> bool:
        """
        Unload a model from cache

        Args:
            model_id: Model identifier

        Returns:
            True if successful
        """
        if model_id in self.model_cache:
            model = self.model_cache[model_id]
            await model.unload()
            del self.model_cache[model_id]
            logger.info(f"Unloaded model: {model_id}")
            return True
        return False

    def get_cached_model(self, model_id: str) -> Optional[NERModel]:
        """Get cached model if available"""
        return self.model_cache.get(model_id)


class ModelProviderRegistry:
    """Central registry for all model providers"""

    def __init__(self):
        self.providers: Dict[str, NERModelProvider] = {}
        self._lock = asyncio.Lock()

    def register_provider(self, provider: NERModelProvider):
        """
        Register a new model provider

        Args:
            provider: Model provider instance
        """
        name = provider.get_provider_name()
        self.providers[name] = provider
        logger.info(f"Registered model provider: {name}")

    def unregister_provider(self, provider_name: str):
        """
        Unregister a model provider

        Args:
            provider_name: Name of provider to remove
        """
        if provider_name in self.providers:
            del self.providers[provider_name]
            logger.info(f"Unregistered model provider: {provider_name}")

    def get_provider(self, provider_name: str) -> Optional[NERModelProvider]:
        """
        Get a registered provider

        Args:
            provider_name: Provider name

        Returns:
            Provider instance or None
        """
        return self.providers.get(provider_name)

    def list_providers(self) -> List[str]:
        """List all registered providers"""
        return list(self.providers.keys())

    async def discover_all_models(self, domain: Optional[str] = None) -> Dict[str, List[ModelMetadata]]:
        """
        Query all providers and build comprehensive catalog

        Args:
            domain: Optional domain filter

        Returns:
            Dictionary mapping provider names to their available models
        """
        async with self._lock:
            catalog = {}

            for provider_name, provider in self.providers.items():
                try:
                    logger.info(f"Discovering models from provider: {provider_name}")
                    models = await provider.list_available_models(domain)
                    catalog[provider_name] = models
                    logger.info(f"Discovered {len(models)} models from {provider_name}")

                except Exception as e:
                    logger.error(f"Failed to discover models from {provider_name}: {e}")
                    catalog[provider_name] = []

            return catalog

    async def load_model(self, provider_name: str, model_id: str, version: str = "latest") -> Optional[NERModel]:
        """
        Load a model from a specific provider

        Args:
            provider_name: Provider name
            model_id: Model identifier
            version: Model version

        Returns:
            Loaded model or None if failed
        """
        provider = self.get_provider(provider_name)
        if not provider:
            logger.error(f"Provider not found: {provider_name}")
            return None

        try:
            # Check cache first
            cached = provider.get_cached_model(model_id)
            if cached and cached.is_loaded():
                logger.info(f"Using cached model: {model_id}")
                return cached

            # Load model
            logger.info(f"Loading model: {model_id} from {provider_name}")
            model = await provider.load_model(model_id, version)
            return model

        except Exception as e:
            logger.error(f"Failed to load model {model_id} from {provider_name}: {e}")
            return None

    def get_optimal_models(
        self,
        catalog: Dict[str, List[ModelMetadata]],
        criteria: SelectionCriteria
    ) -> List[ModelMetadata]:
        """
        Select optimal models based on criteria

        Args:
            catalog: Model catalog from discover_all_models
            criteria: Selection criteria

        Returns:
            List of selected models ranked by score
        """
        candidates = []

        # Collect all models from all providers
        for provider_name, models in catalog.items():
            for model in models:
                # Apply filters
                if criteria.require_trusted and not model.trusted:
                    continue

                if criteria.preferred_providers and model.provider not in criteria.preferred_providers:
                    continue

                if model.performance.f1_score < criteria.min_f1_score:
                    continue

                if model.performance.latency_ms > criteria.max_latency_ms:
                    continue

                if criteria.max_model_size_mb and model.model_size_mb:
                    if model.model_size_mb > criteria.max_model_size_mb:
                        continue

                # Check entity type overlap
                if criteria.entity_types:
                    model_types = set(model.capabilities.entity_types)
                    required_types = set(criteria.entity_types)
                    if not required_types.intersection(model_types):
                        continue

                # Check language support
                model_languages = set(model.capabilities.languages)
                required_languages = set(criteria.languages)
                if not required_languages.intersection(model_languages):
                    continue

                candidates.append(model)

        # Rank by composite score
        ranked = sorted(
            candidates,
            key=lambda m: self._calculate_model_score(m, criteria),
            reverse=True
        )

        # Return within min/max bounds
        min_count = criteria.min_models
        max_count = criteria.max_models

        if len(ranked) < min_count:
            logger.warning(
                f"Found {len(ranked)} models but {min_count} required. "
                f"Returning all available models."
            )
            return ranked

        return ranked[:max_count]

    def _calculate_model_score(self, model: ModelMetadata, criteria: SelectionCriteria) -> float:
        """
        Calculate composite score for model ranking

        Score considers:
        - F1 score (weighted 40%)
        - Latency (weighted 30%)
        - Provider preference (weighted 20%)
        - Entity type coverage (weighted 10%)
        """
        score = 0.0

        # F1 score component (0-40 points)
        score += model.performance.f1_score * 40

        # Latency component (0-30 points) - lower is better
        latency_score = max(0, 1 - (model.performance.latency_ms / criteria.max_latency_ms))
        score += latency_score * 30

        # Provider preference (0-20 points)
        if model.provider in criteria.preferred_providers:
            provider_rank = criteria.preferred_providers.index(model.provider)
            provider_score = 1 - (provider_rank / len(criteria.preferred_providers))
            score += provider_score * 20

        # Entity type coverage (0-10 points)
        if criteria.entity_types:
            model_types = set(model.capabilities.entity_types)
            required_types = set(criteria.entity_types)
            coverage = len(required_types.intersection(model_types)) / len(required_types)
            score += coverage * 10

        return score

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Check health of all providers

        Returns:
            Dictionary mapping provider names to health status
        """
        results = {}

        for provider_name, provider in self.providers.items():
            try:
                # Try to list models as health check
                models = await provider.list_available_models()
                results[provider_name] = True
                logger.debug(f"Provider {provider_name} is healthy ({len(models)} models available)")

            except Exception as e:
                logger.error(f"Provider {provider_name} health check failed: {e}")
                results[provider_name] = False

        return results

    async def cleanup_all(self):
        """Cleanup all providers and cached models"""
        for provider_name, provider in self.providers.items():
            try:
                # Unload all cached models
                for model_id in list(provider.model_cache.keys()):
                    await provider.unload_model(model_id)

                logger.info(f"Cleaned up provider: {provider_name}")

            except Exception as e:
                logger.error(f"Error cleaning up provider {provider_name}: {e}")


# Global registry instance
_global_registry: Optional[ModelProviderRegistry] = None
_registry_lock = asyncio.Lock()


async def get_global_registry() -> ModelProviderRegistry:
    """Get or create the global model provider registry"""
    global _global_registry

    if _global_registry is None:
        async with _registry_lock:
            if _global_registry is None:
                _global_registry = ModelProviderRegistry()
                logger.info("Initialized global model provider registry")

    return _global_registry


async def initialize_providers(config: Optional[Dict[str, Any]] = None):
    """
    Initialize and register all available providers

    Args:
        config: Configuration dictionary with provider settings
    """
    registry = await get_global_registry()
    config = config or {}

    # Import and register providers
    try:
        # Register SpaCy provider if available
        if config.get('enable_spacy', True):
            from ner_models.providers.spacy_provider import SpacyModelProvider
            spacy_config = config.get('spacy', {})
            spacy_provider = SpacyModelProvider(spacy_config)
            registry.register_provider(spacy_provider)

    except ImportError as e:
        logger.warning(f"Could not load SpaCy provider: {e}")

    try:
        # Register Hugging Face provider if available
        if config.get('enable_huggingface', True):
            from ner_models.providers.huggingface_provider import HuggingFaceProvider
            hf_config = config.get('huggingface', {})
            hf_provider = HuggingFaceProvider(hf_config)
            registry.register_provider(hf_provider)

    except ImportError as e:
        logger.warning(f"Could not load Hugging Face provider: {e}")

    try:
        # Register Custom provider if configured
        if config.get('enable_custom', False):
            from ner_models.providers.custom_provider import CustomModelProvider
            custom_config = config.get('custom', {})
            custom_provider = CustomModelProvider(custom_config)
            registry.register_provider(custom_provider)

    except ImportError as e:
        logger.warning(f"Could not load Custom provider: {e}")

    logger.info(f"Initialized {len(registry.list_providers())} model providers")

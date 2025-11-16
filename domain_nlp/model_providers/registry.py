"""
Central registry for all NER model providers.

This module manages model discovery, loading, and selection across
multiple provider backends.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict

from .base import (
    NERModelProvider,
    ModelMetadata,
    NERModel,
    SelectionCriteria,
    ModelCapabilities
)

logger = logging.getLogger(__name__)


class ModelCatalog:
    """Persistent catalog of discovered models"""

    def __init__(self):
        self._models: Dict[str, List[ModelMetadata]] = defaultdict(list)
        self._by_domain: Dict[str, List[ModelMetadata]] = defaultdict(list)
        self._last_updated: Dict[str, datetime] = {}

    def update(self, provider_models: Dict[str, List[ModelMetadata]]) -> None:
        """Update catalog with new model discoveries"""
        for provider, models in provider_models.items():
            self._models[provider] = models
            self._last_updated[provider] = datetime.now()

            # Index by domain
            for model in models:
                if model not in self._by_domain[model.domain]:
                    self._by_domain[model.domain].append(model)

        logger.info(f"Updated catalog with {sum(len(m) for m in provider_models.values())} models")

    def query(
        self,
        domain: Optional[str] = None,
        provider: Optional[str] = None,
        min_f1: float = 0.0,
        max_latency: float = float("inf"),
        entity_types: Optional[set] = None
    ) -> List[ModelMetadata]:
        """Query catalog with filters"""
        results = []

        if provider:
            models = self._models.get(provider, [])
        elif domain:
            models = self._by_domain.get(domain, [])
        else:
            models = [m for provider_models in self._models.values() for m in provider_models]

        for model in models:
            if domain and model.domain != domain:
                continue
            if model.performance.f1_score < min_f1:
                continue
            if model.performance.latency_ms > max_latency:
                continue
            if entity_types and not entity_types.issubset(model.entity_types):
                continue
            results.append(model)

        return results

    def get_all_models(self) -> List[ModelMetadata]:
        """Get all models in catalog"""
        return [m for provider_models in self._models.values() for m in provider_models]

    def get_by_id(self, model_id: str) -> Optional[ModelMetadata]:
        """Get model by ID"""
        for models in self._models.values():
            for model in models:
                if model.model_id == model_id:
                    return model
        return None


class TrustValidator:
    """Validates models from trusted sources"""

    def __init__(self):
        self.trusted_domains = {
            "github.com/explosion",
            "huggingface.co",
            "allenai.github.io",
            "microsoft.github.io",
            "nlpaueb",
            "scispacy"
        }
        self.min_f1_threshold = 0.70

    def validate(self, model: ModelMetadata) -> bool:
        """Comprehensive trust validation"""
        checks = [
            self._check_source(model),
            self._check_performance(model),
            self._check_metadata(model)
        ]
        return all(checks)

    def _check_source(self, model: ModelMetadata) -> bool:
        """Verify source is from trusted domain"""
        if model.trusted:
            return True

        for trusted in self.trusted_domains:
            if trusted in model.source_url or trusted in model.model_id:
                return True

        logger.warning(f"Untrusted source for model {model.model_id}")
        return False

    def _check_performance(self, model: ModelMetadata) -> bool:
        """Check minimum performance requirements"""
        if model.performance.f1_score < self.min_f1_threshold:
            logger.warning(
                f"Model {model.model_id} below F1 threshold: "
                f"{model.performance.f1_score} < {self.min_f1_threshold}"
            )
            return False
        return True

    def _check_metadata(self, model: ModelMetadata) -> bool:
        """Validate model has required metadata"""
        if not model.entity_types:
            logger.warning(f"Model {model.model_id} has no entity types defined")
            return False
        return True


class ModelProviderRegistry:
    """Central registry for all model providers"""

    def __init__(self):
        self.providers: Dict[str, NERModelProvider] = {}
        self.model_catalog = ModelCatalog()
        self.trust_validator = TrustValidator()
        self._loaded_models: Dict[str, NERModel] = {}
        self._model_load_times: Dict[str, datetime] = {}

    def register_provider(self, name: str, provider: NERModelProvider) -> None:
        """Register a new model provider"""
        self.providers[name] = provider
        logger.info(f"Registered model provider: {name}")

    def unregister_provider(self, name: str) -> None:
        """Remove a provider from registry"""
        if name in self.providers:
            del self.providers[name]
            logger.info(f"Unregistered model provider: {name}")

    def list_providers(self) -> List[str]:
        """List all registered providers"""
        return list(self.providers.keys())

    async def discover_all_models(self) -> Dict[str, List[ModelMetadata]]:
        """Query all providers and build comprehensive catalog"""
        catalog = {}

        for provider_name, provider in self.providers.items():
            try:
                logger.info(f"Discovering models from {provider_name}...")
                models = provider.list_available_models()

                # Validate and trust check
                validated = [m for m in models if self.trust_validator.validate(m)]

                catalog[provider_name] = validated
                logger.info(f"Discovered {len(validated)} valid models from {provider_name}")

            except Exception as e:
                logger.error(f"Failed to discover from {provider_name}: {e}")
                catalog[provider_name] = []

        # Store in persistent catalog
        self.model_catalog.update(catalog)
        return catalog

    def get_optimal_model(
        self,
        domain: str,
        criteria: SelectionCriteria
    ) -> Optional[ModelMetadata]:
        """Select optimal model based on criteria"""
        candidates = self.model_catalog.query(
            domain=domain,
            min_f1=criteria.min_f1_score,
            max_latency=criteria.max_latency_ms
        )

        if not candidates:
            logger.warning(f"No models found for domain {domain} matching criteria")
            return None

        # Filter by additional criteria
        filtered = [m for m in candidates if criteria.matches(m)]
        if not filtered:
            logger.warning("No models match all selection criteria, using best available")
            filtered = candidates

        # Rank by composite score
        ranked = sorted(
            filtered,
            key=lambda m: self._calculate_score(m, criteria),
            reverse=True
        )

        logger.info(f"Selected optimal model: {ranked[0].model_id}")
        return ranked[0]

    def get_top_models(
        self,
        domain: str,
        criteria: SelectionCriteria,
        count: int = 3
    ) -> List[ModelMetadata]:
        """Get top N models for ensemble"""
        candidates = self.model_catalog.query(
            domain=domain,
            min_f1=criteria.min_f1_score,
            max_latency=criteria.max_latency_ms
        )

        if not candidates:
            return []

        # Filter and rank
        filtered = [m for m in candidates if criteria.matches(m)]
        if not filtered:
            filtered = candidates

        ranked = sorted(
            filtered,
            key=lambda m: self._calculate_score(m, criteria),
            reverse=True
        )

        return ranked[:count]

    def _calculate_score(self, model: ModelMetadata, criteria: SelectionCriteria) -> float:
        """Calculate composite score for model ranking"""
        score = 0.0

        # F1 score weighted heavily (0-50 points)
        score += model.performance.f1_score * 50

        # Latency (inverse, 0-30 points)
        max_acceptable_latency = criteria.max_latency_ms
        if model.performance.latency_ms > 0:
            latency_score = max(
                0,
                30 * (1 - model.performance.latency_ms / max_acceptable_latency)
            )
            score += latency_score

        # Trusted source (10 points)
        if model.trusted:
            score += 10

        # Preferred provider (5 points)
        if model.provider in criteria.preferred_providers:
            score += 5

        # Entity type coverage (0-5 points)
        if criteria.entity_types:
            coverage = len(model.entity_types & criteria.entity_types) / len(criteria.entity_types)
            score += coverage * 5

        return score

    async def load_model(self, model_id: str, version: str = "latest") -> Optional[NERModel]:
        """Load a model by ID"""
        cache_key = f"{model_id}:{version}"

        # Check if already loaded
        if cache_key in self._loaded_models:
            logger.info(f"Using cached model: {cache_key}")
            return self._loaded_models[cache_key]

        # Find the provider for this model
        model_meta = self.model_catalog.get_by_id(model_id)
        if not model_meta:
            logger.error(f"Model {model_id} not found in catalog")
            return None

        provider_name = model_meta.provider
        if provider_name not in self.providers:
            logger.error(f"Provider {provider_name} not registered")
            return None

        provider = self.providers[provider_name]

        try:
            logger.info(f"Loading model {model_id} from {provider_name}...")
            model = await provider.load_model(model_id, version)
            self._loaded_models[cache_key] = model
            self._model_load_times[cache_key] = datetime.now()
            logger.info(f"Successfully loaded model: {cache_key}")
            return model

        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            return None

    async def unload_model(self, model_id: str, version: str = "latest") -> None:
        """Unload a model to free resources"""
        cache_key = f"{model_id}:{version}"

        if cache_key in self._loaded_models:
            model = self._loaded_models[cache_key]
            model.cleanup()
            del self._loaded_models[cache_key]
            if cache_key in self._model_load_times:
                del self._model_load_times[cache_key]
            logger.info(f"Unloaded model: {cache_key}")

    def get_loaded_models(self) -> List[str]:
        """Get list of currently loaded models"""
        return list(self._loaded_models.keys())

    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all providers"""
        results = {}
        for name, provider in self.providers.items():
            try:
                results[name] = await provider.health_check()
            except Exception as e:
                logger.error(f"Health check failed for {name}: {e}")
                results[name] = False
        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics"""
        return {
            "total_providers": len(self.providers),
            "provider_names": list(self.providers.keys()),
            "total_models_discovered": len(self.model_catalog.get_all_models()),
            "loaded_models": len(self._loaded_models),
            "loaded_model_ids": list(self._loaded_models.keys()),
            "models_by_domain": {
                domain: len(models)
                for domain, models in self.model_catalog._by_domain.items()
            }
        }

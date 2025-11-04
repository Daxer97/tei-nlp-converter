"""
Model Catalog - Persistent storage and querying of model metadata
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
from pathlib import Path
from ner_models.base import ModelMetadata, ModelCapabilities, ModelPerformanceMetrics
from logger import get_logger

logger = get_logger(__name__)


class ModelCatalog:
    """
    Manages persistent storage and querying of model metadata

    This catalog provides:
    - Model metadata storage (file-based or database-backed)
    - Efficient querying by domain, provider, performance metrics
    - Model versioning and history tracking
    - Caching for fast lookups
    """

    def __init__(self, storage_path: str = "data/model_catalog.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._catalog: Dict[str, ModelMetadata] = {}
        self._load_catalog()

    def _load_catalog(self):
        """Load catalog from storage"""
        try:
            if self.storage_path.exists():
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)

                for model_id, model_data in data.items():
                    try:
                        # Reconstruct ModelMetadata from dict
                        metadata = self._deserialize_metadata(model_data)
                        self._catalog[model_id] = metadata

                    except Exception as e:
                        logger.error(f"Failed to load model {model_id}: {e}")

                logger.info(f"Loaded {len(self._catalog)} models from catalog")

        except Exception as e:
            logger.warning(f"Could not load catalog from {self.storage_path}: {e}")
            self._catalog = {}

    def _save_catalog(self):
        """Save catalog to storage"""
        try:
            data = {}
            for model_id, metadata in self._catalog.items():
                data[model_id] = metadata.to_dict()

            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)

            logger.debug(f"Saved {len(self._catalog)} models to catalog")

        except Exception as e:
            logger.error(f"Failed to save catalog: {e}")

    def _deserialize_metadata(self, data: Dict[str, Any]) -> ModelMetadata:
        """Reconstruct ModelMetadata from dictionary"""

        # Reconstruct capabilities
        cap_data = data['capabilities']
        capabilities = ModelCapabilities(
            entity_types=cap_data['entity_types'],
            supports_confidence_scores=cap_data.get('supports_confidence_scores', True),
            supports_multiword_entities=cap_data.get('supports_multiword_entities', True),
            supports_nested_entities=cap_data.get('supports_nested_entities', False),
            supports_entity_linking=cap_data.get('supports_entity_linking', False),
            max_text_length=cap_data.get('max_text_length'),
            languages=cap_data.get('languages', ['en'])
        )

        # Reconstruct performance metrics
        perf_data = data['performance']
        performance = ModelPerformanceMetrics(
            f1_score=perf_data['f1_score'],
            precision=perf_data['precision'],
            recall=perf_data['recall'],
            latency_ms=perf_data['latency_ms'],
            throughput_docs_per_sec=perf_data.get('throughput_docs_per_sec'),
            memory_mb=perf_data.get('memory_mb'),
            last_evaluated=datetime.fromisoformat(perf_data['last_evaluated']) if perf_data.get('last_evaluated') else None,
            evaluation_dataset=perf_data.get('evaluation_dataset')
        )

        # Reconstruct metadata
        metadata = ModelMetadata(
            model_id=data['model_id'],
            provider=data['provider'],
            version=data['version'],
            domain=data['domain'],
            capabilities=capabilities,
            performance=performance,
            source_url=data['source_url'],
            trusted=data.get('trusted', False),
            requires_kb=data.get('requires_kb', []),
            description=data.get('description'),
            license=data.get('license'),
            model_size_mb=data.get('model_size_mb'),
            signature=data.get('signature'),
            created_at=datetime.fromisoformat(data['created_at']) if 'created_at' in data else datetime.now()
        )

        return metadata

    def add_model(self, metadata: ModelMetadata):
        """
        Add or update a model in the catalog

        Args:
            metadata: Model metadata to add
        """
        self._catalog[metadata.model_id] = metadata
        self._save_catalog()
        logger.info(f"Added model to catalog: {metadata.model_id}")

    def add_models_bulk(self, models: List[ModelMetadata]):
        """
        Add multiple models in bulk

        Args:
            models: List of model metadata
        """
        for metadata in models:
            self._catalog[metadata.model_id] = metadata

        self._save_catalog()
        logger.info(f"Added {len(models)} models to catalog")

    def get_model(self, model_id: str) -> Optional[ModelMetadata]:
        """
        Get a model by ID

        Args:
            model_id: Model identifier

        Returns:
            Model metadata or None if not found
        """
        return self._catalog.get(model_id)

    def remove_model(self, model_id: str) -> bool:
        """
        Remove a model from catalog

        Args:
            model_id: Model identifier

        Returns:
            True if removed, False if not found
        """
        if model_id in self._catalog:
            del self._catalog[model_id]
            self._save_catalog()
            logger.info(f"Removed model from catalog: {model_id}")
            return True

        return False

    def query(
        self,
        domain: Optional[str] = None,
        provider: Optional[str] = None,
        min_f1: Optional[float] = None,
        max_latency: Optional[float] = None,
        entity_types: Optional[List[str]] = None,
        trusted_only: bool = False,
        language: str = 'en'
    ) -> List[ModelMetadata]:
        """
        Query models by various criteria

        Args:
            domain: Filter by domain
            provider: Filter by provider
            min_f1: Minimum F1 score
            max_latency: Maximum latency in ms
            entity_types: Required entity types
            trusted_only: Only return trusted models
            language: Required language support

        Returns:
            List of matching models
        """
        results = []

        for model in self._catalog.values():
            # Apply filters
            if domain and model.domain != domain:
                continue

            if provider and model.provider != provider:
                continue

            if min_f1 and model.performance.f1_score < min_f1:
                continue

            if max_latency and model.performance.latency_ms > max_latency:
                continue

            if trusted_only and not model.trusted:
                continue

            if language not in model.capabilities.languages:
                continue

            if entity_types:
                model_types = set(model.capabilities.entity_types)
                required_types = set(entity_types)
                if not required_types.intersection(model_types):
                    continue

            results.append(model)

        return results

    def list_all_models(self) -> List[ModelMetadata]:
        """Get all models in catalog"""
        return list(self._catalog.values())

    def list_domains(self) -> List[str]:
        """List all available domains"""
        return sorted(set(m.domain for m in self._catalog.values()))

    def list_providers(self) -> List[str]:
        """List all available providers"""
        return sorted(set(m.provider for m in self._catalog.values()))

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get catalog statistics

        Returns:
            Dictionary with statistics
        """
        models = list(self._catalog.values())

        if not models:
            return {
                'total_models': 0,
                'domains': [],
                'providers': [],
                'avg_f1_score': 0,
                'avg_latency_ms': 0
            }

        return {
            'total_models': len(models),
            'domains': self.list_domains(),
            'providers': self.list_providers(),
            'avg_f1_score': sum(m.performance.f1_score for m in models) / len(models),
            'avg_latency_ms': sum(m.performance.latency_ms for m in models) / len(models),
            'trusted_models': sum(1 for m in models if m.trusted),
            'untrusted_models': sum(1 for m in models if not m.trusted)
        }

    def update(self, catalog_data: Dict[str, List[ModelMetadata]]):
        """
        Update catalog with discovered models

        Args:
            catalog_data: Dictionary mapping provider names to model lists
        """
        updated = 0
        new = 0

        for provider_name, models in catalog_data.items():
            for metadata in models:
                if metadata.model_id in self._catalog:
                    updated += 1
                else:
                    new += 1

                self._catalog[metadata.model_id] = metadata

        self._save_catalog()
        logger.info(f"Updated catalog: {new} new models, {updated} updated models")

    def clear(self):
        """Clear the entire catalog"""
        self._catalog.clear()
        self._save_catalog()
        logger.warning("Cleared entire model catalog")

    def export(self, output_path: str):
        """
        Export catalog to a different file

        Args:
            output_path: Path to export to
        """
        try:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)

            data = {}
            for model_id, metadata in self._catalog.items():
                data[model_id] = metadata.to_dict()

            with open(output, 'w') as f:
                json.dump(data, f, indent=2, default=str)

            logger.info(f"Exported catalog to {output_path}")

        except Exception as e:
            logger.error(f"Failed to export catalog: {e}")

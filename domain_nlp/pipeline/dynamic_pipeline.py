"""
Dynamic NLP Pipeline with ensemble merging and KB enrichment.

This is the core orchestrator that:
- Loads optimal models based on configuration
- Extracts entities using multiple models in parallel
- Applies pattern matching for structured data
- Enriches entities with knowledge base data
- Merges results using ensemble strategies
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

from ..model_providers.base import Entity, SelectionCriteria, NERModel
from ..model_providers.registry import ModelProviderRegistry
from ..knowledge_bases.base import KBSelectionCriteria, EnrichedEntity, KBEntity
from ..knowledge_bases.registry import KnowledgeBaseRegistry
from ..pattern_matching.matcher import DomainPatternMatcher, StructuredEntity
from .ensemble import EnsembleMerger

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for dynamic NLP pipeline"""
    domain: str
    model_selection_criteria: SelectionCriteria
    kb_selection_criteria: KBSelectionCriteria
    ensemble_strategy: str = "majority_vote"
    enable_pattern_matching: bool = True
    enable_kb_enrichment: bool = True
    max_parallel_models: int = 3
    custom_patterns: Optional[Dict[str, Dict]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnrichedDocument:
    """Result of processing a document through the pipeline"""
    text: str
    entities: List[EnrichedEntity]
    structured_entities: List[StructuredEntity] = field(default_factory=list)
    processing_time_ms: float = 0.0
    models_used: List[str] = field(default_factory=list)
    kb_hit_rate: float = 0.0
    ensemble_agreement: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "entities": [e.to_dict() for e in self.entities],
            "structured_entities": [e.to_dict() for e in self.structured_entities],
            "processing_time_ms": self.processing_time_ms,
            "models_used": self.models_used,
            "kb_hit_rate": self.kb_hit_rate,
            "ensemble_agreement": self.ensemble_agreement,
            "metadata": self.metadata
        }

    def get_entity_count(self) -> int:
        """Get total number of entities"""
        return len(self.entities) + len(self.structured_entities)

    def get_enriched_entities(self) -> List[EnrichedEntity]:
        """Get only entities that have KB enrichment"""
        return [e for e in self.entities if e.is_enriched]


@dataclass
class PerformanceMetrics:
    """Tracks pipeline performance metrics"""
    total_processed: int = 0
    total_entities_extracted: int = 0
    avg_latency_ms: float = 0.0
    avg_kb_hit_rate: float = 0.0
    avg_ensemble_agreement: float = 0.0
    history: List[Dict[str, Any]] = field(default_factory=list)

    def record(self, doc: EnrichedDocument) -> None:
        """Record metrics from processed document"""
        self.total_processed += 1
        self.total_entities_extracted += doc.get_entity_count()

        # Update rolling averages
        n = self.total_processed
        self.avg_latency_ms = ((n - 1) * self.avg_latency_ms + doc.processing_time_ms) / n
        self.avg_kb_hit_rate = ((n - 1) * self.avg_kb_hit_rate + doc.kb_hit_rate) / n
        self.avg_ensemble_agreement = ((n - 1) * self.avg_ensemble_agreement + doc.ensemble_agreement) / n

        # Keep history for analysis
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "latency_ms": doc.processing_time_ms,
            "entity_count": doc.get_entity_count(),
            "kb_hit_rate": doc.kb_hit_rate,
            "ensemble_agreement": doc.ensemble_agreement
        })

        # Trim history to last 1000 entries
        if len(self.history) > 1000:
            self.history = self.history[-1000:]

    def should_optimize(self) -> bool:
        """Check if optimization should be triggered"""
        if self.total_processed < 100:
            return False

        # Trigger optimization if performance degrades
        recent = self.history[-10:] if len(self.history) >= 10 else self.history
        recent_latency = sum(h["latency_ms"] for h in recent) / len(recent)

        return recent_latency > self.avg_latency_ms * 1.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_processed": self.total_processed,
            "total_entities_extracted": self.total_entities_extracted,
            "avg_latency_ms": self.avg_latency_ms,
            "avg_kb_hit_rate": self.avg_kb_hit_rate,
            "avg_ensemble_agreement": self.avg_ensemble_agreement,
            "history_size": len(self.history)
        }


class DynamicNLPPipeline:
    """
    Dynamically configurable, self-optimizing NLP pipeline.

    Orchestrates model loading, entity extraction, pattern matching,
    and knowledge base enrichment with automatic optimization.
    """

    def __init__(
        self,
        config: PipelineConfig,
        model_registry: Optional[ModelProviderRegistry] = None,
        kb_registry: Optional[KnowledgeBaseRegistry] = None
    ):
        self.config = config
        self.domain = config.domain

        # Registries (use provided or create new)
        self.model_registry = model_registry or ModelProviderRegistry()
        self.kb_registry = kb_registry or KnowledgeBaseRegistry()

        # Active models for processing
        self.active_models: List[NERModel] = []
        self.model_weights: List[float] = []

        # Pattern matcher
        self.pattern_matcher = DomainPatternMatcher(
            domain=self.domain,
            custom_patterns=config.custom_patterns
        )

        # Ensemble merger
        self.ensemble_merger = EnsembleMerger(strategy=config.ensemble_strategy)

        # Performance tracking
        self.metrics = PerformanceMetrics()

        # Initialization flag
        self._initialized = False

        logger.info(f"Created pipeline for domain '{self.domain}'")

    async def initialize(self) -> None:
        """Initialize pipeline by loading models and starting KB sync"""
        if self._initialized:
            logger.info("Pipeline already initialized")
            return

        logger.info(f"Initializing pipeline for domain '{self.domain}'")

        # Discover and load optimal models
        await self._load_optimal_models()

        # Start KB sync if enrichment enabled
        if self.config.enable_kb_enrichment:
            await self._initialize_kbs()

        self._initialized = True
        logger.info(f"Pipeline initialized with {len(self.active_models)} models")

    async def _load_optimal_models(self) -> None:
        """Load optimal models based on selection criteria"""
        criteria = self.config.model_selection_criteria

        # Discover all available models
        await self.model_registry.discover_all_models()

        # Get top models for ensemble
        top_models = self.model_registry.get_top_models(
            domain=self.domain,
            criteria=criteria,
            count=self.config.max_parallel_models
        )

        if not top_models:
            logger.warning(f"No models found for domain '{self.domain}'")
            return

        # Load models in parallel
        load_tasks = [
            self.model_registry.load_model(model.model_id, model.version)
            for model in top_models
        ]

        loaded = await asyncio.gather(*load_tasks, return_exceptions=True)

        # Filter successful loads
        for i, result in enumerate(loaded):
            if isinstance(result, Exception):
                logger.error(f"Failed to load model: {result}")
            elif result:
                self.active_models.append(result)
                # Weight based on F1 score
                weight = top_models[i].performance.f1_score
                self.model_weights.append(weight)

        logger.info(f"Loaded {len(self.active_models)} models")

    async def _initialize_kbs(self) -> None:
        """Initialize knowledge base sync"""
        kb_criteria = self.config.kb_selection_criteria

        # Start sync for required KBs
        for kb_id in kb_criteria.required_kbs:
            if kb_id in self.kb_registry.providers:
                await self.kb_registry.start_sync(kb_id)

        # Start sync for optional KBs
        for kb_id in kb_criteria.optional_kbs:
            if kb_id in self.kb_registry.providers:
                await self.kb_registry.start_sync(kb_id)

        logger.info("Initialized KB sync")

    async def process(self, text: str) -> EnrichedDocument:
        """
        Process text through the complete pipeline.

        Args:
            text: Input text to process

        Returns:
            Enriched document with entities and metadata
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()

        # Step 1: Extract entities from all models in parallel
        model_results = []
        if self.active_models:
            extraction_tasks = [
                model.extract_entities(text) for model in self.active_models
            ]
            model_results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

            # Filter out errors
            valid_results = []
            for result in model_results:
                if isinstance(result, Exception):
                    logger.error(f"Model extraction error: {result}")
                    valid_results.append([])
                else:
                    valid_results.append(result)
            model_results = valid_results

        # Step 2: Pattern matching for structured data
        structured_entities = []
        if self.config.enable_pattern_matching:
            structured_entities = self.pattern_matcher.extract_structured_data(text)

        # Step 3: Ensemble merge model results
        consolidated_entities = []
        ensemble_agreement = 1.0
        if model_results:
            consolidated_entities = self.ensemble_merger.merge(
                model_results,
                weights=self.model_weights
            )
            ensemble_agreement = self.ensemble_merger.calculate_agreement_score(model_results)

        # Step 4: Convert to enriched entities
        enriched_entities = [
            EnrichedEntity(
                text=e.text,
                entity_type=e.type,
                start=e.start,
                end=e.end,
                confidence=e.confidence,
                model_id=e.model_id,
                kb_entity=None,
                sources=e.sources
            )
            for e in consolidated_entities
        ]

        # Step 5: Knowledge base enrichment
        kb_hit_rate = 0.0
        if self.config.enable_kb_enrichment and enriched_entities:
            enriched_entities, kb_hit_rate = await self._enrich_with_kbs(enriched_entities)

        # Calculate processing time
        processing_time_ms = (time.time() - start_time) * 1000

        # Build result document
        doc = EnrichedDocument(
            text=text,
            entities=enriched_entities,
            structured_entities=structured_entities,
            processing_time_ms=processing_time_ms,
            models_used=[m.model_id for m in self.active_models],
            kb_hit_rate=kb_hit_rate,
            ensemble_agreement=ensemble_agreement,
            metadata={
                "domain": self.domain,
                "timestamp": datetime.now().isoformat(),
                "ensemble_strategy": self.config.ensemble_strategy
            }
        )

        # Record metrics
        self.metrics.record(doc)

        # Check if optimization needed
        if self.metrics.should_optimize():
            logger.info("Performance degradation detected, consider optimization")

        logger.debug(
            f"Processed text: {len(text)} chars, "
            f"{len(enriched_entities)} entities, "
            f"{len(structured_entities)} patterns, "
            f"{processing_time_ms:.2f}ms"
        )

        return doc

    async def _enrich_with_kbs(
        self,
        entities: List[EnrichedEntity]
    ) -> tuple[List[EnrichedEntity], float]:
        """
        Enrich entities with knowledge base data.

        Args:
            entities: List of entities to enrich

        Returns:
            Tuple of (enriched entities, hit rate)
        """
        fallback_chain = self.config.kb_selection_criteria.fallback_chain
        if not fallback_chain:
            return entities, 0.0

        enriched = []
        hits = 0

        for entity in entities:
            kb_entity = await self.kb_registry.lookup_with_fallback(
                entity.text,
                fallback_chain,
                entity.entity_type
            )

            if kb_entity:
                entity.kb_entity = kb_entity
                hits += 1

            enriched.append(entity)

        hit_rate = hits / len(entities) if entities else 0.0
        return enriched, hit_rate

    async def process_batch(self, texts: List[str]) -> List[EnrichedDocument]:
        """
        Process multiple texts in parallel.

        Args:
            texts: List of texts to process

        Returns:
            List of enriched documents
        """
        tasks = [self.process(text) for text in texts]
        return await asyncio.gather(*tasks)

    def add_model(self, model: NERModel, weight: float = 1.0) -> None:
        """Add a model to the active ensemble"""
        self.active_models.append(model)
        self.model_weights.append(weight)
        logger.info(f"Added model {model.model_id} with weight {weight}")

    def remove_model(self, model_id: str) -> None:
        """Remove a model from the active ensemble"""
        for i, model in enumerate(self.active_models):
            if model.model_id == model_id:
                model.cleanup()
                del self.active_models[i]
                del self.model_weights[i]
                logger.info(f"Removed model {model_id}")
                return

    def update_ensemble_strategy(self, strategy: str) -> None:
        """Update the ensemble merging strategy"""
        self.ensemble_merger = EnsembleMerger(strategy=strategy)
        self.config.ensemble_strategy = strategy
        logger.info(f"Updated ensemble strategy to '{strategy}'")

    def get_statistics(self) -> Dict[str, Any]:
        """Get pipeline statistics"""
        return {
            "domain": self.domain,
            "active_models": len(self.active_models),
            "model_ids": [m.model_id for m in self.active_models],
            "model_weights": self.model_weights,
            "ensemble_strategy": self.config.ensemble_strategy,
            "pattern_matching_enabled": self.config.enable_pattern_matching,
            "kb_enrichment_enabled": self.config.enable_kb_enrichment,
            "initialized": self._initialized,
            "metrics": self.metrics.to_dict(),
            "pattern_count": len(self.pattern_matcher.patterns)
        }

    async def shutdown(self) -> None:
        """Gracefully shutdown pipeline"""
        logger.info("Shutting down pipeline")

        # Cleanup models
        for model in self.active_models:
            model.cleanup()
        self.active_models.clear()
        self.model_weights.clear()

        # Shutdown KB sync
        await self.kb_registry.shutdown()

        self._initialized = False
        logger.info("Pipeline shutdown complete")

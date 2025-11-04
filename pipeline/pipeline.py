"""
Unified Dynamic Processing Pipeline

Orchestrates NER, knowledge base enrichment, and pattern matching
into a cohesive processing workflow with hot-swapping and optimization.
"""
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from pathlib import Path
import yaml
import asyncio

from .trust import TrustValidator, TrustPolicy
from .hot_swap import HotSwapManager, ComponentType
from logger import get_logger

logger = get_logger(__name__)


class ProcessingStage(Enum):
    """Stages in the processing pipeline"""
    NER = "ner"                      # Named entity recognition
    KB_ENRICHMENT = "kb_enrichment"  # Knowledge base enrichment
    PATTERN_MATCHING = "pattern_matching"  # Pattern extraction
    POST_PROCESSING = "post_processing"   # Deduplication, merging


@dataclass
class EntityResult:
    """Unified entity result from pipeline"""
    text: str
    type: str
    start: int
    end: int
    confidence: float

    # Source information
    source_stage: ProcessingStage
    source_model: Optional[str] = None

    # Knowledge base enrichment
    kb_id: Optional[str] = None
    kb_entity_id: Optional[str] = None
    canonical_name: Optional[str] = None
    definition: Optional[str] = None
    semantic_types: List[str] = field(default_factory=list)

    # Pattern matching
    normalized_text: Optional[str] = None
    validated: bool = False
    validation_passed: bool = False

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Complete result from pipeline processing"""
    # Input
    text: str
    domain: Optional[str]

    # Results by stage
    entities: List[EntityResult] = field(default_factory=list)
    ner_entities: List[EntityResult] = field(default_factory=list)
    kb_enriched_entities: List[EntityResult] = field(default_factory=list)
    pattern_matches: List[EntityResult] = field(default_factory=list)

    # Performance metrics
    total_time_ms: float = 0.0
    ner_time_ms: float = 0.0
    kb_time_ms: float = 0.0
    pattern_time_ms: float = 0.0
    post_processing_time_ms: float = 0.0

    # Pipeline metadata
    models_used: List[str] = field(default_factory=list)
    kbs_used: List[str] = field(default_factory=list)
    stages_completed: List[ProcessingStage] = field(default_factory=list)

    # Errors/warnings
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class PipelineConfig:
    """Configuration for pipeline processing"""
    # Stages to run
    enabled_stages: Set[ProcessingStage] = field(default_factory=lambda: {
        ProcessingStage.NER,
        ProcessingStage.KB_ENRICHMENT,
        ProcessingStage.PATTERN_MATCHING,
        ProcessingStage.POST_PROCESSING
    })

    # NER configuration
    ner_model_ids: List[str] = field(default_factory=list)
    ner_ensemble_mode: bool = False
    ner_min_confidence: float = 0.5

    # Knowledge base configuration
    kb_ids: List[str] = field(default_factory=list)
    kb_enrich_all: bool = False  # Enrich all entities or just high-confidence
    kb_min_confidence_for_enrichment: float = 0.7

    # Pattern matching configuration
    pattern_domains: List[str] = field(default_factory=lambda: ["medical", "legal"])
    pattern_auto_detect_domain: bool = True
    pattern_min_confidence: float = 0.5

    # Post-processing configuration
    deduplication_enabled: bool = True
    deduplication_threshold: float = 0.8  # IoU threshold
    merge_overlapping: bool = True

    # Performance tuning
    parallel_processing: bool = True
    max_concurrent_kb_lookups: int = 10
    timeout_seconds: float = 30.0

    # Trust and security
    trust_policy: Optional[TrustPolicy] = None
    enable_trust_validation: bool = True

    @classmethod
    def from_yaml(cls, config_path: Path) -> 'PipelineConfig':
        """Load configuration from YAML file"""
        with open(config_path, 'r') as f:
            config_dict = yaml.safe_load(f)

        # Convert stage names to enums
        if 'enabled_stages' in config_dict:
            config_dict['enabled_stages'] = {
                ProcessingStage(stage) for stage in config_dict['enabled_stages']
            }

        # Create trust policy if configured
        if 'trust_policy' in config_dict:
            trust_config = config_dict.pop('trust_policy')
            config_dict['trust_policy'] = TrustPolicy(**trust_config)

        return cls(**config_dict)


class Pipeline:
    """
    Unified dynamic processing pipeline

    Orchestrates NER, KB enrichment, and pattern matching with:
    - Hot-swappable components
    - Trust validation
    - Self-optimization
    - Configuration-driven behavior

    Example:
        config = PipelineConfig.from_yaml("config/pipeline.yaml")
        pipeline = Pipeline(config)
        await pipeline.initialize()

        result = await pipeline.process(
            "Patient diagnosed with I10 hypertension",
            domain="medical"
        )
    """

    def __init__(self, config: PipelineConfig):
        self.config = config

        # Component managers
        self.hot_swap = HotSwapManager()
        self.trust_validator = TrustValidator(config.trust_policy)

        # Component registries (will be populated during initialization)
        self._ner_registry = None
        self._kb_registry = None
        self._pattern_matcher = None

        self._initialized = False

    async def initialize(self):
        """Initialize pipeline components"""
        if self._initialized:
            logger.warning("Pipeline already initialized")
            return

        logger.info("Initializing pipeline...")

        # Import here to avoid circular dependencies
        from ner_models.registry import ModelProviderRegistry
        from knowledge_bases.registry import KnowledgeBaseRegistry
        from pattern_matching import DomainPatternMatcher

        # Initialize NER registry
        self._ner_registry = ModelProviderRegistry()
        await self._ner_registry.initialize()

        # Initialize KB registry
        self._kb_registry = KnowledgeBaseRegistry()
        await self._kb_registry.initialize()

        # Initialize pattern matcher
        self._pattern_matcher = DomainPatternMatcher()
        self._pattern_matcher.initialize(domains=self.config.pattern_domains)

        # Register components with hot-swap manager
        self._register_components()

        self._initialized = True
        logger.info("Pipeline initialized successfully")

    def _register_components(self):
        """Register components with hot-swap manager"""
        # Register NER models
        if self._ner_registry:
            for model_id in self.config.ner_model_ids:
                # In a full implementation, would load actual models
                logger.debug(f"Registered NER model for hot-swapping: {model_id}")

        # Register KBs
        if self._kb_registry:
            for kb_id in self.config.kb_ids:
                logger.debug(f"Registered KB for hot-swapping: {kb_id}")

        # Register pattern matchers
        if self._pattern_matcher:
            for domain in self.config.pattern_domains:
                logger.debug(f"Registered pattern matcher for hot-swapping: {domain}")

    async def process(
        self,
        text: str,
        domain: Optional[str] = None,
        override_config: Optional[Dict[str, Any]] = None
    ) -> PipelineResult:
        """
        Process text through the pipeline

        Args:
            text: Input text to process
            domain: Optional domain hint (e.g., "medical", "legal")
            override_config: Optional config overrides for this request

        Returns:
            PipelineResult with extracted entities and metadata
        """
        if not self._initialized:
            raise RuntimeError("Pipeline not initialized. Call initialize() first.")

        start_time = asyncio.get_event_loop().time()

        result = PipelineResult(text=text, domain=domain)

        try:
            # Stage 1: Named Entity Recognition
            if ProcessingStage.NER in self.config.enabled_stages:
                ner_start = asyncio.get_event_loop().time()
                result.ner_entities = await self._run_ner_stage(text, domain)
                result.ner_time_ms = (asyncio.get_event_loop().time() - ner_start) * 1000
                result.stages_completed.append(ProcessingStage.NER)
                logger.debug(f"NER stage completed: {len(result.ner_entities)} entities")

            # Stage 2: Knowledge Base Enrichment
            if ProcessingStage.KB_ENRICHMENT in self.config.enabled_stages:
                kb_start = asyncio.get_event_loop().time()
                result.kb_enriched_entities = await self._run_kb_enrichment_stage(
                    result.ner_entities, domain
                )
                result.kb_time_ms = (asyncio.get_event_loop().time() - kb_start) * 1000
                result.stages_completed.append(ProcessingStage.KB_ENRICHMENT)
                logger.debug(f"KB enrichment completed: {len(result.kb_enriched_entities)} enriched")

            # Stage 3: Pattern Matching
            if ProcessingStage.PATTERN_MATCHING in self.config.enabled_stages:
                pattern_start = asyncio.get_event_loop().time()
                result.pattern_matches = await self._run_pattern_matching_stage(text, domain)
                result.pattern_time_ms = (asyncio.get_event_loop().time() - pattern_start) * 1000
                result.stages_completed.append(ProcessingStage.PATTERN_MATCHING)
                logger.debug(f"Pattern matching completed: {len(result.pattern_matches)} matches")

            # Stage 4: Post-processing
            if ProcessingStage.POST_PROCESSING in self.config.enabled_stages:
                post_start = asyncio.get_event_loop().time()
                result.entities = await self._run_post_processing_stage(
                    result.ner_entities,
                    result.kb_enriched_entities,
                    result.pattern_matches
                )
                result.post_processing_time_ms = (asyncio.get_event_loop().time() - post_start) * 1000
                result.stages_completed.append(ProcessingStage.POST_PROCESSING)
                logger.debug(f"Post-processing completed: {len(result.entities)} final entities")
            else:
                # If no post-processing, combine all entities
                result.entities = (
                    result.ner_entities +
                    result.kb_enriched_entities +
                    result.pattern_matches
                )

            result.total_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            logger.info(
                f"Pipeline completed: {len(result.entities)} entities extracted in {result.total_time_ms:.2f}ms"
            )

        except Exception as e:
            logger.error(f"Pipeline processing failed: {e}")
            result.errors.append(str(e))

        return result

    async def _run_ner_stage(
        self,
        text: str,
        domain: Optional[str]
    ) -> List[EntityResult]:
        """Run NER stage"""
        entities = []

        if not self._ner_registry:
            return entities

        # TODO: In full implementation, would:
        # 1. Select optimal models based on domain and config
        # 2. Run models (ensemble if configured)
        # 3. Convert results to EntityResult format
        # 4. Filter by confidence threshold

        # Placeholder implementation
        logger.debug(f"Running NER with models: {self.config.ner_model_ids}")

        # Simulated NER results
        # In production, would call actual models
        return entities

    async def _run_kb_enrichment_stage(
        self,
        entities: List[EntityResult],
        domain: Optional[str]
    ) -> List[EntityResult]:
        """Run knowledge base enrichment stage"""
        enriched = []

        if not self._kb_registry:
            return enriched

        # Filter entities for enrichment
        entities_to_enrich = entities
        if not self.config.kb_enrich_all:
            entities_to_enrich = [
                e for e in entities
                if e.confidence >= self.config.kb_min_confidence_for_enrichment
            ]

        logger.debug(f"Enriching {len(entities_to_enrich)} entities from {len(entities)} total")

        # TODO: In full implementation, would:
        # 1. Look up each entity in relevant KBs
        # 2. Add canonical names, definitions, relationships
        # 3. Respect concurrency limits
        # 4. Handle timeouts

        # Placeholder implementation
        for entity in entities_to_enrich:
            # Simulated KB lookup
            # In production, would call actual KB providers
            enriched_entity = EntityResult(
                text=entity.text,
                type=entity.type,
                start=entity.start,
                end=entity.end,
                confidence=entity.confidence,
                source_stage=ProcessingStage.KB_ENRICHMENT,
                source_model=entity.source_model,
                # KB enrichment would add:
                # kb_id, kb_entity_id, canonical_name, definition, etc.
            )
            enriched.append(enriched_entity)

        return enriched

    async def _run_pattern_matching_stage(
        self,
        text: str,
        domain: Optional[str]
    ) -> List[EntityResult]:
        """Run pattern matching stage"""
        entities = []

        if not self._pattern_matcher:
            return entities

        logger.debug(f"Running pattern matching for domain: {domain}")

        try:
            # Extract patterns
            if self.config.pattern_auto_detect_domain:
                matches = self._pattern_matcher.extract_with_auto_domain(
                    text,
                    min_confidence=self.config.pattern_min_confidence
                )
            elif domain:
                matches = self._pattern_matcher.extract_from_domain(
                    text,
                    domain,
                    min_confidence=self.config.pattern_min_confidence
                )
            else:
                matches = self._pattern_matcher.extract_patterns(
                    text,
                    min_confidence=self.config.pattern_min_confidence
                )

            # Convert to EntityResult format
            for match in matches:
                entity = EntityResult(
                    text=match.matched_text,
                    type=match.pattern_type.value,
                    start=match.start,
                    end=match.end,
                    confidence=match.confidence,
                    source_stage=ProcessingStage.PATTERN_MATCHING,
                    normalized_text=match.normalized_text,
                    validated=True,
                    validation_passed=match.metadata.get('validation_result', {}).get('is_valid', True),
                    metadata=match.metadata
                )
                entities.append(entity)

        except Exception as e:
            logger.error(f"Pattern matching failed: {e}")

        return entities

    async def _run_post_processing_stage(
        self,
        ner_entities: List[EntityResult],
        kb_entities: List[EntityResult],
        pattern_entities: List[EntityResult]
    ) -> List[EntityResult]:
        """Run post-processing stage"""
        # Combine all entities
        all_entities = ner_entities + kb_entities + pattern_entities

        logger.debug(f"Post-processing {len(all_entities)} entities")

        # Deduplicate
        if self.config.deduplication_enabled:
            all_entities = self._deduplicate_entities(all_entities)
            logger.debug(f"After deduplication: {len(all_entities)} entities")

        # Merge overlapping
        if self.config.merge_overlapping:
            all_entities = self._merge_overlapping_entities(all_entities)
            logger.debug(f"After merging: {len(all_entities)} entities")

        # Sort by position
        all_entities.sort(key=lambda e: e.start)

        return all_entities

    def _deduplicate_entities(
        self,
        entities: List[EntityResult]
    ) -> List[EntityResult]:
        """Remove duplicate entities"""
        if not entities:
            return entities

        # Group by text and type
        seen = set()
        unique = []

        for entity in entities:
            key = (entity.text.lower(), entity.type, entity.start, entity.end)

            if key not in seen:
                seen.add(key)
                unique.append(entity)

        return unique

    def _merge_overlapping_entities(
        self,
        entities: List[EntityResult]
    ) -> List[EntityResult]:
        """Merge overlapping entities"""
        if len(entities) <= 1:
            return entities

        # Sort by start position
        sorted_entities = sorted(entities, key=lambda e: (e.start, -e.confidence))

        merged = []
        current = sorted_entities[0]

        for next_entity in sorted_entities[1:]:
            # Check for overlap
            overlap = self._calculate_overlap(current, next_entity)

            if overlap >= self.config.deduplication_threshold:
                # Merge: keep the one with higher confidence
                if next_entity.confidence > current.confidence:
                    current = next_entity
            else:
                # No overlap, add current and move to next
                merged.append(current)
                current = next_entity

        # Add last entity
        merged.append(current)

        return merged

    def _calculate_overlap(
        self,
        entity1: EntityResult,
        entity2: EntityResult
    ) -> float:
        """Calculate IoU (Intersection over Union) overlap between entities"""
        # Calculate intersection
        intersection_start = max(entity1.start, entity2.start)
        intersection_end = min(entity1.end, entity2.end)
        intersection = max(0, intersection_end - intersection_start)

        # Calculate union
        union_start = min(entity1.start, entity2.start)
        union_end = max(entity1.end, entity2.end)
        union = union_end - union_start

        # Calculate IoU
        if union == 0:
            return 0.0

        return intersection / union

    async def update_config(self, new_config: PipelineConfig):
        """Update pipeline configuration (hot-swap)"""
        logger.info("Updating pipeline configuration")

        # Update config
        old_config = self.config
        self.config = new_config

        try:
            # Re-initialize if needed
            if new_config.pattern_domains != old_config.pattern_domains:
                self._pattern_matcher.initialize(domains=new_config.pattern_domains)

            logger.info("Pipeline configuration updated successfully")

        except Exception as e:
            logger.error(f"Failed to update configuration: {e}")
            # Rollback
            self.config = old_config
            raise

    def get_metrics(self) -> Dict[str, Any]:
        """Get pipeline metrics"""
        return {
            "hot_swap_metrics": self.hot_swap.get_metrics(),
            "active_components": self.hot_swap.list_components(),
            "pending_swaps": self.hot_swap.list_pending_swaps(),
            "config": {
                "enabled_stages": [stage.value for stage in self.config.enabled_stages],
                "ner_models": self.config.ner_model_ids,
                "kbs": self.config.kb_ids,
                "pattern_domains": self.config.pattern_domains
            }
        }

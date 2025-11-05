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
        """Run NER stage with actual model integration"""
        entities = []

        if not self._ner_registry:
            logger.warning("NER registry not initialized")
            return entities

        try:
            # 1. Discover and select optimal models for domain
            catalog = await self._ner_registry.discover_all_models(domain)

            if not catalog or not any(catalog.values()):
                logger.warning(f"No models available for domain: {domain}")
                return entities

            # Get selection criteria from config
            from ner_models.base import SelectionCriteria
            criteria = SelectionCriteria(
                min_f1_score=0.70,  # Minimum acceptable F1 score
                max_latency_ms=500,  # Maximum latency
                preferred_providers=["spacy", "huggingface"],
                entity_types=self._get_entity_types_for_domain(domain),
                languages=["en"],
                min_models=1,
                max_models=3 if self.config.ner_ensemble_mode else 1,
                require_trusted=self.config.enable_trust_validation
            )

            optimal_models = self._ner_registry.get_optimal_models(catalog, criteria)

            if not optimal_models:
                logger.warning(f"No models match criteria for domain: {domain}")
                return entities

            logger.info(f"Selected {len(optimal_models)} models for domain {domain}")

            # 2. Load models
            loaded_models = []
            for model_metadata in optimal_models:
                model = await self._ner_registry.load_model(
                    model_metadata.provider,
                    model_metadata.model_id,
                    model_metadata.version
                )
                if model:
                    loaded_models.append((model, model_metadata))
                    logger.debug(f"Loaded model: {model_metadata.model_id}")

            if not loaded_models:
                logger.error("Failed to load any models")
                return entities

            # 3. Run ensemble extraction if multiple models
            if self.config.ner_ensemble_mode and len(loaded_models) > 1:
                entities = await self._ensemble_extraction(text, loaded_models)
                logger.info(f"Ensemble extraction completed: {len(entities)} entities")
            else:
                # Single model extraction
                model, metadata = loaded_models[0]
                raw_entities = await model.extract_entities(text)
                entities = self._convert_to_entity_results(
                    raw_entities,
                    metadata,
                    ProcessingStage.NER
                )
                logger.info(f"Single model extraction: {len(entities)} entities")

            # 4. Filter by confidence threshold
            initial_count = len(entities)
            entities = [
                e for e in entities
                if e.confidence >= self.config.ner_min_confidence
            ]

            if initial_count != len(entities):
                logger.debug(
                    f"Filtered {initial_count - len(entities)} low-confidence entities "
                    f"(threshold: {self.config.ner_min_confidence})"
                )

            return entities

        except Exception as e:
            logger.error(f"NER stage failed: {e}", exc_info=True)
            return []

    async def _ensemble_extraction(
        self,
        text: str,
        models: List[Tuple[Any, Any]]  # List[(NERModel, ModelMetadata)]
    ) -> List[EntityResult]:
        """Run ensemble extraction with majority voting"""
        from collections import Counter, defaultdict

        logger.debug(f"Running ensemble extraction with {len(models)} models")

        # Extract from all models in parallel
        tasks = [
            model.extract_entities(text)
            for model, _ in models
        ]

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Ensemble extraction failed: {e}")
            return []

        # Filter out exceptions
        valid_results = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Model {models[idx][1].model_id} failed: {result}")
            else:
                valid_results.append((result, models[idx][1]))

        if not valid_results:
            logger.error("All models failed in ensemble")
            return []

        # Group entities by span (start, end)
        span_groups = defaultdict(list)

        for entities, metadata in valid_results:
            converted = self._convert_to_entity_results(
                entities,
                metadata,
                ProcessingStage.NER
            )

            for entity in converted:
                span_key = (entity.start, entity.end)
                span_groups[span_key].append(entity)

        # Voting: majority vote on entity type
        consolidated = []

        for span, entity_list in span_groups.items():
            # Count votes for each entity type
            type_votes = Counter([e.type for e in entity_list])
            winning_type, vote_count = type_votes.most_common(1)[0]

            # Calculate average confidence
            avg_confidence = sum(e.confidence for e in entity_list) / len(entity_list)

            # Boost confidence if multiple models agree
            agreement_boost = (vote_count / len(entity_list)) * 0.1
            final_confidence = min(1.0, avg_confidence + agreement_boost)

            # Use first entity for text
            entity = entity_list[0]

            # Create consolidated entity
            result = EntityResult(
                text=entity.text,
                type=winning_type,
                start=span[0],
                end=span[1],
                confidence=final_confidence,
                source_stage=ProcessingStage.NER,
                source_model=f"ensemble_{len(entity_list)}_models",
                metadata={
                    'models': [e.source_model for e in entity_list],
                    'votes': dict(type_votes),
                    'agreement_ratio': vote_count / len(entity_list)
                }
            )
            consolidated.append(result)

        logger.debug(
            f"Ensemble consolidation: {sum(len(v) for v in span_groups.values())} → "
            f"{len(consolidated)} entities"
        )

        return consolidated

    def _convert_to_entity_results(
        self,
        raw_entities: List[Any],
        metadata: Any,
        stage: ProcessingStage
    ) -> List[EntityResult]:
        """Convert model-specific entity format to EntityResult"""
        results = []

        for entity in raw_entities:
            # Handle different entity formats
            if hasattr(entity, 'text'):
                text = entity.text
            elif isinstance(entity, dict):
                text = entity.get('text', '')
            else:
                text = str(entity)

            if hasattr(entity, 'label'):
                entity_type = entity.label
            elif isinstance(entity, dict):
                entity_type = entity.get('label', 'UNKNOWN')
            else:
                entity_type = 'UNKNOWN'

            if hasattr(entity, 'start'):
                start = entity.start
            elif isinstance(entity, dict):
                start = entity.get('start', 0)
            else:
                start = 0

            if hasattr(entity, 'end'):
                end = entity.end
            elif isinstance(entity, dict):
                end = entity.get('end', len(text))
            else:
                end = len(text)

            if hasattr(entity, 'confidence'):
                confidence = entity.confidence
            elif isinstance(entity, dict):
                confidence = entity.get('confidence', 0.8)
            else:
                confidence = 0.8

            result = EntityResult(
                text=text,
                type=entity_type,
                start=start,
                end=end,
                confidence=confidence,
                source_stage=stage,
                source_model=metadata.model_id if hasattr(metadata, 'model_id') else 'unknown'
            )

            results.append(result)

        return results

    def _get_entity_types_for_domain(self, domain: Optional[str]) -> List[str]:
        """Get expected entity types for a domain"""
        if domain == "medical":
            return ["DRUG", "DISEASE", "PROCEDURE", "CHEMICAL", "ANATOMY", "SYMPTOM"]
        elif domain == "legal":
            return ["CASE_CITATION", "STATUTE", "COURT", "LEGAL_ENTITY", "LAW"]
        elif domain == "scientific":
            return ["CHEMICAL", "GENE", "PROTEIN", "SPECIES", "MEASUREMENT"]
        else:
            return ["PERSON", "ORG", "LOC", "DATE", "MONEY"]

    async def _run_kb_enrichment_stage(
        self,
        entities: List[EntityResult],
        domain: Optional[str]
    ) -> List[EntityResult]:
        """Run knowledge base enrichment stage with real KB providers"""
        if not self._kb_registry:
            logger.warning("KB registry not initialized, skipping enrichment")
            return entities

        if not entities:
            return entities

        try:
            # Filter entities for enrichment based on confidence
            entities_to_enrich = entities
            if not self.config.kb_enrich_all:
                entities_to_enrich = [
                    e for e in entities
                    if e.confidence >= self.config.kb_min_confidence_for_enrichment
                ]

            logger.debug(
                f"Enriching {len(entities_to_enrich)} entities from {len(entities)} total "
                f"(threshold: {self.config.kb_min_confidence_for_enrichment})"
            )

            if not entities_to_enrich:
                return entities

            # Get KB fallback chain for domain
            kb_chain = self._get_kb_chain_for_domain(domain)

            if not kb_chain:
                logger.debug(f"No KB chain configured for domain: {domain}")
                return entities

            logger.info(f"Using KB chain: {kb_chain}")

            # Create semaphore for concurrency control
            semaphore = asyncio.Semaphore(self.config.max_concurrent_kb_lookups)

            async def enrich_entity(entity: EntityResult) -> EntityResult:
                """Enrich a single entity with KB data"""
                async with semaphore:
                    # Try each KB in the fallback chain
                    for kb_id in kb_chain:
                        try:
                            kb_provider = self._kb_registry.get_provider(kb_id)
                            if not kb_provider:
                                logger.debug(f"KB provider not found: {kb_id}")
                                continue

                            # Lookup entity in KB
                            kb_entity = await asyncio.wait_for(
                                kb_provider.lookup_entity(entity.text, entity.type),
                                timeout=5.0  # 5 second timeout per KB lookup
                            )

                            if kb_entity:
                                # Enrich the entity with KB data
                                entity.kb_id = kb_id
                                entity.kb_entity_id = kb_entity.entity_id if hasattr(kb_entity, 'entity_id') else None
                                entity.canonical_name = kb_entity.canonical_name if hasattr(kb_entity, 'canonical_name') else None
                                entity.definition = kb_entity.definition if hasattr(kb_entity, 'definition') else None

                                if hasattr(kb_entity, 'semantic_types'):
                                    entity.semantic_types = kb_entity.semantic_types

                                # Add relationships to metadata
                                if hasattr(kb_entity, 'relationships'):
                                    if 'kb_relationships' not in entity.metadata:
                                        entity.metadata['kb_relationships'] = {}
                                    entity.metadata['kb_relationships'][kb_id] = kb_entity.relationships

                                # Add alternative names
                                if hasattr(kb_entity, 'alternative_names'):
                                    entity.metadata['alternative_names'] = kb_entity.alternative_names

                                logger.debug(
                                    f"Enriched '{entity.text}' with {kb_id}: "
                                    f"{entity.canonical_name or 'N/A'}"
                                )

                                # Successfully enriched, break fallback chain
                                break

                        except asyncio.TimeoutError:
                            logger.warning(f"KB lookup timeout for {kb_id}: {entity.text}")
                            continue

                        except Exception as e:
                            logger.warning(
                                f"KB lookup failed for {kb_id} (entity: '{entity.text}'): {e}"
                            )
                            continue

                    return entity

            # Enrich all entities in parallel (with concurrency limit)
            enriched = await asyncio.gather(*[
                enrich_entity(entity) for entity in entities_to_enrich
            ])

            # Create dictionary mapping using stable keys (not id() which can be reused)
            enriched_map = {}
            for i, entity in enumerate(entities_to_enrich):
                key = (entity.start, entity.end, entity.text.lower(), entity.type)
                enriched_map[key] = enriched[i]

            # Combine enriched and non-enriched entities
            result = []
            for entity in entities:
                key = (entity.start, entity.end, entity.text.lower(), entity.type)
                if key in enriched_map:
                    # Use the enriched version
                    result.append(enriched_map[key])
                else:
                    result.append(entity)

            # Count how many were actually enriched
            enriched_count = sum(1 for e in result if e.kb_id is not None)
            logger.info(
                f"KB enrichment completed: {enriched_count}/{len(entities_to_enrich)} entities enriched"
            )

            return result

        except Exception as e:
            logger.error(f"KB enrichment stage failed: {e}", exc_info=True)
            return entities  # Return original entities on failure

    def _get_kb_chain_for_domain(self, domain: Optional[str]) -> List[str]:
        """Get KB fallback chain for a domain"""
        if domain == "medical":
            return ["umls", "rxnorm", "snomed"]
        elif domain == "legal":
            return ["usc", "courtlistener", "cfr"]
        elif domain == "scientific":
            return ["umls", "pubchem"]
        else:
            return []

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

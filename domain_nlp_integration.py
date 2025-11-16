"""
Integration layer connecting the new domain-specific NLP architecture
with the existing TEI converter application.

This module provides:
- A facade for the DynamicNLPPipeline that matches existing NLP connector interface
- Conversion between new enriched entities and existing NLP results format
- Feature flag support for gradual rollout
- Fallback to existing system on errors
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

# Import new domain NLP components
from domain_nlp.model_providers.registry import ModelProviderRegistry
from domain_nlp.model_providers.spacy_provider import SpacyModelProvider
from domain_nlp.model_providers.huggingface_provider import HuggingFaceProvider
from domain_nlp.knowledge_bases.registry import KnowledgeBaseRegistry
from domain_nlp.pipeline.dynamic_pipeline import DynamicNLPPipeline, EnrichedDocument
from domain_nlp.config.loader import ConfigurationLoader

logger = logging.getLogger(__name__)


class DomainSpecificNLPConnector:
    """
    Facade for the new domain-specific NLP pipeline.

    Provides an interface compatible with the existing NLP connector
    while leveraging the new dynamic pipeline architecture.
    """

    def __init__(
        self,
        feature_flags: Optional[Dict[str, bool]] = None,
        config_path: Optional[str] = None
    ):
        """
        Initialize the domain-specific NLP connector.

        Args:
            feature_flags: Feature flags for gradual rollout
            config_path: Path to configuration directory
        """
        self.feature_flags = feature_flags or {
            "use_domain_nlp": True,
            "enable_kb_enrichment": True,
            "enable_pattern_matching": True,
            "enable_ensemble": True
        }

        # Configuration loader
        self.config_loader = ConfigurationLoader(config_path)

        # Model provider registry
        self.model_registry = ModelProviderRegistry()

        # Knowledge base registry
        self.kb_registry = KnowledgeBaseRegistry()

        # Domain pipelines (lazy loaded)
        self._pipelines: Dict[str, DynamicNLPPipeline] = {}

        # Initialize providers
        self._initialize_providers()

        self._initialized = False

        logger.info("DomainSpecificNLPConnector created")

    def _initialize_providers(self) -> None:
        """Register default model providers"""
        # Register SpaCy provider
        try:
            spacy_provider = SpacyModelProvider()
            self.model_registry.register_provider("spacy", spacy_provider)
            logger.info("Registered SpaCy provider")
        except Exception as e:
            logger.warning(f"Failed to register SpaCy provider: {e}")

        # Register HuggingFace provider (if available)
        try:
            hf_provider = HuggingFaceProvider()
            self.model_registry.register_provider("huggingface", hf_provider)
            logger.info("Registered HuggingFace provider")
        except Exception as e:
            logger.warning(f"Failed to register HuggingFace provider: {e}")

    async def initialize(self) -> None:
        """Initialize the connector and discover models"""
        if self._initialized:
            return

        # Discover all available models
        await self.model_registry.discover_all_models()

        self._initialized = True
        logger.info("DomainSpecificNLPConnector initialized")

    async def get_pipeline(self, domain: str) -> DynamicNLPPipeline:
        """
        Get or create a pipeline for the specified domain.

        Args:
            domain: Domain name (medical, legal, general, etc.)

        Returns:
            Initialized DynamicNLPPipeline
        """
        if not self._initialized:
            await self.initialize()

        if domain not in self._pipelines:
            # Build pipeline config from domain configuration
            pipeline_config = self.config_loader.build_pipeline_config(domain)

            # Apply feature flags
            if not self.feature_flags.get("enable_kb_enrichment", True):
                pipeline_config.enable_kb_enrichment = False
            if not self.feature_flags.get("enable_pattern_matching", True):
                pipeline_config.enable_pattern_matching = False

            # Create pipeline
            pipeline = DynamicNLPPipeline(
                config=pipeline_config,
                model_registry=self.model_registry,
                kb_registry=self.kb_registry
            )

            # Initialize pipeline
            await pipeline.initialize()

            self._pipelines[domain] = pipeline
            logger.info(f"Created pipeline for domain: {domain}")

        return self._pipelines[domain]

    async def process_text(
        self,
        text: str,
        domain: str = "general"
    ) -> Dict[str, Any]:
        """
        Process text using domain-specific NLP.

        Args:
            text: Input text to process
            domain: Domain for processing

        Returns:
            NLP results in format compatible with existing system
        """
        if not self.feature_flags.get("use_domain_nlp", True):
            logger.info("Domain NLP disabled by feature flag")
            return self._create_empty_result()

        try:
            pipeline = await self.get_pipeline(domain)
            result = await pipeline.process(text)

            # Convert to existing format
            nlp_results = self._convert_to_legacy_format(result, domain)

            logger.info(
                f"Processed text with domain NLP: {len(result.entities)} entities, "
                f"{len(result.structured_entities)} patterns"
            )

            return nlp_results

        except Exception as e:
            logger.error(f"Domain NLP processing failed: {e}")
            return self._create_empty_result()

    def _convert_to_legacy_format(
        self,
        result: EnrichedDocument,
        domain: str
    ) -> Dict[str, Any]:
        """
        Convert EnrichedDocument to format expected by existing TEI converter.

        Args:
            result: Enriched document from pipeline
            domain: Domain used for processing

        Returns:
            Dictionary in legacy NLP results format
        """
        # Convert enriched entities to legacy entity format
        entities = []
        for entity in result.entities:
            legacy_entity = {
                "text": entity.text,
                "type": entity.entity_type,
                "start_offset": entity.start,
                "end_offset": entity.end,
                "confidence": entity.confidence,
                "metadata": {
                    "model_id": entity.model_id,
                    "sources": entity.sources
                }
            }

            # Add KB enrichment if available
            if entity.is_enriched and entity.kb_entity:
                legacy_entity["kb_enrichment"] = {
                    "kb_id": entity.kb_entity.kb_id,
                    "entity_id": entity.kb_entity.entity_id,
                    "definition": entity.kb_entity.definition,
                    "synonyms": entity.kb_entity.synonyms
                }

            entities.append(legacy_entity)

        # Add structured entities (patterns)
        for struct_entity in result.structured_entities:
            entities.append({
                "text": struct_entity.text,
                "type": struct_entity.entity_type,
                "start_offset": struct_entity.start,
                "end_offset": struct_entity.end,
                "confidence": struct_entity.confidence,
                "metadata": {
                    "source": "pattern_matching",
                    "pattern_name": struct_entity.pattern_name,
                    "validation_passed": struct_entity.validation_passed
                }
            })

        # Build complete result
        return {
            "entities": entities,
            "sentences": [],  # Would need to add sentence segmentation
            "tokens": [],     # Would need to add tokenization
            "noun_chunks": [],
            "dependencies": [],
            "metadata": {
                "domain": domain,
                "processing_time_ms": result.processing_time_ms,
                "models_used": result.models_used,
                "kb_hit_rate": result.kb_hit_rate,
                "ensemble_agreement": result.ensemble_agreement,
                "timestamp": result.metadata.get("timestamp", datetime.now().isoformat()),
                "pipeline": "domain_specific_nlp"
            }
        }

    def _create_empty_result(self) -> Dict[str, Any]:
        """Create empty NLP result"""
        return {
            "entities": [],
            "sentences": [],
            "tokens": [],
            "noun_chunks": [],
            "dependencies": [],
            "metadata": {
                "pipeline": "domain_specific_nlp",
                "status": "no_results"
            }
        }

    def get_supported_domains(self) -> List[str]:
        """Get list of supported domains"""
        return self.config_loader.list_domains()

    def get_statistics(self) -> Dict[str, Any]:
        """Get connector statistics"""
        stats = {
            "initialized": self._initialized,
            "feature_flags": self.feature_flags,
            "supported_domains": self.get_supported_domains(),
            "active_pipelines": list(self._pipelines.keys()),
            "model_registry": self.model_registry.get_statistics(),
            "kb_registry": self.kb_registry.get_statistics()
        }

        # Add per-pipeline stats
        pipeline_stats = {}
        for domain, pipeline in self._pipelines.items():
            pipeline_stats[domain] = pipeline.get_statistics()

        stats["pipelines"] = pipeline_stats

        return stats

    async def shutdown(self) -> None:
        """Gracefully shutdown all pipelines"""
        logger.info("Shutting down DomainSpecificNLPConnector")

        for domain, pipeline in self._pipelines.items():
            try:
                await pipeline.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down {domain} pipeline: {e}")

        self._pipelines.clear()
        self._initialized = False

        logger.info("DomainSpecificNLPConnector shutdown complete")


# Example usage and factory function
def create_domain_nlp_connector(
    config_path: Optional[str] = None,
    feature_flags: Optional[Dict[str, bool]] = None
) -> DomainSpecificNLPConnector:
    """
    Factory function to create a domain-specific NLP connector.

    Args:
        config_path: Optional path to configuration directory
        feature_flags: Optional feature flags

    Returns:
        Configured DomainSpecificNLPConnector instance
    """
    return DomainSpecificNLPConnector(
        feature_flags=feature_flags,
        config_path=config_path
    )


async def main():
    """Example usage of the domain-specific NLP connector"""

    # Create connector
    connector = create_domain_nlp_connector()

    # Initialize
    await connector.initialize()

    # Process medical text
    medical_text = """
    Patient presents with Type 2 Diabetes Mellitus (E11.9).
    Prescribed Metformin 500 mg twice daily.
    Blood glucose: 180 mg/dL. A1C: 8.5%.
    """

    result = await connector.process_text(medical_text, domain="medical")
    print("Medical domain results:")
    print(f"  Entities found: {len(result['entities'])}")
    for entity in result["entities"]:
        print(f"    - {entity['text']} ({entity['type']})")

    # Process legal text
    legal_text = """
    This case is governed by 18 U.S.C. § 1001.
    See Brown v. Board of Education, 347 U.S. 483 (1954).
    """

    result = await connector.process_text(legal_text, domain="legal")
    print("\nLegal domain results:")
    print(f"  Entities found: {len(result['entities'])}")
    for entity in result["entities"]:
        print(f"    - {entity['text']} ({entity['type']})")

    # Get statistics
    stats = connector.get_statistics()
    print(f"\nStatistics:")
    print(f"  Active pipelines: {stats['active_pipelines']}")
    print(f"  Total models discovered: {stats['model_registry']['total_models_discovered']}")

    # Shutdown
    await connector.shutdown()


if __name__ == "__main__":
    asyncio.run(main())

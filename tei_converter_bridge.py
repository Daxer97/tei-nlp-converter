"""
TEI Converter Bridge - Backward-compatible integration layer

This module provides seamless integration between:
- The OLD TEIConverter (schema-based, hardcoded mappings)
- The NEW DynamicTEIGenerator (config-driven, Universal Annotation Model)

Usage:
    # Drop-in replacement for TEIConverter
    converter = UnifiedTEIConverter(schema)
    tei_xml = converter.convert(text, nlp_results)

The bridge:
1. Automatically detects if input is old-style NLP results or new AnnotationDocument
2. Converts between formats as needed
3. Uses the new flexible system when enabled, falls back to old system otherwise
4. Provides migration utilities
"""

from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
import json

from annotation_model import (
    AnnotationDocument, Annotation, AnnotationLayer,
    AnnotationType, Target, TargetType, Provenance, FeatureBundle
)
from dynamic_tei_mapper import (
    DynamicTEIGenerator, MappingProfileRegistry, MappingProfile
)
from tei_converter import TEIConverter
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class ConverterConfig:
    """Configuration for the unified converter"""
    use_dynamic_mapper: bool = True      # Use new system or legacy
    profile_id: str = "universal"         # Mapping profile to use
    fallback_to_legacy: bool = True       # Fallback on errors
    preserve_legacy_format: bool = False  # Output legacy format even with new system
    migration_mode: bool = False          # Enable migration utilities


class NLPResultsConverter:
    """
    Converts old-style NLP results to AnnotationDocument.
    This enables the new dynamic mapper to work with existing NLP pipelines.
    """

    @staticmethod
    def to_annotation_document(text: str, nlp_results: Dict[str, Any],
                               model_info: Optional[Dict[str, str]] = None) -> AnnotationDocument:
        """
        Convert legacy NLP results format to AnnotationDocument.

        Args:
            text: Original text
            nlp_results: Legacy format NLP results
            model_info: Optional model metadata

        Returns:
            AnnotationDocument ready for dynamic TEI generation
        """
        # Use the built-in factory method
        return AnnotationDocument.from_nlp_results(text, nlp_results, model_info)

    @staticmethod
    def from_annotation_document(doc: AnnotationDocument) -> Dict[str, Any]:
        """
        Convert AnnotationDocument back to legacy NLP results format.
        Useful for compatibility with old systems.

        Args:
            doc: AnnotationDocument

        Returns:
            Legacy format NLP results dict
        """
        # Reconstruct sentences from token annotations
        sentences = []
        tokens = []

        token_layer = doc.get_layer(AnnotationType.TOKEN.value)
        if token_layer:
            for ann in sorted(token_layer.annotations,
                            key=lambda a: a.targets[0].start if a.targets else 0):
                token_data = {
                    "i": int(ann.id.split("_")[-1]) if "_" in ann.id else 0,
                    "text": ann.text or "",
                    "lemma": ann.body.get("lemma", ann.text),
                    "pos": ann.body.get("pos", "X"),
                    "tag": ann.body.get("tag", ""),
                    "dep": ann.body.get("dep", ""),
                    "is_punct": ann.body.get("is_punct", False),
                    "is_space": ann.body.get("is_space", False),
                    "idx": ann.targets[0].start if ann.targets else 0
                }
                tokens.append(token_data)

        # Group tokens into sentences (simplified - assumes one sentence)
        if tokens:
            sentences = [{
                "text": doc.text,
                "tokens": tokens
            }]

        # Convert entities
        entities = []
        entity_layer = doc.get_layer(AnnotationType.ENTITY.value)
        if entity_layer:
            for ann in entity_layer.annotations:
                entity_data = {
                    "text": ann.text or "",
                    "label": ann.category or ann.label or "UNKNOWN",
                    "start": ann.targets[0].start if ann.targets else 0,
                    "end": ann.targets[0].end if ann.targets else 0,
                    "start_char": ann.targets[0].start if ann.targets else 0,
                    "end_char": ann.targets[0].end if ann.targets else 0,
                    "confidence": ann.certainty
                }
                if ann.kb_ref:
                    entity_data["kb_id"] = ann.kb_ref
                if ann.kb_data:
                    entity_data.update(ann.kb_data)
                entities.append(entity_data)

        # Convert dependencies
        dependencies = []
        dep_layer = doc.get_layer(AnnotationType.DEPENDENCY.value)
        if dep_layer:
            for ann in dep_layer.annotations:
                if len(ann.targets) >= 2:
                    dep_data = {
                        "dep": ann.label or ann.body.get("relation", "dep"),
                        "from": ann.targets[0].start,
                        "to": ann.targets[1].start,
                        "from_text": ann.body.get("child_text", ""),
                        "to_text": ann.body.get("head_text", "")
                    }
                    dependencies.append(dep_data)

        return {
            "sentences": sentences,
            "entities": entities,
            "dependencies": dependencies,
            "language": doc.metadata.get("language", "en"),
            "metadata": doc.metadata
        }


class UnifiedTEIConverter:
    """
    Unified TEI Converter that bridges old and new systems.

    This is a drop-in replacement for TEIConverter that:
    - Works with both old NLP results and new AnnotationDocuments
    - Uses the dynamic mapper when enabled
    - Falls back to legacy converter when needed
    - Provides migration utilities
    """

    def __init__(self, schema: Dict[str, Any],
                 config: Optional[ConverterConfig] = None,
                 profiles_dir: Optional[str] = None):
        """
        Initialize unified converter.

        Args:
            schema: Domain schema (for legacy compatibility)
            config: Converter configuration
            profiles_dir: Directory for custom mapping profiles
        """
        self.schema = schema
        self.config = config or ConverterConfig()

        # Initialize legacy converter
        self.legacy_converter = TEIConverter(schema)

        # Initialize new dynamic system
        self.profile_registry = MappingProfileRegistry(profiles_dir)
        self._init_dynamic_mapper()

    def _init_dynamic_mapper(self):
        """Initialize the dynamic mapper with appropriate profile"""
        # Try to map domain to profile
        domain = self.schema.get("domain", "default")
        profile_id = self._domain_to_profile(domain)

        profile = self.profile_registry.get_profile(profile_id)
        self.dynamic_mapper = DynamicTEIGenerator(profile)

    def _domain_to_profile(self, domain: str) -> str:
        """Map legacy domain to mapping profile"""
        domain_profile_map = {
            "default": "universal",
            "literary": "universal",
            "historical": "universal",
            "legal": "legal",
            "scientific": "universal",
            "medical": "medical",
            "linguistic": "universal",
            "classical": "classical"
        }
        return domain_profile_map.get(domain, "universal")

    def convert(self, text: str,
                nlp_results: Union[Dict[str, Any], AnnotationDocument],
                metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Convert NLP results to TEI XML.

        This method automatically handles both:
        - Old-style Dict NLP results
        - New AnnotationDocument objects

        Args:
            text: Original text (used if nlp_results is Dict)
            nlp_results: NLP results in either format
            metadata: Additional metadata

        Returns:
            TEI XML string
        """
        if not self.config.use_dynamic_mapper:
            # Use legacy converter
            if isinstance(nlp_results, AnnotationDocument):
                nlp_results = NLPResultsConverter.from_annotation_document(nlp_results)
            return self.legacy_converter.convert(text, nlp_results)

        try:
            # Convert to AnnotationDocument if needed
            if isinstance(nlp_results, dict):
                doc = NLPResultsConverter.to_annotation_document(
                    text, nlp_results,
                    model_info=nlp_results.get("metadata", {})
                )
            else:
                doc = nlp_results

            # Generate TEI with dynamic mapper
            combined_metadata = {
                "title": self.schema.get("title", "Annotated Text"),
                "domain": self.schema.get("domain", "default"),
                **(metadata or {})
            }

            return self.dynamic_mapper.generate(doc, combined_metadata)

        except Exception as e:
            logger.error(f"Dynamic mapper failed: {e}")

            if self.config.fallback_to_legacy:
                logger.info("Falling back to legacy converter")
                if isinstance(nlp_results, AnnotationDocument):
                    nlp_results = NLPResultsConverter.from_annotation_document(nlp_results)
                return self.legacy_converter.convert(text, nlp_results)
            else:
                raise

    def set_profile(self, profile_id: str) -> None:
        """Change the mapping profile"""
        profile = self.profile_registry.get_profile(profile_id)
        self.dynamic_mapper = DynamicTEIGenerator(profile)

    def get_available_profiles(self) -> List[str]:
        """Get list of available mapping profiles"""
        return self.profile_registry.list_profiles()


class SchemaToProfileConverter:
    """
    Utility to convert old-style domain schemas to new mapping profiles.
    Helps migrate existing configurations to the new system.
    """

    @staticmethod
    def convert_schema_to_profile(schema: Dict[str, Any]) -> MappingProfile:
        """
        Convert a legacy OntologyManager schema to a MappingProfile.

        Args:
            schema: Legacy schema dict

        Returns:
            Equivalent MappingProfile
        """
        from dynamic_tei_mapper import MappingRule, RenderStrategy

        rules = []

        # Convert entity mappings
        entity_mappings = schema.get("entity_mappings", {})
        for entity_type, tei_element in entity_mappings.items():
            if entity_type == "DEFAULT":
                # Add as low-priority catch-all
                rules.append(MappingRule(
                    annotation_type="entity",
                    tei_element=tei_element,
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={"category": "type"},
                    priority=0
                ))
            else:
                rules.append(MappingRule(
                    annotation_type="entity",
                    category_pattern=f"^{entity_type}$",
                    tei_element=tei_element,
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={"kb_ref": "ref", "certainty": "cert"},
                    priority=10
                ))

        # Add token rule based on schema settings
        include_features = []
        if schema.get("include_morph", False):
            include_features.append("morph")
        if schema.get("include_dep", False):
            include_features.append("dep")

        token_attrs = {}
        if schema.get("include_lemma", True):
            token_attrs["lemma"] = "lemma"
        if schema.get("include_pos", True):
            token_attrs["pos"] = "pos"

        rules.append(MappingRule(
            annotation_type="token",
            tei_element="w",
            render_strategy=RenderStrategy.INLINE,
            attribute_map=token_attrs,
            include_features=include_features,
            priority=5
        ))

        # Add dependency rule if enabled
        if schema.get("include_dependencies", False):
            rules.append(MappingRule(
                annotation_type="dependency",
                tei_element="link",
                render_strategy=RenderStrategy.STANDOFF,
                attribute_map={"label": "type"},
                priority=5
            ))

        # Determine default render strategy
        strategy_str = schema.get("annotation_strategy", "inline")
        default_strategy = RenderStrategy(strategy_str)

        return MappingProfile(
            profile_id=f"migrated_{schema.get('domain', 'default')}",
            name=schema.get("title", "Migrated Profile"),
            description=f"Auto-migrated from legacy schema: {schema.get('domain', 'default')}",
            rules=rules,
            default_render_strategy=default_strategy,
            include_provenance=True,
            include_certainty=True,
            use_feature_structures=schema.get("include_analysis", False)
        )

    @staticmethod
    def migrate_all_schemas(ontology_manager, output_dir: str) -> Dict[str, str]:
        """
        Migrate all schemas from OntologyManager to YAML profiles.

        Args:
            ontology_manager: OntologyManager instance
            output_dir: Directory to write YAML files

        Returns:
            Dict mapping domain names to output file paths
        """
        from pathlib import Path

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        results = {}

        for domain in ontology_manager.get_available_domains():
            schema = ontology_manager.get_schema(domain)
            profile = SchemaToProfileConverter.convert_schema_to_profile(schema)

            yaml_path = output_path / f"{domain}.yaml"
            profile.to_yaml(str(yaml_path))

            results[domain] = str(yaml_path)
            logger.info(f"Migrated schema '{domain}' to {yaml_path}")

        return results


def create_converter(schema: Dict[str, Any],
                    use_dynamic: bool = True,
                    profile_id: Optional[str] = None,
                    profiles_dir: Optional[str] = None) -> UnifiedTEIConverter:
    """
    Factory function to create a properly configured converter.

    Args:
        schema: Domain schema
        use_dynamic: Whether to use new dynamic system
        profile_id: Specific profile to use (overrides auto-detection)
        profiles_dir: Directory for custom profiles

    Returns:
        Configured UnifiedTEIConverter
    """
    config = ConverterConfig(
        use_dynamic_mapper=use_dynamic,
        profile_id=profile_id or "universal",
        fallback_to_legacy=True
    )

    converter = UnifiedTEIConverter(schema, config, profiles_dir)

    if profile_id:
        converter.set_profile(profile_id)

    return converter

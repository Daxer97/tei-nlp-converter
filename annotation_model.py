"""
Universal Annotation Model (UAM) - Model-agnostic annotation representation

This module provides a flexible, standards-based annotation layer that decouples
NLP model outputs from TEI structure. Based on W3C Web Annotation Data Model
with extensions for linguistic annotations.

Key benefits:
- Any NLP model output can be represented without loss
- No schema changes needed for new annotation types
- Supports uncertainty, provenance, and multi-model scenarios
- Clean separation between annotation storage and TEI rendering
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Union
from enum import Enum, auto
from datetime import datetime
import uuid
import json
from abc import ABC, abstractmethod


class AnnotationType(Enum):
    """Extensible annotation type registry"""
    # Core linguistic types
    TOKEN = "token"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"

    # Named entities
    ENTITY = "entity"

    # Syntactic
    DEPENDENCY = "dependency"
    CONSTITUENT = "constituent"

    # Semantic
    COREFERENCE = "coreference"
    SEMANTIC_ROLE = "semantic_role"
    WORD_SENSE = "word_sense"

    # Discourse
    DISCOURSE_RELATION = "discourse_relation"
    TOPIC = "topic"

    # Domain-specific
    BOTANICAL = "botanical"
    MEDICAL = "medical"
    LEGAL = "legal"

    # Custom (for extensibility)
    CUSTOM = "custom"


class TargetType(Enum):
    """Types of annotation targets"""
    CHARACTER_OFFSET = "char"      # Character-based offset
    TOKEN_OFFSET = "token"         # Token-based offset
    XPATH = "xpath"                # XPath expression
    ELEMENT_REF = "element"        # Element ID reference
    MULTI_TARGET = "multi"         # Multiple targets (for relations)


@dataclass
class Target:
    """
    Annotation target specification (what the annotation refers to).
    Supports multiple addressing schemes for flexibility.
    """
    target_type: TargetType
    start: Union[int, str]
    end: Optional[Union[int, str]] = None
    selector: Optional[str] = None  # For complex selections

    def to_tei_target(self) -> str:
        """Convert to TEI-compatible target string"""
        if self.target_type == TargetType.CHARACTER_OFFSET:
            return f"#char({self.start},{self.end})"
        elif self.target_type == TargetType.TOKEN_OFFSET:
            return f"#w{self.start}" if self.end is None else f"#w{self.start} #w{self.end}"
        elif self.target_type == TargetType.ELEMENT_REF:
            return f"#{self.start}"
        return str(self.start)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.target_type.value,
            "start": self.start,
            "end": self.end,
            "selector": self.selector
        }


@dataclass
class Provenance:
    """
    Tracks the source and creation of annotations.
    Essential for multi-model scenarios and reproducibility.
    """
    agent_id: str                           # Model or system ID
    agent_type: str                         # "nlp_model", "human", "rule"
    model_name: Optional[str] = None        # e.g., "en_core_web_lg"
    model_version: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    confidence: Optional[float] = None      # Model confidence [0,1]
    method: Optional[str] = None            # Processing method used

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "created_at": self.created_at.isoformat(),
            "confidence": self.confidence,
            "method": self.method
        }


@dataclass
class FeatureBundle:
    """
    Flexible feature-value container for annotation attributes.
    Maps directly to TEI <fs> (feature structure) elements.
    """
    features: Dict[str, Any] = field(default_factory=dict)

    def set(self, name: str, value: Any) -> 'FeatureBundle':
        self.features[name] = value
        return self

    def get(self, name: str, default: Any = None) -> Any:
        return self.features.get(name, default)

    def has(self, name: str) -> bool:
        return name in self.features

    def to_tei_fs(self) -> Dict[str, Any]:
        """Convert to TEI feature structure format"""
        return {
            "type": "fs",
            "features": [
                {"name": k, "value": v, "value_type": self._infer_type(v)}
                for k, v in self.features.items()
            ]
        }

    def _infer_type(self, value: Any) -> str:
        """Infer TEI feature value type"""
        if isinstance(value, bool):
            return "binary"
        elif isinstance(value, (int, float)):
            return "numeric"
        elif isinstance(value, str):
            return "symbol" if value.isupper() else "string"
        elif isinstance(value, list):
            return "vColl"
        return "string"

    def to_dict(self) -> Dict[str, Any]:
        return self.features.copy()


@dataclass
class Annotation:
    """
    Universal annotation representation.

    This is the core data structure that represents ANY annotation type.
    It's designed to:
    - Capture all information from NLP models without loss
    - Support multiple addressing schemes
    - Track provenance and uncertainty
    - Enable flexible TEI rendering
    """
    id: str
    annotation_type: AnnotationType
    targets: List[Target]
    body: FeatureBundle
    provenance: Provenance

    # Optional metadata
    label: Optional[str] = None             # Human-readable label
    category: Optional[str] = None          # Subcategory (e.g., "PERSON" for entity)
    text: Optional[str] = None              # Covered text
    certainty: Optional[float] = None       # Combined certainty

    # Relations to other annotations
    related_to: List[str] = field(default_factory=list)  # Annotation IDs
    part_of: Optional[str] = None           # Parent annotation ID

    # Knowledge base linking
    kb_ref: Optional[str] = None            # External KB reference
    kb_data: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if not self.id:
            self.id = f"ann_{uuid.uuid4().hex[:8]}"

    @classmethod
    def from_nlp_entity(cls, entity: Dict[str, Any], provenance: Provenance) -> 'Annotation':
        """Factory method to create annotation from NLP entity output"""
        features = FeatureBundle()
        features.set("label", entity.get("label", "UNKNOWN"))

        if "lemma" in entity:
            features.set("lemma", entity["lemma"])
        if "confidence" in entity:
            features.set("confidence", entity["confidence"])

        # Handle KB enrichment data
        kb_data = None
        kb_ref = entity.get("kb_id")
        if kb_ref or entity.get("kb_data"):
            kb_data = {
                "kb_id": kb_ref,
                "definition": entity.get("definition"),
                "synonyms": entity.get("synonyms", []),
                "source": entity.get("kb_source")
            }

        return cls(
            id=f"ent_{entity.get('start', 0)}_{entity.get('end', 0)}",
            annotation_type=AnnotationType.ENTITY,
            targets=[Target(
                target_type=TargetType.CHARACTER_OFFSET,
                start=entity.get("start_char", entity.get("start", 0)),
                end=entity.get("end_char", entity.get("end", 0))
            )],
            body=features,
            provenance=provenance,
            label=entity.get("label"),
            category=entity.get("label"),
            text=entity.get("text"),
            certainty=entity.get("confidence"),
            kb_ref=kb_ref,
            kb_data=kb_data
        )

    @classmethod
    def from_nlp_token(cls, token: Dict[str, Any], provenance: Provenance) -> 'Annotation':
        """Factory method to create annotation from NLP token output"""
        features = FeatureBundle()

        # Core token features
        if "lemma" in token:
            features.set("lemma", token["lemma"])
        if "pos" in token:
            features.set("pos", token["pos"])
        if "tag" in token:
            features.set("tag", token["tag"])
        if "dep" in token:
            features.set("dep", token["dep"])
        if "morph" in token:
            features.set("morph", token["morph"])

        # Boolean flags
        for flag in ["is_punct", "is_space", "is_stop", "is_alpha"]:
            if flag in token:
                features.set(flag, token[flag])

        return cls(
            id=f"tok_{token.get('i', 0)}",
            annotation_type=AnnotationType.TOKEN,
            targets=[Target(
                target_type=TargetType.CHARACTER_OFFSET,
                start=token.get("idx", 0),
                end=token.get("idx", 0) + len(token.get("text", ""))
            )],
            body=features,
            provenance=provenance,
            text=token.get("text"),
            category="TOKEN"
        )

    @classmethod
    def from_nlp_dependency(cls, dep: Dict[str, Any], provenance: Provenance) -> 'Annotation':
        """Factory method to create annotation from NLP dependency"""
        features = FeatureBundle()
        features.set("relation", dep.get("dep"))
        features.set("head_text", dep.get("to_text"))
        features.set("child_text", dep.get("from_text"))

        return cls(
            id=f"dep_{dep.get('from', 0)}_{dep.get('to', 0)}",
            annotation_type=AnnotationType.DEPENDENCY,
            targets=[
                Target(TargetType.TOKEN_OFFSET, start=dep.get("from", 0)),
                Target(TargetType.TOKEN_OFFSET, start=dep.get("to", 0))
            ],
            body=features,
            provenance=provenance,
            label=dep.get("dep"),
            category="DEPENDENCY"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON export"""
        return {
            "id": self.id,
            "type": self.annotation_type.value,
            "targets": [t.to_dict() for t in self.targets],
            "body": self.body.to_dict(),
            "provenance": self.provenance.to_dict(),
            "label": self.label,
            "category": self.category,
            "text": self.text,
            "certainty": self.certainty,
            "related_to": self.related_to,
            "part_of": self.part_of,
            "kb_ref": self.kb_ref,
            "kb_data": self.kb_data
        }


@dataclass
class AnnotationLayer:
    """
    A collection of related annotations of the same type.
    Enables efficient querying and grouping.
    """
    layer_id: str
    annotation_type: AnnotationType
    annotations: List[Annotation] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add(self, annotation: Annotation) -> None:
        self.annotations.append(annotation)

    def get_by_id(self, ann_id: str) -> Optional[Annotation]:
        return next((a for a in self.annotations if a.id == ann_id), None)

    def get_by_span(self, start: int, end: int) -> List[Annotation]:
        """Get annotations overlapping with character span"""
        results = []
        for ann in self.annotations:
            for target in ann.targets:
                if target.target_type == TargetType.CHARACTER_OFFSET:
                    if target.start < end and target.end > start:
                        results.append(ann)
                        break
        return results

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "type": self.annotation_type.value,
            "count": len(self.annotations),
            "annotations": [a.to_dict() for a in self.annotations],
            "metadata": self.metadata
        }


@dataclass
class AnnotationDocument:
    """
    Complete annotation document containing all layers.
    This is the top-level container that holds:
    - Original text
    - All annotation layers
    - Document-level metadata
    - Provenance chain
    """
    document_id: str
    text: str
    layers: Dict[str, AnnotationLayer] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance_chain: List[Provenance] = field(default_factory=list)

    def __post_init__(self):
        if not self.document_id:
            self.document_id = f"doc_{uuid.uuid4().hex[:8]}"

    def add_layer(self, layer: AnnotationLayer) -> None:
        self.layers[layer.layer_id] = layer

    def get_layer(self, layer_id: str) -> Optional[AnnotationLayer]:
        return self.layers.get(layer_id)

    def get_or_create_layer(self, layer_id: str, annotation_type: AnnotationType) -> AnnotationLayer:
        if layer_id not in self.layers:
            self.layers[layer_id] = AnnotationLayer(layer_id, annotation_type)
        return self.layers[layer_id]

    def add_annotation(self, annotation: Annotation, layer_id: Optional[str] = None) -> None:
        """Add annotation to appropriate layer"""
        if layer_id is None:
            layer_id = annotation.annotation_type.value

        layer = self.get_or_create_layer(layer_id, annotation.annotation_type)
        layer.add(annotation)

    def get_all_annotations(self) -> List[Annotation]:
        """Get all annotations across all layers"""
        all_annotations = []
        for layer in self.layers.values():
            all_annotations.extend(layer.annotations)
        return all_annotations

    def get_annotations_at(self, char_offset: int) -> List[Annotation]:
        """Get all annotations at a character position"""
        results = []
        for layer in self.layers.values():
            for ann in layer.annotations:
                for target in ann.targets:
                    if target.target_type == TargetType.CHARACTER_OFFSET:
                        if target.start <= char_offset < target.end:
                            results.append(ann)
                            break
        return results

    def get_entity_annotations(self) -> List[Annotation]:
        """Get all entity annotations"""
        entity_layer = self.get_layer(AnnotationType.ENTITY.value)
        return entity_layer.annotations if entity_layer else []

    @classmethod
    def from_nlp_results(cls, text: str, nlp_results: Dict[str, Any],
                         model_info: Optional[Dict[str, str]] = None) -> 'AnnotationDocument':
        """
        Factory method to create AnnotationDocument from standard NLP results.
        This is the main entry point for converting NLP output to UAM.
        """
        doc = cls(
            document_id=f"doc_{uuid.uuid4().hex[:8]}",
            text=text,
            metadata={
                "language": nlp_results.get("language", "en"),
                "source": "nlp_processing",
                "created_at": datetime.now().isoformat()
            }
        )

        # Create provenance from model info
        provenance = Provenance(
            agent_id=model_info.get("model_id", "unknown") if model_info else "unknown",
            agent_type="nlp_model",
            model_name=model_info.get("model_name") if model_info else None,
            model_version=model_info.get("model_version") if model_info else None
        )
        doc.provenance_chain.append(provenance)

        # Process entities
        for entity in nlp_results.get("entities", []):
            ann = Annotation.from_nlp_entity(entity, provenance)
            doc.add_annotation(ann, AnnotationType.ENTITY.value)

        # Process tokens
        for sentence in nlp_results.get("sentences", []):
            for token in sentence.get("tokens", []):
                ann = Annotation.from_nlp_token(token, provenance)
                doc.add_annotation(ann, AnnotationType.TOKEN.value)

        # Process dependencies
        for dep in nlp_results.get("dependencies", []):
            ann = Annotation.from_nlp_dependency(dep, provenance)
            doc.add_annotation(ann, AnnotationType.DEPENDENCY.value)

        return doc

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "text_length": len(self.text),
            "layers": {k: v.to_dict() for k, v in self.layers.items()},
            "metadata": self.metadata,
            "provenance_chain": [p.to_dict() for p in self.provenance_chain]
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class AnnotationMerger:
    """
    Merges annotations from multiple models/sources.
    Handles conflicts, voting, and confidence aggregation.
    """

    @staticmethod
    def merge_documents(docs: List[AnnotationDocument],
                       strategy: str = "union") -> AnnotationDocument:
        """
        Merge multiple annotation documents into one.

        Strategies:
        - union: Keep all annotations from all sources
        - intersection: Keep only annotations agreed upon by all sources
        - majority: Keep annotations agreed upon by majority
        - highest_confidence: Keep highest confidence annotation for conflicts
        """
        if not docs:
            raise ValueError("No documents to merge")

        # Use first document as base
        merged = AnnotationDocument(
            document_id=f"merged_{uuid.uuid4().hex[:8]}",
            text=docs[0].text,
            metadata={
                "merged_from": [d.document_id for d in docs],
                "merge_strategy": strategy
            }
        )

        # Collect provenance from all sources
        for doc in docs:
            merged.provenance_chain.extend(doc.provenance_chain)

        if strategy == "union":
            # Simply add all annotations
            for doc in docs:
                for ann in doc.get_all_annotations():
                    merged.add_annotation(ann)

        elif strategy == "highest_confidence":
            # Group annotations by span and keep highest confidence
            span_annotations: Dict[str, List[Annotation]] = {}

            for doc in docs:
                for ann in doc.get_all_annotations():
                    if ann.targets:
                        span_key = f"{ann.targets[0].start}_{ann.targets[0].end}_{ann.annotation_type.value}"
                        if span_key not in span_annotations:
                            span_annotations[span_key] = []
                        span_annotations[span_key].append(ann)

            for span_key, annotations in span_annotations.items():
                best = max(annotations, key=lambda a: a.certainty or 0)
                merged.add_annotation(best)

        return merged

"""
Dynamic TEI Mapping Engine - Configuration-driven NLP to TEI transformation

This module provides a flexible, config-driven system for mapping annotations
to TEI elements WITHOUT requiring code changes. New annotation types and
TEI mappings can be added purely through YAML/JSON configuration.

Key features:
- No hardcoded entity mappings - all driven by configuration
- Supports any annotation type without code modification
- TEI Feature Structures (<fs>) for complex linguistic data
- Automatic element generation based on annotation structure
- Full standoff annotation support
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Union
import xml.etree.ElementTree as ET
from datetime import datetime
import yaml
import json
from pathlib import Path
from enum import Enum
import re

from annotation_model import (
    AnnotationDocument, Annotation, AnnotationLayer,
    AnnotationType, TargetType, FeatureBundle
)
from logger import get_logger

logger = get_logger(__name__)


class RenderStrategy(Enum):
    """How to render annotations in TEI"""
    INLINE = "inline"           # Embed in text flow
    STANDOFF = "standoff"       # Separate annotation section
    FEATURE_STRUCTURE = "fs"    # TEI <fs> element
    LINK = "link"               # TEI <link> element
    SEGMENT = "seg"             # TEI <seg> with @ana


@dataclass
class MappingRule:
    """
    A single mapping rule from annotation type to TEI representation.

    This is the core configuration unit. Each rule specifies:
    - What annotation types it matches
    - How to render in TEI (element name, attributes, etc.)
    - Which features to include
    - How to handle nested/related annotations
    """
    # Matching criteria
    annotation_type: str                    # e.g., "entity", "token"
    category_pattern: Optional[str] = None  # Regex for category matching
    label_pattern: Optional[str] = None     # Regex for label matching

    # TEI rendering
    tei_element: str = "name"               # TEI element to create
    render_strategy: RenderStrategy = RenderStrategy.INLINE
    namespace: str = "http://www.tei-c.org/ns/1.0"

    # Attribute mapping: annotation feature -> TEI attribute
    attribute_map: Dict[str, str] = field(default_factory=dict)

    # Feature inclusion
    include_features: List[str] = field(default_factory=list)  # Features to include in <fs>
    exclude_features: List[str] = field(default_factory=list)

    # Nesting rules
    can_contain: List[str] = field(default_factory=list)       # Child annotation types
    must_be_in: Optional[str] = None                           # Parent element requirement

    # Priority for conflict resolution
    priority: int = 0

    def matches(self, annotation: Annotation) -> bool:
        """Check if this rule matches an annotation"""
        # Check type
        if self.annotation_type != annotation.annotation_type.value:
            return False

        # Check category pattern
        if self.category_pattern and annotation.category:
            if not re.match(self.category_pattern, annotation.category):
                return False

        # Check label pattern
        if self.label_pattern and annotation.label:
            if not re.match(self.label_pattern, annotation.label):
                return False

        return True


@dataclass
class MappingProfile:
    """
    A complete mapping configuration for a domain.
    Contains all rules needed to convert annotations to TEI.
    """
    profile_id: str
    name: str
    description: str = ""
    rules: List[MappingRule] = field(default_factory=list)
    default_render_strategy: RenderStrategy = RenderStrategy.INLINE

    # Global settings
    include_provenance: bool = True
    include_certainty: bool = True
    use_feature_structures: bool = True
    generate_ids: bool = True

    # Namespace configuration
    namespaces: Dict[str, str] = field(default_factory=lambda: {
        "tei": "http://www.tei-c.org/ns/1.0",
        "xml": "http://www.w3.org/XML/1998/namespace"
    })

    def get_rule_for(self, annotation: Annotation) -> Optional[MappingRule]:
        """Find the best matching rule for an annotation"""
        matching_rules = [r for r in self.rules if r.matches(annotation)]
        if not matching_rules:
            return None
        # Return highest priority match
        return max(matching_rules, key=lambda r: r.priority)

    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'MappingProfile':
        """Load profile from YAML file"""
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MappingProfile':
        """Create profile from dictionary"""
        rules = []
        for rule_data in data.get('rules', []):
            rules.append(MappingRule(
                annotation_type=rule_data.get('annotation_type', 'entity'),
                category_pattern=rule_data.get('category_pattern'),
                label_pattern=rule_data.get('label_pattern'),
                tei_element=rule_data.get('tei_element', 'name'),
                render_strategy=RenderStrategy(rule_data.get('render_strategy', 'inline')),
                attribute_map=rule_data.get('attribute_map', {}),
                include_features=rule_data.get('include_features', []),
                exclude_features=rule_data.get('exclude_features', []),
                can_contain=rule_data.get('can_contain', []),
                must_be_in=rule_data.get('must_be_in'),
                priority=rule_data.get('priority', 0)
            ))

        return cls(
            profile_id=data.get('profile_id', 'default'),
            name=data.get('name', 'Default Profile'),
            description=data.get('description', ''),
            rules=rules,
            default_render_strategy=RenderStrategy(
                data.get('default_render_strategy', 'inline')
            ),
            include_provenance=data.get('include_provenance', True),
            include_certainty=data.get('include_certainty', True),
            use_feature_structures=data.get('use_feature_structures', True),
            generate_ids=data.get('generate_ids', True),
            namespaces=data.get('namespaces', {
                "tei": "http://www.tei-c.org/ns/1.0",
                "xml": "http://www.w3.org/XML/1998/namespace"
            })
        )

    def to_yaml(self, yaml_path: str) -> None:
        """Save profile to YAML file"""
        data = {
            'profile_id': self.profile_id,
            'name': self.name,
            'description': self.description,
            'default_render_strategy': self.default_render_strategy.value,
            'include_provenance': self.include_provenance,
            'include_certainty': self.include_certainty,
            'use_feature_structures': self.use_feature_structures,
            'generate_ids': self.generate_ids,
            'namespaces': self.namespaces,
            'rules': [
                {
                    'annotation_type': r.annotation_type,
                    'category_pattern': r.category_pattern,
                    'label_pattern': r.label_pattern,
                    'tei_element': r.tei_element,
                    'render_strategy': r.render_strategy.value,
                    'attribute_map': r.attribute_map,
                    'include_features': r.include_features,
                    'exclude_features': r.exclude_features,
                    'can_contain': r.can_contain,
                    'must_be_in': r.must_be_in,
                    'priority': r.priority
                }
                for r in self.rules
            ]
        }
        with open(yaml_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)


class MappingProfileRegistry:
    """
    Registry of mapping profiles.
    Provides default profiles and loads custom ones.
    """

    def __init__(self, profiles_dir: Optional[str] = None):
        self.profiles: Dict[str, MappingProfile] = {}
        self._register_default_profiles()
        if profiles_dir:
            self._load_custom_profiles(profiles_dir)

    def _register_default_profiles(self):
        """Register built-in mapping profiles"""

        # Universal profile - handles any annotation type automatically
        self.profiles['universal'] = MappingProfile(
            profile_id='universal',
            name='Universal Auto-Mapping',
            description='Automatically maps any annotation type to TEI using conventions',
            rules=[
                # Person entities -> persName
                MappingRule(
                    annotation_type='entity',
                    category_pattern=r'^(PERSON|PER|PERS)$',
                    tei_element='persName',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'kb_ref': 'ref', 'certainty': 'cert'},
                    priority=10
                ),
                # Location entities -> placeName
                MappingRule(
                    annotation_type='entity',
                    category_pattern=r'^(LOC|GPE|LOCATION|PLACE)$',
                    tei_element='placeName',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'kb_ref': 'ref', 'certainty': 'cert'},
                    priority=10
                ),
                # Organization entities -> orgName
                MappingRule(
                    annotation_type='entity',
                    category_pattern=r'^(ORG|ORGANIZATION)$',
                    tei_element='orgName',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'kb_ref': 'ref', 'certainty': 'cert'},
                    priority=10
                ),
                # Date/Time entities -> date
                MappingRule(
                    annotation_type='entity',
                    category_pattern=r'^(DATE|TIME)$',
                    tei_element='date',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'when': 'when', 'certainty': 'cert'},
                    priority=10
                ),
                # Fallback for any entity -> name with type attribute
                MappingRule(
                    annotation_type='entity',
                    tei_element='name',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'category': 'type', 'kb_ref': 'ref', 'certainty': 'cert'},
                    priority=0
                ),
                # Tokens -> w (word)
                MappingRule(
                    annotation_type='token',
                    tei_element='w',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'lemma': 'lemma', 'pos': 'pos'},
                    include_features=['morph', 'dep', 'tag'],
                    priority=5
                ),
                # Dependencies -> link in standoff
                MappingRule(
                    annotation_type='dependency',
                    tei_element='link',
                    render_strategy=RenderStrategy.STANDOFF,
                    attribute_map={'label': 'type'},
                    priority=5
                ),
                # Coreference -> link group
                MappingRule(
                    annotation_type='coreference',
                    tei_element='linkGrp',
                    render_strategy=RenderStrategy.STANDOFF,
                    attribute_map={'label': 'type'},
                    priority=5
                ),
            ],
            use_feature_structures=True
        )

        # Medical domain profile
        self.profiles['medical'] = MappingProfile(
            profile_id='medical',
            name='Medical/Clinical Domain',
            description='Optimized for medical texts with drug, disease, procedure entities',
            rules=[
                MappingRule(
                    annotation_type='entity',
                    category_pattern=r'^(DRUG|MEDICATION|CHEMICAL)$',
                    tei_element='term',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'kb_ref': 'ref', 'category': 'type'},
                    priority=10
                ),
                MappingRule(
                    annotation_type='entity',
                    category_pattern=r'^(DISEASE|CONDITION|DISORDER)$',
                    tei_element='term',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'kb_ref': 'ref', 'category': 'type'},
                    priority=10
                ),
                MappingRule(
                    annotation_type='entity',
                    category_pattern=r'^(PROCEDURE|TREATMENT)$',
                    tei_element='term',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'kb_ref': 'ref', 'category': 'type'},
                    priority=10
                ),
                MappingRule(
                    annotation_type='medical',
                    category_pattern=r'^(ICD10|CPT|RXNORM)$',
                    tei_element='idno',
                    render_strategy=RenderStrategy.STANDOFF,
                    attribute_map={'category': 'type'},
                    priority=15
                ),
                # Include universal rules as fallback
                *self.profiles.get('universal', MappingProfile('', '')).rules
            ],
            use_feature_structures=True
        )

        # Legal domain profile
        self.profiles['legal'] = MappingProfile(
            profile_id='legal',
            name='Legal Domain',
            description='Optimized for legal texts with citations, statutes, cases',
            rules=[
                MappingRule(
                    annotation_type='entity',
                    category_pattern=r'^(CASE|CASE_CITATION)$',
                    tei_element='bibl',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'kb_ref': 'ref'},
                    priority=10
                ),
                MappingRule(
                    annotation_type='entity',
                    category_pattern=r'^(STATUTE|LAW|USC_CITATION|CFR_CITATION)$',
                    tei_element='ref',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'kb_ref': 'target', 'category': 'type'},
                    priority=10
                ),
                MappingRule(
                    annotation_type='entity',
                    category_pattern=r'^(COURT|JUDGE)$',
                    tei_element='orgName',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'category': 'type'},
                    priority=10
                ),
                MappingRule(
                    annotation_type='legal',
                    tei_element='seg',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'category': 'ana'},
                    priority=5
                ),
            ],
            use_feature_structures=True
        )

        # Classical texts profile (Latin/Greek)
        self.profiles['classical'] = MappingProfile(
            profile_id='classical',
            name='Classical Languages',
            description='For Latin and Ancient Greek texts with botanical terms',
            rules=[
                MappingRule(
                    annotation_type='botanical',
                    tei_element='term',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'scientific_name': 'ref', 'category': 'type'},
                    include_features=['lemma', 'common_name'],
                    priority=15
                ),
                MappingRule(
                    annotation_type='token',
                    tei_element='w',
                    render_strategy=RenderStrategy.INLINE,
                    attribute_map={'lemma': 'lemma', 'pos': 'pos'},
                    include_features=['morph', 'case', 'number', 'gender', 'tense', 'mood', 'voice'],
                    priority=10
                ),
            ],
            use_feature_structures=True,
            include_provenance=True
        )

    def _load_custom_profiles(self, profiles_dir: str):
        """Load custom profiles from directory"""
        profiles_path = Path(profiles_dir)
        if not profiles_path.exists():
            return

        for yaml_file in profiles_path.glob("*.yaml"):
            try:
                profile = MappingProfile.from_yaml(str(yaml_file))
                self.profiles[profile.profile_id] = profile
                logger.info(f"Loaded custom mapping profile: {profile.profile_id}")
            except Exception as e:
                logger.error(f"Failed to load profile {yaml_file}: {e}")

    def get_profile(self, profile_id: str) -> MappingProfile:
        """Get profile by ID, fallback to universal"""
        return self.profiles.get(profile_id, self.profiles['universal'])

    def list_profiles(self) -> List[str]:
        """List available profile IDs"""
        return list(self.profiles.keys())


class DynamicTEIGenerator:
    """
    Generates TEI XML from AnnotationDocument using MappingProfile.

    This is the main rendering engine that:
    - Takes annotation documents
    - Applies mapping rules
    - Generates valid TEI XML
    - Handles all render strategies (inline, standoff, fs)
    """

    TEI_NS = "http://www.tei-c.org/ns/1.0"
    XML_NS = "http://www.w3.org/XML/1998/namespace"

    def __init__(self, profile: MappingProfile):
        self.profile = profile
        self._register_namespaces()

    def _register_namespaces(self):
        """Register XML namespaces"""
        for prefix, uri in self.profile.namespaces.items():
            ET.register_namespace(prefix, uri)

    def generate(self, doc: AnnotationDocument, metadata: Optional[Dict] = None) -> str:
        """
        Generate TEI XML from annotation document.

        Args:
            doc: AnnotationDocument to render
            metadata: Additional metadata for header

        Returns:
            Pretty-printed TEI XML string
        """
        # Create root TEI element
        root = self._create_root()

        # Add header
        header = self._create_header(doc, metadata or {})
        root.append(header)

        # Create text element
        text_elem = ET.SubElement(root, f'{{{self.TEI_NS}}}text')

        # Add body with inline annotations
        body = ET.SubElement(text_elem, f'{{{self.TEI_NS}}}body')
        self._render_body(body, doc)

        # Add standoff section if needed
        standoff_annotations = self._get_standoff_annotations(doc)
        if standoff_annotations:
            standoff = ET.SubElement(text_elem, f'{{{self.TEI_NS}}}standOff')
            self._render_standoff(standoff, standoff_annotations, doc)

        # Convert to string and prettify
        xml_str = ET.tostring(root, encoding='unicode', method='xml')
        return self._prettify_xml(xml_str)

    def _create_root(self) -> ET.Element:
        """Create TEI root element"""
        root = ET.Element(f'{{{self.TEI_NS}}}TEI')
        root.set('version', '5.0')
        root.set(f'{{{self.XML_NS}}}lang', 'en')
        return root

    def _create_header(self, doc: AnnotationDocument,
                      metadata: Dict[str, Any]) -> ET.Element:
        """Create comprehensive TEI header"""
        header = ET.Element(f'{{{self.TEI_NS}}}teiHeader')

        # File description
        file_desc = ET.SubElement(header, f'{{{self.TEI_NS}}}fileDesc')

        # Title statement
        title_stmt = ET.SubElement(file_desc, f'{{{self.TEI_NS}}}titleStmt')
        title = ET.SubElement(title_stmt, f'{{{self.TEI_NS}}}title')
        title.text = metadata.get('title', 'Annotated Text')

        # Responsibility statement
        resp_stmt = ET.SubElement(title_stmt, f'{{{self.TEI_NS}}}respStmt')
        resp = ET.SubElement(resp_stmt, f'{{{self.TEI_NS}}}resp')
        resp.text = 'NLP Processing and TEI Encoding'
        name_elem = ET.SubElement(resp_stmt, f'{{{self.TEI_NS}}}name')
        name_elem.text = 'TEI NLP Converter (Dynamic Mapper)'

        # Publication statement
        pub_stmt = ET.SubElement(file_desc, f'{{{self.TEI_NS}}}publicationStmt')
        publisher = ET.SubElement(pub_stmt, f'{{{self.TEI_NS}}}publisher')
        publisher.text = 'TEI NLP Converter System'
        pub_date = ET.SubElement(pub_stmt, f'{{{self.TEI_NS}}}date')
        pub_date.set('when', datetime.now().isoformat())

        # Source description
        source_desc = ET.SubElement(file_desc, f'{{{self.TEI_NS}}}sourceDesc')
        source_p = ET.SubElement(source_desc, f'{{{self.TEI_NS}}}p')
        source_p.text = f"Generated from annotation document: {doc.document_id}"

        # Encoding description with feature declarations
        encoding_desc = ET.SubElement(header, f'{{{self.TEI_NS}}}encodingDesc')

        # Declare feature structure types used
        if self.profile.use_feature_structures:
            self._add_feature_declarations(encoding_desc, doc)

        # Add provenance if configured
        if self.profile.include_provenance and doc.provenance_chain:
            self._add_provenance_to_header(encoding_desc, doc)

        # Profile description
        profile_desc = ET.SubElement(header, f'{{{self.TEI_NS}}}profileDesc')

        # Language
        lang_usage = ET.SubElement(profile_desc, f'{{{self.TEI_NS}}}langUsage')
        language = ET.SubElement(lang_usage, f'{{{self.TEI_NS}}}language')
        language.set('ident', doc.metadata.get('language', 'en'))

        return header

    def _add_feature_declarations(self, encoding_desc: ET.Element,
                                  doc: AnnotationDocument):
        """Add TEI feature structure declarations"""
        fs_decl = ET.SubElement(encoding_desc, f'{{{self.TEI_NS}}}fsdDecl')

        # Collect all feature types from annotations
        feature_types: Dict[str, set] = {}
        for ann in doc.get_all_annotations():
            ann_type = ann.annotation_type.value
            if ann_type not in feature_types:
                feature_types[ann_type] = set()
            feature_types[ann_type].update(ann.body.features.keys())

        # Create feature structure declarations
        for fs_type, features in feature_types.items():
            fs_decl_item = ET.SubElement(fs_decl, f'{{{self.TEI_NS}}}fsDecl')
            fs_decl_item.set('type', fs_type)

            for feat_name in features:
                f_decl = ET.SubElement(fs_decl_item, f'{{{self.TEI_NS}}}fDecl')
                f_decl.set('name', feat_name)

    def _add_provenance_to_header(self, encoding_desc: ET.Element,
                                  doc: AnnotationDocument):
        """Add processing provenance to header"""
        app_info = ET.SubElement(encoding_desc, f'{{{self.TEI_NS}}}appInfo')

        for prov in doc.provenance_chain:
            app = ET.SubElement(app_info, f'{{{self.TEI_NS}}}application')
            app.set('ident', prov.agent_id)
            if prov.model_version:
                app.set('version', prov.model_version)

            label = ET.SubElement(app, f'{{{self.TEI_NS}}}label')
            label.text = prov.model_name or prov.agent_id

            if prov.method:
                desc = ET.SubElement(app, f'{{{self.TEI_NS}}}desc')
                desc.text = f"Method: {prov.method}"

    def _render_body(self, body: ET.Element, doc: AnnotationDocument):
        """Render document body with inline annotations"""
        div = ET.SubElement(body, f'{{{self.TEI_NS}}}div')
        div.set('type', 'content')

        # Get inline annotations sorted by position
        inline_annotations = self._get_inline_annotations(doc)

        # Render text with interleaved annotations
        self._render_text_with_annotations(div, doc.text, inline_annotations)

    def _get_inline_annotations(self, doc: AnnotationDocument) -> List[Annotation]:
        """Get annotations that should be rendered inline"""
        inline = []
        for ann in doc.get_all_annotations():
            rule = self.profile.get_rule_for(ann)
            if rule and rule.render_strategy == RenderStrategy.INLINE:
                inline.append(ann)
            elif rule is None and self.profile.default_render_strategy == RenderStrategy.INLINE:
                inline.append(ann)
        return sorted(inline, key=lambda a: a.targets[0].start if a.targets else 0)

    def _get_standoff_annotations(self, doc: AnnotationDocument) -> List[Annotation]:
        """Get annotations that should be rendered in standoff section"""
        standoff = []
        for ann in doc.get_all_annotations():
            rule = self.profile.get_rule_for(ann)
            if rule and rule.render_strategy in (RenderStrategy.STANDOFF, RenderStrategy.LINK):
                standoff.append(ann)
            elif rule is None and self.profile.default_render_strategy == RenderStrategy.STANDOFF:
                standoff.append(ann)
        return standoff

    def _render_text_with_annotations(self, parent: ET.Element, text: str,
                                      annotations: List[Annotation]):
        """Render text with inline annotations"""
        # Sort annotations by start position
        sorted_anns = sorted(annotations, key=lambda a: a.targets[0].start if a.targets else 0)

        # Build position -> annotation map
        ann_starts: Dict[int, List[Annotation]] = {}
        ann_ends: Dict[int, List[Annotation]] = {}

        for ann in sorted_anns:
            if ann.targets:
                target = ann.targets[0]
                if target.target_type == TargetType.CHARACTER_OFFSET:
                    start = target.start
                    end = target.end or start + len(ann.text or '')
                    if start not in ann_starts:
                        ann_starts[start] = []
                    ann_starts[start].append(ann)
                    if end not in ann_ends:
                        ann_ends[end] = []
                    ann_ends[end].append(ann)

        # Render segments
        p_elem = ET.SubElement(parent, f'{{{self.TEI_NS}}}p')
        current_pos = 0
        open_elements: List[tuple] = []  # (annotation, element) pairs

        for pos in range(len(text) + 1):
            # Close elements ending at this position
            if pos in ann_ends:
                for ann in ann_ends[pos]:
                    # Find and close the element
                    for i, (open_ann, elem) in enumerate(open_elements):
                        if open_ann.id == ann.id:
                            # Add remaining text to element
                            if current_pos < pos:
                                segment = text[current_pos:pos]
                                if elem.text is None:
                                    elem.text = segment
                                else:
                                    # Find last child and add to tail
                                    children = list(elem)
                                    if children:
                                        if children[-1].tail is None:
                                            children[-1].tail = segment
                                        else:
                                            children[-1].tail += segment
                                    else:
                                        elem.text = (elem.text or '') + segment
                                current_pos = pos
                            open_elements.pop(i)
                            break

            # Open elements starting at this position
            if pos in ann_starts:
                # Add text before annotation
                if current_pos < pos:
                    segment = text[current_pos:pos]
                    if open_elements:
                        _, parent_elem = open_elements[-1]
                        children = list(parent_elem)
                        if children:
                            if children[-1].tail is None:
                                children[-1].tail = segment
                            else:
                                children[-1].tail += segment
                        elif parent_elem.text is None:
                            parent_elem.text = segment
                        else:
                            parent_elem.text += segment
                    else:
                        if p_elem.text is None:
                            p_elem.text = segment
                        else:
                            children = list(p_elem)
                            if children:
                                if children[-1].tail is None:
                                    children[-1].tail = segment
                                else:
                                    children[-1].tail += segment
                            else:
                                p_elem.text += segment
                    current_pos = pos

                for ann in ann_starts[pos]:
                    elem = self._create_annotation_element(ann)
                    if open_elements:
                        _, parent_elem = open_elements[-1]
                        parent_elem.append(elem)
                    else:
                        p_elem.append(elem)
                    open_elements.append((ann, elem))

        # Add remaining text
        if current_pos < len(text):
            segment = text[current_pos:]
            children = list(p_elem)
            if children:
                if children[-1].tail is None:
                    children[-1].tail = segment
                else:
                    children[-1].tail += segment
            elif p_elem.text is None:
                p_elem.text = segment
            else:
                p_elem.text += segment

    def _create_annotation_element(self, ann: Annotation) -> ET.Element:
        """Create TEI element for an annotation"""
        rule = self.profile.get_rule_for(ann)
        tei_element = rule.tei_element if rule else 'seg'

        elem = ET.Element(f'{{{self.TEI_NS}}}{tei_element}')

        # Add ID
        if self.profile.generate_ids:
            elem.set(f'{{{self.XML_NS}}}id', ann.id)

        # Apply attribute mappings
        if rule and rule.attribute_map:
            for ann_attr, tei_attr in rule.attribute_map.items():
                value = None
                if ann_attr == 'category':
                    value = ann.category
                elif ann_attr == 'label':
                    value = ann.label
                elif ann_attr == 'kb_ref':
                    value = ann.kb_ref
                elif ann_attr == 'certainty':
                    value = self._format_certainty(ann.certainty)
                elif ann.body.has(ann_attr):
                    value = ann.body.get(ann_attr)

                if value is not None:
                    elem.set(tei_attr, str(value))

        # Add certainty if configured
        if self.profile.include_certainty and ann.certainty is not None:
            if not elem.get('cert'):
                elem.set('cert', self._format_certainty(ann.certainty))

        # Add feature structure for complex data
        if self.profile.use_feature_structures and rule and rule.include_features:
            self._add_feature_structure(elem, ann, rule.include_features)

        return elem

    def _add_feature_structure(self, elem: ET.Element, ann: Annotation,
                               feature_names: List[str]):
        """Add TEI feature structure element"""
        features_to_add = {
            k: v for k, v in ann.body.features.items()
            if k in feature_names
        }

        if not features_to_add:
            return

        fs = ET.SubElement(elem, f'{{{self.TEI_NS}}}fs')
        fs.set('type', ann.annotation_type.value)

        for feat_name, feat_value in features_to_add.items():
            f = ET.SubElement(fs, f'{{{self.TEI_NS}}}f')
            f.set('name', feat_name)

            # Determine value element type
            if isinstance(feat_value, bool):
                binary = ET.SubElement(f, f'{{{self.TEI_NS}}}binary')
                binary.set('value', 'true' if feat_value else 'false')
            elif isinstance(feat_value, (int, float)):
                numeric = ET.SubElement(f, f'{{{self.TEI_NS}}}numeric')
                numeric.set('value', str(feat_value))
            elif isinstance(feat_value, str):
                if feat_value.isupper():
                    symbol = ET.SubElement(f, f'{{{self.TEI_NS}}}symbol')
                    symbol.set('value', feat_value)
                else:
                    string = ET.SubElement(f, f'{{{self.TEI_NS}}}string')
                    string.text = feat_value
            elif isinstance(feat_value, list):
                v_coll = ET.SubElement(f, f'{{{self.TEI_NS}}}vColl')
                for item in feat_value:
                    string = ET.SubElement(v_coll, f'{{{self.TEI_NS}}}string')
                    string.text = str(item)

    def _render_standoff(self, standoff: ET.Element,
                        annotations: List[Annotation],
                        doc: AnnotationDocument):
        """Render standoff annotation section"""
        # Group annotations by type
        by_type: Dict[str, List[Annotation]] = {}
        for ann in annotations:
            ann_type = ann.annotation_type.value
            if ann_type not in by_type:
                by_type[ann_type] = []
            by_type[ann_type].append(ann)

        # Render each type group
        for ann_type, anns in by_type.items():
            if ann_type == 'dependency':
                self._render_dependency_standoff(standoff, anns)
            else:
                self._render_generic_standoff(standoff, anns, ann_type)

    def _render_dependency_standoff(self, standoff: ET.Element,
                                    dependencies: List[Annotation]):
        """Render dependency relations in standoff format"""
        link_grp = ET.SubElement(standoff, f'{{{self.TEI_NS}}}linkGrp')
        link_grp.set('type', 'syntactic-dependencies')

        for dep in dependencies:
            link = ET.SubElement(link_grp, f'{{{self.TEI_NS}}}link')
            link.set(f'{{{self.XML_NS}}}id', dep.id)

            if dep.label:
                link.set('type', dep.label)

            # Build target from annotation targets
            targets = []
            for target in dep.targets:
                targets.append(target.to_tei_target())
            link.set('target', ' '.join(targets))

            # Add feature structure
            if self.profile.use_feature_structures:
                self._add_feature_structure(link, dep, list(dep.body.features.keys()))

    def _render_generic_standoff(self, standoff: ET.Element,
                                 annotations: List[Annotation],
                                 ann_type: str):
        """Render generic annotation list in standoff format"""
        list_ann = ET.SubElement(standoff, f'{{{self.TEI_NS}}}listAnnotation')
        list_ann.set('type', ann_type)

        for ann in annotations:
            annotation = ET.SubElement(list_ann, f'{{{self.TEI_NS}}}annotation')
            annotation.set(f'{{{self.XML_NS}}}id', ann.id)

            if ann.category:
                annotation.set('type', ann.category)

            # Add target
            if ann.targets:
                annotation.set('target', ann.targets[0].to_tei_target())

            # Add certainty
            if self.profile.include_certainty and ann.certainty is not None:
                certainty = ET.SubElement(annotation, f'{{{self.TEI_NS}}}certainty')
                certainty.set('degree', str(ann.certainty))

            # Add note with text
            if ann.text:
                note = ET.SubElement(annotation, f'{{{self.TEI_NS}}}note')
                note.text = ann.text

            # Add feature structure
            if self.profile.use_feature_structures:
                self._add_feature_structure(annotation, ann, list(ann.body.features.keys()))

    def _format_certainty(self, certainty: Optional[float]) -> str:
        """Convert numeric certainty to TEI certainty value"""
        if certainty is None:
            return 'unknown'
        if certainty >= 0.9:
            return 'high'
        elif certainty >= 0.7:
            return 'medium'
        elif certainty >= 0.5:
            return 'low'
        return 'unknown'

    def _prettify_xml(self, xml_str: str) -> str:
        """Pretty print XML"""
        try:
            from defusedxml.minidom import parseString
            dom = parseString(xml_str)
            pretty = dom.toprettyxml(indent="  ")

            # Clean up
            lines = [line.rstrip() for line in pretty.split('\n') if line.strip()]
            if lines[0].startswith('<?xml'):
                lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'

            return '\n'.join(lines)
        except Exception as e:
            logger.error(f"Failed to prettify XML: {e}")
            return xml_str

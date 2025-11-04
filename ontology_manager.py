"""
ontology_manager.py - Domain-specific TEI schema management
"""
from typing import Dict, List, Any, Optional, Tuple
import json
from pathlib import Path
from logger import get_logger

logger = get_logger(__name__)

class OntologyManager:
    """
    Manages domain-specific ontologies and TEI schemas
    Provides customization for different academic domains
    Supports provider-aware entity mappings for optimal conversions
    """

    def __init__(self, schemas_dir: str = "schemas"):
        self.schemas_dir = Path(schemas_dir)
        self.schemas_dir.mkdir(exist_ok=True)
        self.schemas_cache = {}
        self._initialize_provider_mappings()
        self._initialize_default_schemas()
        self._load_custom_schemas()

    def _initialize_provider_mappings(self):
        """Initialize provider-specific entity type to TEI element mappings"""
        self.provider_entity_mappings = {
            'google': {
                'PERSON': 'persName',
                'LOC': 'placeName',
                'LOCATION': 'placeName',
                'ORG': 'orgName',
                'ORGANIZATION': 'orgName',
                'EVENT': 'event',
                'WORK_OF_ART': 'title',
                'PRODUCT': 'objectName',
                'CONSUMER_GOOD': 'objectName',
                'OTHER': 'name',
                'UNKNOWN': 'name',
                # Google-specific entities
                'PHONE': 'num',
                'PHONE_NUMBER': 'num',
                'ADDRESS': 'address',
                'DATE': 'date',
                'TIME': 'time',
                'CARDINAL': 'num',
                'NUMBER': 'num',
                'MONEY': 'measure',
                'PRICE': 'measure',
                'PERCENT': 'measure',
                'QUANTITY': 'measure',
                'ORDINAL': 'num',
                'DEFAULT': 'name'
            },
            'spacy': {
                'PERSON': 'persName',
                'PER': 'persName',
                'LOC': 'placeName',
                'GPE': 'placeName',
                'FAC': 'placeName',
                'ORG': 'orgName',
                'DATE': 'date',
                'TIME': 'time',
                'MONEY': 'measure',
                'QUANTITY': 'measure',
                'PERCENT': 'measure',
                'CARDINAL': 'num',
                'ORDINAL': 'num',
                'NORP': 'orgName',
                'PRODUCT': 'objectName',
                'WORK_OF_ART': 'title',
                'LAW': 'ref',
                'LANGUAGE': 'lang',
                'EVENT': 'event',
                'DEFAULT': 'name'
            },
            'remote': {
                # Generic mappings for remote server
                'PERSON': 'persName',
                'LOC': 'placeName',
                'ORG': 'orgName',
                'DATE': 'date',
                'TIME': 'time',
                'MONEY': 'measure',
                'DEFAULT': 'name'
            }
        }
    
    def _initialize_default_schemas(self):
        """Initialize built-in domain schemas"""
        self.default_schemas = {
            "default": {
                "domain": "default",
                "title": "General Text",
                "description": "Default TEI schema for general text processing",
                "annotation_strategy": "inline",
                "include_pos": True,
                "include_lemma": True,
                "include_dependencies": True,
                "include_analysis": True,
                "use_paragraphs": False,
                "entity_mappings": {
                    "PERSON": "persName",
                    "PER": "persName",
                    "LOC": "placeName",
                    "GPE": "placeName",
                    "ORG": "orgName",
                    "DATE": "date",
                    "TIME": "time",
                    "MONEY": "measure",
                    "DEFAULT": "name"
                }
            },
            
            "literary": {
                "domain": "literary",
                "title": "Literary Analysis",
                "description": "TEI schema optimized for literary texts and criticism",
                "annotation_strategy": "standoff",
                "include_pos": True,
                "include_lemma": True,
                "include_dependencies": True,
                "include_analysis": True,
                "use_paragraphs": True,
                "include_morph": True,
                "entity_mappings": {
                    "PERSON": "persName",
                    "CHARACTER": "persName",
                    "LOC": "placeName",
                    "SETTING": "placeName",
                    "ORG": "orgName",
                    "WORK_OF_ART": "title",
                    "EVENT": "name",
                    "DEFAULT": "rs"
                },
                "additional_tags": ["l", "lg", "quote", "said", "stage"],
                "classification": True,
                "text_class": "literary"
            },
            
            "historical": {
                "domain": "historical",
                "title": "Historical Document",
                "description": "TEI schema for historical texts and documents",
                "annotation_strategy": "standoff",
                "include_pos": True,
                "include_lemma": True,
                "include_dependencies": False,
                "include_analysis": True,
                "use_paragraphs": True,
                "entity_mappings": {
                    "PERSON": "persName",
                    "LOC": "placeName",
                    "GPE": "placeName",
                    "ORG": "orgName",
                    "DATE": "date",
                    "EVENT": "event",
                    "DEFAULT": "name"
                },
                "additional_tags": ["date", "event", "bibl", "orig", "reg"],
                "classification": True,
                "text_class": "historical",
                "include_provenance": True
            },
            
            "legal": {
                "domain": "legal",
                "title": "Legal Document",
                "description": "TEI schema for legal texts and contracts",
                "annotation_strategy": "standoff",
                "include_pos": False,
                "include_lemma": False,
                "include_dependencies": False,
                "include_analysis": False,
                "use_paragraphs": True,
                "entity_mappings": {
                    "PERSON": "persName",
                    "ORG": "orgName",
                    "LAW": "name",
                    "CASE": "name",
                    "STATUTE": "ref",
                    "COURT": "orgName",
                    "DEFAULT": "name"
                },
                "additional_tags": ["clause", "provision", "article", "section"],
                "classification": True,
                "text_class": "legal",
                "strict_structure": True
            },
            
            "scientific": {
                "domain": "scientific",
                "title": "Scientific Text",
                "description": "TEI schema for scientific papers and research",
                "annotation_strategy": "inline",
                "include_pos": True,
                "include_lemma": True,
                "include_dependencies": True,
                "include_analysis": True,
                "use_paragraphs": True,
                "entity_mappings": {
                    "PERSON": "persName",
                    "ORG": "orgName",
                    "CHEMICAL": "term",
                    "DISEASE": "term",
                    "GENE": "term",
                    "SPECIES": "term",
                    "MEASUREMENT": "measure",
                    "DEFAULT": "term"
                },
                "additional_tags": ["formula", "figure", "table", "citation"],
                "classification": True,
                "text_class": "scientific",
                "include_references": True
            },
            
            "linguistic": {
                "domain": "linguistic",
                "title": "Linguistic Analysis",
                "description": "TEI schema for linguistic corpus and analysis",
                "annotation_strategy": "standoff",
                "include_pos": True,
                "include_lemma": True,
                "include_dependencies": True,
                "include_analysis": True,
                "include_morph": True,
                "include_dep": True,
                "use_paragraphs": False,
                "entity_mappings": {
                    "DEFAULT": "name"
                },
                "additional_tags": ["w", "pc", "c", "phr", "cl", "s", "u"],
                "classification": True,
                "text_class": "linguistic",
                "detailed_tokens": True
            },
            
            "manuscript": {
                "domain": "manuscript",
                "title": "Manuscript Transcription",
                "description": "TEI schema for manuscript transcription and description",
                "annotation_strategy": "inline",
                "include_pos": False,
                "include_lemma": False,
                "include_dependencies": False,
                "include_analysis": False,
                "use_paragraphs": True,
                "entity_mappings": {
                    "PERSON": "persName",
                    "PLACE": "placeName",
                    "DEFAULT": "name"
                },
                "additional_tags": ["pb", "lb", "cb", "fw", "add", "del", "gap", "unclear", "damage"],
                "classification": True,
                "text_class": "manuscript",
                "include_physical": True,
                "preserve_layout": True
            },
            
            "dramatic": {
                "domain": "dramatic",
                "title": "Dramatic Text",
                "description": "TEI schema for plays and dramatic texts",
                "annotation_strategy": "inline",
                "include_pos": True,
                "include_lemma": False,
                "include_dependencies": False,
                "include_analysis": True,
                "use_paragraphs": False,
                "entity_mappings": {
                    "PERSON": "persName",
                    "CHARACTER": "role",
                    "LOC": "placeName",
                    "DEFAULT": "name"
                },
                "additional_tags": ["sp", "speaker", "stage", "role", "roleDesc", "act", "scene"],
                "classification": True,
                "text_class": "dramatic",
                "structure_type": "dramatic"
            },
            
            "poetry": {
                "domain": "poetry",
                "title": "Poetic Text",
                "description": "TEI schema for poetry and verse",
                "annotation_strategy": "inline",
                "include_pos": True,
                "include_lemma": True,
                "include_dependencies": False,
                "include_analysis": True,
                "use_paragraphs": False,
                "entity_mappings": {
                    "PERSON": "persName",
                    "LOC": "placeName",
                    "DEFAULT": "name"
                },
                "additional_tags": ["l", "lg", "rhyme", "caesura", "enjamb"],
                "classification": True,
                "text_class": "poetry",
                "preserve_lineation": True,
                "analyze_meter": True
            },
            
            "epistolary": {
                "domain": "epistolary",
                "title": "Correspondence",
                "description": "TEI schema for letters and correspondence",
                "annotation_strategy": "inline",
                "include_pos": False,
                "include_lemma": False,
                "include_dependencies": False,
                "include_analysis": False,
                "use_paragraphs": True,
                "entity_mappings": {
                    "PERSON": "persName",
                    "LOC": "placeName",
                    "ORG": "orgName",
                    "DATE": "date",
                    "DEFAULT": "name"
                },
                "additional_tags": ["opener", "closer", "salute", "signed", "postscript", "dateline", "address"],
                "classification": True,
                "text_class": "correspondence",
                "include_metadata": True
            }
        }
        
        # Cache default schemas
        self.schemas_cache.update(self.default_schemas)
    
    def _load_custom_schemas(self):
        """Load custom schemas from JSON files"""
        try:
            for schema_file in self.schemas_dir.glob("*.json"):
                try:
                    with open(schema_file, 'r', encoding='utf-8') as f:
                        schema = json.load(f)
                        domain = schema.get('domain', schema_file.stem)
                        self.schemas_cache[domain] = schema
                        logger.info(f"Loaded custom schema: {domain}")
                except Exception as e:
                    logger.error(f"Failed to load schema from {schema_file}: {e}")
        except Exception as e:
            logger.warning(f"Could not load custom schemas: {e}")
    
    def get_schema(self, domain: str) -> Dict[str, Any]:
        """Get schema for a specific domain"""
        if domain in self.schemas_cache:
            return self.schemas_cache[domain].copy()
        
        logger.warning(f"Schema for domain '{domain}' not found, using default")
        return self.schemas_cache["default"].copy()
    
    def get_available_domains(self) -> List[str]:
        """Get list of available domains"""
        return sorted(list(self.schemas_cache.keys()))
    
    def validate_domain(self, domain: str) -> bool:
        """Check if a domain exists"""
        return domain in self.schemas_cache
    
    def get_entity_mappings(self, domain: str) -> Dict[str, str]:
        """Get entity type to TEI element mappings for a domain"""
        schema = self.get_schema(domain)
        return schema.get("entity_mappings", self.default_schemas["default"]["entity_mappings"])
    
    def get_annotation_strategy(self, domain: str) -> str:
        """Get annotation strategy for a domain"""
        schema = self.get_schema(domain)
        return schema.get("annotation_strategy", "inline")
    
    def save_custom_schema(self, domain: str, schema: Dict[str, Any]) -> bool:
        """Save a custom schema to file"""
        try:
            schema_file = self.schemas_dir / f"{domain}.json"
            with open(schema_file, 'w', encoding='utf-8') as f:
                json.dump(schema, f, indent=2)
            
            # Update cache
            self.schemas_cache[domain] = schema
            logger.info(f"Saved custom schema: {domain}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save schema for {domain}: {e}")
            return False
    
    def update_schema(self, domain: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing schema with new values"""
        schema = self.get_schema(domain)
        schema.update(updates)
        
        # Save if it's a custom schema
        if domain not in self.default_schemas:
            self.save_custom_schema(domain, schema)
        
        return schema
    
    def export_all_schemas(self, output_dir: str = None) -> bool:
        """Export all schemas to a directory"""
        try:
            output_path = Path(output_dir) if output_dir else self.schemas_dir / "export"
            output_path.mkdir(exist_ok=True, parents=True)
            
            for domain, schema in self.schemas_cache.items():
                schema_file = output_path / f"{domain}.json"
                with open(schema_file, 'w', encoding='utf-8') as f:
                    json.dump(schema, f, indent=2)
            
            logger.info(f"Exported {len(self.schemas_cache)} schemas to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export schemas: {e}")
            return False
    
    def get_schema_info(self, domain: str) -> Dict[str, Any]:
        """Get detailed information about a schema"""
        schema = self.get_schema(domain)
        return {
            "domain": domain,
            "title": schema.get("title", "Unknown"),
            "description": schema.get("description", "No description available"),
            "annotation_strategy": schema.get("annotation_strategy", "inline"),
            "entity_types": list(schema.get("entity_mappings", {}).keys()),
            "additional_tags": schema.get("additional_tags", []),
            "features": {
                "pos_tags": schema.get("include_pos", False),
                "lemmas": schema.get("include_lemma", False),
                "dependencies": schema.get("include_dependencies", False),
                "morphology": schema.get("include_morph", False),
                "analysis": schema.get("include_analysis", False)
            },
            "is_custom": domain not in self.default_schemas
        }
    
    def validate_schema(self, schema: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate a schema structure"""
        errors = []
        required_fields = ["domain", "title", "annotation_strategy"]

        for field in required_fields:
            if field not in schema:
                errors.append(f"Missing required field: {field}")

        if "annotation_strategy" in schema:
            valid_strategies = ["inline", "standoff", "mixed"]
            if schema["annotation_strategy"] not in valid_strategies:
                errors.append(f"Invalid annotation_strategy. Must be one of: {', '.join(valid_strategies)}")

        if "entity_mappings" in schema:
            if not isinstance(schema["entity_mappings"], dict):
                errors.append("entity_mappings must be a dictionary")

        return len(errors) == 0, errors

    def get_provider_entity_mappings(self, provider: str, domain: str = None) -> Dict[str, str]:
        """
        Get provider-specific entity mappings, optionally merged with domain-specific mappings

        Args:
            provider: NLP provider name ('google', 'spacy', 'remote')
            domain: Optional domain to merge domain-specific mappings

        Returns:
            Dictionary of entity type to TEI element mappings
        """
        # Start with provider-specific mappings
        provider_key = provider.lower()
        mappings = self.provider_entity_mappings.get(provider_key, {}).copy()

        # Merge with domain-specific mappings if domain is provided
        if domain:
            schema = self.get_schema(domain)
            domain_mappings = schema.get('entity_mappings', {})
            # Domain mappings take precedence
            mappings.update(domain_mappings)

        # Ensure DEFAULT mapping exists
        if 'DEFAULT' not in mappings:
            mappings['DEFAULT'] = 'name'

        return mappings

    def get_provider_capabilities_map(self, provider: str) -> Dict[str, Any]:
        """
        Get provider-specific capability information for optimization

        Args:
            provider: NLP provider name

        Returns:
            Dictionary describing provider capabilities and optimization hints
        """
        capabilities = {
            'google': {
                'entity_sentiment': True,
                'entity_salience': True,
                'knowledge_graph': True,
                'rich_morphology': True,
                'syntax_analysis': True,
                'text_classification': True,
                'optimal_for': ['legal', 'scientific', 'historical'],
                'max_text_length': 1000000,
                'supports_entities': [
                    'PERSON', 'LOCATION', 'ORGANIZATION', 'EVENT',
                    'WORK_OF_ART', 'CONSUMER_GOOD', 'PHONE_NUMBER',
                    'ADDRESS', 'DATE', 'NUMBER', 'PRICE'
                ]
            },
            'spacy': {
                'entity_sentiment': False,
                'entity_salience': False,
                'knowledge_graph': False,
                'rich_morphology': True,
                'syntax_analysis': True,
                'text_classification': False,
                'optimal_for': ['literary', 'linguistic', 'general'],
                'max_text_length': 1000000,
                'supports_entities': [
                    'PERSON', 'LOC', 'GPE', 'ORG', 'DATE', 'TIME',
                    'MONEY', 'PERCENT', 'PRODUCT', 'WORK_OF_ART'
                ]
            },
            'remote': {
                'entity_sentiment': False,
                'entity_salience': False,
                'knowledge_graph': False,
                'rich_morphology': True,
                'syntax_analysis': True,
                'text_classification': False,
                'optimal_for': ['general'],
                'max_text_length': 100000,
                'supports_entities': ['PERSON', 'LOC', 'ORG', 'DATE', 'TIME']
            }
        }

        return capabilities.get(provider.lower(), capabilities['spacy'])

    def select_optimal_provider(self, text: str, domain: str) -> str:
        """
        Select optimal provider based on text characteristics and domain

        Args:
            text: The text to be processed
            domain: The domain schema to use

        Returns:
            Recommended provider name
        """
        text_length = len(text)
        schema = self.get_schema(domain)

        # Legal domain benefits from Google's precision
        if domain in ['legal', 'scientific', 'historical']:
            if text_length <= 1000000:  # Google's limit
                return 'google'

        # Linguistic analysis works well with SpaCy
        if domain in ['linguistic', 'literary']:
            return 'spacy'

        # For very long texts, prefer local processing
        if text_length > 100000:
            return 'spacy'

        # Default recommendation based on domain requirements
        if schema.get('include_morph') or schema.get('detailed_tokens'):
            return 'spacy'

        # Google for rich entity analysis
        return 'google'

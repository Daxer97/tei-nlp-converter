"""
SpaCy Model Provider

Provides dynamic discovery and loading of spaCy models including:
- Standard spaCy models (en_core_web_sm, en_core_web_md, en_core_web_lg)
- Specialized models (SciSpacy for medical/scientific text)
- Custom trained spaCy models
"""
import spacy
from spacy.cli import download as spacy_download
from typing import List, Optional, Dict, Any
import asyncio
from datetime import datetime
import subprocess
import json
import re

from ner_models.base import (
    NERModel,
    ModelMetadata,
    ModelCapabilities,
    ModelPerformanceMetrics,
    Entity
)
from ner_models.registry import NERModelProvider
from logger import get_logger

logger = get_logger(__name__)


class SpacyNERModel(NERModel):
    """Wrapper for spaCy model"""

    def __init__(self, model_id: str, version: str, metadata: Optional[ModelMetadata] = None):
        super().__init__(model_id, version, metadata)
        self.nlp = None
        self._entity_type_map = {}

    async def load(self) -> bool:
        """Load the spaCy model"""
        try:
            logger.info(f"Loading spaCy model: {self.model_id}")

            # Extract spaCy model name from model_id (e.g., "spacy/en_core_web_sm" -> "en_core_web_sm")
            model_name = self.model_id.split('/')[-1]

            # Try to load the model
            try:
                self.nlp = spacy.load(model_name)
            except OSError:
                # Model not installed, try to download it
                logger.info(f"Model {model_name} not found, downloading...")
                spacy_download(model_name)
                self.nlp = spacy.load(model_name)

            self._loaded = True
            logger.info(f"Successfully loaded spaCy model: {self.model_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to load spaCy model {self.model_id}: {e}")
            self._loaded = False
            return False

    async def extract_entities(self, text: str) -> List[Entity]:
        """Extract entities from text"""
        if not self._loaded or not self.nlp:
            raise RuntimeError(f"Model {self.model_id} not loaded")

        try:
            doc = self.nlp(text)
            entities = []

            for ent in doc.ents:
                entity = Entity(
                    text=ent.text,
                    type=ent.label_,
                    start=ent.start_char,
                    end=ent.end_char,
                    confidence=1.0,  # spaCy doesn't provide confidence scores by default
                    model_id=self.model_id,
                    metadata={
                        'lemma': ent.lemma_,
                        'pos': ent.root.pos_,
                        'dep': ent.root.dep_
                    }
                )
                entities.append(entity)

            return entities

        except Exception as e:
            logger.error(f"Error extracting entities with {self.model_id}: {e}")
            return []

    async def extract_entities_batch(self, texts: List[str]) -> List[List[Entity]]:
        """Extract entities from multiple texts"""
        if not self._loaded or not self.nlp:
            raise RuntimeError(f"Model {self.model_id} not loaded")

        try:
            results = []

            # Process in batches for efficiency
            for doc in self.nlp.pipe(texts):
                entities = []

                for ent in doc.ents:
                    entity = Entity(
                        text=ent.text,
                        type=ent.label_,
                        start=ent.start_char,
                        end=ent.end_char,
                        confidence=1.0,
                        model_id=self.model_id,
                        metadata={
                            'lemma': ent.lemma_,
                            'pos': ent.root.pos_,
                            'dep': ent.root.dep_
                        }
                    )
                    entities.append(entity)

                results.append(entities)

            return results

        except Exception as e:
            logger.error(f"Error in batch extraction with {self.model_id}: {e}")
            return [[] for _ in texts]

    def get_capabilities(self) -> ModelCapabilities:
        """Get model capabilities"""
        if not self._loaded or not self.nlp:
            # Return default capabilities if not loaded
            return ModelCapabilities(
                entity_types=["PERSON", "ORG", "GPE", "LOC", "PRODUCT"],
                supports_confidence_scores=False,
                supports_multiword_entities=True,
                supports_nested_entities=False,
                languages=["en"]
            )

        # Get actual entity types from loaded model
        entity_types = list(self.nlp.get_pipe("ner").labels)

        return ModelCapabilities(
            entity_types=entity_types,
            supports_confidence_scores=False,
            supports_multiword_entities=True,
            supports_nested_entities=False,
            languages=[self.nlp.lang]
        )

    async def unload(self) -> bool:
        """Unload model from memory"""
        try:
            if self.nlp:
                # Remove references to allow garbage collection
                self.nlp = None
                self._loaded = False
                logger.info(f"Unloaded spaCy model: {self.model_id}")
                return True

        except Exception as e:
            logger.error(f"Error unloading model {self.model_id}: {e}")

        return False


class SpacyModelProvider(NERModelProvider):
    """SpaCy model provider with dynamic model discovery"""

    # Known spaCy model configurations
    KNOWN_MODELS = {
        # Standard English models
        "en_core_web_sm": {
            "domain": "general",
            "description": "English pipeline optimized for CPU. Small model.",
            "entities": ["PERSON", "NORP", "FAC", "ORG", "GPE", "LOC", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW", "LANGUAGE", "DATE", "TIME", "PERCENT", "MONEY", "QUANTITY", "ORDINAL", "CARDINAL"],
            "size_mb": 12,
            "f1": 0.85,
            "latency_ms": 10
        },
        "en_core_web_md": {
            "domain": "general",
            "description": "English pipeline optimized for CPU. Medium model with word vectors.",
            "entities": ["PERSON", "NORP", "FAC", "ORG", "GPE", "LOC", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW", "LANGUAGE", "DATE", "TIME", "PERCENT", "MONEY", "QUANTITY", "ORDINAL", "CARDINAL"],
            "size_mb": 40,
            "f1": 0.87,
            "latency_ms": 20
        },
        "en_core_web_lg": {
            "domain": "general",
            "description": "English pipeline optimized for CPU. Large model with word vectors.",
            "entities": ["PERSON", "NORP", "FAC", "ORG", "GPE", "LOC", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW", "LANGUAGE", "DATE", "TIME", "PERCENT", "MONEY", "QUANTITY", "ORDINAL", "CARDINAL"],
            "size_mb": 560,
            "f1": 0.87,
            "latency_ms": 40
        },
        # SciSpacy models (medical/scientific)
        "en_core_sci_sm": {
            "domain": "medical",
            "description": "A full spaCy pipeline for biomedical data",
            "entities": ["DISEASE", "CHEMICAL", "ANATOMY", "GENE", "PROTEIN"],
            "size_mb": 15,
            "f1": 0.75,
            "latency_ms": 15,
            "requires_kb": ["UMLS"]
        },
        "en_core_sci_md": {
            "domain": "medical",
            "description": "A full spaCy pipeline for biomedical data with word vectors",
            "entities": ["DISEASE", "CHEMICAL", "ANATOMY", "GENE", "PROTEIN"],
            "size_mb": 100,
            "f1": 0.78,
            "latency_ms": 25,
            "requires_kb": ["UMLS"]
        },
        "en_ner_bc5cdr_md": {
            "domain": "medical",
            "description": "NER model for diseases and chemicals (BC5CDR corpus)",
            "entities": ["DISEASE", "CHEMICAL"],
            "size_mb": 100,
            "f1": 0.89,
            "latency_ms": 20,
            "requires_kb": ["UMLS", "RxNorm"]
        },
        "en_ner_bionlp13cg_md": {
            "domain": "medical",
            "description": "NER model for cancer genetics (BioNLP13CG corpus)",
            "entities": ["GENE", "PROTEIN", "CELL", "DNA", "RNA"],
            "size_mb": 100,
            "f1": 0.80,
            "latency_ms": 20,
            "requires_kb": ["UMLS"]
        },
        "en_ner_craft_md": {
            "domain": "medical",
            "description": "NER model for biomedical entities (CRAFT corpus)",
            "entities": ["GENE", "PROTEIN", "CELL", "CHEMICAL", "TAXON"],
            "size_mb": 100,
            "f1": 0.77,
            "latency_ms": 20,
            "requires_kb": ["UMLS"]
        },
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.manifest = None
        self._load_manifest()

    def get_provider_name(self) -> str:
        return "spacy"

    def _load_manifest(self):
        """Load spaCy models manifest"""
        try:
            # Try to get installed models
            result = subprocess.run(
                ["python", "-m", "spacy", "info", "--json"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                info = json.loads(result.stdout)
                self.manifest = info
                logger.debug("Loaded spaCy manifest")

        except Exception as e:
            logger.debug(f"Could not load spaCy manifest: {e}")
            self.manifest = None

    async def list_available_models(self, domain: Optional[str] = None) -> List[ModelMetadata]:
        """
        Discover available spaCy models

        Args:
            domain: Optional domain filter

        Returns:
            List of model metadata
        """
        models = []

        for model_name, model_info in self.KNOWN_MODELS.items():
            # Filter by domain if specified
            if domain and model_info['domain'] != domain:
                continue

            # Check if model matches domain
            model_domain = model_info.get('domain', 'general')

            # Create metadata
            capabilities = ModelCapabilities(
                entity_types=model_info['entities'],
                supports_confidence_scores=False,
                supports_multiword_entities=True,
                supports_nested_entities=False,
                languages=['en']
            )

            performance = ModelPerformanceMetrics(
                f1_score=model_info.get('f1', 0.80),
                precision=model_info.get('f1', 0.80),  # Approximate
                recall=model_info.get('f1', 0.80),  # Approximate
                latency_ms=model_info.get('latency_ms', 20),
                memory_mb=model_info.get('size_mb')
            )

            metadata = ModelMetadata(
                model_id=f"spacy/{model_name}",
                provider="spacy",
                version="latest",
                domain=model_domain,
                capabilities=capabilities,
                performance=performance,
                source_url=f"https://github.com/explosion/spacy-models/releases/{model_name}",
                trusted=True,  # spaCy models are trusted
                requires_kb=model_info.get('requires_kb', []),
                description=model_info.get('description'),
                model_size_mb=model_info.get('size_mb'),
                created_at=datetime.now()
            )

            models.append(metadata)

        logger.info(f"Discovered {len(models)} spaCy models" + (f" for domain '{domain}'" if domain else ""))
        return models

    async def load_model(self, model_id: str, version: str = "latest") -> NERModel:
        """
        Load a specific spaCy model

        Args:
            model_id: Model identifier (e.g., "spacy/en_core_web_sm")
            version: Model version (not used for spaCy)

        Returns:
            Loaded NER model
        """
        # Check cache
        cache_key = f"{model_id}:{version}"
        if cache_key in self.model_cache:
            logger.info(f"Using cached model: {model_id}")
            return self.model_cache[cache_key]

        # Create model instance
        model = SpacyNERModel(model_id, version)

        # Load the model
        if await model.load():
            self.model_cache[cache_key] = model
            return model
        else:
            raise RuntimeError(f"Failed to load spaCy model: {model_id}")

    def get_model_capabilities(self, model_id: str) -> ModelCapabilities:
        """Get capabilities of a model"""

        # Extract model name
        model_name = model_id.split('/')[-1]

        if model_name in self.KNOWN_MODELS:
            model_info = self.KNOWN_MODELS[model_name]
            return ModelCapabilities(
                entity_types=model_info['entities'],
                supports_confidence_scores=False,
                supports_multiword_entities=True,
                supports_nested_entities=False,
                languages=['en']
            )

        # Default capabilities
        return ModelCapabilities(
            entity_types=["PERSON", "ORG", "GPE", "LOC"],
            supports_confidence_scores=False,
            supports_multiword_entities=True,
            supports_nested_entities=False,
            languages=['en']
        )

    def _is_installed(self, model_name: str) -> bool:
        """Check if a model is installed"""
        try:
            spacy.load(model_name)
            return True
        except OSError:
            return False

"""
SpaCy model provider with dynamic model discovery.

Supports loading models from:
- spaCy core models (en_core_web_sm, etc.)
- SciSpacy biomedical models
- Custom trained models
"""

import logging
import time
import asyncio
from typing import List, Optional, Set, Dict, Any
from datetime import datetime

try:
    import spacy
    from spacy.language import Language
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False

from .base import (
    NERModelProvider,
    NERModel,
    ModelMetadata,
    ModelCapabilities,
    ModelPerformance,
    ModelStatus,
    Entity
)

logger = logging.getLogger(__name__)


class SpacyNERModel(NERModel):
    """Wrapper for spaCy NLP model"""

    def __init__(self, nlp: "Language", model_id: str, version: str, domain: str = "general"):
        super().__init__(model_id, version, domain)
        self.nlp = nlp
        self.status = ModelStatus.READY
        self.load_time = datetime.now()
        self._entity_types = self._detect_entity_types()
        self.capabilities = self._build_capabilities()

    def _detect_entity_types(self) -> Set[str]:
        """Detect entity types from model's NER labels"""
        if "ner" in self.nlp.pipe_names:
            ner = self.nlp.get_pipe("ner")
            return set(ner.labels)
        return set()

    def _build_capabilities(self) -> ModelCapabilities:
        """Build capabilities from loaded model"""
        capabilities = ModelCapabilities(
            entity_types=self._entity_types,
            supports_batch=True,
            supports_context=True,
            max_sequence_length=1000000,  # spaCy has no hard limit
            languages={"en"}
        )

        # Check for additional components
        pipe_names = self.nlp.pipe_names
        capabilities.additional_features = {
            "pos_tagging": "tagger" in pipe_names,
            "dependency_parsing": "parser" in pipe_names,
            "lemmatization": "lemmatizer" in pipe_names or "tagger" in pipe_names,
            "sentence_segmentation": "parser" in pipe_names or "sentencizer" in pipe_names,
            "entity_linking": "entity_linker" in pipe_names
        }

        return capabilities

    async def extract_entities(self, text: str) -> List[Entity]:
        """Extract named entities from text"""
        start_time = time.time()

        # Run spaCy in thread pool to not block async
        loop = asyncio.get_event_loop()
        doc = await loop.run_in_executor(None, self.nlp, text)

        entities = []
        for ent in doc.ents:
            entity = Entity(
                text=ent.text,
                type=ent.label_,
                start=ent.start_char,
                end=ent.end_char,
                confidence=1.0,  # spaCy doesn't provide confidence
                model_id=self.model_id,
                sources=[self.model_id],
                metadata={
                    "root_text": ent.root.text,
                    "root_dep": ent.root.dep_,
                    "sent_start": ent.sent.start_char if ent.sent else None,
                    "sent_end": ent.sent.end_char if ent.sent else None
                }
            )
            entities.append(entity)

        latency_ms = (time.time() - start_time) * 1000
        self.record_performance(latency_ms, len(entities))

        return entities

    async def extract_entities_batch(self, texts: List[str]) -> List[List[Entity]]:
        """Extract entities from multiple texts"""
        loop = asyncio.get_event_loop()

        # Use spaCy's pipe for efficient batch processing
        def process_batch():
            results = []
            for doc in self.nlp.pipe(texts, batch_size=50):
                doc_entities = []
                for ent in doc.ents:
                    entity = Entity(
                        text=ent.text,
                        type=ent.label_,
                        start=ent.start_char,
                        end=ent.end_char,
                        confidence=1.0,
                        model_id=self.model_id,
                        sources=[self.model_id]
                    )
                    doc_entities.append(entity)
                results.append(doc_entities)
            return results

        results = await loop.run_in_executor(None, process_batch)
        return results

    def get_capabilities(self) -> ModelCapabilities:
        """Return model capabilities"""
        return self.capabilities

    def cleanup(self) -> None:
        """Release model resources"""
        self.status = ModelStatus.UNLOADED
        # spaCy models don't need explicit cleanup
        logger.info(f"Cleaned up model: {self.model_id}")


class SpacyModelProvider(NERModelProvider):
    """Dynamic spaCy model provider"""

    def __init__(self):
        if not SPACY_AVAILABLE:
            raise ImportError("spaCy is not installed")

        self._model_cache: Dict[str, SpacyNERModel] = {}

        # Pre-defined model metadata for known models
        self._known_models = self._build_known_models()

    def _build_known_models(self) -> Dict[str, ModelMetadata]:
        """Build metadata for known spaCy models"""
        models = {}

        # Core spaCy models
        models["spacy/en_core_web_sm"] = ModelMetadata(
            model_id="spacy/en_core_web_sm",
            provider="spacy",
            version="3.7.0",
            domain="general",
            entity_types={"PERSON", "ORG", "GPE", "LOC", "DATE", "TIME", "MONEY", "PERCENT",
                          "FACILITY", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW", "LANGUAGE",
                          "NORP", "QUANTITY", "ORDINAL", "CARDINAL"},
            performance=ModelPerformance(
                f1_score=0.84,
                precision=0.85,
                recall=0.83,
                latency_ms=15.0
            ),
            source_url="https://github.com/explosion/spacy-models",
            trusted=True,
            size_mb=12.0,
            license="MIT",
            description="English multi-task CNN trained on OntoNotes"
        )

        models["spacy/en_core_web_md"] = ModelMetadata(
            model_id="spacy/en_core_web_md",
            provider="spacy",
            version="3.7.0",
            domain="general",
            entity_types={"PERSON", "ORG", "GPE", "LOC", "DATE", "TIME", "MONEY", "PERCENT",
                          "FACILITY", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW", "LANGUAGE",
                          "NORP", "QUANTITY", "ORDINAL", "CARDINAL"},
            performance=ModelPerformance(
                f1_score=0.85,
                precision=0.86,
                recall=0.84,
                latency_ms=25.0
            ),
            source_url="https://github.com/explosion/spacy-models",
            trusted=True,
            size_mb=43.0,
            license="MIT",
            description="English multi-task CNN with word vectors"
        )

        models["spacy/en_core_web_lg"] = ModelMetadata(
            model_id="spacy/en_core_web_lg",
            provider="spacy",
            version="3.7.0",
            domain="general",
            entity_types={"PERSON", "ORG", "GPE", "LOC", "DATE", "TIME", "MONEY", "PERCENT",
                          "FACILITY", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW", "LANGUAGE",
                          "NORP", "QUANTITY", "ORDINAL", "CARDINAL"},
            performance=ModelPerformance(
                f1_score=0.86,
                precision=0.87,
                recall=0.85,
                latency_ms=35.0
            ),
            source_url="https://github.com/explosion/spacy-models",
            trusted=True,
            size_mb=560.0,
            license="MIT",
            description="English multi-task CNN with large word vectors"
        )

        # SciSpacy biomedical models
        models["scispacy/en_core_sci_sm"] = ModelMetadata(
            model_id="scispacy/en_core_sci_sm",
            provider="spacy",
            version="0.5.1",
            domain="medical",
            entity_types={"ENTITY"},
            performance=ModelPerformance(
                f1_score=0.78,
                precision=0.80,
                recall=0.76,
                latency_ms=20.0
            ),
            source_url="https://allenai.github.io/scispacy/",
            trusted=True,
            size_mb=96.0,
            license="Apache-2.0",
            description="Small spaCy model trained on biomedical text",
            tags={"biomedical", "scientific"}
        )

        models["scispacy/en_ner_bc5cdr_md"] = ModelMetadata(
            model_id="scispacy/en_ner_bc5cdr_md",
            provider="spacy",
            version="0.5.1",
            domain="medical",
            entity_types={"CHEMICAL", "DISEASE"},
            performance=ModelPerformance(
                f1_score=0.89,
                precision=0.90,
                recall=0.88,
                latency_ms=45.0
            ),
            source_url="https://allenai.github.io/scispacy/",
            trusted=True,
            requires_kb=["UMLS", "RxNorm"],
            size_mb=385.0,
            license="Apache-2.0",
            description="BC5CDR corpus NER model for chemicals and diseases",
            tags={"biomedical", "chemicals", "diseases", "drugs"}
        )

        models["scispacy/en_ner_jnlpba_md"] = ModelMetadata(
            model_id="scispacy/en_ner_jnlpba_md",
            provider="spacy",
            version="0.5.1",
            domain="medical",
            entity_types={"PROTEIN", "DNA", "RNA", "CELL_LINE", "CELL_TYPE"},
            performance=ModelPerformance(
                f1_score=0.75,
                precision=0.76,
                recall=0.74,
                latency_ms=48.0
            ),
            source_url="https://allenai.github.io/scispacy/",
            trusted=True,
            size_mb=385.0,
            license="Apache-2.0",
            description="JNLPBA corpus NER model for biomedical entities",
            tags={"biomedical", "genetics", "proteins"}
        )

        models["scispacy/en_ner_bionlp13cg_md"] = ModelMetadata(
            model_id="scispacy/en_ner_bionlp13cg_md",
            provider="spacy",
            version="0.5.1",
            domain="medical",
            entity_types={
                "AMINO_ACID", "ANATOMICAL_SYSTEM", "CANCER", "CELL",
                "CELLULAR_COMPONENT", "DEVELOPING_ANATOMICAL_STRUCTURE",
                "GENE_OR_GENE_PRODUCT", "IMMATERIAL_ANATOMICAL_ENTITY",
                "MULTI_TISSUE_STRUCTURE", "ORGAN", "ORGANISM",
                "ORGANISM_SUBDIVISION", "ORGANISM_SUBSTANCE",
                "PATHOLOGICAL_FORMATION", "SIMPLE_CHEMICAL", "TISSUE"
            },
            performance=ModelPerformance(
                f1_score=0.81,
                precision=0.82,
                recall=0.80,
                latency_ms=50.0
            ),
            source_url="https://allenai.github.io/scispacy/",
            trusted=True,
            size_mb=385.0,
            license="Apache-2.0",
            description="BioNLP13CG corpus NER model for cancer genetics",
            tags={"biomedical", "cancer", "genetics"}
        )

        return models

    def list_available_models(self, domain: Optional[str] = None) -> List[ModelMetadata]:
        """Fetch available models from spaCy registry"""
        models = list(self._known_models.values())

        # Filter by domain if specified
        if domain:
            models = [m for m in models if m.domain == domain]

        return models

    async def load_model(self, model_id: str, version: str = "latest") -> NERModel:
        """Load spaCy model dynamically"""
        cache_key = f"{model_id}:{version}"

        if cache_key in self._model_cache:
            return self._model_cache[cache_key]

        # Extract model name from ID
        model_name = model_id.replace("spacy/", "").replace("scispacy/", "")

        loop = asyncio.get_event_loop()

        def load():
            try:
                nlp = spacy.load(model_name)
                return nlp
            except OSError:
                # Model not installed, attempt to download
                logger.info(f"Downloading spaCy model: {model_name}")
                spacy.cli.download(model_name)
                return spacy.load(model_name)

        nlp = await loop.run_in_executor(None, load)

        # Determine domain from known models
        domain = "general"
        if model_id in self._known_models:
            domain = self._known_models[model_id].domain

        wrapped_model = SpacyNERModel(nlp, model_id, version, domain)
        self._model_cache[cache_key] = wrapped_model

        logger.info(f"Loaded spaCy model: {model_id}")
        return wrapped_model

    def get_model_capabilities(self, model_id: str) -> ModelCapabilities:
        """Get capabilities of a specific model"""
        if model_id in self._known_models:
            meta = self._known_models[model_id]
            return ModelCapabilities(
                entity_types=meta.entity_types,
                supports_batch=True,
                supports_context=True
            )

        # Default capabilities
        return ModelCapabilities(
            entity_types=set(),
            supports_batch=True,
            supports_context=True
        )

    def get_provider_name(self) -> str:
        """Return provider name"""
        return "spacy"

    async def health_check(self) -> bool:
        """Check if provider is available"""
        return SPACY_AVAILABLE

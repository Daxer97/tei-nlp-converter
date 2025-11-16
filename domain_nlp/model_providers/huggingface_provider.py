"""
Hugging Face model provider for transformer-based NER models.

Supports loading models from Hugging Face Hub including:
- BiomedNLP models (PubMedBERT, BioBERT)
- Legal BERT models
- Domain-specific fine-tuned models
"""

import logging
import time
import asyncio
from typing import List, Optional, Set, Dict, Any
from datetime import datetime

# Lazy imports for optional dependencies
TRANSFORMERS_AVAILABLE = False
HF_API_AVAILABLE = False

try:
    from transformers import (
        AutoTokenizer,
        AutoModelForTokenClassification,
        pipeline as hf_pipeline
    )
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    pass

try:
    from huggingface_hub import HfApi, ModelFilter
    HF_API_AVAILABLE = True
except ImportError:
    pass

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


class HuggingFaceNERModel(NERModel):
    """Wrapper for Hugging Face NER pipeline"""

    def __init__(
        self,
        ner_pipeline: Any,
        model_id: str,
        version: str,
        domain: str = "general",
        entity_types: Optional[Set[str]] = None
    ):
        super().__init__(model_id, version, domain)
        self.pipeline = ner_pipeline
        self._entity_types = entity_types or set()
        self.status = ModelStatus.READY
        self.load_time = datetime.now()
        self.capabilities = self._build_capabilities()

    def _build_capabilities(self) -> ModelCapabilities:
        """Build capabilities from pipeline"""
        return ModelCapabilities(
            entity_types=self._entity_types,
            supports_batch=True,
            supports_context=True,
            max_sequence_length=512,  # Typical BERT limit
            languages={"en"}
        )

    async def extract_entities(self, text: str) -> List[Entity]:
        """Extract named entities using HF pipeline"""
        start_time = time.time()

        # Run pipeline in thread pool
        loop = asyncio.get_event_loop()

        def run_pipeline():
            return self.pipeline(text)

        results = await loop.run_in_executor(None, run_pipeline)

        entities = []
        for item in results:
            # Handle aggregated results
            entity_text = item.get("word", item.get("entity_group", ""))
            entity_type = item.get("entity_group", item.get("entity", ""))
            start = item.get("start", 0)
            end = item.get("end", len(entity_text))
            score = item.get("score", 1.0)

            # Clean up subword tokens
            if entity_text.startswith("##"):
                entity_text = entity_text[2:]

            entity = Entity(
                text=entity_text,
                type=entity_type.replace("B-", "").replace("I-", ""),
                start=start,
                end=end,
                confidence=float(score),
                model_id=self.model_id,
                sources=[self.model_id],
                metadata={
                    "raw_entity": item.get("entity", entity_type),
                    "index": item.get("index", 0)
                }
            )
            entities.append(entity)

        latency_ms = (time.time() - start_time) * 1000
        self.record_performance(latency_ms, len(entities))

        return entities

    async def extract_entities_batch(self, texts: List[str]) -> List[List[Entity]]:
        """Extract entities from multiple texts"""
        loop = asyncio.get_event_loop()

        def process_batch():
            results = []
            for text in texts:
                pipeline_results = self.pipeline(text)
                doc_entities = []
                for item in pipeline_results:
                    entity = Entity(
                        text=item.get("word", ""),
                        type=item.get("entity_group", item.get("entity", "")).replace("B-", "").replace("I-", ""),
                        start=item.get("start", 0),
                        end=item.get("end", 0),
                        confidence=float(item.get("score", 1.0)),
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
        # Release GPU memory if applicable
        if hasattr(self.pipeline, "model"):
            del self.pipeline.model
        if hasattr(self.pipeline, "tokenizer"):
            del self.pipeline.tokenizer
        logger.info(f"Cleaned up HF model: {self.model_id}")


class HuggingFaceProvider(NERModelProvider):
    """Dynamic Hugging Face model provider"""

    def __init__(self, api_token: Optional[str] = None):
        if not TRANSFORMERS_AVAILABLE:
            logger.warning("Transformers library not installed, HF provider will have limited functionality")

        self.api_token = api_token
        self._model_cache: Dict[str, HuggingFaceNERModel] = {}

        # Pre-defined model metadata for known domain-specific models
        self._known_models = self._build_known_models()

        # HF API for dynamic discovery (optional)
        self.hf_api = None
        if HF_API_AVAILABLE and api_token:
            self.hf_api = HfApi(token=api_token)

    def _build_known_models(self) -> Dict[str, ModelMetadata]:
        """Build metadata for known HF models"""
        models = {}

        # Medical/Biomedical models
        models["microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext"] = ModelMetadata(
            model_id="microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
            provider="huggingface",
            version="latest",
            domain="medical",
            entity_types={"DISEASE", "DRUG", "GENE", "PROTEIN", "SPECIES", "DNA", "RNA"},
            performance=ModelPerformance(
                f1_score=0.92,
                precision=0.91,
                recall=0.93,
                latency_ms=120.0
            ),
            source_url="https://huggingface.co/microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext",
            trusted=True,
            requires_kb=["UMLS"],
            size_mb=438.0,
            license="MIT",
            description="PubMedBERT trained on PubMed abstracts and full-text articles",
            tags={"biomedical", "medical", "pubmed"}
        )

        models["dmis-lab/biobert-v1.1"] = ModelMetadata(
            model_id="dmis-lab/biobert-v1.1",
            provider="huggingface",
            version="latest",
            domain="medical",
            entity_types={"DISEASE", "DRUG", "GENE", "SPECIES", "CELL_LINE", "CELL_TYPE"},
            performance=ModelPerformance(
                f1_score=0.87,
                precision=0.86,
                recall=0.88,
                latency_ms=110.0
            ),
            source_url="https://huggingface.co/dmis-lab/biobert-v1.1",
            trusted=True,
            requires_kb=["UMLS"],
            size_mb=438.0,
            license="Apache-2.0",
            description="BioBERT pre-trained on biomedical domain corpora",
            tags={"biomedical", "medical"}
        )

        models["allenai/scibert_scivocab_uncased"] = ModelMetadata(
            model_id="allenai/scibert_scivocab_uncased",
            provider="huggingface",
            version="latest",
            domain="scientific",
            entity_types={"ENTITY"},  # Base model, needs fine-tuning
            performance=ModelPerformance(
                f1_score=0.85,
                precision=0.84,
                recall=0.86,
                latency_ms=105.0
            ),
            source_url="https://huggingface.co/allenai/scibert_scivocab_uncased",
            trusted=True,
            size_mb=438.0,
            license="Apache-2.0",
            description="SciBERT trained on scientific text",
            tags={"scientific", "research"}
        )

        # Legal models
        models["nlpaueb/legal-bert-base-uncased"] = ModelMetadata(
            model_id="nlpaueb/legal-bert-base-uncased",
            provider="huggingface",
            version="latest",
            domain="legal",
            entity_types={"CASE_CITATION", "STATUTE", "LEGAL_ENTITY", "COURT", "JUDGE"},
            performance=ModelPerformance(
                f1_score=0.85,
                precision=0.84,
                recall=0.86,
                latency_ms=95.0
            ),
            source_url="https://huggingface.co/nlpaueb/legal-bert-base-uncased",
            trusted=True,
            requires_kb=["USC", "CFR"],
            size_mb=438.0,
            license="Apache-2.0",
            description="Legal-BERT trained on legal text from US, UK, EU",
            tags={"legal", "law"}
        )

        models["casehold/custom-legalbert"] = ModelMetadata(
            model_id="casehold/custom-legalbert",
            provider="huggingface",
            version="latest",
            domain="legal",
            entity_types={"CASE_CITATION", "STATUTE", "LEGAL_TERM", "PARTY"},
            performance=ModelPerformance(
                f1_score=0.82,
                precision=0.81,
                recall=0.83,
                latency_ms=100.0
            ),
            source_url="https://huggingface.co/casehold/custom-legalbert",
            trusted=True,
            size_mb=438.0,
            license="Apache-2.0",
            description="CaseHOLD LegalBERT for case law understanding",
            tags={"legal", "case_law"}
        )

        # Financial models
        models["yiyanghkust/finbert-tone"] = ModelMetadata(
            model_id="yiyanghkust/finbert-tone",
            provider="huggingface",
            version="latest",
            domain="financial",
            entity_types={"COMPANY", "TICKER", "MONETARY", "PERCENTAGE", "DATE"},
            performance=ModelPerformance(
                f1_score=0.86,
                precision=0.85,
                recall=0.87,
                latency_ms=90.0
            ),
            source_url="https://huggingface.co/yiyanghkust/finbert-tone",
            trusted=True,
            size_mb=438.0,
            license="Apache-2.0",
            description="FinBERT for financial sentiment and entity recognition",
            tags={"financial", "finance", "sentiment"}
        )

        # General NER models (fine-tuned)
        models["dslim/bert-base-NER"] = ModelMetadata(
            model_id="dslim/bert-base-NER",
            provider="huggingface",
            version="latest",
            domain="general",
            entity_types={"PER", "ORG", "LOC", "MISC"},
            performance=ModelPerformance(
                f1_score=0.91,
                precision=0.90,
                recall=0.92,
                latency_ms=80.0
            ),
            source_url="https://huggingface.co/dslim/bert-base-NER",
            trusted=True,
            size_mb=438.0,
            license="MIT",
            description="BERT fine-tuned for NER on CoNLL-2003",
            tags={"general", "ner"}
        )

        return models

    def list_available_models(self, domain: Optional[str] = None) -> List[ModelMetadata]:
        """List available models, optionally filtered by domain"""
        models = list(self._known_models.values())

        # Filter by domain if specified
        if domain:
            models = [m for m in models if m.domain == domain]

        # Optionally search HF Hub for more models
        if self.hf_api and domain:
            discovered = self._search_hub_models(domain)
            # Add any new models not already in known list
            existing_ids = {m.model_id for m in models}
            for model in discovered:
                if model.model_id not in existing_ids:
                    models.append(model)

        return models

    def _search_hub_models(self, domain: str) -> List[ModelMetadata]:
        """Search HF Hub for domain-specific models"""
        if not self.hf_api:
            return []

        try:
            # Map domain to search tags
            tag_mapping = {
                "medical": ["biomedical", "medical", "clinical"],
                "legal": ["legal", "law"],
                "scientific": ["scientific", "science"],
                "financial": ["financial", "finance"]
            }

            tags = tag_mapping.get(domain, [domain])
            discovered = []

            for tag in tags:
                models = list(self.hf_api.list_models(
                    filter=ModelFilter(task="token-classification", tags=tag),
                    sort="downloads",
                    direction=-1,
                    limit=10
                ))

                for model in models:
                    metadata = ModelMetadata(
                        model_id=model.modelId,
                        provider="huggingface",
                        version="latest",
                        domain=domain,
                        entity_types=set(),  # Would need to parse model card
                        performance=ModelPerformance(
                            f1_score=0.80,  # Estimated
                            latency_ms=100.0
                        ),
                        source_url=f"https://huggingface.co/{model.modelId}",
                        trusted=model.downloads > 1000,  # Trust if popular
                        description=model.pipeline_tag or ""
                    )
                    discovered.append(metadata)

            return discovered
        except Exception as e:
            logger.warning(f"HF Hub search failed: {e}")
            return []

    async def load_model(self, model_id: str, version: str = "latest") -> NERModel:
        """Load Hugging Face model dynamically"""
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError("Transformers library is required to load HF models")

        cache_key = f"{model_id}:{version}"

        if cache_key in self._model_cache:
            return self._model_cache[cache_key]

        loop = asyncio.get_event_loop()

        def load():
            revision = None if version == "latest" else version

            tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
            model = AutoModelForTokenClassification.from_pretrained(model_id, revision=revision)

            ner_pipeline = hf_pipeline(
                "ner",
                model=model,
                tokenizer=tokenizer,
                aggregation_strategy="simple"
            )

            return ner_pipeline

        pipeline = await loop.run_in_executor(None, load)

        # Get entity types from known models
        entity_types = set()
        domain = "general"
        if model_id in self._known_models:
            entity_types = self._known_models[model_id].entity_types
            domain = self._known_models[model_id].domain

        wrapped_model = HuggingFaceNERModel(
            pipeline,
            model_id,
            version,
            domain,
            entity_types
        )
        self._model_cache[cache_key] = wrapped_model

        logger.info(f"Loaded HF model: {model_id}")
        return wrapped_model

    def get_model_capabilities(self, model_id: str) -> ModelCapabilities:
        """Get capabilities of a specific model"""
        if model_id in self._known_models:
            meta = self._known_models[model_id]
            return ModelCapabilities(
                entity_types=meta.entity_types,
                supports_batch=True,
                supports_context=True,
                max_sequence_length=512
            )

        # Default capabilities
        return ModelCapabilities(
            entity_types=set(),
            supports_batch=True,
            supports_context=True,
            max_sequence_length=512
        )

    def get_provider_name(self) -> str:
        """Return provider name"""
        return "huggingface"

    async def health_check(self) -> bool:
        """Check if provider is available"""
        return TRANSFORMERS_AVAILABLE

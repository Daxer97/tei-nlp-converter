"""
Hugging Face Model Provider

Provides dynamic discovery and loading of NER models from Hugging Face Hub including:
- BiomedNLP models for medical text
- Legal-BERT for legal documents
- FinBERT for financial text
- Custom fine-tuned models
"""
from typing import List, Optional, Dict, Any
import asyncio
from datetime import datetime
import torch

try:
    from transformers import (
        AutoTokenizer,
        AutoModelForTokenClassification,
        pipeline,
        Pipeline
    )
    from huggingface_hub import HfApi, ModelFilter, list_models
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

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


class HuggingFaceNERModel(NERModel):
    """Wrapper for Hugging Face NER model"""

    def __init__(self, model_id: str, version: str, metadata: Optional[ModelMetadata] = None):
        super().__init__(model_id, version, metadata)
        self.tokenizer = None
        self.model = None
        self.ner_pipeline: Optional[Pipeline] = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    async def load(self) -> bool:
        """Load the Hugging Face model"""
        if not HF_AVAILABLE:
            logger.error("transformers library not available")
            return False

        try:
            logger.info(f"Loading Hugging Face model: {self.model_id}")

            # Extract model name (remove "huggingface/" prefix if present)
            model_name = self.model_id.replace("huggingface/", "")

            # Load tokenizer and model
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForTokenClassification.from_pretrained(model_name)

            # Move to device
            self.model.to(self.device)

            # Create pipeline
            self.ner_pipeline = pipeline(
                "ner",
                model=self.model,
                tokenizer=self.tokenizer,
                device=0 if self.device == "cuda" else -1,
                aggregation_strategy="simple"  # Aggregate subword tokens
            )

            self._loaded = True
            logger.info(f"Successfully loaded Hugging Face model: {self.model_id} on {self.device}")
            return True

        except Exception as e:
            logger.error(f"Failed to load Hugging Face model {self.model_id}: {e}")
            self._loaded = False
            return False

    async def extract_entities(self, text: str) -> List[Entity]:
        """Extract entities from text"""
        if not self._loaded or not self.ner_pipeline:
            raise RuntimeError(f"Model {self.model_id} not loaded")

        try:
            # Run NER pipeline
            results = self.ner_pipeline(text)

            entities = []
            for result in results:
                entity = Entity(
                    text=result['word'],
                    type=result['entity_group'],
                    start=result['start'],
                    end=result['end'],
                    confidence=result['score'],
                    model_id=self.model_id,
                    metadata={
                        'aggregation_strategy': 'simple'
                    }
                )
                entities.append(entity)

            return entities

        except Exception as e:
            logger.error(f"Error extracting entities with {self.model_id}: {e}")
            return []

    async def extract_entities_batch(self, texts: List[str]) -> List[List[Entity]]:
        """Extract entities from multiple texts"""
        if not self._loaded or not self.ner_pipeline:
            raise RuntimeError(f"Model {self.model_id} not loaded")

        try:
            results = []

            # Process each text
            for text in texts:
                entities = await self.extract_entities(text)
                results.append(entities)

            return results

        except Exception as e:
            logger.error(f"Error in batch extraction with {self.model_id}: {e}")
            return [[] for _ in texts]

    def get_capabilities(self) -> ModelCapabilities:
        """Get model capabilities"""
        if not self._loaded or not self.model:
            return ModelCapabilities(
                entity_types=["MISC", "PER", "ORG", "LOC"],
                supports_confidence_scores=True,
                supports_multiword_entities=True,
                supports_nested_entities=False,
                languages=["en"]
            )

        # Get entity types from model config
        label_list = self.model.config.id2label.values() if hasattr(self.model.config, 'id2label') else []

        # Extract unique entity types (remove B- and I- prefixes)
        entity_types = list(set(
            label.replace('B-', '').replace('I-', '')
            for label in label_list
            if label != 'O'  # Exclude "Outside" label
        ))

        return ModelCapabilities(
            entity_types=entity_types,
            supports_confidence_scores=True,
            supports_multiword_entities=True,
            supports_nested_entities=False,
            max_text_length=512,  # BERT-based models typically have 512 token limit
            languages=["en"]  # Most are English, but this could be detected
        )

    async def unload(self) -> bool:
        """Unload model from memory"""
        try:
            if self.model:
                # Move to CPU and delete to free GPU memory
                self.model.cpu()
                del self.model
                del self.tokenizer
                del self.ner_pipeline

                self.model = None
                self.tokenizer = None
                self.ner_pipeline = None
                self._loaded = False

                # Clear CUDA cache if using GPU
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

                logger.info(f"Unloaded Hugging Face model: {self.model_id}")
                return True

        except Exception as e:
            logger.error(f"Error unloading model {self.model_id}: {e}")

        return False


class HuggingFaceProvider(NERModelProvider):
    """Hugging Face model provider with Hub integration"""

    # Curated list of high-quality NER models on HuggingFace Hub
    CURATED_MODELS = {
        # Medical/Biomedical
        "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext": {
            "domain": "medical",
            "description": "BERT model pretrained on PubMed abstracts and full-text articles",
            "entities": ["DISEASE", "DRUG", "GENE", "PROTEIN", "CHEMICAL"],
            "f1": 0.92,
            "latency_ms": 120,
            "requires_kb": ["UMLS"]
        },
        "allenai/scibert_scivocab_uncased": {
            "domain": "medical",
            "description": "BERT model trained on scientific text",
            "entities": ["DISEASE", "CHEMICAL", "GENE", "PROTEIN"],
            "f1": 0.85,
            "latency_ms": 110,
            "requires_kb": ["UMLS"]
        },
        "dmis-lab/biobert-base-cased-v1.2": {
            "domain": "medical",
            "description": "BioBERT v1.2 for biomedical text mining",
            "entities": ["DISEASE", "DRUG", "GENE", "PROTEIN"],
            "f1": 0.89,
            "latency_ms": 115,
            "requires_kb": ["UMLS"]
        },

        # Legal
        "nlpaueb/legal-bert-base-uncased": {
            "domain": "legal",
            "description": "BERT model pretrained on legal text",
            "entities": ["CASE_CITATION", "STATUTE", "LEGAL_ENTITY", "COURT"],
            "f1": 0.85,
            "latency_ms": 95,
            "requires_kb": ["USC", "CFR"]
        },

        # General purpose (high quality)
        "dslim/bert-base-NER": {
            "domain": "general",
            "description": "Fine-tuned BERT model for Named Entity Recognition",
            "entities": ["PERSON", "LOCATION", "ORGANIZATION", "MISC"],
            "f1": 0.90,
            "latency_ms": 80
        },
        "dbmdz/bert-large-cased-finetuned-conll03-english": {
            "domain": "general",
            "description": "BERT-large fine-tuned on CoNLL-03",
            "entities": ["PERSON", "LOCATION", "ORGANIZATION", "MISC"],
            "f1": 0.92,
            "latency_ms": 150
        }
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.api_token = config.get('api_token') if config else None
        self.api = HfApi(token=self.api_token) if HF_AVAILABLE else None

    def get_provider_name(self) -> str:
        return "huggingface"

    async def list_available_models(self, domain: Optional[str] = None) -> List[ModelMetadata]:
        """
        Discover available models from Hugging Face Hub

        Args:
            domain: Optional domain filter

        Returns:
            List of model metadata
        """
        if not HF_AVAILABLE:
            logger.warning("transformers/huggingface_hub not available")
            return []

        models = []

        # Use curated list
        for model_id, model_info in self.CURATED_MODELS.items():
            # Filter by domain if specified
            if domain and model_info.get('domain') != domain:
                continue

            # Create metadata
            capabilities = ModelCapabilities(
                entity_types=model_info.get('entities', []),
                supports_confidence_scores=True,
                supports_multiword_entities=True,
                supports_nested_entities=False,
                max_text_length=512,
                languages=['en']
            )

            performance = ModelPerformanceMetrics(
                f1_score=model_info.get('f1', 0.80),
                precision=model_info.get('f1', 0.80),  # Approximate
                recall=model_info.get('f1', 0.80),  # Approximate
                latency_ms=model_info.get('latency_ms', 100)
            )

            metadata = ModelMetadata(
                model_id=f"huggingface/{model_id}",
                provider="huggingface",
                version="latest",
                domain=model_info.get('domain', 'general'),
                capabilities=capabilities,
                performance=performance,
                source_url=f"https://huggingface.co/{model_id}",
                trusted=True,  # Curated models are trusted
                requires_kb=model_info.get('requires_kb', []),
                description=model_info.get('description'),
                created_at=datetime.now()
            )

            models.append(metadata)

        # Optionally search Hub for additional models
        if self.config.get('search_hub', False):
            try:
                hub_models = await self._search_hub(domain)
                models.extend(hub_models)
            except Exception as e:
                logger.warning(f"Failed to search Hugging Face Hub: {e}")

        logger.info(f"Discovered {len(models)} Hugging Face models" + (f" for domain '{domain}'" if domain else ""))
        return models

    async def _search_hub(self, domain: Optional[str] = None) -> List[ModelMetadata]:
        """Search Hugging Face Hub for NER models"""
        if not self.api:
            return []

        try:
            # Search for token classification models
            model_filter = ModelFilter(task="token-classification")

            # Add domain-specific filters
            if domain:
                tags = []
                if domain == "medical":
                    tags = ["medical", "biomedical", "clinical"]
                elif domain == "legal":
                    tags = ["legal", "law"]
                elif domain == "financial":
                    tags = ["financial", "finance"]

                if tags:
                    model_filter.tags = tags

            # Search with limit
            model_list = list(list_models(
                filter=model_filter,
                sort="downloads",
                direction=-1,
                limit=20
            ))

            models = []
            for model_info in model_list:
                # Skip if already in curated list
                if model_info.modelId in self.CURATED_MODELS:
                    continue

                # Create basic metadata
                # Note: We can't get detailed performance metrics without downloading
                metadata = ModelMetadata(
                    model_id=f"huggingface/{model_info.modelId}",
                    provider="huggingface",
                    version="latest",
                    domain=domain or "general",
                    capabilities=ModelCapabilities(
                        entity_types=["PERSON", "ORG", "LOC", "MISC"],  # Default, actual types unknown
                        supports_confidence_scores=True,
                        supports_multiword_entities=True,
                        max_text_length=512
                    ),
                    performance=ModelPerformanceMetrics(
                        f1_score=0.80,  # Unknown, use default
                        precision=0.80,
                        recall=0.80,
                        latency_ms=100
                    ),
                    source_url=f"https://huggingface.co/{model_info.modelId}",
                    trusted=False,  # Not curated, so not automatically trusted
                    description=model_info.modelId,
                    created_at=datetime.now()
                )

                models.append(metadata)

            return models

        except Exception as e:
            logger.error(f"Error searching Hugging Face Hub: {e}")
            return []

    async def load_model(self, model_id: str, version: str = "latest") -> NERModel:
        """
        Load a specific Hugging Face model

        Args:
            model_id: Model identifier
            version: Model version/revision

        Returns:
            Loaded NER model
        """
        # Check cache
        cache_key = f"{model_id}:{version}"
        if cache_key in self.model_cache:
            logger.info(f"Using cached model: {model_id}")
            return self.model_cache[cache_key]

        # Create model instance
        model = HuggingFaceNERModel(model_id, version)

        # Load the model
        if await model.load():
            self.model_cache[cache_key] = model
            return model
        else:
            raise RuntimeError(f"Failed to load Hugging Face model: {model_id}")

    def get_model_capabilities(self, model_id: str) -> ModelCapabilities:
        """Get capabilities of a model"""

        # Extract model name
        model_name = model_id.replace("huggingface/", "")

        if model_name in self.CURATED_MODELS:
            model_info = self.CURATED_MODELS[model_name]
            return ModelCapabilities(
                entity_types=model_info.get('entities', []),
                supports_confidence_scores=True,
                supports_multiword_entities=True,
                supports_nested_entities=False,
                max_text_length=512,
                languages=['en']
            )

        # Default capabilities
        return ModelCapabilities(
            entity_types=["PERSON", "ORG", "LOC", "MISC"],
            supports_confidence_scores=True,
            supports_multiword_entities=True,
            max_text_length=512,
            languages=['en']
        )

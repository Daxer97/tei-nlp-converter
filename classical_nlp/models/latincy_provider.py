"""
LatinCy NLP Provider

Provides NLP processing for Latin texts using the LatinCy spaCy model.
LatinCy is specifically designed for Latin language processing and provides:
- Lemmatization
- POS tagging
- Morphological analysis
- Dependency parsing
"""

import asyncio
from typing import Dict, List, Any, Optional
import logging

from .base import (
    ClassicalNLPProvider,
    ClassicalProcessingResult,
    ProviderStatus,
    BotanicalTerm,
    TokenInfo,
    LATIN_BOTANICAL_TERMS
)

logger = logging.getLogger(__name__)


class LatinCyProvider(ClassicalNLPProvider):
    """
    NLP Provider using LatinCy for Latin text processing.

    LatinCy is a spaCy-based model trained on Latin texts,
    providing high-quality lemmatization and morphological analysis.
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._nlp = None
        self._model_name = config.get("model_name", "la_core_web_lg") if config else "la_core_web_lg"

    @property
    def name(self) -> str:
        return "LatinCy"

    @property
    def supported_languages(self) -> List[str]:
        return ["latin", "la"]

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "lemmatization": True,
            "pos_tagging": True,
            "morphology": True,
            "dependency_parsing": True,
            "entity_recognition": False,
            "botanical_detection": True,
            "metrical_analysis": False
        }

    async def initialize(self) -> bool:
        """Initialize LatinCy model."""
        try:
            # Import spacy in async context to avoid blocking
            loop = asyncio.get_event_loop()
            self._nlp = await loop.run_in_executor(None, self._load_model)

            if self._nlp:
                self._status = ProviderStatus.AVAILABLE
                logger.info(f"LatinCy model '{self._model_name}' loaded successfully")
                return True
            else:
                self._status = ProviderStatus.UNAVAILABLE
                return False

        except Exception as e:
            logger.error(f"Failed to initialize LatinCy: {e}")
            self._status = ProviderStatus.UNAVAILABLE
            return False

    def _load_model(self):
        """Load the spaCy model synchronously."""
        try:
            import spacy

            # Try to load LatinCy model
            try:
                nlp = spacy.load(self._model_name)
                return nlp
            except OSError:
                # Try alternative model names
                alternative_models = ["la_core_web_sm", "la_core_web_md", "latincy"]
                for model in alternative_models:
                    try:
                        nlp = spacy.load(model)
                        self._model_name = model
                        return nlp
                    except OSError:
                        continue

                # If no model found, try to create a blank Latin model
                logger.warning("LatinCy model not found, creating blank Latin model")
                nlp = spacy.blank("la")
                return nlp

        except ImportError:
            logger.error("spaCy not installed. Install with: pip install spacy")
            return None

    async def process(self, text: str, options: Dict[str, Any] = None) -> ClassicalProcessingResult:
        """Process Latin text with LatinCy."""
        if not self._nlp:
            await self.initialize()

        if not self._nlp:
            raise RuntimeError("LatinCy model not available")

        options = options or {}

        # Process text in executor to avoid blocking
        loop = asyncio.get_event_loop()
        doc = await loop.run_in_executor(None, self._nlp, text)

        # Extract all annotations
        sentences = self._extract_sentences(doc)
        tokens = self._extract_tokens(doc)
        entities = self._extract_entities(doc)
        dependencies = self._extract_dependencies(doc)
        noun_chunks = self._extract_noun_chunks(doc)
        botanical_terms = self._extract_botanical_terms(doc)

        return ClassicalProcessingResult(
            text=text,
            language="latin",
            model_used=f"LatinCy ({self._model_name})",
            sentences=sentences,
            entities=entities,
            tokens=tokens,
            dependencies=dependencies,
            noun_chunks=noun_chunks,
            botanical_terms=botanical_terms,
            metadata={
                "provider": self.name,
                "model": self._model_name,
                "token_count": len(doc),
                "sentence_count": len(list(doc.sents)) if doc.has_annotation("SENT_START") else 1
            }
        )

    def _extract_sentences(self, doc) -> List[Dict[str, Any]]:
        """Extract sentence information from doc."""
        sentences = []

        if doc.has_annotation("SENT_START"):
            for sent in doc.sents:
                tokens = []
                for token in sent:
                    tokens.append(self._token_to_dict(token))

                sentences.append({
                    "text": sent.text,
                    "start_char": sent.start_char,
                    "end_char": sent.end_char,
                    "tokens": tokens
                })
        else:
            # Single sentence fallback
            tokens = [self._token_to_dict(token) for token in doc]
            sentences.append({
                "text": doc.text,
                "start_char": 0,
                "end_char": len(doc.text),
                "tokens": tokens
            })

        return sentences

    def _token_to_dict(self, token) -> Dict[str, Any]:
        """Convert spaCy token to dictionary."""
        # Extract morphological features
        morph_str = str(token.morph) if hasattr(token, 'morph') else ""

        return {
            "text": token.text,
            "lemma": token.lemma_,
            "pos": token.pos_,
            "tag": token.tag_ if hasattr(token, 'tag_') else token.pos_,
            "morph": morph_str,
            "dep": token.dep_,
            "head": token.head.i,
            "idx": token.idx,
            "i": token.i,
            "is_punct": token.is_punct,
            "is_space": token.is_space,
            "whitespace_": token.whitespace_
        }

    def _extract_tokens(self, doc) -> List[Dict[str, Any]]:
        """Extract all tokens from doc."""
        return [self._token_to_dict(token) for token in doc]

    def _extract_entities(self, doc) -> List[Dict[str, Any]]:
        """Extract named entities from doc."""
        entities = []

        if doc.ents:
            for ent in doc.ents:
                entities.append({
                    "text": ent.text,
                    "label": ent.label_,
                    "start": ent.start,
                    "end": ent.end,
                    "start_char": ent.start_char,
                    "end_char": ent.end_char
                })

        return entities

    def _extract_dependencies(self, doc) -> List[Dict[str, Any]]:
        """Extract dependency relations from doc."""
        dependencies = []

        for token in doc:
            if token.dep_ != "ROOT" and token.head != token:
                dependencies.append({
                    "from": token.head.i,
                    "to": token.i,
                    "dep": token.dep_,
                    "from_text": token.head.text,
                    "to_text": token.text
                })

        return dependencies

    def _extract_noun_chunks(self, doc) -> List[Dict[str, Any]]:
        """Extract noun chunks from doc."""
        chunks = []

        try:
            for chunk in doc.noun_chunks:
                chunks.append({
                    "text": chunk.text,
                    "root": chunk.root.text,
                    "root_lemma": chunk.root.lemma_,
                    "start": chunk.start,
                    "end": chunk.end,
                    "start_char": chunk.start_char,
                    "end_char": chunk.end_char
                })
        except (ValueError, NotImplementedError):
            # noun_chunks may not be available for all models
            pass

        return chunks

    def _extract_botanical_terms(self, doc) -> List[BotanicalTerm]:
        """Extract botanical terms from Latin text."""
        botanical_terms = []
        term_occurrences = {}  # Track occurrences of each term

        for token in doc:
            lemma_lower = token.lemma_.lower()

            if lemma_lower in LATIN_BOTANICAL_TERMS:
                term_info = LATIN_BOTANICAL_TERMS[lemma_lower]

                if lemma_lower not in term_occurrences:
                    term_occurrences[lemma_lower] = {
                        "term": BotanicalTerm(
                            text=token.text,
                            lemma=token.lemma_,
                            scientific_name=term_info.get("scientific"),
                            common_name=term_info.get("common"),
                            start_char=token.idx,
                            end_char=token.idx + len(token.text),
                            occurrences=1,
                            positions=[f"char:{token.idx}"]
                        ),
                        "positions": [f"char:{token.idx}"]
                    }
                else:
                    term_occurrences[lemma_lower]["term"].occurrences += 1
                    term_occurrences[lemma_lower]["positions"].append(f"char:{token.idx}")

        # Collect all unique botanical terms
        for lemma, data in term_occurrences.items():
            data["term"].positions = data["positions"]
            botanical_terms.append(data["term"])

        return botanical_terms

    async def health_check(self) -> bool:
        """Check if LatinCy is operational."""
        try:
            if not self._nlp:
                return False

            # Quick test processing
            loop = asyncio.get_event_loop()
            doc = await loop.run_in_executor(None, self._nlp, "Gallia est omnis divisa")
            return len(doc) > 0

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

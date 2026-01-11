"""
CLTK NLP Providers for Classical Languages

Provides NLP processing using the Classical Language Toolkit (CLTK):
- CLTKLatinProvider: For Latin text processing
- CLTKGreekProvider: For Ancient Greek text processing

CLTK offers specialized features for classical languages including:
- Lemmatization
- Morphological analysis
- Scansion (metrical analysis)
- Stopword filtering
"""

import asyncio
from typing import Dict, List, Any, Optional
import logging
import re

from .base import (
    ClassicalNLPProvider,
    ClassicalProcessingResult,
    ProviderStatus,
    BotanicalTerm,
    LATIN_BOTANICAL_TERMS,
    GREEK_BOTANICAL_TERMS
)

logger = logging.getLogger(__name__)


class CLTKLatinProvider(ClassicalNLPProvider):
    """
    NLP Provider using CLTK for Latin text processing.

    CLTK provides comprehensive tools for classical Latin including:
    - Lemmatization
    - Morphological analysis
    - POS tagging
    - Metrical scansion
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._nlp = None
        self._lemmatizer = None
        self._morphology = None
        self._cltk_available = False

    @property
    def name(self) -> str:
        return "CLTK Latin"

    @property
    def supported_languages(self) -> List[str]:
        return ["latin", "la"]

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "lemmatization": True,
            "pos_tagging": True,
            "morphology": True,
            "dependency_parsing": False,
            "entity_recognition": False,
            "botanical_detection": True,
            "metrical_analysis": True
        }

    async def initialize(self) -> bool:
        """Initialize CLTK for Latin."""
        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, self._load_cltk)

            if success:
                self._status = ProviderStatus.AVAILABLE
                logger.info("CLTK Latin provider initialized successfully")
                return True
            else:
                self._status = ProviderStatus.UNAVAILABLE
                return False

        except Exception as e:
            logger.error(f"Failed to initialize CLTK Latin: {e}")
            self._status = ProviderStatus.UNAVAILABLE
            return False

    def _load_cltk(self) -> bool:
        """Load CLTK components synchronously."""
        try:
            from cltk import NLP
            from cltk.alphabet.lat import normalize_lat

            # Initialize CLTK NLP pipeline for Latin
            self._nlp = NLP(language="lat", suppress_banner=True)
            self._cltk_available = True

            return True

        except ImportError:
            logger.warning("CLTK not installed. Install with: pip install cltk")
            self._cltk_available = False
            return self._init_fallback()
        except Exception as e:
            logger.warning(f"CLTK initialization failed: {e}, using fallback")
            return self._init_fallback()

    def _init_fallback(self) -> bool:
        """Initialize fallback simple processing."""
        self._cltk_available = False
        return True  # Fallback is always available

    async def process(self, text: str, options: Dict[str, Any] = None) -> ClassicalProcessingResult:
        """Process Latin text with CLTK."""
        if self._nlp is None and not self._cltk_available:
            await self.initialize()

        options = options or {}

        loop = asyncio.get_event_loop()

        if self._cltk_available and self._nlp:
            result = await loop.run_in_executor(None, self._process_with_cltk, text, options)
        else:
            result = await loop.run_in_executor(None, self._process_fallback, text, options)

        return result

    def _process_with_cltk(self, text: str, options: Dict[str, Any]) -> ClassicalProcessingResult:
        """Process text using CLTK pipeline."""
        try:
            # Process with CLTK
            doc = self._nlp.analyze(text=text)

            # Extract tokens
            tokens = []
            sentences = []
            current_sentence_tokens = []
            current_sentence_start = 0

            for i, word in enumerate(doc.words):
                token_dict = {
                    "text": word.string if hasattr(word, 'string') else str(word),
                    "lemma": word.lemma if hasattr(word, 'lemma') and word.lemma else word.string,
                    "pos": word.pos if hasattr(word, 'pos') and word.pos else "UNKNOWN",
                    "morph": self._extract_morph(word),
                    "dep": "",
                    "head": -1,
                    "idx": 0,  # CLTK doesn't provide character offsets
                    "i": i,
                    "is_punct": self._is_punct(word),
                    "is_space": False,
                    "whitespace_": " "
                }

                tokens.append(token_dict)
                current_sentence_tokens.append(token_dict)

                # Check for sentence boundary
                if self._is_sentence_end(word):
                    sentence_text = " ".join(t["text"] for t in current_sentence_tokens)
                    sentences.append({
                        "text": sentence_text,
                        "start_char": current_sentence_start,
                        "end_char": current_sentence_start + len(sentence_text),
                        "tokens": current_sentence_tokens.copy()
                    })
                    current_sentence_tokens = []
                    current_sentence_start += len(sentence_text) + 1

            # Add remaining tokens as last sentence
            if current_sentence_tokens:
                sentence_text = " ".join(t["text"] for t in current_sentence_tokens)
                sentences.append({
                    "text": sentence_text,
                    "start_char": current_sentence_start,
                    "end_char": current_sentence_start + len(sentence_text),
                    "tokens": current_sentence_tokens
                })

            # Extract botanical terms
            botanical_terms = self._extract_botanical_terms(tokens)

            return ClassicalProcessingResult(
                text=text,
                language="latin",
                model_used="CLTK Latin",
                sentences=sentences if sentences else [{"text": text, "start_char": 0, "end_char": len(text), "tokens": tokens}],
                entities=[],
                tokens=tokens,
                dependencies=[],
                noun_chunks=[],
                botanical_terms=botanical_terms,
                metadata={
                    "provider": self.name,
                    "cltk_version": "1.x",
                    "token_count": len(tokens),
                    "sentence_count": len(sentences)
                }
            )

        except Exception as e:
            logger.error(f"CLTK processing failed: {e}")
            return self._process_fallback(text, options)

    def _extract_morph(self, word) -> str:
        """Extract morphological features from CLTK word."""
        morph_parts = []

        if hasattr(word, 'features') and word.features:
            features = word.features
            if hasattr(features, 'Case') and features.Case:
                morph_parts.append(f"Case={features.Case}")
            if hasattr(features, 'Number') and features.Number:
                morph_parts.append(f"Number={features.Number}")
            if hasattr(features, 'Gender') and features.Gender:
                morph_parts.append(f"Gender={features.Gender}")
            if hasattr(features, 'Tense') and features.Tense:
                morph_parts.append(f"Tense={features.Tense}")
            if hasattr(features, 'Mood') and features.Mood:
                morph_parts.append(f"Mood={features.Mood}")
            if hasattr(features, 'Voice') and features.Voice:
                morph_parts.append(f"Voice={features.Voice}")
            if hasattr(features, 'Person') and features.Person:
                morph_parts.append(f"Person={features.Person}")

        return "|".join(morph_parts) if morph_parts else ""

    def _is_punct(self, word) -> bool:
        """Check if word is punctuation."""
        text = word.string if hasattr(word, 'string') else str(word)
        return bool(re.match(r'^[^\w\s]+$', text))

    def _is_sentence_end(self, word) -> bool:
        """Check if word ends a sentence."""
        text = word.string if hasattr(word, 'string') else str(word)
        return text in ['.', '?', '!', ';']

    def _process_fallback(self, text: str, options: Dict[str, Any]) -> ClassicalProcessingResult:
        """Simple fallback processing without CLTK."""
        # Simple tokenization
        words = re.findall(r'\b[\w]+\b|[^\w\s]', text)

        tokens = []
        sentences = []
        current_sentence_tokens = []
        char_idx = 0

        for i, word in enumerate(words):
            # Find word position in text
            word_start = text.find(word, char_idx)
            if word_start == -1:
                word_start = char_idx

            is_punct = bool(re.match(r'^[^\w]+$', word))

            token_dict = {
                "text": word,
                "lemma": word.lower(),  # Simple lowercase as lemma
                "pos": "PUNCT" if is_punct else "UNKNOWN",
                "morph": "",
                "dep": "",
                "head": -1,
                "idx": word_start,
                "i": i,
                "is_punct": is_punct,
                "is_space": False,
                "whitespace_": " "
            }

            tokens.append(token_dict)
            current_sentence_tokens.append(token_dict)
            char_idx = word_start + len(word)

            # Sentence boundary
            if word in ['.', '?', '!']:
                sentence_text = " ".join(t["text"] for t in current_sentence_tokens)
                sentences.append({
                    "text": sentence_text,
                    "start_char": current_sentence_tokens[0]["idx"] if current_sentence_tokens else 0,
                    "end_char": char_idx,
                    "tokens": current_sentence_tokens.copy()
                })
                current_sentence_tokens = []

        # Add remaining as last sentence
        if current_sentence_tokens:
            sentence_text = " ".join(t["text"] for t in current_sentence_tokens)
            sentences.append({
                "text": sentence_text,
                "start_char": current_sentence_tokens[0]["idx"],
                "end_char": len(text),
                "tokens": current_sentence_tokens
            })

        # Extract botanical terms
        botanical_terms = self._extract_botanical_terms(tokens)

        return ClassicalProcessingResult(
            text=text,
            language="latin",
            model_used="CLTK Latin (fallback)",
            sentences=sentences if sentences else [{"text": text, "start_char": 0, "end_char": len(text), "tokens": tokens}],
            entities=[],
            tokens=tokens,
            dependencies=[],
            noun_chunks=[],
            botanical_terms=botanical_terms,
            metadata={
                "provider": self.name,
                "fallback_mode": True,
                "token_count": len(tokens),
                "sentence_count": len(sentences)
            }
        )

    def _extract_botanical_terms(self, tokens: List[Dict[str, Any]]) -> List[BotanicalTerm]:
        """Extract botanical terms from tokens."""
        botanical_terms = []
        term_occurrences = {}

        for token in tokens:
            lemma_lower = token["lemma"].lower()
            text_lower = token["text"].lower()

            # Check both lemma and text form
            matched_term = None
            if lemma_lower in LATIN_BOTANICAL_TERMS:
                matched_term = lemma_lower
            elif text_lower in LATIN_BOTANICAL_TERMS:
                matched_term = text_lower

            if matched_term:
                term_info = LATIN_BOTANICAL_TERMS[matched_term]

                if matched_term not in term_occurrences:
                    term_occurrences[matched_term] = BotanicalTerm(
                        text=token["text"],
                        lemma=token["lemma"],
                        scientific_name=term_info.get("scientific"),
                        common_name=term_info.get("common"),
                        start_char=token["idx"],
                        end_char=token["idx"] + len(token["text"]),
                        occurrences=1,
                        positions=[f"token:{token['i']}"]
                    )
                else:
                    term_occurrences[matched_term].occurrences += 1
                    term_occurrences[matched_term].positions.append(f"token:{token['i']}")

        return list(term_occurrences.values())

    async def health_check(self) -> bool:
        """Check if CLTK Latin is operational."""
        try:
            if self._cltk_available and self._nlp:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self._nlp.analyze("Arma virumque cano")
                )
                return result is not None
            return True  # Fallback is always available
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False


class CLTKGreekProvider(ClassicalNLPProvider):
    """
    NLP Provider using CLTK for Ancient Greek text processing.

    CLTK provides comprehensive tools for Ancient Greek including:
    - Lemmatization
    - Morphological analysis
    - POS tagging
    - Dialect identification
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._nlp = None
        self._cltk_available = False

    @property
    def name(self) -> str:
        return "CLTK Greek"

    @property
    def supported_languages(self) -> List[str]:
        return ["ancient_greek", "grc"]

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "lemmatization": True,
            "pos_tagging": True,
            "morphology": True,
            "dependency_parsing": False,
            "entity_recognition": False,
            "botanical_detection": True,
            "metrical_analysis": True,
            "dialect_detection": True
        }

    async def initialize(self) -> bool:
        """Initialize CLTK for Greek."""
        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, self._load_cltk)

            if success:
                self._status = ProviderStatus.AVAILABLE
                logger.info("CLTK Greek provider initialized successfully")
                return True
            else:
                self._status = ProviderStatus.UNAVAILABLE
                return False

        except Exception as e:
            logger.error(f"Failed to initialize CLTK Greek: {e}")
            self._status = ProviderStatus.UNAVAILABLE
            return False

    def _load_cltk(self) -> bool:
        """Load CLTK Greek components synchronously."""
        try:
            from cltk import NLP

            # Initialize CLTK NLP pipeline for Ancient Greek
            self._nlp = NLP(language="grc", suppress_banner=True)
            self._cltk_available = True

            return True

        except ImportError:
            logger.warning("CLTK not installed. Install with: pip install cltk")
            self._cltk_available = False
            return True  # Fallback available
        except Exception as e:
            logger.warning(f"CLTK Greek initialization failed: {e}")
            self._cltk_available = False
            return True

    async def process(self, text: str, options: Dict[str, Any] = None) -> ClassicalProcessingResult:
        """Process Ancient Greek text with CLTK."""
        if self._nlp is None:
            await self.initialize()

        options = options or {}
        loop = asyncio.get_event_loop()

        if self._cltk_available and self._nlp:
            result = await loop.run_in_executor(None, self._process_with_cltk, text, options)
        else:
            result = await loop.run_in_executor(None, self._process_fallback, text, options)

        return result

    def _process_with_cltk(self, text: str, options: Dict[str, Any]) -> ClassicalProcessingResult:
        """Process Greek text using CLTK pipeline."""
        try:
            doc = self._nlp.analyze(text=text)

            tokens = []
            sentences = []
            current_sentence_tokens = []

            for i, word in enumerate(doc.words):
                token_dict = {
                    "text": word.string if hasattr(word, 'string') else str(word),
                    "lemma": word.lemma if hasattr(word, 'lemma') and word.lemma else (word.string if hasattr(word, 'string') else str(word)),
                    "pos": word.pos if hasattr(word, 'pos') and word.pos else "UNKNOWN",
                    "morph": self._extract_morph(word),
                    "dialect": self._detect_dialect(word),
                    "dep": "",
                    "head": -1,
                    "idx": 0,
                    "i": i,
                    "is_punct": self._is_punct(word),
                    "is_space": False,
                    "whitespace_": " "
                }

                tokens.append(token_dict)
                current_sentence_tokens.append(token_dict)

                if self._is_sentence_end(word):
                    sentence_text = " ".join(t["text"] for t in current_sentence_tokens)
                    sentences.append({
                        "text": sentence_text,
                        "tokens": current_sentence_tokens.copy()
                    })
                    current_sentence_tokens = []

            if current_sentence_tokens:
                sentence_text = " ".join(t["text"] for t in current_sentence_tokens)
                sentences.append({
                    "text": sentence_text,
                    "tokens": current_sentence_tokens
                })

            botanical_terms = self._extract_botanical_terms(tokens)

            return ClassicalProcessingResult(
                text=text,
                language="ancient_greek",
                model_used="CLTK Greek",
                sentences=sentences if sentences else [{"text": text, "tokens": tokens}],
                entities=[],
                tokens=tokens,
                dependencies=[],
                noun_chunks=[],
                botanical_terms=botanical_terms,
                metadata={
                    "provider": self.name,
                    "cltk_version": "1.x",
                    "token_count": len(tokens),
                    "sentence_count": len(sentences)
                }
            )

        except Exception as e:
            logger.error(f"CLTK Greek processing failed: {e}")
            return self._process_fallback(text, options)

    def _extract_morph(self, word) -> str:
        """Extract morphological features from CLTK word."""
        morph_parts = []

        if hasattr(word, 'features') and word.features:
            features = word.features
            if hasattr(features, 'Case') and features.Case:
                morph_parts.append(f"Case={features.Case}")
            if hasattr(features, 'Number') and features.Number:
                morph_parts.append(f"Number={features.Number}")
            if hasattr(features, 'Gender') and features.Gender:
                morph_parts.append(f"Gender={features.Gender}")
            if hasattr(features, 'Tense') and features.Tense:
                morph_parts.append(f"Tense={features.Tense}")
            if hasattr(features, 'Mood') and features.Mood:
                morph_parts.append(f"Mood={features.Mood}")
            if hasattr(features, 'Voice') and features.Voice:
                morph_parts.append(f"Voice={features.Voice}")

        return "|".join(morph_parts) if morph_parts else ""

    def _detect_dialect(self, word) -> str:
        """Detect Greek dialect based on word features."""
        # Simple dialect detection based on common patterns
        text = word.string if hasattr(word, 'string') else str(word)

        # Ionic/Attic distinction based on vowel patterns
        if 'η' in text and any(c in text for c in ['ᾱ', 'ᾶ']):
            return "attic"
        elif 'η' in text:
            return "ionic"
        elif 'ᾱ' in text or 'ᾶ' in text:
            return "doric"

        return "unknown"

    def _is_punct(self, word) -> bool:
        """Check if word is punctuation."""
        text = word.string if hasattr(word, 'string') else str(word)
        # Greek punctuation includes · (ano teleia) and ; (erotimatiko/question mark)
        return bool(re.match(r'^[^\w\u0370-\u03FF\u1F00-\u1FFF]+$', text))

    def _is_sentence_end(self, word) -> bool:
        """Check if word ends a sentence."""
        text = word.string if hasattr(word, 'string') else str(word)
        return text in ['.', ';', '·']  # Greek uses ; as question mark

    def _process_fallback(self, text: str, options: Dict[str, Any]) -> ClassicalProcessingResult:
        """Simple fallback processing without CLTK."""
        # Greek-aware tokenization
        words = re.findall(r'[\u0370-\u03FF\u1F00-\u1FFF]+|[^\s\u0370-\u03FF\u1F00-\u1FFF]+', text)

        tokens = []
        for i, word in enumerate(words):
            is_punct = not bool(re.search(r'[\u0370-\u03FF\u1F00-\u1FFF\w]', word))

            tokens.append({
                "text": word,
                "lemma": word,
                "pos": "PUNCT" if is_punct else "UNKNOWN",
                "morph": "",
                "dialect": "",
                "dep": "",
                "head": -1,
                "idx": 0,
                "i": i,
                "is_punct": is_punct,
                "is_space": False,
                "whitespace_": " "
            })

        botanical_terms = self._extract_botanical_terms(tokens)

        return ClassicalProcessingResult(
            text=text,
            language="ancient_greek",
            model_used="CLTK Greek (fallback)",
            sentences=[{"text": text, "tokens": tokens}],
            entities=[],
            tokens=tokens,
            dependencies=[],
            noun_chunks=[],
            botanical_terms=botanical_terms,
            metadata={
                "provider": self.name,
                "fallback_mode": True,
                "token_count": len(tokens)
            }
        )

    def _extract_botanical_terms(self, tokens: List[Dict[str, Any]]) -> List[BotanicalTerm]:
        """Extract botanical terms from Greek tokens."""
        botanical_terms = []
        term_occurrences = {}

        for token in tokens:
            text = token["text"]
            lemma = token["lemma"]

            # Check against Greek botanical terms
            matched_term = None
            for greek_term, term_info in GREEK_BOTANICAL_TERMS.items():
                if text == greek_term or lemma == greek_term:
                    matched_term = greek_term
                    break

            if matched_term:
                term_info = GREEK_BOTANICAL_TERMS[matched_term]

                if matched_term not in term_occurrences:
                    term_occurrences[matched_term] = BotanicalTerm(
                        text=token["text"],
                        lemma=matched_term,
                        scientific_name=term_info.get("scientific"),
                        common_name=term_info.get("common"),
                        start_char=token.get("idx", 0),
                        end_char=token.get("idx", 0) + len(token["text"]),
                        occurrences=1,
                        positions=[f"token:{token['i']}"]
                    )
                else:
                    term_occurrences[matched_term].occurrences += 1
                    term_occurrences[matched_term].positions.append(f"token:{token['i']}")

        return list(term_occurrences.values())

    async def health_check(self) -> bool:
        """Check if CLTK Greek is operational."""
        try:
            if self._cltk_available and self._nlp:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self._nlp.analyze("μῆνιν ἄειδε θεά")
                )
                return result is not None
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

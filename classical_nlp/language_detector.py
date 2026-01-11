"""
Language Detection for Classical Languages

Detects whether text is in Latin or Ancient Greek based on:
1. Character analysis (Greek Unicode ranges)
2. N-gram frequency patterns
3. Stop word identification
"""

import re
import unicodedata
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class ClassicalLanguage(str, Enum):
    """Supported classical languages."""
    LATIN = "latin"
    ANCIENT_GREEK = "ancient_greek"
    UNKNOWN = "unknown"


@dataclass
class DetectionResult:
    """Result of language detection."""
    language: ClassicalLanguage
    confidence: float
    greek_char_ratio: float
    latin_char_ratio: float
    details: Dict[str, any]


# Greek Unicode ranges
GREEK_BASIC = (0x0370, 0x03FF)  # Greek and Coptic
GREEK_EXTENDED = (0x1F00, 0x1FFF)  # Greek Extended

# Latin stop words (high frequency)
LATIN_STOPWORDS = {
    'et', 'in', 'non', 'ad', 'est', 'ut', 'cum', 'sed', 'per', 'ex',
    'de', 'ab', 'ac', 'aut', 'atque', 'qui', 'quae', 'quod', 'quo',
    'enim', 'autem', 'vel', 'nec', 'neque', 'si', 'dum', 'tamen',
    'iam', 'hic', 'haec', 'hoc', 'ille', 'illa', 'illud', 'ipse',
    'ego', 'tu', 'nos', 'vos', 'me', 'te', 'se', 'mihi', 'tibi',
    'sibi', 'nobis', 'vobis', 'esse', 'sum', 'fui', 'eram', 'ero',
}

# Greek stop words (high frequency)
GREEK_STOPWORDS = {
    'καί', 'καὶ', 'δέ', 'δὲ', 'τό', 'τὸ', 'τῆς', 'τοῦ', 'ὁ', 'ἡ',
    'τά', 'τὰ', 'τήν', 'τὴν', 'τόν', 'τὸν', 'εἰς', 'ἐν', 'ἐπί',
    'ἐπὶ', 'πρός', 'πρὸς', 'ἀπό', 'ἀπὸ', 'διά', 'διὰ', 'μετά',
    'μετὰ', 'οὐ', 'οὐκ', 'μή', 'μὴ', 'ὡς', 'γάρ', 'γὰρ', 'ἀλλά',
    'ἀλλὰ', 'τε', 'μέν', 'μὲν', 'αὐτός', 'αὐτὸς', 'οὗτος', 'ἐστί',
}

# Common Latin bigrams and trigrams
LATIN_NGRAMS = {
    'que', 'orum', 'arum', 'ibus', 'tion', 'atio', 'ment', 'tio',
    'um', 'us', 'is', 'it', 'ae', 'am', 'os', 'as', 'em', 'es',
}

# Common Greek bigrams and trigrams
GREEK_NGRAMS = {
    'ται', 'της', 'του', 'ους', 'ων', 'αι', 'οι', 'ον', 'ας', 'ες',
    'εν', 'ην', 'ος', 'ις', 'μεν', 'σιν', 'σαν', 'θαι', 'ειν',
}


class ClassicalLanguageDetector:
    """
    Detector for classical languages (Latin and Ancient Greek).

    Uses multiple heuristics:
    1. Character-based detection (Greek Unicode ranges)
    2. Stop word analysis
    3. N-gram frequency patterns
    """

    def __init__(self, greek_threshold: float = 0.1):
        """
        Initialize the detector.

        Args:
            greek_threshold: Minimum ratio of Greek characters to classify as Greek
        """
        self.greek_threshold = greek_threshold

    def detect(self, text: str) -> DetectionResult:
        """
        Detect the language of the given text.

        Args:
            text: The text to analyze

        Returns:
            DetectionResult with language classification and confidence
        """
        if not text or not text.strip():
            return DetectionResult(
                language=ClassicalLanguage.UNKNOWN,
                confidence=0.0,
                greek_char_ratio=0.0,
                latin_char_ratio=0.0,
                details={"error": "Empty text"}
            )

        # Step 1: Character analysis
        char_stats = self._analyze_characters(text)

        # Step 2: If significant Greek characters, it's Greek
        if char_stats['greek_ratio'] >= self.greek_threshold:
            confidence = min(0.95, 0.5 + char_stats['greek_ratio'])
            return DetectionResult(
                language=ClassicalLanguage.ANCIENT_GREEK,
                confidence=confidence,
                greek_char_ratio=char_stats['greek_ratio'],
                latin_char_ratio=char_stats['latin_ratio'],
                details={
                    "method": "character_analysis",
                    "greek_chars": char_stats['greek_count'],
                    "total_chars": char_stats['total_alpha']
                }
            )

        # Step 3: Analyze stop words
        stopword_result = self._analyze_stopwords(text)

        # Step 4: Analyze n-grams
        ngram_result = self._analyze_ngrams(text)

        # Step 5: Combine signals for Latin detection
        latin_signals = [
            stopword_result['latin_score'] > stopword_result['greek_score'],
            ngram_result['latin_score'] > ngram_result['greek_score'],
            char_stats['latin_ratio'] > 0.8
        ]

        latin_score = sum(latin_signals) / len(latin_signals)

        if latin_score >= 0.5:
            # Calculate confidence based on multiple signals
            confidence = (
                0.3 * (1 if char_stats['latin_ratio'] > 0.8 else 0.5) +
                0.4 * min(1.0, stopword_result['latin_score'] * 2) +
                0.3 * min(1.0, ngram_result['latin_score'] * 2)
            )
            return DetectionResult(
                language=ClassicalLanguage.LATIN,
                confidence=min(0.95, confidence),
                greek_char_ratio=char_stats['greek_ratio'],
                latin_char_ratio=char_stats['latin_ratio'],
                details={
                    "method": "multi_signal",
                    "stopword_latin_score": stopword_result['latin_score'],
                    "ngram_latin_score": ngram_result['latin_score'],
                    "latin_stopwords_found": stopword_result['latin_matches']
                }
            )

        # Cannot determine with confidence
        return DetectionResult(
            language=ClassicalLanguage.UNKNOWN,
            confidence=0.3,
            greek_char_ratio=char_stats['greek_ratio'],
            latin_char_ratio=char_stats['latin_ratio'],
            details={
                "method": "inconclusive",
                "stopword_result": stopword_result,
                "ngram_result": ngram_result
            }
        )

    def _analyze_characters(self, text: str) -> Dict[str, float]:
        """Analyze character composition of text."""
        greek_count = 0
        latin_count = 0
        total_alpha = 0

        for char in text:
            if char.isalpha():
                total_alpha += 1
                code = ord(char)

                # Check Greek ranges
                if (GREEK_BASIC[0] <= code <= GREEK_BASIC[1] or
                    GREEK_EXTENDED[0] <= code <= GREEK_EXTENDED[1]):
                    greek_count += 1
                # Check Latin (basic ASCII letters)
                elif (65 <= code <= 90 or  # A-Z
                      97 <= code <= 122 or  # a-z
                      192 <= code <= 255):  # Extended Latin
                    latin_count += 1

        if total_alpha == 0:
            return {
                'greek_count': 0,
                'latin_count': 0,
                'total_alpha': 0,
                'greek_ratio': 0.0,
                'latin_ratio': 0.0
            }

        return {
            'greek_count': greek_count,
            'latin_count': latin_count,
            'total_alpha': total_alpha,
            'greek_ratio': greek_count / total_alpha,
            'latin_ratio': latin_count / total_alpha
        }

    def _analyze_stopwords(self, text: str) -> Dict[str, any]:
        """Analyze presence of language-specific stop words."""
        # Normalize text for matching
        words = re.findall(r'\b[\w\u0370-\u03FF\u1F00-\u1FFF]+\b', text.lower())

        latin_matches = []
        greek_matches = []

        for word in words:
            if word in LATIN_STOPWORDS:
                latin_matches.append(word)
            if word in GREEK_STOPWORDS:
                greek_matches.append(word)

        total_words = len(words) if words else 1

        return {
            'latin_score': len(latin_matches) / total_words,
            'greek_score': len(greek_matches) / total_words,
            'latin_matches': latin_matches,
            'greek_matches': greek_matches
        }

    def _analyze_ngrams(self, text: str) -> Dict[str, float]:
        """Analyze n-gram patterns for language identification."""
        # Clean text
        text_clean = re.sub(r'[^\w\u0370-\u03FF\u1F00-\u1FFF]', '', text.lower())

        latin_score = 0
        greek_score = 0

        # Check for Latin n-grams
        for ngram in LATIN_NGRAMS:
            if ngram in text_clean:
                latin_score += text_clean.count(ngram)

        # Check for Greek n-grams
        for ngram in GREEK_NGRAMS:
            if ngram in text_clean:
                greek_score += text_clean.count(ngram)

        # Normalize by text length
        text_len = len(text_clean) if text_clean else 1

        return {
            'latin_score': latin_score / text_len,
            'greek_score': greek_score / text_len
        }


def detect_classical_language(text: str) -> str:
    """
    Simple function to detect classical language.

    Args:
        text: Text to analyze

    Returns:
        'latin', 'ancient_greek', or 'unknown'
    """
    detector = ClassicalLanguageDetector()
    result = detector.detect(text)
    return result.language.value

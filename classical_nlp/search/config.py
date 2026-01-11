"""
Search Configuration and Data Classes

Defines the configuration options and result structures for
occurrence searching in classical texts.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List


class SearchMode(Enum):
    """Available search modes."""
    EXACT = "exact"  # Exact string match
    LEMMATIZED = "lemmatized"  # Match by lemma (all inflected forms)
    REGEX = "regex"  # Regular expression search
    FUZZY = "fuzzy"  # Fuzzy matching with Levenshtein distance


@dataclass
class SearchResult:
    """
    Represents a single occurrence found in the text.

    Attributes:
        word_found: The actual word form found
        context_before: Words before the occurrence
        context_after: Words after the occurrence
        position: Character position in text
        line_number: Line number (1-indexed)
        section_ref: TEI section reference (e.g., "div.1.s.3")
        lemma: Dictionary form of the word
        pos_tag: Part of speech tag
        morph: Morphological features
        token_index: Index of the token in the document
        sentence_index: Index of the sentence containing the match
        match_score: Similarity score for fuzzy matches (0-1)
    """
    word_found: str
    context_before: str
    context_after: str
    position: int
    line_number: int
    section_ref: Optional[str] = None
    lemma: Optional[str] = None
    pos_tag: Optional[str] = None
    morph: Optional[str] = None
    token_index: int = 0
    sentence_index: int = 0
    match_score: float = 1.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "word_found": self.word_found,
            "context_before": self.context_before,
            "context_after": self.context_after,
            "position": self.position,
            "line_number": self.line_number,
            "section_ref": self.section_ref,
            "lemma": self.lemma,
            "pos_tag": self.pos_tag,
            "morph": self.morph,
            "token_index": self.token_index,
            "sentence_index": self.sentence_index,
            "match_score": self.match_score
        }


@dataclass
class SearchConfig:
    """
    Configuration for occurrence search.

    Attributes:
        query: The search term or pattern
        mode: Search mode (exact, lemmatized, regex, fuzzy)
        words_before: Number of context words before match
        words_after: Number of context words after match
        fuzzy_threshold: Minimum similarity for fuzzy matches (0-1)
        case_sensitive: Whether search is case sensitive
        show_position: Include position information in results
        include_morph: Include morphological analysis in results
        max_results: Maximum number of results to return
    """
    query: str
    mode: SearchMode = SearchMode.EXACT
    words_before: int = 5
    words_after: int = 5
    fuzzy_threshold: float = 0.8
    case_sensitive: bool = False
    show_position: bool = True
    include_morph: bool = True
    max_results: int = 1000

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "query": self.query,
            "mode": self.mode.value,
            "words_before": self.words_before,
            "words_after": self.words_after,
            "fuzzy_threshold": self.fuzzy_threshold,
            "case_sensitive": self.case_sensitive,
            "show_position": self.show_position,
            "include_morph": self.include_morph,
            "max_results": self.max_results
        }


@dataclass
class SearchStatistics:
    """
    Statistics about search results.

    Attributes:
        total_occurrences: Total number of matches found
        total_words: Total words in document
        frequency: Percentage of occurrences
        unique_forms: Number of unique word forms matching
        forms_distribution: Count of each word form
        sentence_distribution: Distribution across sentences
        context_words: Common words appearing in context
    """
    total_occurrences: int
    total_words: int
    frequency: float
    unique_forms: int
    forms_distribution: dict = field(default_factory=dict)
    sentence_distribution: dict = field(default_factory=dict)
    context_words: List[tuple] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total_occurrences": self.total_occurrences,
            "total_words": self.total_words,
            "frequency": self.frequency,
            "unique_forms": self.unique_forms,
            "forms_distribution": self.forms_distribution,
            "sentence_distribution": self.sentence_distribution,
            "context_words": self.context_words
        }

"""
Occurrence Searcher for Classical Texts

Provides comprehensive search functionality across TEI documents
with multiple search modes and context extraction.
"""

from typing import Dict, List, Any, Optional, Tuple
from collections import Counter
import re
import logging

from .config import SearchConfig, SearchMode, SearchResult, SearchStatistics

logger = logging.getLogger(__name__)


class OccurrenceSearcher:
    """
    Search engine for finding occurrences in TEI documents.

    Supports multiple search modes:
    - Exact: Case-insensitive exact match
    - Lemmatized: Match all forms sharing the same lemma
    - Regex: Regular expression matching
    - Fuzzy: Approximate matching with similarity threshold

    Example:
        >>> searcher = OccurrenceSearcher(tei_document)
        >>> config = SearchConfig(query="vitis", mode=SearchMode.LEMMATIZED)
        >>> results = searcher.search(config)
    """

    def __init__(self, document: Dict[str, Any] = None, tei_xml: str = None):
        """
        Initialize the searcher with a document.

        Args:
            document: NLP processing result dictionary with tokens
            tei_xml: Raw TEI XML string (parsed if document not provided)
        """
        self.document = document
        self.tei_xml = tei_xml
        self.words: List[Dict[str, Any]] = []
        self.text: str = ""

        if document:
            self._extract_words_from_document()
        elif tei_xml:
            self._parse_tei_xml()

    def _extract_words_from_document(self):
        """Extract word data from NLP processing result."""
        if not self.document:
            return

        self.text = self.document.get('text', '')
        self.words = []
        char_offset = 0

        sentences = self.document.get('sentences', [])

        for sent_idx, sentence in enumerate(sentences):
            tokens = sentence.get('tokens', [])

            for token in tokens:
                if token.get('is_space'):
                    continue

                word_data = {
                    'text': token.get('text', ''),
                    'lemma': token.get('lemma', ''),
                    'pos': token.get('pos', ''),
                    'morph': token.get('morph', ''),
                    'char_position': token.get('idx', char_offset),
                    'token_index': token.get('i', len(self.words)),
                    'sentence_index': sent_idx,
                    'tei_ref': f"div.1.s.{sent_idx + 1}.w.{token.get('i', 0) + 1}",
                    'line': self._estimate_line_number(token.get('idx', char_offset))
                }
                self.words.append(word_data)
                char_offset = token.get('idx', char_offset) + len(token.get('text', '')) + 1

    def _parse_tei_xml(self):
        """Parse TEI XML to extract word data."""
        if not self.tei_xml:
            return

        try:
            from defusedxml import ElementTree as ET

            root = ET.fromstring(self.tei_xml)
            ns = {'tei': 'http://www.tei-c.org/ns/1.0'}

            # Extract all word elements
            self.words = []
            word_idx = 0

            for w_elem in root.findall('.//tei:w', ns):
                word_data = {
                    'text': w_elem.text or '',
                    'lemma': w_elem.get('lemma', ''),
                    'pos': w_elem.get('pos', ''),
                    'morph': w_elem.get('msd', ''),
                    'char_position': 0,
                    'token_index': word_idx,
                    'tei_ref': w_elem.get('{http://www.w3.org/XML/1998/namespace}id', ''),
                    'line': 0
                }
                self.words.append(word_data)
                word_idx += 1

            # Reconstruct text
            self.text = ' '.join(w['text'] for w in self.words)

        except Exception as e:
            logger.error(f"Failed to parse TEI XML: {e}")

    def _estimate_line_number(self, char_position: int) -> int:
        """Estimate line number from character position."""
        if not self.text:
            return 1

        text_before = self.text[:char_position]
        return text_before.count('\n') + 1

    def search(self, config: SearchConfig) -> List[SearchResult]:
        """
        Execute search according to the specified configuration.

        Args:
            config: SearchConfig with query and options

        Returns:
            List of SearchResult objects
        """
        if not self.words:
            logger.warning("No words to search in")
            return []

        # Dispatch to appropriate search method
        if config.mode == SearchMode.EXACT:
            results = self._search_exact(config)
        elif config.mode == SearchMode.LEMMATIZED:
            results = self._search_lemmatized(config)
        elif config.mode == SearchMode.REGEX:
            results = self._search_regex(config)
        elif config.mode == SearchMode.FUZZY:
            results = self._search_fuzzy(config)
        else:
            logger.error(f"Unknown search mode: {config.mode}")
            return []

        # Limit results
        if len(results) > config.max_results:
            results = results[:config.max_results]

        return results

    def _search_exact(self, config: SearchConfig) -> List[SearchResult]:
        """
        Perform exact string matching.

        Case-insensitive by default.
        """
        results = []
        query = config.query if config.case_sensitive else config.query.lower()

        for i, word_data in enumerate(self.words):
            text = word_data['text'] if config.case_sensitive else word_data['text'].lower()

            if text == query:
                result = self._build_result(i, config)
                results.append(result)

        return results

    def _search_lemmatized(self, config: SearchConfig) -> List[SearchResult]:
        """
        Search by lemma to find all inflected forms.

        First tries to find the lemma of the query, then finds
        all words with the same lemma.
        """
        results = []
        query = config.query if config.case_sensitive else config.query.lower()

        # Find the target lemma
        target_lemma = self._get_lemma(query)

        for i, word_data in enumerate(self.words):
            word_lemma = word_data.get('lemma', '')
            if not config.case_sensitive:
                word_lemma = word_lemma.lower()

            if word_lemma == target_lemma:
                result = self._build_result(i, config)
                results.append(result)

        return results

    def _get_lemma(self, query: str) -> str:
        """
        Get the lemma for a query word.

        Searches for the query in the document and returns its lemma,
        or returns the query itself if not found.
        """
        query_lower = query.lower()

        # Check if query is already a lemma
        for word_data in self.words:
            if word_data.get('lemma', '').lower() == query_lower:
                return query_lower

        # Find word matching query and return its lemma
        for word_data in self.words:
            if word_data['text'].lower() == query_lower:
                return word_data.get('lemma', query).lower()

        return query_lower

    def _search_regex(self, config: SearchConfig) -> List[SearchResult]:
        """
        Search using regular expression pattern.
        """
        results = []

        try:
            flags = 0 if config.case_sensitive else re.IGNORECASE
            pattern = re.compile(config.query, flags)
        except re.error as e:
            logger.error(f"Invalid regex pattern: {e}")
            return []

        for i, word_data in enumerate(self.words):
            if pattern.search(word_data['text']):
                result = self._build_result(i, config)
                results.append(result)

        return results

    def _search_fuzzy(self, config: SearchConfig) -> List[SearchResult]:
        """
        Search with fuzzy matching using sequence similarity.
        """
        results = []
        query = config.query if config.case_sensitive else config.query.lower()

        for i, word_data in enumerate(self.words):
            text = word_data['text'] if config.case_sensitive else word_data['text'].lower()

            similarity = self._calculate_similarity(query, text)

            if similarity >= config.fuzzy_threshold:
                result = self._build_result(i, config)
                result.match_score = similarity
                results.append(result)

        # Sort by similarity score descending
        results.sort(key=lambda r: r.match_score, reverse=True)

        return results

    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate string similarity using SequenceMatcher.

        Returns a value between 0 and 1.
        """
        try:
            from difflib import SequenceMatcher
            return SequenceMatcher(None, s1, s2).ratio()
        except Exception:
            # Fallback to simple comparison
            return 1.0 if s1 == s2 else 0.0

    def _build_result(self, word_index: int, config: SearchConfig) -> SearchResult:
        """
        Build a SearchResult with context.

        Args:
            word_index: Index of the matched word
            config: Search configuration

        Returns:
            SearchResult object
        """
        word_data = self.words[word_index]

        # Extract context
        start = max(0, word_index - config.words_before)
        end = min(len(self.words), word_index + config.words_after + 1)

        context_before = ' '.join(
            w['text'] for w in self.words[start:word_index]
        )
        context_after = ' '.join(
            w['text'] for w in self.words[word_index + 1:end]
        )

        return SearchResult(
            word_found=word_data['text'],
            context_before=context_before,
            context_after=context_after,
            position=word_data.get('char_position', 0),
            line_number=word_data.get('line', 1),
            section_ref=word_data.get('tei_ref') if config.show_position else None,
            lemma=word_data.get('lemma') if config.include_morph else None,
            pos_tag=word_data.get('pos') if config.include_morph else None,
            morph=word_data.get('morph') if config.include_morph else None,
            token_index=word_data.get('token_index', word_index),
            sentence_index=word_data.get('sentence_index', 0),
            match_score=1.0
        )

    def get_statistics(self, results: List[SearchResult]) -> SearchStatistics:
        """
        Calculate statistics about search results.

        Args:
            results: List of search results

        Returns:
            SearchStatistics object
        """
        if not results:
            return SearchStatistics(
                total_occurrences=0,
                total_words=len(self.words),
                frequency=0.0,
                unique_forms=0
            )

        # Count unique forms
        forms = [r.word_found for r in results]
        forms_counter = Counter(forms)

        # Count sentences
        sentences = [r.sentence_index for r in results]
        sentence_counter = Counter(sentences)

        # Extract context words for word cloud
        context_words = []
        for r in results:
            words = r.context_before.split() + r.context_after.split()
            context_words.extend([
                w.lower().strip('.,;:!?()[]"\'')
                for w in words
                if len(w) > 2
            ])

        context_counter = Counter(context_words).most_common(50)

        # Calculate frequency
        total_words = len(self.words)
        frequency = (len(results) / total_words * 100) if total_words > 0 else 0

        return SearchStatistics(
            total_occurrences=len(results),
            total_words=total_words,
            frequency=frequency,
            unique_forms=len(forms_counter),
            forms_distribution=dict(forms_counter),
            sentence_distribution=dict(sentence_counter),
            context_words=context_counter
        )

    def get_concordance(
        self,
        results: List[SearchResult],
        format_type: str = "kwic"
    ) -> List[str]:
        """
        Generate concordance view of results.

        Args:
            results: List of search results
            format_type: "kwic" for Key Word In Context, "full" for full context

        Returns:
            List of formatted concordance lines
        """
        lines = []

        for i, result in enumerate(results, 1):
            if format_type == "kwic":
                # KWIC format: right-aligned context | KEYWORD | left-aligned context
                line = f"{result.context_before:>40} | {result.word_found:^15} | {result.context_after:<40}"
            else:
                # Full format with metadata
                line = (
                    f"[{i}] Line {result.line_number}: "
                    f"...{result.context_before} **{result.word_found}** {result.context_after}..."
                )
                if result.lemma:
                    line += f" (lemma: {result.lemma})"

            lines.append(line)

        return lines

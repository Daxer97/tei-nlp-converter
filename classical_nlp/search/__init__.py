"""
Occurrence Search Module for Classical Texts

Provides multiple search modes for finding occurrences in TEI documents:
- Exact match
- Lemmatized search (all inflected forms)
- Regex search
- Fuzzy search (for variant spellings)
"""

from .searcher import OccurrenceSearcher
from .config import SearchConfig, SearchMode, SearchResult

__all__ = [
    "OccurrenceSearcher",
    "SearchConfig",
    "SearchMode",
    "SearchResult",
]

"""
Base classes and interfaces for pattern matching
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Pattern as RegexPattern
from enum import Enum
import re


class PatternType(Enum):
    """Types of patterns"""
    # Medical
    ICD_CODE = "icd_code"
    CPT_CODE = "cpt_code"
    DOSAGE = "dosage"
    ROUTE = "route"
    FREQUENCY = "frequency"
    MEASUREMENT = "measurement"

    # Legal
    USC_CITATION = "usc_citation"
    CASE_CITATION = "case_citation"
    CFR_CITATION = "cfr_citation"
    STATE_CODE = "state_code"

    # General
    DATE = "date"
    TIME = "time"
    PHONE = "phone"
    EMAIL = "email"
    URL = "url"


class Priority(Enum):
    """Pattern matching priority"""
    CRITICAL = 1  # Must match, high confidence
    HIGH = 2
    MEDIUM = 3
    LOW = 4


@dataclass
class Pattern:
    """Represents a pattern definition"""
    pattern_type: PatternType
    name: str
    regex: str
    priority: Priority = Priority.MEDIUM
    description: Optional[str] = None
    requires_validation: bool = False
    requires_normalization: bool = False
    context_window: int = 50  # Characters before/after for context
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Compile regex pattern"""
        try:
            self.compiled_regex = re.compile(self.regex, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern '{self.regex}': {e}")


@dataclass
class PatternMatch:
    """Represents a matched pattern in text"""
    pattern_type: PatternType
    text: str
    start: int
    end: int
    confidence: float
    validated: bool = False
    normalized_value: Optional[str] = None
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'pattern_type': self.pattern_type.value,
            'text': self.text,
            'start': self.start,
            'end': self.end,
            'confidence': self.confidence,
            'validated': self.validated,
            'normalized_value': self.normalized_value,
            'context_before': self.context_before,
            'context_after': self.context_after,
            'metadata': self.metadata
        }


@dataclass
class ValidationResult:
    """Result of pattern validation"""
    is_valid: bool
    confidence: float
    normalized_value: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class PatternMatcher(ABC):
    """Abstract base class for pattern matchers"""

    def __init__(self, patterns: Optional[List[Pattern]] = None):
        self.patterns = patterns or []
        self._patterns_by_type: Dict[PatternType, List[Pattern]] = {}
        self._index_patterns()

    def _index_patterns(self):
        """Index patterns by type for efficient lookup"""
        self._patterns_by_type.clear()
        for pattern in self.patterns:
            if pattern.pattern_type not in self._patterns_by_type:
                self._patterns_by_type[pattern.pattern_type] = []
            self._patterns_by_type[pattern.pattern_type].append(pattern)

        # Sort by priority
        for patterns in self._patterns_by_type.values():
            patterns.sort(key=lambda p: p.priority.value)

    def add_pattern(self, pattern: Pattern):
        """Add a pattern to the matcher"""
        self.patterns.append(pattern)
        self._index_patterns()

    def extract_all(self, text: str) -> List[PatternMatch]:
        """
        Extract all pattern matches from text

        Args:
            text: Input text

        Returns:
            List of pattern matches
        """
        matches = []

        for pattern in self.patterns:
            pattern_matches = self._extract_pattern(text, pattern)
            matches.extend(pattern_matches)

        # Remove overlapping matches (keep higher priority)
        matches = self._resolve_overlaps(matches)

        return matches

    def _extract_pattern(self, text: str, pattern: Pattern) -> List[PatternMatch]:
        """Extract matches for a specific pattern"""
        matches = []

        for match in pattern.compiled_regex.finditer(text):
            matched_text = match.group(0)
            start = match.start()
            end = match.end()

            # Extract context
            context_before = text[max(0, start - pattern.context_window):start]
            context_after = text[end:min(len(text), end + pattern.context_window)]

            # Create match object
            pattern_match = PatternMatch(
                pattern_type=pattern.pattern_type,
                text=matched_text,
                start=start,
                end=end,
                confidence=1.0,  # Will be adjusted by validation
                context_before=context_before,
                context_after=context_after,
                metadata={'pattern_name': pattern.name}
            )

            # Validate if required
            if pattern.requires_validation:
                validation = self.validate_match(pattern_match)
                pattern_match.validated = validation.is_valid
                pattern_match.confidence = validation.confidence

                if not validation.is_valid:
                    continue  # Skip invalid matches

            # Normalize if required
            if pattern.requires_normalization:
                normalized = self.normalize_match(pattern_match)
                pattern_match.normalized_value = normalized

            matches.append(pattern_match)

        return matches

    def _resolve_overlaps(self, matches: List[PatternMatch]) -> List[PatternMatch]:
        """
        Resolve overlapping matches by keeping higher priority ones

        Args:
            matches: List of pattern matches

        Returns:
            Non-overlapping matches
        """
        if not matches:
            return []

        # Sort by start position
        sorted_matches = sorted(matches, key=lambda m: (m.start, -m.confidence))

        resolved = []
        for match in sorted_matches:
            # Check if this match overlaps with any already resolved
            overlaps = False
            for existing in resolved:
                if self._overlaps(match, existing):
                    overlaps = True
                    break

            if not overlaps:
                resolved.append(match)

        return resolved

    def _overlaps(self, match1: PatternMatch, match2: PatternMatch) -> bool:
        """Check if two matches overlap"""
        return not (match1.end <= match2.start or match2.end <= match1.start)

    @abstractmethod
    def validate_match(self, match: PatternMatch) -> ValidationResult:
        """
        Validate a pattern match

        Args:
            match: Pattern match to validate

        Returns:
            Validation result
        """
        pass

    @abstractmethod
    def normalize_match(self, match: PatternMatch) -> Optional[str]:
        """
        Normalize a pattern match to standard form

        Args:
            match: Pattern match to normalize

        Returns:
            Normalized value
        """
        pass

    def get_patterns_by_type(self, pattern_type: PatternType) -> List[Pattern]:
        """Get all patterns of a specific type"""
        return self._patterns_by_type.get(pattern_type, [])


class ContextAwarePatternMatcher(PatternMatcher):
    """Pattern matcher that uses context for disambiguation"""

    def __init__(self, patterns: Optional[List[Pattern]] = None):
        super().__init__(patterns)
        self.context_rules: Dict[PatternType, List[Dict[str, Any]]] = {}

    def add_context_rule(
        self,
        pattern_type: PatternType,
        before_keywords: Optional[List[str]] = None,
        after_keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        confidence_boost: float = 0.1
    ):
        """
        Add a context rule for pattern disambiguation

        Args:
            pattern_type: Type of pattern this rule applies to
            before_keywords: Keywords that should appear before match
            after_keywords: Keywords that should appear after match
            exclude_keywords: Keywords that invalidate the match
            confidence_boost: Confidence increase if rule matches
        """
        if pattern_type not in self.context_rules:
            self.context_rules[pattern_type] = []

        rule = {
            'before_keywords': [kw.lower() for kw in (before_keywords or [])],
            'after_keywords': [kw.lower() for kw in (after_keywords or [])],
            'exclude_keywords': [kw.lower() for kw in (exclude_keywords or [])],
            'confidence_boost': confidence_boost
        }

        self.context_rules[pattern_type].append(rule)

    def _extract_pattern(self, text: str, pattern: Pattern) -> List[PatternMatch]:
        """Extract with context awareness"""
        matches = super()._extract_pattern(text, pattern)

        # Apply context rules
        if pattern.pattern_type in self.context_rules:
            for match in matches:
                self._apply_context_rules(match)

        return matches

    def _apply_context_rules(self, match: PatternMatch):
        """Apply context rules to adjust confidence"""
        rules = self.context_rules.get(match.pattern_type, [])

        context_before = (match.context_before or '').lower()
        context_after = (match.context_after or '').lower()

        for rule in rules:
            # Check exclude keywords
            exclude_keywords = rule['exclude_keywords']
            if any(kw in context_before or kw in context_after for kw in exclude_keywords):
                match.confidence *= 0.5  # Penalize
                continue

            # Check positive keywords
            before_match = any(kw in context_before for kw in rule['before_keywords']) if rule['before_keywords'] else True
            after_match = any(kw in context_after for kw in rule['after_keywords']) if rule['after_keywords'] else True

            if before_match and after_match:
                match.confidence = min(1.0, match.confidence + rule['confidence_boost'])

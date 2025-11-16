"""
Domain pattern matcher for extracting structured data from text.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

from .patterns import MEDICAL_PATTERNS, LEGAL_PATTERNS, FINANCIAL_PATTERNS, GENERAL_PATTERNS

logger = logging.getLogger(__name__)


@dataclass
class PatternRule:
    """Definition of a pattern matching rule"""
    name: str
    pattern: str
    entity_type: str
    description: str = ""
    priority: str = "medium"  # high, medium, low
    case_insensitive: bool = False
    validation: Optional[str] = None
    examples: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def compile(self) -> re.Pattern:
        """Compile the regex pattern"""
        flags = re.IGNORECASE if self.case_insensitive else 0
        return re.compile(self.pattern, flags)


@dataclass
class StructuredEntity:
    """Represents an extracted structured entity"""
    text: str
    entity_type: str
    start: int
    end: int
    pattern_name: str
    confidence: float = 1.0
    matched_groups: Optional[Dict[str, str]] = None
    validation_passed: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "entity_type": self.entity_type,
            "start": self.start,
            "end": self.end,
            "pattern_name": self.pattern_name,
            "confidence": self.confidence,
            "matched_groups": self.matched_groups,
            "validation_passed": self.validation_passed,
            "metadata": self.metadata
        }


class DomainPatternMatcher:
    """Extracts structured entities using domain-specific patterns"""

    def __init__(self, domain: str = "general", custom_patterns: Optional[Dict[str, Dict]] = None):
        self.domain = domain
        self.patterns: Dict[str, PatternRule] = {}
        self.compiled_patterns: Dict[str, re.Pattern] = {}

        # Load domain-specific patterns
        self._load_domain_patterns(domain)

        # Load custom patterns if provided
        if custom_patterns:
            self._load_custom_patterns(custom_patterns)

        # Always include general patterns
        self._load_general_patterns()

        # Compile all patterns
        self._compile_patterns()

        logger.info(f"Initialized pattern matcher for domain '{domain}' with {len(self.patterns)} patterns")

    def _load_domain_patterns(self, domain: str) -> None:
        """Load patterns for specific domain"""
        domain_mapping = {
            "medical": MEDICAL_PATTERNS,
            "legal": LEGAL_PATTERNS,
            "financial": FINANCIAL_PATTERNS,
            "general": {}
        }

        patterns = domain_mapping.get(domain, {})
        for name, config in patterns.items():
            rule = PatternRule(
                name=name,
                pattern=config["pattern"],
                entity_type=name.upper(),
                description=config.get("description", ""),
                priority=config.get("priority", "medium"),
                case_insensitive=config.get("case_insensitive", False),
                validation=config.get("validation"),
                examples=config.get("examples", [])
            )
            self.patterns[name] = rule

    def _load_custom_patterns(self, custom_patterns: Dict[str, Dict]) -> None:
        """Load custom patterns"""
        for name, config in custom_patterns.items():
            rule = PatternRule(
                name=name,
                pattern=config["pattern"],
                entity_type=config.get("entity_type", name.upper()),
                description=config.get("description", ""),
                priority=config.get("priority", "medium"),
                case_insensitive=config.get("case_insensitive", False),
                validation=config.get("validation"),
                examples=config.get("examples", [])
            )
            self.patterns[name] = rule

    def _load_general_patterns(self) -> None:
        """Load general patterns applicable to all domains"""
        for name, config in GENERAL_PATTERNS.items():
            # Only add if not already present
            if name not in self.patterns:
                rule = PatternRule(
                    name=name,
                    pattern=config["pattern"],
                    entity_type=name.upper(),
                    description=config.get("description", ""),
                    priority=config.get("priority", "low")
                )
                self.patterns[name] = rule

    def _compile_patterns(self) -> None:
        """Compile all regex patterns"""
        for name, rule in self.patterns.items():
            try:
                self.compiled_patterns[name] = rule.compile()
            except re.error as e:
                logger.error(f"Failed to compile pattern '{name}': {e}")

    def extract_structured_data(self, text: str) -> List[StructuredEntity]:
        """
        Extract all structured entities from text.

        Args:
            text: Input text to process

        Returns:
            List of extracted structured entities
        """
        entities = []
        seen_spans: Set[tuple] = set()  # Track (start, end) to avoid duplicates

        # Sort patterns by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_patterns = sorted(
            self.patterns.items(),
            key=lambda x: priority_order.get(x[1].priority, 1)
        )

        for name, rule in sorted_patterns:
            pattern = self.compiled_patterns.get(name)
            if not pattern:
                continue

            for match in pattern.finditer(text):
                start = match.start()
                end = match.end()
                span = (start, end)

                # Skip if we already have an entity for this span
                if span in seen_spans:
                    continue

                # Check for overlapping spans with higher priority
                overlaps = False
                for existing_span in seen_spans:
                    if self._spans_overlap(span, existing_span):
                        overlaps = True
                        break

                if overlaps:
                    continue

                matched_text = match.group(0)

                # Extract matched groups
                matched_groups = {}
                for i, group in enumerate(match.groups(), 1):
                    if group:
                        matched_groups[f"group_{i}"] = group

                # Validate if validation pattern provided
                validation_passed = True
                if rule.validation:
                    try:
                        validation_pattern = re.compile(rule.validation)
                        validation_passed = bool(validation_pattern.match(matched_text))
                    except re.error:
                        validation_passed = True

                # Calculate confidence based on validation and priority
                confidence = 1.0
                if not validation_passed:
                    confidence = 0.7
                if rule.priority == "low":
                    confidence *= 0.8

                entity = StructuredEntity(
                    text=matched_text,
                    entity_type=rule.entity_type,
                    start=start,
                    end=end,
                    pattern_name=name,
                    confidence=confidence,
                    matched_groups=matched_groups,
                    validation_passed=validation_passed,
                    metadata={
                        "domain": self.domain,
                        "description": rule.description,
                        "priority": rule.priority
                    }
                )
                entities.append(entity)
                seen_spans.add(span)

        # Sort by start position
        entities.sort(key=lambda e: e.start)

        logger.debug(f"Extracted {len(entities)} structured entities from text")
        return entities

    def _spans_overlap(self, span1: tuple, span2: tuple) -> bool:
        """Check if two spans overlap"""
        start1, end1 = span1
        start2, end2 = span2
        return not (end1 <= start2 or end2 <= start1)

    def validate_entity(self, entity_type: str, text: str) -> bool:
        """
        Validate a specific entity against its pattern.

        Args:
            entity_type: Type of entity (pattern name)
            text: Text to validate

        Returns:
            True if valid, False otherwise
        """
        # Find pattern for this entity type
        rule = None
        for name, r in self.patterns.items():
            if r.entity_type == entity_type or name == entity_type.lower():
                rule = r
                break

        if not rule:
            return False

        pattern = self.compiled_patterns.get(rule.name)
        if not pattern:
            return False

        match = pattern.fullmatch(text)
        if not match:
            return False

        # Additional validation if provided
        if rule.validation:
            try:
                validation_pattern = re.compile(rule.validation)
                return bool(validation_pattern.match(text))
            except re.error:
                pass

        return True

    def normalize_entity(self, entity: StructuredEntity) -> StructuredEntity:
        """
        Normalize an extracted entity.

        Args:
            entity: Entity to normalize

        Returns:
            Normalized entity
        """
        normalized_text = entity.text.strip()

        # Domain-specific normalization
        if self.domain == "medical":
            normalized_text = self._normalize_medical(entity, normalized_text)
        elif self.domain == "legal":
            normalized_text = self._normalize_legal(entity, normalized_text)
        elif self.domain == "financial":
            normalized_text = self._normalize_financial(entity, normalized_text)

        entity.text = normalized_text
        return entity

    def _normalize_medical(self, entity: StructuredEntity, text: str) -> str:
        """Normalize medical entities"""
        if entity.entity_type == "DOSAGE":
            # Standardize units
            text = text.replace("mcg", "µg")
            text = text.replace("unit", "U")
        elif entity.entity_type == "ROUTE":
            # Uppercase route abbreviations
            text = text.upper()
        elif entity.entity_type == "FREQUENCY":
            # Standardize frequency abbreviations
            text = text.lower().replace(".", "")
        return text

    def _normalize_legal(self, entity: StructuredEntity, text: str) -> str:
        """Normalize legal entities"""
        if entity.entity_type == "USC_CITATION":
            # Standardize USC format
            text = text.replace("section", "§").replace("sec.", "§")
            text = re.sub(r'U\.?S\.?C\.?', 'U.S.C.', text)
        elif entity.entity_type == "CFR_CITATION":
            # Standardize CFR format
            text = re.sub(r'C\.?F\.?R\.?', 'C.F.R.', text)
        return text

    def _normalize_financial(self, entity: StructuredEntity, text: str) -> str:
        """Normalize financial entities"""
        if entity.entity_type == "CURRENCY_AMOUNT":
            # Remove spaces within amount
            text = text.replace(" ", "")
        elif entity.entity_type == "TICKER_SYMBOL":
            # Uppercase ticker
            text = text.upper()
        return text

    def add_pattern(self, name: str, pattern: str, entity_type: str, **kwargs) -> None:
        """
        Add a new pattern at runtime.

        Args:
            name: Pattern name
            pattern: Regex pattern string
            entity_type: Entity type to assign
            **kwargs: Additional pattern configuration
        """
        rule = PatternRule(
            name=name,
            pattern=pattern,
            entity_type=entity_type,
            **kwargs
        )
        self.patterns[name] = rule
        try:
            self.compiled_patterns[name] = rule.compile()
            logger.info(f"Added pattern '{name}' for entity type '{entity_type}'")
        except re.error as e:
            logger.error(f"Failed to add pattern '{name}': {e}")

    def remove_pattern(self, name: str) -> None:
        """Remove a pattern"""
        if name in self.patterns:
            del self.patterns[name]
        if name in self.compiled_patterns:
            del self.compiled_patterns[name]
        logger.info(f"Removed pattern '{name}'")

    def get_pattern_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all loaded patterns"""
        info = {}
        for name, rule in self.patterns.items():
            info[name] = {
                "entity_type": rule.entity_type,
                "description": rule.description,
                "priority": rule.priority,
                "examples": rule.examples,
                "case_insensitive": rule.case_insensitive,
                "has_validation": rule.validation is not None
            }
        return info

    def get_supported_entity_types(self) -> Set[str]:
        """Get all entity types this matcher can extract"""
        return {rule.entity_type for rule in self.patterns.values()}

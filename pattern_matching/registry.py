"""
Pattern Matcher Registry

Manages multiple pattern matchers and provides a unified interface
for pattern extraction across different domains.
"""
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import re

from .base import PatternMatcher, PatternMatch, PatternType
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class RegistryStats:
    """Statistics about registered pattern matchers"""
    total_matchers: int
    total_patterns: int
    domains: Set[str]
    pattern_types: Set[PatternType]


class PatternMatcherRegistry:
    """
    Central registry for all pattern matchers

    Manages multiple domain-specific pattern matchers and provides
    a unified interface for extracting patterns from text.

    Example:
        registry = PatternMatcherRegistry()
        registry.register("medical", medical_matcher)
        registry.register("legal", legal_matcher)

        # Extract all patterns
        matches = registry.extract_all(text)

        # Extract only from specific domain
        medical_matches = registry.extract_from_domain(text, "medical")
    """

    def __init__(self):
        self._matchers: Dict[str, PatternMatcher] = {}
        self._enabled_matchers: Set[str] = set()

    def register(self, domain: str, matcher: PatternMatcher, enabled: bool = True):
        """
        Register a pattern matcher for a domain

        Args:
            domain: Domain identifier (e.g., "medical", "legal")
            matcher: PatternMatcher instance
            enabled: Whether matcher is enabled by default
        """
        if domain in self._matchers:
            logger.warning(f"Overwriting existing matcher for domain: {domain}")

        self._matchers[domain] = matcher

        if enabled:
            self._enabled_matchers.add(domain)

        logger.info(f"Registered pattern matcher for domain: {domain}")

    def unregister(self, domain: str):
        """Unregister a pattern matcher"""
        if domain in self._matchers:
            del self._matchers[domain]
            self._enabled_matchers.discard(domain)
            logger.info(f"Unregistered pattern matcher for domain: {domain}")
        else:
            logger.warning(f"Cannot unregister non-existent domain: {domain}")

    def enable_matcher(self, domain: str):
        """Enable a registered matcher"""
        if domain in self._matchers:
            self._enabled_matchers.add(domain)
            logger.info(f"Enabled matcher for domain: {domain}")
        else:
            logger.warning(f"Cannot enable non-existent domain: {domain}")

    def disable_matcher(self, domain: str):
        """Disable a registered matcher"""
        self._enabled_matchers.discard(domain)
        logger.info(f"Disabled matcher for domain: {domain}")

    def get_matcher(self, domain: str) -> Optional[PatternMatcher]:
        """Get a specific matcher by domain"""
        return self._matchers.get(domain)

    def list_domains(self) -> List[str]:
        """List all registered domains"""
        return list(self._matchers.keys())

    def list_enabled_domains(self) -> List[str]:
        """List enabled domains"""
        return list(self._enabled_matchers)

    def extract_all(
        self,
        text: str,
        domains: Optional[List[str]] = None,
        pattern_types: Optional[List[PatternType]] = None
    ) -> List[PatternMatch]:
        """
        Extract patterns from all enabled matchers

        Args:
            text: Input text
            domains: Optional list of domains to use (defaults to all enabled)
            pattern_types: Optional filter by pattern types

        Returns:
            List of all pattern matches sorted by position
        """
        if not text:
            return []

        # Determine which domains to use
        if domains is None:
            domains = list(self._enabled_matchers)
        else:
            # Only use domains that are both specified and enabled
            domains = [d for d in domains if d in self._enabled_matchers]

        if not domains:
            logger.debug("No enabled matchers to extract patterns")
            return []

        # Collect matches from all domains
        all_matches = []

        for domain in domains:
            matcher = self._matchers.get(domain)
            if not matcher:
                continue

            try:
                matches = matcher.extract_all(text)

                # Add domain metadata
                for match in matches:
                    match.metadata['domain'] = domain

                all_matches.extend(matches)

            except Exception as e:
                logger.error(f"Error extracting patterns from {domain} matcher: {e}")

        # Filter by pattern types if specified
        if pattern_types:
            pattern_type_set = set(pattern_types)
            all_matches = [m for m in all_matches if m.pattern_type in pattern_type_set]

        # Sort by position
        all_matches.sort(key=lambda m: m.start)

        # Resolve cross-domain overlaps
        all_matches = self._resolve_cross_domain_overlaps(all_matches)

        return all_matches

    def extract_from_domain(
        self,
        text: str,
        domain: str,
        pattern_types: Optional[List[PatternType]] = None
    ) -> List[PatternMatch]:
        """
        Extract patterns from a specific domain

        Args:
            text: Input text
            domain: Domain to extract from
            pattern_types: Optional filter by pattern types

        Returns:
            List of pattern matches
        """
        if domain not in self._matchers:
            logger.warning(f"Domain not registered: {domain}")
            return []

        if domain not in self._enabled_matchers:
            logger.warning(f"Domain not enabled: {domain}")
            return []

        matcher = self._matchers[domain]

        try:
            matches = matcher.extract_all(text)

            # Add domain metadata
            for match in matches:
                match.metadata['domain'] = domain

            # Filter by pattern types if specified
            if pattern_types:
                pattern_type_set = set(pattern_types)
                matches = [m for m in matches if m.pattern_type in pattern_type_set]

            return matches

        except Exception as e:
            logger.error(f"Error extracting patterns from {domain} matcher: {e}")
            return []

    def _resolve_cross_domain_overlaps(
        self,
        matches: List[PatternMatch]
    ) -> List[PatternMatch]:
        """
        Resolve overlapping matches from different domains

        When patterns from different domains overlap, keep the one with:
        1. Higher confidence
        2. If confidence is equal, higher priority
        3. If priority is equal, keep first by domain order
        """
        if len(matches) <= 1:
            return matches

        # Sort by start position, then by confidence (descending)
        sorted_matches = sorted(
            matches,
            key=lambda m: (m.start, -m.confidence, -m.priority.value)
        )

        result = []
        last_end = -1

        for match in sorted_matches:
            # Check if this match overlaps with the last accepted match
            if match.start >= last_end:
                # No overlap, accept this match
                result.append(match)
                last_end = match.end
            else:
                # Overlap detected
                # Compare with last accepted match
                last_match = result[-1]

                # Keep the one with higher confidence
                if match.confidence > last_match.confidence:
                    result[-1] = match
                    last_end = match.end
                elif match.confidence == last_match.confidence:
                    # If confidence is equal, keep the one with higher priority
                    if match.priority.value > last_match.priority.value:
                        result[-1] = match
                        last_end = match.end

        return result

    def get_stats(self) -> RegistryStats:
        """Get statistics about registered matchers"""
        total_patterns = 0
        pattern_types = set()

        for matcher in self._matchers.values():
            patterns = matcher.get_patterns()
            total_patterns += len(patterns)
            pattern_types.update(p.pattern_type for p in patterns)

        return RegistryStats(
            total_matchers=len(self._matchers),
            total_patterns=total_patterns,
            domains=set(self._matchers.keys()),
            pattern_types=pattern_types
        )

    def validate_text(self, text: str) -> Dict[str, List[str]]:
        """
        Validate text against all matchers and return validation errors

        Args:
            text: Text to validate

        Returns:
            Dict mapping domain to list of validation error messages
        """
        errors = {}

        for domain in self._enabled_matchers:
            matcher = self._matchers.get(domain)
            if not matcher:
                continue

            # Extract patterns
            matches = matcher.extract_all(text)

            # Collect validation errors
            domain_errors = []
            for match in matches:
                if match.metadata.get('validation_result'):
                    val_result = match.metadata['validation_result']
                    if not val_result.is_valid and val_result.message:
                        domain_errors.append(
                            f"{match.pattern_type.value} at position {match.start}: {val_result.message}"
                        )

            if domain_errors:
                errors[domain] = domain_errors

        return errors

    def get_pattern_coverage(self, text: str) -> Dict[str, Dict[str, int]]:
        """
        Get coverage statistics for each domain

        Args:
            text: Text to analyze

        Returns:
            Dict mapping domain to pattern type counts
        """
        coverage = {}

        for domain in self._enabled_matchers:
            matcher = self._matchers.get(domain)
            if not matcher:
                continue

            matches = matcher.extract_all(text)

            # Count by pattern type
            type_counts = {}
            for match in matches:
                pattern_type = match.pattern_type.value
                type_counts[pattern_type] = type_counts.get(pattern_type, 0) + 1

            coverage[domain] = type_counts

        return coverage


# Global registry instance
_global_registry: Optional[PatternMatcherRegistry] = None


def get_global_registry() -> PatternMatcherRegistry:
    """Get the global pattern matcher registry (singleton)"""
    global _global_registry

    if _global_registry is None:
        _global_registry = PatternMatcherRegistry()
        logger.info("Created global pattern matcher registry")

    return _global_registry


def reset_global_registry():
    """Reset the global registry (mainly for testing)"""
    global _global_registry
    _global_registry = None
    logger.info("Reset global pattern matcher registry")

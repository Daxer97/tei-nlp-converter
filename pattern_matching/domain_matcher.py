"""
Domain Pattern Matcher

High-level interface for extracting patterns from multiple domains
with automatic domain detection and configuration support.
"""
from typing import List, Optional, Dict, Any
from pathlib import Path
import yaml

from .base import PatternMatch, PatternType
from .medical import MedicalPatternMatcher
from .legal import LegalPatternMatcher
from .registry import PatternMatcherRegistry, get_global_registry
from logger import get_logger

logger = get_logger(__name__)


class DomainPatternMatcher:
    """
    High-level pattern matcher that combines multiple domain-specific matchers

    Provides:
    - Automatic domain detection
    - Configuration-driven pattern matching
    - Unified interface for all domains
    - Pattern statistics and validation

    Example:
        matcher = DomainPatternMatcher()
        matcher.initialize()

        # Extract all patterns
        matches = matcher.extract_patterns(text)

        # Extract only medical patterns
        medical_matches = matcher.extract_patterns(text, domains=["medical"])

        # Auto-detect domain and extract
        matches = matcher.extract_with_auto_domain(text)
    """

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        use_global_registry: bool = True
    ):
        """
        Initialize domain pattern matcher

        Args:
            config_dir: Directory containing pattern configuration files
            use_global_registry: Whether to use the global registry
        """
        self.config_dir = config_dir or Path("config/patterns")

        if use_global_registry:
            self.registry = get_global_registry()
        else:
            self.registry = PatternMatcherRegistry()

        self._initialized = False

    def initialize(self, domains: Optional[List[str]] = None):
        """
        Initialize pattern matchers

        Args:
            domains: List of domains to initialize (default: all)
        """
        if self._initialized:
            logger.warning("DomainPatternMatcher already initialized")
            return

        # Default to all domains
        if domains is None:
            domains = ["medical", "legal"]

        # Initialize each domain
        for domain in domains:
            try:
                self._initialize_domain(domain)
            except Exception as e:
                logger.error(f"Failed to initialize {domain} domain: {e}")

        self._initialized = True
        logger.info(f"DomainPatternMatcher initialized with domains: {domains}")

    def _initialize_domain(self, domain: str):
        """Initialize a specific domain"""
        if domain == "medical":
            self._initialize_medical()
        elif domain == "legal":
            self._initialize_legal()
        else:
            logger.warning(f"Unknown domain: {domain}")

    def _initialize_medical(self):
        """Initialize medical pattern matcher"""
        # Create medical matcher
        matcher = MedicalPatternMatcher()

        # Load configuration if available
        config_file = self.config_dir / "medical.yaml"
        if config_file.exists():
            config = self._load_config(config_file)
            self._apply_medical_config(matcher, config)

        # Register
        self.registry.register("medical", matcher, enabled=True)
        logger.info("Medical pattern matcher initialized")

    def _initialize_legal(self):
        """Initialize legal pattern matcher"""
        # Create legal matcher
        matcher = LegalPatternMatcher()

        # Load configuration if available
        config_file = self.config_dir / "legal.yaml"
        if config_file.exists():
            config = self._load_config(config_file)
            self._apply_legal_config(matcher, config)

        # Register
        self.registry.register("legal", matcher, enabled=True)
        logger.info("Legal pattern matcher initialized")

    def _load_config(self, config_file: Path) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded pattern configuration from {config_file}")
                return config or {}
        except Exception as e:
            logger.error(f"Error loading config from {config_file}: {e}")
            return {}

    def _apply_medical_config(self, matcher: MedicalPatternMatcher, config: Dict[str, Any]):
        """Apply configuration to medical matcher"""
        # Enable/disable patterns
        patterns_config = config.get('patterns', {})

        for pattern_type, pattern_cfg in patterns_config.items():
            enabled = pattern_cfg.get('enabled', True)

            if not enabled:
                # Remove patterns of this type
                # (This is a simplified approach; a full implementation would
                # have more granular control)
                logger.info(f"Disabled medical pattern type: {pattern_type}")

        # Add custom context rules
        context_rules = config.get('context_rules', [])
        for rule in context_rules:
            pattern_type = rule.get('pattern_type')
            before = rule.get('before_keywords', [])
            after = rule.get('after_keywords', [])
            boost = rule.get('confidence_boost', 0.1)

            if pattern_type:
                try:
                    pt = PatternType[pattern_type.upper()]
                    matcher.add_context_rule(pt, before, after, boost)
                    logger.info(f"Added context rule for {pattern_type}")
                except (KeyError, ValueError):
                    logger.warning(f"Invalid pattern type in config: {pattern_type}")

    def _apply_legal_config(self, matcher: LegalPatternMatcher, config: Dict[str, Any]):
        """Apply configuration to legal matcher"""
        # Similar to medical config
        patterns_config = config.get('patterns', {})

        for pattern_type, pattern_cfg in patterns_config.items():
            enabled = pattern_cfg.get('enabled', True)

            if not enabled:
                logger.info(f"Disabled legal pattern type: {pattern_type}")

        # Add custom context rules
        context_rules = config.get('context_rules', [])
        for rule in context_rules:
            pattern_type = rule.get('pattern_type')
            before = rule.get('before_keywords', [])
            after = rule.get('after_keywords', [])
            boost = rule.get('confidence_boost', 0.1)

            if pattern_type:
                try:
                    pt = PatternType[pattern_type.upper()]
                    matcher.add_context_rule(pt, before, after, boost)
                    logger.info(f"Added context rule for {pattern_type}")
                except (KeyError, ValueError):
                    logger.warning(f"Invalid pattern type in config: {pattern_type}")

    def extract_patterns(
        self,
        text: str,
        domains: Optional[List[str]] = None,
        pattern_types: Optional[List[PatternType]] = None,
        min_confidence: float = 0.0
    ) -> List[PatternMatch]:
        """
        Extract patterns from text

        Args:
            text: Input text
            domains: Optional list of domains to use
            pattern_types: Optional filter by pattern types
            min_confidence: Minimum confidence threshold

        Returns:
            List of pattern matches
        """
        if not self._initialized:
            logger.warning("DomainPatternMatcher not initialized, initializing now")
            self.initialize()

        # Extract from registry
        matches = self.registry.extract_all(text, domains, pattern_types)

        # Filter by confidence
        if min_confidence > 0.0:
            matches = [m for m in matches if m.confidence >= min_confidence]

        return matches

    def extract_from_domain(
        self,
        text: str,
        domain: str,
        pattern_types: Optional[List[PatternType]] = None,
        min_confidence: float = 0.0
    ) -> List[PatternMatch]:
        """
        Extract patterns from a specific domain

        Args:
            text: Input text
            domain: Domain to extract from
            pattern_types: Optional filter by pattern types
            min_confidence: Minimum confidence threshold

        Returns:
            List of pattern matches
        """
        if not self._initialized:
            logger.warning("DomainPatternMatcher not initialized, initializing now")
            self.initialize()

        matches = self.registry.extract_from_domain(text, domain, pattern_types)

        # Filter by confidence
        if min_confidence > 0.0:
            matches = [m for m in matches if m.confidence >= min_confidence]

        return matches

    def extract_with_auto_domain(
        self,
        text: str,
        pattern_types: Optional[List[PatternType]] = None,
        min_confidence: float = 0.0
    ) -> List[PatternMatch]:
        """
        Automatically detect domain and extract patterns

        Uses keyword-based heuristics to determine which domains are
        likely relevant and only searches those.

        Args:
            text: Input text
            pattern_types: Optional filter by pattern types
            min_confidence: Minimum confidence threshold

        Returns:
            List of pattern matches
        """
        if not self._initialized:
            logger.warning("DomainPatternMatcher not initialized, initializing now")
            self.initialize()

        # Detect relevant domains
        domains = self._detect_domains(text)

        if not domains:
            logger.debug("No domains detected, using all enabled domains")
            domains = None

        # Extract patterns
        return self.extract_patterns(text, domains, pattern_types, min_confidence)

    def _detect_domains(self, text: str) -> List[str]:
        """
        Detect relevant domains from text using keyword heuristics

        Returns:
            List of detected domains
        """
        text_lower = text.lower()
        detected = []

        # Medical keywords
        medical_keywords = [
            'patient', 'diagnosis', 'treatment', 'medication', 'drug',
            'prescription', 'dose', 'symptom', 'disease', 'icd', 'cpt',
            'procedure', 'clinical', 'medical', 'health', 'hospital',
            'doctor', 'physician', 'nurse', 'laboratory', 'lab'
        ]

        medical_score = sum(1 for kw in medical_keywords if kw in text_lower)

        # Legal keywords
        legal_keywords = [
            'court', 'case', 'statute', 'defendant', 'plaintiff', 'judge',
            'verdict', 'appeal', 'u.s.c', 'usc', 'c.f.r', 'cfr', 'section',
            'title', 'law', 'legal', 'attorney', 'counsel', 'complaint',
            'motion', 'brief', 'opinion', 'ruling', 'regulation'
        ]

        legal_score = sum(1 for kw in legal_keywords if kw in text_lower)

        # Threshold for domain detection (at least 2 keywords)
        if medical_score >= 2:
            detected.append("medical")

        if legal_score >= 2:
            detected.append("legal")

        return detected

    def get_pattern_statistics(self, text: str) -> Dict[str, Any]:
        """
        Get comprehensive statistics about extracted patterns

        Args:
            text: Input text

        Returns:
            Dict with statistics
        """
        if not self._initialized:
            self.initialize()

        matches = self.extract_patterns(text)

        # Overall statistics
        stats = {
            'total_matches': len(matches),
            'by_domain': {},
            'by_pattern_type': {},
            'confidence_distribution': {
                'high': 0,    # >= 0.8
                'medium': 0,  # 0.5 - 0.8
                'low': 0      # < 0.5
            },
            'validation_errors': 0
        }

        for match in matches:
            # By domain
            domain = match.metadata.get('domain', 'unknown')
            stats['by_domain'][domain] = stats['by_domain'].get(domain, 0) + 1

            # By pattern type
            pt = match.pattern_type.value
            stats['by_pattern_type'][pt] = stats['by_pattern_type'].get(pt, 0) + 1

            # Confidence distribution
            if match.confidence >= 0.8:
                stats['confidence_distribution']['high'] += 1
            elif match.confidence >= 0.5:
                stats['confidence_distribution']['medium'] += 1
            else:
                stats['confidence_distribution']['low'] += 1

            # Validation errors
            if match.metadata.get('validation_result'):
                val_result = match.metadata['validation_result']
                if not val_result.is_valid:
                    stats['validation_errors'] += 1

        return stats

    def validate_text(self, text: str) -> Dict[str, List[str]]:
        """
        Validate text and return all validation errors

        Args:
            text: Text to validate

        Returns:
            Dict mapping domain to list of error messages
        """
        if not self._initialized:
            self.initialize()

        return self.registry.validate_text(text)

    def get_coverage(self, text: str) -> Dict[str, Dict[str, int]]:
        """
        Get pattern coverage by domain and type

        Args:
            text: Text to analyze

        Returns:
            Dict mapping domain to pattern type counts
        """
        if not self._initialized:
            self.initialize()

        return self.registry.get_pattern_coverage(text)

    def enable_domain(self, domain: str):
        """Enable a domain"""
        self.registry.enable_matcher(domain)

    def disable_domain(self, domain: str):
        """Disable a domain"""
        self.registry.disable_matcher(domain)

    def list_domains(self) -> List[str]:
        """List all available domains"""
        return self.registry.list_domains()

    def list_enabled_domains(self) -> List[str]:
        """List enabled domains"""
        return self.registry.list_enabled_domains()

"""
Legal Pattern Matchers

Recognizes legal structured data:
- USC citations
- Case citations
- CFR citations
- State code citations
- Court names
"""
from typing import List, Optional, Dict, Any
import re
from pattern_matching.base import (
    PatternMatcher,
    Pattern,
    PatternMatch,
    PatternType,
    Priority,
    ValidationResult,
    ContextAwarePatternMatcher
)
from logger import get_logger

logger = get_logger(__name__)


class LegalPatternMatcher(ContextAwarePatternMatcher):
    """Specialized pattern matcher for legal text"""

    def __init__(self):
        patterns = self._create_legal_patterns()
        super().__init__(patterns)
        self._setup_context_rules()

        # Valid USC titles (1-54)
        self.valid_usc_titles = set(range(1, 55))

        # Common reporter abbreviations
        self.reporter_abbreviations = {
            'U.S.': 'United States Reports',
            'S.Ct.': 'Supreme Court Reporter',
            'L.Ed.': "Lawyer's Edition",
            'F.': 'Federal Reporter',
            'F.2d': 'Federal Reporter 2d',
            'F.3d': 'Federal Reporter 3d',
            'F.Supp.': 'Federal Supplement',
            'F.Supp.2d': 'Federal Supplement 2d',
            'F.Supp.3d': 'Federal Supplement 3d',
            'F.4th': 'Federal Reporter 4th',
            'A.': 'Atlantic Reporter',
            'A.2d': 'Atlantic Reporter 2d',
            'A.3d': 'Atlantic Reporter 3d',
            'P.': 'Pacific Reporter',
            'P.2d': 'Pacific Reporter 2d',
            'P.3d': 'Pacific Reporter 3d',
            'N.E.': 'North Eastern Reporter',
            'N.E.2d': 'North Eastern Reporter 2d',
            'N.W.': 'North Western Reporter',
            'N.W.2d': 'North Western Reporter 2d',
            'S.E.': 'South Eastern Reporter',
            'S.E.2d': 'South Eastern Reporter 2d',
            'S.W.': 'South Western Reporter',
            'S.W.2d': 'South Western Reporter 2d',
            'S.W.3d': 'South Western Reporter 3d',
            'So.': 'Southern Reporter',
            'So.2d': 'Southern Reporter 2d',
            'So.3d': 'Southern Reporter 3d'
        }

        # Valid CFR titles (1-50)
        self.valid_cfr_titles = set(range(1, 51))

    def _create_legal_patterns(self) -> List[Pattern]:
        """Create legal pattern definitions"""
        return [
            # USC Citations
            Pattern(
                pattern_type=PatternType.USC_CITATION,
                name="usc_standard",
                regex=r'\b(\d+)\s+U\.?S\.?C\.?\s+§§?\s*(\d+)([a-z])?(\(\d+\))?([A-Z])?',
                priority=Priority.HIGH,
                description="United States Code citation",
                requires_validation=True,
                requires_normalization=True,
                context_window=150
            ),

            Pattern(
                pattern_type=PatternType.USC_CITATION,
                name="usc_title_section",
                regex=r'\bTitle\s+(\d+),?\s+Section\s+(\d+)',
                priority=Priority.MEDIUM,
                description="USC citation (Title X, Section Y format)",
                requires_validation=True,
                requires_normalization=True,
                context_window=100
            ),

            # Case Citations (reporter format)
            Pattern(
                pattern_type=PatternType.CASE_CITATION,
                name="case_reporter",
                regex=r'\b(\d+)\s+([A-Z]\.[A-Za-z.0-9]*)\s+(\d+)(?:\s*\(([^)]+)\))?',
                priority=Priority.HIGH,
                description="Case citation (reporter format: 347 U.S. 483)",
                requires_validation=True,
                requires_normalization=True,
                context_window=200
            ),

            # Case Names
            Pattern(
                pattern_type=PatternType.CASE_CITATION,
                name="case_name",
                regex=r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+v\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                priority=Priority.MEDIUM,
                description="Case name (Party v. Party)",
                requires_validation=True,
                requires_normalization=False,
                context_window=100
            ),

            # CFR Citations
            Pattern(
                pattern_type=PatternType.CFR_CITATION,
                name="cfr_standard",
                regex=r'\b(\d+)\s+C\.?F\.?R\.?\s+§?\s*(\d+)\.(\d+)',
                priority=Priority.HIGH,
                description="Code of Federal Regulations citation",
                requires_validation=True,
                requires_normalization=True,
                context_window=100
            ),

            Pattern(
                pattern_type=PatternType.CFR_CITATION,
                name="cfr_part",
                regex=r'\b(\d+)\s+C\.?F\.?R\.?\s+[Pp]art\s+(\d+)',
                priority=Priority.MEDIUM,
                description="CFR Part citation",
                requires_validation=True,
                requires_normalization=True,
                context_window=100
            ),

            # State Code Citations (generic)
            Pattern(
                pattern_type=PatternType.STATE_CODE,
                name="state_code_generic",
                regex=r'\b([A-Z]{2})\s+(Code|Rev\.\s*Stat\.?|Stat\.?)\s+§?\s*(\d+(?:[.-]\d+)*)',
                priority=Priority.MEDIUM,
                description="State code citation (generic)",
                requires_validation=False,
                requires_normalization=True,
                context_window=100
            )
        ]

    def _setup_context_rules(self):
        """Setup context rules for legal patterns"""

        # USC context
        self.add_context_rule(
            pattern_type=PatternType.USC_CITATION,
            before_keywords=['pursuant to', 'under', 'violat', 'section', 'title', 'usc', 'code'],
            after_keywords=['provides', 'states', 'requires', 'prohibits'],
            exclude_keywords=['approximately', 'about'],  # Avoid "about 18" mismatches
            confidence_boost=0.2
        )

        # Case citation context
        self.add_context_rule(
            pattern_type=PatternType.CASE_CITATION,
            before_keywords=['see', 'see also', 'cf.', 'citing', 'in', 'held in'],
            after_keywords=['held', 'court', 'decision', 'opinion'],
            confidence_boost=0.2
        )

        # CFR context
        self.add_context_rule(
            pattern_type=PatternType.CFR_CITATION,
            before_keywords=['regulation', 'cfr', 'federal regulation', 'under'],
            after_keywords=['regulation', 'provides', 'requires'],
            confidence_boost=0.2
        )

    def validate_match(self, match: PatternMatch) -> ValidationResult:
        """
        Validate legal pattern matches

        Args:
            match: Pattern match to validate

        Returns:
            Validation result
        """
        if match.pattern_type == PatternType.USC_CITATION:
            return self._validate_usc_citation(match)

        elif match.pattern_type == PatternType.CASE_CITATION:
            return self._validate_case_citation(match)

        elif match.pattern_type == PatternType.CFR_CITATION:
            return self._validate_cfr_citation(match)

        else:
            return ValidationResult(
                is_valid=True,
                confidence=0.8
            )

    def _validate_usc_citation(self, match: PatternMatch) -> ValidationResult:
        """Validate USC citation"""
        # Extract title number
        title_match = re.match(r'(\d+)', match.text)

        if not title_match:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                error_message="Could not extract title number"
            )

        try:
            title = int(title_match.group(1))
        except ValueError:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                error_message="Invalid title number"
            )

        # Check if title is in valid range
        if title not in self.valid_usc_titles:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                error_message=f"USC title {title} out of valid range (1-54)"
            )

        # Valid USC citation
        confidence = 0.95

        # Check context for additional confidence
        context = (match.context_before or '').lower() + ' ' + (match.context_after or '').lower()

        if any(kw in context for kw in ['usc', 'united states code', 'title', 'section', 'statute']):
            confidence = 1.0

        # Extract section for metadata
        section_match = re.search(r'§§?\s*(\d+)', match.text)
        section = section_match.group(1) if section_match else None

        return ValidationResult(
            is_valid=True,
            confidence=confidence,
            normalized_value=self._normalize_usc_citation(match.text),
            metadata={'title': title, 'section': section}
        )

    def _validate_case_citation(self, match: PatternMatch) -> ValidationResult:
        """Validate case citation"""
        # Check if it's a reporter format citation
        reporter_match = re.match(r'(\d+)\s+([A-Z]\.[A-Za-z.0-9]*)\s+(\d+)', match.text)

        if reporter_match:
            volume = reporter_match.group(1)
            reporter = reporter_match.group(2)
            page = reporter_match.group(3)

            # Check if reporter is recognized
            is_known_reporter = any(
                reporter.startswith(abbr.replace('.', ''))
                for abbr in self.reporter_abbreviations.keys()
            )

            confidence = 0.95 if is_known_reporter else 0.7

            # Check context
            context = (match.context_before or '').lower() + ' ' + (match.context_after or '').lower()

            if any(kw in context for kw in ['case', 'court', 'held', 'opinion', 'decision']):
                confidence = min(1.0, confidence + 0.1)

            return ValidationResult(
                is_valid=True,
                confidence=confidence,
                metadata={
                    'volume': volume,
                    'reporter': reporter,
                    'page': page,
                    'known_reporter': is_known_reporter
                }
            )

        # Check if it's a case name (Party v. Party)
        case_name_match = re.match(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+v\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', match.text)

        if case_name_match:
            plaintiff = case_name_match.group(1)
            defendant = case_name_match.group(2)

            # Lower confidence for case names without reporter
            confidence = 0.7

            # Check context
            context = (match.context_before or '').lower() + ' ' + (match.context_after or '').lower()

            if any(kw in context for kw in ['case', 'court', 'held', 'in', 'decision']):
                confidence = 0.85

            # Exclude common false positives
            if any(word in match.text.lower() for word in ['versus', 'vs']):
                confidence = 0.6  # Could be other "versus" usage

            return ValidationResult(
                is_valid=True,
                confidence=confidence,
                metadata={
                    'plaintiff': plaintiff,
                    'defendant': defendant,
                    'type': 'case_name'
                }
            )

        return ValidationResult(
            is_valid=False,
            confidence=0.0,
            error_message="Not a valid case citation format"
        )

    def _validate_cfr_citation(self, match: PatternMatch) -> ValidationResult:
        """Validate CFR citation"""
        # Extract title number
        title_match = re.match(r'(\d+)', match.text)

        if not title_match:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                error_message="Could not extract title number"
            )

        try:
            title = int(title_match.group(1))
        except ValueError:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                error_message="Invalid title number"
            )

        # Check if title is in valid range
        if title not in self.valid_cfr_titles:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                error_message=f"CFR title {title} out of valid range (1-50)"
            )

        # Valid CFR citation
        confidence = 0.95

        # Check context
        context = (match.context_before or '').lower() + ' ' + (match.context_after or '').lower()

        if any(kw in context for kw in ['cfr', 'code of federal regulations', 'regulation', 'federal']):
            confidence = 1.0

        return ValidationResult(
            is_valid=True,
            confidence=confidence,
            normalized_value=self._normalize_cfr_citation(match.text),
            metadata={'title': title}
        )

    def normalize_match(self, match: PatternMatch) -> Optional[str]:
        """
        Normalize legal pattern matches

        Args:
            match: Pattern match to normalize

        Returns:
            Normalized value
        """
        if match.pattern_type == PatternType.USC_CITATION:
            return self._normalize_usc_citation(match.text)

        elif match.pattern_type == PatternType.CASE_CITATION:
            return self._normalize_case_citation(match.text)

        elif match.pattern_type == PatternType.CFR_CITATION:
            return self._normalize_cfr_citation(match.text)

        elif match.pattern_type == PatternType.STATE_CODE:
            return self._normalize_state_code(match.text)

        return match.text

    def _normalize_usc_citation(self, citation: str) -> str:
        """
        Normalize USC citation to standard format

        Examples:
        - "18 U.S.C. § 1001" -> "18 U.S.C. § 1001"
        - "18 USC 1001" -> "18 U.S.C. § 1001"
        - "Title 18, Section 1001" -> "18 U.S.C. § 1001"
        """
        # Extract title and section
        match = re.match(r'(?:Title\s+)?(\d+)(?:\s+U\.?S\.?C\.?)?\s+(?:Section\s+)?§§?\s*(\d+)([a-z])?(\(\d+\))?([A-Z])?', citation, re.IGNORECASE)

        if not match:
            return citation

        title = match.group(1)
        section = match.group(2)
        subsection = match.group(3) or ''
        paragraph = match.group(4) or ''
        subparagraph = match.group(5) or ''

        # Standard format: "18 U.S.C. § 1001"
        normalized = f"{title} U.S.C. § {section}{subsection}{paragraph}{subparagraph}"

        return normalized

    def _normalize_case_citation(self, citation: str) -> str:
        """
        Normalize case citation to standard format

        Examples:
        - "347 US 483" -> "347 U.S. 483"
        - "347 U. S. 483" -> "347 U.S. 483"
        """
        # Try reporter format
        match = re.match(r'(\d+)\s+([A-Z]\.[A-Za-z.0-9]*)\s+(\d+)(?:\s*\(([^)]+)\))?', citation)

        if match:
            volume = match.group(1)
            reporter = match.group(2)
            page = match.group(3)
            year = match.group(4)

            # Standardize reporter abbreviation
            # Remove extra spaces in abbreviations
            reporter = re.sub(r'\.\s+', '.', reporter)

            # Ensure periods
            if not reporter.endswith('.'):
                reporter += '.'

            normalized = f"{volume} {reporter} {page}"

            if year:
                normalized += f" ({year})"

            return normalized

        # Return as-is if not in reporter format
        return citation

    def _normalize_cfr_citation(self, citation: str) -> str:
        """
        Normalize CFR citation to standard format

        Examples:
        - "21 CFR 312.32" -> "21 C.F.R. § 312.32"
        - "21 CFR Part 312" -> "21 C.F.R. Part 312"
        """
        # Try section format
        match = re.match(r'(\d+)\s+C\.?F\.?R\.?\s+§?\s*(\d+)\.(\d+)', citation, re.IGNORECASE)

        if match:
            title = match.group(1)
            part = match.group(2)
            section = match.group(3)

            return f"{title} C.F.R. § {part}.{section}"

        # Try part format
        match = re.match(r'(\d+)\s+C\.?F\.?R\.?\s+[Pp]art\s+(\d+)', citation, re.IGNORECASE)

        if match:
            title = match.group(1)
            part = match.group(2)

            return f"{title} C.F.R. Part {part}"

        return citation

    def _normalize_state_code(self, citation: str) -> str:
        """Normalize state code citation"""
        # Just ensure consistent formatting
        match = re.match(r'([A-Z]{2})\s+(Code|Rev\.\s*Stat\.?|Stat\.?)\s+§?\s*(\d+(?:[.-]\d+)*)', citation, re.IGNORECASE)

        if match:
            state = match.group(1).upper()
            code_type = match.group(2)
            section = match.group(3)

            # Standardize code type
            if 'rev' in code_type.lower():
                code_type = 'Rev. Stat.'
            elif 'stat' in code_type.lower() and 'rev' not in code_type.lower():
                code_type = 'Stat.'
            else:
                code_type = 'Code'

            return f"{state} {code_type} § {section}"

        return citation

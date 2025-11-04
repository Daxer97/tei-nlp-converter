"""
Medical Pattern Matchers

Recognizes medical structured data:
- ICD-10 codes
- CPT codes
- Dosages
- Routes of administration
- Frequency
- Measurements
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


class MedicalPatternMatcher(ContextAwarePatternMatcher):
    """Specialized pattern matcher for medical text"""

    def __init__(self):
        patterns = self._create_medical_patterns()
        super().__init__(patterns)
        self._setup_context_rules()

        # ICD-10 code structure
        self.icd10_valid_chapters = [
            'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
            'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T',
            'U', 'V', 'W', 'X', 'Y', 'Z'
        ]

        # Common CPT code ranges
        self.cpt_ranges = {
            'evaluation_management': (99201, 99499),
            'anesthesia': (0, 1999),
            'surgery': (10021, 69990),
            'radiology': (70010, 79999),
            'pathology': (80047, 89398),
            'medicine': (90281, 99607)
        }

        # Valid routes of administration
        self.valid_routes = {
            'IV', 'IM', 'PO', 'SQ', 'SC', 'PR', 'INH', 'TOP',
            'SL', 'BUCCAL', 'NASAL', 'OPHTHALMIC', 'OTIC',
            'RECTAL', 'VAGINAL', 'TRANSDERMAL', 'EPIDURAL',
            'INTRATHECAL', 'INTRAVENOUS', 'INTRAMUSCULAR',
            'SUBCUTANEOUS', 'ORAL', 'TOPICAL', 'SUBLINGUAL'
        }

    def _create_medical_patterns(self) -> List[Pattern]:
        """Create medical pattern definitions"""
        return [
            # ICD-10 Codes
            Pattern(
                pattern_type=PatternType.ICD_CODE,
                name="icd10_standard",
                regex=r'\b[A-TV-Z][0-9]{2}\.?[0-9A-TV-Z]{0,4}\b',
                priority=Priority.HIGH,
                description="ICD-10 diagnosis codes",
                requires_validation=True,
                requires_normalization=True,
                context_window=100
            ),

            # CPT Codes
            Pattern(
                pattern_type=PatternType.CPT_CODE,
                name="cpt_standard",
                regex=r'\b\d{5}\b',
                priority=Priority.HIGH,
                description="CPT procedure codes (5 digits)",
                requires_validation=True,
                requires_normalization=False,
                context_window=100
            ),

            # Dosages with units
            Pattern(
                pattern_type=PatternType.DOSAGE,
                name="dosage_metric",
                regex=r'\b\d+\.?\d*\s*(mg|g|ml|mcg|µg|L|mL|units?|IU|mEq|mmol)\b',
                priority=Priority.MEDIUM,
                description="Dosage with metric units",
                requires_validation=False,
                requires_normalization=True,
                context_window=50
            ),

            # Routes of administration
            Pattern(
                pattern_type=PatternType.ROUTE,
                name="route_abbreviation",
                regex=r'\b(IV|IM|PO|SQ|SC|PR|INH|TOP|SL|BUCCAL|NASAL|OPHTHALMIC|OTIC|RECTAL|VAGINAL|TRANSDERMAL|EPIDURAL|INTRATHECAL)\b',
                priority=Priority.MEDIUM,
                description="Route of administration (abbreviations)",
                requires_validation=True,
                requires_normalization=True,
                context_window=30
            ),

            Pattern(
                pattern_type=PatternType.ROUTE,
                name="route_full",
                regex=r'\b(intravenous|intramuscular|subcutaneous|oral|topical|sublingual|intranasal|ophthalmic|otic|rectal|vaginal|transdermal|epidural|intrathecal)\b',
                priority=Priority.MEDIUM,
                description="Route of administration (full words)",
                requires_validation=False,
                requires_normalization=True,
                context_window=30
            ),

            # Frequency
            Pattern(
                pattern_type=PatternType.FREQUENCY,
                name="frequency_standard",
                regex=r'\b(QD|BID|TID|QID|QHS|PRN|Q\d+H|once daily|twice daily|three times daily|four times daily|every \d+ hours?|as needed)\b',
                priority=Priority.MEDIUM,
                description="Medication frequency",
                requires_validation=False,
                requires_normalization=True,
                context_window=50
            ),

            # Lab measurements
            Pattern(
                pattern_type=PatternType.MEASUREMENT,
                name="lab_value",
                regex=r'\b\d+\.?\d*\s*(mmHg|mg/dL|g/dL|mmol/L|mEq/L|U/L|IU/L|%|bpm)\b',
                priority=Priority.LOW,
                description="Laboratory values with units",
                requires_validation=False,
                requires_normalization=False,
                context_window=100
            )
        ]

    def _setup_context_rules(self):
        """Setup context rules for medical patterns"""

        # ICD code context
        self.add_context_rule(
            pattern_type=PatternType.ICD_CODE,
            before_keywords=['diagnosis', 'dx', 'icd', 'code', 'diagnosed with'],
            after_keywords=['diagnosis', 'condition', 'disease'],
            confidence_boost=0.2
        )

        # CPT code context
        self.add_context_rule(
            pattern_type=PatternType.CPT_CODE,
            before_keywords=['procedure', 'cpt', 'billed', 'performed', 'code'],
            after_keywords=['procedure', 'service', 'performed'],
            confidence_boost=0.2
        )

        # Dosage context
        self.add_context_rule(
            pattern_type=PatternType.DOSAGE,
            before_keywords=['dose', 'dosage', 'take', 'administer', 'give', 'prescribe'],
            after_keywords=['dose', 'tablet', 'capsule', 'daily', 'bid', 'tid'],
            confidence_boost=0.1
        )

        # Route context
        self.add_context_rule(
            pattern_type=PatternType.ROUTE,
            before_keywords=['via', 'by', 'route', 'given', 'administered'],
            after_keywords=['route', 'administration', 'injection'],
            confidence_boost=0.1
        )

    def validate_match(self, match: PatternMatch) -> ValidationResult:
        """
        Validate medical pattern matches

        Args:
            match: Pattern match to validate

        Returns:
            Validation result
        """
        if match.pattern_type == PatternType.ICD_CODE:
            return self._validate_icd_code(match)

        elif match.pattern_type == PatternType.CPT_CODE:
            return self._validate_cpt_code(match)

        elif match.pattern_type == PatternType.ROUTE:
            return self._validate_route(match)

        else:
            # Default: accept with high confidence
            return ValidationResult(
                is_valid=True,
                confidence=0.9
            )

    def _validate_icd_code(self, match: PatternMatch) -> ValidationResult:
        """Validate ICD-10 code structure"""
        code = match.text.upper()

        # Check first character (chapter)
        if code[0] not in self.icd10_valid_chapters:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                error_message=f"Invalid ICD-10 chapter: {code[0]}"
            )

        # Check structure: Letter + 2 digits + optional decimal + 0-4 more chars
        if not re.match(r'^[A-TV-Z]\d{2}\.?[0-9A-TV-Z]{0,4}$', code):
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                error_message="Invalid ICD-10 code structure"
            )

        # Valid structure
        confidence = 0.95

        # Check context for additional confidence
        context = (match.context_before or '').lower() + ' ' + (match.context_after or '').lower()

        if any(kw in context for kw in ['diagnosis', 'icd', 'code', 'dx']):
            confidence = 1.0

        return ValidationResult(
            is_valid=True,
            confidence=confidence,
            normalized_value=self._normalize_icd_code(code)
        )

    def _validate_cpt_code(self, match: PatternMatch) -> ValidationResult:
        """Validate CPT code"""
        try:
            code = int(match.text)
        except ValueError:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                error_message="Invalid CPT code format"
            )

        # Check if in valid CPT range (00000-99999)
        if code < 0 or code > 99999:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                error_message="CPT code out of range"
            )

        # Check if in a known CPT category
        in_range = False
        category = None

        for cat_name, (min_code, max_code) in self.cpt_ranges.items():
            if min_code <= code <= max_code:
                in_range = True
                category = cat_name
                break

        # Higher confidence if in known range
        confidence = 0.95 if in_range else 0.7

        # Check context
        context = (match.context_before or '').lower() + ' ' + (match.context_after or '').lower()

        if any(kw in context for kw in ['cpt', 'procedure', 'code', 'billed']):
            confidence = min(1.0, confidence + 0.1)

        # Must be in some known range to be considered valid
        if not in_range:
            # Could be a valid CPT, but less confident
            confidence = 0.6

        return ValidationResult(
            is_valid=True,
            confidence=confidence,
            metadata={'category': category} if category else {}
        )

    def _validate_route(self, match: PatternMatch) -> ValidationResult:
        """Validate route of administration"""
        route = match.text.upper()

        # Check if it's a valid route
        if route not in self.valid_routes:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                error_message=f"Unknown route: {route}"
            )

        # Valid route
        return ValidationResult(
            is_valid=True,
            confidence=0.9,
            normalized_value=self._normalize_route(route)
        )

    def normalize_match(self, match: PatternMatch) -> Optional[str]:
        """
        Normalize medical pattern matches

        Args:
            match: Pattern match to normalize

        Returns:
            Normalized value
        """
        if match.pattern_type == PatternType.ICD_CODE:
            return self._normalize_icd_code(match.text)

        elif match.pattern_type == PatternType.DOSAGE:
            return self._normalize_dosage(match.text)

        elif match.pattern_type == PatternType.ROUTE:
            return self._normalize_route(match.text)

        elif match.pattern_type == PatternType.FREQUENCY:
            return self._normalize_frequency(match.text)

        return match.text

    def _normalize_icd_code(self, code: str) -> str:
        """
        Normalize ICD-10 code to standard format

        Examples:
        - "I10" -> "I10"
        - "I10.0" -> "I10.0"
        - "i10" -> "I10"
        """
        code = code.upper().strip()

        # Ensure decimal point after 3rd character if there are more characters
        if len(code) > 3 and '.' not in code:
            code = code[:3] + '.' + code[3:]

        return code

    def _normalize_dosage(self, dosage: str) -> str:
        """
        Normalize dosage to standard format

        Examples:
        - "10 mg" -> "10 mg"
        - "10mg" -> "10 mg"
        - "10 micrograms" -> "10 mcg"
        """
        # Standardize spacing
        dosage = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', dosage)

        # Standardize units
        replacements = {
            'micrograms': 'mcg',
            'microgram': 'mcg',
            'µg': 'mcg',
            'milligrams': 'mg',
            'milligram': 'mg',
            'grams': 'g',
            'gram': 'g',
            'milliliters': 'mL',
            'milliliter': 'mL',
            'liters': 'L',
            'liter': 'L',
            'unit': 'units'
        }

        for old, new in replacements.items():
            dosage = re.sub(rf'\b{old}\b', new, dosage, flags=re.IGNORECASE)

        return dosage.strip()

    def _normalize_route(self, route: str) -> str:
        """
        Normalize route to standard abbreviation

        Examples:
        - "intravenous" -> "IV"
        - "iv" -> "IV"
        - "by mouth" -> "PO"
        """
        route = route.upper().strip()

        # Map full forms to abbreviations
        route_map = {
            'INTRAVENOUS': 'IV',
            'INTRAMUSCULAR': 'IM',
            'SUBCUTANEOUS': 'SC',
            'ORAL': 'PO',
            'BY MOUTH': 'PO',
            'TOPICAL': 'TOP',
            'SUBLINGUAL': 'SL',
            'INTRANASAL': 'NASAL',
            'OPHTHALMIC': 'OPHTHALMIC',
            'OTIC': 'OTIC',
            'RECTAL': 'PR',
            'VAGINAL': 'VAGINAL',
            'TRANSDERMAL': 'TRANSDERMAL',
            'EPIDURAL': 'EPIDURAL',
            'INTRATHECAL': 'INTRATHECAL'
        }

        return route_map.get(route, route)

    def _normalize_frequency(self, frequency: str) -> str:
        """
        Normalize frequency to standard abbreviation

        Examples:
        - "once daily" -> "QD"
        - "twice daily" -> "BID"
        - "every 4 hours" -> "Q4H"
        """
        frequency = frequency.upper().strip()

        # Map full forms to abbreviations
        freq_map = {
            'ONCE DAILY': 'QD',
            'TWICE DAILY': 'BID',
            'THREE TIMES DAILY': 'TID',
            'FOUR TIMES DAILY': 'QID',
            'AT BEDTIME': 'QHS',
            'AS NEEDED': 'PRN'
        }

        if frequency in freq_map:
            return freq_map[frequency]

        # Handle "every X hours" -> "QXH"
        match = re.match(r'EVERY (\d+) HOURS?', frequency)
        if match:
            hours = match.group(1)
            return f'Q{hours}H'

        return frequency

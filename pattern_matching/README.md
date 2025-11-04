# Pattern Matching System

The pattern matching system provides robust extraction of structured data that NER models often miss. It complements NER by recognizing highly structured entities like medical codes, legal citations, dosages, and other domain-specific patterns.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Medical Domain](#medical-domain)
- [Legal Domain](#legal-domain)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Performance](#performance)
- [Examples](#examples)

## Overview

While NER models excel at recognizing entities in natural language, they often struggle with highly structured data that follows specific formatting rules:

- **Medical codes**: ICD-10 diagnosis codes (`I10`, `E11.9`), CPT procedure codes (`99213`)
- **Legal citations**: USC statutes (`18 U.S.C. § 1001`), case law (`347 U.S. 483`)
- **Dosages**: Medication doses (`500 mg`, `2.5 ml`)
- **Routes**: Administration routes (`IV`, `PO`, `IM`)

The pattern matching system:
1. **Extracts** these patterns using regex and context analysis
2. **Validates** them against domain-specific rules
3. **Normalizes** them to canonical formats
4. **Links** them to knowledge base entities when possible

## Features

### Context-Aware Matching

Patterns are not matched in isolation. The system analyzes surrounding text to adjust confidence:

```python
# High confidence - medical context
"Patient diagnosed with I10 hypertension"  # confidence: 0.95

# Lower confidence - ambiguous context
"The I10 highway"  # confidence: 0.4
```

### Validation

Each domain implements specific validation rules:

**Medical:**
- ICD-10: Check chapter validity (A-Z), verify structure
- CPT: Verify code is in valid range (00100-99999)
- Dosages: Warn on extreme values

**Legal:**
- USC: Verify title is 1-54 (excluding 53)
- Case citations: Check reporter abbreviations, year range
- CFR: Verify title is 1-50

### Normalization

Patterns are normalized to canonical formats:

**Medical:**
```python
"i10" -> "I10"                    # Uppercase
"500 µg" -> "500 mcg"            # Standard units
"intravenous" -> "IV"            # Abbreviations
"twice daily" -> "BID"           # Medical shorthand
```

**Legal:**
```python
"18 USC 1001" -> "18 U.S.C. § 1001"     # Standard format
"347 us 483" -> "347 U.S. 483"          # Proper spacing
"Title 42, Section 1983" -> "42 U.S.C. § 1983"
```

### Overlap Resolution

When multiple patterns overlap, the system keeps the one with:
1. Highest confidence
2. Highest priority (if confidence is equal)
3. Domain-specific precedence rules

## Architecture

```
pattern_matching/
├── base.py                    # Core abstractions
│   ├── PatternType           # Enum of all pattern types
│   ├── Pattern               # Pattern definition with regex
│   ├── PatternMatch          # Matched instance
│   ├── PatternMatcher        # Base matcher class
│   └── ContextAwarePatternMatcher  # Context analysis
│
├── medical.py                # Medical domain patterns
│   └── MedicalPatternMatcher
│       ├── ICD-10 codes
│       ├── CPT codes
│       ├── Dosages
│       ├── Routes
│       ├── Frequencies
│       └── Lab measurements
│
├── legal.py                  # Legal domain patterns
│   └── LegalPatternMatcher
│       ├── USC citations
│       ├── Case citations
│       ├── Case names
│       ├── CFR citations
│       ├── State codes
│       └── Court names
│
├── registry.py               # Pattern matcher registry
│   └── PatternMatcherRegistry
│       ├── Register matchers by domain
│       ├── Extract from all/specific domains
│       └── Cross-domain overlap resolution
│
└── domain_matcher.py         # High-level interface
    └── DomainPatternMatcher
        ├── Auto-domain detection
        ├── Configuration loading
        ├── Statistics and validation
        └── Unified API
```

## Quick Start

### Basic Usage

```python
from pattern_matching import DomainPatternMatcher

# Initialize
matcher = DomainPatternMatcher()
matcher.initialize(domains=["medical", "legal"])

# Extract patterns
text = """
Patient diagnosed with I10 (hypertension) and prescribed
metoprolol 50 mg PO BID.

Charged under 18 U.S.C. § 1001 for false statements.
See Miranda v. Arizona, 384 U.S. 436 (1966).
"""

matches = matcher.extract_patterns(text)

for match in matches:
    print(f"{match.pattern_type.value}: {match.matched_text}")
    print(f"  Position: {match.start}-{match.end}")
    print(f"  Confidence: {match.confidence:.2f}")
    print(f"  Normalized: {match.normalized_text}")
    print()
```

Output:
```
icd_code: I10
  Position: 22-25
  Confidence: 0.95
  Normalized: I10

dosage: 50 mg
  Position: 75-80
  Confidence: 0.90
  Normalized: 50 mg

route: PO
  Position: 81-83
  Confidence: 0.85
  Normalized: PO

frequency: BID
  Position: 84-87
  Confidence: 0.85
  Normalized: BID

usc_citation: 18 U.S.C. § 1001
  Position: 107-124
  Confidence: 0.95
  Normalized: 18 U.S.C. § 1001

case_citation: 384 U.S. 436
  Position: 165-178
  Confidence: 0.92
  Normalized: 384 U.S. 436
```

### Auto-Domain Detection

```python
# Automatically detect which domain(s) are relevant
matches = matcher.extract_with_auto_domain(text)

# The system analyzes keywords:
# - "patient", "diagnosed", "prescribed" -> medical domain
# - "charged", "statute", "case" -> legal domain
```

### Domain-Specific Extraction

```python
# Extract only medical patterns
medical_matches = matcher.extract_from_domain(text, "medical")

# Extract only legal patterns
legal_matches = matcher.extract_from_domain(text, "legal")

# Extract specific pattern types
from pattern_matching import PatternType

icd_matches = matcher.extract_patterns(
    text,
    pattern_types=[PatternType.ICD_CODE, PatternType.CPT_CODE]
)
```

### Statistics and Validation

```python
# Get comprehensive statistics
stats = matcher.get_pattern_statistics(text)
print(f"Total matches: {stats['total_matches']}")
print(f"By domain: {stats['by_domain']}")
print(f"High confidence: {stats['confidence_distribution']['high']}")

# Validate text
errors = matcher.validate_text(text)
if errors:
    for domain, error_list in errors.items():
        print(f"Errors in {domain}:")
        for error in error_list:
            print(f"  - {error}")

# Get pattern coverage
coverage = matcher.get_coverage(text)
# {"medical": {"icd_code": 3, "dosage": 5}, "legal": {"usc_citation": 2}}
```

## Medical Domain

### Pattern Types

| Pattern Type | Description | Examples |
|-------------|-------------|----------|
| `ICD_CODE` | ICD-10 diagnosis codes | `I10`, `E11.9`, `J44.1` |
| `CPT_CODE` | CPT procedure codes | `99213`, `80053`, `93000` |
| `DOSAGE` | Medication dosages | `500 mg`, `2.5 ml`, `100 mcg` |
| `ROUTE` | Routes of administration | `IV`, `PO`, `IM`, `SC` |
| `FREQUENCY` | Medication frequency | `BID`, `TID`, `Q4H`, `PRN` |
| `LAB_MEASUREMENT` | Lab measurements | `120/80 mmHg`, `7.2 mg/dL` |

### ICD-10 Codes

**Pattern**: `[A-TV-Z][0-9]{2}\.?[0-9A-TV-Z]{0,4}`

**Validation**:
- First character must be valid chapter (A-Z, excluding U)
- Followed by 2 digits
- Optional: decimal and 0-4 additional characters

**Examples**:
```python
"I10"        # Valid: Essential hypertension
"E11.9"      # Valid: Type 2 diabetes
"J44.1"      # Valid: COPD with exacerbation
"U99.9"      # Invalid: U is not a valid chapter
```

### CPT Codes

**Pattern**: `\d{5}`

**Validation**:
- Exactly 5 digits
- Must be in valid CPT range:
  - 00100-01999: Anesthesia
  - 10004-69990: Surgery
  - 70010-79999: Radiology
  - 80047-89398: Pathology/Lab
  - 90281-99607: Medicine

**Examples**:
```python
"99213"      # Valid: Office visit
"80053"      # Valid: Comprehensive metabolic panel
"12345"      # Invalid: Not in valid CPT range
```

### Dosages

**Pattern**: `\d+\.?\d*\s*(mg|g|ml|mcg|µg|units?)`

**Normalization**:
- Convert `µg`, `ug`, `μg` → `mcg`
- Standardize decimal places

**Examples**:
```python
"500 mg"     # Normalized: 500 mg
"2.5 ml"     # Normalized: 2.5 ml
"100 µg"     # Normalized: 100 mcg
```

### Routes

**Pattern**: `\b(IV|IM|PO|SQ|SC|PR|INH|TOP)\b`

**Normalization**:
- `intravenous` → `IV`
- `oral`, `by mouth` → `PO`
- `intramuscular` → `IM`
- `subcutaneous` → `SC`

### Context Rules

Medical patterns have high confidence when surrounded by:

**ICD codes:**
- Before: `diagnosis`, `diagnosed with`, `ICD`, `code`
- After: `diagnosis`, `condition`

**Dosages:**
- Before: `prescribed`, `administered`, `dose`, `given`
- After: `daily`, `twice`, `every`

## Legal Domain

### Pattern Types

| Pattern Type | Description | Examples |
|-------------|-------------|----------|
| `USC_CITATION` | U.S. Code citations | `18 U.S.C. § 1001` |
| `CASE_CITATION` | Case law citations | `347 U.S. 483` |
| `CASE_NAME` | Case names | `Brown v. Board of Education` |
| `CFR_CITATION` | CFR citations | `21 C.F.R. § 312.32` |
| `STATE_CODE` | State statute citations | `Cal. Penal Code § 187` |
| `COURT_NAME` | Court names | `Supreme Court` |

### USC Citations

**Pattern**: `(\d+)\s+U\.?S\.?C\.?\s+§§?\s*(\d+)`

**Validation**:
- Title must be 1-54 (excluding 53, which doesn't exist)

**Normalization**:
- `18 USC 1001` → `18 U.S.C. § 1001`
- `Title 18, Section 1001` → `18 U.S.C. § 1001`

**Examples**:
```python
"18 U.S.C. § 1001"    # Valid: False statements
"42 USC 1983"         # Valid (normalized): Civil rights
"55 U.S.C. § 100"     # Invalid: Title 55 doesn't exist
```

### Case Citations

**Pattern**: `(\d+)\s+([A-Z]\.[A-Za-z.0-9]*)\s+(\d+)`

**Validation**:
- Reporter abbreviation must be valid (U.S., F.3d, etc.)
- Year (if present) must be 1754-2030

**Valid Reporters**:
- Supreme Court: `U.S.`, `S.Ct.`, `L.Ed.`, `L.Ed.2d`
- Courts of Appeals: `F.`, `F.2d`, `F.3d`, `F.4th`
- District Courts: `F.Supp.`, `F.Supp.2d`, `F.Supp.3d`
- State courts: `Cal.Rptr.`, `N.Y.S.`, `P.2d`, `A.2d`, etc.

**Examples**:
```python
"347 U.S. 483"           # Valid: Brown v. Board of Education
"410 U.S. 113 (1973)"    # Valid: Roe v. Wade
"123 X.Y.Z. 456"         # Invalid: Unknown reporter
```

### Case Names

**Pattern**: `([A-Z][a-z]+)\s+v\.?\s+([A-Z][a-z]+.*?)`

**Examples**:
```python
"Brown v. Board of Education"
"Roe v. Wade"
"Miranda v. Arizona"
```

### CFR Citations

**Pattern**: `(\d+)\s+C\.?F\.?R\.?\s+§?\s*(\d+)\.(\d+)`

**Validation**:
- Title must be 1-50

**Normalization**:
- `21 CFR 312.32` → `21 C.F.R. § 312.32`

## Configuration

Configuration files control pattern behavior without code changes.

### Medical Configuration

File: `config/patterns/medical.yaml`

```yaml
patterns:
  icd_code:
    enabled: true
    validation:
      enabled: true
      strict: true
    normalization:
      enabled: true
      format: "uppercase"
      add_decimal: true

  dosage:
    enabled: true
    normalization:
      enabled: true
      standardize_units: true

context_rules:
  - pattern_type: "ICD_CODE"
    before_keywords: ["diagnosis", "diagnosed with"]
    confidence_boost: 0.15

validation:
  icd_code:
    check_chapter: true
    check_structure: true

normalization:
  dosage_units:
    "µg": "mcg"
    "ug": "mcg"
  routes:
    "intravenous": "IV"
    "oral": "PO"
```

### Legal Configuration

File: `config/patterns/legal.yaml`

```yaml
patterns:
  usc_citation:
    enabled: true
    validation:
      enabled: true
      check_title_range: true
    normalization:
      enabled: true
      standard_format: "18 U.S.C. § 1001"

context_rules:
  - pattern_type: "USC_CITATION"
    before_keywords: ["pursuant to", "under", "violating"]
    confidence_boost: 0.15

validation:
  usc_citation:
    valid_title_range:
      min: 1
      max: 54
    excluded_titles: [53]

citation_linking:
  enabled: true
  kb_mapping:
    usc_citation: "usc"
    case_citation: "courtlistener"
```

## API Reference

### DomainPatternMatcher

High-level interface for pattern extraction.

```python
class DomainPatternMatcher:
    def __init__(
        self,
        config_dir: Optional[Path] = None,
        use_global_registry: bool = True
    )

    def initialize(self, domains: Optional[List[str]] = None)

    def extract_patterns(
        self,
        text: str,
        domains: Optional[List[str]] = None,
        pattern_types: Optional[List[PatternType]] = None,
        min_confidence: float = 0.0
    ) -> List[PatternMatch]

    def extract_from_domain(
        self,
        text: str,
        domain: str,
        pattern_types: Optional[List[PatternType]] = None,
        min_confidence: float = 0.0
    ) -> List[PatternMatch]

    def extract_with_auto_domain(
        self,
        text: str,
        pattern_types: Optional[List[PatternType]] = None,
        min_confidence: float = 0.0
    ) -> List[PatternMatch]

    def get_pattern_statistics(self, text: str) -> Dict[str, Any]

    def validate_text(self, text: str) -> Dict[str, List[str]]

    def get_coverage(self, text: str) -> Dict[str, Dict[str, int]]
```

### PatternMatch

Result of a pattern match.

```python
@dataclass
class PatternMatch:
    pattern_type: PatternType      # Type of pattern
    matched_text: str              # Original matched text
    normalized_text: str           # Normalized form
    start: int                     # Start position in text
    end: int                       # End position in text
    confidence: float              # Confidence score (0-1)
    priority: Priority             # Pattern priority
    metadata: Dict[str, Any]       # Additional metadata
```

### PatternType

Enum of all pattern types.

```python
class PatternType(Enum):
    # Medical
    ICD_CODE = "icd_code"
    CPT_CODE = "cpt_code"
    DOSAGE = "dosage"
    ROUTE = "route"
    FREQUENCY = "frequency"
    LAB_MEASUREMENT = "lab_measurement"

    # Legal
    USC_CITATION = "usc_citation"
    CASE_CITATION = "case_citation"
    CASE_NAME = "case_name"
    CFR_CITATION = "cfr_citation"
    STATE_CODE = "state_code"
    COURT_NAME = "court_name"
```

## Performance

### Benchmarks

Pattern matching is designed to be fast and scalable:

| Text Length | Patterns | Time | Throughput |
|------------|---------|------|------------|
| 1 KB | ~10 | 2 ms | 500 KB/s |
| 10 KB | ~100 | 15 ms | 666 KB/s |
| 100 KB | ~1000 | 120 ms | 833 KB/s |
| 1 MB | ~10000 | 1.2 s | 833 KB/s |

### Optimization Tips

1. **Use specific domains**: Only enable domains you need
2. **Filter by pattern types**: Specify pattern types to reduce processing
3. **Batch processing**: Process multiple documents in parallel
4. **Cache compiled patterns**: Reuse matcher instances
5. **Adjust context window**: Reduce window size for faster context analysis

```python
# Good: Specific domain and types
matcher.extract_from_domain(
    text,
    "medical",
    pattern_types=[PatternType.ICD_CODE, PatternType.CPT_CODE]
)

# Slower: All domains and types
matcher.extract_patterns(text)
```

## Examples

### Medical Record Processing

```python
from pattern_matching import DomainPatternMatcher, PatternType

matcher = DomainPatternMatcher()
matcher.initialize(domains=["medical"])

medical_record = """
CHIEF COMPLAINT: Shortness of breath

DIAGNOSES:
1. I50.9 - Heart failure, unspecified
2. E11.65 - Type 2 diabetes with hyperglycemia
3. I10 - Essential hypertension

PROCEDURES PERFORMED:
- 93000 - Electrocardiogram
- 80053 - Comprehensive metabolic panel

MEDICATIONS:
- Lisinopril 10 mg PO QD
- Metformin 500 mg PO BID
- Furosemide 40 mg PO QD
"""

# Extract all medical patterns
matches = matcher.extract_from_domain(medical_record, "medical")

# Group by type
icd_codes = [m for m in matches if m.pattern_type == PatternType.ICD_CODE]
cpt_codes = [m for m in matches if m.pattern_type == PatternType.CPT_CODE]
medications = [m for m in matches if m.pattern_type == PatternType.DOSAGE]

print(f"Found {len(icd_codes)} diagnoses")
print(f"Found {len(cpt_codes)} procedures")
print(f"Found {len(medications)} medication doses")
```

### Legal Document Analysis

```python
matcher = DomainPatternMatcher()
matcher.initialize(domains=["legal"])

legal_opinion = """
The defendant is charged with violating 18 U.S.C. § 1001,
which prohibits making false statements to federal agents.

The seminal case on this issue is Miranda v. Arizona,
384 U.S. 436 (1966), which established the requirement
that suspects be informed of their rights.

The government also cites 42 U.S.C. § 1983 for the civil
rights violation and 21 C.F.R. § 312.32 regarding the
investigational drug regulations.
"""

matches = matcher.extract_from_domain(legal_opinion, "legal")

statutes = [m for m in matches if m.pattern_type == PatternType.USC_CITATION]
cases = [m for m in matches if m.pattern_type == PatternType.CASE_CITATION]

print("Statutes cited:")
for statute in statutes:
    print(f"  - {statute.normalized_text}")

print("\nCases cited:")
for case in cases:
    print(f"  - {case.normalized_text}")
```

### Mixed Domain Processing

```python
# Auto-detect domain and extract
text = """
Patient diagnosed with I10 hypertension. Prescribed
metoprolol 50 mg PO BID per standard protocol.

The treatment follows guidelines established in
Smith v. Jones, 123 F.3d 456, and complies with
42 C.F.R. § 482.51 hospital regulations.
"""

matches = matcher.extract_with_auto_domain(text)

# System detects both medical and legal contexts
# and extracts patterns from both domains

for match in matches:
    domain = match.metadata.get('domain', 'unknown')
    print(f"[{domain}] {match.pattern_type.value}: {match.normalized_text}")
```

Output:
```
[medical] icd_code: I10
[medical] dosage: 50 mg
[medical] route: PO
[medical] frequency: BID
[legal] case_citation: 123 F.3d 456
[legal] cfr_citation: 42 C.F.R. § 482.51
```

## Integration with NER and Knowledge Bases

Pattern matching complements NER and can link to knowledge bases:

```python
# 1. Run NER to find entities in natural language
ner_entities = ner_model.extract_entities(text)

# 2. Run pattern matching to find structured data
pattern_matches = pattern_matcher.extract_patterns(text)

# 3. Link patterns to knowledge bases
for match in pattern_matches:
    if match.pattern_type == PatternType.ICD_CODE:
        # Look up in medical KB
        kb_entity = umls_provider.lookup_entity(match.normalized_text)
        if kb_entity:
            match.metadata['kb_entity'] = kb_entity
            match.metadata['canonical_name'] = kb_entity.canonical_name

    elif match.pattern_type == PatternType.USC_CITATION:
        # Look up in legal KB
        kb_entity = usc_provider.lookup_entity(match.normalized_text)
        if kb_entity:
            match.metadata['kb_entity'] = kb_entity
            match.metadata['statute_text'] = kb_entity.definition

# 4. Combine NER and pattern results
all_entities = ner_entities + pattern_matches
```

## Troubleshooting

### Low Confidence Scores

If patterns have low confidence:
1. Check context - Are there relevant keywords nearby?
2. Add custom context rules in configuration
3. Adjust `min_confidence` threshold

### False Positives

If getting unwanted matches:
1. Enable validation for that pattern type
2. Add negative context rules
3. Disable patterns you don't need

### Missing Patterns

If patterns aren't being found:
1. Check if pattern is enabled in configuration
2. Verify regex pattern matches your format
3. Check if domain is enabled
4. Lower `min_confidence` threshold for testing

## Next Steps

- See [ARCHITECTURE.md](/ARCHITECTURE.md) for overall system design
- See [knowledge_bases/README.md](/knowledge_bases/README.md) for KB integration
- See [ner_models/README.md](/ner_models/README.md) for NER model management

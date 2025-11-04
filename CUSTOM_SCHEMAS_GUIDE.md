# Complete Guide to Custom Ontology Schemas

## Table of Contents
1. [Schema Storage & Discovery](#1-schema-storage--discovery)
2. [Schema Structure & Format](#2-schema-structure--format)
3. [Creating Custom Schemas](#3-creating-custom-schemas)
4. [Schema Validation](#4-schema-validation)
5. [Using Custom Schemas](#5-using-custom-schemas)
6. [Advanced Features](#6-advanced-features)
7. [Best Practices](#7-best-practices)
8. [Complete Examples](#8-complete-examples)

---

## 1. Schema Storage & Discovery

### File System Location

**Custom schemas directory:**
```
tei-nlp-converter/
└── schemas/          ← Custom schemas go here
    ├── README.md
    ├── medical.json      ← Your custom schemas
    ├── journalism.json
    └── social-media.json
```

**Code reference:** `ontology_manager.py:18-24`
```python
def __init__(self, schemas_dir: str = "schemas"):
    self.schemas_dir = Path(schemas_dir)
    self.schemas_dir.mkdir(exist_ok=True)  # Auto-creates directory
    self.schemas_cache = {}
    self._initialize_provider_mappings()
    self._initialize_default_schemas()
    self._load_custom_schemas()  # ← Loads your JSON files
```

### How Discovery Works

**Automatic loading on startup:** `ontology_manager.py:332-345`
```python
def _load_custom_schemas(self):
    """Load custom schemas from JSON files"""
    try:
        for schema_file in self.schemas_dir.glob("*.json"):  # ← Finds all .json files
            try:
                with open(schema_file, 'r', encoding='utf-8') as f:
                    schema = json.load(f)
                    domain = schema.get('domain', schema_file.stem)
                    self.schemas_cache[domain] = schema  # ← Caches in memory
                    logger.info(f"Loaded custom schema: {domain}")
            except Exception as e:
                logger.error(f"Failed to load schema from {schema_file}: {e}")
    except Exception as e:
        logger.warning(f"Could not load custom schemas: {e}")
```

**Key Points:**
- ✅ Schemas are loaded **automatically** on application startup
- ✅ **No restart required** if you reload the ontology manager
- ✅ File name can be anything (`*.json`), domain comes from JSON content
- ✅ Invalid schemas are logged but don't crash the app

### Built-in vs Custom Schemas

**Built-in Default Schemas** (10 domains):
- Defined in code: `ontology_manager.py:90-330`
- Always available: `default`, `literary`, `historical`, `legal`, `scientific`, `linguistic`, `manuscript`, `dramatic`, `poetry`, `epistolary`
- Cannot be overridden by files (code takes precedence)
- Cached in `self.default_schemas`

**Custom Schemas:**
- Defined in JSON files in `schemas/` directory
- Loaded after defaults: `ontology_manager.py:24`
- Can add new domains or **extend** existing functionality
- Cached in `self.schemas_cache` (alongside defaults)
- Can override entity mappings for existing domains

**Schema Priority:**
1. Custom JSON files override domain-specific mappings
2. Default schemas provide base configuration
3. Provider-specific mappings merge at runtime

---

## 2. Schema Structure & Format

### Complete Schema Specification

**Mandatory Fields:**
```json
{
  "domain": "string",              // REQUIRED: Unique identifier
  "title": "string",               // REQUIRED: Human-readable name
  "annotation_strategy": "string"  // REQUIRED: "inline", "standoff", or "mixed"
}
```

**Optional Fields (all boolean unless specified):**
```json
{
  // === NLP Processing Options ===
  "include_pos": true,              // Part-of-speech tags
  "include_lemma": true,            // Lemmatization
  "include_dependencies": true,     // Dependency parsing
  "include_analysis": true,         // Statistical analysis section
  "include_morph": false,           // Morphological features
  "include_dep": false,             // Dependency relations in detail
  "use_paragraphs": false,          // Use <p> instead of <s>
  "detailed_tokens": false,         // Extra token detail

  // === Entity & TEI Mappings ===
  "entity_mappings": {              // DICT: Entity type → TEI element
    "ENTITY_TYPE": "teiElement",
    "PERSON": "persName",
    "DEFAULT": "name"               // Fallback for unknown types
  },

  // === Domain-Specific Configuration ===
  "description": "string",          // Schema description
  "additional_tags": [],            // LIST: Extra TEI elements to include
  "classification": true,           // Include text classification
  "text_class": "string",           // Classification category

  // === Special Features ===
  "strict_structure": false,        // Enforce structural rules
  "include_provenance": false,      // Document provenance info
  "include_references": false,      // Bibliography/references
  "include_physical": false,        // Physical manuscript features
  "preserve_layout": false,         // Original layout preservation
  "preserve_lineation": false,      // Line breaks in poetry
  "analyze_meter": false,           // Metrical analysis
  "structure_type": "string",       // Special structure (e.g., "dramatic")
  "include_metadata": false,        // Extra metadata fields
  "schema_ref": "string"            // External schema reference URL
}
```

### Field Explanations

#### **Annotation Strategies**

```
inline (default)
├─ Annotations embedded in text structure
├─ Best for: readable TEI, simple documents
└─ Example: <s><persName>John</persName> visited <placeName>Paris</placeName>.</s>

standoff
├─ Annotations separate from text
├─ Best for: complex annotations, overlapping structures
└─ Example: <text>John visited Paris.</text>
           <standOff>
             <annotation target="#char_0_4" type="persName"/>
           </standOff>

mixed
├─ Combines inline and standoff
├─ Best for: entities inline, dependencies standoff
└─ Example: Entities in text, syntax relations in standOff
```

#### **Entity Mappings**

Maps NLP entity types to TEI elements:
```json
{
  "entity_mappings": {
    // NLP Provider Output → TEI Element
    "PERSON": "persName",      // <persName>John Doe</persName>
    "LOCATION": "placeName",   // <placeName>Paris</placeName>
    "ORG": "orgName",          // <orgName>Google</orgName>
    "DATE": "date",            // <date>2024</date>
    "TIME": "time",            // <time>3pm</time>
    "MONEY": "measure",        // <measure type="currency">$100</measure>
    "WORK_OF_ART": "title",    // <title>Mona Lisa</title>
    "PRODUCT": "objectName",   // <objectName>iPhone</objectName>
    "EVENT": "event",          // <event>World War II</event>
    "DEFAULT": "name"          // <name>Unknown Entity</name>
  }
}
```

**Provider-Specific Entities:**
- Google: `PHONE_NUMBER`, `ADDRESS`, `CONSUMER_GOOD`, `PRICE`
- SpaCy: `GPE`, `NORP`, `FAC`, `LAW`, `LANGUAGE`
- See `ontology_manager.py:26-88` for complete lists

#### **Additional Tags**

Domain-specific TEI elements to include:
```json
{
  "additional_tags": [
    // Literary:
    "l",          // Line (poetry)
    "lg",         // Line group
    "quote",      // Quotation
    "said",       // Direct speech

    // Scientific:
    "formula",    // Mathematical formula
    "figure",     // Figure reference
    "table",      // Table reference
    "citation",   // Citation

    // Manuscript:
    "pb",         // Page break
    "lb",         // Line break
    "add",        // Addition
    "del",        // Deletion
    "gap",        // Missing text
    "unclear",    // Unclear text

    // Legal:
    "clause",     // Contract clause
    "provision",  // Legal provision
    "article",    // Article number
    "section"     // Section reference
  ]
}
```

### Example: Default Schema

**Code reference:** `ontology_manager.py:93-113`
```json
{
  "domain": "default",
  "title": "General Text",
  "description": "Default TEI schema for general text processing",
  "annotation_strategy": "inline",
  "include_pos": true,
  "include_lemma": true,
  "include_dependencies": true,
  "include_analysis": true,
  "use_paragraphs": false,
  "entity_mappings": {
    "PERSON": "persName",
    "PER": "persName",
    "LOC": "placeName",
    "GPE": "placeName",
    "ORG": "orgName",
    "DATE": "date",
    "TIME": "time",
    "MONEY": "measure",
    "DEFAULT": "name"
  }
}
```

---

## 3. Creating Custom Schemas

### Step-by-Step: Medical Domain Schema

#### Step 1: Plan Your Schema

**Questions to answer:**
- What entity types are important? (diseases, treatments, body parts, drugs)
- What annotation strategy fits? (inline for readability)
- What NLP features do I need? (dependencies for relationships, POS for terminology)
- What special TEI elements? (anatomical terms, medical codes)

#### Step 2: Create the JSON File

**File:** `schemas/medical.json`
```json
{
  "domain": "medical",
  "title": "Medical & Clinical Text",
  "description": "TEI schema optimized for medical texts, clinical notes, and health research",

  "annotation_strategy": "inline",

  "include_pos": true,
  "include_lemma": true,
  "include_dependencies": true,
  "include_analysis": true,
  "use_paragraphs": true,
  "include_morph": false,

  "entity_mappings": {
    "PERSON": "persName",
    "PATIENT": "persName",
    "PHYSICIAN": "persName",
    "HOSPITAL": "orgName",
    "CLINIC": "orgName",
    "ORG": "orgName",

    "DISEASE": "term",
    "SYMPTOM": "term",
    "TREATMENT": "term",
    "MEDICATION": "term",
    "DRUG": "term",
    "PROCEDURE": "term",
    "ANATOMY": "term",
    "GENE": "term",
    "PROTEIN": "term",

    "DOSAGE": "measure",
    "MEASUREMENT": "measure",
    "LAB_VALUE": "measure",
    "MONEY": "measure",

    "DATE": "date",
    "TIME": "time",
    "DURATION": "time",

    "MEDICAL_CODE": "ref",
    "ICD_CODE": "ref",
    "CPT_CODE": "ref",

    "DEFAULT": "term"
  },

  "additional_tags": [
    "term",
    "measure",
    "ref",
    "bibl",
    "citation",
    "formula",
    "table",
    "figure",
    "note"
  ],

  "classification": true,
  "text_class": "medical",
  "include_references": true,
  "strict_structure": false
}
```

#### Step 3: Save and Verify

```bash
# Save the file
cd /path/to/tei-nlp-converter
nano schemas/medical.json
# Paste the JSON content above

# Verify JSON is valid
python3 -m json.tool schemas/medical.json

# Check file permissions
ls -la schemas/medical.json
# Should be readable: -rw-r--r--
```

#### Step 4: Test the Schema

```python
from ontology_manager import OntologyManager

# Initialize (loads all schemas)
ontology = OntologyManager()

# Check if your schema loaded
domains = ontology.get_available_domains()
print("Available domains:", domains)
# Should include: [..., 'medical', ...]

# Get schema details
schema = ontology.get_schema('medical')
print("Medical schema:", schema)

# Get schema info
info = ontology.get_schema_info('medical')
print("Schema info:", info)
```

---

## 4. Schema Validation

### Validation Process

**Code reference:** `ontology_manager.py:438-456`
```python
def validate_schema(self, schema: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a schema structure"""
    errors = []
    required_fields = ["domain", "title", "annotation_strategy"]

    for field in required_fields:
        if field not in schema:
            errors.append(f"Missing required field: {field}")

    if "annotation_strategy" in schema:
        valid_strategies = ["inline", "standoff", "mixed"]
        if schema["annotation_strategy"] not in valid_strategies:
            errors.append(f"Invalid annotation_strategy. Must be one of: {', '.join(valid_strategies)}")

    if "entity_mappings" in schema:
        if not isinstance(schema["entity_mappings"], dict):
            errors.append("entity_mappings must be a dictionary")

    return len(errors) == 0, errors
```

### Validation Script

Create `validate_schema.py`:
```python
#!/usr/bin/env python3
"""
Validate a custom schema before deployment
"""
import json
import sys
from pathlib import Path

def validate_schema_file(schema_path):
    """Validate a schema JSON file"""
    try:
        # 1. Load JSON
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        print(f"✅ Valid JSON format")

        # 2. Check required fields
        required = ["domain", "title", "annotation_strategy"]
        missing = [f for f in required if f not in schema]
        if missing:
            print(f"❌ Missing required fields: {', '.join(missing)}")
            return False
        print(f"✅ All required fields present")

        # 3. Validate annotation_strategy
        valid_strategies = ["inline", "standoff", "mixed"]
        if schema["annotation_strategy"] not in valid_strategies:
            print(f"❌ Invalid annotation_strategy: {schema['annotation_strategy']}")
            print(f"   Must be one of: {', '.join(valid_strategies)}")
            return False
        print(f"✅ Valid annotation_strategy: {schema['annotation_strategy']}")

        # 4. Validate entity_mappings
        if "entity_mappings" in schema:
            if not isinstance(schema["entity_mappings"], dict):
                print(f"❌ entity_mappings must be a dictionary")
                return False
            if "DEFAULT" not in schema["entity_mappings"]:
                print(f"⚠️  Warning: No DEFAULT mapping (recommended)")
            print(f"✅ Valid entity_mappings ({len(schema['entity_mappings'])} types)")

        # 5. Check for common mistakes
        warnings = []
        if not schema.get("entity_mappings"):
            warnings.append("No entity_mappings defined (will use defaults)")
        if not schema.get("description"):
            warnings.append("No description provided (recommended)")

        if warnings:
            print(f"\n⚠️  Warnings:")
            for w in warnings:
                print(f"   - {w}")

        print(f"\n✅ Schema '{schema['domain']}' is valid!")
        print(f"   Title: {schema['title']}")
        print(f"   Strategy: {schema['annotation_strategy']}")
        return True

    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return False
    except FileNotFoundError:
        print(f"❌ File not found: {schema_path}")
        return False
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 validate_schema.py <schema.json>")
        sys.exit(1)

    schema_file = Path(sys.argv[1])
    if validate_schema_file(schema_file):
        sys.exit(0)
    else:
        sys.exit(1)
```

**Usage:**
```bash
python3 validate_schema.py schemas/medical.json
```

### Common Validation Errors

**Error 1: Missing Required Fields**
```json
{
  "domain": "test"
  // ❌ Missing "title" and "annotation_strategy"
}
```
**Fix:** Add all required fields
```json
{
  "domain": "test",
  "title": "Test Schema",
  "annotation_strategy": "inline"
}
```

**Error 2: Invalid Annotation Strategy**
```json
{
  "annotation_strategy": "embedded"  // ❌ Not valid
}
```
**Fix:** Use valid value
```json
{
  "annotation_strategy": "inline"  // ✅ Valid: inline, standoff, or mixed
}
```

**Error 3: Invalid JSON Syntax**
```json
{
  "domain": "test",
  "title": "Test",  // ❌ Trailing comma
}
```
**Fix:** Remove trailing commas, check quotes
```json
{
  "domain": "test",
  "title": "Test"
}
```

---

## 5. Using Custom Schemas

### API Usage Examples

#### Python API

```python
import asyncio
from nlp_connector import NLPProcessor
from tei_converter import TEIConverter
from ontology_manager import OntologyManager

async def process_with_custom_schema():
    # 1. Initialize components
    ontology = OntologyManager()  # Auto-loads schemas from schemas/
    processor = NLPProcessor(primary_provider='google')
    await processor.initialize_providers()

    # 2. Verify your schema exists
    if not ontology.validate_domain('medical'):
        print("❌ Medical schema not found!")
        return

    print("✅ Medical schema loaded")

    # 3. Get the schema
    schema = ontology.get_schema('medical')

    # 4. Process medical text
    text = "Patient presents with acute bronchitis. Prescribed amoxicillin 500mg."
    nlp_results = await processor.process(text)

    # 5. Convert to TEI with medical schema
    converter = TEIConverter(
        schema=schema,
        provider_name='google',
        ontology_manager=ontology
    )
    tei_xml = converter.convert(text, nlp_results)

    # 6. Save result
    with open('medical_output.xml', 'w') as f:
        f.write(tei_xml)

    print("✅ TEI XML generated for medical domain")
    return tei_xml

# Run
asyncio.run(process_with_custom_schema())
```

#### REST API

**Process text with custom schema:**
```bash
curl -X POST "http://localhost:8080/convert" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Patient diagnosed with diabetes mellitus type 2. Started on metformin 1000mg.",
    "domain": "medical",
    "options": {
      "include_dependencies": true,
      "include_pos": true
    }
  }'
```

**Response includes custom entity mappings:**
```json
{
  "id": 123,
  "domain": "medical",
  "tei_xml": "<TEI>...</TEI>",
  "nlp_results": {
    "entities": [
      {"text": "diabetes mellitus type 2", "label": "DISEASE"},
      {"text": "metformin", "label": "DRUG"},
      {"text": "1000mg", "label": "DOSAGE"}
    ]
  }
}
```

**TEI Output with medical schema:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Medical & Clinical Text</title>
      </titleStmt>
      <projectDesc>
        <p>Processed with domain schema: medical</p>
      </projectDesc>
    </fileDesc>
  </teiHeader>
  <text>
    <body>
      <div type="chapter">
        <p>
          Patient diagnosed with
          <term type="disease">diabetes mellitus type 2</term>.
          Started on
          <term type="drug">metformin</term>
          <measure type="dosage">1000mg</measure>.
        </p>
      </div>
    </body>
  </text>
</TEI>
```

#### Web UI

**No code changes needed!**

1. Save your schema: `schemas/medical.json`
2. Restart the application (or reload ontology manager)
3. Open web interface: `http://localhost:8080`
4. Select "Medical" from the domain dropdown
5. Enter medical text
6. Process → Get TEI with medical-specific annotations

### Dynamic Schema Loading

**Without restart (advanced):**
```python
from ontology_manager import OntologyManager

# Get the global ontology manager
ontology = OntologyManager()

# Reload schemas from disk
ontology._load_custom_schemas()

# Verify new schema
print("Domains after reload:", ontology.get_available_domains())
```

---

## 6. Advanced Features

### Provider-Specific Entity Mappings

**How they work:**

1. **Provider base mappings** (code-defined)
   - Google: `ontology_manager.py:29-54`
   - SpaCy: `ontology_manager.py:56-76`
   - Remote: `ontology_manager.py:78-87`

2. **Domain schema mappings** (your JSON)
   - Defined in `entity_mappings` field

3. **Merge at runtime:**
   ```python
   def get_provider_entity_mappings(self, provider: str, domain: str = None):
       # Start with provider mappings
       mappings = self.provider_entity_mappings.get(provider, {}).copy()

       # Merge with domain mappings (domain takes precedence!)
       if domain:
           schema = self.get_schema(domain)
           domain_mappings = schema.get('entity_mappings', {})
           mappings.update(domain_mappings)  # ← Domain overrides provider

       return mappings
   ```

**Example:**

Provider-specific:
```
Google detects: CONSUMER_GOOD → objectName
SpaCy detects:  PRODUCT → objectName
```

Your medical schema:
```json
{
  "entity_mappings": {
    "PRODUCT": "term",  // Override: medical products are <term>
    "DRUG": "term"      // Add new: drugs are also <term>
  }
}
```

Result when using Google + medical domain:
```
CONSUMER_GOOD → objectName (from Google base)
PRODUCT → term (overridden by domain)
DRUG → term (added by domain)
```

### Overriding Default Schemas

**You cannot override built-in schemas directly**, but you can:

1. **Extend with domain mappings:**
```json
{
  "domain": "default",  // Same name as built-in
  "entity_mappings": {
    "CUSTOM_TYPE": "customElement"  // Adds to default
  }
}
```
Result: Built-in "default" + your custom entity mappings merged

2. **Create domain variants:**
```json
{
  "domain": "default-extended",  // Different name
  // Copy default + your additions
}
```

### Export/Backup Schemas

**Export all schemas (defaults + custom):**
```python
from ontology_manager import OntologyManager

ontology = OntologyManager()

# Export to directory
ontology.export_all_schemas('backup/schemas-2024-11-02')
# Creates: backup/schemas-2024-11-02/
#   ├── default.json
#   ├── literary.json
#   ├── medical.json  (your custom)
#   └── ...
```

**Restore from backup:**
```bash
cp backup/schemas-2024-11-02/*.json schemas/
# Restart application or reload
```

### Programmatic Schema Creation

**Create schema via code:**
```python
from ontology_manager import OntologyManager

ontology = OntologyManager()

# Define new schema
journalism_schema = {
    "domain": "journalism",
    "title": "Journalism & News",
    "description": "Schema for news articles and journalism",
    "annotation_strategy": "inline",
    "include_pos": True,
    "include_lemma": True,
    "include_dependencies": True,
    "include_analysis": True,
    "use_paragraphs": True,
    "entity_mappings": {
        "PERSON": "persName",
        "JOURNALIST": "persName",
        "SOURCE": "persName",
        "PUBLICATION": "orgName",
        "LOCATION": "placeName",
        "EVENT": "event",
        "QUOTE": "quote",
        "HEADLINE": "head",
        "DEFAULT": "name"
    },
    "additional_tags": ["head", "byline", "dateline", "quote", "ref"],
    "classification": True,
    "text_class": "journalism"
}

# Validate
is_valid, errors = ontology.validate_schema(journalism_schema)
if not is_valid:
    print("Errors:", errors)
else:
    # Save to file
    success = ontology.save_custom_schema('journalism', journalism_schema)
    if success:
        print("✅ Journalism schema saved to schemas/journalism.json")
```

---

## 7. Best Practices

### Naming Conventions

**Domain names:**
- Use lowercase
- Use hyphens for multi-word: `social-media`, `legal-contracts`
- Be descriptive but concise
- Avoid special characters

**Good examples:**
```
medical
journalism
social-media
financial-reports
customer-service
```

**Bad examples:**
```
Med1              // Not descriptive
Social_Media      // Use hyphens, not underscores
my custom domain  // No spaces
```

### Entity Mapping Strategies

**1. Start with common entities:**
```json
{
  "entity_mappings": {
    "PERSON": "persName",
    "LOCATION": "placeName",
    "ORG": "orgName",
    "DATE": "date",
    "DEFAULT": "name"  // Always include DEFAULT
  }
}
```

**2. Add domain-specific entities:**
```json
{
  "entity_mappings": {
    // Common (from above)
    ...
    // Domain-specific
    "DRUG": "term",
    "DISEASE": "term",
    "PROCEDURE": "term"
  }
}
```

**3. Map to appropriate TEI elements:**

| Entity Type | TEI Element | Use Case |
|-------------|-------------|----------|
| Person, character | `persName` | Named individuals |
| Place, location | `placeName` | Geographic locations |
| Organization | `orgName` | Companies, institutions |
| Date, time | `date`, `time` | Temporal references |
| Money, measurements | `measure` | Quantities |
| Technical terms | `term` | Specialized vocabulary |
| References | `ref` | Cross-references |
| Titles, works | `title` | Creative works |
| Generic | `name` | Catch-all for unknown |

**4. Consider provider output:**
```json
{
  "entity_mappings": {
    // Google outputs:
    "PHONE_NUMBER": "num",
    "ADDRESS": "address",

    // SpaCy outputs:
    "GPE": "placeName",
    "NORP": "orgName",

    // Both:
    "PERSON": "persName",
    "DEFAULT": "name"
  }
}
```

### Annotation Strategy Selection

**Choose based on your use case:**

#### Use **inline** when:
- ✅ Reading TEI is important (human editors)
- ✅ Simple, linear text structure
- ✅ Few overlapping annotations
- ✅ Output will be displayed/printed
- ✅ Examples: articles, simple documents, poetry

```xml
<s>
  <persName>John</persName> visited
  <placeName>Paris</placeName> in
  <date>2024</date>.
</s>
```

#### Use **standoff** when:
- ✅ Complex overlapping annotations
- ✅ Multiple annotation layers
- ✅ Computational analysis focus
- ✅ Large-scale corpus
- ✅ Examples: linguistic corpora, historical manuscripts

```xml
<text>John visited Paris in 2024.</text>
<standOff>
  <annotation id="e1" type="persName" target="#char_0_4"/>
  <annotation id="e2" type="placeName" target="#char_13_18"/>
</standOff>
```

#### Use **mixed** when:
- ✅ Entities inline (readable)
- ✅ Relations standoff (complex)
- ✅ Balanced approach
- ✅ Examples: literary analysis, complex documents

```xml
<s>
  <persName xml:id="p1">John</persName> visited
  <placeName xml:id="l1">Paris</placeName>.
</s>
<standOff>
  <link type="visited" target="#p1 #l1"/>
</standOff>
```

### Optimization Tips

**1. Enable features based on need:**

Heavy processing (slow):
```json
{
  "include_pos": true,
  "include_lemma": true,
  "include_dependencies": true,
  "include_morph": true,
  "include_analysis": true
}
```

Lightweight (fast):
```json
{
  "include_pos": false,
  "include_lemma": false,
  "include_dependencies": false,
  "include_analysis": false
}
```

**2. Choose provider wisely:**

```python
# In your schema (hint for system):
{
  "domain": "medical",
  // Implicitly suggests Google for precision
}

# System selects optimal provider:
# ontology_manager.py:541-573
def select_optimal_provider(self, text, domain):
    if domain in ['legal', 'scientific', 'historical']:
        return 'google'  # Precision domains
    elif domain in ['linguistic', 'literary']:
        return 'spacy'   # Morphology domains
    ...
```

**3. Use appropriate text structure:**

For paragraphs:
```json
{"use_paragraphs": true}  // <p>...</p>
```

For sentences:
```json
{"use_paragraphs": false}  // <s>...</s>
```

---

## 8. Complete Examples

### Example 1: Medical Domain

**File:** `schemas/medical.json`
```json
{
  "domain": "medical",
  "title": "Medical & Clinical Text",
  "description": "TEI schema for medical records, clinical notes, and health research",

  "annotation_strategy": "inline",

  "include_pos": true,
  "include_lemma": true,
  "include_dependencies": true,
  "include_analysis": true,
  "use_paragraphs": true,

  "entity_mappings": {
    "PERSON": "persName",
    "PATIENT": "persName",
    "PHYSICIAN": "persName",
    "HOSPITAL": "orgName",
    "CLINIC": "orgName",
    "ORG": "orgName",

    "DISEASE": "term",
    "CONDITION": "term",
    "SYMPTOM": "term",
    "TREATMENT": "term",
    "MEDICATION": "term",
    "DRUG": "term",
    "PROCEDURE": "term",
    "THERAPY": "term",
    "ANATOMY": "term",
    "BODY_PART": "term",
    "GENE": "term",
    "PROTEIN": "term",
    "ENZYME": "term",

    "DOSAGE": "measure",
    "MEASUREMENT": "measure",
    "LAB_VALUE": "measure",
    "VITAL_SIGN": "measure",
    "BLOOD_PRESSURE": "measure",
    "MONEY": "measure",

    "DATE": "date",
    "TIME": "time",
    "DURATION": "time",
    "FREQUENCY": "time",

    "ICD_CODE": "ref",
    "CPT_CODE": "ref",
    "SNOMED_CODE": "ref",
    "LOINC_CODE": "ref",
    "MEDICAL_CODE": "ref",

    "DEFAULT": "term"
  },

  "additional_tags": [
    "term",
    "measure",
    "ref",
    "bibl",
    "citation",
    "formula",
    "table",
    "figure",
    "note",
    "abbr"
  ],

  "classification": true,
  "text_class": "medical",
  "include_references": true,
  "strict_structure": false
}
```

**Usage:**
```python
text = """
Patient: John Doe, 45-year-old male
Chief Complaint: Chest pain
Diagnosis: Acute myocardial infarction
Treatment: Administered aspirin 325mg, nitroglycerin 0.4mg sublingual
Lab Results: Troponin I elevated at 2.3 ng/mL
Plan: Admit to ICU, cardiology consult
"""

schema = ontology.get_schema('medical')
# Process with medical-specific entity recognition
```

### Example 2: Journalism Domain

**File:** `schemas/journalism.json`
```json
{
  "domain": "journalism",
  "title": "Journalism & News Articles",
  "description": "TEI schema for news articles, press releases, and journalism",

  "annotation_strategy": "inline",

  "include_pos": false,
  "include_lemma": false,
  "include_dependencies": false,
  "include_analysis": true,
  "use_paragraphs": true,

  "entity_mappings": {
    "PERSON": "persName",
    "JOURNALIST": "persName",
    "AUTHOR": "persName",
    "SOURCE": "persName",
    "OFFICIAL": "persName",

    "ORG": "orgName",
    "PUBLICATION": "orgName",
    "NEWS_OUTLET": "orgName",
    "AGENCY": "orgName",
    "GOVERNMENT": "orgName",
    "COMPANY": "orgName",

    "LOC": "placeName",
    "LOCATION": "placeName",
    "COUNTRY": "placeName",
    "CITY": "placeName",

    "DATE": "date",
    "TIME": "time",

    "EVENT": "event",
    "INCIDENT": "event",

    "QUOTE": "quote",
    "STATEMENT": "quote",

    "HEADLINE": "head",
    "TITLE": "title",

    "DEFAULT": "name"
  },

  "additional_tags": [
    "head",
    "byline",
    "dateline",
    "quote",
    "said",
    "ref",
    "bibl",
    "note"
  ],

  "classification": true,
  "text_class": "journalism",
  "include_metadata": true
}
```

**Usage:**
```python
text = """
Breaking: Tech Giant Announces Merger

By Jane Smith, Tech Reporter
San Francisco, November 2, 2024

Apple Inc. announced today a landmark $50 billion acquisition of
a leading AI startup. CEO Tim Cook stated, "This represents the
future of computing." The deal is expected to close in Q1 2025.
"""

schema = ontology.get_schema('journalism')
# Get TEI with journalistic structure (byline, dateline, quotes)
```

### Example 3: Social Media Domain

**File:** `schemas/social-media.json`
```json
{
  "domain": "social-media",
  "title": "Social Media Content",
  "description": "TEI schema for social media posts, comments, and online discourse",

  "annotation_strategy": "inline",

  "include_pos": false,
  "include_lemma": false,
  "include_dependencies": false,
  "include_analysis": true,
  "use_paragraphs": false,

  "entity_mappings": {
    "PERSON": "persName",
    "USERNAME": "persName",
    "MENTION": "persName",
    "INFLUENCER": "persName",

    "ORG": "orgName",
    "BRAND": "orgName",
    "PLATFORM": "orgName",

    "LOC": "placeName",
    "LOCATION": "placeName",

    "HASHTAG": "ref",
    "TAG": "ref",
    "URL": "ref",
    "LINK": "ref",

    "EMOJI": "note",
    "EMOTICON": "note",

    "DATE": "date",
    "TIME": "time",
    "TIMESTAMP": "time",

    "PRODUCT": "objectName",

    "DEFAULT": "name"
  },

  "additional_tags": [
    "ref",
    "note",
    "quote",
    "abbr",
    "emph"
  ],

  "classification": true,
  "text_class": "social-media",
  "strict_structure": false
}
```

**Usage:**
```python
text = """
@john_doe just tried the new #iPhone15 😍
Best camera ever! 📸 Check it out: https://apple.com
@Apple you nailed it! 🎉
"""

schema = ontology.get_schema('social-media')
# Process with social media-specific features (hashtags, mentions, emoji)
```

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────┐
│           CUSTOM SCHEMA QUICK GUIDE                 │
├─────────────────────────────────────────────────────┤
│ 1. Create JSON: schemas/mydomain.json              │
│ 2. Required fields: domain, title, annotation_str  │
│ 3. Add entity_mappings (always include DEFAULT)    │
│ 4. Choose strategy: inline/standoff/mixed          │
│ 5. Validate: python3 validate_schema.py file.json  │
│ 6. Restart app or reload OntologyManager           │
│ 7. Use in API: {"domain": "mydomain", ...}         │
└─────────────────────────────────────────────────────┘
```

## Additional Resources

- **TEI Guidelines:** https://tei-c.org/guidelines/
- **Code Reference:** `ontology_manager.py`, `tei_converter.py`
- **Default Schemas:** See `ontology_manager.py:90-330`
- **Provider Mappings:** See `ontology_manager.py:26-88`
- **Validation:** See `ontology_manager.py:438-456`

## Support

For questions or issues:
- Check logs: `logs/app.log`
- Validate schema: Run validation script above
- Test loading: Python REPL with OntologyManager
- Review examples: See complete examples in this guide

---

**Last Updated:** 2024-11-02
**Version:** 2.1.0

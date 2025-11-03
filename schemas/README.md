# Custom TEI Schemas Directory

This directory contains custom domain-specific schemas for TEI XML conversion.

## 📚 Available Schemas

### Built-in Schemas (in code)
- `default` - General text processing
- `literary` - Literary analysis
- `historical` - Historical documents
- `legal` - Legal texts and contracts
- `scientific` - Scientific papers
- `linguistic` - Linguistic corpus analysis
- `manuscript` - Manuscript transcription
- `dramatic` - Plays and dramatic texts
- `poetry` - Poetic texts
- `epistolary` - Letters and correspondence

### Custom Schemas (in this directory)
- `medical.json` - Medical and clinical texts
- `journalism.json` - News articles and journalism
- `social-media.json` - Social media content

## 🚀 Quick Start

### Using a Custom Schema

**Via Python API:**
```python
from ontology_manager import OntologyManager

ontology = OntologyManager()
schema = ontology.get_schema('medical')
```

**Via REST API:**
```bash
curl -X POST http://localhost:8080/convert \
  -d '{"text": "Patient has diabetes", "domain": "medical"}'
```

**Via Web UI:**
1. Open http://localhost:8080
2. Select "Medical" from domain dropdown
3. Enter text and click "Process"

## 📝 Creating Custom Schemas

### Step 1: Create JSON File
```bash
nano schemas/mydomain.json
```

### Step 2: Define Schema Structure
```json
{
  "domain": "mydomain",
  "title": "My Custom Domain",
  "description": "Schema for my specific use case",
  "annotation_strategy": "inline",
  "include_pos": true,
  "include_lemma": true,
  "include_dependencies": true,
  "entity_mappings": {
    "PERSON": "persName",
    "LOCATION": "placeName",
    "CUSTOM_TYPE": "term",
    "DEFAULT": "name"
  }
}
```

### Step 3: Validate Schema
```bash
python3 validate_schema.py schemas/mydomain.json
```

### Step 4: Use Immediately
No restart needed! The schema is loaded on first request.

## 📖 Documentation

For comprehensive documentation on creating custom schemas:
- **Full Guide**: [CUSTOM_SCHEMAS_GUIDE.md](../CUSTOM_SCHEMAS_GUIDE.md)
- **Validation Tool**: `validate_schema.py` in project root
- **Code Reference**: `ontology_manager.py`

## 🔧 Schema Format

### Required Fields
```json
{
  "domain": "string",              // Unique identifier
  "title": "string",               // Human-readable name
  "annotation_strategy": "string"  // "inline", "standoff", or "mixed"
}
```

### Optional Fields
- `description` - Schema description
- `include_pos` - Part-of-speech tags
- `include_lemma` - Lemmatization
- `include_dependencies` - Dependency parsing
- `include_analysis` - Analysis section
- `use_paragraphs` - Use `<p>` tags
- `entity_mappings` - Entity type → TEI element mappings
- `additional_tags` - Extra TEI elements

### Entity Mappings
Map NLP entity types to TEI elements:
```json
"entity_mappings": {
  "PERSON": "persName",     // <persName>John</persName>
  "LOCATION": "placeName",  // <placeName>Paris</placeName>
  "ORG": "orgName",         // <orgName>Google</orgName>
  "DATE": "date",           // <date>2024</date>
  "DRUG": "term",           // <term type="drug">aspirin</term>
  "DEFAULT": "name"         // Fallback for unknown types
}
```

## 🎯 Examples

### Medical Domain
```json
{
  "domain": "medical",
  "title": "Medical & Clinical Text",
  "entity_mappings": {
    "DISEASE": "term",
    "DRUG": "term",
    "DOSAGE": "measure",
    "ICD_CODE": "ref"
  }
}
```

### Journalism Domain
```json
{
  "domain": "journalism",
  "title": "News Articles",
  "entity_mappings": {
    "JOURNALIST": "persName",
    "PUBLICATION": "orgName",
    "QUOTE": "quote",
    "HEADLINE": "head"
  }
}
```

## 🔍 Provider-Specific Features

Custom schemas work with all NLP providers:
- **Google Cloud NLP** - Adds salience, sentiment, Knowledge Graph links
- **SpaCy** - Provides rich morphology and dependency parsing
- **Remote Server** - Generic NLP processing

Entity mappings merge with provider-specific mappings:
```json
{
  "entity_mappings": {
    "PRODUCT": "term"  // Overrides provider default
  }
}
```

## ✅ Validation

Validate schemas before deployment:
```bash
# Single schema
python3 validate_schema.py schemas/medical.json

# All schemas
python3 validate_schema.py schemas/*.json
```

## 🔄 Management

### Export All Schemas
```python
from ontology_manager import OntologyManager
ontology = OntologyManager()
ontology.export_all_schemas('backup/schemas')
```

### List Available Domains
```python
domains = ontology.get_available_domains()
print(domains)
# ['default', 'literary', 'medical', 'journalism', ...]
```

### Get Schema Info
```python
info = ontology.get_schema_info('medical')
print(info)
# {
#   'domain': 'medical',
#   'title': 'Medical & Clinical Text',
#   'entity_types': ['DISEASE', 'DRUG', ...],
#   'is_custom': True
# }
```

## 🎨 Best Practices

1. **Naming**: Use lowercase with hyphens: `social-media`, `legal-contracts`
2. **DEFAULT Mapping**: Always include `"DEFAULT": "name"` in entity_mappings
3. **Validation**: Run validation before deploying to production
4. **Documentation**: Add description field for clarity
5. **Annotation Strategy**:
   - Use `inline` for readable TEI (articles, documents)
   - Use `standoff` for complex annotations (linguistics, manuscripts)
   - Use `mixed` for balanced approach

## 🆘 Support

- Check validation errors: `python3 validate_schema.py <file>`
- View logs: `logs/app.log`
- Full documentation: `CUSTOM_SCHEMAS_GUIDE.md`
- Code: `ontology_manager.py`

---

**Last Updated**: 2024-11-02
**Version**: 2.1.0

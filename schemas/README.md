# TEI Schema Configuration

## Overview

This directory contains JSON schema files that define domain-specific TEI (Text Encoding Initiative) conversion rules. Each schema maps NLP entity types to TEI XML elements and configures annotation strategies.

## Schema Files

| File | Domain | Description |
|------|--------|-------------|
| `literary.json` | Literary Analysis | Character names, quotes, dialogues, works of art |
| `historical.json` | Historical Documents | Events, dates, places, historical figures |
| `legal.json` | Legal Documents | Statutes, case citations, court names, laws |
| `scientific.json` | Scientific Papers | Chemicals, formulas, measurements |
| `linguistic.json` | Linguistic Analysis | Detailed token analysis, morphology |

## Schema Structure

```json
{
  "domain": "domain_name",
  "entity_mappings": {
    "NLP_ENTITY_TYPE": "tei_element_name"
  },
  "annotation_strategy": "inline|standoff|mixed",
  "include_pos": true,
  "include_lemma": true,
  "include_dependencies": false,
  "custom_rules": {}
}
```

## Entity Mappings

### Standard NLP to TEI Mappings

```json
{
  "PERSON": "persName",
  "LOC": "placeName",
  "GPE": "placeName",
  "ORG": "orgName",
  "DATE": "date",
  "TIME": "time",
  "MONEY": "measure",
  "PERCENT": "measure",
  "WORK_OF_ART": "title",
  "LAW": "name",
  "EVENT": "event"
}
```

### Domain-Specific Mappings

With the new domain-specific NLP architecture, schemas now support specialized entity types:

**Medical Domain**:
```json
{
  "DRUG": "term",
  "DISEASE": "term",
  "CHEMICAL": "term",
  "PROCEDURE": "term",
  "ANATOMY": "term",
  "ICD10_CODE": "idno",
  "CPT_CODE": "idno",
  "DOSAGE": "measure"
}
```

**Legal Domain**:
```json
{
  "STATUTE": "name",
  "CASE_CITATION": "bibl",
  "COURT": "orgName",
  "USC_CITATION": "ref",
  "CFR_CITATION": "ref",
  "PUBLIC_LAW": "name"
}
```

**Financial Domain**:
```json
{
  "TICKER_SYMBOL": "name",
  "CURRENCY_AMOUNT": "measure",
  "CUSIP": "idno",
  "ISIN": "idno",
  "FISCAL_PERIOD": "date"
}
```

## Creating Custom Schemas

### Step 1: Create JSON File

```json
{
  "domain": "medical",
  "entity_mappings": {
    "PERSON": "persName",
    "DRUG": "term",
    "DISEASE": "term",
    "ICD10_CODE": "idno",
    "DOSAGE": "measure"
  },
  "annotation_strategy": "inline",
  "include_pos": false,
  "include_lemma": false,
  "include_dependencies": false,
  "custom_rules": {
    "term_attributes": {
      "type": "medical"
    },
    "idno_attributes": {
      "type": "code"
    }
  }
}
```

### Step 2: Register with Ontology Manager

The schema is automatically discovered when placed in this directory. The `OntologyManager` loads schemas dynamically:

```python
from ontology_manager import OntologyManager

manager = OntologyManager()
schema = manager.get_schema("medical")
```

### Step 3: Use in TEI Conversion

```python
from tei_converter import TEIConverter

converter = TEIConverter(schema="medical")
tei_xml = converter.convert(text, nlp_results)
```

## Integration with Domain-Specific NLP

The new domain-specific NLP module (`domain_nlp/`) produces enriched entity types that schemas must handle:

### Pattern-Matched Entities

Entities from pattern matching include additional metadata:

```json
{
  "text": "E11.9",
  "type": "ICD10_CODE",
  "metadata": {
    "source": "pattern_matching",
    "pattern_name": "icd10_code",
    "validation_passed": true
  }
}
```

Schema mapping for pattern entities:
```json
{
  "ICD10_CODE": "idno",
  "USC_CITATION": "ref",
  "CASE_CITATION": "bibl"
}
```

### KB-Enriched Entities

Entities enriched from knowledge bases include definitions:

```json
{
  "text": "Metformin",
  "type": "DRUG",
  "kb_enrichment": {
    "kb_id": "rxnorm",
    "entity_id": "6809",
    "definition": "Biguanide antihyperglycemic agent",
    "synonyms": ["Glucophage", "Fortamet"]
  }
}
```

To include KB data in TEI:
```json
{
  "custom_rules": {
    "include_kb_attributes": true,
    "kb_ref_attribute": "ref",
    "kb_definition_element": "gloss"
  }
}
```

Generated TEI:
```xml
<term type="drug" ref="rxnorm:6809">Metformin</term>
<gloss target="#metformin">Biguanide antihyperglycemic agent</gloss>
```

## Annotation Strategies

### Inline
Entities marked directly in text flow:
```xml
<s><persName>John</persName> has <term type="disease">diabetes</term>.</s>
```

### Standoff
Annotations separate from text:
```xml
<text>
  <body><p id="p1">John has diabetes.</p></body>
</text>
<standOff>
  <annotation target="#char_0_4" type="person">John</annotation>
  <annotation target="#char_9_17" type="disease">diabetes</annotation>
</standOff>
```

### Mixed
Combination of inline and standoff for different entity types.

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `domain` | string | required | Domain identifier |
| `entity_mappings` | object | required | NLP type to TEI element mapping |
| `annotation_strategy` | string | "inline" | inline, standoff, or mixed |
| `include_pos` | boolean | false | Include POS tags on tokens |
| `include_lemma` | boolean | false | Include lemmatized forms |
| `include_dependencies` | boolean | false | Include dependency relations |
| `custom_rules` | object | {} | Domain-specific processing rules |

## Best Practices

1. **Match NLP Provider Output**: Ensure mappings cover all entity types from your NLP provider
2. **Handle Unknown Types**: Include a DEFAULT mapping for unrecognized entities
3. **Validate TEI Output**: Generated XML should conform to TEI P5 Guidelines
4. **Document Custom Rules**: Add comments explaining domain-specific customizations
5. **Test with Sample Data**: Verify mappings work with representative domain text

## Migration from Google Cloud NLP

If migrating from Google Cloud NLP schemas, update entity mappings:

**Old (Google Cloud NLP)**:
```json
{
  "ORGANIZATION": "orgName",
  "LOCATION": "placeName",
  "OTHER": "name"
}
```

**New (Domain-Specific NLP)**:
```json
{
  "ORG": "orgName",
  "LOC": "placeName",
  "GPE": "placeName",
  "DRUG": "term",
  "DISEASE": "term",
  "ICD10_CODE": "idno"
}
```

See `MIGRATION_GUIDE.md` for complete migration instructions.

## References

- [TEI P5 Guidelines](https://tei-c.org/guidelines/p5/)
- [TEI Named Entities](https://www.tei-c.org/release/doc/tei-p5-doc/en/html/ND.html)
- [Domain-Specific NLP Architecture](../ARCHITECTURE.md)
- [Domain NLP Module Documentation](../domain_nlp/README.md)

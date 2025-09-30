"""
Test suite for TEI conversion
"""
import pytest
from tei_converter import TEIConverter
from defusedxml import ElementTree as ET
import json

def get_sample_nlp_results():
    """Get sample NLP results for testing"""
    return {
        "sentences": [
            {
                "text": "John visited Paris.",
                "start": 0,
                "end": 3,
                "tokens": [
                    {
                        "text": "John",
                        "lemma": "John",
                        "pos": "PROPN",
                        "tag": "NNP",
                        "dep": "nsubj",
                        "head": 1,
                        "idx": 0,
                        "i": 0,
                        "is_punct": False,
                        "is_space": False,
                        "shape": "Xxxx",
                        "is_alpha": True,
                        "is_stop": False
                    },
                    {
                        "text": "visited",
                        "lemma": "visit",
                        "pos": "VERB",
                        "tag": "VBD",
                        "dep": "ROOT",
                        "head": 1,
                        "idx": 5,
                        "i": 1,
                        "is_punct": False,
                        "is_space": False,
                        "shape": "xxxx",
                        "is_alpha": True,
                        "is_stop": False
                    },
                    {
                        "text": "Paris",
                        "lemma": "Paris",
                        "pos": "PROPN",
                        "tag": "NNP",
                        "dep": "dobj",
                        "head": 1,
                        "idx": 13,
                        "i": 2,
                        "is_punct": False,
                        "is_space": False,
                        "shape": "Xxxx",
                        "is_alpha": True,
                        "is_stop": False
                    }
                ]
            }
        ],
        "entities": [
            {
                "text": "John",
                "label": "PERSON",
                "start": 0,
                "end": 1,
                "start_char": 0,
                "end_char": 4
            },
            {
                "text": "Paris",
                "label": "GPE",
                "start": 2,
                "end": 3,
                "start_char": 13,
                "end_char": 18
            }
        ],
        "noun_chunks": [],
        "dependencies": [
            {
                "from": 1,
                "to": 0,
                "dep": "nsubj",
                "from_text": "visited",
                "to_text": "John"
            },
            {
                "from": 1,
                "to": 2,
                "dep": "dobj",
                "from_text": "visited",
                "to_text": "Paris"
            }
        ],
        "text": "John visited Paris.",
        "language": "en"
    }

def test_tei_conversion_basic():
    """Test basic TEI conversion"""
    schema = {
        "domain": "default",
        "title": "Test Document",
        "annotation_strategy": "inline"
    }
    
    converter = TEIConverter(schema)
    nlp_results = get_sample_nlp_results()
    
    tei_xml = converter.convert("John visited Paris.", nlp_results)
    
    assert tei_xml is not None
    assert "<?xml" in tei_xml
    assert "TEI" in tei_xml
    assert "teiHeader" in tei_xml
    assert "text" in tei_xml

def test_inline_annotations():
    """Test inline annotation strategy"""
    schema = {
        "domain": "default",
        "title": "Test Inline",
        "annotation_strategy": "inline",
        "include_pos": True,
        "include_lemma": True
    }
    
    converter = TEIConverter(schema)
    nlp_results = get_sample_nlp_results()
    
    tei_xml = converter.convert("John visited Paris.", nlp_results)
    
    # Parse XML to check structure
    root = ET.fromstring(tei_xml.encode('utf-8'))
    
    # Check for word elements with attributes
    words = root.findall(".//{http://www.tei-c.org/ns/1.0}w")
    assert len(words) > 0
    
    # Check for entity elements
    persNames = root.findall(".//{http://www.tei-c.org/ns/1.0}persName")
    assert len(persNames) >= 1  # John
    
    placeNames = root.findall(".//{http://www.tei-c.org/ns/1.0}placeName")
    assert len(placeNames) >= 1  # Paris

def test_standoff_annotations():
    """Test standoff annotation strategy"""
    schema = {
        "domain": "default",
        "title": "Test Standoff",
        "annotation_strategy": "standoff"
    }
    
    converter = TEIConverter(schema)
    nlp_results = get_sample_nlp_results()
    
    tei_xml = converter.convert("John visited Paris.", nlp_results)
    
    # Check for standOff section
    assert "standOff" in tei_xml
    assert "listAnnotation" in tei_xml
    assert "annotation" in tei_xml

def test_domain_specific_schema():
    """Test domain-specific schema application"""
    schema = {
        "domain": "legal",
        "title": "Legal Document",
        "annotation_strategy": "standoff",
        "entity_mappings": {
            "PERSON": "persName",
            "ORG": "orgName",
            "LAW": "name"
        }
    }
    
    converter = TEIConverter(schema)
    nlp_results = get_sample_nlp_results()
    
    tei_xml = converter.convert("Test text", nlp_results)
    
    assert "domain: legal" in tei_xml

def test_xml_validity():
    """Test that generated XML is valid"""
    schema = {"domain": "default", "title": "Test"}
    converter = TEIConverter(schema)
    nlp_results = get_sample_nlp_results()
    
    tei_xml = converter.convert("John visited Paris.", nlp_results)
    
    # Should parse without errors
    try:
        root = ET.fromstring(tei_xml.encode('utf-8'))
        assert root is not None
    except ET.ParseError:
        pytest.fail("Generated XML is not valid")

def test_header_metadata():
    """Test TEI header metadata"""
    schema = {
        "domain": "literary",
        "title": "Literary Analysis",
        "author": "Test Author",
        "classification": True
    }
    
    converter = TEIConverter(schema)
    nlp_results = get_sample_nlp_results()
    
    tei_xml = converter.convert("Test text", nlp_results)
    
    assert "Literary Analysis" in tei_xml
    assert "Test Author" in tei_xml
    assert "fileDesc" in tei_xml
    assert "encodingDesc" in tei_xml
    assert "profileDesc" in tei_xml

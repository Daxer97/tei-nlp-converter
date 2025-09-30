"""
Test suite for NLP processing
"""
import pytest
from nlp_connector import NLPProcessor
from cache_manager import CacheManager

def test_nlp_initialization():
    """Test NLP processor initialization"""
    processor = NLPProcessor()
    assert processor.nlp is not None
    assert processor.model_name == "en_core_web_sm"

def test_text_processing():
    """Test basic text processing"""
    processor = NLPProcessor()
    text = "John Smith visited Paris last summer."
    result = processor.process(text)
    
    assert "sentences" in result
    assert "entities" in result
    assert "dependencies" in result
    assert len(result["sentences"]) > 0
    assert len(result["entities"]) > 0

def test_entity_extraction():
    """Test entity extraction"""
    processor = NLPProcessor()
    text = "Apple Inc. was founded by Steve Jobs in California."
    result = processor.process(text)
    
    entities = result["entities"]
    entity_types = [e["label"] for e in entities]
    
    assert "ORG" in entity_types  # Apple Inc.
    assert "PERSON" in entity_types  # Steve Jobs
    assert "GPE" in entity_types  # California

def test_sentence_tokenization():
    """Test sentence tokenization"""
    processor = NLPProcessor()
    text = "First sentence. Second sentence! Third sentence?"
    result = processor.process(text)
    
    assert len(result["sentences"]) == 3
    
    for sentence in result["sentences"]:
        assert "tokens" in sentence
        assert len(sentence["tokens"]) > 0

def test_caching():
    """Test NLP result caching"""
    cache_manager = CacheManager()
    processor = NLPProcessor(cache_manager=cache_manager)
    
    text = "Test caching functionality."
    
    # First call - should process
    result1 = processor.process(text)
    
    # Second call - should return cached
    result2 = processor.process(text)
    
    assert result1 == result2

def test_custom_options():
    """Test processing with custom options"""
    processor = NLPProcessor()
    text = "Testing custom options."
    
    options = {
        "include_dependencies": False,
        "include_noun_chunks": False
    }
    
    result = processor.process(text, options)
    assert result["dependencies"] == []
    assert result["noun_chunks"] == []

def test_batch_processing():
    """Test batch processing multiple texts"""
    processor = NLPProcessor()
    texts = [
        "First text.",
        "Second text.",
        "Third text."
    ]
    
    results = processor.batch_process(texts, batch_size=2)
    assert len(results) == 3
    
    for result in results:
        assert "sentences" in result
        assert "entities" in result

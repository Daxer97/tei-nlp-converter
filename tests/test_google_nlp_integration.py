"""
Comprehensive tests for Google Cloud NLP integration

Tests cover:
- Google-specific entity types
- Sentiment analysis integration
- Knowledge Graph metadata extraction
- Provider fallback to SpaCy when Google quota exceeded
- Provider-specific TEI conversion
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from nlp_providers.google_cloud import GoogleCloudNLPProvider
from nlp_providers.base import ProcessingOptions, ProviderStatus, ProviderCapabilities
from nlp_connector import NLPProcessor
from tei_converter import TEIConverter
from ontology_manager import OntologyManager


@pytest.fixture
def google_provider_config():
    """Mock Google Cloud provider configuration"""
    return {
        'project_id': 'test-project',
        'credentials_path': '/path/to/test-credentials.json',
    }


@pytest.fixture
def mock_google_client():
    """Create a mock Google Cloud NLP client"""
    client = Mock()

    # Mock entity response with Google-specific features
    mock_entity_response = Mock()
    mock_entity = Mock()
    mock_entity.type_.name = 'PERSON'
    mock_entity.salience = 0.8
    mock_entity.metadata = {'wikipedia_url': 'https://en.wikipedia.org/wiki/John_Doe'}

    mock_mention = Mock()
    mock_mention.text.content = 'John Doe'
    mock_mention.text.begin_offset = 0
    mock_mention.type_.name = 'PROPER'

    # Add sentiment to mention
    mock_sentiment = Mock()
    mock_sentiment.score = 0.5
    mock_sentiment.magnitude = 0.9
    mock_mention.sentiment = mock_sentiment

    mock_entity.mentions = [mock_mention]
    mock_entity_response.entities = [mock_entity]

    client.analyze_entity_sentiment.return_value = mock_entity_response
    client.analyze_entities.return_value = mock_entity_response

    # Mock syntax response
    mock_syntax_response = Mock()
    mock_token = Mock()
    mock_token.text.content = 'John'
    mock_token.text.begin_offset = 0
    mock_token.part_of_speech.tag.name = 'NOUN'
    mock_token.lemma = 'John'
    mock_token.dependency_edge.label.name = 'nsubj'
    mock_token.dependency_edge.head_token_index = 1

    mock_sentence = Mock()
    mock_sentence.text.content = 'John Doe is here.'
    mock_sentence.text.begin_offset = 0

    mock_syntax_response.tokens = [mock_token]
    mock_syntax_response.sentences = [mock_sentence]
    mock_syntax_response.language = 'en'

    client.analyze_syntax.return_value = mock_syntax_response

    return client


class TestGoogleCloudNLPProvider:
    """Test Google Cloud NLP provider functionality"""

    @pytest.mark.asyncio
    async def test_google_capabilities(self, google_provider_config):
        """Test that Google provider reports correct capabilities"""
        provider = GoogleCloudNLPProvider(google_provider_config)
        capabilities = provider.get_capabilities()

        assert capabilities.entities is True
        assert capabilities.sentiment is True
        assert capabilities.entity_sentiment is True
        assert capabilities.syntax_analysis is True
        assert capabilities.language_detection is True
        assert capabilities.noun_chunks is False  # Google doesn't provide noun chunks

    @pytest.mark.asyncio
    async def test_entity_salience_extraction(self, google_provider_config, mock_google_client):
        """Test extraction of entity salience scores (Google-specific)"""
        with patch('nlp_providers.google_cloud.language_v1.LanguageServiceClient',
                   return_value=mock_google_client):
            provider = GoogleCloudNLPProvider(google_provider_config)
            provider.client = mock_google_client

            options = ProcessingOptions(include_entities=True)
            result = await provider.process("John Doe is here.", options)

            # Check that salience is captured
            assert len(result['entities']) > 0
            entity = result['entities'][0]
            assert 'salience' in entity
            assert entity['salience'] == 0.8

    @pytest.mark.asyncio
    async def test_entity_sentiment_extraction(self, google_provider_config, mock_google_client):
        """Test extraction of entity sentiment (Google-specific)"""
        with patch('nlp_providers.google_cloud.language_v1.LanguageServiceClient',
                   return_value=mock_google_client):
            provider = GoogleCloudNLPProvider(google_provider_config)
            provider.client = mock_google_client

            options = ProcessingOptions(include_entities=True)
            result = await provider.process("John Doe is here.", options)

            # Check that entity sentiment is captured
            entity = result['entities'][0]
            assert 'sentiment' in entity
            assert 'score' in entity['sentiment']
            assert 'magnitude' in entity['sentiment']
            assert entity['sentiment']['score'] == 0.5
            assert entity['sentiment']['magnitude'] == 0.9

    @pytest.mark.asyncio
    async def test_knowledge_graph_metadata(self, google_provider_config, mock_google_client):
        """Test extraction of Knowledge Graph metadata (Google-specific)"""
        with patch('nlp_providers.google_cloud.language_v1.LanguageServiceClient',
                   return_value=mock_google_client):
            provider = GoogleCloudNLPProvider(google_provider_config)
            provider.client = mock_google_client

            options = ProcessingOptions(include_entities=True)
            result = await provider.process("John Doe is here.", options)

            # Check that Knowledge Graph metadata is captured
            entity = result['entities'][0]
            assert 'metadata' in entity
            assert 'wikipedia_url' in entity['metadata']
            assert entity['metadata']['wikipedia_url'] == 'https://en.wikipedia.org/wiki/John_Doe'

    @pytest.mark.asyncio
    async def test_entity_sorting_by_salience(self, google_provider_config, mock_google_client):
        """Test that entities are sorted by salience (Google-specific)"""
        # Create mock with multiple entities
        mock_entity_response = Mock()

        entity1 = Mock()
        entity1.type_.name = 'PERSON'
        entity1.salience = 0.3
        entity1.metadata = {}
        mention1 = Mock()
        mention1.text.content = 'Alice'
        mention1.text.begin_offset = 0
        mention1.type_.name = 'PROPER'
        entity1.mentions = [mention1]

        entity2 = Mock()
        entity2.type_.name = 'PERSON'
        entity2.salience = 0.7
        entity2.metadata = {}
        mention2 = Mock()
        mention2.text.content = 'Bob'
        mention2.text.begin_offset = 10
        mention2.type_.name = 'PROPER'
        entity2.mentions = [mention2]

        mock_entity_response.entities = [entity1, entity2]
        mock_google_client.analyze_entity_sentiment.return_value = mock_entity_response

        with patch('nlp_providers.google_cloud.language_v1.LanguageServiceClient',
                   return_value=mock_google_client):
            provider = GoogleCloudNLPProvider(google_provider_config)
            provider.client = mock_google_client

            options = ProcessingOptions(include_entities=True)
            result = await provider.process("Alice and Bob", options)

            # Entities should be sorted by salience (high to low)
            assert result['entities'][0]['text'] == 'Bob'  # Higher salience (0.7)
            assert result['entities'][1]['text'] == 'Alice'  # Lower salience (0.3)


class TestProviderAwareTEIConversion:
    """Test provider-aware TEI conversion"""

    def test_google_specific_tei_attributes(self):
        """Test that Google-specific features are included in TEI output"""
        ontology_manager = OntologyManager()
        schema = ontology_manager.get_schema('default')

        converter = TEIConverter(
            schema=schema,
            provider_name='google',
            ontology_manager=ontology_manager
        )

        # Mock NLP results with Google-specific features
        nlp_results = {
            'text': 'John Doe is here.',
            'language': 'en',
            'sentences': [{
                'text': 'John Doe is here.',
                'tokens': [
                    {'text': 'John', 'i': 0, 'idx': 0, 'lemma': 'John', 'pos': 'PROPN',
                     'dep': 'nsubj', 'is_punct': False, 'is_space': False, 'is_alpha': True},
                    {'text': 'Doe', 'i': 1, 'idx': 5, 'lemma': 'Doe', 'pos': 'PROPN',
                     'dep': 'flat', 'is_punct': False, 'is_space': False, 'is_alpha': True},
                ]
            }],
            'entities': [{
                'text': 'John Doe',
                'label': 'PERSON',
                'start': 0,
                'end': 2,
                'start_char': 0,
                'end_char': 8,
                'salience': 0.8,
                'sentiment': {'score': 0.5, 'magnitude': 0.9},
                'metadata': {'wikipedia_url': 'https://en.wikipedia.org/wiki/John_Doe'},
                'provider': 'google'
            }],
            'dependencies': [],
            'noun_chunks': []
        }

        tei_xml = converter.convert('John Doe is here.', nlp_results)

        # Check that Google-specific attributes are present
        assert 'salience' in tei_xml
        assert 'sentiment' in tei_xml
        assert 'wikipedia.org' in tei_xml

    def test_provider_specific_entity_mappings(self):
        """Test that provider-specific entity mappings are used"""
        ontology_manager = OntologyManager()

        # Get Google-specific mappings
        google_mappings = ontology_manager.get_provider_entity_mappings('google')

        # Google-specific entities should be mapped
        assert google_mappings.get('PHONE_NUMBER') == 'num'
        assert google_mappings.get('ADDRESS') == 'address'
        assert google_mappings.get('CONSUMER_GOOD') == 'objectName'


class TestProviderFallback:
    """Test fallback mechanism when Google quota is exceeded"""

    @pytest.mark.asyncio
    async def test_fallback_on_quota_exceeded(self):
        """Test that system falls back to SpaCy when Google quota exceeded"""
        from google.api_core.exceptions import ResourceExhausted

        # Create processor with Google primary and SpaCy fallback
        processor = NLPProcessor(
            primary_provider='google',
            fallback_providers=['spacy']
        )

        # Mock Google provider to raise quota error
        mock_google = AsyncMock()
        mock_google.health_check.return_value = ProviderStatus.AVAILABLE
        mock_google.process.side_effect = RuntimeError("API quota exceeded")
        mock_google.get_name.return_value = "Google Cloud NLP"

        # Mock SpaCy provider to succeed
        mock_spacy = AsyncMock()
        mock_spacy.health_check.return_value = ProviderStatus.AVAILABLE
        mock_spacy.get_name.return_value = "SpaCy Local"
        mock_spacy.process.return_value = {
            'text': 'Test text',
            'sentences': [{'text': 'Test text', 'tokens': []}],
            'entities': [],
            'dependencies': [],
            'noun_chunks': []
        }

        # Replace registry instances
        processor.registry._instances = {
            'google': mock_google,
            'spacy': mock_spacy
        }

        result = await processor.process("Test text")

        # Should successfully process with fallback
        assert result is not None
        assert result['_metadata']['provider'] == 'SpaCy Local'
        assert result['_metadata']['fallback_used'] is True


class TestProviderSelection:
    """Test optimal provider selection logic"""

    def test_select_google_for_legal_domain(self):
        """Test that Google is selected for legal domain"""
        ontology_manager = OntologyManager()

        # Legal domain should prefer Google for precision
        provider = ontology_manager.select_optimal_provider(
            text="This is a legal contract.",
            domain='legal'
        )

        assert provider == 'google'

    def test_select_spacy_for_long_texts(self):
        """Test that SpaCy is selected for very long texts"""
        ontology_manager = OntologyManager()

        # Very long text should use local processing (SpaCy)
        long_text = "word " * 50000  # > 100,000 characters
        provider = ontology_manager.select_optimal_provider(
            text=long_text,
            domain='default'
        )

        assert provider == 'spacy'

    def test_select_spacy_for_linguistic_domain(self):
        """Test that SpaCy is selected for linguistic analysis"""
        ontology_manager = OntologyManager()

        provider = ontology_manager.select_optimal_provider(
            text="Linguistic analysis text.",
            domain='linguistic'
        )

        assert provider == 'spacy'


class TestGranularityAwareProcessing:
    """Test that processing options are adjusted based on provider"""

    @pytest.mark.asyncio
    async def test_google_enables_sentiment(self):
        """Test that sentiment is automatically enabled for Google"""
        processor = NLPProcessor(primary_provider='google')

        # Create a mock Google provider
        mock_provider = Mock()
        mock_provider.get_capabilities.return_value = ProviderCapabilities(
            sentiment=True,
            entity_sentiment=True,
            noun_chunks=False
        )

        processor.registry._instances['google'] = mock_provider

        # Process with default options (sentiment not explicitly enabled)
        options = processor._parse_options({})

        # Sentiment should be automatically enabled for Google
        assert options.include_sentiment is True
        # Noun chunks should be disabled (Google doesn't support them)
        assert options.include_noun_chunks is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

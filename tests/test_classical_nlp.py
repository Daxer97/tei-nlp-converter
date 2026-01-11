"""
Tests for Classical NLP Module

Tests the language detection, NLP processing, TEI generation,
and occurrence search functionality with Latin and Greek texts.

Includes excerpts from Virgil's Georgics for botanical term testing.
"""

import pytest
import asyncio
from typing import Dict, Any

# Import classical NLP components
from classical_nlp.language_detector import (
    ClassicalLanguageDetector,
    ClassicalLanguage,
    detect_classical_language
)
from classical_nlp.models import (
    LatinCyProvider,
    CLTKLatinProvider,
    CLTKGreekProvider,
    get_provider_for_language,
    get_available_models
)
from classical_nlp.tei import (
    LatinTEIGenerator,
    GreekTEIGenerator,
    create_tei_generator
)
from classical_nlp.search import (
    OccurrenceSearcher,
    SearchConfig,
    SearchMode,
    SearchResult
)
from classical_nlp.export import HTMLReportGenerator


# Test data: Virgil's Georgics excerpts (Book I and II)
GEORGICS_BOOK_1 = """
Quid faciat laetas segetes, quo sidere terram
vertere, Maecenas, ulmisque adiungere vitis
conveniat, quae cura boum, qui cultus habendo
sit pecori, apibus quanta experientia parcis,
hinc canere incipiam.
"""

GEORGICS_BOOK_2 = """
Hactenus arvorum cultus et sidera caeli;
nunc te, Bacche, canam, nec non silvestria tecum
virgulta et prolem tarde crescentis olivae.
Huc, pater o Lenaee: tuis hic omnia plena
muneribus, tibi pampineo gravidus autumno
floret ager, spumat plenis vindemia labris;
huc, pater o Lenaee, veni, nudataque musto
tinge novo mecum dereptis crura cothurnis.
"""

GEORGICS_BOTANICAL = """
Prima Ceres ferro mortalis vertere terram
instituit, cum iam glandes atque arbuta sacrae
deficerent silvae et victum Dodona negaret.
Mox et frumentis labor additus, ut mala culmos
esset robigo segnisque horreret in arvis
carduus; intereunt segetes, subit aspera silva,
lappaeque tribolique, interque nitentia culta
infelix lolium et steriles dominantur avenae.
"""

# Greek test data (Hesiod's Works and Days excerpt)
HESIOD_GREEK = """
Μοῦσαι Πιερίηθεν, ἀοιδῇσι κλείουσαι,
δεῦτε, Δί' ἐννέπετε, σφέτερον πατέρ' ὑμνείουσαι.
"""

# Homer's Odyssey excerpt about plants
ODYSSEY_PLANTS = """
ἐν δ' αὐτῇ κρατὴρ χρύσειος, ἐν δὲ τράπεζα
ἀργυρέη· κειμήλια δ' αὐτόθι κεῖτο ἄλεκτα.
"""


class TestLanguageDetector:
    """Test the classical language detector."""

    def test_detect_latin(self):
        """Test detection of Latin text."""
        detector = ClassicalLanguageDetector()
        result = detector.detect(GEORGICS_BOOK_1)

        assert result.language == ClassicalLanguage.LATIN
        assert result.confidence > 0.5
        assert result.latin_char_ratio > 0.8

    def test_detect_greek(self):
        """Test detection of Greek text."""
        detector = ClassicalLanguageDetector()
        result = detector.detect(HESIOD_GREEK)

        assert result.language == ClassicalLanguage.ANCIENT_GREEK
        assert result.confidence > 0.5
        assert result.greek_char_ratio > 0.5

    def test_simple_function(self):
        """Test the simple detect function."""
        assert detect_classical_language(GEORGICS_BOOK_1) == "latin"
        assert detect_classical_language(HESIOD_GREEK) == "ancient_greek"

    def test_empty_text(self):
        """Test detection with empty text."""
        detector = ClassicalLanguageDetector()
        result = detector.detect("")

        assert result.language == ClassicalLanguage.UNKNOWN
        assert result.confidence == 0.0

    def test_mixed_text(self):
        """Test detection with very short text."""
        detector = ClassicalLanguageDetector()
        result = detector.detect("et")

        # Short text should still attempt detection
        assert result.language in [ClassicalLanguage.LATIN, ClassicalLanguage.UNKNOWN]


class TestLatinProviders:
    """Test Latin NLP providers."""

    @pytest.fixture
    def latin_text(self):
        return GEORGICS_BOOK_1.strip()

    @pytest.mark.asyncio
    async def test_cltk_latin_provider(self, latin_text):
        """Test CLTK Latin provider."""
        provider = CLTKLatinProvider()
        await provider.initialize()

        result = await provider.process(latin_text)

        assert result.language == "latin"
        assert len(result.tokens) > 0
        assert len(result.sentences) > 0

    @pytest.mark.asyncio
    async def test_botanical_detection(self):
        """Test botanical term detection in Georgics."""
        provider = CLTKLatinProvider()
        await provider.initialize()

        result = await provider.process(GEORGICS_BOTANICAL)

        # Should detect botanical terms
        assert len(result.botanical_terms) > 0

        # Check for expected botanical terms
        lemmas = [bt.lemma.lower() for bt in result.botanical_terms]
        # Should find terms like silva, avena, frumentum, etc.
        assert any(term in lemmas for term in ['silva', 'avena', 'arbuta'])

    @pytest.mark.asyncio
    async def test_provider_capabilities(self):
        """Test provider capabilities reporting."""
        provider = CLTKLatinProvider()
        caps = provider.get_capabilities()

        assert caps['lemmatization'] == True
        assert caps['botanical_detection'] == True


class TestGreekProvider:
    """Test Ancient Greek NLP provider."""

    @pytest.mark.asyncio
    async def test_cltk_greek_provider(self):
        """Test CLTK Greek provider."""
        provider = CLTKGreekProvider()
        await provider.initialize()

        result = await provider.process(HESIOD_GREEK)

        assert result.language == "ancient_greek"
        assert len(result.tokens) > 0


class TestTEIGeneration:
    """Test TEI XML generation."""

    @pytest.fixture
    def sample_nlp_result(self) -> Dict[str, Any]:
        """Create sample NLP result for testing."""
        return {
            'text': GEORGICS_BOOK_1.strip(),
            'language': 'latin',
            'model_used': 'CLTK Latin (test)',
            'sentences': [
                {
                    'text': 'Quid faciat laetas segetes, quo sidere terram vertere.',
                    'tokens': [
                        {'text': 'Quid', 'lemma': 'quis', 'pos': 'PRON', 'morph': '', 'i': 0, 'is_punct': False, 'whitespace_': ' '},
                        {'text': 'faciat', 'lemma': 'facio', 'pos': 'VERB', 'morph': '', 'i': 1, 'is_punct': False, 'whitespace_': ' '},
                        {'text': 'laetas', 'lemma': 'laetus', 'pos': 'ADJ', 'morph': '', 'i': 2, 'is_punct': False, 'whitespace_': ' '},
                        {'text': 'segetes', 'lemma': 'seges', 'pos': 'NOUN', 'morph': '', 'i': 3, 'is_punct': False, 'whitespace_': ' '},
                        {'text': '.', 'lemma': '.', 'pos': 'PUNCT', 'morph': '', 'i': 4, 'is_punct': True, 'whitespace_': ''},
                    ]
                }
            ],
            'entities': [],
            'tokens': [],
            'dependencies': [],
            'noun_chunks': [],
            'botanical_terms': [
                {
                    'text': 'segetes',
                    'lemma': 'seges',
                    'scientific_name': None,
                    'common_name': 'messe',
                    'occurrences': 1,
                    'positions': ['char:30']
                }
            ],
            'metadata': {}
        }

    def test_latin_tei_generator(self, sample_nlp_result):
        """Test Latin TEI generation."""
        config = {
            'title': 'Georgics Test',
            'author': 'Virgil',
            'include_lemma': True,
            'include_pos': True,
            'include_morph': True
        }

        generator = LatinTEIGenerator(config)
        tei_xml = generator.generate(sample_nlp_result)

        # Verify basic TEI structure
        assert '<?xml version="1.0" encoding="UTF-8"?>' in tei_xml
        assert '<TEI xmlns="http://www.tei-c.org/ns/1.0"' in tei_xml
        assert 'xml:lang="la"' in tei_xml
        assert '<title>Georgics Test</title>' in tei_xml
        assert '<author>Virgil</author>' in tei_xml

        # Check for botanical index
        assert 'botanical-index' in tei_xml
        assert 'seges' in tei_xml

    def test_greek_tei_generator(self):
        """Test Greek TEI generation."""
        nlp_result = {
            'text': HESIOD_GREEK.strip(),
            'language': 'ancient_greek',
            'model_used': 'CLTK Greek (test)',
            'sentences': [{'text': HESIOD_GREEK.strip(), 'tokens': []}],
            'entities': [],
            'tokens': [],
            'dependencies': [],
            'noun_chunks': [],
            'botanical_terms': [],
            'metadata': {}
        }

        generator = GreekTEIGenerator()
        tei_xml = generator.generate(nlp_result)

        assert 'xml:lang="grc"' in tei_xml
        assert 'Greco Antico' in tei_xml

    def test_tei_factory(self):
        """Test TEI generator factory."""
        latin_gen = create_tei_generator('latin')
        assert isinstance(latin_gen, LatinTEIGenerator)

        greek_gen = create_tei_generator('ancient_greek')
        assert isinstance(greek_gen, GreekTEIGenerator)


class TestOccurrenceSearch:
    """Test occurrence search functionality."""

    @pytest.fixture
    def sample_document(self) -> Dict[str, Any]:
        """Create sample document for search testing."""
        text = "Mox et frumentis labor additus, ut mala culmos esset robigo segnisque horreret in arvis carduus."

        return {
            'text': text,
            'sentences': [
                {
                    'text': text,
                    'tokens': [
                        {'text': 'Mox', 'lemma': 'mox', 'pos': 'ADV', 'morph': '', 'idx': 0, 'i': 0, 'is_space': False},
                        {'text': 'et', 'lemma': 'et', 'pos': 'CONJ', 'morph': '', 'idx': 4, 'i': 1, 'is_space': False},
                        {'text': 'frumentis', 'lemma': 'frumentum', 'pos': 'NOUN', 'morph': '', 'idx': 7, 'i': 2, 'is_space': False},
                        {'text': 'labor', 'lemma': 'labor', 'pos': 'NOUN', 'morph': '', 'idx': 17, 'i': 3, 'is_space': False},
                        {'text': 'additus', 'lemma': 'addo', 'pos': 'VERB', 'morph': '', 'idx': 23, 'i': 4, 'is_space': False},
                        {'text': ',', 'lemma': ',', 'pos': 'PUNCT', 'morph': '', 'idx': 30, 'i': 5, 'is_space': False},
                        {'text': 'ut', 'lemma': 'ut', 'pos': 'CONJ', 'morph': '', 'idx': 32, 'i': 6, 'is_space': False},
                        {'text': 'mala', 'lemma': 'malus', 'pos': 'ADJ', 'morph': '', 'idx': 35, 'i': 7, 'is_space': False},
                        {'text': 'culmos', 'lemma': 'culmus', 'pos': 'NOUN', 'morph': '', 'idx': 40, 'i': 8, 'is_space': False},
                        {'text': 'esset', 'lemma': 'sum', 'pos': 'VERB', 'morph': '', 'idx': 47, 'i': 9, 'is_space': False},
                        {'text': 'robigo', 'lemma': 'robigo', 'pos': 'NOUN', 'morph': '', 'idx': 53, 'i': 10, 'is_space': False},
                    ]
                }
            ],
            'tokens': [],
            'entities': [],
            'dependencies': [],
            'noun_chunks': [],
            'botanical_terms': []
        }

    def test_exact_search(self, sample_document):
        """Test exact search mode."""
        searcher = OccurrenceSearcher(document=sample_document)

        config = SearchConfig(query="labor", mode=SearchMode.EXACT)
        results = searcher.search(config)

        assert len(results) == 1
        assert results[0].word_found == "labor"

    def test_lemmatized_search(self, sample_document):
        """Test lemmatized search mode."""
        searcher = OccurrenceSearcher(document=sample_document)

        # Search for lemma 'frumentum'
        config = SearchConfig(query="frumentum", mode=SearchMode.LEMMATIZED)
        results = searcher.search(config)

        assert len(results) == 1
        assert results[0].word_found == "frumentis"
        assert results[0].lemma == "frumentum"

    def test_regex_search(self, sample_document):
        """Test regex search mode."""
        searcher = OccurrenceSearcher(document=sample_document)

        # Search for words starting with 'fr'
        config = SearchConfig(query=r"^fr", mode=SearchMode.REGEX)
        results = searcher.search(config)

        assert len(results) == 1
        assert results[0].word_found == "frumentis"

    def test_context_extraction(self, sample_document):
        """Test context extraction in search results."""
        searcher = OccurrenceSearcher(document=sample_document)

        config = SearchConfig(query="labor", mode=SearchMode.EXACT, words_before=2, words_after=2)
        results = searcher.search(config)

        assert len(results) == 1
        assert "frumentis" in results[0].context_before
        assert "additus" in results[0].context_after

    def test_search_statistics(self, sample_document):
        """Test search statistics calculation."""
        searcher = OccurrenceSearcher(document=sample_document)

        config = SearchConfig(query="et", mode=SearchMode.EXACT)
        results = searcher.search(config)

        stats = searcher.get_statistics(results)

        assert stats.total_occurrences >= 1
        assert stats.total_words > 0
        assert stats.frequency >= 0


class TestHTMLExport:
    """Test HTML report generation."""

    def test_html_report_generation(self):
        """Test HTML report generation."""
        text = "Prima Ceres ferro mortalis vertere terram instituit."

        results = [
            SearchResult(
                word_found="terram",
                context_before="mortalis vertere",
                context_after="instituit",
                position=35,
                line_number=1,
                section_ref="div.1.s.1",
                lemma="terra",
                pos_tag="NOUN"
            )
        ]

        config = SearchConfig(query="terram", mode=SearchMode.EXACT)

        generator = HTMLReportGenerator(
            original_text=text,
            search_results=results,
            config=config,
            document_title="Georgics Test",
            language="Latino"
        )

        html = generator.generate()

        # Verify HTML structure
        assert '<!DOCTYPE html>' in html
        assert 'Analisi Occorrenze' in html
        assert 'terram' in html
        assert '1 occorrenze' in html or 'Occorrenze Totali' in html
        assert 'Georgics Test' in html


class TestModelRegistry:
    """Test model registry functionality."""

    def test_get_available_models(self):
        """Test listing available models."""
        models = get_available_models()

        assert 'latin' in models
        assert 'ancient_greek' in models
        assert len(models['latin']) > 0

    def test_get_provider_for_latin(self):
        """Test getting provider for Latin."""
        provider = get_provider_for_language('latin')

        assert provider is not None
        assert 'latin' in provider.supported_languages or 'la' in provider.supported_languages

    def test_get_provider_for_greek(self):
        """Test getting provider for Greek."""
        provider = get_provider_for_language('ancient_greek')

        assert provider is not None
        assert 'ancient_greek' in provider.supported_languages or 'grc' in provider.supported_languages


# Integration test
class TestIntegration:
    """Integration tests for the complete pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_latin(self):
        """Test complete pipeline from text to TEI."""
        text = GEORGICS_BOOK_2.strip()

        # 1. Detect language
        detector = ClassicalLanguageDetector()
        detection = detector.detect(text)
        assert detection.language == ClassicalLanguage.LATIN

        # 2. Process with NLP
        provider = get_provider_for_language('latin')
        await provider.initialize()
        nlp_result = await provider.process(text)

        assert nlp_result.language == 'latin'
        assert len(nlp_result.tokens) > 0

        # 3. Generate TEI
        tei_generator = create_tei_generator('latin', config={'title': 'Georgics II'})
        tei_xml = tei_generator.generate(nlp_result.to_dict())

        assert '<?xml version="1.0"' in tei_xml
        assert 'TEI' in tei_xml

        # 4. Search for botanical terms
        searcher = OccurrenceSearcher(document=nlp_result.to_dict())
        config = SearchConfig(query="vitis", mode=SearchMode.LEMMATIZED)
        results = searcher.search(config)

        # Note: actual results depend on NLP processing quality
        assert isinstance(results, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

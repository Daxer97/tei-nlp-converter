"""
Comprehensive tests for the domain-specific NLP architecture.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Import domain NLP components
from domain_nlp.model_providers.base import (
    Entity,
    ModelMetadata,
    ModelCapabilities,
    ModelPerformance,
    SelectionCriteria,
    NERModel,
    ModelStatus
)
from domain_nlp.model_providers.registry import ModelProviderRegistry, ModelCatalog, TrustValidator
from domain_nlp.model_providers.spacy_provider import SpacyModelProvider
from domain_nlp.knowledge_bases.base import (
    KBEntity,
    KBMetadata,
    EnrichedEntity,
    KBSelectionCriteria,
    SyncFrequency,
    CacheStrategy
)
from domain_nlp.knowledge_bases.registry import KnowledgeBaseRegistry
from domain_nlp.knowledge_bases.cache import LRUCache, MultiTierCacheManager
from domain_nlp.pattern_matching.matcher import DomainPatternMatcher, StructuredEntity
from domain_nlp.pattern_matching.patterns import MEDICAL_PATTERNS, LEGAL_PATTERNS
from domain_nlp.pipeline.ensemble import EnsembleMerger
from domain_nlp.pipeline.dynamic_pipeline import DynamicNLPPipeline, PipelineConfig
from domain_nlp.config.loader import ConfigurationLoader, DomainConfig


# ==================== Model Provider Tests ====================

class TestModelMetadata:
    """Tests for ModelMetadata"""

    def test_model_metadata_creation(self):
        meta = ModelMetadata(
            model_id="test/model",
            provider="test",
            version="1.0",
            domain="medical",
            entity_types={"DRUG", "DISEASE"},
            performance=ModelPerformance(f1_score=0.85, latency_ms=50.0),
            trusted=True
        )

        assert meta.model_id == "test/model"
        assert meta.domain == "medical"
        assert "DRUG" in meta.entity_types
        assert meta.performance.f1_score == 0.85
        assert meta.trusted is True

    def test_model_metadata_to_dict(self):
        meta = ModelMetadata(
            model_id="test/model",
            provider="test",
            version="1.0"
        )

        data = meta.to_dict()
        assert "model_id" in data
        assert "provider" in data
        assert "performance" in data
        assert isinstance(data["entity_types"], list)


class TestModelCatalog:
    """Tests for ModelCatalog"""

    def test_catalog_update(self):
        catalog = ModelCatalog()

        models = {
            "spacy": [
                ModelMetadata(
                    model_id="spacy/en_core_web_sm",
                    provider="spacy",
                    version="3.7.0",
                    domain="general"
                )
            ],
            "huggingface": [
                ModelMetadata(
                    model_id="biobert",
                    provider="huggingface",
                    version="1.0",
                    domain="medical"
                )
            ]
        }

        catalog.update(models)

        assert len(catalog.get_all_models()) == 2
        assert catalog.get_by_id("spacy/en_core_web_sm") is not None
        assert catalog.get_by_id("biobert") is not None

    def test_catalog_query_by_domain(self):
        catalog = ModelCatalog()

        models = {
            "test": [
                ModelMetadata("m1", "test", "1.0", domain="medical"),
                ModelMetadata("m2", "test", "1.0", domain="legal"),
                ModelMetadata("m3", "test", "1.0", domain="medical"),
            ]
        }

        catalog.update(models)

        medical_models = catalog.query(domain="medical")
        assert len(medical_models) == 2

        legal_models = catalog.query(domain="legal")
        assert len(legal_models) == 1

    def test_catalog_query_by_performance(self):
        catalog = ModelCatalog()

        models = {
            "test": [
                ModelMetadata("m1", "test", "1.0", performance=ModelPerformance(f1_score=0.85)),
                ModelMetadata("m2", "test", "1.0", performance=ModelPerformance(f1_score=0.70)),
                ModelMetadata("m3", "test", "1.0", performance=ModelPerformance(f1_score=0.90)),
            ]
        }

        catalog.update(models)

        high_f1 = catalog.query(min_f1=0.80)
        assert len(high_f1) == 2


class TestTrustValidator:
    """Tests for TrustValidator"""

    def test_trusted_source_validation(self):
        validator = TrustValidator()

        trusted_model = ModelMetadata(
            model_id="spacy/en_core_web_sm",
            provider="spacy",
            version="1.0",
            source_url="https://github.com/explosion/spacy-models",
            entity_types={"PERSON"},
            performance=ModelPerformance(f1_score=0.85)
        )

        assert validator.validate(trusted_model) is True

    def test_untrusted_source_validation(self):
        validator = TrustValidator()

        untrusted_model = ModelMetadata(
            model_id="unknown/model",
            provider="unknown",
            version="1.0",
            source_url="https://unknown-source.com",
            entity_types={"PERSON"},
            performance=ModelPerformance(f1_score=0.85)
        )

        assert validator.validate(untrusted_model) is False

    def test_low_performance_validation(self):
        validator = TrustValidator()

        low_perf_model = ModelMetadata(
            model_id="spacy/model",
            provider="spacy",
            version="1.0",
            source_url="https://github.com/explosion",
            entity_types={"PERSON"},
            performance=ModelPerformance(f1_score=0.50)
        )

        assert validator.validate(low_perf_model) is False


class TestSelectionCriteria:
    """Tests for SelectionCriteria"""

    def test_criteria_matches(self):
        criteria = SelectionCriteria(
            min_f1_score=0.80,
            max_latency_ms=100,
            entity_types={"PERSON", "ORG"},
            prefer_trusted=True
        )

        good_model = ModelMetadata(
            model_id="good",
            provider="test",
            version="1.0",
            entity_types={"PERSON", "ORG", "LOC"},
            performance=ModelPerformance(f1_score=0.85, latency_ms=50),
            trusted=True
        )

        assert criteria.matches(good_model) is True

    def test_criteria_rejects_low_f1(self):
        criteria = SelectionCriteria(min_f1_score=0.80)

        bad_model = ModelMetadata(
            model_id="bad",
            provider="test",
            version="1.0",
            performance=ModelPerformance(f1_score=0.70)
        )

        assert criteria.matches(bad_model) is False

    def test_criteria_rejects_high_latency(self):
        criteria = SelectionCriteria(max_latency_ms=100)

        slow_model = ModelMetadata(
            model_id="slow",
            provider="test",
            version="1.0",
            performance=ModelPerformance(latency_ms=200)
        )

        assert criteria.matches(slow_model) is False


# ==================== Pattern Matching Tests ====================

class TestPatternMatcher:
    """Tests for DomainPatternMatcher"""

    def test_medical_pattern_extraction(self):
        matcher = DomainPatternMatcher(domain="medical")

        text = "Patient was prescribed Metformin 500 mg twice daily for ICD-10 E11.9"
        entities = matcher.extract_structured_data(text)

        # Should find dosage pattern
        dosages = [e for e in entities if e.entity_type == "DOSAGE"]
        assert len(dosages) > 0
        assert "500" in dosages[0].text

    def test_legal_pattern_extraction(self):
        matcher = DomainPatternMatcher(domain="legal")

        text = "This case is governed by 18 U.S.C. § 1001 and 29 C.F.R. § 1910.134"
        entities = matcher.extract_structured_data(text)

        # Should find USC and CFR citations
        usc = [e for e in entities if "USC" in e.entity_type]
        cfr = [e for e in entities if "CFR" in e.entity_type]

        assert len(usc) > 0 or len(cfr) > 0

    def test_custom_pattern_addition(self):
        matcher = DomainPatternMatcher(domain="general")

        matcher.add_pattern(
            name="custom_code",
            pattern=r'\bCODE-(\d{4})\b',
            entity_type="CUSTOM_CODE"
        )

        text = "Reference CODE-1234 for details"
        entities = matcher.extract_structured_data(text)

        custom_codes = [e for e in entities if e.entity_type == "CUSTOM_CODE"]
        assert len(custom_codes) == 1

    def test_entity_validation(self):
        matcher = DomainPatternMatcher(domain="medical")

        # Valid ICD-10 code
        assert matcher.validate_entity("icd10_code", "E11.9") is True

        # Invalid format
        assert matcher.validate_entity("icd10_code", "INVALID") is False

    def test_pattern_info(self):
        matcher = DomainPatternMatcher(domain="medical")
        info = matcher.get_pattern_info()

        assert "dosage" in info
        assert info["dosage"]["priority"] == "high"


# ==================== Ensemble Merging Tests ====================

class TestEnsembleMerger:
    """Tests for EnsembleMerger"""

    def test_majority_vote_merging(self):
        merger = EnsembleMerger(strategy="majority_vote")

        # Three models, two agree on PERSON, one says ORG
        model_results = [
            [Entity("John", "PERSON", 0, 4, 0.9)],
            [Entity("John", "PERSON", 0, 4, 0.85)],
            [Entity("John", "ORG", 0, 4, 0.7)]
        ]

        merged = merger.merge(model_results)

        assert len(merged) == 1
        assert merged[0].type == "PERSON"  # Majority vote wins
        assert merged[0].confidence > 0.8  # High confidence due to agreement

    def test_weighted_vote_merging(self):
        merger = EnsembleMerger(strategy="weighted_vote")

        model_results = [
            [Entity("John", "PERSON", 0, 4, 0.9)],
            [Entity("John", "ORG", 0, 4, 0.8)]
        ]

        # Higher weight for second model
        weights = [0.3, 0.7]

        merged = merger.merge(model_results, weights=weights)

        assert len(merged) == 1
        assert merged[0].type == "ORG"  # Higher weighted model wins

    def test_union_merging(self):
        merger = EnsembleMerger(strategy="union")

        model_results = [
            [Entity("John", "PERSON", 0, 4, 0.9)],
            [Entity("IBM", "ORG", 10, 13, 0.85)]
        ]

        merged = merger.merge(model_results)

        assert len(merged) == 2  # Both entities kept

    def test_intersection_merging(self):
        merger = EnsembleMerger(strategy="intersection")

        model_results = [
            [Entity("John", "PERSON", 0, 4, 0.9), Entity("IBM", "ORG", 10, 13, 0.85)],
            [Entity("John", "PERSON", 0, 4, 0.8)]
        ]

        merged = merger.merge(model_results)

        assert len(merged) == 1  # Only common entity
        assert merged[0].text == "John"

    def test_agreement_score_calculation(self):
        merger = EnsembleMerger()

        # Perfect agreement
        model_results = [
            [Entity("John", "PERSON", 0, 4, 0.9)],
            [Entity("John", "PERSON", 0, 4, 0.85)],
            [Entity("John", "PERSON", 0, 4, 0.88)]
        ]

        score = merger.calculate_agreement_score(model_results)
        assert score == 1.0

    def test_disagreement_score_calculation(self):
        merger = EnsembleMerger()

        # Disagreement on type
        model_results = [
            [Entity("John", "PERSON", 0, 4, 0.9)],
            [Entity("John", "ORG", 0, 4, 0.85)],
            [Entity("John", "LOC", 0, 4, 0.88)]
        ]

        score = merger.calculate_agreement_score(model_results)
        assert score < 0.5  # Low agreement


# ==================== Knowledge Base Tests ====================

class TestLRUCache:
    """Tests for LRU cache"""

    def test_cache_basic_operations(self):
        cache = LRUCache(maxsize=3)

        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)

        assert cache.get("a") == 1
        assert cache.get("b") == 2
        assert len(cache) == 3

    def test_cache_eviction(self):
        cache = LRUCache(maxsize=2)

        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # Should evict "a"

        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_cache_lru_order(self):
        cache = LRUCache(maxsize=2)

        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")  # Access "a" to make it recently used
        cache.set("c", 3)  # Should evict "b"

        assert cache.get("a") == 1
        assert cache.get("b") is None
        assert cache.get("c") == 3

    def test_cache_stats(self):
        cache = LRUCache(maxsize=10)

        cache.set("a", 1)
        cache.get("a")  # Hit
        cache.get("b")  # Miss

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5


class TestKBEntity:
    """Tests for KBEntity"""

    def test_kb_entity_creation(self):
        entity = KBEntity(
            kb_id="umls",
            entity_id="C0011849",
            text="Diabetes Mellitus",
            entity_type="DISEASE",
            synonyms=["Diabetes", "DM"],
            definition="A metabolic disease..."
        )

        assert entity.kb_id == "umls"
        assert "Diabetes" in entity.synonyms

    def test_kb_entity_serialization(self):
        entity = KBEntity(
            kb_id="rxnorm",
            entity_id="R123",
            text="Metformin",
            entity_type="DRUG"
        )

        data = entity.to_dict()
        restored = KBEntity.from_dict(data)

        assert restored.kb_id == entity.kb_id
        assert restored.text == entity.text


class TestEnrichedEntity:
    """Tests for EnrichedEntity"""

    def test_enriched_entity_with_kb(self):
        kb_entity = KBEntity("umls", "C123", "Aspirin", "DRUG")

        enriched = EnrichedEntity(
            text="aspirin",
            entity_type="DRUG",
            start=10,
            end=17,
            confidence=0.95,
            kb_entity=kb_entity
        )

        assert enriched.is_enriched is True
        assert enriched.kb_id == "C123"

    def test_enriched_entity_without_kb(self):
        enriched = EnrichedEntity(
            text="aspirin",
            entity_type="DRUG",
            start=10,
            end=17,
            confidence=0.95
        )

        assert enriched.is_enriched is False
        assert enriched.kb_id is None


# ==================== Configuration Tests ====================

class TestConfigurationLoader:
    """Tests for ConfigurationLoader"""

    def test_default_configs_loaded(self):
        loader = ConfigurationLoader()

        domains = loader.list_domains()
        assert "medical" in domains
        assert "legal" in domains
        assert "general" in domains

    def test_get_domain_config(self):
        loader = ConfigurationLoader()

        medical_config = loader.get_domain_config("medical")
        assert medical_config is not None
        assert medical_config.name == "medical"
        assert medical_config.enabled is True

    def test_build_pipeline_config(self):
        loader = ConfigurationLoader()

        pipeline_config = loader.build_pipeline_config("medical")

        assert pipeline_config.domain == "medical"
        assert isinstance(pipeline_config.model_selection_criteria, SelectionCriteria)
        assert isinstance(pipeline_config.kb_selection_criteria, KBSelectionCriteria)

    def test_pipeline_config_criteria(self):
        loader = ConfigurationLoader()

        config = loader.build_pipeline_config("medical")

        # Check model selection criteria
        assert config.model_selection_criteria.min_f1_score >= 0.80
        assert config.model_selection_criteria.max_latency_ms <= 300

    def test_add_custom_domain(self):
        loader = ConfigurationLoader()

        custom = DomainConfig(
            name="custom_domain",
            enabled=True,
            model_selection={"min_f1_score": 0.90}
        )

        loader.add_domain_config(custom)

        retrieved = loader.get_domain_config("custom_domain")
        assert retrieved is not None
        assert retrieved.model_selection["min_f1_score"] == 0.90


# ==================== Pipeline Tests ====================

class TestPipelineConfig:
    """Tests for PipelineConfig"""

    def test_pipeline_config_creation(self):
        config = PipelineConfig(
            domain="medical",
            model_selection_criteria=SelectionCriteria(min_f1_score=0.85),
            kb_selection_criteria=KBSelectionCriteria(fallback_chain=["umls"]),
            ensemble_strategy="majority_vote"
        )

        assert config.domain == "medical"
        assert config.enable_pattern_matching is True
        assert config.enable_kb_enrichment is True


# ==================== Integration Tests ====================

@pytest.mark.asyncio
class TestDynamicPipelineIntegration:
    """Integration tests for DynamicNLPPipeline"""

    async def test_pipeline_initialization(self):
        """Test pipeline can be created"""
        config = PipelineConfig(
            domain="general",
            model_selection_criteria=SelectionCriteria(),
            kb_selection_criteria=KBSelectionCriteria(),
            enable_kb_enrichment=False
        )

        pipeline = DynamicNLPPipeline(config)

        assert pipeline.domain == "general"
        assert pipeline._initialized is False

    async def test_pipeline_statistics(self):
        """Test pipeline statistics"""
        config = PipelineConfig(
            domain="medical",
            model_selection_criteria=SelectionCriteria(),
            kb_selection_criteria=KBSelectionCriteria(),
            enable_kb_enrichment=False
        )

        pipeline = DynamicNLPPipeline(config)

        stats = pipeline.get_statistics()

        assert stats["domain"] == "medical"
        assert stats["active_models"] == 0
        assert "metrics" in stats

    async def test_ensemble_strategy_update(self):
        """Test updating ensemble strategy"""
        config = PipelineConfig(
            domain="general",
            model_selection_criteria=SelectionCriteria(),
            kb_selection_criteria=KBSelectionCriteria(),
            ensemble_strategy="majority_vote"
        )

        pipeline = DynamicNLPPipeline(config)

        pipeline.update_ensemble_strategy("weighted_vote")

        assert pipeline.config.ensemble_strategy == "weighted_vote"
        assert pipeline.ensemble_merger.strategy == "weighted_vote"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

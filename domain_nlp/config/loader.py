"""
Configuration loader for domain-specific NLP settings.

Loads domain configurations from YAML files and converts them
to pipeline configuration objects.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from ..model_providers.base import SelectionCriteria
from ..knowledge_bases.base import KBSelectionCriteria, SyncFrequency, CacheStrategy
from ..pipeline.dynamic_pipeline import PipelineConfig

logger = logging.getLogger(__name__)


@dataclass
class DomainConfig:
    """Complete configuration for a domain"""
    name: str
    enabled: bool = True
    model_selection: Dict[str, Any] = field(default_factory=dict)
    kb_selection: Dict[str, Any] = field(default_factory=dict)
    pattern_matching: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConfigurationLoader:
    """Loads and manages domain configurations"""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration loader.

        Args:
            config_path: Path to configuration directory (defaults to ./domain_nlp/config/domains)
        """
        if not YAML_AVAILABLE:
            logger.warning("PyYAML not installed, using default configurations")

        if config_path:
            self.config_path = Path(config_path)
        else:
            # Default to config/domains directory relative to this module
            self.config_path = Path(__file__).parent / "domains"

        self._configs: Dict[str, DomainConfig] = {}
        self._load_configs()

    def _load_configs(self) -> None:
        """Load all configuration files"""
        if not self.config_path.exists():
            logger.warning(f"Config path does not exist: {self.config_path}")
            self._load_default_configs()
            return

        if not YAML_AVAILABLE:
            self._load_default_configs()
            return

        # Load all YAML files in config directory
        for config_file in self.config_path.glob("*.yaml"):
            try:
                with open(config_file, "r") as f:
                    config_data = yaml.safe_load(f)

                if config_data and "domain" in config_data:
                    domain_name = config_data["domain"]
                    self._configs[domain_name] = self._parse_config(config_data)
                    logger.info(f"Loaded configuration for domain: {domain_name}")
            except Exception as e:
                logger.error(f"Failed to load config {config_file}: {e}")

        # Load defaults if no configs found
        if not self._configs:
            self._load_default_configs()

    def _load_default_configs(self) -> None:
        """Load default configurations"""
        # Medical domain defaults
        self._configs["medical"] = DomainConfig(
            name="medical",
            enabled=True,
            model_selection={
                "min_f1_score": 0.85,
                "max_latency_ms": 200,
                "preferred_providers": ["spacy", "huggingface"],
                "entity_types": ["DRUG", "DISEASE", "CHEMICAL", "GENE"],
                "ensemble_strategy": "majority_vote",
                "min_models": 2,
                "max_models": 3
            },
            kb_selection={
                "required_kbs": [],
                "optional_kbs": ["rxnorm", "snomed"],
                "fallback_chain": ["umls", "rxnorm", "snomed"],
                "cache_strategy": "aggressive",
                "sync_frequency": "daily"
            },
            pattern_matching={
                "enabled": True,
                "custom_patterns": {}
            }
        )

        # Legal domain defaults
        self._configs["legal"] = DomainConfig(
            name="legal",
            enabled=True,
            model_selection={
                "min_f1_score": 0.80,
                "max_latency_ms": 250,
                "preferred_providers": ["huggingface"],
                "entity_types": ["CASE_CITATION", "STATUTE", "LEGAL_ENTITY"],
                "ensemble_strategy": "weighted_vote",
                "min_models": 1,
                "max_models": 2
            },
            kb_selection={
                "required_kbs": [],
                "optional_kbs": ["courtlistener"],
                "fallback_chain": ["usc", "courtlistener", "cfr"],
                "cache_strategy": "moderate",
                "sync_frequency": "weekly"
            },
            pattern_matching={
                "enabled": True,
                "custom_patterns": {}
            }
        )

        # General domain defaults
        self._configs["general"] = DomainConfig(
            name="general",
            enabled=True,
            model_selection={
                "min_f1_score": 0.75,
                "max_latency_ms": 100,
                "preferred_providers": ["spacy"],
                "entity_types": ["PERSON", "ORG", "GPE", "DATE"],
                "ensemble_strategy": "majority_vote",
                "min_models": 1,
                "max_models": 2
            },
            kb_selection={
                "required_kbs": [],
                "optional_kbs": [],
                "fallback_chain": [],
                "cache_strategy": "minimal",
                "sync_frequency": "weekly"
            },
            pattern_matching={
                "enabled": True,
                "custom_patterns": {}
            }
        )

        logger.info("Loaded default configurations")

    def _parse_config(self, data: Dict[str, Any]) -> DomainConfig:
        """Parse configuration data into DomainConfig"""
        return DomainConfig(
            name=data.get("domain", "unknown"),
            enabled=data.get("enabled", True),
            model_selection=data.get("model_selection", {}),
            kb_selection=data.get("kb_selection", {}),
            pattern_matching=data.get("pattern_matching", {}),
            metadata=data.get("metadata", {})
        )

    def get_domain_config(self, domain: str) -> Optional[DomainConfig]:
        """Get configuration for a specific domain"""
        return self._configs.get(domain)

    def list_domains(self) -> List[str]:
        """List all configured domains"""
        return list(self._configs.keys())

    def build_pipeline_config(self, domain: str) -> PipelineConfig:
        """
        Build a PipelineConfig from domain configuration.

        Args:
            domain: Domain name

        Returns:
            PipelineConfig ready for use
        """
        domain_config = self.get_domain_config(domain)

        if not domain_config:
            logger.warning(f"No config for domain '{domain}', using general defaults")
            domain_config = self.get_domain_config("general")
            if not domain_config:
                domain_config = DomainConfig(name=domain)

        # Build model selection criteria
        model_sel = domain_config.model_selection
        model_criteria = SelectionCriteria(
            min_f1_score=model_sel.get("min_f1_score", 0.75),
            max_latency_ms=model_sel.get("max_latency_ms", 200),
            preferred_providers=model_sel.get("preferred_providers", []),
            entity_types=set(model_sel.get("entity_types", [])),
            ensemble_strategy=model_sel.get("ensemble_strategy", "majority_vote"),
            min_models=model_sel.get("min_models", 1),
            max_models=model_sel.get("max_models", 3),
            prefer_trusted=model_sel.get("prefer_trusted", True)
        )

        # Build KB selection criteria
        kb_sel = domain_config.kb_selection
        sync_freq_str = kb_sel.get("sync_frequency", "weekly")
        cache_strat_str = kb_sel.get("cache_strategy", "moderate")

        try:
            sync_freq = SyncFrequency(sync_freq_str)
        except ValueError:
            sync_freq = SyncFrequency.WEEKLY

        try:
            cache_strat = CacheStrategy(cache_strat_str)
        except ValueError:
            cache_strat = CacheStrategy.MODERATE

        kb_criteria = KBSelectionCriteria(
            required_kbs=kb_sel.get("required_kbs", []),
            optional_kbs=kb_sel.get("optional_kbs", []),
            fallback_chain=kb_sel.get("fallback_chain", []),
            cache_strategy=cache_strat,
            sync_frequency=sync_freq,
            prefer_trusted=kb_sel.get("prefer_trusted", True)
        )

        # Build pattern matching config
        pattern_config = domain_config.pattern_matching
        custom_patterns = pattern_config.get("custom_patterns", {})

        # Build complete pipeline config
        pipeline_config = PipelineConfig(
            domain=domain,
            model_selection_criteria=model_criteria,
            kb_selection_criteria=kb_criteria,
            ensemble_strategy=model_sel.get("ensemble_strategy", "majority_vote"),
            enable_pattern_matching=pattern_config.get("enabled", True),
            enable_kb_enrichment=bool(kb_criteria.fallback_chain),
            max_parallel_models=model_sel.get("max_models", 3),
            custom_patterns=custom_patterns if custom_patterns else None,
            metadata=domain_config.metadata
        )

        return pipeline_config

    def reload_configs(self) -> None:
        """Reload all configurations from disk"""
        self._configs.clear()
        self._load_configs()
        logger.info("Reloaded configurations")

    def add_domain_config(self, domain_config: DomainConfig) -> None:
        """Add or update a domain configuration"""
        self._configs[domain_config.name] = domain_config
        logger.info(f"Added/updated configuration for domain: {domain_config.name}")

    def save_domain_config(self, domain: str) -> bool:
        """
        Save domain configuration to disk.

        Args:
            domain: Domain name to save

        Returns:
            True if successful, False otherwise
        """
        if not YAML_AVAILABLE:
            logger.error("PyYAML not installed, cannot save config")
            return False

        domain_config = self._configs.get(domain)
        if not domain_config:
            logger.error(f"No configuration found for domain: {domain}")
            return False

        # Ensure config directory exists
        self.config_path.mkdir(parents=True, exist_ok=True)

        config_file = self.config_path / f"{domain}.yaml"

        try:
            config_data = {
                "domain": domain_config.name,
                "enabled": domain_config.enabled,
                "model_selection": domain_config.model_selection,
                "kb_selection": domain_config.kb_selection,
                "pattern_matching": domain_config.pattern_matching,
                "metadata": domain_config.metadata
            }

            with open(config_file, "w") as f:
                yaml.safe_dump(config_data, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Saved configuration for domain '{domain}' to {config_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to save config for domain '{domain}': {e}")
            return False


def create_sample_configs(config_path: str) -> None:
    """Create sample YAML configuration files"""
    if not YAML_AVAILABLE:
        logger.error("PyYAML not installed, cannot create sample configs")
        return

    path = Path(config_path)
    path.mkdir(parents=True, exist_ok=True)

    # Medical domain sample
    medical_config = {
        "domain": "medical",
        "enabled": True,
        "model_selection": {
            "min_f1_score": 0.85,
            "max_latency_ms": 200,
            "preferred_providers": ["spacy", "huggingface"],
            "entity_types": ["DRUG", "DISEASE", "CHEMICAL", "PROCEDURE", "ANATOMY"],
            "ensemble_strategy": "majority_vote",
            "min_models": 2,
            "max_models": 3,
            "prefer_trusted": True
        },
        "kb_selection": {
            "required_kbs": [],
            "optional_kbs": ["rxnorm", "snomed"],
            "fallback_chain": ["umls", "rxnorm", "snomed"],
            "cache_strategy": "aggressive",
            "sync_frequency": "daily",
            "prefer_trusted": True
        },
        "pattern_matching": {
            "enabled": True,
            "custom_patterns": {
                "mrn": {
                    "pattern": "\\bMRN[:#]?\\s*(\\d{6,10})\\b",
                    "entity_type": "MEDICAL_RECORD_NUMBER",
                    "description": "Medical Record Number",
                    "priority": "high"
                }
            }
        },
        "metadata": {
            "version": "1.0.0",
            "author": "NLP Team",
            "last_updated": "2024-01-01"
        }
    }

    with open(path / "medical.yaml", "w") as f:
        yaml.safe_dump(medical_config, f, default_flow_style=False, sort_keys=False)

    # Legal domain sample
    legal_config = {
        "domain": "legal",
        "enabled": True,
        "model_selection": {
            "min_f1_score": 0.80,
            "max_latency_ms": 250,
            "preferred_providers": ["huggingface"],
            "entity_types": ["CASE_CITATION", "STATUTE", "LEGAL_ENTITY", "COURT", "JUDGE"],
            "ensemble_strategy": "weighted_vote",
            "min_models": 1,
            "max_models": 2,
            "prefer_trusted": True
        },
        "kb_selection": {
            "required_kbs": [],
            "optional_kbs": ["courtlistener"],
            "fallback_chain": ["usc", "courtlistener", "cfr"],
            "cache_strategy": "moderate",
            "sync_frequency": "weekly"
        },
        "pattern_matching": {
            "enabled": True,
            "custom_patterns": {}
        },
        "metadata": {
            "version": "1.0.0",
            "author": "NLP Team"
        }
    }

    with open(path / "legal.yaml", "w") as f:
        yaml.safe_dump(legal_config, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Created sample configuration files in {path}")

"""
Auto-Discovery Service

Automatically discovers new models and knowledge bases from
various sources (Hugging Face, spaCy, registries, etc.)
"""
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import asyncio
import aiohttp

from logger import get_logger

logger = get_logger(__name__)


class DiscoverySource(Enum):
    """Sources for component discovery"""
    HUGGINGFACE = "huggingface"
    SPACY = "spacy"
    REGISTRY_FILE = "registry_file"
    DATABASE = "database"
    GITHUB = "github"


@dataclass
class DiscoveredComponent:
    """Component discovered from a source"""
    component_type: str          # "ner_model" or "knowledge_base"
    component_id: str
    source: DiscoverySource
    source_url: str

    # Metadata
    name: str
    description: str = ""
    version: Optional[str] = None
    provider: str = ""
    domain: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)

    # Quality indicators
    downloads: int = 0
    stars: int = 0
    last_updated: Optional[datetime] = None

    # Discovery metadata
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    already_registered: bool = False


class AutoDiscoveryService:
    """
    Automatically discovers new models and knowledge bases

    Features:
    - Periodic scanning of discovery sources
    - Filtering by domain, quality, recency
    - Deduplication
    - Automatic registration (opt-in)

    Example:
        discovery = AutoDiscoveryService()

        # Configure sources
        discovery.add_source(DiscoverySource.HUGGINGFACE, {
            "filter_domains": ["medical", "legal"],
            "min_downloads": 1000
        })

        # Run discovery
        discovered = await discovery.discover()

        print(f"Found {len(discovered)} new components")
        for component in discovered:
            print(f"  - {component.name} ({component.source.value})")
    """

    def __init__(
        self,
        scan_interval_hours: int = 24,
        auto_register: bool = False
    ):
        """
        Initialize auto-discovery service

        Args:
            scan_interval_hours: How often to scan sources
            auto_register: Automatically register discovered components
        """
        self.scan_interval = timedelta(hours=scan_interval_hours)
        self.auto_register = auto_register

        # Source configurations
        self._sources: Dict[DiscoverySource, Dict[str, Any]] = {}

        # Discovered components
        self._discovered: List[DiscoveredComponent] = []

        # Already known components
        self._known_components: Set[str] = set()

        # Running state
        self._running = False
        self._scan_task = None

    def add_source(
        self,
        source: DiscoverySource,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Add a discovery source

        Args:
            source: Source type
            config: Source-specific configuration
        """
        self._sources[source] = config or {}
        logger.info(f"Added discovery source: {source.value}")

    def remove_source(self, source: DiscoverySource):
        """Remove a discovery source"""
        if source in self._sources:
            del self._sources[source]
            logger.info(f"Removed discovery source: {source.value}")

    async def start(self):
        """Start periodic discovery scans"""
        if self._running:
            logger.warning("Auto-discovery already running")
            return

        self._running = True
        self._scan_task = asyncio.create_task(self._scan_loop())

        logger.info(
            f"Started auto-discovery service "
            f"(interval={self.scan_interval.total_seconds() / 3600:.0f}h)"
        )

    async def stop(self):
        """Stop discovery scans"""
        if not self._running:
            return

        self._running = False

        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped auto-discovery service")

    async def _scan_loop(self):
        """Periodic scan loop"""
        while self._running:
            try:
                logger.info("Running auto-discovery scan...")
                discovered = await self.discover()
                logger.info(f"Discovery scan found {len(discovered)} new components")

            except Exception as e:
                logger.error(f"Error in discovery scan: {e}")

            # Wait for next scan
            await asyncio.sleep(self.scan_interval.total_seconds())

    async def discover(self) -> List[DiscoveredComponent]:
        """
        Run discovery across all sources

        Returns:
            List of newly discovered components
        """
        all_discovered = []

        # Discover from each source
        for source, config in self._sources.items():
            try:
                logger.debug(f"Discovering from {source.value}...")

                if source == DiscoverySource.HUGGINGFACE:
                    discovered = await self._discover_huggingface(config)
                elif source == DiscoverySource.SPACY:
                    discovered = await self._discover_spacy(config)
                elif source == DiscoverySource.REGISTRY_FILE:
                    discovered = await self._discover_registry_file(config)
                elif source == DiscoverySource.DATABASE:
                    discovered = await self._discover_database(config)
                elif source == DiscoverySource.GITHUB:
                    discovered = await self._discover_github(config)
                else:
                    logger.warning(f"Unknown discovery source: {source}")
                    continue

                logger.debug(f"Found {len(discovered)} components from {source.value}")
                all_discovered.extend(discovered)

            except Exception as e:
                logger.error(f"Error discovering from {source.value}: {e}")

        # Deduplicate and filter
        new_components = self._filter_new_components(all_discovered)

        # Update discovered list
        self._discovered.extend(new_components)

        return new_components

    async def _discover_huggingface(
        self,
        config: Dict[str, Any]
    ) -> List[DiscoveredComponent]:
        """Discover models from Hugging Face"""
        discovered = []

        # Filters
        filter_domains = config.get("filter_domains", [])
        min_downloads = config.get("min_downloads", 0)
        tags = config.get("tags", ["ner", "token-classification"])

        try:
            # Search Hugging Face API
            base_url = "https://huggingface.co/api/models"

            async with aiohttp.ClientSession() as session:
                for tag in tags:
                    url = f"{base_url}?filter={tag}&sort=downloads&limit=50"

                    async with session.get(url) as response:
                        if response.status != 200:
                            logger.warning(f"Hugging Face API returned {response.status}")
                            continue

                        models = await response.json()

                        for model in models:
                            # Filter by downloads
                            if model.get("downloads", 0) < min_downloads:
                                continue

                            # Try to infer domain from tags or modelId
                            domain = self._infer_domain(
                                model.get("tags", []),
                                model.get("modelId", "")
                            )

                            # Filter by domain
                            if filter_domains and domain not in filter_domains:
                                continue

                            component = DiscoveredComponent(
                                component_type="ner_model",
                                component_id=model["modelId"],
                                source=DiscoverySource.HUGGINGFACE,
                                source_url=f"https://huggingface.co/{model['modelId']}",
                                name=model["modelId"],
                                description=model.get("description", ""),
                                provider="huggingface",
                                domain=domain,
                                capabilities=model.get("tags", []),
                                downloads=model.get("downloads", 0),
                                stars=model.get("likes", 0),
                                last_updated=datetime.fromisoformat(
                                    model["lastModified"].replace("Z", "+00:00")
                                ) if "lastModified" in model else None
                            )

                            discovered.append(component)

        except Exception as e:
            logger.error(f"Error discovering from Hugging Face: {e}")

        return discovered

    async def _discover_spacy(
        self,
        config: Dict[str, Any]
    ) -> List[DiscoveredComponent]:
        """Discover models from spaCy"""
        discovered = []

        # Known spaCy models (could also fetch from spacy.io API)
        known_models = [
            {
                "id": "en_core_web_sm",
                "name": "English Core Web (Small)",
                "domain": "general",
                "capabilities": ["NER", "POS", "DEP"]
            },
            {
                "id": "en_core_web_lg",
                "name": "English Core Web (Large)",
                "domain": "general",
                "capabilities": ["NER", "POS", "DEP", "vectors"]
            },
            {
                "id": "en_ner_bc5cdr_md",
                "name": "BC5CDR (SciSpacy)",
                "domain": "medical",
                "capabilities": ["DISEASE", "CHEMICAL"]
            },
            {
                "id": "en_ner_bionlp13cg_md",
                "name": "BioNLP13CG (SciSpacy)",
                "domain": "medical",
                "capabilities": ["CANCER", "ORGAN", "TISSUE", "CELL"]
            },
            {
                "id": "en_core_sci_sm",
                "name": "SciSpacy Small",
                "domain": "medical",
                "capabilities": ["NER", "POS", "DEP"]
            }
        ]

        filter_domains = config.get("filter_domains", [])

        for model_info in known_models:
            # Filter by domain
            if filter_domains and model_info["domain"] not in filter_domains:
                continue

            component = DiscoveredComponent(
                component_type="ner_model",
                component_id=model_info["id"],
                source=DiscoverySource.SPACY,
                source_url=f"https://spacy.io/models/{model_info['id']}",
                name=model_info["name"],
                provider="spacy",
                domain=model_info["domain"],
                capabilities=model_info["capabilities"]
            )

            discovered.append(component)

        return discovered

    async def _discover_registry_file(
        self,
        config: Dict[str, Any]
    ) -> List[DiscoveredComponent]:
        """Discover components from a registry file"""
        discovered = []

        # Read registry file (YAML or JSON)
        registry_path = config.get("path")
        if not registry_path:
            logger.warning("No registry file path configured")
            return discovered

        try:
            import yaml
            from pathlib import Path

            with open(registry_path, 'r') as f:
                registry = yaml.safe_load(f)

            # Parse models
            for model in registry.get("models", []):
                component = DiscoveredComponent(
                    component_type="ner_model",
                    component_id=model["id"],
                    source=DiscoverySource.REGISTRY_FILE,
                    source_url=model.get("url", ""),
                    name=model["name"],
                    description=model.get("description", ""),
                    provider=model.get("provider", ""),
                    domain=model.get("domain"),
                    capabilities=model.get("capabilities", [])
                )
                discovered.append(component)

            # Parse knowledge bases
            for kb in registry.get("knowledge_bases", []):
                component = DiscoveredComponent(
                    component_type="knowledge_base",
                    component_id=kb["id"],
                    source=DiscoverySource.REGISTRY_FILE,
                    source_url=kb.get("url", ""),
                    name=kb["name"],
                    description=kb.get("description", ""),
                    provider=kb.get("provider", ""),
                    domain=kb.get("domain")
                )
                discovered.append(component)

        except Exception as e:
            logger.error(f"Error reading registry file: {e}")

        return discovered

    async def _discover_database(
        self,
        config: Dict[str, Any]
    ) -> List[DiscoveredComponent]:
        """Discover components from database"""
        # Placeholder - would query database for registered components
        return []

    async def _discover_github(
        self,
        config: Dict[str, Any]
    ) -> List[DiscoveredComponent]:
        """Discover models from GitHub repositories"""
        # Placeholder - would search GitHub for NER models
        return []

    def _infer_domain(self, tags: List[str], name: str) -> Optional[str]:
        """Infer domain from tags and name"""
        text = " ".join(tags + [name]).lower()

        # Medical keywords
        medical_keywords = [
            "medical", "bio", "clinical", "disease", "drug", "pubmed",
            "medline", "umls", "snomed", "icd", "healthcare"
        ]

        # Legal keywords
        legal_keywords = [
            "legal", "law", "court", "statute", "case", "regulation",
            "contract", "agreement", "legislation"
        ]

        if any(kw in text for kw in medical_keywords):
            return "medical"
        elif any(kw in text for kw in legal_keywords):
            return "legal"

        return None

    def _filter_new_components(
        self,
        components: List[DiscoveredComponent]
    ) -> List[DiscoveredComponent]:
        """Filter out already known components"""
        new_components = []

        for component in components:
            key = f"{component.component_type}:{component.component_id}"

            if key not in self._known_components:
                new_components.append(component)
                self._known_components.add(key)
            else:
                component.already_registered = True

        return new_components

    def mark_as_known(self, component_type: str, component_id: str):
        """Mark a component as known (already registered)"""
        key = f"{component_type}:{component_id}"
        self._known_components.add(key)

    def get_discovered(
        self,
        component_type: Optional[str] = None,
        domain: Optional[str] = None,
        source: Optional[DiscoverySource] = None
    ) -> List[DiscoveredComponent]:
        """Get discovered components with optional filters"""
        components = self._discovered

        if component_type:
            components = [c for c in components if c.component_type == component_type]

        if domain:
            components = [c for c in components if c.domain == domain]

        if source:
            components = [c for c in components if c.source == source]

        return components

    def get_top_discovered(
        self,
        limit: int = 10,
        sort_by: str = "downloads"
    ) -> List[DiscoveredComponent]:
        """Get top discovered components"""
        if sort_by == "downloads":
            return sorted(
                self._discovered,
                key=lambda c: c.downloads,
                reverse=True
            )[:limit]
        elif sort_by == "stars":
            return sorted(
                self._discovered,
                key=lambda c: c.stars,
                reverse=True
            )[:limit]
        elif sort_by == "recent":
            return sorted(
                self._discovered,
                key=lambda c: c.last_updated or datetime.min,
                reverse=True
            )[:limit]
        else:
            return self._discovered[:limit]

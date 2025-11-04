"""
USC (United States Code) Provider

Provides access to federal statutes from the US Code via the
Government Publishing Office (GPO) API.

API Documentation: https://api.govinfo.gov/docs/
"""
from typing import List, Optional, Dict, Any, AsyncIterator
from datetime import datetime
import aiohttp
import asyncio
import re

from knowledge_bases.base import (
    KnowledgeBaseProvider,
    KBEntity,
    KBMetadata,
    KBCapabilities,
    Relationship,
    RelationType
)
from logger import get_logger

logger = get_logger(__name__)


class USCProvider(KnowledgeBaseProvider):
    """
    United States Code knowledge base provider

    Provides access to:
    - Federal statutory law organized by subject matter
    - USC titles (1-54)
    - Statute sections and text
    - Citation resolution
    """

    # USC Titles
    USC_TITLES = {
        1: "General Provisions",
        2: "The Congress",
        3: "The President",
        4: "Flag and Seal, Seat of Government, and the States",
        5: "Government Organization and Employees",
        6: "Domestic Security",
        7: "Agriculture",
        8: "Aliens and Nationality",
        9: "Arbitration",
        10: "Armed Forces",
        11: "Bankruptcy",
        12: "Banks and Banking",
        13: "Census",
        14: "Coast Guard",
        15: "Commerce and Trade",
        16: "Conservation",
        17: "Copyrights",
        18: "Crimes and Criminal Procedure",
        19: "Customs Duties",
        20: "Education",
        21: "Food and Drugs",
        22: "Foreign Relations and Intercourse",
        23: "Highways",
        24: "Hospitals and Asylums",
        25: "Indians",
        26: "Internal Revenue Code",
        27: "Intoxicating Liquors",
        28: "Judiciary and Judicial Procedure",
        29: "Labor",
        30: "Mineral Lands and Mining",
        31: "Money and Finance",
        32: "National Guard",
        33: "Navigation and Navigable Waters",
        34: "Crime Control and Law Enforcement",
        35: "Patents",
        36: "Patriotic and National Observances",
        37: "Pay and Allowances of the Uniformed Services",
        38: "Veterans' Benefits",
        39: "Postal Service",
        40: "Public Buildings, Property, and Works",
        41: "Public Contracts",
        42: "The Public Health and Welfare",
        43: "Public Lands",
        44: "Public Printing and Documents",
        45: "Railroads",
        46: "Shipping",
        47: "Telecommunications",
        48: "Territories and Insular Possessions",
        49: "Transportation",
        50: "War and National Defense",
        51: "National and Commercial Space Programs",
        52: "Voting and Elections",
        54: "National Park Service and Related Programs"
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.api_key = config.get('api_key') if config else None
        self.base_url = "https://api.govinfo.gov"
        self.session: Optional[aiohttp.ClientSession] = None

    def get_kb_id(self) -> str:
        return "usc"

    def get_capabilities(self) -> KBCapabilities:
        return KBCapabilities(
            entity_types=["STATUTE", "USC_SECTION", "LEGAL_PROVISION"],
            supports_relationships=True,
            supports_semantic_types=False,
            supports_synonyms=False,
            supports_definitions=True,
            supports_hierarchies=True,
            update_frequency="annual",
            total_entities=50_000,  # Approximate
            languages=['en']
        )

    async def initialize(self) -> bool:
        """Initialize USC provider"""
        try:
            # Create HTTP session
            headers = {}
            if self.api_key:
                headers['X-Api-Key'] = self.api_key

            self.session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            )

            logger.info("USC provider initialized")
            return True

        except Exception as e:
            logger.error(f"Error initializing USC provider: {e}")
            return False

    async def stream_entities(
        self,
        entity_type: Optional[str] = None,
        batch_size: int = 1000,
        since: Optional[datetime] = None
    ) -> AsyncIterator[List[KBEntity]]:
        """
        Stream USC statutes

        Note: This is a simplified implementation. A full implementation
        would parse USC XML/JSON from GPO bulk data.
        """
        if not self.session:
            logger.error("USC provider not initialized")
            return

        try:
            # Stream sections for each title
            for title_num in self.USC_TITLES.keys():
                batch = []

                # Get sections for this title
                sections = await self._get_title_sections(title_num)

                for section in sections:
                    entity = await self._transform_statute(title_num, section)

                    if entity:
                        batch.append(entity)

                    if len(batch) >= batch_size:
                        yield batch
                        batch = []
                        await asyncio.sleep(0.1)

                if batch:
                    yield batch

        except Exception as e:
            logger.error(f"Error streaming USC entities: {e}")

    async def _get_title_sections(self, title: int) -> List[Dict[str, Any]]:
        """Get sections for a USC title"""
        # Note: This is a placeholder. Real implementation would query GPO API
        # or parse bulk data files from https://www.govinfo.gov/bulkdata/USCODE/
        return []

    async def lookup_entity(
        self,
        entity_text: str,
        entity_type: Optional[str] = None
    ) -> Optional[KBEntity]:
        """
        Lookup USC statute by citation

        Args:
            entity_text: Citation text (e.g., "18 U.S.C. § 1001")
            entity_type: Optional entity type filter

        Returns:
            KBEntity or None if not found
        """
        if not self.session:
            logger.error("USC provider not initialized")
            return None

        try:
            # Parse USC citation
            citation = self._parse_usc_citation(entity_text)

            if not citation:
                return None

            title = citation['title']
            section = citation['section']

            # Get statute details
            statute = await self._fetch_statute(title, section)

            if statute:
                return await self._transform_statute(title, statute)

            return None

        except Exception as e:
            logger.error(f"Error looking up USC entity: {e}")
            return None

    def _parse_usc_citation(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse USC citation from text

        Examples:
        - "18 U.S.C. § 1001"
        - "42 USC 1983"
        - "Title 18, Section 1001"
        """
        # Pattern 1: "18 U.S.C. § 1001"
        pattern1 = r'(\d+)\s+U\.?S\.?C\.?\s+§?\s*(\d+)([a-z])?'
        match = re.search(pattern1, text, re.IGNORECASE)

        if match:
            return {
                'title': int(match.group(1)),
                'section': match.group(2),
                'subsection': match.group(3)
            }

        # Pattern 2: "Title 18, Section 1001"
        pattern2 = r'Title\s+(\d+),?\s+Section\s+(\d+)'
        match = re.search(pattern2, text, re.IGNORECASE)

        if match:
            return {
                'title': int(match.group(1)),
                'section': match.group(2),
                'subsection': None
            }

        return None

    async def _fetch_statute(self, title: int, section: str) -> Optional[Dict[str, Any]]:
        """Fetch statute from GPO API"""
        try:
            # Search for the statute
            url = f"{self.base_url}/collections/USCODE/{title}/usc-{title}-{section}"

            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data

                elif response.status == 404:
                    logger.debug(f"Statute not found: Title {title}, Section {section}")
                    return None

                else:
                    logger.warning(f"GPO API returned {response.status}")
                    return None

        except Exception as e:
            logger.debug(f"Error fetching statute: {e}")
            return None

    async def _transform_statute(self, title: int, statute: Dict[str, Any]) -> Optional[KBEntity]:
        """Transform statute data to KBEntity"""
        try:
            section = statute.get('section', '')
            heading = statute.get('heading', '')

            entity_id = f"{title}-{section}"

            entity = KBEntity(
                kb_id="usc",
                entity_id=entity_id,
                entity_type="STATUTE",
                canonical_name=f"{title} U.S.C. § {section}",
                aliases=[
                    f"Title {title}, Section {section}",
                    f"{title} USC {section}"
                ],
                definition=heading,
                semantic_types=["FEDERAL_STATUTE"],
                relationships=[],
                metadata={
                    'title': title,
                    'title_name': self.USC_TITLES.get(title, ''),
                    'section': section,
                    'heading': heading,
                    'text': statute.get('text', ''),
                    'date': statute.get('date')
                },
                last_updated=datetime.now()
            )

            return entity

        except Exception as e:
            logger.error(f"Error transforming statute: {e}")
            return None

    async def get_relationships(self, entity_id: str) -> List[Relationship]:
        """Get relationships for a statute"""
        # USC statutes have hierarchical relationships
        # (title → chapter → section → subsection)
        relationships = []

        try:
            # Parse entity_id (format: "title-section")
            parts = entity_id.split('-')
            if len(parts) >= 2:
                title = int(parts[0])

                # Add relationship to title
                title_id = f"{title}"
                relationships.append(
                    Relationship(
                        source_id=entity_id,
                        target_id=title_id,
                        relation_type=RelationType.PART_OF,
                        confidence=1.0,
                        metadata={'relation': 'part_of_title'}
                    )
                )

            return relationships

        except Exception as e:
            logger.error(f"Error getting relationships: {e}")
            return []

    async def get_metadata(self, entity_id: str) -> Dict[str, Any]:
        """Get enrichment metadata for statute"""
        try:
            parts = entity_id.split('-')
            if len(parts) >= 2:
                title = int(parts[0])
                section = parts[1]

                statute = await self._fetch_statute(title, section)
                if statute:
                    return statute

            return {}

        except Exception as e:
            logger.error(f"Error getting metadata: {e}")
            return {}

    async def close(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()
            self.session = None


def get_usc_metadata() -> KBMetadata:
    """Get USC KB metadata"""
    capabilities = KBCapabilities(
        entity_types=["STATUTE", "USC_SECTION", "LEGAL_PROVISION"],
        supports_relationships=True,
        supports_semantic_types=False,
        supports_synonyms=False,
        supports_definitions=True,
        supports_hierarchies=True,
        update_frequency="annual",
        total_entities=50_000,
        languages=['en']
    )

    return KBMetadata(
        kb_id="usc",
        provider="USCProvider",
        version="2024",
        domain="legal",
        capabilities=capabilities,
        stream_url="https://api.govinfo.gov",
        api_key_required=False,  # API key is optional
        trusted=True,
        description="United States Code - federal statutory law",
        license="Public Domain",
        cache_strategy="moderate",
        sync_frequency="annual",
        created_at=datetime.now()
    )

"""
CourtListener Provider

Provides access to case law from CourtListener / Free Law Project,
a comprehensive database of legal opinions and documents.

API Documentation: https://www.courtlistener.com/api/rest-info/
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


class CourtListenerProvider(KnowledgeBaseProvider):
    """
    CourtListener knowledge base provider

    Provides access to:
    - Federal and state court opinions
    - Case citations
    - Court information
    - Judge information
    - Docket entries
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.api_key = config.get('api_key') if config else None
        self.base_url = "https://www.courtlistener.com/api/rest/v3"
        self.session: Optional[aiohttp.ClientSession] = None

    def get_kb_id(self) -> str:
        return "courtlistener"

    def get_capabilities(self) -> KBCapabilities:
        return KBCapabilities(
            entity_types=["CASE_CITATION", "OPINION", "COURT", "JUDGE"],
            supports_relationships=True,
            supports_semantic_types=False,
            supports_synonyms=True,
            supports_definitions=True,
            supports_hierarchies=False,
            update_frequency="daily",
            total_entities=10_000_000,  # Approximate
            languages=['en']
        )

    async def initialize(self) -> bool:
        """Initialize CourtListener provider"""
        try:
            # Create HTTP session
            headers = {}
            if self.api_key:
                headers['Authorization'] = f'Token {self.api_key}'

            self.session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            )

            # Test connection
            url = f"{self.base_url}/opinions/"
            params = {'page_size': 1}

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    logger.info("CourtListener provider initialized")
                    return True
                else:
                    logger.error(f"CourtListener connection test failed: {response.status}")
                    return False

        except Exception as e:
            logger.error(f"Error initializing CourtListener provider: {e}")
            return False

    async def stream_entities(
        self,
        entity_type: Optional[str] = None,
        batch_size: int = 100,
        since: Optional[datetime] = None
    ) -> AsyncIterator[List[KBEntity]]:
        """
        Stream case opinions from CourtListener

        Args:
            entity_type: Optional entity type filter
            batch_size: Number of entities per batch (max 100)
            since: Only stream opinions added/modified since this date
        """
        if not self.session:
            logger.error("CourtListener provider not initialized")
            return

        try:
            url = f"{self.base_url}/opinions/"
            page = 1

            params = {
                'page_size': min(batch_size, 100),  # API max is 100
                'ordering': '-date_created'
            }

            # Filter by date if provided
            if since:
                params['date_created__gte'] = since.isoformat()

            while True:
                params['page'] = page

                async with self.session.get(url, params=params) as response:
                    if response.status != 200:
                        logger.warning(f"CourtListener API returned {response.status}")
                        break

                    data = await response.json()
                    results = data.get('results', [])

                    if not results:
                        break

                    # Transform to KBEntity objects
                    entities = []
                    for result in results:
                        entity = await self._transform_opinion(result)
                        if entity:
                            entities.append(entity)

                    if entities:
                        yield entities

                    # Check if there are more pages
                    if not data.get('next'):
                        break

                    page += 1

                    # Rate limiting
                    await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Error streaming CourtListener entities: {e}")

    async def lookup_entity(
        self,
        entity_text: str,
        entity_type: Optional[str] = None
    ) -> Optional[KBEntity]:
        """
        Lookup case by citation

        Args:
            entity_text: Case citation (e.g., "347 U.S. 483" or "Brown v. Board of Education")
            entity_type: Optional entity type filter

        Returns:
            KBEntity or None if not found
        """
        if not self.session:
            logger.error("CourtListener provider not initialized")
            return None

        try:
            # Parse citation if it looks like one
            citation = self._parse_case_citation(entity_text)

            if citation:
                # Search by citation
                return await self._search_by_citation(citation)
            else:
                # Search by case name
                return await self._search_by_name(entity_text)

        except Exception as e:
            logger.error(f"Error looking up CourtListener entity: {e}")
            return None

    def _parse_case_citation(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse case citation from text

        Examples:
        - "347 U.S. 483"
        - "410 U.S. 113"
        - "539 F.3d 166"
        """
        # Pattern: "volume reporter page"
        pattern = r'(\d+)\s+([A-Za-z\.]+)\s+(\d+)'
        match = re.search(pattern, text)

        if match:
            return {
                'volume': match.group(1),
                'reporter': match.group(2),
                'page': match.group(3)
            }

        return None

    async def _search_by_citation(self, citation: Dict[str, Any]) -> Optional[KBEntity]:
        """Search for case by citation"""
        try:
            url = f"{self.base_url}/opinions/"
            params = {
                'cites': f"{citation['volume']} {citation['reporter']} {citation['page']}",
                'page_size': 1
            }

            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                results = data.get('results', [])

                if results:
                    return await self._transform_opinion(results[0])

                return None

        except Exception as e:
            logger.debug(f"Error searching by citation: {e}")
            return None

    async def _search_by_name(self, case_name: str) -> Optional[KBEntity]:
        """Search for case by name"""
        try:
            url = f"{self.base_url}/search/"
            params = {
                'q': case_name,
                'type': 'o',  # opinions
                'order_by': 'score desc',
                'page_size': 1
            }

            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                results = data.get('results', [])

                if results:
                    # Get opinion details
                    opinion_id = results[0].get('id')
                    return await self._get_opinion_details(opinion_id)

                return None

        except Exception as e:
            logger.debug(f"Error searching by name: {e}")
            return None

    async def _get_opinion_details(self, opinion_id: int) -> Optional[KBEntity]:
        """Get detailed opinion information"""
        try:
            url = f"{self.base_url}/opinions/{opinion_id}/"

            async with self.session.get(url) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                return await self._transform_opinion(data)

        except Exception as e:
            logger.error(f"Error getting opinion details: {e}")
            return None

    async def _transform_opinion(self, opinion: Dict[str, Any]) -> Optional[KBEntity]:
        """Transform opinion data to KBEntity"""
        try:
            opinion_id = opinion.get('id')
            case_name = opinion.get('case_name', '')

            if not opinion_id:
                return None

            # Get cluster info (contains citation)
            cluster_id = opinion.get('cluster')
            citation = ''
            court = ''

            if cluster_id:
                cluster = await self._get_cluster(cluster_id)
                if cluster:
                    citation = cluster.get('citation_string', '')
                    court = cluster.get('court', '')

            # Build aliases
            aliases = []
            if citation:
                aliases.append(citation)

            # Get case name variations
            case_name_short = opinion.get('case_name_short')
            if case_name_short and case_name_short != case_name:
                aliases.append(case_name_short)

            entity = KBEntity(
                kb_id="courtlistener",
                entity_id=str(opinion_id),
                entity_type="CASE_CITATION",
                canonical_name=case_name or citation,
                aliases=aliases,
                definition=self._extract_summary(opinion),
                semantic_types=["LEGAL_OPINION"],
                relationships=await self._get_opinion_relationships(opinion),
                metadata={
                    'opinion_id': opinion_id,
                    'citation': citation,
                    'court': court,
                    'date_filed': opinion.get('date_filed'),
                    'author': opinion.get('author_str'),
                    'type': opinion.get('type'),
                    'download_url': opinion.get('download_url'),
                    'local_path': opinion.get('local_path')
                },
                last_updated=datetime.now()
            )

            return entity

        except Exception as e:
            logger.error(f"Error transforming opinion: {e}")
            return None

    async def _get_cluster(self, cluster_id: int) -> Optional[Dict[str, Any]]:
        """Get opinion cluster information"""
        try:
            url = f"{self.base_url}/clusters/{cluster_id}/"

            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()

                return None

        except Exception as e:
            logger.debug(f"Error getting cluster: {e}")
            return None

    def _extract_summary(self, opinion: Dict[str, Any]) -> Optional[str]:
        """Extract case summary"""
        # Try various summary fields
        summary = (
            opinion.get('headnotes') or
            opinion.get('syllabus') or
            opinion.get('summary')
        )

        if summary and len(summary) > 500:
            summary = summary[:500] + '...'

        return summary

    async def _get_opinion_relationships(self, opinion: Dict[str, Any]) -> List[Relationship]:
        """Get relationships for an opinion"""
        relationships = []

        try:
            # Get cited cases
            opinion_id = opinion.get('id')

            if opinion_id:
                url = f"{self.base_url}/opinions/{opinion_id}/cited-by/"

                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        cited_by = data.get('results', [])

                        for cited in cited_by[:10]:  # Limit to 10
                            cited_id = cited.get('id')

                            if cited_id:
                                relationship = Relationship(
                                    source_id=str(opinion_id),
                                    target_id=str(cited_id),
                                    relation_type=RelationType.CITED_BY,
                                    confidence=1.0,
                                    metadata={'case_name': cited.get('case_name')}
                                )
                                relationships.append(relationship)

            return relationships

        except Exception as e:
            logger.debug(f"Error getting relationships: {e}")
            return []

    async def get_relationships(self, entity_id: str) -> List[Relationship]:
        """Get relationships for a case"""
        try:
            opinion_id = int(entity_id)
            url = f"{self.base_url}/opinions/{opinion_id}/"

            async with self.session.get(url) as response:
                if response.status == 200:
                    opinion = await response.json()
                    return await self._get_opinion_relationships(opinion)

                return []

        except Exception as e:
            logger.error(f"Error getting relationships: {e}")
            return []

    async def get_metadata(self, entity_id: str) -> Dict[str, Any]:
        """Get enrichment metadata for case"""
        try:
            opinion_id = int(entity_id)
            url = f"{self.base_url}/opinions/{opinion_id}/"

            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()

                return {}

        except Exception as e:
            logger.error(f"Error getting metadata: {e}")
            return {}

    async def close(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()
            self.session = None


def get_courtlistener_metadata() -> KBMetadata:
    """Get CourtListener KB metadata"""
    capabilities = KBCapabilities(
        entity_types=["CASE_CITATION", "OPINION", "COURT", "JUDGE"],
        supports_relationships=True,
        supports_semantic_types=False,
        supports_synonyms=True,
        supports_definitions=True,
        supports_hierarchies=False,
        update_frequency="daily",
        total_entities=10_000_000,
        languages=['en']
    )

    return KBMetadata(
        kb_id="courtlistener",
        provider="CourtListenerProvider",
        version="current",
        domain="legal",
        capabilities=capabilities,
        stream_url="https://www.courtlistener.com/api/rest/v3",
        api_key_required=True,  # Recommended for higher rate limits
        trusted=True,
        description="CourtListener - comprehensive case law database from Free Law Project",
        license="CC BY-NC-SA",
        cache_strategy="moderate",
        sync_frequency="weekly",
        created_at=datetime.now()
    )

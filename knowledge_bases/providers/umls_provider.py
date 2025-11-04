"""
UMLS (Unified Medical Language System) Provider

Provides access to the UMLS Metathesaurus, which integrates terminology
from multiple biomedical vocabularies.

API Documentation: https://documentation.uts.nlm.nih.gov/rest/home.html
"""
from typing import List, Optional, Dict, Any, AsyncIterator
from datetime import datetime
import aiohttp
import asyncio
from urllib.parse import urlencode

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


class UMLSProvider(KnowledgeBaseProvider):
    """
    UMLS knowledge base provider

    Provides access to:
    - Medical concepts (diseases, drugs, procedures, anatomy)
    - Semantic types and relationships
    - Multi-lingual support
    - Cross-vocabulary mappings
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.api_key = config.get('api_key') if config else None
        self.base_url = "https://uts-ws.nlm.nih.gov/rest"
        self.version = "current"
        self.session: Optional[aiohttp.ClientSession] = None
        self._ticket_granting_ticket = None
        self._service_ticket = None

    def get_kb_id(self) -> str:
        return "umls"

    def get_capabilities(self) -> KBCapabilities:
        return KBCapabilities(
            entity_types=[
                "DISEASE",
                "DRUG",
                "MEDICATION",
                "PROCEDURE",
                "ANATOMY",
                "CLINICAL_FINDING",
                "LABORATORY_TEST",
                "BODY_SUBSTANCE",
                "CHEMICAL"
            ],
            supports_relationships=True,
            supports_semantic_types=True,
            supports_synonyms=True,
            supports_definitions=True,
            supports_hierarchies=True,
            update_frequency="quarterly",
            total_entities=4_000_000,  # Approximate
            languages=['en', 'es', 'fr', 'de', 'it', 'ja', 'zh']
        )

    async def initialize(self) -> bool:
        """Initialize UMLS provider"""
        if not self.api_key:
            logger.error("UMLS API key not provided")
            return False

        try:
            # Create HTTP session
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )

            # Test authentication
            tgt = await self._get_ticket_granting_ticket()
            if tgt:
                logger.info("UMLS provider initialized successfully")
                return True
            else:
                logger.error("Failed to authenticate with UMLS API")
                return False

        except Exception as e:
            logger.error(f"Error initializing UMLS provider: {e}")
            return False

    async def _get_ticket_granting_ticket(self) -> Optional[str]:
        """Get Ticket Granting Ticket for authentication"""
        if self._ticket_granting_ticket:
            return self._ticket_granting_ticket

        try:
            auth_url = "https://utslogin.nlm.nih.gov/cas/v1/api-key"

            async with self.session.post(auth_url, data={'apikey': self.api_key}) as response:
                if response.status == 201:
                    # Extract TGT from Location header
                    location = response.headers.get('Location')
                    if location:
                        self._ticket_granting_ticket = location
                        return location
                else:
                    logger.error(f"Failed to get TGT: {response.status}")
                    return None

        except Exception as e:
            logger.error(f"Error getting TGT: {e}")
            return None

    async def _get_service_ticket(self) -> Optional[str]:
        """Get Service Ticket for API calls"""
        try:
            tgt = await self._get_ticket_granting_ticket()
            if not tgt:
                return None

            service = "http://umlsks.nlm.nih.gov"

            async with self.session.post(tgt, data={'service': service}) as response:
                if response.status == 200:
                    ticket = await response.text()
                    return ticket.strip()
                else:
                    logger.error(f"Failed to get service ticket: {response.status}")
                    return None

        except Exception as e:
            logger.error(f"Error getting service ticket: {e}")
            return None

    async def stream_entities(
        self,
        entity_type: Optional[str] = None,
        batch_size: int = 1000,
        since: Optional[datetime] = None
    ) -> AsyncIterator[List[KBEntity]]:
        """
        Stream UMLS concepts

        Note: UMLS doesn't provide direct streaming. This implementation
        searches by semantic type and paginates results.
        """
        if not self.session:
            logger.error("UMLS provider not initialized")
            return

        try:
            # Map entity type to UMLS semantic types
            semantic_types = self._get_semantic_types(entity_type)

            for sem_type in semantic_types:
                page = 1

                while True:
                    ticket = await self._get_service_ticket()
                    if not ticket:
                        break

                    # Search by semantic type
                    params = {
                        'ticket': ticket,
                        'pageNumber': page,
                        'pageSize': min(batch_size, 100),  # UMLS max is 100
                        'semanticType': sem_type
                    }

                    url = f"{self.base_url}/search/{self.version}"

                    async with self.session.get(url, params=params) as response:
                        if response.status != 200:
                            logger.warning(f"UMLS search failed: {response.status}")
                            break

                        data = await response.json()
                        results = data.get('result', {}).get('results', [])

                        if not results:
                            break

                        # Transform to KBEntity objects
                        entities = []
                        for result in results:
                            entity = await self._transform_concept(result)
                            if entity:
                                entities.append(entity)

                        if entities:
                            yield entities

                        page += 1

                        # Rate limiting
                        await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Error streaming UMLS entities: {e}")

    def _get_semantic_types(self, entity_type: Optional[str]) -> List[str]:
        """Map entity type to UMLS semantic types"""
        mapping = {
            "DISEASE": ["T047"],  # Disease or Syndrome
            "DRUG": ["T121", "T109"],  # Pharmacologic Substance, Organic Chemical
            "MEDICATION": ["T121"],
            "PROCEDURE": ["T061"],  # Therapeutic or Preventive Procedure
            "ANATOMY": ["T017", "T029"],  # Anatomical Structure, Body Location
            "CLINICAL_FINDING": ["T033"],  # Finding
            "LABORATORY_TEST": ["T059"],  # Laboratory Procedure
            "CHEMICAL": ["T103", "T109"],  # Chemical, Organic Chemical
        }

        if entity_type and entity_type in mapping:
            return mapping[entity_type]

        # Return common semantic types if no specific type
        return ["T047", "T121", "T061", "T033"]

    async def lookup_entity(
        self,
        entity_text: str,
        entity_type: Optional[str] = None
    ) -> Optional[KBEntity]:
        """
        Lookup entity in UMLS

        Args:
            entity_text: Entity text to search
            entity_type: Optional entity type filter

        Returns:
            KBEntity or None if not found
        """
        if not self.session:
            logger.error("UMLS provider not initialized")
            return None

        try:
            ticket = await self._get_service_ticket()
            if not ticket:
                return None

            # Search for exact match
            params = {
                'ticket': ticket,
                'string': entity_text,
                'searchType': 'exact',
                'returnIdType': 'concept'
            }

            url = f"{self.base_url}/search/{self.version}"

            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.warning(f"UMLS lookup failed: {response.status}")
                    return None

                data = await response.json()
                results = data.get('result', {}).get('results', [])

                if not results:
                    # Try approximate match
                    params['searchType'] = 'words'

                    async with self.session.get(url, params=params) as response2:
                        if response2.status == 200:
                            data2 = await response2.json()
                            results = data2.get('result', {}).get('results', [])

                if results:
                    # Return first matching result
                    return await self._transform_concept(results[0])

                return None

        except Exception as e:
            logger.error(f"Error looking up entity in UMLS: {e}")
            return None

    async def _transform_concept(self, result: Dict[str, Any]) -> Optional[KBEntity]:
        """Transform UMLS search result to KBEntity"""
        try:
            cui = result.get('ui')
            name = result.get('name')

            if not cui or not name:
                return None

            # Get additional concept details
            concept_details = await self._get_concept_details(cui)

            entity = KBEntity(
                kb_id="umls",
                entity_id=cui,
                entity_type=self._infer_entity_type(result),
                canonical_name=name,
                aliases=concept_details.get('aliases', []),
                definition=concept_details.get('definition'),
                semantic_types=concept_details.get('semantic_types', []),
                relationships=concept_details.get('relationships', []),
                metadata={
                    'source_vocabularies': concept_details.get('sources', []),
                    'root_source': result.get('rootSource'),
                    'uri': result.get('uri')
                },
                last_updated=datetime.now()
            )

            return entity

        except Exception as e:
            logger.error(f"Error transforming UMLS concept: {e}")
            return None

    async def _get_concept_details(self, cui: str) -> Dict[str, Any]:
        """Get detailed information about a concept"""
        details = {
            'aliases': [],
            'definition': None,
            'semantic_types': [],
            'relationships': [],
            'sources': []
        }

        try:
            ticket = await self._get_service_ticket()
            if not ticket:
                return details

            # Get concept details
            url = f"{self.base_url}/content/{self.version}/CUI/{cui}"
            params = {'ticket': ticket}

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    result = data.get('result', {})

                    # Extract semantic types
                    sem_types = result.get('semanticTypes', [])
                    details['semantic_types'] = [st.get('name') for st in sem_types]

                    # Get atoms (alternative names/aliases)
                    atoms = result.get('atoms', {}).get('result', [])
                    details['aliases'] = [atom.get('name') for atom in atoms if atom.get('name')]

                    # Get definitions
                    definitions = result.get('definitions', {}).get('result', [])
                    if definitions:
                        details['definition'] = definitions[0].get('value')

                    # Get source vocabularies
                    details['sources'] = result.get('sourceVocabularies', [])

            # Get relationships
            rel_url = f"{self.base_url}/content/{self.version}/CUI/{cui}/relations"

            async with self.session.get(rel_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    relations = data.get('result', [])

                    for rel in relations[:10]:  # Limit to first 10
                        rel_type = self._map_relation_type(rel.get('relationLabel', ''))
                        related_cui = rel.get('relatedId')

                        if rel_type and related_cui:
                            relationship = Relationship(
                                source_id=cui,
                                target_id=related_cui,
                                relation_type=rel_type,
                                confidence=1.0,
                                metadata={'label': rel.get('relationLabel')}
                            )
                            details['relationships'].append(relationship)

            return details

        except Exception as e:
            logger.error(f"Error getting concept details for {cui}: {e}")
            return details

    def _map_relation_type(self, umls_relation: str) -> Optional[RelationType]:
        """Map UMLS relation to RelationType"""
        mapping = {
            'RO': RelationType.IS_A,
            'CHD': RelationType.IS_A,
            'PAR': RelationType.IS_A,
            'RB': RelationType.RELATED_TO,
            'RN': RelationType.RELATED_TO,
            'SY': RelationType.SYNONYM,
            'may_treat': RelationType.TREATS,
            'may_prevent': RelationType.TREATS,
            'may_cause': RelationType.CAUSES,
        }

        return mapping.get(umls_relation)

    def _infer_entity_type(self, result: Dict[str, Any]) -> str:
        """Infer entity type from UMLS result"""
        # Could use semantic type here for more accurate classification
        return "MEDICAL_CONCEPT"

    async def get_relationships(self, entity_id: str) -> List[Relationship]:
        """Get relationships for a concept"""
        try:
            ticket = await self._get_service_ticket()
            if not ticket:
                return []

            url = f"{self.base_url}/content/{self.version}/CUI/{entity_id}/relations"
            params = {'ticket': ticket}

            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    return []

                data = await response.json()
                relations = data.get('result', [])

                relationships = []
                for rel in relations:
                    rel_type = self._map_relation_type(rel.get('relationLabel', ''))
                    related_cui = rel.get('relatedId')

                    if rel_type and related_cui:
                        relationship = Relationship(
                            source_id=entity_id,
                            target_id=related_cui,
                            relation_type=rel_type,
                            confidence=1.0,
                            metadata={
                                'label': rel.get('relationLabel'),
                                'source': rel.get('rootSource')
                            }
                        )
                        relationships.append(relationship)

                return relationships

        except Exception as e:
            logger.error(f"Error getting relationships for {entity_id}: {e}")
            return []

    async def get_metadata(self, entity_id: str) -> Dict[str, Any]:
        """Get enrichment metadata for entity"""
        details = await self._get_concept_details(entity_id)
        return details

    async def close(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()
            self.session = None


def get_umls_metadata() -> KBMetadata:
    """Get UMLS KB metadata"""
    capabilities = KBCapabilities(
        entity_types=[
            "DISEASE",
            "DRUG",
            "MEDICATION",
            "PROCEDURE",
            "ANATOMY",
            "CLINICAL_FINDING",
            "LABORATORY_TEST",
            "BODY_SUBSTANCE",
            "CHEMICAL"
        ],
        supports_relationships=True,
        supports_semantic_types=True,
        supports_synonyms=True,
        supports_definitions=True,
        supports_hierarchies=True,
        update_frequency="quarterly",
        total_entities=4_000_000,
        languages=['en', 'es', 'fr', 'de', 'it', 'ja', 'zh']
    )

    return KBMetadata(
        kb_id="umls",
        provider="UMLSProvider",
        version="2024AA",
        domain="medical",
        capabilities=capabilities,
        stream_url="https://uts-ws.nlm.nih.gov/rest",
        api_key_required=True,
        trusted=True,
        description="Unified Medical Language System - comprehensive medical terminology",
        license="UMLS Metathesaurus License",
        cache_strategy="aggressive",
        sync_frequency="quarterly",
        created_at=datetime.now()
    )

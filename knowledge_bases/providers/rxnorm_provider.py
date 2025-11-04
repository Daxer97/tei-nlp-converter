"""
RxNorm Provider

Provides access to RxNorm, a standardized nomenclature for clinical drugs
and drug delivery devices maintained by the NLM.

API Documentation: https://lhncbc.nlm.nih.gov/RxNav/APIs/
"""
from typing import List, Optional, Dict, Any, AsyncIterator
from datetime import datetime
import aiohttp
import asyncio

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


class RxNormProvider(KnowledgeBaseProvider):
    """
    RxNorm knowledge base provider

    Provides access to:
    - Standardized drug names
    - Drug ingredient information
    - Brand name to generic name mappings
    - Drug relationships (has_ingredient, has_dose_form, etc.)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = "https://rxnav.nlm.nih.gov/REST"
        self.session: Optional[aiohttp.ClientSession] = None

    def get_kb_id(self) -> str:
        return "rxnorm"

    def get_capabilities(self) -> KBCapabilities:
        return KBCapabilities(
            entity_types=["DRUG", "MEDICATION", "INGREDIENT", "BRAND_NAME"],
            supports_relationships=True,
            supports_semantic_types=False,
            supports_synonyms=True,
            supports_definitions=False,
            supports_hierarchies=True,
            update_frequency="monthly",
            total_entities=150_000,  # Approximate
            languages=['en']
        )

    async def initialize(self) -> bool:
        """Initialize RxNorm provider"""
        try:
            # Create HTTP session
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )

            # Test connection
            url = f"{self.base_url}/version.json"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    version = data.get('version')
                    logger.info(f"RxNorm provider initialized (version: {version})")
                    return True
                else:
                    logger.error(f"RxNorm connection test failed: {response.status}")
                    return False

        except Exception as e:
            logger.error(f"Error initializing RxNorm provider: {e}")
            return False

    async def stream_entities(
        self,
        entity_type: Optional[str] = None,
        batch_size: int = 1000,
        since: Optional[datetime] = None
    ) -> AsyncIterator[List[KBEntity]]:
        """
        Stream RxNorm concepts

        Note: RxNorm doesn't provide full streaming. This implementation
        retrieves all RxCUIs and fetches details in batches.
        """
        if not self.session:
            logger.error("RxNorm provider not initialized")
            return

        try:
            # Get all RxCUIs
            url = f"{self.base_url}/allconcepts.json"

            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to get RxNorm concepts: {response.status}")
                    return

                data = await response.json()
                concepts = data.get('minConceptGroup', {}).get('minConcept', [])

                if not concepts:
                    logger.warning("No RxNorm concepts found")
                    return

                # Process in batches
                batch = []

                for i, concept in enumerate(concepts):
                    rxcui = concept.get('rxcui')

                    if rxcui:
                        # Get concept details
                        entity = await self._get_concept_details(rxcui)

                        if entity:
                            batch.append(entity)

                    # Yield batch when full
                    if len(batch) >= batch_size:
                        yield batch
                        batch = []

                        # Rate limiting
                        await asyncio.sleep(0.5)

                # Yield remaining
                if batch:
                    yield batch

        except Exception as e:
            logger.error(f"Error streaming RxNorm entities: {e}")

    async def lookup_entity(
        self,
        entity_text: str,
        entity_type: Optional[str] = None
    ) -> Optional[KBEntity]:
        """
        Lookup drug in RxNorm

        Args:
            entity_text: Drug name to search
            entity_type: Optional entity type filter

        Returns:
            KBEntity or None if not found
        """
        if not self.session:
            logger.error("RxNorm provider not initialized")
            return None

        try:
            # Search for drug by name
            url = f"{self.base_url}/rxcui.json"
            params = {'name': entity_text, 'search': '1'}

            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.warning(f"RxNorm lookup failed: {response.status}")
                    return None

                data = await response.json()
                id_group = data.get('idGroup', {})
                rxcui_list = id_group.get('rxnormId')

                if not rxcui_list:
                    # Try approximate match
                    url = f"{self.base_url}/approximateTerm.json"
                    params = {'term': entity_text}

                    async with self.session.get(url, params=params) as response2:
                        if response2.status == 200:
                            data2 = await response2.json()
                            candidates = data2.get('approximateGroup', {}).get('candidate', [])

                            if candidates:
                                # Get first match
                                rxcui_list = [candidates[0].get('rxcui')]

                if rxcui_list:
                    rxcui = rxcui_list[0]
                    return await self._get_concept_details(rxcui)

                return None

        except Exception as e:
            logger.error(f"Error looking up entity in RxNorm: {e}")
            return None

    async def _get_concept_details(self, rxcui: str) -> Optional[KBEntity]:
        """Get detailed information about an RxNorm concept"""
        try:
            # Get concept properties
            url = f"{self.base_url}/rxcui/{rxcui}/properties.json"

            async with self.session.get(url) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                properties = data.get('properties', {})

                name = properties.get('name')
                if not name:
                    return None

                # Get synonyms
                aliases = await self._get_synonyms(rxcui)

                # Get relationships
                relationships = await self._get_relationships(rxcui)

                # Determine entity type
                tty = properties.get('tty', '')
                entity_type = self._map_term_type(tty)

                entity = KBEntity(
                    kb_id="rxnorm",
                    entity_id=rxcui,
                    entity_type=entity_type,
                    canonical_name=name,
                    aliases=aliases,
                    definition=None,  # RxNorm doesn't provide definitions
                    semantic_types=[tty],  # Use term type as semantic type
                    relationships=relationships,
                    metadata={
                        'term_type': tty,
                        'suppress': properties.get('suppress'),
                        'umlscui': properties.get('umlscui')
                    },
                    last_updated=datetime.now()
                )

                return entity

        except Exception as e:
            logger.error(f"Error getting RxNorm concept details for {rxcui}: {e}")
            return None

    async def _get_synonyms(self, rxcui: str) -> List[str]:
        """Get synonyms for an RxNorm concept"""
        try:
            url = f"{self.base_url}/rxcui/{rxcui}/allrelated.json"

            async with self.session.get(url) as response:
                if response.status != 200:
                    return []

                data = await response.json()
                related_group = data.get('allRelatedGroup', {})
                concept_groups = related_group.get('conceptGroup', [])

                aliases = set()

                for group in concept_groups:
                    concepts = group.get('conceptProperties', [])
                    for concept in concepts:
                        name = concept.get('name')
                        if name:
                            aliases.add(name)

                return list(aliases)

        except Exception as e:
            logger.debug(f"Error getting synonyms for {rxcui}: {e}")
            return []

    async def _get_relationships(self, rxcui: str) -> List[Relationship]:
        """Get relationships for an RxNorm concept"""
        relationships = []

        try:
            # Get related concepts by relation type
            url = f"{self.base_url}/rxcui/{rxcui}/related.json"
            params = {'rela': 'has_ingredient+ingredient_of+has_dose_form+has_tradename'}

            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    return []

                data = await response.json()
                related_group = data.get('relatedGroup', {})
                concept_groups = related_group.get('conceptGroup', [])

                for group in concept_groups:
                    relation_type_str = group.get('tty', '')
                    concepts = group.get('conceptProperties', [])

                    for concept in concepts:
                        related_rxcui = concept.get('rxcui')

                        if related_rxcui:
                            rel_type = self._map_rxnorm_relation(relation_type_str)

                            if rel_type:
                                relationship = Relationship(
                                    source_id=rxcui,
                                    target_id=related_rxcui,
                                    relation_type=rel_type,
                                    confidence=1.0,
                                    metadata={
                                        'relation': relation_type_str,
                                        'name': concept.get('name')
                                    }
                                )
                                relationships.append(relationship)

            return relationships

        except Exception as e:
            logger.debug(f"Error getting relationships for {rxcui}: {e}")
            return []

    def _map_term_type(self, tty: str) -> str:
        """Map RxNorm term type to entity type"""
        mapping = {
            'SCD': 'DRUG',  # Semantic Clinical Drug
            'SBD': 'DRUG',  # Semantic Branded Drug
            'GPCK': 'DRUG',  # Generic Pack
            'BPCK': 'DRUG',  # Brand Name Pack
            'IN': 'INGREDIENT',  # Ingredient
            'PIN': 'INGREDIENT',  # Precise Ingredient
            'MIN': 'INGREDIENT',  # Multiple Ingredients
            'BN': 'BRAND_NAME',  # Brand Name
        }

        return mapping.get(tty, 'DRUG')

    def _map_rxnorm_relation(self, relation: str) -> Optional[RelationType]:
        """Map RxNorm relation to RelationType"""
        mapping = {
            'has_ingredient': RelationType.PART_OF,
            'ingredient_of': RelationType.PART_OF,
            'has_dose_form': RelationType.RELATED_TO,
            'has_tradename': RelationType.SYNONYM,
            'tradename_of': RelationType.SYNONYM,
        }

        return mapping.get(relation.lower())

    async def get_relationships(self, entity_id: str) -> List[Relationship]:
        """Get relationships for a drug"""
        return await self._get_relationships(entity_id)

    async def get_metadata(self, entity_id: str) -> Dict[str, Any]:
        """Get enrichment metadata for entity"""
        try:
            url = f"{self.base_url}/rxcui/{entity_id}/properties.json"

            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('properties', {})

                return {}

        except Exception as e:
            logger.error(f"Error getting metadata for {entity_id}: {e}")
            return {}

    async def close(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()
            self.session = None


def get_rxnorm_metadata() -> KBMetadata:
    """Get RxNorm KB metadata"""
    capabilities = KBCapabilities(
        entity_types=["DRUG", "MEDICATION", "INGREDIENT", "BRAND_NAME"],
        supports_relationships=True,
        supports_semantic_types=False,
        supports_synonyms=True,
        supports_definitions=False,
        supports_hierarchies=True,
        update_frequency="monthly",
        total_entities=150_000,
        languages=['en']
    )

    return KBMetadata(
        kb_id="rxnorm",
        provider="RxNormProvider",
        version="current",
        domain="medical",
        capabilities=capabilities,
        stream_url="https://rxnav.nlm.nih.gov/REST",
        api_key_required=False,
        trusted=True,
        description="RxNorm - standardized nomenclature for clinical drugs",
        license="Public Domain",
        cache_strategy="aggressive",
        sync_frequency="monthly",
        created_at=datetime.now()
    )

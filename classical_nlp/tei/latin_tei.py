"""
Latin TEI Generator

Specialized TEI generation for Latin texts with:
- Botanical annotations for Virgil project
- Morphological markup (case, number, gender, etc.)
- Support for poetic texts
"""

from typing import Dict, List, Any, Optional
import xml.etree.ElementTree as ET
from datetime import datetime
import logging

from .base import ClassicalTEIGenerator, TEI_NS, XML_NS

logger = logging.getLogger(__name__)


class LatinTEIGenerator(ClassicalTEIGenerator):
    """
    TEI Generator for Latin texts.

    Optimized for:
    - Virgil's works (Georgics, Aeneid, etc.)
    - Botanical texts
    - Poetic and prose texts

    Features:
    - Botanical term annotations with scientific names
    - Rich morphological markup
    - Metrical analysis support (if available)
    """

    @property
    def language_code(self) -> str:
        return "la"

    @property
    def language_name(self) -> str:
        return "Latino"

    def generate(self, nlp_result: Dict[str, Any]) -> str:
        """
        Generate TEI XML for Latin text.

        Args:
            nlp_result: Dictionary with NLP processing results including:
                - text: Original text
                - sentences: List of sentence dictionaries
                - entities: List of entity dictionaries
                - botanical_terms: List of botanical term dictionaries

        Returns:
            TEI XML string
        """
        try:
            # Create root
            root = self._create_root()

            # Create header
            model_used = nlp_result.get('model_used', 'Unknown')
            header = self._create_latin_header(nlp_result, model_used)
            root.append(header)

            # Create text body
            text_elem = ET.SubElement(root, f'{{{TEI_NS}}}text')
            text_elem.set(f'{{{XML_NS}}}lang', 'la')

            body = ET.SubElement(text_elem, f'{{{TEI_NS}}}body')

            # Add annotated content
            self._add_body_content(body, nlp_result)

            # Add back matter with botanical index
            botanical_terms = nlp_result.get('botanical_terms', [])
            if botanical_terms:
                back = self._create_botanical_index(botanical_terms)
                text_elem.append(back)

            # Convert to string
            xml_str = ET.tostring(root, encoding='unicode', method='xml')
            return self._prettify_xml(xml_str)

        except Exception as e:
            logger.error(f"Failed to generate Latin TEI: {e}")
            return self._create_fallback_tei(nlp_result.get('text', ''), str(e))

    def _create_latin_header(
        self,
        nlp_result: Dict[str, Any],
        model_used: str
    ) -> ET.Element:
        """Create Latin-specific TEI header."""
        header = self._create_header(nlp_result, model_used)

        # Get profileDesc element
        profile_desc = header.find(f'.//{{{TEI_NS}}}profileDesc')

        if profile_desc is not None:
            # Add textClass with botanical classification
            text_class = ET.SubElement(profile_desc, f'{{{TEI_NS}}}textClass')

            # Add keywords for botanical project
            keywords = ET.SubElement(text_class, f'{{{TEI_NS}}}keywords')
            keywords.set('scheme', 'botanical')

            # Add botanical terms as keywords
            botanical_terms = nlp_result.get('botanical_terms', [])
            for bt in botanical_terms[:10]:  # Limit to top 10
                term = ET.SubElement(keywords, f'{{{TEI_NS}}}term')
                if isinstance(bt, dict):
                    term.text = bt.get('lemma', bt.get('text', ''))
                else:
                    term.text = getattr(bt, 'lemma', str(bt))

        # Enhance encoding description
        encoding_desc = header.find(f'.//{{{TEI_NS}}}encodingDesc')

        if encoding_desc is not None:
            # Add project description
            project_desc = ET.SubElement(encoding_desc, f'{{{TEI_NS}}}projectDesc')
            p = ET.SubElement(project_desc, f'{{{TEI_NS}}}p')
            p.text = "Progetto Botanica-Virgilio: Analisi NLP per identificazione termini botanici nei testi latini classici"

        return header

    def _add_body_content(self, body: ET.Element, nlp_result: Dict[str, Any]):
        """Add annotated content to body."""
        sentences = nlp_result.get('sentences', [])

        if not sentences:
            # Fallback: create single paragraph
            p = ET.SubElement(body, f'{{{TEI_NS}}}p')
            p.text = nlp_result.get('text', '')
            return

        # Create main division
        div = ET.SubElement(body, f'{{{TEI_NS}}}div')
        div.set('type', 'section')
        div.set('n', '1')

        # Build botanical term lookup
        botanical_lookup = self._build_botanical_lookup(nlp_result.get('botanical_terms', []))

        # Process each sentence
        for sent_idx, sentence in enumerate(sentences):
            self._add_sentence(div, sentence, sent_idx, botanical_lookup)

    def _build_botanical_lookup(self, botanical_terms: List[Any]) -> Dict[str, Dict[str, Any]]:
        """Build lookup table for botanical terms."""
        lookup = {}

        for bt in botanical_terms:
            if isinstance(bt, dict):
                lemma = bt.get('lemma', '').lower()
                lookup[lemma] = bt
            else:
                lemma = getattr(bt, 'lemma', '').lower()
                lookup[lemma] = {
                    'lemma': lemma,
                    'scientific_name': getattr(bt, 'scientific_name', None),
                    'common_name': getattr(bt, 'common_name', None)
                }

        return lookup

    def _add_sentence(
        self,
        parent: ET.Element,
        sentence: Dict[str, Any],
        sent_idx: int,
        botanical_lookup: Dict[str, Dict[str, Any]]
    ):
        """Add a sentence element with token annotations."""
        # Create sentence element
        s_elem = ET.SubElement(parent, f'{{{TEI_NS}}}s')
        s_elem.set(f'{{{XML_NS}}}id', f's{sent_idx + 1}')
        s_elem.set('n', str(sent_idx + 1))

        tokens = sentence.get('tokens', [])

        for token in tokens:
            if token.get('is_space'):
                continue

            lemma_lower = token.get('lemma', '').lower()

            # Check if this is a botanical term
            if lemma_lower in botanical_lookup:
                bt_info = botanical_lookup[lemma_lower]
                self._add_botanical_word(s_elem, token, bt_info)
            else:
                # Regular word
                w_elem = self._create_word_element(token)
                s_elem.append(w_elem)

    def _add_botanical_word(
        self,
        parent: ET.Element,
        token: Dict[str, Any],
        bt_info: Dict[str, Any]
    ):
        """Add a botanical term with special markup."""
        # Create name element for botanical term
        name_elem = ET.Element(f'{{{TEI_NS}}}name')
        name_elem.set('type', 'plant')

        # Add reference to botanical database if scientific name available
        if bt_info.get('scientific_name'):
            name_elem.set('ref', f'#plant-{bt_info.get("lemma", "unknown")}')

        # Add the word element inside the name element
        w_elem = self._create_word_element(token)
        name_elem.append(w_elem)

        # Add tail for spacing
        name_elem.tail = ' '

        parent.append(name_elem)

    def _create_botanical_index(self, botanical_terms: List[Any]) -> ET.Element:
        """
        Create back matter with botanical index.

        Args:
            botanical_terms: List of botanical terms found in text

        Returns:
            <back> element with botanical index
        """
        back = ET.Element(f'{{{TEI_NS}}}back')

        div = ET.SubElement(back, f'{{{TEI_NS}}}div')
        div.set('type', 'botanical-index')

        # Add heading
        head = ET.SubElement(div, f'{{{TEI_NS}}}head')
        head.text = 'Indice Botanico'

        # Create list of plants
        list_elem = ET.SubElement(div, f'{{{TEI_NS}}}list')
        list_elem.set('type', 'plants')

        # Sort terms by lemma
        sorted_terms = sorted(
            botanical_terms,
            key=lambda x: (x.get('lemma', '') if isinstance(x, dict) else getattr(x, 'lemma', ''))
        )

        for idx, bt in enumerate(sorted_terms, 1):
            if isinstance(bt, dict):
                lemma = bt.get('lemma', '')
                scientific = bt.get('scientific_name', '')
                common = bt.get('common_name', '')
                occurrences = bt.get('occurrences', 1)
                positions = bt.get('positions', [])
            else:
                lemma = getattr(bt, 'lemma', '')
                scientific = getattr(bt, 'scientific_name', '')
                common = getattr(bt, 'common_name', '')
                occurrences = getattr(bt, 'occurrences', 1)
                positions = getattr(bt, 'positions', [])

            item = ET.SubElement(list_elem, f'{{{TEI_NS}}}item')
            item.set(f'{{{XML_NS}}}id', f'plant-{lemma}')

            # Add term
            term = ET.SubElement(item, f'{{{TEI_NS}}}term')
            term.text = lemma

            # Add gloss with scientific and common names
            if scientific or common:
                gloss = ET.SubElement(item, f'{{{TEI_NS}}}gloss')
                parts = []
                if common:
                    parts.append(common)
                if scientific:
                    parts.append(f"({scientific})")
                gloss.text = ' - '.join(parts) if parts else lemma

            # Add occurrence count
            note_occ = ET.SubElement(item, f'{{{TEI_NS}}}note')
            note_occ.set('type', 'occurrences')
            note_occ.text = str(occurrences)

            # Add positions
            if positions:
                note_pos = ET.SubElement(item, f'{{{TEI_NS}}}note')
                note_pos.set('type', 'positions')
                note_pos.text = ', '.join(str(p) for p in positions[:10])  # Limit positions

        return back

    def _create_fallback_tei(self, text: str, error: str) -> str:
        """Create minimal valid TEI on error."""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="la">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Testo Latino Processato</title>
      </titleStmt>
      <publicationStmt>
        <p>Generato da TEI NLP Converter (modalità fallback)</p>
      </publicationStmt>
      <sourceDesc>
        <p>Errore durante elaborazione: {self._escape_xml(error)}</p>
      </sourceDesc>
    </fileDesc>
    <profileDesc>
      <langUsage>
        <language ident="la">Latino</language>
      </langUsage>
    </profileDesc>
  </teiHeader>
  <text xml:lang="la">
    <body>
      <p>{self._escape_xml(text)}</p>
    </body>
  </text>
</TEI>"""

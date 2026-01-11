"""
Ancient Greek TEI Generator

Specialized TEI generation for Ancient Greek texts with:
- Dialect annotations (Attic, Ionic, Doric, etc.)
- Morphological markup with Greek-specific features
- Support for polytonic Greek
"""

from typing import Dict, List, Any, Optional
import xml.etree.ElementTree as ET
from datetime import datetime
import logging

from .base import ClassicalTEIGenerator, TEI_NS, XML_NS

logger = logging.getLogger(__name__)


class GreekTEIGenerator(ClassicalTEIGenerator):
    """
    TEI Generator for Ancient Greek texts.

    Optimized for:
    - Homeric Greek
    - Attic Greek (Classical period)
    - Hellenistic Greek

    Features:
    - Dialect variation annotations
    - Polytonic Greek support
    - Morphological features specific to Greek
    """

    @property
    def language_code(self) -> str:
        return "grc"

    @property
    def language_name(self) -> str:
        return "Greco Antico"

    def generate(self, nlp_result: Dict[str, Any]) -> str:
        """
        Generate TEI XML for Ancient Greek text.

        Args:
            nlp_result: Dictionary with NLP processing results

        Returns:
            TEI XML string
        """
        try:
            # Create root
            root = self._create_root()

            # Create header
            model_used = nlp_result.get('model_used', 'Unknown')
            header = self._create_greek_header(nlp_result, model_used)
            root.append(header)

            # Create text body
            text_elem = ET.SubElement(root, f'{{{TEI_NS}}}text')
            text_elem.set(f'{{{XML_NS}}}lang', 'grc')

            body = ET.SubElement(text_elem, f'{{{TEI_NS}}}body')

            # Add annotated content
            self._add_body_content(body, nlp_result)

            # Add botanical index if present
            botanical_terms = nlp_result.get('botanical_terms', [])
            if botanical_terms:
                back = self._create_botanical_index(botanical_terms)
                text_elem.append(back)

            # Convert to string
            xml_str = ET.tostring(root, encoding='unicode', method='xml')
            return self._prettify_xml(xml_str)

        except Exception as e:
            logger.error(f"Failed to generate Greek TEI: {e}")
            return self._create_fallback_tei(nlp_result.get('text', ''), str(e))

    def _create_greek_header(
        self,
        nlp_result: Dict[str, Any],
        model_used: str
    ) -> ET.Element:
        """Create Greek-specific TEI header."""
        header = self._create_header(nlp_result, model_used)

        # Get or create encodingDesc
        encoding_desc = header.find(f'.//{{{TEI_NS}}}encodingDesc')

        if encoding_desc is not None:
            # Add Greek-specific classification declaration
            class_decl = encoding_desc.find(f'.//{{{TEI_NS}}}classDecl')

            if class_decl is None:
                class_decl = ET.SubElement(encoding_desc, f'{{{TEI_NS}}}classDecl')

            # Add Greek NLP taxonomy
            taxonomy = ET.SubElement(class_decl, f'{{{TEI_NS}}}taxonomy')
            taxonomy.set(f'{{{XML_NS}}}id', 'nlp-grc')

            categories = [
                ('lemma', 'Lemma', 'Forma del dizionario'),
                ('pos', 'Part of Speech', 'Categoria grammaticale'),
                ('morph', 'Morfologia', 'Caratteristiche morfologiche (caso, numero, genere, tempo, modo)'),
                ('dialect', 'Dialetto', 'Variante dialettale (attico, ionico, dorico, eolico)')
            ]

            for cat_id, cat_name, cat_desc in categories:
                category = ET.SubElement(taxonomy, f'{{{TEI_NS}}}category')
                category.set(f'{{{XML_NS}}}id', cat_id)
                cat_desc_elem = ET.SubElement(category, f'{{{TEI_NS}}}catDesc')
                cat_desc_elem.text = f"{cat_name}: {cat_desc}"

        return header

    def _add_body_content(self, body: ET.Element, nlp_result: Dict[str, Any]):
        """Add annotated content to body."""
        sentences = nlp_result.get('sentences', [])

        if not sentences:
            p = ET.SubElement(body, f'{{{TEI_NS}}}p')
            p.text = nlp_result.get('text', '')
            return

        # Create main division
        div = ET.SubElement(body, f'{{{TEI_NS}}}div')
        div.set('type', 'section')

        # Build botanical lookup
        botanical_lookup = self._build_botanical_lookup(nlp_result.get('botanical_terms', []))

        for sent_idx, sentence in enumerate(sentences):
            self._add_sentence(div, sentence, sent_idx, botanical_lookup)

    def _build_botanical_lookup(self, botanical_terms: List[Any]) -> Dict[str, Dict[str, Any]]:
        """Build lookup table for botanical terms."""
        lookup = {}

        for bt in botanical_terms:
            if isinstance(bt, dict):
                lemma = bt.get('lemma', '')
                lookup[lemma] = bt
            else:
                lemma = getattr(bt, 'lemma', '')
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
        """Add a sentence element with Greek-specific annotations."""
        s_elem = ET.SubElement(parent, f'{{{TEI_NS}}}s')
        s_elem.set(f'{{{XML_NS}}}id', f's{sent_idx + 1}')
        s_elem.set('n', str(sent_idx + 1))

        tokens = sentence.get('tokens', [])

        for token in tokens:
            if token.get('is_space'):
                continue

            lemma = token.get('lemma', '')

            # Check for botanical term
            if lemma in botanical_lookup:
                bt_info = botanical_lookup[lemma]
                self._add_botanical_word(s_elem, token, bt_info)
            else:
                # Regular word with Greek-specific attributes
                w_elem = self._create_greek_word_element(token)
                s_elem.append(w_elem)

    def _create_greek_word_element(self, token: Dict[str, Any]) -> ET.Element:
        """Create a word element with Greek-specific annotations."""
        if token.get('is_punct'):
            elem = ET.Element(f'{{{TEI_NS}}}pc')
        else:
            elem = ET.Element(f'{{{TEI_NS}}}w')

            # Add lemma
            if self.config.get('include_lemma', True) and token.get('lemma'):
                elem.set('lemma', token['lemma'])

            # Add POS
            if self.config.get('include_pos', True) and token.get('pos'):
                elem.set('pos', token['pos'])

            # Add morphology with Greek features
            if self.config.get('include_morph', True) and token.get('morph'):
                elem.set('msd', token['morph'])

            # Add dialect annotation if available
            if token.get('dialect') and token['dialect'] != 'unknown':
                elem.set('dialect', token['dialect'])

        elem.set(f'{{{XML_NS}}}id', f'w{token.get("i", 0) + 1}')
        elem.text = token['text']

        if token.get('whitespace_', ' ') == ' ':
            elem.tail = ' '

        return elem

    def _add_botanical_word(
        self,
        parent: ET.Element,
        token: Dict[str, Any],
        bt_info: Dict[str, Any]
    ):
        """Add a botanical term with special markup."""
        name_elem = ET.Element(f'{{{TEI_NS}}}name')
        name_elem.set('type', 'plant')

        if bt_info.get('scientific_name'):
            name_elem.set('ref', '#botanical-db')

        w_elem = self._create_greek_word_element(token)
        name_elem.append(w_elem)
        name_elem.tail = ' '

        parent.append(name_elem)

    def _create_botanical_index(self, botanical_terms: List[Any]) -> ET.Element:
        """Create back matter with botanical index for Greek texts."""
        back = ET.Element(f'{{{TEI_NS}}}back')

        div = ET.SubElement(back, f'{{{TEI_NS}}}div')
        div.set('type', 'botanical-index')

        head = ET.SubElement(div, f'{{{TEI_NS}}}head')
        head.text = 'Βοτανικὸς Κατάλογος'  # "Botanical Index" in Greek

        list_elem = ET.SubElement(div, f'{{{TEI_NS}}}list')
        list_elem.set('type', 'plants')

        for idx, bt in enumerate(botanical_terms, 1):
            if isinstance(bt, dict):
                lemma = bt.get('lemma', '')
                scientific = bt.get('scientific_name', '')
                common = bt.get('common_name', '')
                occurrences = bt.get('occurrences', 1)
            else:
                lemma = getattr(bt, 'lemma', '')
                scientific = getattr(bt, 'scientific_name', '')
                common = getattr(bt, 'common_name', '')
                occurrences = getattr(bt, 'occurrences', 1)

            item = ET.SubElement(list_elem, f'{{{TEI_NS}}}item')
            item.set(f'{{{XML_NS}}}id', f'plant-{idx}')

            term = ET.SubElement(item, f'{{{TEI_NS}}}term')
            term.text = lemma

            if scientific or common:
                gloss = ET.SubElement(item, f'{{{TEI_NS}}}gloss')
                parts = []
                if common:
                    parts.append(common)
                if scientific:
                    parts.append(f"({scientific})")
                gloss.text = ' - '.join(parts) if parts else lemma

            note_occ = ET.SubElement(item, f'{{{TEI_NS}}}note')
            note_occ.set('type', 'occurrences')
            note_occ.text = str(occurrences)

        return back

    def _create_fallback_tei(self, text: str, error: str) -> str:
        """Create minimal valid TEI on error."""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="grc">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Κείμενον Ἑλληνικόν</title>
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
        <language ident="grc">Greco Antico</language>
      </langUsage>
    </profileDesc>
  </teiHeader>
  <text xml:lang="grc">
    <body>
      <p>{self._escape_xml(text)}</p>
    </body>
  </text>
</TEI>"""

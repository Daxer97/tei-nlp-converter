"""
Base TEI Generator for Classical Languages

Provides the abstract interface and common functionality for
generating TEI XML from classical NLP processing results.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime
import xml.etree.ElementTree as ET
from defusedxml.minidom import parseString
import logging

logger = logging.getLogger(__name__)

# TEI namespace
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"


class ClassicalTEIGenerator(ABC):
    """
    Abstract base class for classical language TEI generators.

    Generates TEI XML with appropriate structure for classical texts,
    including support for:
    - Linguistic annotations (lemma, POS, morphology)
    - Named entities
    - Domain-specific annotations (botanical terms, etc.)
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the TEI generator.

        Args:
            config: Configuration dictionary with options like:
                - title: Document title
                - author: Document author
                - include_lemma: Include lemma annotations
                - include_pos: Include POS annotations
                - include_morph: Include morphological annotations
                - annotation_strategy: 'inline', 'standoff', or 'mixed'
        """
        self.config = config or {}

        # Register namespaces
        ET.register_namespace('', TEI_NS)
        ET.register_namespace('xml', XML_NS)

    @property
    @abstractmethod
    def language_code(self) -> str:
        """Get the ISO language code for this generator."""
        pass

    @property
    @abstractmethod
    def language_name(self) -> str:
        """Get the human-readable language name."""
        pass

    @abstractmethod
    def generate(self, nlp_result: Dict[str, Any]) -> str:
        """
        Generate TEI XML from NLP processing results.

        Args:
            nlp_result: Dictionary with NLP processing results

        Returns:
            TEI XML string
        """
        pass

    def _create_root(self) -> ET.Element:
        """Create the root TEI element."""
        root = ET.Element(f'{{{TEI_NS}}}TEI')
        root.set('version', '5.0')
        root.set(f'{{{XML_NS}}}lang', self.language_code)
        return root

    def _create_header(
        self,
        nlp_result: Dict[str, Any],
        model_used: str = "Unknown"
    ) -> ET.Element:
        """
        Create the TEI header with metadata.

        Args:
            nlp_result: NLP processing results
            model_used: Name of the NLP model used

        Returns:
            teiHeader element
        """
        header = ET.Element(f'{{{TEI_NS}}}teiHeader')

        # File description
        file_desc = ET.SubElement(header, f'{{{TEI_NS}}}fileDesc')

        # Title statement
        title_stmt = ET.SubElement(file_desc, f'{{{TEI_NS}}}titleStmt')
        title = ET.SubElement(title_stmt, f'{{{TEI_NS}}}title')
        title.text = self.config.get('title', 'Processed Classical Text')

        if self.config.get('author'):
            author = ET.SubElement(title_stmt, f'{{{TEI_NS}}}author')
            author.text = self.config['author']

        # Responsibility statement
        resp_stmt = ET.SubElement(title_stmt, f'{{{TEI_NS}}}respStmt')
        resp = ET.SubElement(resp_stmt, f'{{{TEI_NS}}}resp')
        resp.text = 'NLP Processing and TEI Encoding'
        name = ET.SubElement(resp_stmt, f'{{{TEI_NS}}}name')
        name.text = 'Classical NLP System'

        # Publication statement
        pub_stmt = ET.SubElement(file_desc, f'{{{TEI_NS}}}publicationStmt')
        publisher = ET.SubElement(pub_stmt, f'{{{TEI_NS}}}publisher')
        publisher.text = 'TEI NLP Converter - Classical Languages'
        pub_date = ET.SubElement(pub_stmt, f'{{{TEI_NS}}}date')
        pub_date.set('when', datetime.now().isoformat())

        # Source description
        source_desc = ET.SubElement(file_desc, f'{{{TEI_NS}}}sourceDesc')
        p = ET.SubElement(source_desc, f'{{{TEI_NS}}}p')
        p.text = f"Processed with {model_used} - Analysis for {self.language_name}"

        # Profile description
        profile_desc = ET.SubElement(header, f'{{{TEI_NS}}}profileDesc')

        # Language usage
        lang_usage = ET.SubElement(profile_desc, f'{{{TEI_NS}}}langUsage')
        language = ET.SubElement(lang_usage, f'{{{TEI_NS}}}language')
        language.set('ident', self.language_code)
        language.text = self.language_name

        # Encoding description
        encoding_desc = ET.SubElement(header, f'{{{TEI_NS}}}encodingDesc')

        # Classification declaration for NLP analysis
        class_decl = ET.SubElement(encoding_desc, f'{{{TEI_NS}}}classDecl')
        taxonomy = ET.SubElement(class_decl, f'{{{TEI_NS}}}taxonomy')
        taxonomy.set(f'{{{XML_NS}}}id', 'nlp-analysis')

        # Add category definitions
        categories = [
            ('lemma', 'Lemma', 'Dictionary form of the word'),
            ('pos', 'Part of Speech', 'Grammatical category'),
            ('morph', 'Morphology', 'Morphological features')
        ]

        for cat_id, cat_name, cat_desc in categories:
            category = ET.SubElement(taxonomy, f'{{{TEI_NS}}}category')
            category.set(f'{{{XML_NS}}}id', cat_id)
            cat_desc_elem = ET.SubElement(category, f'{{{TEI_NS}}}catDesc')
            cat_desc_elem.text = f"{cat_name}: {cat_desc}"

        return header

    def _create_word_element(self, token: Dict[str, Any]) -> ET.Element:
        """
        Create a word element with linguistic annotations.

        Args:
            token: Token dictionary with NLP annotations

        Returns:
            <w> element
        """
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

            # Add morphology
            if self.config.get('include_morph', True) and token.get('morph'):
                elem.set('msd', token['morph'])

        elem.set(f'{{{XML_NS}}}id', f'w{token.get("i", 0) + 1}')
        elem.text = token['text']

        # Preserve whitespace
        if token.get('whitespace_', ' ') == ' ':
            elem.tail = ' '

        return elem

    def _prettify_xml(self, xml_str: str) -> str:
        """
        Format XML with proper indentation.

        Args:
            xml_str: Raw XML string

        Returns:
            Formatted XML string
        """
        try:
            dom = parseString(xml_str)
            pretty = dom.toprettyxml(indent="  ")

            # Clean up and ensure proper declaration
            lines = []
            for line in pretty.split('\n'):
                if line.strip():
                    lines.append(line.rstrip())

            if lines and lines[0].startswith('<?xml'):
                lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'

            return '\n'.join(lines)

        except Exception as e:
            logger.error(f"Failed to prettify XML: {e}")
            return xml_str

    def _escape_xml(self, text: str) -> str:
        """Escape special XML characters."""
        if not text:
            return ""

        text = str(text)
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        text = text.replace('"', "&quot;")
        text = text.replace("'", "&apos;")
        return text

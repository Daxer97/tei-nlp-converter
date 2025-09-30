"""
TEI XML Converter - Enhanced with validation and error handling
"""
from defusedxml import ElementTree as ET
from defusedxml.minidom import parseString
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import uuid
import re
from logger import get_logger

logger = get_logger(__name__)

class TEIConverter:
    def __init__(self, schema: Dict[str, Any], security_manager = None):
        """Initialize converter with domain-specific schema and security"""
        self.schema = schema
        self.security_manager = security_manager
        self.namespaces = {
            'tei': 'http://www.tei-c.org/ns/1.0',
            'xml': 'http://www.w3.org/XML/1998/namespace'
        }
        
        # Validate schema structure
        self._validate_schema()
        
        # Entity type mappings
        self.entity_mappings = schema.get('entity_mappings', {
            "PERSON": "persName",
            "PER": "persName",
            "LOC": "placeName",
            "GPE": "placeName",
            "ORG": "orgName",
            "DATE": "date",
            "TIME": "time",
            "MONEY": "measure",
            "DEFAULT": "name"
        })
    
    def _validate_schema(self):
        """Validate schema structure"""
        required_fields = ['domain', 'annotation_strategy']
        
        for field in required_fields:
            if field not in self.schema:
                raise ValueError(f"Schema missing required field: {field}")
        
        # Validate annotation strategy
        valid_strategies = ['inline', 'standoff', 'mixed']
        if self.schema['annotation_strategy'] not in valid_strategies:
            raise ValueError(f"Invalid annotation_strategy: {self.schema['annotation_strategy']}")
    
    def _validate_nlp_results(self, nlp_results: Dict[str, Any]) -> bool:
        """Validate NLP results structure before conversion"""
        try:
            # Check required fields
            required = ['sentences', 'entities']
            for field in required:
                if field not in nlp_results:
                    logger.error(f"NLP results missing required field: {field}")
                    return False
            
            # Validate sentences
            if not isinstance(nlp_results['sentences'], list):
                logger.error("NLP results 'sentences' must be a list")
                return False
            
            for i, sentence in enumerate(nlp_results['sentences']):
                if not isinstance(sentence, dict):
                    logger.error(f"Sentence {i} is not a dictionary")
                    return False
                if 'text' not in sentence:
                    logger.error(f"Sentence {i} missing 'text' field")
                    return False
                if 'tokens' in sentence and not isinstance(sentence['tokens'], list):
                    logger.error(f"Sentence {i} 'tokens' must be a list")
                    return False
            
            # Validate entities
            if not isinstance(nlp_results['entities'], list):
                logger.error("NLP results 'entities' must be a list")
                return False
            
            for i, entity in enumerate(nlp_results['entities']):
                if not isinstance(entity, dict):
                    logger.error(f"Entity {i} is not a dictionary")
                    return False
                required_entity_fields = ['text', 'label']
                for field in required_entity_fields:
                    if field not in entity:
                        logger.error(f"Entity {i} missing '{field}' field")
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating NLP results: {e}")
            return False
    
    def convert(self, text: str, nlp_results: Dict[str, Any]) -> str:
        """Convert NLP results to TEI XML with validation"""
        # Validate NLP results
        if not self._validate_nlp_results(nlp_results):
            logger.warning("Invalid NLP results, creating minimal TEI")
            return self._create_fallback_tei(text, "Invalid NLP results structure")
        
        try:
            # Register namespaces
            for prefix, uri in self.namespaces.items():
                ET.register_namespace(prefix, uri)
            
            # Create root TEI element
            root = self._create_root()
            
            # Add TEI Header
            header = self._create_header(nlp_results)
            root.append(header)
            
            # Add text body
            text_elem = ET.SubElement(root, '{http://www.tei-c.org/ns/1.0}text')
            body = ET.SubElement(text_elem, '{http://www.tei-c.org/ns/1.0}body')
            
            # Process based on annotation strategy
            annotation_strategy = self.schema.get('annotation_strategy', 'inline')
            
            if annotation_strategy == 'inline':
                self._add_inline_annotations(body, nlp_results)
            elif annotation_strategy == 'standoff':
                self._add_standoff_annotations(text_elem, body, nlp_results)
            else:
                # Mixed strategy
                self._add_mixed_annotations(text_elem, body, nlp_results)
            
            # Add analysis if configured
            if self.schema.get('include_analysis', False):
                self._add_analysis_section(text_elem, nlp_results)
            
            # Convert to string and prettify
            xml_str = ET.tostring(root, encoding='unicode', method='xml')
            return self._prettify_xml(xml_str)
            
        except Exception as e:
            logger.error(f"TEI conversion failed: {str(e)}", exc_info=True)
            return self._create_fallback_tei(text, str(e))
    
    def _create_fallback_tei(self, text: str, error: str) -> str:
        """Create minimal valid TEI as fallback"""
        escaped_text = self._escape_xml(text)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Processed Text - {self.schema.get('domain', 'default')}</title>
      </titleStmt>
      <publicationStmt>
        <p>Generated by TEI NLP Converter (fallback mode)</p>
      </publicationStmt>
      <sourceDesc>
        <p>Automated processing with error: {self._escape_xml(error)}</p>
      </sourceDesc>
    </fileDesc>
  </teiHeader>
  <text>
    <body>
      <p>{escaped_text}</p>
    </body>
  </text>
</TEI>"""
    
    def _escape_xml(self, text: str) -> str:
        """Properly escape XML special characters"""
        if not text:
            return ""
        
        text = str(text)
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        text = text.replace('"', "&quot;")
        text = text.replace("'", "&apos;")
        return text
    
    # ... [Rest of the methods remain the same with added validation] ...
    
    def _create_root(self) -> ET.Element:
        """Create root TEI element with proper attributes"""
        root = ET.Element('{http://www.tei-c.org/ns/1.0}TEI')
        root.set('version', '5.0')
        root.set('{http://www.w3.org/XML/1998/namespace}lang', 'en')
        
        # Add schema reference if configured
        if 'schema_ref' in self.schema:
            root.set('schemaRef', self.schema['schema_ref'])
        
        return root
    
    def _create_header(self, nlp_results: Dict[str, Any]) -> ET.Element:
        """Create comprehensive TEI header with metadata"""
        header = ET.Element('{http://www.tei-c.org/ns/1.0}teiHeader')
        
        # File description
        file_desc = ET.SubElement(header, '{http://www.tei-c.org/ns/1.0}fileDesc')
        
        # Title statement
        title_stmt = ET.SubElement(file_desc, '{http://www.tei-c.org/ns/1.0}titleStmt')
        title = ET.SubElement(title_stmt, '{http://www.tei-c.org/ns/1.0}title')
        title.text = self.schema.get('title', 'NLP Processed Text')
        
        # Add author if available
        if 'author' in self.schema:
            author = ET.SubElement(title_stmt, '{http://www.tei-c.org/ns/1.0}author')
            author.text = self.schema['author']
        
        # Responsibility statement
        resp_stmt = ET.SubElement(title_stmt, '{http://www.tei-c.org/ns/1.0}respStmt')
        resp = ET.SubElement(resp_stmt, '{http://www.tei-c.org/ns/1.0}resp')
        resp.text = 'NLP Processing and TEI Encoding'
        name = ET.SubElement(resp_stmt, '{http://www.tei-c.org/ns/1.0}name')
        name.text = 'TEI NLP Converter'
        
        # Edition statement
        edition_stmt = ET.SubElement(file_desc, '{http://www.tei-c.org/ns/1.0}editionStmt')
        edition = ET.SubElement(edition_stmt, '{http://www.tei-c.org/ns/1.0}edition')
        edition.text = 'Automated NLP Edition'
        date_elem = ET.SubElement(edition, '{http://www.tei-c.org/ns/1.0}date')
        date_elem.set('when', datetime.now().isoformat())
        
        # Publication statement
        pub_stmt = ET.SubElement(file_desc, '{http://www.tei-c.org/ns/1.0}publicationStmt')
        publisher = ET.SubElement(pub_stmt, '{http://www.tei-c.org/ns/1.0}publisher')
        publisher.text = 'TEI NLP Converter System'
        
        pub_date = ET.SubElement(pub_stmt, '{http://www.tei-c.org/ns/1.0}date')
        pub_date.set('when', datetime.now().isoformat())
        
        availability = ET.SubElement(pub_stmt, '{http://www.tei-c.org/ns/1.0}availability')
        availability.set('status', 'free')
        p = ET.SubElement(availability, '{http://www.tei-c.org/ns/1.0}p')
        p.text = 'Available for research and educational purposes'
        
        # Source description
        source_desc = ET.SubElement(file_desc, '{http://www.tei-c.org/ns/1.0}sourceDesc')
        p = ET.SubElement(source_desc, '{http://www.tei-c.org/ns/1.0}p')
        p.text = 'Generated from NLP processing of digital text'
        
        # Encoding description
        encoding_desc = ET.SubElement(header, '{http://www.tei-c.org/ns/1.0}encodingDesc')
        
        # Project description
        project_desc = ET.SubElement(encoding_desc, '{http://www.tei-c.org/ns/1.0}projectDesc')
        p = ET.SubElement(project_desc, '{http://www.tei-c.org/ns/1.0}p')
        p.text = f"Processed with domain schema: {self.schema.get('domain', 'default')}"
        
        # Tagging declaration
        tagging_decl = ET.SubElement(encoding_desc, '{http://www.tei-c.org/ns/1.0}tagsDecl')
        namespace = ET.SubElement(tagging_decl, '{http://www.tei-c.org/ns/1.0}namespace')
        namespace.set('name', 'http://www.tei-c.org/ns/1.0')
        
        # Add tag usage statistics
        self._add_tag_usage(namespace, nlp_results)
        
        # Classification declaration
        if self.schema.get('classification'):
            class_decl = ET.SubElement(encoding_desc, '{http://www.tei-c.org/ns/1.0}classDecl')
            self._add_classification(class_decl)
        
        # Profile description
        profile_desc = ET.SubElement(header, '{http://www.tei-c.org/ns/1.0}profileDesc')
        
        # Language usage
        lang_usage = ET.SubElement(profile_desc, '{http://www.tei-c.org/ns/1.0}langUsage')
        language = ET.SubElement(lang_usage, '{http://www.tei-c.org/ns/1.0}language')
        language.set('ident', nlp_results.get('language', 'en'))
        language.text = 'English'
        
        # Text classification
        if 'text_class' in self.schema:
            text_class = ET.SubElement(profile_desc, '{http://www.tei-c.org/ns/1.0}textClass')
            keywords = ET.SubElement(text_class, '{http://www.tei-c.org/ns/1.0}keywords')
            keywords.set('scheme', '#domain')
            term = ET.SubElement(keywords, '{http://www.tei-c.org/ns/1.0}term')
            term.text = self.schema['domain']
        
        return header
    
    def _add_inline_annotations(self, body: ET.Element, nlp_results: Dict[str, Any]):
        """Add complete inline annotations to the body"""
        div = ET.SubElement(body, '{http://www.tei-c.org/ns/1.0}div')
        div.set('type', 'chapter')
        div.set('n', '1')
        
        # Build entity map for efficient lookup
        entity_map = self._build_entity_map(nlp_results['entities'])
        
        # Process each sentence
        for sent_idx, sentence in enumerate(nlp_results['sentences']):
            # Create paragraph or sentence container
            if self.schema.get('use_paragraphs', False):
                container = ET.SubElement(div, '{http://www.tei-c.org/ns/1.0}p')
            else:
                container = ET.SubElement(div, '{http://www.tei-c.org/ns/1.0}s')
            
            container.set('{http://www.w3.org/XML/1998/namespace}id', f's{sent_idx+1}')
            container.set('n', str(sent_idx + 1))
            
            # Process tokens in sentence with entity awareness
            self._process_sentence_tokens(container, sentence, entity_map)
    
    def _process_sentence_tokens(self, container: ET.Element, sentence: Dict[str, Any], 
                                entity_map: Dict[int, Dict[str, Any]]):
        """Process tokens in a sentence with proper entity nesting"""
        tokens = sentence['tokens']
        i = 0
        
        while i < len(tokens):
            token = tokens[i]
            token_idx = token['i']
            
            # Check if token starts an entity
            if token_idx in entity_map and entity_map[token_idx].get('is_start'):
                entity = entity_map[token_idx]
                entity_elem = self._create_entity_element(entity)
                
                # Collect all tokens in this entity
                entity_end = entity['end']
                while i < len(tokens) and tokens[i]['i'] < entity_end:
                    self._add_token_element(entity_elem, tokens[i])
                    i += 1
                
                container.append(entity_elem)
            else:
                # Regular token outside entity
                self._add_token_element(container, token)
                i += 1
    
    def _add_token_element(self, parent: ET.Element, token: Dict[str, Any]):
        """Add a token element with appropriate attributes"""
        if token['is_punct']:
            elem = ET.SubElement(parent, '{http://www.tei-c.org/ns/1.0}pc')
        elif token['is_space']:
            # Skip pure whitespace tokens
            return
        else:
            elem = ET.SubElement(parent, '{http://www.tei-c.org/ns/1.0}w')
            
            # Add linguistic attributes
            if self.schema.get('include_lemma', True):
                elem.set('lemma', token['lemma'])
            
            if self.schema.get('include_pos', True):
                elem.set('pos', token['pos'])
            
            if self.schema.get('include_morph', False) and 'morph' in token:
                elem.set('msd', token['morph'])
            
            if self.schema.get('include_dep', False):
                elem.set('function', token['dep'])
        
        elem.set('{http://www.w3.org/XML/1998/namespace}id', f'w{token["i"]+1}')
        elem.text = token['text']
        
        # Add trailing space if needed
        if token.get('whitespace_', ' ') == ' ':
            elem.tail = ' '
    
    def _add_standoff_annotations(self, text_elem: ET.Element, body: ET.Element, 
                                  nlp_results: Dict[str, Any]):
        """Add complete standoff annotations"""
        # Add plain text with milestone elements
        div = ET.SubElement(body, '{http://www.tei-c.org/ns/1.0}div')
        
        current_pos = 0
        for sent_idx, sentence in enumerate(nlp_results['sentences']):
            # Add milestone for sentence start
            milestone = ET.SubElement(div, '{http://www.tei-c.org/ns/1.0}milestone')
            milestone.set('unit', 'sentence')
            milestone.set('n', str(sent_idx + 1))
            milestone.set('{http://www.w3.org/XML/1998/namespace}id', f'sent{sent_idx+1}')
            
            # Add sentence text
            p_elem = ET.SubElement(div, '{http://www.tei-c.org/ns/1.0}p')
            p_elem.set('{http://www.w3.org/XML/1998/namespace}id', f'p{sent_idx+1}')
            p_elem.text = sentence['text']
        
        # Add standoff annotations section
        standoff = ET.SubElement(text_elem, '{http://www.tei-c.org/ns/1.0}standOff')
        
        # Entity annotations
        if nlp_results['entities']:
            self._add_standoff_entities(standoff, nlp_results['entities'])
        
        # Linguistic annotations
        if self.schema.get('include_pos', True) or self.schema.get('include_lemma', True):
            self._add_standoff_linguistic(standoff, nlp_results['sentences'])
        
        # Dependency relations
        if self.schema.get('include_dependencies', True) and nlp_results['dependencies']:
            self._add_standoff_dependencies(standoff, nlp_results['dependencies'])
    
    def _add_standoff_entities(self, standoff: ET.Element, entities: List[Dict[str, Any]]):
        """Add entity annotations in standoff format"""
        list_annotation = ET.SubElement(standoff, '{http://www.tei-c.org/ns/1.0}listAnnotation')
        list_annotation.set('type', 'entities')
        
        for idx, entity in enumerate(entities):
            annotation = ET.SubElement(list_annotation, '{http://www.tei-c.org/ns/1.0}annotation')
            annotation.set('{http://www.w3.org/XML/1998/namespace}id', f'ent{idx+1}')
            annotation.set('type', 'named-entity')
            annotation.set('subtype', entity['label'])
            
            # Add target span
            annotation.set('target', f'#char_{entity["start_char"]}_{entity["end_char"]}')
            
            # Add confidence if available
            if 'confidence' in entity:
                certainty = ET.SubElement(annotation, '{http://www.tei-c.org/ns/1.0}certainty')
                certainty.set('degree', str(entity['confidence']))
            
            # Add entity text
            note = ET.SubElement(annotation, '{http://www.tei-c.org/ns/1.0}note')
            note.text = entity['text']
    
    def _add_standoff_linguistic(self, standoff: ET.Element, sentences: List[Dict[str, Any]]):
        """Add linguistic annotations in standoff format"""
        list_annotation = ET.SubElement(standoff, '{http://www.tei-c.org/ns/1.0}listAnnotation')
        list_annotation.set('type', 'linguistic')
        
        for sentence in sentences:
            for token in sentence['tokens']:
                if token['is_space']:
                    continue
                
                annotation = ET.SubElement(list_annotation, '{http://www.tei-c.org/ns/1.0}annotation')
                annotation.set('{http://www.w3.org/XML/1998/namespace}id', f'tok{token["i"]+1}')
                annotation.set('type', 'token')
                annotation.set('target', f'#char_{token["idx"]}_{token["idx"]+len(token["text"])}')
                
                # Add feature structure
                fs = ET.SubElement(annotation, '{http://www.tei-c.org/ns/1.0}fs')
                
                if self.schema.get('include_lemma', True):
                    f = ET.SubElement(fs, '{http://www.tei-c.org/ns/1.0}f')
                    f.set('name', 'lemma')
                    string = ET.SubElement(f, '{http://www.tei-c.org/ns/1.0}string')
                    string.text = token['lemma']
                
                if self.schema.get('include_pos', True):
                    f = ET.SubElement(fs, '{http://www.tei-c.org/ns/1.0}f')
                    f.set('name', 'pos')
                    symbol = ET.SubElement(f, '{http://www.tei-c.org/ns/1.0}symbol')
                    symbol.set('value', token['pos'])
    
    def _add_standoff_dependencies(self, standoff: ET.Element, dependencies: List[Dict[str, Any]]):
        """Add dependency relations in standoff format"""
        link_grp = ET.SubElement(standoff, '{http://www.tei-c.org/ns/1.0}linkGrp')
        link_grp.set('type', 'syntactic-dependencies')
        
        for idx, dep in enumerate(dependencies):
            link = ET.SubElement(link_grp, '{http://www.tei-c.org/ns/1.0}link')
            link.set('{http://www.w3.org/XML/1998/namespace}id', f'dep{idx+1}')
            link.set('type', dep['dep'])
            link.set('target', f'#w{dep["from"]+1} #w{dep["to"]+1}')
            
            # Add relation details
            note = ET.SubElement(link, '{http://www.tei-c.org/ns/1.0}note')
            note.text = f'{dep["from_text"]} --{dep["dep"]}--> {dep["to_text"]}'
    
    def _add_mixed_annotations(self, text_elem: ET.Element, body: ET.Element, 
                               nlp_results: Dict[str, Any]):
        """Add mixed inline and standoff annotations"""
        # Add inline basic structure
        self._add_inline_annotations(body, nlp_results)
        
        # Add standoff for complex relations
        standoff = ET.SubElement(text_elem, '{http://www.tei-c.org/ns/1.0}standOff')
        
        # Add only dependencies in standoff (entities are inline)
        if self.schema.get('include_dependencies', True) and nlp_results['dependencies']:
            self._add_standoff_dependencies(standoff, nlp_results['dependencies'])
    
    def _add_analysis_section(self, text_elem: ET.Element, nlp_results: Dict[str, Any]):
        """Add analysis section with statistics and insights"""
        back = ET.SubElement(text_elem, '{http://www.tei-c.org/ns/1.0}back')
        div = ET.SubElement(back, '{http://www.tei-c.org/ns/1.0}div')
        div.set('type', 'analysis')
        
        head = ET.SubElement(div, '{http://www.tei-c.org/ns/1.0}head')
        head.text = 'NLP Analysis Results'
        
        # Statistics
        list_elem = ET.SubElement(div, '{http://www.tei-c.org/ns/1.0}list')
        list_elem.set('type', 'statistics')
        
        stats = [
            ('Sentences', len(nlp_results['sentences'])),
            ('Tokens', sum(len(s['tokens']) for s in nlp_results['sentences'])),
            ('Entities', len(nlp_results['entities'])),
            ('Dependencies', len(nlp_results['dependencies'])),
            ('Noun Phrases', len(nlp_results.get('noun_chunks', [])))
        ]
        
        for label, value in stats:
            item = ET.SubElement(list_elem, '{http://www.tei-c.org/ns/1.0}item')
            label_elem = ET.SubElement(item, '{http://www.tei-c.org/ns/1.0}label')
            label_elem.text = label
            item.text = str(value)
    
    def _create_entity_element(self, entity: Dict[str, Any]) -> ET.Element:
        """Create appropriate entity element based on type"""
        entity_type = entity['label'].upper()
        
        # Get mapping from schema or use default
        element_name = self.entity_mappings.get(
            entity_type, 
            self.entity_mappings.get('DEFAULT', 'name')
        )
        
        elem = ET.Element(f'{{http://www.tei-c.org/ns/1.0}}{element_name}')
        
        # Add type attribute if using generic name element
        if element_name == 'name':
            elem.set('type', entity_type.lower())
        
        # Add confidence if available
        if 'confidence' in entity:
            elem.set('cert', self._confidence_to_certainty(entity['confidence']))
        
        # Add reference if available
        if 'kb_id' in entity:
            elem.set('ref', entity['kb_id'])
        
        return elem
    
    def _confidence_to_certainty(self, confidence: float) -> str:
        """Convert confidence score to TEI certainty value"""
        if confidence >= 0.9:
            return 'high'
        elif confidence >= 0.7:
            return 'medium'
        elif confidence >= 0.5:
            return 'low'
        else:
            return 'unknown'
    
    def _build_entity_map(self, entities: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        """Build a map of token positions to entities"""
        entity_map = {}
        
        for entity in entities:
            # Mark start token
            if entity['start'] not in entity_map:
                entity_map[entity['start']] = entity.copy()
                entity_map[entity['start']]['is_start'] = True
            
            # Mark all tokens in entity
            for i in range(entity['start'], entity['end']):
                if i not in entity_map:
                    entity_map[i] = entity.copy()
                    entity_map[i]['is_start'] = False
        
        return entity_map
    
    def _add_tag_usage(self, namespace: ET.Element, nlp_results: Dict[str, Any]):
        """Add tag usage statistics to header"""
        tag_counts = {
            'w': sum(len([t for t in s['tokens'] if not t['is_punct'] and not t['is_space']]) 
                    for s in nlp_results['sentences']),
            'pc': sum(len([t for t in s['tokens'] if t['is_punct']]) 
                     for s in nlp_results['sentences']),
            's': len(nlp_results['sentences'])
        }
        
        # Add entity element counts
        for entity in nlp_results['entities']:
            element_name = self.entity_mappings.get(
                entity['label'], 
                self.entity_mappings.get('DEFAULT', 'name')
            )
            tag_counts[element_name] = tag_counts.get(element_name, 0) + 1
        
        for tag, count in tag_counts.items():
            if count > 0:
                tag_usage = ET.SubElement(namespace, '{http://www.tei-c.org/ns/1.0}tagUsage')
                tag_usage.set('gi', tag)
                tag_usage.set('occurs', str(count))
    
    def _add_classification(self, class_decl: ET.Element):
        """Add classification taxonomy"""
        taxonomy = ET.SubElement(class_decl, '{http://www.tei-c.org/ns/1.0}taxonomy')
        taxonomy.set('{http://www.w3.org/XML/1998/namespace}id', 'domain')
        
        category = ET.SubElement(taxonomy, '{http://www.tei-c.org/ns/1.0}category')
        category.set('{http://www.w3.org/XML/1998/namespace}id', self.schema['domain'])
        
        cat_desc = ET.SubElement(category, '{http://www.tei-c.org/ns/1.0}catDesc')
        cat_desc.text = self.schema.get('description', f'{self.schema["domain"]} domain texts')
    
    def _prettify_xml(self, xml_str: str) -> str:
        """Pretty print XML with proper indentation and security"""
        try:
            # Use defusedxml for safe parsing
            dom = parseString(xml_str)
            pretty_xml = dom.toprettyxml(indent="  ")
            
            # Remove extra blank lines and clean up
            lines = []
            for line in pretty_xml.split('\n'):
                if line.strip():
                    lines.append(line.rstrip())
            
            # Ensure XML declaration is correct
            if lines[0].startswith('<?xml'):
                lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
            
            return '\n'.join(lines)
            
        except Exception as e:
            logger.error(f"Failed to prettify XML: {str(e)}")
            # Return the original if prettification fails
            return xml_str

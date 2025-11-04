"""
Local SpaCy NLP provider - Fixed with proper resource management
"""
import asyncio
import spacy
import asyncio
from typing import Dict, List, Any
from concurrent.futures import ThreadPoolExecutor
from nlp_providers.base import NLPProvider, ProviderCapabilities, ProcessingOptions, ProviderStatus
from logger import get_logger
from config import settings
import atexit

logger = get_logger(__name__)

class SpacyLocalProvider(NLPProvider):
    """Local SpaCy NLP provider with proper async handling and resource cleanup"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        config = config or {}
        self.model_name = config.get('model_name', settings.get('spacy_model', 'en_core_web_sm'))
        self.enable_gpu = config.get('enable_gpu', settings.get('enable_gpu', False))
        self.batch_size = config.get('batch_size', settings.get('batch_size', 32))
        self.nlp = None
        self._executor = None
        self._initialized = False
        
        # Register cleanup on exit
        atexit.register(self._cleanup)
        
    def get_name(self) -> str:
        return f"SpaCy Local ({self.model_name})"
    
    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            entities=True,
            sentences=True,
            tokens=True,
            pos_tags=True,
            dependencies=True,
            lemmas=True,
            noun_chunks=True,
            sentiment=False,
            embeddings=True,
            language_detection=False,
            syntax_analysis=True,
            entity_sentiment=False,
            classification=False
        )
    
    async def initialize(self) -> bool:
        """Initialize SpaCy model with proper error handling"""
        if self._initialized:
            return True
        
        try:
            # Create executor for CPU-bound operations
            self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="spacy")
            
            # Run initialization in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor,
                self._initialize_model
            )
            
            if result:
                self._initialized = True
            
            return result
        except Exception as e:
            logger.error(f"Failed to initialize SpaCy: {e}")
            self._status = ProviderStatus.UNAVAILABLE
            self._cleanup()
            return False
    
    def _initialize_model(self) -> bool:
        """Synchronous model initialization"""
        try:
            # Enable GPU if configured
            if self.enable_gpu:
                try:
                    spacy.require_gpu()
                    logger.info("GPU enabled for SpaCy")
                except Exception as e:
                    logger.info(f"GPU not available, using CPU: {e}")
            
            # Load model
            self.nlp = spacy.load(self.model_name)
            
            # Add sentencizer if not present
            if "sentencizer" not in self.nlp.pipe_names:
                self.nlp.add_pipe("sentencizer", first=True)
            
            # Set batch size for better performance
            self.nlp.max_length = settings.get('max_text_length', 100000)
            
            logger.info(f"Loaded SpaCy model: {self.model_name}")
            self._status = ProviderStatus.AVAILABLE
            return True
            
        except OSError:
            logger.warning(f"SpaCy model {self.model_name} not found, attempting download")
            try:
                import subprocess
                subprocess.run(
                    ["python", "-m", "spacy", "download", self.model_name], 
                    check=True,
                    capture_output=True
                )
                self.nlp = spacy.load(self.model_name)
                self._status = ProviderStatus.AVAILABLE
                return True
            except Exception as e:
                logger.error(f"Failed to download SpaCy model: {e}")
                self._status = ProviderStatus.UNAVAILABLE
                return False
        except Exception as e:
            logger.error(f"Failed to initialize SpaCy model: {e}")
            self._status = ProviderStatus.UNAVAILABLE
            return False
    
    async def health_check(self) -> ProviderStatus:
        """Check SpaCy availability"""
        if not self._initialized or not self.nlp:
            return ProviderStatus.UNAVAILABLE
        
        try:
            # Run health check in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._executor,
                lambda: self.nlp("test")
            )
            self._status = ProviderStatus.AVAILABLE
        except Exception as e:
            logger.warning(f"SpaCy health check failed: {e}")
            self._status = ProviderStatus.DEGRADED
            
        return self._status
    
    async def process(self, text: str, options: ProcessingOptions) -> Dict[str, Any]:
        """Process text using SpaCy with async execution"""
        if not self._initialized or not self.nlp:
            raise RuntimeError("SpaCy model not initialized")
        
        # Validate input
        if not text:
            raise ValueError("Text cannot be empty")
        
        # Validate options
        options = self.validate_options(options)
        
        # Run CPU-bound processing in thread pool
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                self._executor,
                self._process_sync,
                text,
                options
            )
        except Exception as e:
            logger.error(f"SpaCy processing failed: {e}")
            raise
        
        return result
    
    def _process_sync(self, text: str, options: ProcessingOptions) -> Dict[str, Any]:
        """Synchronous text processing"""
        # Process with SpaCy
        doc = self.nlp(text)
        
        result = {
            "text": text,
            "language": doc.lang_,
            "sentences": [],
            "entities": [],
            "tokens": [],
            "dependencies": [],
            "noun_chunks": [],
            "metadata": {"provider": self.get_name()}
        }
        
        # Extract sentences
        if options.include_sentences:
            result["sentences"] = self._extract_sentences(doc, options)
        
        # Extract entities
        if options.include_entities:
            result["entities"] = self._extract_entities(doc)
        
        # Extract noun chunks
        if options.include_noun_chunks:
            result["noun_chunks"] = self._extract_noun_chunks(doc)
        
        # Extract dependencies
        if options.include_dependencies:
            result["dependencies"] = self._extract_dependencies(doc)
        
        # Add embeddings if requested
        if options.include_embeddings and doc.has_vector:
            result["embeddings"] = doc.vector.tolist()
        
        return result
    
    def _extract_sentences(self, doc, options: ProcessingOptions) -> List[Dict[str, Any]]:
        """Extract sentences with tokens"""
        sentences = []
        
        for sent_idx, sent in enumerate(doc.sents):
            sentence_data = {
                "text": sent.text.strip(),
                "start": sent.start,
                "end": sent.end,
                "tokens": []
            }
            
            if options.include_tokens:
                for token in sent:
                    token_data = {
                        "text": token.text,
                        "idx": token.idx,
                        "i": token.i,
                        "is_punct": token.is_punct,
                        "is_space": token.is_space,
                        "is_alpha": token.is_alpha,
                        "is_stop": token.is_stop,
                        "shape": token.shape_
                    }
                    
                    if options.include_lemmas:
                        token_data["lemma"] = token.lemma_
                    
                    if options.include_pos:
                        token_data["pos"] = token.pos_
                        token_data["tag"] = token.tag_
                        token_data["dep"] = token.dep_
                        token_data["head"] = token.head.i
                        
                        if token.morph:
                            token_data["morph"] = str(token.morph)
                    
                    sentence_data["tokens"].append(token_data)
            
            sentences.append(sentence_data)
        
        return sentences
    
    def _extract_entities(self, doc) -> List[Dict[str, Any]]:
        """Extract named entities"""
        entities = []
        
        for ent in doc.ents:
            entity_data = {
                "text": ent.text,
                "label": self.normalize_entity_type(ent.label_),
                "start": ent.start,
                "end": ent.end,
                "start_char": ent.start_char,
                "end_char": ent.end_char
            }
            
            if ent.kb_id_:
                entity_data["kb_id"] = ent.kb_id_
            
            entities.append(entity_data)
        
        return entities
    
    def _extract_noun_chunks(self, doc) -> List[Dict[str, Any]]:
        """Extract noun chunks"""
        noun_chunks = []
        
        for chunk in doc.noun_chunks:
            chunk_data = {
                "text": chunk.text,
                "root": chunk.root.text,
                "root_dep": chunk.root.dep_,
                "root_head": chunk.root.head.text,
                "root_pos": chunk.root.pos_,
                "start": chunk.start,
                "end": chunk.end
            }
            noun_chunks.append(chunk_data)
        
        return noun_chunks
    
    def _extract_dependencies(self, doc) -> List[Dict[str, Any]]:
        """Extract syntactic dependencies"""
        dependencies = []
        seen = set()
        
        for token in doc:
            if token.dep_ != "ROOT" and token.i != token.head.i:
                dep_key = (token.head.i, token.i, token.dep_)
                if dep_key not in seen:
                    seen.add(dep_key)
                    dependencies.append({
                        "from": token.head.i,
                        "to": token.i,
                        "dep": token.dep_,
                        "from_text": token.head.text,
                        "from_pos": token.head.pos_,
                        "to_text": token.text,
                        "to_pos": token.pos_
                    })
        
        return dependencies
    
    def _cleanup(self):
        """Clean up resources"""
        if self._executor:
            try:
                # Shutdown with wait=True to ensure all threads are cleaned up
                # This prevents thread leaks but may block briefly
                self._executor.shutdown(wait=True)
                logger.debug("Executor shutdown completed")
            except Exception as e:
                logger.warning(f"Error shutting down executor: {e}")
            finally:
                self._executor = None

        # Clear SpaCy model from memory
        if self.nlp:
            # Breaking circular references in SpaCy's internal structures
            self.nlp = None
            logger.debug("SpaCy model cleared from memory")

        self._initialized = False

    async def close(self):
        """
        Cleanup resources and free memory

        Shuts down thread pool executor, clears SpaCy model from memory,
        and breaks circular references to prevent memory leaks.
        """
        self._cleanup()
        logger.info("SpaCy provider closed successfully")

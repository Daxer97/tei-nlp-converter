"""
Google Cloud Natural Language API provider - Fixed with better error handling
"""
from typing import Dict, List, Any, Optional
import os
import stat
from nlp_providers.base import NLPProvider, ProviderCapabilities, ProcessingOptions, ProviderStatus
from logger import get_logger

logger = get_logger(__name__)

# Import Google Cloud libraries with proper error handling
try:
    from google.cloud import language_v1
    from google.cloud.language_v1 import types as language_types
    from google.oauth2 import service_account
    from google.auth.exceptions import DefaultCredentialsError, RefreshError
    from google.api_core.exceptions import (
        GoogleAPIError, 
        PermissionDenied, 
        InvalidArgument,
        ResourceExhausted,
        ServiceUnavailable
    )
    GOOGLE_CLOUD_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Google Cloud libraries not installed: {e}")
    GOOGLE_CLOUD_AVAILABLE = False
    # Create dummy classes to prevent errors
    DefaultCredentialsError = Exception
    GoogleAPIError = Exception

class GoogleCloudNLPProvider(NLPProvider):
    """Google Cloud Natural Language API provider with enhanced error handling"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        config = config or {}
        self.client = None
        self.credentials = None
        
        # Google Cloud specific config
        self.project_id = config.get('project_id') or os.getenv('GOOGLE_CLOUD_PROJECT')
        self.credentials_path = config.get('credentials_path') or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        self.api_key = config.get('api_key') or os.getenv('GOOGLE_CLOUD_API_KEY')
        
        # Validate configuration
        if not GOOGLE_CLOUD_AVAILABLE:
            logger.error("Google Cloud libraries not available. Install with: pip install google-cloud-language")
            self._status = ProviderStatus.UNAVAILABLE
        elif not any([self.project_id, self.credentials_path, self.api_key]):
            logger.warning(
                "Google Cloud NLP provider configured but missing credentials. "
                "Please provide one of: project_id, credentials_path (GOOGLE_APPLICATION_CREDENTIALS), or api_key"
            )
            self._status = ProviderStatus.UNAVAILABLE
        
    def get_name(self) -> str:
        return "Google Cloud NLP"
    
    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            entities=True,
            sentences=True,
            tokens=True,
            pos_tags=True,
            dependencies=True,
            lemmas=True,
            noun_chunks=False,  # Google doesn't provide noun chunks directly
            sentiment=True,
            embeddings=False,
            language_detection=True,
            syntax_analysis=True,
            entity_sentiment=True,
            classification=True
        )
    
    async def initialize(self) -> bool:
        """Initialize Google Cloud NLP client with detailed error handling"""
        if not GOOGLE_CLOUD_AVAILABLE:
            logger.error("Cannot initialize Google Cloud NLP: libraries not installed")
            self._status = ProviderStatus.UNAVAILABLE
            return False
        
        try:
            # Try different authentication methods in order of preference
            
            # Method 1: Service account file
            if self.credentials_path:
                if not os.path.exists(self.credentials_path):
                    logger.error(f"Credentials file not found: {self.credentials_path}")
                    self._status = ProviderStatus.UNAVAILABLE
                    return False
                
                # Check file permissions for security
                try:
                    file_stat = os.stat(self.credentials_path)
                    file_mode = stat.S_IMODE(file_stat.st_mode)
                    if file_mode & 0o077:  # Check if group/others have any permissions
                        logger.warning(
                            f"Credentials file {self.credentials_path} has overly permissive permissions. "
                            f"Consider running: chmod 600 {self.credentials_path}"
                        )
                except OSError as e:
                    logger.warning(f"Could not check credentials file permissions: {e}")
                
                try:
                    self.credentials = service_account.Credentials.from_service_account_file(
                        self.credentials_path
                    )
                    self.client = language_v1.LanguageServiceClient(credentials=self.credentials)
                    logger.info(f"Google Cloud NLP initialized with service account: {self.credentials_path}")
                except ValueError as e:
                    logger.error(f"Invalid service account file: {e}")
                    self._status = ProviderStatus.UNAVAILABLE
                    return False
            
            # Method 2: API Key
            elif self.api_key:
                try:
                    from google.cloud import language_v1
                    # API key authentication
                    self.client = language_v1.LanguageServiceClient(
                        client_options={"api_key": self.api_key}
                    )
                    logger.info("Google Cloud NLP initialized with API key")
                except Exception as e:
                    logger.error(f"Failed to initialize with API key: {e}")
                    self._status = ProviderStatus.UNAVAILABLE
                    return False
            
            # Method 3: Default credentials (ADC)
            else:
                try:
                    self.client = language_v1.LanguageServiceClient()
                    logger.info("Google Cloud NLP initialized with default credentials")
                except DefaultCredentialsError as e:
                    logger.error(
                        f"Google Cloud default credentials not found: {e}\n"
                        "Please either:\n"
                        "1. Set GOOGLE_APPLICATION_CREDENTIALS environment variable\n"
                        "2. Run 'gcloud auth application-default login'\n"
                        "3. Provide credentials_path or api_key in configuration"
                    )
                    self._status = ProviderStatus.UNAVAILABLE
                    return False
            
            # Test the connection
            test_status = await self.health_check()
            if test_status == ProviderStatus.AVAILABLE:
                logger.info("Google Cloud NLP client initialized and tested successfully")
                self._status = ProviderStatus.AVAILABLE
                return True
            else:
                logger.warning(f"Google Cloud NLP initialized but health check returned: {test_status}")
                return False
                
        except DefaultCredentialsError as e:
            logger.error(
                f"Google Cloud credentials error: {e}\n"
                "Ensure credentials are properly configured"
            )
            self._status = ProviderStatus.UNAVAILABLE
            return False
            
        except RefreshError as e:
            logger.error(f"Google Cloud token refresh failed: {e}")
            self._status = ProviderStatus.UNAVAILABLE
            return False
            
        except PermissionDenied as e:
            logger.error(
                f"Google Cloud permission denied: {e}\n"
                "Ensure the service account has 'Cloud Natural Language API' permissions"
            )
            self._status = ProviderStatus.UNAVAILABLE
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error initializing Google Cloud NLP: {e}", exc_info=True)
            self._status = ProviderStatus.UNAVAILABLE
            return False
    
    async def health_check(self) -> ProviderStatus:
        """Check Google Cloud NLP service availability with detailed error handling"""
        if not self.client:
            return ProviderStatus.UNAVAILABLE
        
        try:
            # Test with a minimal request
            document = language_types.Document(
                content="Test",
                type_=language_v1.Document.Type.PLAIN_TEXT,
                language="en"
            )
            
            # Try to analyze entities (lightweight operation)
            self.client.analyze_entities(
                request={"document": document, "encoding_type": language_v1.EncodingType.UTF8}
            )
            
            self._status = ProviderStatus.AVAILABLE
            return ProviderStatus.AVAILABLE
            
        except PermissionDenied as e:
            logger.error(f"Health check failed - Permission denied: {e}")
            self._status = ProviderStatus.UNAVAILABLE
            return ProviderStatus.UNAVAILABLE
            
        except InvalidArgument as e:
            logger.error(f"Health check failed - Invalid request: {e}")
            self._status = ProviderStatus.DEGRADED
            return ProviderStatus.DEGRADED
            
        except ResourceExhausted as e:
            logger.warning(f"Health check - API quota exceeded: {e}")
            self._status = ProviderStatus.DEGRADED
            return ProviderStatus.DEGRADED
            
        except ServiceUnavailable as e:
            logger.warning(f"Health check - Service temporarily unavailable: {e}")
            self._status = ProviderStatus.DEGRADED
            return ProviderStatus.DEGRADED
            
        except Exception as e:
            logger.warning(f"Health check failed with unexpected error: {e}")
            self._status = ProviderStatus.DEGRADED
            return ProviderStatus.DEGRADED
    
    async def process(self, text: str, options: ProcessingOptions) -> Dict[str, Any]:
        """Process text using Google Cloud NLP API with comprehensive error handling"""
        if not self.client:
            raise RuntimeError("Google Cloud NLP client not initialized")
        
        # Validate text length (Google Cloud has limits)
        if len(text) > 1000000:  # 1M characters limit
            raise ValueError(f"Text exceeds Google Cloud NLP limit of 1M characters: {len(text)} chars")
        
        # Validate options
        options = self.validate_options(options)
        
        # Create document
        document = language_types.Document(
            content=text,
            type_=language_v1.Document.Type.PLAIN_TEXT,
            language=options.language if options.language != "auto" else None
        )
        
        # Determine encoding type
        encoding_type = getattr(
            language_v1.EncodingType, 
            options.encoding_type.upper(), 
            language_v1.EncodingType.UTF8
        )
        
        result = {
            "text": text,
            "language": options.language,
            "sentences": [],
            "entities": [],
            "tokens": [],
            "dependencies": [],
            "noun_chunks": [],  # Google doesn't provide this directly
            "metadata": {"provider": self.get_name()}
        }
        
        try:
            # Analyze syntax (includes tokens, POS, dependencies, lemmas)
            if any([options.include_tokens, options.include_pos, 
                   options.include_dependencies, options.include_lemmas]):
                try:
                    syntax_response = self.client.analyze_syntax(
                        request={
                            "document": document,
                            "encoding_type": encoding_type
                        }
                    )
                    
                    # Process sentences
                    if options.include_sentences:
                        result["sentences"] = self._process_sentences(syntax_response)
                    
                    # Process tokens with linguistic features
                    if options.include_tokens:
                        tokens_data = self._process_tokens(syntax_response, options)
                        result["tokens"] = tokens_data["tokens"]
                        
                        # Extract dependencies from token data
                        if options.include_dependencies:
                            result["dependencies"] = tokens_data["dependencies"]
                            
                except InvalidArgument as e:
                    logger.error(f"Invalid syntax analysis request: {e}")
                    # Continue with other analyses if syntax fails
            
            # Analyze entities with sentiment (Google-specific feature)
            if options.include_entities:
                try:
                    # Use entity sentiment analysis for richer entity information
                    if self.capabilities.entity_sentiment:
                        entity_response = self.client.analyze_entity_sentiment(
                            request={
                                "document": document,
                                "encoding_type": encoding_type
                            }
                        )
                    else:
                        entity_response = self.client.analyze_entities(
                            request={
                                "document": document,
                                "encoding_type": encoding_type
                            }
                        )
                    result["entities"] = self._process_entities(entity_response)
                except InvalidArgument as e:
                    logger.error(f"Invalid entity analysis request: {e}")
            
            # Add sentiment if requested
            if options.include_sentiment and self.capabilities.sentiment:
                try:
                    sentiment_response = self.client.analyze_sentiment(
                        request={
                            "document": document,
                            "encoding_type": encoding_type
                        }
                    )
                    result["sentiment"] = self._process_sentiment(sentiment_response)
                except InvalidArgument as e:
                    logger.error(f"Invalid sentiment analysis request: {e}")
            
            # Detect language if not specified
            if options.language == "auto" and 'syntax_response' in locals():
                result["language"] = syntax_response.language or "en"
            
            return result
            
        except ResourceExhausted as e:
            logger.error(f"Google Cloud API quota exceeded: {e}")
            raise RuntimeError(
                "API quota exceeded. Please try again later or check your Google Cloud quotas."
            )
            
        except ServiceUnavailable as e:
            logger.error(f"Google Cloud service unavailable: {e}")
            raise RuntimeError(
                "Google Cloud NLP service is temporarily unavailable. Please try again later."
            )
            
        except PermissionDenied as e:
            logger.error(f"Permission denied: {e}")
            raise RuntimeError(
                "Permission denied. Check that your credentials have access to the Natural Language API."
            )
            
        except GoogleAPIError as e:
            logger.error(f"Google Cloud API error: {e}")
            raise RuntimeError(f"Google Cloud API error: {str(e)}")
            
        except Exception as e:
            logger.error(f"Unexpected error during processing: {e}", exc_info=True)
            raise
    
    # [Keep all the existing helper methods: _process_sentences, _process_tokens, _process_entities, _process_sentiment]
    
    def _process_sentences(self, response) -> List[Dict[str, Any]]:
        """Process sentences from Google Cloud NLP response"""
        sentences = []
        
        for sentence in response.sentences:
            sentences.append({
                "text": sentence.text.content,
                "start": sentence.text.begin_offset,
                "sentiment": {
                    "score": sentence.sentiment.score,
                    "magnitude": sentence.sentiment.magnitude
                } if hasattr(sentence, 'sentiment') else None
            })
        
        return sentences
    
    def _process_tokens(self, response, options: ProcessingOptions) -> Dict[str, Any]:
        """Process tokens and extract linguistic features"""
        tokens_data = {
            "tokens": [],
            "dependencies": []
        }
        
        for i, token in enumerate(response.tokens):
            token_info = {
                "text": token.text.content,
                "idx": token.text.begin_offset,
                "i": i
            }
            
            # Add POS tag if requested
            if options.include_pos:
                token_info["pos"] = token.part_of_speech.tag.name
                token_info["tag"] = token.part_of_speech.tag.name
                
                # Add morphological features
                morph_features = []
                pos = token.part_of_speech
                
                if pos.mood:
                    morph_features.append(f"Mood={pos.mood.name}")
                if pos.tense:
                    morph_features.append(f"Tense={pos.tense.name}")
                if pos.voice:
                    morph_features.append(f"Voice={pos.voice.name}")
                if pos.person:
                    morph_features.append(f"Person={pos.person.name}")
                if pos.number:
                    morph_features.append(f"Number={pos.number.name}")
                if pos.gender:
                    morph_features.append(f"Gender={pos.gender.name}")
                
                if morph_features:
                    token_info["morph"] = "|".join(morph_features)
            
            # Add lemma if requested
            if options.include_lemmas:
                token_info["lemma"] = token.lemma
            
            # Add dependency information
            if options.include_dependencies:
                dep_edge = token.dependency_edge
                token_info["dep"] = dep_edge.label.name
                token_info["head"] = dep_edge.head_token_index
                
                # Create dependency relation
                if dep_edge.head_token_index != i:
                    tokens_data["dependencies"].append({
                        "from": dep_edge.head_token_index,
                        "to": i,
                        "dep": dep_edge.label.name,
                        "from_text": response.tokens[dep_edge.head_token_index].text.content 
                                    if dep_edge.head_token_index < len(response.tokens) else "ROOT",
                        "to_text": token.text.content
                    })
            
            # Determine token type
            token_info["is_punct"] = token.part_of_speech.tag.name == "PUNCT"
            token_info["is_space"] = token.text.content.isspace()
            token_info["is_alpha"] = token.text.content.isalpha()
            
            tokens_data["tokens"].append(token_info)
        
        return tokens_data
    
    def _process_entities(self, response) -> List[Dict[str, Any]]:
        """Process entities from Google Cloud NLP response with full Google-specific features"""
        entities = []

        for entity in response.entities:
            # Get entity span from mentions
            for mention in entity.mentions:
                entity_data = {
                    "text": mention.text.content,
                    "label": self.normalize_entity_type(entity.type_.name),
                    "start_char": mention.text.begin_offset,
                    "end_char": mention.text.begin_offset + len(mention.text.content),
                    # Google-specific: Salience (importance) score
                    "salience": float(entity.salience),
                    # Google-specific: Mention type (PROPER, COMMON, etc.)
                    "mention_type": mention.type_.name if hasattr(mention, 'type_') else None,
                }

                # Google-specific: Entity sentiment (emotional context)
                if hasattr(mention, 'sentiment') and mention.sentiment:
                    entity_data["sentiment"] = {
                        "score": float(mention.sentiment.score),
                        "magnitude": float(mention.sentiment.magnitude)
                    }
                elif hasattr(entity, 'sentiment') and entity.sentiment:
                    # Fallback to entity-level sentiment
                    entity_data["sentiment"] = {
                        "score": float(entity.sentiment.score),
                        "magnitude": float(entity.sentiment.magnitude)
                    }

                # Google-specific: Knowledge Graph metadata
                if entity.metadata:
                    metadata = {}
                    if entity.metadata.get("wikipedia_url"):
                        metadata["wikipedia_url"] = entity.metadata.get("wikipedia_url")
                    if entity.metadata.get("mid"):
                        metadata["knowledge_graph_mid"] = entity.metadata.get("mid")
                    if metadata:
                        entity_data["metadata"] = metadata

                # Provider identification
                entity_data["provider"] = "google"

                entities.append(entity_data)

        # Sort entities by salience (importance) for Google results
        entities.sort(key=lambda x: x.get("salience", 0), reverse=True)

        return entities
    
    def _process_sentiment(self, response) -> Dict[str, Any]:
        """Process sentiment analysis results"""
        return {
            "document": {
                "score": response.document_sentiment.score,
                "magnitude": response.document_sentiment.magnitude
            },
            "sentences": [
                {
                    "text": sentence.text.content,
                    "score": sentence.sentiment.score,
                    "magnitude": sentence.sentiment.magnitude
                }
                for sentence in response.sentences
            ] if hasattr(response, 'sentences') else []
        }
    
    async def close(self):
        """Cleanup Google Cloud NLP client"""
        if self.client:
            # Google Cloud client doesn't need explicit cleanup
            self.client = None
            logger.info("Google Cloud NLP client closed")

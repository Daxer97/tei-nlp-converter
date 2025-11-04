"""
NLP Connector - Fixed config access issues
"""
import asyncio
from typing import Dict, List, Any, Optional
import hashlib
import json
from nlp_providers.base import NLPProvider, ProcessingOptions, ProviderStatus
from nlp_providers.registry import get_registry
from cache_manager import CacheManager
from logger import get_logger
from config import settings
from metrics import nlp_processing_duration
import time

logger = get_logger(__name__)

class NLPProcessor:
    """
    Main NLP processor with provider abstraction, fallback chain, and proper error handling
    """
    
    def __init__(self, 
                 primary_provider: str = None,
                 fallback_providers: List[str] = None,
                 cache_manager: Optional[CacheManager] = None):
        """
        Initialize NLP Processor with safe configuration access
        """
        self.cache_manager = cache_manager or CacheManager()
        self.registry = get_registry()
        
        # Safe configuration with defaults
        self.primary_provider = primary_provider or settings.get('nlp_provider', 'spacy')
        
        # Ensure fallback_providers is always a list
        default_fallbacks = settings.get('nlp_fallback_providers', ['spacy'])
        if isinstance(default_fallbacks, str):
            default_fallbacks = [default_fallbacks]
        
        self.fallback_providers = fallback_providers or default_fallbacks
        
        # Ensure fallback_providers is a list
        if isinstance(self.fallback_providers, str):
            self.fallback_providers = [self.fallback_providers]
        
        # Ensure primary provider is not in fallbacks
        self.fallback_providers = [p for p in self.fallback_providers if p != self.primary_provider]
        
        # Set default provider in registry
        self.registry.set_default(self.primary_provider)
        
        # Track initialization state
        self._initialized = False
        self._initialization_lock = asyncio.Lock()
        
        logger.info(f"NLP Processor configured with primary: {self.primary_provider}, "
                   f"fallbacks: {self.fallback_providers}")

    async def initialize_providers(self):
        """Initialize configured providers with proper error handling"""
        async with self._initialization_lock:
            if self._initialized:
                return
            
            providers_to_init = [self.primary_provider] + self.fallback_providers
            successful_inits = []
            
            for provider_name in providers_to_init:
                try:
                    # Get provider config from settings
                    config = self._get_provider_config(provider_name)
                    provider = await self.registry.get_or_create(provider_name, config)
                    
                    # Verify provider is actually working
                    status = await provider.health_check()
                    if status == ProviderStatus.AVAILABLE:
                        successful_inits.append(provider_name)
                        logger.info(f"Successfully initialized provider: {provider.get_name()}")
                    else:
                        logger.warning(f"Provider {provider_name} initialized but not available: {status}")
                        
                except Exception as e:
                    logger.error(f"Failed to initialize provider {provider_name}: {e}")
            
            if not successful_inits:
                logger.error("No NLP providers could be initialized successfully")
                raise RuntimeError("Failed to initialize any NLP provider")
            
            # Update primary provider if it failed
            if self.primary_provider not in successful_inits and successful_inits:
                old_primary = self.primary_provider
                self.primary_provider = successful_inits[0]
                logger.warning(f"Primary provider {old_primary} failed, using {self.primary_provider} instead")
            
            self._initialized = True
    
    def _get_provider_config(self, provider_name: str) -> Dict[str, Any]:
        """Get configuration for a specific provider with safe access"""
        config = {}
        
        if provider_name == 'google':
            config = {
                'project_id': settings.get('google_project_id'),
                'credentials_path': settings.get('google_credentials_path'),
                'api_key': settings.get('google_api_key')
            }
        elif provider_name == 'spacy':
            config = {
                'model_name': settings.get('spacy_model', 'en_core_web_sm'),
                'enable_gpu': settings.get('enable_gpu', False),
                'batch_size': settings.get('batch_size', 32)
            }
        elif provider_name == 'remote':
            config = {
                'base_url': settings.get('nlp_server_url', 'http://localhost:8081'),
                'api_key': settings.get('nlp_server_api_key'),
                'timeout': settings.get('nlp_server_timeout', 30),
                'circuit_breaker_threshold': settings.get('nlp_circuit_breaker_threshold', 5),
                'circuit_breaker_timeout': settings.get('nlp_circuit_breaker_timeout', 60)
            }

        # Filter out None values
        config = {k: v for k, v in config.items() if v is not None}
        
        return config
    
    async def process(self, text: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process text with automatic provider selection and fallback
        """
        # Ensure providers are initialized
        if not self._initialized:
            await self.initialize_providers()
        
        # Validate input
        if not text:
            raise ValueError("Text cannot be empty")
        
        if len(text) > settings.get('max_text_length', 100000):
            raise ValueError(f"Text exceeds maximum length of {settings.get('max_text_length')} characters")
        
        # Convert options to ProcessingOptions
        processing_options = self._parse_options(options)
        
        # Generate cache key
        cache_key = self._generate_cache_key(text, processing_options)
        
        # Check cache
        cached = self.cache_manager.get(cache_key)
        if cached:
            logger.debug("Returning cached NLP result")
            from metrics import cache_hits
            cache_hits.inc()
            return cached
        
        from metrics import cache_misses
        cache_misses.inc()
        
        # Try processing with provider chain
        result = await self._process_with_fallback(text, processing_options)
        
        # Validate result structure
        if not self._validate_result(result):
            logger.error("Invalid NLP result structure")
            raise ValueError("NLP processing returned invalid result")
        
        # Cache the result
        cache_ttl = settings.get('cache_ttl', 3600)
        self.cache_manager.set(cache_key, result, ttl=cache_ttl)
        
        return result

    def _validate_result(self, result: Dict[str, Any]) -> bool:
        """Validate NLP result structure"""
        required_fields = ['sentences', 'entities', 'text']
        
        for field in required_fields:
            if field not in result:
                logger.error(f"Missing required field in NLP result: {field}")
                return False
        
        # Validate sentences structure
        if not isinstance(result['sentences'], list):
            return False
        
        for sentence in result['sentences']:
            if not isinstance(sentence, dict) or 'text' not in sentence:
                return False
        
        # Validate entities structure
        if not isinstance(result['entities'], list):
            return False
        
        for entity in result['entities']:
            if not isinstance(entity, dict) or 'text' not in entity or 'label' not in entity:
                return False
        
        return True
    
    async def _process_with_fallback(self, text: str, options: ProcessingOptions) -> Dict[str, Any]:
        """Process with fallback chain and comprehensive error handling"""
        provider_chain = [self.primary_provider] + self.fallback_providers
        last_error = None
        attempted_providers = []
        
        for provider_name in provider_chain:
            try:
                provider = self.registry.get_instance(provider_name)
                
                if not provider:
                    # Try to create provider on demand
                    logger.info(f"Creating provider {provider_name} on demand")
                    config = self._get_provider_config(provider_name)
                    provider = await self.registry.create_provider(provider_name, config)
                
                # Check provider health with timeout
                try:
                    status = await asyncio.wait_for(
                        provider.health_check(),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Health check timeout for provider {provider_name}")
                    status = ProviderStatus.UNAVAILABLE
                
                if status == ProviderStatus.UNAVAILABLE:
                    logger.warning(f"Provider {provider_name} is unavailable, trying next")
                    attempted_providers.append(provider_name)
                    continue
                
                # Process with provider
                start_time = time.time()
                
                # Add timeout for processing
                try:
                    result = await asyncio.wait_for(
                        provider.process(text, options),
                        timeout=settings.get('request_timeout', 300)
                    )
                except asyncio.TimeoutError:
                    raise TimeoutError(f"Provider {provider_name} processing timeout")
                
                processing_time = time.time() - start_time
                
                # Record metrics
                nlp_processing_duration.labels(source=provider_name).observe(processing_time)
                
                # Add processing metadata
                result["_metadata"] = {
                    "provider": provider.get_name(),
                    "processing_time": processing_time,
                    "fallback_used": provider_name != self.primary_provider,
                    "attempted_providers": attempted_providers
                }
                
                logger.info(f"Successfully processed text with provider: {provider.get_name()}")
                return result
                
            except Exception as e:
                last_error = e
                attempted_providers.append(provider_name)
                logger.warning(f"Provider {provider_name} failed: {e}")
                
                if provider_name != provider_chain[-1]:
                    logger.info(f"Falling back to next provider")
                    continue
        
        # All providers failed
        error_msg = f"All NLP providers failed. Last error: {last_error}. Attempted: {attempted_providers}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    def _parse_options(self, options: Optional[Dict[str, Any]]) -> ProcessingOptions:
        """Parse options dict to ProcessingOptions"""
        if not options:
            return ProcessingOptions()
        
        return ProcessingOptions(
            include_entities=options.get('include_entities', True),
            include_sentences=options.get('include_sentences', True),
            include_tokens=options.get('include_tokens', True),
            include_pos=options.get('include_pos', True),
            include_dependencies=options.get('include_dependencies', True),
            include_lemmas=options.get('include_lemmas', True),
            include_noun_chunks=options.get('include_noun_chunks', True),
            include_sentiment=options.get('include_sentiment', False),
            include_embeddings=options.get('include_embeddings', False),
            language=options.get('language', 'en')
        )
    
    def _generate_cache_key(self, text: str, options: ProcessingOptions) -> str:
        """Generate unique cache key"""
        # Convert options to stable string representation
        options_str = json.dumps({
            'entities': options.include_entities,
            'sentences': options.include_sentences,
            'tokens': options.include_tokens,
            'pos': options.include_pos,
            'dependencies': options.include_dependencies,
            'lemmas': options.include_lemmas,
            'noun_chunks': options.include_noun_chunks,
            'sentiment': options.include_sentiment,
            'embeddings': options.include_embeddings,
            'language': options.language
        }, sort_keys=True)
        
        content = f"{text}:{options_str}"
        return f"nlp:{hashlib.sha256(content.encode()).hexdigest()}"
    
    async def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all providers"""
        statuses = await self.registry.health_check_all()
        
        return {
            "primary": self.primary_provider,
            "fallbacks": self.fallback_providers,
            "provider_status": {
                name: status.value for name, status in statuses.items()
            },
            "available_providers": self.registry.list_providers()
        }
    
    async def switch_provider(self, provider_name: str):
        """Switch primary provider at runtime"""
        if provider_name not in self.registry.list_providers():
            raise ValueError(f"Provider {provider_name} not available")
        
        # Initialize if needed
        if not self.registry.get_instance(provider_name):
            config = self._get_provider_config(provider_name)
            await self.registry.create_provider(provider_name, config)
        
        # Switch primary
        self.primary_provider = provider_name
        self.registry.set_default(provider_name)
        
        logger.info(f"Switched primary provider to: {provider_name}")
    
    async def close(self):
        """Clean up resources properly"""
        try:
            await self.registry.close_all()
            logger.info("NLP processor closed successfully")
        except Exception as e:
            logger.error(f"Error closing NLP processor: {e}")

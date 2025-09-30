"""
Remote NLP server provider (refactored from original RemoteNLPClient)
"""
import aiohttp
import asyncio
from typing import Dict, Any, Optional
from nlp_providers.base import NLPProvider, ProviderCapabilities, ProcessingOptions, ProviderStatus
from circuit_breaker import CircuitBreaker
from logger import get_logger
from config import settings

logger = get_logger(__name__)

class RemoteServerProvider(NLPProvider):
    """Remote NLP server provider"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        
        # Remote server config
        self.base_url = (config.get('base_url', settings.nlp_server_url) if config 
                        else settings.nlp_server_url).rstrip('/')
        self.api_key = config.get('api_key', settings.nlp_server_api_key) if config else settings.nlp_server_api_key
        self.timeout = config.get('timeout', settings.nlp_server_timeout) if config else settings.nlp_server_timeout
        self.max_retries = config.get('max_retries', 3) if config else 3
        
        self.session = None
        
        # Circuit breaker
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.nlp_circuit_breaker_threshold,
            recovery_timeout=settings.nlp_circuit_breaker_timeout,
            expected_exception=aiohttp.ClientError
        )
    
    def get_name(self) -> str:
        return f"Remote NLP Server ({self.base_url})"
    
    def get_capabilities(self) -> ProviderCapabilities:
        # Capabilities depend on the remote server
        # This should ideally be fetched from the server
        return ProviderCapabilities(
            entities=True,
            sentences=True,
            tokens=True,
            pos_tags=True,
            dependencies=True,
            lemmas=True,
            noun_chunks=True,
            sentiment=False,
            embeddings=False,
            language_detection=False,
            syntax_analysis=True
        )
    
    async def initialize(self) -> bool:
        """Initialize HTTP session"""
        try:
            connector = aiohttp.TCPConnector(
                limit=100,
                ttl_dns_cache=300,
                enable_cleanup_closed=True
            )
            timeout_config = aiohttp.ClientTimeout(total=self.timeout)
            
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout_config,
                headers=headers
            )
            
            # Test connection
            status = await self.health_check()
            self._status = status
            
            return status == ProviderStatus.AVAILABLE
            
        except Exception as e:
            logger.error(f"Failed to initialize remote NLP client: {e}")
            self._status = ProviderStatus.UNAVAILABLE
            return False
    
    async def health_check(self) -> ProviderStatus:
        """Check remote server health"""
        if not self.session:
            return ProviderStatus.UNAVAILABLE
        
        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    return ProviderStatus.AVAILABLE
                else:
                    return ProviderStatus.DEGRADED
        except Exception as e:
            logger.warning(f"Remote NLP health check failed: {e}")
            return ProviderStatus.UNAVAILABLE
    
    @CircuitBreaker(failure_threshold=5, recovery_timeout=60)
    async def process(self, text: str, options: ProcessingOptions) -> Dict[str, Any]:
        """Process text through remote server"""
        if not self.session:
            raise RuntimeError("Remote NLP client not initialized")
        
        # Convert options to dict for remote API
        options_dict = {
            "include_entities": options.include_entities,
            "include_sentences": options.include_sentences,
            "include_tokens": options.include_tokens,
            "include_pos": options.include_pos,
            "include_dependencies": options.include_dependencies,
            "include_lemmas": options.include_lemmas,
            "include_noun_chunks": options.include_noun_chunks
        }
        
        payload = {
            "text": text,
            "options": options_dict
        }
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with self.session.post(
                    f"{self.base_url}/process",
                    json=payload
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        result["metadata"] = {"provider": self.get_name()}
                        logger.info(f"Remote NLP processing successful (attempt {attempt + 1})")
                        return result
                    elif response.status == 503:
                        last_error = f"Service unavailable (HTTP {response.status})"
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                    else:
                        error_text = await response.text()
                        raise Exception(f"Remote NLP error: {response.status} - {error_text}")
                        
            except aiohttp.ClientError as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    logger.warning(f"Remote NLP attempt {attempt + 1} failed: {e}")
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
        
        raise Exception(f"Remote NLP failed after {self.max_retries} attempts: {last_error}")
    
    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("Remote NLP client closed")

"""
Provider registry and factory
"""
import asyncio
from typing import Dict, Type, Optional, List, Any
from nlp_providers.base import NLPProvider, ProviderStatus
from nlp_providers.spacy_local import SpacyLocalProvider
from nlp_providers.google_cloud import GoogleCloudNLPProvider
from nlp_providers.remote_server import RemoteServerProvider
from logger import get_logger

logger = get_logger(__name__)

class ProviderRegistry:
    """Registry for NLP providers"""
    
    def __init__(self):
        self._providers: Dict[str, Type[NLPProvider]] = {}
        self._instances: Dict[str, NLPProvider] = {}
        self._default_provider: Optional[str] = None
        
        # Register built-in providers
        self._register_builtin_providers()
    
    def _register_builtin_providers(self):
        """Register built-in providers"""
        self.register("spacy", SpacyLocalProvider)
        self.register("google", GoogleCloudNLPProvider)
        self.register("remote", RemoteServerProvider)
        
        logger.info(f"Registered {len(self._providers)} built-in providers")
    
    def register(self, name: str, provider_class: Type[NLPProvider]):
        """Register a new provider"""
        if not issubclass(provider_class, NLPProvider):
            raise ValueError(f"{provider_class} must inherit from NLPProvider")
        
        self._providers[name] = provider_class
        logger.info(f"Registered provider: {name}")
    
    def unregister(self, name: str):
        """Unregister a provider"""
        if name in self._providers:
            del self._providers[name]
            if name in self._instances:
                del self._instances[name]
            logger.info(f"Unregistered provider: {name}")
    
    def get_provider_class(self, name: str) -> Optional[Type[NLPProvider]]:
        """Get provider class by name"""
        return self._providers.get(name)
    
    def list_providers(self) -> List[str]:
        """List all registered providers"""
        return list(self._providers.keys())
    
    async def create_provider(self, name: str, config: Dict[str, Any] = None) -> NLPProvider:
        """Create and initialize a provider instance"""
        if name not in self._providers:
            raise ValueError(f"Provider '{name}' not registered")
        
        # Check if instance already exists
        if name in self._instances:
            return self._instances[name]
        
        # Create new instance
        provider_class = self._providers[name]
        provider = provider_class(config)
        
        # Initialize the provider
        if await provider.initialize():
            self._instances[name] = provider
            logger.info(f"Created and initialized provider: {name}")
            return provider
        else:
            raise RuntimeError(f"Failed to initialize provider: {name}")
    
    def get_instance(self, name: str) -> Optional[NLPProvider]:
        """Get existing provider instance"""
        return self._instances.get(name)
    
    async def get_or_create(self, name: str, config: Dict[str, Any] = None) -> NLPProvider:
        """Get existing instance or create new one"""
        if name in self._instances:
            return self._instances[name]
        return await self.create_provider(name, config)
    
    def set_default(self, name: str):
        """Set default provider"""
        if name not in self._providers:
            raise ValueError(f"Provider '{name}' not registered")
        self._default_provider = name
        logger.info(f"Set default provider: {name}")
    
    def get_default(self) -> Optional[str]:
        """Get default provider name"""
        return self._default_provider
    
    async def health_check_all(self) -> Dict[str, ProviderStatus]:
        """Check health of all initialized providers"""
        results = {}
        
        for name, provider in self._instances.items():
            try:
                status = await provider.health_check()
                results[name] = status
            except Exception as e:
                logger.error(f"Health check failed for {name}: {e}")
                results[name] = ProviderStatus.UNAVAILABLE
        
        return results
    
    async def close_all(self):
        """Close all provider instances"""
        for name, provider in self._instances.items():
            try:
                await provider.close()
                logger.info(f"Closed provider: {name}")
            except Exception as e:
                logger.error(f"Error closing provider {name}: {e}")
        
        self._instances.clear()

# Global registry instance
_registry = None

def get_registry() -> ProviderRegistry:
    """Get the global provider registry"""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry

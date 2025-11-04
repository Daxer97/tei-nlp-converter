"""
Test resource cleanup and memory leak prevention
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from nlp_connector import NLPProcessor
from nlp_providers.base import NLPProvider, ProviderStatus
from nlp_providers.registry import ProviderRegistry


class MockProvider(NLPProvider):
    """Mock provider for testing"""

    def __init__(self, config=None, should_fail=False):
        super().__init__(config)
        self.should_fail = should_fail
        self.close_called = False
        self.initialize_called = False

    async def initialize(self) -> bool:
        self.initialize_called = True
        if self.should_fail:
            raise RuntimeError("Initialization failed")
        self._initialized = True
        return True

    async def close(self):
        """Track that close was called"""
        self.close_called = True
        self._initialized = False

    async def health_check(self) -> ProviderStatus:
        return ProviderStatus.AVAILABLE if self._initialized else ProviderStatus.UNAVAILABLE

    async def process_text(self, text: str, options=None):
        return {"entities": [], "text": text}

    def get_name(self) -> str:
        return "mock"


@pytest.fixture
def clean_registry():
    """Create a fresh registry for each test"""
    registry = ProviderRegistry()
    # Clear any existing instances
    registry._instances.clear()
    yield registry
    # Cleanup after test
    asyncio.run(registry.close_all())


@pytest.mark.asyncio
async def test_resources_tracked_during_initialization(clean_registry):
    """Test that resources are tracked as they're initialized"""
    clean_registry.register("mock1", MockProvider)
    clean_registry.register("mock2", MockProvider)

    processor = NLPProcessor(
        primary_provider="mock1",
        fallback_providers=["mock2"]
    )
    processor.registry = clean_registry

    # Before initialization, tracking list should be empty
    assert len(processor._resources_to_cleanup) == 0

    await processor.initialize_providers()

    # After initialization, both providers should be tracked
    assert len(processor._resources_to_cleanup) == 2
    assert "mock1" in processor._resources_to_cleanup
    assert "mock2" in processor._resources_to_cleanup


@pytest.mark.asyncio
async def test_partial_cleanup_on_initialization_failure(clean_registry):
    """Test that partial cleanup occurs when initialization fails"""

    # Create mock providers - second one will fail
    class FailingMockProvider(MockProvider):
        async def initialize(self) -> bool:
            self.initialize_called = True
            raise RuntimeError("Intentional initialization failure")

    clean_registry.register("mock_success", MockProvider)
    clean_registry.register("mock_fail", FailingMockProvider)

    # Track instances
    success_provider = None
    fail_provider = None

    async def mock_get_or_create(name, config=None):
        nonlocal success_provider, fail_provider
        if name == "mock_success":
            if not success_provider:
                success_provider = MockProvider()
                await success_provider.initialize()
            return success_provider
        elif name == "mock_fail":
            if not fail_provider:
                fail_provider = FailingMockProvider()
                await fail_provider.initialize()
            return fail_provider

    clean_registry.get_or_create = mock_get_or_create

    processor = NLPProcessor(
        primary_provider="mock_fail",  # Will fail
        fallback_providers=["mock_success"]  # Will succeed
    )
    processor.registry = clean_registry

    # Initialize - should succeed with fallback
    await processor.initialize_providers()

    # Should have at least one provider initialized
    assert processor._initialized
    assert "mock_success" in processor._resources_to_cleanup


@pytest.mark.asyncio
async def test_close_clears_tracking_list(clean_registry):
    """Test that close() clears the resource tracking list"""
    clean_registry.register("mock", MockProvider)

    processor = NLPProcessor(primary_provider="mock", fallback_providers=[])
    processor.registry = clean_registry

    await processor.initialize_providers()

    # Should have tracked resources
    assert len(processor._resources_to_cleanup) > 0

    await processor.close()

    # Tracking list should be cleared
    assert len(processor._resources_to_cleanup) == 0
    # Initialized flag should be reset
    assert not processor._initialized


@pytest.mark.asyncio
async def test_close_is_idempotent(clean_registry):
    """Test that close() can be called multiple times safely"""
    clean_registry.register("mock", MockProvider)

    processor = NLPProcessor(primary_provider="mock", fallback_providers=[])
    processor.registry = clean_registry

    await processor.initialize_providers()

    # Call close multiple times
    await processor.close()
    await processor.close()
    await processor.close()

    # Should not raise exceptions
    assert len(processor._resources_to_cleanup) == 0


@pytest.mark.asyncio
async def test_cleanup_continues_on_provider_close_error(clean_registry):
    """Test that cleanup continues even if one provider fails to close"""

    class FailingCloseProvider(MockProvider):
        async def close(self):
            self.close_called = True
            raise RuntimeError("Close failed")

    clean_registry.register("mock_fail", FailingCloseProvider)
    clean_registry.register("mock_success", MockProvider)

    processor = NLPProcessor(
        primary_provider="mock_success",
        fallback_providers=["mock_fail"]
    )
    processor.registry = clean_registry

    await processor.initialize_providers()

    # Close should not raise even if one provider fails
    # (Though it logs the error)
    try:
        await processor.close()
    except Exception as e:
        pytest.fail(f"close() should not raise exceptions: {e}")


@pytest.mark.asyncio
async def test_partial_cleanup_on_no_successful_inits(clean_registry):
    """Test partial cleanup when no providers initialize successfully"""

    class AlwaysFailProvider(MockProvider):
        async def initialize(self) -> bool:
            raise RuntimeError("Always fails")

    clean_registry.register("fail1", AlwaysFailProvider)
    clean_registry.register("fail2", AlwaysFailProvider)

    processor = NLPProcessor(
        primary_provider="fail1",
        fallback_providers=["fail2"]
    )
    processor.registry = clean_registry

    # Should raise RuntimeError
    with pytest.raises(RuntimeError, match="Failed to initialize any NLP provider"):
        await processor.initialize_providers()

    # Tracking list should be empty after cleanup
    assert len(processor._resources_to_cleanup) == 0


@pytest.mark.asyncio
async def test_reinitialization_cleanup(clean_registry):
    """Test that re-initialization doesn't leak resources"""
    clean_registry.register("mock", MockProvider)

    processor = NLPProcessor(primary_provider="mock", fallback_providers=[])
    processor.registry = clean_registry

    # First initialization
    await processor.initialize_providers()
    first_init_count = len(processor._resources_to_cleanup)

    # Close and re-initialize
    await processor.close()
    await processor.initialize_providers()
    second_init_count = len(processor._resources_to_cleanup)

    # Should have same number of tracked resources
    assert first_init_count == second_init_count


@pytest.mark.asyncio
async def test_concurrent_cleanup_safety(clean_registry):
    """Test that concurrent close calls are safe"""
    clean_registry.register("mock", MockProvider)

    processor = NLPProcessor(primary_provider="mock", fallback_providers=[])
    processor.registry = clean_registry

    await processor.initialize_providers()

    # Call close concurrently
    await asyncio.gather(
        processor.close(),
        processor.close(),
        processor.close()
    )

    # Should complete without errors
    assert len(processor._resources_to_cleanup) == 0


@pytest.mark.asyncio
async def test_provider_close_methods_called(clean_registry):
    """Test that provider close() methods are actually called"""
    mock_provider = MockProvider()
    mock_provider._initialized = True

    clean_registry._instances["mock"] = mock_provider

    # Call close_all on registry
    await clean_registry.close_all()

    # Provider's close method should have been called
    assert mock_provider.close_called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

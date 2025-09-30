"""
tests/test_integration.py - Comprehensive integration tests for production
"""
import pytest
import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import aiohttp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import redis
from unittest.mock import Mock, patch, AsyncMock

# Import the application and dependencies
from app import app, task_manager, storage, cache_manager
from storage import ProcessedText, BackgroundTask, TaskStatus, Base
from nlp_connector import NLPProcessor
from tei_converter import TEIConverter
from ontology_manager import OntologyManager
from security import SecurityManager
from config import settings

# Test configuration
TEST_DATABASE_URL = "sqlite:///test_db.db"
TEST_REDIS_URL = "redis://localhost:6379/15"  # Use different DB number for tests

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def test_client():
    """Create test client with test database"""
    # Override settings for testing
    settings.database_url = TEST_DATABASE_URL
    settings.redis_url = TEST_REDIS_URL
    settings.environment = "testing"
    settings.debug = True
    settings.require_auth = False
    
    # Create test database
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    
    client = TestClient(app)
    yield client
    
    # Cleanup
    Base.metadata.drop_all(engine)
    engine.dispose()

@pytest.fixture
def test_storage():
    """Create test storage instance"""
    from storage import Storage
    storage = Storage(TEST_DATABASE_URL)
    storage.init_db()
    yield storage
    storage.close()

@pytest.fixture
def test_cache():
    """Create test cache instance"""
    from cache_manager import CacheManager
    cache = CacheManager(redis_url=None, max_memory_cache=100)  # Memory only for tests
    yield cache
    cache.close()

class TestEndToEndWorkflow:
    """Test complete user workflows"""
    
    def test_simple_text_processing(self, test_client):
        """Test simple synchronous text processing"""
        response = test_client.post("/process", json={
            "text": "John Smith visited Paris last summer.",
            "domain": "default"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "completed"
        assert "nlp_results" in data
        assert "tei_xml" in data
        assert "id" in data
        
        # Verify NLP results
        nlp_results = data["nlp_results"]
        assert len(nlp_results["sentences"]) > 0
        assert len(nlp_results["entities"]) >= 2  # John Smith, Paris
        
        # Verify TEI XML
        tei_xml = data["tei_xml"]
        assert "<?xml" in tei_xml
        assert "<TEI" in tei_xml
        assert "John Smith" in tei_xml or "John" in tei_xml
        assert "Paris" in tei_xml
    
    @pytest.mark.asyncio
    async def test_large_text_background_processing(self, test_client):
        """Test background processing for large texts"""
        large_text = "This is a test sentence. " * 500  # Large text
        
        response = test_client.post("/process", json={
            "text": large_text,
            "domain": "default"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return task_id for background processing
        assert "task_id" in data
        assert data["status"] == "processing"
        
        task_id = data["task_id"]
        
        # Poll for task completion (with timeout)
        max_attempts = 30
        for attempt in range(max_attempts):
            task_response = test_client.get(f"/task/{task_id}")
            task_data = task_response.json()
            
            if task_data["status"] == "completed":
                assert "result" in task_data
                assert task_data["result"]["tei_xml"] is not None
                break
            elif task_data["status"] == "failed":
                pytest.fail(f"Task failed: {task_data.get('error')}")
            
            await asyncio.sleep(1)
        else:
            pytest.fail("Task did not complete within timeout")
    
    def test_file_upload_processing(self, test_client):
        """Test file upload and processing"""
        content = b"The European Union was established in 1993."
        
        response = test_client.post(
            "/upload",
            files={"file": ("test.txt", content, "text/plain")},
            data={"domain": "historical"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "completed"
        assert data["domain"] == "historical"
        assert "European Union" in str(data["nlp_results"])
    
    def test_processing_history(self, test_client):
        """Test processing history tracking"""
        # Process some texts
        texts = [
            "First text about science.",
            "Second text about literature.",
            "Third text about history."
        ]
        
        for text in texts:
            response = test_client.post("/process", json={
                "text": text,
                "domain": "default"
            })
            assert response.status_code == 200
        
        # Get history
        history_response = test_client.get("/history?limit=10")
        assert history_response.status_code == 200
        
        history_data = history_response.json()
        assert "items" in history_data
        assert len(history_data["items"]) >= 3
        assert history_data["total"] >= 3
    
    def test_text_deletion(self, test_client):
        """Test text deletion with ownership check"""
        # Create a text
        response = test_client.post("/process", json={
            "text": "Text to be deleted.",
            "domain": "default"
        })
        
        assert response.status_code == 200
        text_id = response.json()["id"]
        
        # Delete the text
        delete_response = test_client.delete(f"/text/{text_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["message"] == "Text deleted successfully"
        
        # Verify deletion
        history_response = test_client.get("/history")
        history_items = history_response.json()["items"]
        deleted_ids = [item["id"] for item in history_items]
        assert text_id not in deleted_ids

class TestDomainSchemas:
    """Test domain-specific schema functionality"""
    
    def test_available_domains(self, test_client):
        """Test getting available domains"""
        response = test_client.get("/domains")
        assert response.status_code == 200
        
        data = response.json()
        assert "domains" in data
        assert "schemas" in data
        
        # Check for default domains
        expected_domains = ["default", "literary", "historical", "legal", "scientific"]
        for domain in expected_domains:
            assert domain in data["domains"]
            assert domain in data["schemas"]
    
    def test_domain_specific_processing(self, test_client):
        """Test processing with different domain schemas"""
        test_cases = [
            {
                "text": "Shakespeare wrote Hamlet in 1600.",
                "domain": "literary",
                "expected_entity": "Shakespeare"
            },
            {
                "text": "The contract was signed on January 1, 2024.",
                "domain": "legal",
                "expected_text": "contract"
            },
            {
                "text": "DNA replication occurs in the S phase.",
                "domain": "scientific",
                "expected_text": "DNA"
            }
        ]
        
        for test_case in test_cases:
            response = test_client.post("/process", json={
                "text": test_case["text"],
                "domain": test_case["domain"]
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["domain"] == test_case["domain"]
            
            # Check TEI contains domain-specific elements
            tei_xml = data["tei_xml"]
            assert test_case["domain"] in tei_xml

class TestSecurityAndValidation:
    """Test security features and input validation"""
    
    def test_text_length_limit(self, test_client):
        """Test text length validation"""
        oversized_text = "x" * (settings.max_text_length + 1)
        
        response = test_client.post("/process", json={
            "text": oversized_text,
            "domain": "default"
        })
        
        assert response.status_code == 422  # Validation error
    
    def test_invalid_domain(self, test_client):
        """Test invalid domain validation"""
        response = test_client.post("/process", json={
            "text": "Test text",
            "domain": "invalid_domain_xyz"
        })
        
        assert response.status_code == 422
        assert "Invalid domain" in str(response.content)
    
    def test_xss_prevention(self, test_client):
        """Test XSS attack prevention"""
        malicious_text = "<script>alert('XSS')</script>Hello world"
        
        response = test_client.post("/process", json={
            "text": malicious_text,
            "domain": "default"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that script tags are escaped in TEI
        tei_xml = data["tei_xml"]
        assert "<script>" not in tei_xml
        assert "&lt;script&gt;" in tei_xml or "script" not in tei_xml.lower()
    
    def test_sql_injection_prevention(self, test_client):
        """Test SQL injection prevention"""
        malicious_text = "'; DROP TABLE processed_texts; --"
        
        response = test_client.post("/process", json={
            "text": malicious_text,
            "domain": "default"
        })
        
        # Should process normally without executing SQL
        assert response.status_code == 200
        
        # Verify table still exists
        history_response = test_client.get("/history")
        assert history_response.status_code == 200
    
    @pytest.mark.skipif(not settings.require_auth, reason="Auth not enabled")
    def test_authentication_required(self, test_client):
        """Test authentication requirement"""
        settings.require_auth = True
        
        response = test_client.post("/process", json={
            "text": "Test",
            "domain": "default"
        })
        
        assert response.status_code == 401
        assert "authentication" in str(response.content).lower()

class TestErrorHandlingAndRecovery:
    """Test error handling and recovery mechanisms"""
    
    @pytest.mark.asyncio
    async def test_nlp_service_failure_fallback(self, test_client, monkeypatch):
        """Test fallback when NLP service fails"""
        # Mock NLP failure
        async def mock_nlp_fail(*args, **kwargs):
            raise Exception("NLP service unavailable")
        
        with patch('nlp_connector.RemoteNLPClient.process', mock_nlp_fail):
            response = test_client.post("/process", json={
                "text": "Test text during NLP failure.",
                "domain": "default"
            })
            
            # Should still succeed with fallback processing
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"
            assert "tei_xml" in data
    
    def test_database_connection_recovery(self, test_client, test_storage):
        """Test database connection recovery"""
        # Simulate connection loss and recovery
        original_check = test_storage.check_connection
        
        # Mock connection failure
        test_storage.check_connection = Mock(return_value=False)
        
        health_response = test_client.get("/health")
        assert health_response.status_code == 200
        health_data = health_response.json()
        assert health_data["services"]["database"] == "unhealthy"
        
        # Restore connection
        test_storage.check_connection = original_check
        
        health_response = test_client.get("/health")
        health_data = health_response.json()
        assert health_data["services"]["database"] == "healthy"
    
    def test_circuit_breaker_activation(self, test_client):
        """Test circuit breaker prevents cascade failures"""
        from circuit_breaker import CircuitBreaker, CircuitBreakerError
        
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
        
        @breaker
        def failing_function():
            raise Exception("Service failure")
        
        # Trigger failures to open circuit
        for _ in range(3):
            with pytest.raises(Exception):
                failing_function()
        
        # Circuit should be open now
        with pytest.raises(CircuitBreakerError):
            failing_function()

class TestCachingAndPerformance:
    """Test caching mechanisms and performance"""
    
    def test_cache_hit_for_identical_text(self, test_client):
        """Test that identical texts are cached"""
        text = "The quick brown fox jumps over the lazy dog."
        
        # First request
        response1 = test_client.post("/process", json={
            "text": text,
            "domain": "default"
        })
        assert response1.status_code == 200
        data1 = response1.json()
        
        # Second identical request
        response2 = test_client.post("/process", json={
            "text": text,
            "domain": "default"
        })
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Results should be identical (from cache)
        assert data1["nlp_results"] == data2["nlp_results"]
        assert data1["tei_xml"] == data2["tei_xml"]
    
    def test_cache_invalidation_on_delete(self, test_client):
        """Test cache invalidation when text is deleted"""
        text = "Text for cache invalidation test."
        
        # Process text
        response = test_client.post("/process", json={
            "text": text,
            "domain": "default"
        })
        text_id = response.json()["id"]
        
        # Delete text
        test_client.delete(f"/text/{text_id}")
        
        # Reprocess - should not use cache
        response2 = test_client.post("/process", json={
            "text": text,
            "domain": "default"
        })
        
        # Should get new ID (not cached)
        assert response2.json()["id"] != text_id
    
    @pytest.mark.performance
    def test_concurrent_request_handling(self, test_client):
        """Test handling of concurrent requests"""
        import concurrent.futures
        import time
        
        def make_request(index):
            start = time.time()
            response = test_client.post("/process", json={
                "text": f"Test text number {index}",
                "domain": "default"
            })
            duration = time.time() - start
            return response.status_code, duration
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All requests should succeed
        status_codes = [r[0] for r in results]
        assert all(code == 200 for code in status_codes)
        
        # Check response times are reasonable (< 5 seconds each)
        durations = [r[1] for r in results]
        assert all(d < 5.0 for d in durations)

class TestDataRetentionAndCleanup:
    """Test data retention and cleanup policies"""
    
    def test_old_task_cleanup(self, test_storage):
        """Test cleanup of old background tasks"""
        # Create old tasks
        old_date = datetime.utcnow() - timedelta(days=10)
        
        with test_storage.get_session() as session:
            for i in range(5):
                task = BackgroundTask(
                    task_id=f"old-task-{i}",
                    status=TaskStatus.COMPLETED,
                    input_data={},
                    created_at=old_date,
                    completed_at=old_date
                )
                session.add(task)
        
        # Run cleanup
        deleted = test_storage.cleanup_old_tasks(days=7)
        assert deleted == 5
        
        # Verify cleanup
        with test_storage.get_session() as session:
            remaining = session.query(BackgroundTask).count()
            assert remaining == 0
    
    def test_data_retention_policy(self, test_storage):
        """Test data retention policy enforcement"""
        # Create old and new texts
        old_date = datetime.utcnow() - timedelta(days=100)
        new_date = datetime.utcnow() - timedelta(days=10)
        
        with test_storage.get_session() as session:
            # Old texts (should be deleted)
            for i in range(3):
                old_text = ProcessedText(
                    text=f"Old text {i}",
                    domain="default",
                    nlp_results="{}",
                    tei_xml="<TEI/>",
                    created_at=old_date
                )
                session.add(old_text)
            
            # New texts (should be kept)
            for i in range(2):
                new_text = ProcessedText(
                    text=f"New text {i}",
                    domain="default",
                    nlp_results="{}",
                    tei_xml="<TEI/>",
                    created_at=new_date
                )
                session.add(new_text)
        
        # Run cleanup with 90-day retention
        results = test_storage.cleanup_old_data(days=90)
        assert results["texts"] == 3
        
        # Verify only new texts remain
        with test_storage.get_session() as session:
            remaining = session.query(ProcessedText).count()
            assert remaining == 2

class TestMetricsAndMonitoring:
    """Test metrics and monitoring endpoints"""
    
    def test_health_endpoint(self, test_client):
        """Test health check endpoint"""
        response = test_client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "timestamp" in data
        assert "services" in data
        
        # Check service statuses
        services = data["services"]
        assert "database" in services
        assert "nlp" in services
        assert "cache" in services
    
    def test_metrics_endpoint(self, test_client):
        """Test Prometheus metrics endpoint"""
        settings.enable_metrics = True
        
        response = test_client.get("/metrics")
        assert response.status_code == 200
        
        metrics_text = response.text
        
        # Check for key metrics
        assert "tei_nlp_requests_total" in metrics_text
        assert "tei_nlp_request_duration_seconds" in metrics_text
        assert "tei_nlp_active_tasks" in metrics_text
    
    def test_statistics_endpoint(self, test_client):
        """Test statistics endpoint"""
        # Process some texts first
        for i in range(3):
            test_client.post("/process", json={
                "text": f"Test text {i}",
                "domain": "default"
            })
        
        response = test_client.get("/stats")
        assert response.status_code == 200
        
        stats = response.json()
        assert "total_texts" in stats
        assert "active_tasks" in stats
        assert "domains" in stats
        assert stats["total_texts"] >= 3

class TestLoadAndStress:
    """Load and stress testing"""
    
    @pytest.mark.slow
    @pytest.mark.skipif("not config.getoption('--run-slow')", 
                    reason="need --run-slow option to run")
    def test_load_handling(self, test_client):
        """Test system under load"""
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        num_requests = 100
        start_time = time.time()
        
        def make_request(i):
            return test_client.post("/process", json={
                "text": f"Load test text number {i}",
                "domain": "default"
            })
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_request, i) for i in range(num_requests)]
            results = []
            
            for future in as_completed(futures):
                try:
                    response = future.result()
                    results.append(response.status_code)
                except Exception as e:
                    results.append(None)
        
        duration = time.time() - start_time
        
        # Calculate success rate
        success_count = sum(1 for r in results if r == 200)
        success_rate = success_count / num_requests
        
        # Assertions
        assert success_rate >= 0.95  # At least 95% success rate
        assert duration < 60  # Complete within 60 seconds
        
        print(f"Load test: {success_count}/{num_requests} succeeded in {duration:.2f}s")

# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "performance: marks tests as performance tests"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )

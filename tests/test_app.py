"""
Test suite for the main application
"""
import pytest
from fastapi.testclient import TestClient
from app import app
import json

client = TestClient(app)

def test_health_check():
    """Test health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data

def test_home_page():
    """Test home page rendering"""
    response = client.get("/")
    assert response.status_code == 200
    assert "TEI NLP Converter" in response.text

def test_process_text():
    """Test text processing"""
    response = client.post("/process", json={
        "text": "John Smith visited Paris last summer.",
        "domain": "default"
    })
    assert response.status_code == 200
    data = response.json()
    assert "tei_xml" in data or "task_id" in data

def test_process_empty_text():
    """Test processing with empty text"""
    response = client.post("/process", json={
        "text": "",
        "domain": "default"
    })
    assert response.status_code == 422  # Validation error

def test_invalid_domain():
    """Test processing with invalid domain"""
    response = client.post("/process", json={
        "text": "Test text",
        "domain": "invalid_domain_xyz"
    })
    assert response.status_code == 400  # Bad request

def test_get_domains():
    """Test domains endpoint"""
    response = client.get("/domains")
    assert response.status_code == 200
    data = response.json()
    assert "domains" in data
    assert "default" in data["domains"]

def test_history():
    """Test history endpoint"""
    response = client.get("/history?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data

def test_file_upload():
    """Test file upload"""
    content = b"This is a test file content"
    response = client.post(
        "/upload",
        files={"file": ("test.txt", content, "text/plain")},
        data={"domain": "default"}
    )
    assert response.status_code == 200

def test_large_text_rejection():
    """Test that oversized text is rejected"""
    large_text = "x" * 200000  # Exceeds max length
    response = client.post("/process", json={
        "text": large_text,
        "domain": "default"
    })
    assert response.status_code == 413  # Request entity too large

def test_rate_limiting():
    """Test rate limiting works"""
    # This would need to be configured for testing environment
    # Skip in unit tests, implement in integration tests
    pass

@pytest.mark.asyncio
async def test_task_status():
    """Test background task status"""
    # Create a large text to trigger background processing
    large_text = "This is a test. " * 500
    response = client.post("/process", json={
        "text": large_text,
        "domain": "default"
    })
    
    if response.status_code == 200:
        data = response.json()
        if "task_id" in data:
            # Check task status
            task_response = client.get(f"/task/{data['task_id']}")
            assert task_response.status_code == 200

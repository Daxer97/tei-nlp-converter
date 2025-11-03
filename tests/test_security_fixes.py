"""
Test security fixes from technical assessment
"""
import pytest
from fastapi import HTTPException
from security import SecurityManager


def test_sanitize_domain_prevents_path_traversal():
    """Test that sanitize_domain blocks path traversal attempts"""
    security = SecurityManager("test-secret")
    allowed_domains = ["default", "medical", "literary"]

    # Test valid domains
    assert security.sanitize_domain("default", allowed_domains) == "default"
    assert security.sanitize_domain("medical", allowed_domains) == "medical"

    # Test path traversal attempts
    with pytest.raises(HTTPException) as exc:
        security.sanitize_domain("../../etc/passwd", allowed_domains)
    assert "path traversal" in str(exc.value.detail).lower()

    with pytest.raises(HTTPException) as exc:
        security.sanitize_domain("../passwords", allowed_domains)
    assert "path traversal" in str(exc.value.detail).lower()

    with pytest.raises(HTTPException) as exc:
        security.sanitize_domain("domain/subdir", allowed_domains)
    assert "path traversal" in str(exc.value.detail).lower()

    # Test null byte injection
    with pytest.raises(HTTPException) as exc:
        security.sanitize_domain("default\x00.txt", allowed_domains)
    assert "path traversal" in str(exc.value.detail).lower()

    # Test invalid domain not in allowed list
    with pytest.raises(HTTPException) as exc:
        security.sanitize_domain("malicious", allowed_domains)
    assert "invalid domain" in str(exc.value.detail).lower()


def test_sanitize_filename_prevents_path_traversal():
    """Test that sanitize_filename blocks path traversal attempts"""
    security = SecurityManager("test-secret")

    # Test valid filename
    assert security.sanitize_filename("document.txt") == "document.txt"
    assert security.sanitize_filename("my_file-123.md") == "my_file-123.md"

    # Test path traversal attempts - should extract basename
    assert security.sanitize_filename("../../etc/passwd") == "passwd"
    assert security.sanitize_filename("/etc/passwd") == "passwd"
    assert security.sanitize_filename("../malicious.txt") == "malicious.txt"

    # Test null byte injection
    with pytest.raises(HTTPException) as exc:
        security.sanitize_filename("file\x00.txt")
    assert "dangerous pattern" in str(exc.value.detail).lower()

    # Test empty filename
    with pytest.raises(HTTPException) as exc:
        security.sanitize_filename("")
    assert "cannot be empty" in str(exc.value.detail).lower()

    # Test filename that becomes empty after sanitization
    with pytest.raises(HTTPException) as exc:
        security.sanitize_filename("...")
    assert "invalid after sanitization" in str(exc.value.detail).lower()

    # Test filename too long
    with pytest.raises(HTTPException) as exc:
        security.sanitize_filename("a" * 300)
    assert "too long" in str(exc.value.detail).lower()


def test_validate_content_type():
    """Test content-type validation"""
    security = SecurityManager("test-secret")

    # Test valid content types
    assert security.validate_content_type("text/plain", "document.txt") is True
    assert security.validate_content_type("text/markdown", "doc.md") is True
    assert security.validate_content_type("text/plain; charset=utf-8", "doc.txt") is True

    # Test invalid content type
    with pytest.raises(HTTPException) as exc:
        security.validate_content_type("application/javascript", "malicious.js")
    assert "invalid content-type" in str(exc.value.detail).lower()

    with pytest.raises(HTTPException) as exc:
        security.validate_content_type("application/x-executable", "malware.exe")
    assert "invalid content-type" in str(exc.value.detail).lower()

    # Test None content-type (should pass - rely on file extension)
    assert security.validate_content_type(None, "document.txt") is True


def test_security_regression_upload_endpoint():
    """
    Regression test for upload endpoint path traversal vulnerability

    Previously, the upload endpoint did not sanitize:
    1. Domain parameter (could be ../../etc/passwd)
    2. Filename (could contain path traversal)
    3. Content-type (no validation)

    This test ensures the fix remains in place.
    """
    security = SecurityManager("test-secret")
    allowed_domains = ["default", "medical", "literary"]

    # Simulate attack attempts that should now be blocked
    attack_scenarios = [
        ("../../etc/passwd", "Should block path traversal in domain"),
        ("../passwords", "Should block parent directory access"),
        ("domain/subdir", "Should block directory separator"),
        ("malicious\x00", "Should block null byte injection"),
    ]

    for attack_domain, description in attack_scenarios:
        with pytest.raises(HTTPException, match="path traversal|invalid domain"):
            security.sanitize_domain(attack_domain, allowed_domains)

    # Filename attacks
    filename_attacks = [
        "../../etc/passwd",
        "../../../root/.ssh/id_rsa",
        "malicious\x00.txt",
    ]

    for attack_filename in filename_attacks:
        try:
            # Should either sanitize safely or raise exception
            result = security.sanitize_filename(attack_filename)
            # If it doesn't raise, ensure path components are removed
            assert ".." not in result
            assert "/" not in result
            assert "\x00" not in result
        except HTTPException:
            # Raising exception is also acceptable
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

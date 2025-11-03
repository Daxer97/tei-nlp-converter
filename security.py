"""
Security utilities and middleware
"""
import re
import hashlib
import secrets
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta
from bleach import clean
import html
from defusedxml import ElementTree as ET
from logger import get_logger

logger = get_logger(__name__)

class SecurityManager:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.algorithm = "HS256"
        
    def sanitize_text(self, text: str, max_length: int = 100000) -> str:
        """Sanitize input text to prevent injection attacks"""
        if not text:
            return ""
            
        # Check length
        if len(text) > max_length:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Text exceeds maximum length of {max_length} characters"
            )
        
        # Remove control characters except newlines and tabs
        text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
        
        # Clean HTML tags but preserve text content
        text = clean(text, tags=[], strip=True)
        
        return text
    
    def sanitize_xml(self, xml_string: str) -> str:
        """Sanitize XML to prevent XXE attacks"""
        try:
            # Parse with defusedxml to prevent XXE
            tree = ET.fromstring(xml_string.encode('utf-8'))
            # Re-serialize safely
            return ET.tostring(tree, encoding='unicode')
        except Exception as e:
            logger.error(f"XML sanitization failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid XML content"
            )
    
    def validate_domain(self, domain: str, allowed_domains: list) -> str:
        """Validate domain input"""
        if domain not in allowed_domains:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid domain. Allowed domains: {', '.join(allowed_domains)}"
            )
        return domain
    
    def escape_html(self, text: str) -> str:
        """Escape HTML for safe rendering"""
        return html.escape(text)
    
    def generate_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Generate JWT token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(hours=24)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
    
    def hash_text(self, text: str) -> str:
        """Generate hash of text for caching"""
        return hashlib.sha256(text.encode()).hexdigest()
    
    def validate_file_type(self, filename: str) -> bool:
        """Validate uploaded file type"""
        allowed_extensions = ['.txt', '.text', '.md', '.markdown']
        return any(filename.lower().endswith(ext) for ext in allowed_extensions)

    def sanitize_domain(self, domain: str, allowed_domains: list) -> str:
        """
        Sanitize domain parameter to prevent path traversal attacks

        Args:
            domain: User-provided domain string
            allowed_domains: List of allowed domain names

        Returns:
            Sanitized domain string

        Raises:
            HTTPException: If domain is invalid or contains path traversal patterns
        """
        if not domain:
            return "default"

        # Remove whitespace
        domain = domain.strip()

        # Check for path traversal patterns
        dangerous_patterns = [
            '..',      # Parent directory
            '/',       # Directory separator
            '\\',      # Windows directory separator
            '\0',      # Null byte
            '\n',      # Newline
            '\r',      # Carriage return
        ]

        for pattern in dangerous_patterns:
            if pattern in domain:
                logger.warning(f"Path traversal attempt detected in domain: {domain}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid domain name: path traversal patterns detected"
                )

        # Validate domain is alphanumeric with underscores and hyphens only
        if not re.match(r'^[a-zA-Z0-9_-]+$', domain):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid domain name: only alphanumeric characters, underscores, and hyphens allowed"
            )

        # Check against allowed domains list
        if domain not in allowed_domains:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid domain. Allowed domains: {', '.join(allowed_domains)}"
            )

        return domain

    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename to prevent path traversal and other attacks

        Args:
            filename: User-provided filename

        Returns:
            Sanitized filename (basename only)

        Raises:
            HTTPException: If filename is invalid or dangerous
        """
        if not filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename cannot be empty"
            )

        # Remove any directory path components
        import os
        filename = os.path.basename(filename)

        # Check for path traversal patterns
        dangerous_patterns = [
            '..',      # Parent directory
            '\0',      # Null byte
            '\n',      # Newline
            '\r',      # Carriage return
        ]

        for pattern in dangerous_patterns:
            if pattern in filename:
                logger.warning(f"Dangerous pattern detected in filename: {filename}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid filename: dangerous patterns detected"
                )

        # Remove leading/trailing whitespace and dots
        filename = filename.strip().strip('.')

        # Validate filename is not empty after sanitization
        if not filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename invalid after sanitization"
            )

        # Validate filename length
        if len(filename) > 255:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename too long (max 255 characters)"
            )

        return filename

    def validate_content_type(self, content_type: Optional[str], filename: str) -> bool:
        """
        Validate that content-type matches expected types for text files

        Args:
            content_type: MIME type from upload
            filename: Sanitized filename

        Returns:
            True if valid

        Raises:
            HTTPException: If content-type is invalid
        """
        # Allowed MIME types for text files
        allowed_types = [
            'text/plain',
            'text/markdown',
            'text/x-markdown',
            'application/octet-stream',  # Some browsers use this for .md files
        ]

        if not content_type:
            # If no content-type, rely on file extension validation
            return True

        # Extract base type (ignore charset)
        base_type = content_type.split(';')[0].strip().lower()

        if base_type not in allowed_types:
            logger.warning(f"Invalid content-type for file {filename}: {content_type}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid content-type '{content_type}'. Expected text file."
            )

        return True

class APIKeyAuth(HTTPBearer):
    """API Key authentication"""
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(auto_error=True)
        self.api_key = api_key
    
    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials]:
        if not self.api_key:
            return None
            
        credentials = await super().__call__(request)
        if credentials.credentials != self.api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        return credentials

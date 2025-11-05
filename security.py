"""
Security utilities and middleware
"""
import re
import hashlib
import secrets
import hmac
import asyncio
import random
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError
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
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
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

class APIKeyAuth(HTTPBearer):
    """API Key authentication"""
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(auto_error=True)
        self.api_key = api_key
    
    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials]:
        if not self.api_key:
            return None

        credentials = await super().__call__(request)

        # Use constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(credentials.credentials, self.api_key):
            # Add random delay to further obfuscate timing
            await asyncio.sleep(random.uniform(0.01, 0.05))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        return credentials

"""
middleware.py - Security and tracking middleware
"""
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
import uuid
import time
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict
from logger import get_logger
from config import settings

logger = get_logger(__name__)

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add unique request ID to each request"""
    
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = str(process_time)
        
        # Log request details
        logger.info(
            f"Request {request_id}: {request.method} {request.url.path} "
            f"- {response.status_code} - {process_time:.3f}s"
        )
        
        return response

class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """CSRF protection for state-changing requests"""
    
    def __init__(self, app, exclude_paths: list = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or ["/health", "/api/docs", "/openapi.json"]
    
    async def dispatch(self, request: Request, call_next):
        if not settings.enable_csrf:
            return await call_next(request)
        
        # Skip for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)
        
        # Skip for safe methods
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            return await call_next(request)
        
        # Check CSRF token
        token_header = request.headers.get("X-CSRF-Token")
        token_cookie = request.cookies.get("csrf_token")
        
        if not token_header or not token_cookie or token_header != token_cookie:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "CSRF token validation failed"}
            )
        
        # Validate token age
        if not self._validate_token_age(token_cookie):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "CSRF token expired"}
            )
        
        return await call_next(request)
    
    def _validate_token_age(self, token: str) -> bool:
        """Validate CSRF token age"""
        try:
            # Token format: hash:timestamp
            parts = token.split(":")
            if len(parts) != 2:
                return False
            
            timestamp = float(parts[1])
            age = time.time() - timestamp
            return age < settings.csrf_token_expiry
        except Exception:
            return False

class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Log all API access for audit trail"""
    
    def __init__(self, app, storage):
        super().__init__(app)
        self.storage = storage
    
    async def dispatch(self, request: Request, call_next):
        if not settings.enable_audit_log:
            return await call_next(request)
        
        request_id = getattr(request.state, "request_id", None)
        user_id = getattr(request.state, "user_id", None)
        
        response = await call_next(request)
        
        # Log to audit table
        try:
            self.storage.log_audit(
                action=f"{request.method} {request.url.path}",
                request_id=request_id,
                user_id=user_id,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("User-Agent"),
                status_code=response.status_code,
                metadata={
                    "query_params": dict(request.query_params),
                    "path_params": dict(request.path_params) if hasattr(request, "path_params") else {}
                }
            )
        except Exception as e:
            logger.error(f"Failed to log audit: {e}")
        
        return response

def generate_csrf_token() -> str:
    """Generate CSRF token with timestamp using secure random token"""
    token_value = secrets.token_urlsafe(32)
    timestamp = str(time.time())
    return f"{token_value}:{timestamp}"

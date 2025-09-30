"""
app.py - Production Ready FastAPI Application with fixes
"""
import time
from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Depends, BackgroundTasks, status, Response, Form
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, validator, Field
from typing import Optional, List, Dict, Any
import io
import json
import uuid
import asyncio
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import traceback

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Prometheus metrics
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

# Internal imports
from config import settings
from security import SecurityManager, APIKeyAuth
from cache_manager import CacheManager
from nlp_connector import NLPProcessor
from tei_converter import TEIConverter
from ontology_manager import OntologyManager
from storage import Storage, ProcessedText, TaskStatus, BackgroundTask
from logger import get_logger
from middleware import (
    RequestIDMiddleware, 
    CSRFProtectionMiddleware, 
    AuditLoggingMiddleware,
    generate_csrf_token
)
from metrics import (
    track_request, 
    active_tasks, 
    cache_hits, 
    cache_misses,
    get_metrics
)
from circuit_breaker import CircuitBreaker, CircuitBreakerError

# Initialize logger with request context
logger = get_logger(__name__)

# Initialize components with proper error handling and validation
try:
    security_manager = SecurityManager(settings.get('secret_key'))
    cache_manager = CacheManager(
        redis_url=settings.get('redis_url'),
        ttl=settings.get('cache_ttl', 3600),
        max_memory_cache=settings.get('max_cache_size', 10000)
    )
    storage = Storage(settings.get('database_url'))
    ontology_manager = OntologyManager()
    auth = APIKeyAuth(settings.get('api_key')) if settings.get('require_auth') else None
except Exception as e:
    logger.critical(f"Failed to initialize core components: {e}")
    raise

# Rate limiting with per-user support
def get_rate_limit_key(request: Request) -> str:
    """Get rate limit key (IP or user-based)"""
    user_id = getattr(request.state, "user_id", None)
    if user_id and settings.get('require_auth'):
        return f"user:{user_id}"
    return get_remote_address(request)

limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=[f"{settings.get('rate_limit_per_minute', 100)} per minute"]
)

# Lazy initialization for NLP processor with proper cleanup
_nlp_processor = None
_nlp_lock = asyncio.Lock()

async def get_nlp_processor() -> NLPProcessor:
    """Get or initialize the NLP processor with thread safety"""
    global _nlp_processor
    
    if _nlp_processor is None:
        async with _nlp_lock:
            if _nlp_processor is None:  # Double-check pattern
                _nlp_processor = NLPProcessor(
                    primary_provider=settings.get('nlp_provider', 'spacy'),
                    fallback_providers=settings.get('nlp_fallback_providers', ['spacy']),
                    cache_manager=cache_manager
                )
                # Initialize providers asynchronously
                await _nlp_processor.initialize_providers()
                logger.info(f"NLP processor initialized with provider: {settings.get('nlp_provider')}")
    
    return _nlp_processor

# Enhanced Background task management with persistence and recovery
class PersistentTaskManager:
    """Task manager with database persistence and recovery"""
    
    def __init__(self, storage: Storage):
        self.storage = storage
        self._active_count_cache = 0
        self._last_count_update = datetime.utcnow()
        self.max_concurrent_tasks = settings.get('max_concurrent_tasks', 10)
        self._lock = asyncio.Lock()
    
    @property
    async def active_task_count(self) -> int:
        """Get active task count with caching"""
        async with self._lock:
            # Cache the count for 5 seconds to reduce DB queries
            if (datetime.utcnow() - self._last_count_update).seconds > 5:
                stats = self.storage.get_statistics()
                self._active_count_cache = stats.get('active_tasks', 0)
                self._last_count_update = datetime.utcnow()
            return self._active_count_cache
    
    def create_task(self, task_id: str, data: Dict[str, Any], 
                   request_id: str = None) -> BackgroundTask:
        """Create a new task in database with validation"""
        if not task_id:
            task_id = str(uuid.uuid4())
        
        # Validate data
        if not isinstance(data, dict):
            raise ValueError("Task data must be a dictionary")
        
        task = self.storage.create_task(task_id, data, request_id)
        active_tasks.inc()
        logger.info(f"Created task {task_id} with request {request_id}", 
                   extra={"request_id": request_id, "task_id": task_id})
        return task
    
    def update_task(self, task_id: str, status: TaskStatus, 
                   result: Optional[Dict] = None, error: Optional[str] = None):
        """Update task status in database with proper error handling"""
        try:
            task = self.storage.update_task(task_id, status, result, error)
            
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                active_tasks.dec()
            
            logger.info(f"Updated task {task_id} to {status.value}", 
                       extra={"task_id": task_id, "status": status.value})
            return task
        except Exception as e:
            logger.error(f"Failed to update task {task_id}: {e}", 
                        extra={"task_id": task_id})
            return None
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task from database with proper error handling"""
        task = self.storage.get_task(task_id)
        if task:
            return {
                "id": task.task_id,
                "status": task.status.value,
                "data": task.input_data,
                "result": task.result,
                "error": self._sanitize_error(task.error) if task.error else None,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "duration": (task.completed_at - task.started_at).total_seconds() 
                           if task.completed_at and task.started_at else None
            }
        return None
    
    def _sanitize_error(self, error: Optional[str]) -> str:
        """Sanitize error messages for user display"""
        if not error:
            return "An unknown error occurred"
        
        if settings.get('environment') == "production":
            error_lower = error.lower()
            # More comprehensive error categorization
            error_categories = {
                "database": "A database error occurred",
                "connection": "A connection error occurred",
                "timeout": "The operation timed out",
                "nlp": "Text processing service error",
                "memory": "Insufficient resources to process request",
                "permission": "Permission denied",
                "validation": "Invalid input provided",
                "circuit": "Service temporarily unavailable"
            }
            
            for key, message in error_categories.items():
                if key in error_lower:
                    return message
            
            return "An error occurred during processing"
        return error  # Return full error in development
    
    async def cleanup_stale_tasks(self):
        """Clean up stale tasks periodically with logging"""
        while True:
            await asyncio.sleep(3600)  # Run every hour
            try:
                stale_tasks = self.storage.get_stale_tasks(hours=24)
                for task in stale_tasks:
                    self.update_task(
                        task.task_id, 
                        TaskStatus.FAILED, 
                        error="Task timeout after 24 hours"
                    )
                    logger.warning(f"Marked stale task as failed: {task.task_id}")
                
                # Clean up old completed tasks
                deleted = self.storage.cleanup_old_tasks()
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} old tasks")
                    
            except Exception as e:
                logger.error(f"Error in task cleanup: {e}", exc_info=True)
    
    async def recover_tasks(self):
        """Recover interrupted tasks on startup"""
        if not settings.get('task_recovery_on_startup', True):
            return
        
        try:
            # Find tasks that were processing when shutdown occurred
            interrupted_tasks = self.storage.get_tasks_by_status(TaskStatus.PROCESSING)
            
            for task in interrupted_tasks:
                # Mark as failed with recovery message
                self.update_task(
                    task.task_id,
                    TaskStatus.FAILED,
                    error="Task interrupted by system restart"
                )
                logger.info(f"Marked interrupted task {task.task_id} as failed")
                
        except Exception as e:
            logger.error(f"Failed to recover tasks: {e}")

# Initialize task manager
task_manager = PersistentTaskManager(storage)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle with proper error handling and recovery"""
    startup_tasks = []
    
    # Startup
    try:
        # Initialize database with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                storage.init_db()
                logger.info("Database initialized successfully")
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.critical(f"Failed to initialize database after {max_retries} attempts: {e}")
                    raise
                logger.warning(f"Database init attempt {attempt + 1} failed, retrying in {2**attempt}s...")
                await asyncio.sleep(2 ** attempt)
        
        # Recover interrupted tasks
        await task_manager.recover_tasks()
        
        # Initialize NLP processor after database is ready
        await get_nlp_processor()
        
        # Run database migrations in production
        if settings.get('environment') == "production":
            try:
                from alembic import command
                from alembic.config import Config
                alembic_cfg = Config("alembic.ini")
                command.upgrade(alembic_cfg, "head")
                logger.info("Database migrations completed")
            except ImportError:
                logger.warning("Alembic not installed, skipping migrations")
            except Exception as e:
                logger.error(f"Migration error (non-fatal): {e}")
        
        # Warm up cache with common schemas if enabled
        if settings.get('cache_warmup_on_startup', True):
            try:
                cache_manager.warmup(
                    [f"schema:{domain}" for domain in ontology_manager.get_available_domains()],
                    lambda key: ontology_manager.get_schema(key.split(':')[1])
                )
            except Exception as e:
                logger.warning(f"Cache warmup failed: {e}")
        
        logger.info(f"Application {settings.get('app_name')} v{settings.get('version')} started in {settings.get('environment')} mode")
        
        # Start background tasks
        cleanup_task = asyncio.create_task(task_manager.cleanup_stale_tasks())
        retention_task = asyncio.create_task(run_data_cleanup())
        cache_cleanup_task = asyncio.create_task(run_cache_cleanup())
        startup_tasks.extend([cleanup_task, retention_task, cache_cleanup_task])
        
    except Exception as e:
        logger.critical(f"Startup failed: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Application shutting down gracefully...")
    
    # Cancel background tasks gracefully
    for task in startup_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    # Close connections properly
    try:
        cache_manager.close()
    except Exception as e:
        logger.error(f"Error closing cache manager: {e}")
    
    try:
        storage.close()
    except Exception as e:
        logger.error(f"Error closing storage: {e}")
    
    # Close NLP processor
    if _nlp_processor:
        try:
            await _nlp_processor.close()
        except Exception as e:
            logger.error(f"Error closing NLP processor: {e}")
    
    logger.info("Shutdown complete")

async def run_data_cleanup():
    """Run periodic data cleanup based on retention policy"""
    while True:
        await asyncio.sleep(settings.get('cleanup_interval_hours', 24) * 3600)
        try:
            results = storage.cleanup_old_data()
            logger.info(f"Data cleanup completed: {results}")
        except Exception as e:
            logger.error(f"Data cleanup failed: {e}", exc_info=True)

async def run_cache_cleanup():
    """Run periodic cache cleanup"""
    while True:
        await asyncio.sleep(3600)  # Every hour
        try:
            cache_manager.clear_expired()
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")

# Initialize FastAPI app
app = FastAPI(
    title=settings.get('app_name'),
    version=settings.get('version'),
    lifespan=lifespan,
    docs_url="/api/docs" if settings.get('debug') else None,
    redoc_url="/api/redoc" if settings.get('debug') else None,
    openapi_url="/openapi.json" if settings.get('debug') else None
)

# Add middleware in correct order
app.add_middleware(RequestIDMiddleware)
app.add_middleware(AuditLoggingMiddleware, storage=storage)
app.add_middleware(CSRFProtectionMiddleware, exclude_paths=["/health", "/metrics"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get('cors_origins', []),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time"]
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
if settings.get('environment') == "production":
    app.add_middleware(
        TrustedHostMiddleware, 
        allowed_hosts=["localhost", "127.0.0.1", ".yourdomain.com"]
    )

# Session middleware for CSRF
from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(
    SessionMiddleware, 
    secret_key=settings.get('session_secret'),
    same_site="strict",
    https_only=(settings.get('environment') == "production")
)

# Add rate limit exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount static files with security
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Request/Response Models with enhanced validation
class TextProcessRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=settings.get('max_text_length', 100000))
    domain: str = Field(default="default", pattern="^[a-zA-Z0-9_-]+$", max_length=50)
    options: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    @validator('text')
    def validate_text(cls, v):
        max_length = settings.get('max_text_length', 100000)
        return security_manager.sanitize_text(v, max_length)
    
    @validator('domain')
    def validate_domain(cls, v):
        if not ontology_manager.validate_domain(v):
            raise ValueError(f"Invalid domain. Use /domains endpoint to see available options.")
        return v
    
    @validator('options')
    def validate_options(cls, v):
        # Limit options to prevent abuse
        if len(v) > 20:
            raise ValueError("Too many options provided")
        
        # Validate option types
        valid_options = {
            'include_entities', 'include_sentences', 'include_tokens',
            'include_pos', 'include_dependencies', 'include_lemmas',
            'include_noun_chunks', 'include_sentiment', 'include_embeddings'
        }
        
        invalid_keys = set(v.keys()) - valid_options
        if invalid_keys:
            raise ValueError(f"Invalid options: {invalid_keys}")
        
        return v

# Continue with remaining endpoints...
# [Rest of the corrected app.py continues with the same patterns applied throughout]

class ProcessingResponse(BaseModel):
    id: Optional[int] = None
    task_id: Optional[str] = None
    status: str
    text: Optional[str] = None
    domain: Optional[str] = None
    nlp_results: Optional[Dict] = None
    tei_xml: Optional[str] = None
    created_at: Optional[str] = None
    processing_time: Optional[float] = None
    request_id: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    environment: str
    services: Dict[str, str]

# Utility function for error responses
def create_error_response(status_code: int, detail: str, request_id: str = None) -> JSONResponse:
    """Create standardized error response"""
    content = {"detail": detail}
    if request_id:
        content["request_id"] = request_id
    
    return JSONResponse(
        status_code=status_code,
        content=content
    )

# API Routes
@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint with comprehensive service checks"""
    services = {}
    
    # Database health
    try:
        services["database"] = "healthy" if storage.check_connection() else "unhealthy"
    except Exception:
        services["database"] = "error"
    
    # NLP service health
    services["nlp"] = "healthy"  # Assumes local NLP is always available
    
    # Cache health
    cache_stats = cache_manager.get_stats()
    if cache_stats.get('redis_available'):
        services["cache"] = "redis"
    else:
        services["cache"] = "memory-only"
    
    # Determine overall status
    overall_status = "healthy"
    if any(s in ["unhealthy", "error"] for s in services.values()):
        overall_status = "unhealthy"
    elif "memory-only" in services.values():
        overall_status = "degraded"
    
    return HealthResponse(
        status=overall_status,
        version=settings.version,
        environment=settings.environment,
        timestamp=datetime.utcnow().isoformat(),
        services=services
    )

@app.get("/metrics", tags=["System"])
async def metrics():
    """Prometheus metrics endpoint"""
    if not settings.enable_metrics:
        raise HTTPException(status_code=404)
    
    return Response(content=get_metrics(), media_type=CONTENT_TYPE_LATEST)

@app.get("/", response_class=HTMLResponse, tags=["UI"])
async def home(request: Request):
    """Render the main interface with CSRF token"""
    domains = ontology_manager.get_available_domains()
    csrf_token = generate_csrf_token()
    
    response = templates.TemplateResponse("index.html", {
        "request": request,
        "domains": domains,
        "version": settings.version,
        "csrf_token": csrf_token,
        "environment": settings.environment
    })
    
    # Set secure CSRF cookie
    response.set_cookie(
        "csrf_token",
        csrf_token,
        max_age=settings.csrf_token_expiry,
        httponly=True,
        samesite="strict",
        secure=(settings.environment == "production")
    )
    
    return response

@app.post("/process", response_model=ProcessingResponse, tags=["Processing"])
@limiter.limit("10 per minute")
@track_request("POST", "/process")
async def process_text(
    request: TextProcessRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    auth_result = Depends(auth) if settings.require_auth else None
):
    """
    Process text through NLP and convert to TEI XML
    
    - Small texts: Processed synchronously
    - Large texts: Processed in background (returns task_id)
    """
    start_time = datetime.utcnow()
    request_id = getattr(req.state, "request_id", str(uuid.uuid4()))
    user_id = getattr(req.state, "user_id", "anonymous")
    
    try:
        # Check concurrent task limit
        if await task_manager.active_task_count >= settings.get('max_concurrent_tasks', 10):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Server at capacity, please try again later"
            )
        
        # Check if we should process in background
        if settings.enable_background_tasks and len(request.text) > settings.large_text_threshold:
            task_id = str(uuid.uuid4())
            
            # Create task in database
            task_manager.create_task(
                task_id,
                {
                    "text_preview": request.text[:100],
                    "text_length": len(request.text),
                    "domain": request.domain,
                    "options": request.options
                },
                request_id
            )
            
            # Schedule background processing
            background_tasks.add_task(
                process_text_background,
                task_id,
                request,
                request_id,
                user_id
            )
            
            logger.info(f"Created background task {task_id} for request {request_id}")
            
            return ProcessingResponse(
                task_id=task_id,
                status="processing",
                domain=request.domain,
                request_id=request_id
            )
        
        # Process immediately for small texts
        result = await process_text_sync(request, request_id, user_id)
        
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        # Log successful processing (audit)
        storage.log_audit(
            action="process_text",
            request_id=request_id,
            user_id=user_id,
            resource_type="text",
            resource_id=str(result.id),
            status_code=200,
            metadata={
                "domain": request.domain,
                "text_length": len(request.text),
                "processing_time": processing_time
            }
        )
        
        return ProcessingResponse(
            id=result.id,
            status="completed",
            text=result.text if settings.debug else None,
            domain=result.domain,
            nlp_results=json.loads(result.nlp_results),
            tei_xml=result.tei_xml,
            created_at=result.created_at.isoformat(),
            processing_time=processing_time,
            request_id=request_id
        )
        
    except CircuitBreakerError:
        logger.error(f"Circuit breaker open for request {request_id}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Processing service temporarily unavailable",
            headers={"Retry-After": "60"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing text for request {request_id}: {str(e)}", exc_info=settings.debug)
        
        # Log failed processing
        storage.log_audit(
            action="process_text",
            request_id=request_id,
            user_id=user_id,
            status_code=500,
            error_message=str(e) if settings.debug else "Processing error",
            metadata={
                "domain": request.domain,
                "text_length": len(request.text)
            }
        )
        
        # Return sanitized error in production
        error_detail = str(e) if settings.debug else "An error occurred during processing"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail
        )

async def process_text_sync(request: TextProcessRequest, request_id: str, user_id: str) -> ProcessedText:
    """Synchronously process text with caching and error recovery"""
    # Check cache first
    cache_key = f"processed:{security_manager.hash_text(request.text)}:{request.domain}"
    cached = cache_manager.get(cache_key)
    if cached:
        logger.info(f"Cache hit for request {request_id}")
        cache_hits.inc()
        return cached
    
    cache_misses.inc()
    
    # Process with NLP - use lazy-loaded processor
    nlp_processor = await get_nlp_processor()
    try:
        nlp_results = await nlp_processor.process(request.text, request.options)
    except Exception as e:
        logger.error(f"NLP processing failed: {e}")
        # Fallback to basic processing
        nlp_results = {
            "sentences": [{"text": request.text, "tokens": []}],
            "entities": [],
            "dependencies": [],
            "noun_chunks": [],
            "text": request.text,
            "processing_note": "Simplified processing due to service error"
        }
    
    # Get domain schema
    schema = ontology_manager.get_schema(request.domain)
    
    # Convert to TEI XML
    try:
        tei_converter = TEIConverter(schema, security_manager)
        tei_xml = tei_converter.convert(request.text, nlp_results)
    except Exception as e:
        logger.error(f"TEI conversion failed: {e}")
        # Create minimal valid TEI
        tei_xml = create_minimal_tei(request.text, request.domain, str(e) if settings.debug else None)
    
    # Store in database
    processed_text = storage.save_processed_text(
        text=request.text,
        domain=request.domain,
        nlp_results=nlp_results,
        tei_xml=tei_xml,
        text_hash=security_manager.hash_text(request.text),
        processing_time=0.0,
        request_id=request_id,
        user_id=user_id
    )
    
    # Cache the result
    cache_manager.set(cache_key, processed_text, ttl=settings.cache_ttl)
    
    return processed_text

def create_minimal_tei(text: str, domain: str, error: Optional[str] = None) -> str:
    """Create minimal valid TEI XML as fallback"""
    error_note = f"<!-- Processing error: {error} -->" if error else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Processed Text - {domain}</title>
      </titleStmt>
      <publicationStmt>
        <p>Generated by TEI NLP Converter</p>
      </publicationStmt>
      <sourceDesc>
        <p>Automated processing with fallback</p>
      </sourceDesc>
    </fileDesc>
  </teiHeader>
  <text>
    <body>
      {error_note}
      <p>{security_manager.escape_html(text)}</p>
    </body>
  </text>
</TEI>"""

async def process_text_background(task_id: str, request: TextProcessRequest, 
                                 request_id: str, user_id: str):
    """Process text in background with proper error handling and retry"""
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            task_manager.update_task(task_id, TaskStatus.PROCESSING)
            
            result = await process_text_sync(request, request_id, user_id)
            
            task_manager.update_task(
                task_id, 
                TaskStatus.COMPLETED,
                result={
                    "id": result.id,
                    "domain": result.domain,
                    "nlp_results": json.loads(result.nlp_results),
                    "tei_xml": result.tei_xml,
                    "created_at": result.created_at.isoformat()
                }
            )
            
            logger.info(f"Background task {task_id} completed successfully")
            return
            
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Background task {task_id} attempt {attempt + 1} failed: {e}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
    
    # All retries exhausted
    sanitized_error = last_error if settings.debug else "Processing failed after multiple attempts"
    task_manager.update_task(task_id, TaskStatus.FAILED, error=sanitized_error)
    logger.error(f"Background task {task_id} failed after {max_retries} attempts: {last_error}")

@app.post("/upload", response_model=ProcessingResponse, tags=["Processing"])
@limiter.limit("5 per minute")
async def upload_and_process(
    file: UploadFile = File(...),
    domain: str = Form("default"),
    background_tasks: BackgroundTasks = None,
    req: Request = None,
    auth_result = Depends(auth) if settings.require_auth else None
):
    """Upload a file and process it"""
    request_id = getattr(req.state, "request_id", str(uuid.uuid4()))
    
    # Validate file type
    if not security_manager.validate_file_type(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Supported: .txt, .md"
        )
    
    # Validate file size (100KB max)
    if file.size > 102400:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 100KB"
        )
    
    # Read file content
    try:
        content = await file.read()
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be UTF-8 encoded text"
        )
    
    # Process as regular text
    request = TextProcessRequest(text=text, domain=domain)
    return await process_text(request, background_tasks, req, auth_result)

@app.get("/download/{text_id}", tags=["Processing"])
async def download_tei(
    text_id: int,
    req: Request,
    auth_result = Depends(auth) if settings.require_auth else None
):
    """Download TEI XML for processed text"""
    user_id = getattr(req.state, "user_id", "anonymous")
    
    # Get processed text
    text = storage.get_processed_text(text_id)
    if not text:
        raise HTTPException(status_code=404, detail="Text not found")
    
    # Check ownership if auth is enabled
    if settings.require_auth and text.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Return as XML file
    return StreamingResponse(
        io.BytesIO(text.tei_xml.encode('utf-8')),
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename=tei_{text_id}.xml"
        }
    )

@app.get("/task/{task_id}", tags=["Tasks"])
async def get_task_status(task_id: str, req: Request):
    """Get status of background task"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    task["request_id"] = getattr(req.state, "request_id", None)
    return task

@app.get("/domains", tags=["Configuration"])
async def get_domains():
    """Get available ontological domains with details"""
    domains = ontology_manager.get_available_domains()
    return {
        "domains": domains,
        "schemas": {
            domain: ontology_manager.get_schema_info(domain)
            for domain in domains
        }
    }

@app.get("/history", tags=["History"])
async def get_history(
    limit: int = Field(50, ge=1, le=100),
    offset: int = Field(0, ge=0),
    domain: Optional[str] = None,
    req: Request = None,
    auth_result = Depends(auth) if settings.require_auth else None
):
    """Get processing history for current user"""
    user_id = getattr(req.state, "user_id", "anonymous")
    
    try:
        # Use the proper Storage methods
        if domain:
            texts = storage.get_texts_by_domain_and_user(domain, user_id, limit, offset)
        else:
            texts = storage.get_recent_texts_by_user(user_id, limit, offset)
        
        return {
            "items": [
                {
                    "id": t.id,
                    "text_preview": security_manager.escape_html(
                        t.text[:100] + "..." if len(t.text) > 100 else t.text
                    ),
                    "domain": t.domain,
                    "created_at": t.created_at.isoformat(),
                    "request_id": t.request_id
                }
                for t in texts
            ],
            "total": storage.count_texts_by_user(user_id, domain),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error fetching history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch history"
        )

@app.delete("/text/{text_id}", tags=["Processing"])
async def delete_text(
    text_id: int,
    req: Request,
    auth_result = Depends(auth) if settings.require_auth else None
):
    """Delete processed text (user can only delete their own)"""
    user_id = getattr(req.state, "user_id", "anonymous")
    
    # Get text to verify ownership
    text = storage.get_processed_text(text_id)
    if not text:
        raise HTTPException(status_code=404, detail="Text not found")
    
    # Check ownership
    if text.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this text")
    
    if storage.delete_text(text_id, user_id):
        # Clear from cache
        cache_key = f"processed:{text.text_hash}:{text.domain}"
        cache_manager.delete(cache_key)
        
        # Audit log
        storage.log_audit(
            action="delete_text",
            request_id=getattr(req.state, "request_id", None),
            user_id=user_id,
            resource_type="text",
            resource_id=str(text_id),
            status_code=200
        )
        
        return {"message": "Text deleted successfully", "id": text_id}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Failed to delete text"
        )

@app.get("/stats", tags=["System"])
async def get_statistics(
    req: Request,
    auth_result = Depends(auth) if settings.require_auth else None
):
    """Get application statistics"""
    user_id = getattr(req.state, "user_id", "anonymous")
    
    stats = storage.get_statistics()
    stats.update({
        "active_tasks": await task_manager.active_task_count(),
        "user_texts": storage.count_texts_by_user(user_id),
        "cache": cache_manager.get_stats()
    })
    
    # Remove sensitive information in production
    if settings.environment == "production":
        stats.pop("cache", None)
    
    return stats

# Error handlers with proper sanitization
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning(f"Validation error in request {request_id}: {str(exc)}")
    return create_error_response(
        status.HTTP_400_BAD_REQUEST,
        str(exc) if settings.debug else "Invalid input provided",
        request_id
    )

@app.exception_handler(CircuitBreakerError)
async def circuit_breaker_handler(request: Request, exc: CircuitBreakerError):
    request_id = getattr(request.state, "request_id", "unknown")
    return create_error_response(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Service temporarily unavailable. Please try again later.",
        request_id
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"Unhandled exception in request {request_id}: {str(exc)}", 
                exc_info=settings.debug)
    
    # Log to audit in production
    if settings.environment == "production":
        storage.log_audit(
            action="error",
            request_id=request_id,
            error_message="Internal server error",
            metadata={"path": str(request.url.path)}
        )
    
    return create_error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        str(exc) if settings.debug else "An unexpected error occurred",
        request_id
    )

if __name__ == "__main__":
    import uvicorn
    
    # Configure uvicorn with production settings
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
            },
        },
        "root": {
            "level": settings.log_level,
            "handlers": ["default"],
        },
    }
    
    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers if settings.environment == "production" else 1,
        log_config=log_config,
        reload=(settings.environment == "development"),
        ssl_keyfile="ssl/key.pem" if settings.environment == "production" else None,
        ssl_certfile="ssl/cert.pem" if settings.environment == "production" else None,
    )

"""
Configuration management using Pydantic Settings with safe access wrapper
"""
from pydantic_settings import BaseSettings
from typing import List, Optional, Any
import os
import secrets
from cryptography.fernet import Fernet
import base64
import hashlib

class Settings(BaseSettings):
    # Application settings
    app_name: str = "TEI NLP Converter"
    version: str = "2.1.0"
    debug: bool = False
    environment: str = "production"
    
    # Request tracking
    enable_request_id: bool = True
    enable_audit_log: bool = True
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 4
    
    # NLP settings  
    spacy_model: str = "en_core_web_sm"
    enable_gpu: bool = False
    batch_size: int = 32

    # Remote NLP Server Configuration
    nlp_server_url: str = "http://localhost:8081"
    nlp_server_timeout: int = 30
    nlp_server_api_key: Optional[str] = None
    nlp_circuit_breaker_threshold: int = 5
    nlp_circuit_breaker_timeout: int = 60
    use_remote_nlp: bool = False

    # NLP Provider Configuration
    nlp_provider: str = "spacy"
    nlp_fallback_providers: List[str] = ["spacy"]

    # DEPRECATED: Google Cloud NLP Configuration - removed in favor of local domain-specific NER models
    # Google Cloud NLP has been deprecated because:
    # 1. Generic entity recognition lacks domain-specific understanding
    # 2. Local models provide better accuracy for medical, legal, and other specialized domains
    # 3. Reduces external dependencies and improves data privacy
    # google_project_id: Optional[str] = None  # DEPRECATED
    # google_credentials_path: Optional[str] = None  # DEPRECATED
    # google_api_key: Optional[str] = None  # DEPRECATED
    
    # Database settings
    database_url: str = "sqlite:///data/tei_nlp.db"
    database_pool_size: int = 20
    database_max_overflow: int = 40
    database_pool_recycle: int = 3600
    
    # Security settings
    secret_key: str = os.environ.get("SECRET_KEY", secrets.token_urlsafe(32))
    encryption_key: str = os.environ.get("ENCRYPTION_KEY", Fernet.generate_key().decode())
    cors_origins: List[str] = ["http://localhost:3000"]
    allowed_hosts: List[str] = ["localhost", "127.0.0.1"]
    max_text_length: int = 100000
    rate_limit_per_minute: int = 100
    rate_limit_per_user: int = 200
    require_auth: bool = False
    api_key: Optional[str] = None
    enable_csrf: bool = True
    csrf_token_expiry: int = 3600
    
    # Session settings
    session_secret: str = os.environ.get("SESSION_SECRET", secrets.token_urlsafe(32))
    session_expire_minutes: int = 60
    
    # Cache settings
    redis_url: Optional[str] = "redis://localhost:6379/0"
    cache_ttl: int = 3600
    max_cache_size: int = 10000
    cache_warmup_on_startup: bool = True
    
    # Logging settings
    log_level: str = "INFO"
    log_file_max_bytes: int = 10485760
    log_file_backup_count: int = 10
    audit_log_file: str = "logs/audit.log"
    
    # Background tasks
    enable_background_tasks: bool = True
    large_text_threshold: int = 5000
    task_retention_days: int = 7
    max_concurrent_tasks: int = 10
    task_recovery_on_startup: bool = True
    
    # Data retention
    data_retention_days: int = 90
    cleanup_interval_hours: int = 24
    
    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 9090
    
    # Performance settings
    max_memory_mb: int = 1024
    request_timeout: int = 300
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"   # allow unknown env vars without error

    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._fernet = None
        self._validated = False
        self.validate_settings()
    
    def validate_settings(self):
        """Validate critical settings on startup"""
        if self._validated:
            return
            
        errors = []
        
        # Validate environment
        if self.environment not in ["development", "testing", "production"]:
            errors.append(f"Invalid environment: {self.environment}")
        
        # Validate database URL
        if not self.database_url:
            errors.append("Database URL is required")
        
        # Validate security keys in production
        if self.environment == "production":
            if len(self.secret_key) < 32:
                errors.append("Secret key must be at least 32 characters in production")
            # Check for weak/default patterns instead of exact match
            if self.secret_key.startswith("CHANGE_THIS") or self.secret_key == "default":
                errors.append("Default or weak secret key detected in production")
        
        # Validate NLP provider
        # NOTE: "google" provider removed - use local domain-specific NER models instead
        valid_providers = ["spacy", "remote"]
        if self.nlp_provider not in valid_providers:
            errors.append(f"Invalid NLP provider: {self.nlp_provider}. Valid options: {valid_providers}")
        
        if errors:
            raise ValueError(f"Configuration errors: {'; '.join(errors)}")
        
        self._validated = True
    
    @property
    def fernet(self) -> Fernet:
        """Get Fernet instance for encryption/decryption"""
        if not self._fernet:
            key = base64.urlsafe_b64encode(
                hashlib.sha256(self.encryption_key.encode()).digest()
            )
            self._fernet = Fernet(key)
        return self._fernet
    
    def encrypt_value(self, value: str) -> str:
        """Encrypt sensitive values"""
        return self.fernet.encrypt(value.encode()).decode()
    
    def decrypt_value(self, encrypted: str) -> str:
        """Decrypt sensitive values"""
        try:
            return self.fernet.decrypt(encrypted.encode()).decode()
        except Exception:
            return encrypted

class SafeSettings:
    """Safe wrapper for settings with fallback defaults"""
    
    def __init__(self, settings: Settings):
        self._settings = settings
        self._defaults = {
            "spacy_model": "en_core_web_sm",
            "nlp_provider": "spacy",
            "nlp_fallback_providers": ["spacy"],
            "cache_ttl": 3600,
            "max_cache_size": 10000,
            "log_level": "INFO",
            "environment": "production",
            "debug": False,
            "require_auth": False,
            "enable_metrics": True,
            "enable_audit_log": True,
            "task_retention_days": 7,
            "data_retention_days": 90,
            "max_text_length": 100000,
            "large_text_threshold": 5000,
            "database_pool_size": 20,
            "redis_url": None,
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Safely get setting value with fallback"""
        try:
            value = getattr(self._settings, key, None)
            if value is None:
                value = self._defaults.get(key, default)
            return value
        except Exception:
            return self._defaults.get(key, default)
    
    def __getattr__(self, key: str) -> Any:
        """Proxy attribute access with safety"""
        return self.get(key)
    
    @property
    def raw(self) -> Settings:
        """Get raw settings object"""
        return self._settings

# Initialize settings with safety wrapper
_raw_settings = Settings()
settings = SafeSettings(_raw_settings)

"""
Enhanced logging configuration with rotation and multiple handlers
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Optional
from config import settings

def get_logger(name: str, log_file: Optional[str] = None) -> logging.Logger:
    """Get configured logger instance with rotation"""
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configure logger
    logger = logging.getLogger(name)
    
    # Set log level from settings
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # Prevent duplicate logs
    if logger.handlers:
        return logger
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Console format - simpler for readability
    console_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    
    # File handler with rotation
    log_file = log_file or "tei_nlp.log"
    file_handler = RotatingFileHandler(
        log_dir / log_file,
        maxBytes=settings.log_file_max_bytes,
        backupCount=settings.log_file_backup_count
    )
    file_handler.setLevel(logging.DEBUG)  # More verbose for files
    
    # File format - more detailed
    file_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)
    
    # Error file handler
    error_handler = RotatingFileHandler(
        log_dir / "errors.log",
        maxBytes=settings.log_file_max_bytes,
        backupCount=settings.log_file_backup_count
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_format)
    
    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger

# Configure root logger for third-party libraries
def configure_root_logger():
    """Configure the root logger for third-party libraries"""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)  # Less verbose for third-party
    
    # Add a handler if none exists
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        root_logger.addHandler(handler)

# Call this when the application starts
configure_root_logger()

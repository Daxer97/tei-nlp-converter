"""
NLP Provider Exception Hierarchy

Provides structured error classification for intelligent fallback logic.
"""
from enum import Enum
from typing import Optional


class ErrorSeverity(Enum):
    """Severity levels for provider errors"""
    TRANSIENT = "transient"      # Temporary issue, retry same provider
    DEGRADED = "degraded"          # Provider working but slow/limited
    QUOTA = "quota"                # Quota/rate limit exceeded
    CONFIGURATION = "configuration"  # Invalid config/auth
    FATAL = "fatal"                # Permanent failure, switch provider


class ProviderError(Exception):
    """
    Base class for NLP provider errors with intelligent fallback support

    Attributes:
        message: Human-readable error message
        severity: ErrorSeverity level
        is_retryable: Whether same provider can be retried
        requires_fallback: Whether to switch to fallback provider
        provider_name: Name of provider that failed
        original_error: Original exception if wrapped
    """

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.FATAL,
        is_retryable: bool = False,
        requires_fallback: bool = True,
        provider_name: Optional[str] = None,
        original_error: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.is_retryable = is_retryable
        self.requires_fallback = requires_fallback
        self.provider_name = provider_name
        self.original_error = original_error

    def __str__(self):
        parts = [f"{self.severity.value.upper()}: {self.message}"]
        if self.provider_name:
            parts.append(f"(provider: {self.provider_name})")
        return " ".join(parts)


class TransientError(ProviderError):
    """
    Temporary error that should be retried with same provider

    Examples: network timeout, temporary service unavailable, rate limit (short)
    """

    def __init__(self, message: str, provider_name: Optional[str] = None, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            severity=ErrorSeverity.TRANSIENT,
            is_retryable=True,
            requires_fallback=False,  # Retry same provider first
            provider_name=provider_name,
            original_error=original_error
        )


class QuotaExceededError(ProviderError):
    """
    API quota or rate limit exceeded, switch to fallback immediately

    Examples: daily quota exceeded, burst rate limit, concurrent request limit
    """

    def __init__(self, message: str, provider_name: Optional[str] = None, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            severity=ErrorSeverity.QUOTA,
            is_retryable=False,
            requires_fallback=True,  # Switch provider immediately
            provider_name=provider_name,
            original_error=original_error
        )


class ConfigurationError(ProviderError):
    """
    Provider configuration error, switch to fallback

    Examples: invalid API key, missing credentials, wrong project ID
    """

    def __init__(self, message: str, provider_name: Optional[str] = None, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            severity=ErrorSeverity.CONFIGURATION,
            is_retryable=False,
            requires_fallback=True,  # Config won't fix itself
            provider_name=provider_name,
            original_error=original_error
        )


class FatalError(ProviderError):
    """
    Permanent provider failure, switch to fallback

    Examples: service shutdown, provider deprecated, unsupported operation
    """

    def __init__(self, message: str, provider_name: Optional[str] = None, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            severity=ErrorSeverity.FATAL,
            is_retryable=False,
            requires_fallback=True,
            provider_name=provider_name,
            original_error=original_error
        )


class DegradedPerformanceError(ProviderError):
    """
    Provider available but performing poorly (slow response, high error rate)

    Can continue using but should consider fallback
    """

    def __init__(self, message: str, provider_name: Optional[str] = None, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            severity=ErrorSeverity.DEGRADED,
            is_retryable=True,  # Can retry but may want to switch
            requires_fallback=False,  # Optional, based on policy
            provider_name=provider_name,
            original_error=original_error
        )


def classify_error(error: Exception, provider_name: Optional[str] = None) -> ProviderError:
    """
    Classify a generic exception into appropriate ProviderError subclass

    Args:
        error: Original exception to classify
        provider_name: Name of provider that raised the error

    Returns:
        ProviderError subclass instance
    """
    error_str = str(error).lower()

    # Check for quota/rate limit errors
    quota_keywords = [
        "quota", "rate limit", "too many requests", "429",
        "resource exhausted", "limit exceeded"
    ]
    if any(keyword in error_str for keyword in quota_keywords):
        return QuotaExceededError(
            f"Quota or rate limit exceeded: {error}",
            provider_name=provider_name,
            original_error=error
        )

    # Check for authentication/configuration errors
    auth_keywords = [
        "unauthorized", "forbidden", "401", "403",
        "invalid credentials", "api key", "authentication",
        "permission denied", "access denied"
    ]
    if any(keyword in error_str for keyword in auth_keywords):
        return ConfigurationError(
            f"Configuration or authentication error: {error}",
            provider_name=provider_name,
            original_error=error
        )

    # Check for transient network errors
    transient_keywords = [
        "timeout", "connection", "network", "temporary",
        "503", "502", "504", "unavailable"
    ]
    if any(keyword in error_str for keyword in transient_keywords):
        return TransientError(
            f"Transient error: {error}",
            provider_name=provider_name,
            original_error=error
        )

    # Default to fatal error
    return FatalError(
        f"Provider error: {error}",
        provider_name=provider_name,
        original_error=error
    )

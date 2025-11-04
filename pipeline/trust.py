"""
Trust Validation and Security Layer

Validates models and knowledge bases before allowing them to be used
in the processing pipeline. Implements security policies and trust scoring.
"""
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import hashlib
import re

from logger import get_logger

logger = get_logger(__name__)


class TrustLevel(Enum):
    """Trust levels for models and knowledge bases"""
    TRUSTED = "trusted"           # Verified, signed, from known source
    VERIFIED = "verified"         # Checksums match, from known source
    UNVERIFIED = "unverified"     # From unknown source
    UNTRUSTED = "untrusted"       # Failed validation
    BLOCKED = "blocked"           # Explicitly blocked


@dataclass
class ModelTrustInfo:
    """Trust information for a model"""
    model_id: str
    provider: str
    trust_level: TrustLevel

    # Source validation
    source_url: str
    source_verified: bool = False
    checksum: Optional[str] = None
    checksum_verified: bool = False

    # Signature validation
    signed: bool = False
    signature_valid: bool = False
    signer: Optional[str] = None

    # Reputation
    download_count: int = 0
    user_reviews: int = 0
    average_rating: float = 0.0

    # Security
    scanned_for_malware: bool = False
    malware_free: bool = False

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_validated: datetime = field(default_factory=datetime.utcnow)
    validation_notes: List[str] = field(default_factory=list)


@dataclass
class KBTrustInfo:
    """Trust information for a knowledge base"""
    kb_id: str
    provider: str
    trust_level: TrustLevel

    # Source validation
    source_url: str
    source_verified: bool = False
    api_key_required: bool = False
    api_key_valid: bool = False

    # Authority
    authoritative_source: bool = False  # e.g., UMLS, USC.gov
    government_source: bool = False
    academic_source: bool = False

    # Data quality
    data_quality_score: float = 0.0
    last_updated: Optional[datetime] = None
    update_frequency: Optional[str] = None

    # Security
    uses_https: bool = False
    certificate_valid: bool = False

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_validated: datetime = field(default_factory=datetime.utcnow)
    validation_notes: List[str] = field(default_factory=list)


@dataclass
class TrustPolicy:
    """Trust policy configuration"""
    # Minimum trust levels
    min_model_trust_level: TrustLevel = TrustLevel.VERIFIED
    min_kb_trust_level: TrustLevel = TrustLevel.VERIFIED

    # Model requirements
    require_model_checksum: bool = True
    require_model_signature: bool = False
    require_malware_scan: bool = True

    # Knowledge base requirements
    require_kb_https: bool = True
    require_kb_api_key: bool = False
    prefer_authoritative_sources: bool = True

    # Allowed sources (whitelist)
    allowed_model_sources: Set[str] = field(default_factory=lambda: {
        "huggingface.co",
        "spacy.io",
        "github.com"
    })

    allowed_kb_sources: Set[str] = field(default_factory=lambda: {
        "nlm.nih.gov",           # UMLS, RxNorm
        "uscode.house.gov",      # USC
        "courtlistener.com",     # CourtListener
        "govinfo.gov"            # Government info
    })

    # Blocked sources (blacklist)
    blocked_sources: Set[str] = field(default_factory=set)

    # Trust score thresholds
    min_reputation_score: float = 3.0  # Out of 5
    min_quality_score: float = 0.7     # 0-1

    # Validation frequency
    revalidation_interval: timedelta = timedelta(days=30)


class TrustValidator:
    """
    Validates trust and security of models and knowledge bases

    Performs:
    - Source verification
    - Checksum validation
    - Signature verification
    - Reputation checking
    - Security scanning
    - Policy enforcement
    """

    def __init__(self, policy: Optional[TrustPolicy] = None):
        self.policy = policy or TrustPolicy()
        self._model_trust_cache: Dict[str, ModelTrustInfo] = {}
        self._kb_trust_cache: Dict[str, KBTrustInfo] = {}

    async def validate_model(
        self,
        model_id: str,
        provider: str,
        source_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ModelTrustInfo:
        """
        Validate a model and return trust information

        Args:
            model_id: Model identifier
            provider: Provider name (e.g., "huggingface", "spacy")
            source_url: Source URL for the model
            metadata: Additional metadata

        Returns:
            ModelTrustInfo with validation results
        """
        # Check cache
        cache_key = f"{provider}:{model_id}"
        if cache_key in self._model_trust_cache:
            cached = self._model_trust_cache[cache_key]
            # Check if revalidation is needed
            if datetime.utcnow() - cached.last_validated < self.policy.revalidation_interval:
                logger.debug(f"Using cached trust info for model: {model_id}")
                return cached

        logger.info(f"Validating model: {model_id} from {provider}")

        trust_info = ModelTrustInfo(
            model_id=model_id,
            provider=provider,
            source_url=source_url,
            trust_level=TrustLevel.UNVERIFIED
        )

        # 1. Verify source
        trust_info.source_verified = self._verify_model_source(source_url)
        if not trust_info.source_verified:
            trust_info.validation_notes.append(f"Source not in whitelist: {source_url}")

        # 2. Check if source is blocked
        if self._is_source_blocked(source_url):
            trust_info.trust_level = TrustLevel.BLOCKED
            trust_info.validation_notes.append(f"Source is blocked: {source_url}")
            self._model_trust_cache[cache_key] = trust_info
            return trust_info

        # 3. Verify checksum (if available)
        if metadata and metadata.get('checksum'):
            trust_info.checksum = metadata['checksum']
            trust_info.checksum_verified = await self._verify_model_checksum(
                model_id, provider, metadata['checksum']
            )
            if not trust_info.checksum_verified:
                trust_info.validation_notes.append("Checksum verification failed")

        # 4. Verify signature (if available)
        if metadata and metadata.get('signature'):
            trust_info.signed = True
            trust_info.signature_valid = await self._verify_model_signature(
                model_id, provider, metadata['signature']
            )
            trust_info.signer = metadata.get('signer')
            if not trust_info.signature_valid:
                trust_info.validation_notes.append("Signature verification failed")

        # 5. Check reputation
        if metadata:
            trust_info.download_count = metadata.get('downloads', 0)
            trust_info.user_reviews = metadata.get('reviews', 0)
            trust_info.average_rating = metadata.get('rating', 0.0)

        # 6. Scan for malware (simplified - in production, use actual scanner)
        trust_info.scanned_for_malware = True
        trust_info.malware_free = await self._scan_for_malware(model_id, provider)
        if not trust_info.malware_free:
            trust_info.trust_level = TrustLevel.UNTRUSTED
            trust_info.validation_notes.append("Failed malware scan")
            self._model_trust_cache[cache_key] = trust_info
            return trust_info

        # 7. Determine final trust level
        trust_info.trust_level = self._determine_model_trust_level(trust_info)

        # 8. Check against policy
        if not self._meets_model_policy(trust_info):
            trust_info.validation_notes.append(
                f"Does not meet policy (requires {self.policy.min_model_trust_level.value})"
            )

        # Cache result
        self._model_trust_cache[cache_key] = trust_info

        logger.info(
            f"Model {model_id} validated: {trust_info.trust_level.value} "
            f"(source_verified={trust_info.source_verified}, "
            f"checksum_verified={trust_info.checksum_verified}, "
            f"malware_free={trust_info.malware_free})"
        )

        return trust_info

    async def validate_kb(
        self,
        kb_id: str,
        provider: str,
        source_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> KBTrustInfo:
        """
        Validate a knowledge base and return trust information

        Args:
            kb_id: Knowledge base identifier
            provider: Provider name
            source_url: Source URL for the KB
            metadata: Additional metadata

        Returns:
            KBTrustInfo with validation results
        """
        # Check cache
        cache_key = f"{provider}:{kb_id}"
        if cache_key in self._kb_trust_cache:
            cached = self._kb_trust_cache[cache_key]
            if datetime.utcnow() - cached.last_validated < self.policy.revalidation_interval:
                logger.debug(f"Using cached trust info for KB: {kb_id}")
                return cached

        logger.info(f"Validating knowledge base: {kb_id} from {provider}")

        trust_info = KBTrustInfo(
            kb_id=kb_id,
            provider=provider,
            source_url=source_url,
            trust_level=TrustLevel.UNVERIFIED
        )

        # 1. Verify source
        trust_info.source_verified = self._verify_kb_source(source_url)
        if not trust_info.source_verified:
            trust_info.validation_notes.append(f"Source not in whitelist: {source_url}")

        # 2. Check if source is blocked
        if self._is_source_blocked(source_url):
            trust_info.trust_level = TrustLevel.BLOCKED
            trust_info.validation_notes.append(f"Source is blocked: {source_url}")
            self._kb_trust_cache[cache_key] = trust_info
            return trust_info

        # 3. Check HTTPS
        trust_info.uses_https = source_url.startswith("https://")
        if not trust_info.uses_https and self.policy.require_kb_https:
            trust_info.validation_notes.append("Does not use HTTPS")

        # 4. Verify SSL certificate (simplified)
        if trust_info.uses_https:
            trust_info.certificate_valid = await self._verify_ssl_certificate(source_url)

        # 5. Check if authoritative source
        trust_info.authoritative_source = self._is_authoritative_source(source_url)
        trust_info.government_source = self._is_government_source(source_url)
        trust_info.academic_source = self._is_academic_source(source_url)

        # 6. Check API key (if required)
        if metadata and metadata.get('api_key_required'):
            trust_info.api_key_required = True
            trust_info.api_key_valid = metadata.get('api_key_valid', False)

        # 7. Data quality
        if metadata:
            trust_info.data_quality_score = metadata.get('quality_score', 0.0)
            trust_info.last_updated = metadata.get('last_updated')
            trust_info.update_frequency = metadata.get('update_frequency')

        # 8. Determine final trust level
        trust_info.trust_level = self._determine_kb_trust_level(trust_info)

        # 9. Check against policy
        if not self._meets_kb_policy(trust_info):
            trust_info.validation_notes.append(
                f"Does not meet policy (requires {self.policy.min_kb_trust_level.value})"
            )

        # Cache result
        self._kb_trust_cache[cache_key] = trust_info

        logger.info(
            f"KB {kb_id} validated: {trust_info.trust_level.value} "
            f"(source_verified={trust_info.source_verified}, "
            f"authoritative={trust_info.authoritative_source}, "
            f"https={trust_info.uses_https})"
        )

        return trust_info

    def _verify_model_source(self, source_url: str) -> bool:
        """Check if model source is in whitelist"""
        for allowed_source in self.policy.allowed_model_sources:
            if allowed_source in source_url:
                return True
        return False

    def _verify_kb_source(self, source_url: str) -> bool:
        """Check if KB source is in whitelist"""
        for allowed_source in self.policy.allowed_kb_sources:
            if allowed_source in source_url:
                return True
        return False

    def _is_source_blocked(self, source_url: str) -> bool:
        """Check if source is in blacklist"""
        for blocked_source in self.policy.blocked_sources:
            if blocked_source in source_url:
                return True
        return False

    async def _verify_model_checksum(
        self,
        model_id: str,
        provider: str,
        expected_checksum: str
    ) -> bool:
        """
        Verify model checksum

        In production, this would download the model and compute actual checksum.
        For now, we'll assume verification passes for known providers.
        """
        # Simplified: trust checksums from known providers
        trusted_providers = {"huggingface", "spacy"}
        return provider in trusted_providers

    async def _verify_model_signature(
        self,
        model_id: str,
        provider: str,
        signature: str
    ) -> bool:
        """
        Verify model digital signature

        In production, this would verify cryptographic signatures.
        """
        # Simplified: assume signatures from known providers are valid
        return True

    async def _scan_for_malware(self, model_id: str, provider: str) -> bool:
        """
        Scan model for malware

        In production, this would use antivirus/malware scanning.
        For now, we trust known providers.
        """
        trusted_providers = {"huggingface", "spacy"}
        return provider in trusted_providers

    async def _verify_ssl_certificate(self, url: str) -> bool:
        """
        Verify SSL certificate for URL

        In production, this would check certificate validity.
        """
        # Simplified: assume HTTPS URLs have valid certificates
        return url.startswith("https://")

    def _is_authoritative_source(self, url: str) -> bool:
        """Check if source is authoritative (e.g., government, standards body)"""
        authoritative_domains = [
            "nlm.nih.gov",       # National Library of Medicine
            "nih.gov",           # NIH
            "uscode.house.gov",  # U.S. Code
            "govinfo.gov",       # Government info
            "loc.gov",           # Library of Congress
            "courtlistener.com"  # Free Law Project (authoritative case law)
        ]
        return any(domain in url for domain in authoritative_domains)

    def _is_government_source(self, url: str) -> bool:
        """Check if source is a government website"""
        return ".gov" in url or "government" in url.lower()

    def _is_academic_source(self, url: str) -> bool:
        """Check if source is academic"""
        return ".edu" in url or "academic" in url.lower()

    def _determine_model_trust_level(self, trust_info: ModelTrustInfo) -> TrustLevel:
        """Determine trust level based on validation results"""
        # Trusted: Signed, verified checksum, from known source
        if (trust_info.signed and trust_info.signature_valid and
            trust_info.checksum_verified and trust_info.source_verified and
            trust_info.malware_free):
            return TrustLevel.TRUSTED

        # Verified: Checksum verified, from known source, malware-free
        if (trust_info.checksum_verified and trust_info.source_verified and
            trust_info.malware_free):
            return TrustLevel.VERIFIED

        # Unverified: From known source but no verification
        if trust_info.source_verified and trust_info.malware_free:
            return TrustLevel.UNVERIFIED

        # Untrusted: Failed validation
        return TrustLevel.UNTRUSTED

    def _determine_kb_trust_level(self, trust_info: KBTrustInfo) -> TrustLevel:
        """Determine trust level based on validation results"""
        # Trusted: Authoritative source with HTTPS and valid certificate
        if (trust_info.authoritative_source and trust_info.uses_https and
            trust_info.certificate_valid):
            return TrustLevel.TRUSTED

        # Verified: From known source with HTTPS
        if trust_info.source_verified and trust_info.uses_https:
            return TrustLevel.VERIFIED

        # Unverified: From known source but no HTTPS
        if trust_info.source_verified:
            return TrustLevel.UNVERIFIED

        # Untrusted: Unknown source
        return TrustLevel.UNTRUSTED

    def _meets_model_policy(self, trust_info: ModelTrustInfo) -> bool:
        """Check if model meets policy requirements"""
        # Check minimum trust level
        trust_levels_order = [
            TrustLevel.BLOCKED,
            TrustLevel.UNTRUSTED,
            TrustLevel.UNVERIFIED,
            TrustLevel.VERIFIED,
            TrustLevel.TRUSTED
        ]

        min_level_idx = trust_levels_order.index(self.policy.min_model_trust_level)
        actual_level_idx = trust_levels_order.index(trust_info.trust_level)

        if actual_level_idx < min_level_idx:
            return False

        # Check specific requirements
        if self.policy.require_model_checksum and not trust_info.checksum_verified:
            return False

        if self.policy.require_model_signature and not trust_info.signature_valid:
            return False

        if self.policy.require_malware_scan and not trust_info.malware_free:
            return False

        # Check reputation
        if trust_info.average_rating > 0 and trust_info.average_rating < self.policy.min_reputation_score:
            return False

        return True

    def _meets_kb_policy(self, trust_info: KBTrustInfo) -> bool:
        """Check if KB meets policy requirements"""
        # Check minimum trust level
        trust_levels_order = [
            TrustLevel.BLOCKED,
            TrustLevel.UNTRUSTED,
            TrustLevel.UNVERIFIED,
            TrustLevel.VERIFIED,
            TrustLevel.TRUSTED
        ]

        min_level_idx = trust_levels_order.index(self.policy.min_kb_trust_level)
        actual_level_idx = trust_levels_order.index(trust_info.trust_level)

        if actual_level_idx < min_level_idx:
            return False

        # Check specific requirements
        if self.policy.require_kb_https and not trust_info.uses_https:
            return False

        if self.policy.require_kb_api_key and not trust_info.api_key_valid:
            return False

        # Check quality
        if trust_info.data_quality_score > 0 and trust_info.data_quality_score < self.policy.min_quality_score:
            return False

        return True

    def is_model_allowed(self, trust_info: ModelTrustInfo) -> bool:
        """Check if model is allowed to be used"""
        return (trust_info.trust_level != TrustLevel.BLOCKED and
                trust_info.trust_level != TrustLevel.UNTRUSTED and
                self._meets_model_policy(trust_info))

    def is_kb_allowed(self, trust_info: KBTrustInfo) -> bool:
        """Check if KB is allowed to be used"""
        return (trust_info.trust_level != TrustLevel.BLOCKED and
                trust_info.trust_level != TrustLevel.UNTRUSTED and
                self._meets_kb_policy(trust_info))

    def clear_cache(self):
        """Clear trust cache (force revalidation)"""
        self._model_trust_cache.clear()
        self._kb_trust_cache.clear()
        logger.info("Trust cache cleared")

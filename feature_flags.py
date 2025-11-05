"""
Feature Flag System

Enables gradual rollout and A/B testing of new features:
- Per-user feature flags
- Per-domain feature flags
- Percentage-based rollouts
- Kill switch for emergency rollback
- Feature flag analytics
"""
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import hashlib
import json
from logger import get_logger

logger = get_logger(__name__)


class RolloutStrategy(Enum):
    """Feature flag rollout strategies"""
    ALL_USERS = "all_users"              # Enable for everyone
    NO_USERS = "no_users"                # Disable for everyone
    PERCENTAGE = "percentage"            # Enable for X% of users
    USER_LIST = "user_list"              # Enable for specific users
    DOMAIN_LIST = "domain_list"          # Enable for specific domains
    GRADUAL = "gradual"                  # Gradual percentage increase


@dataclass
class FeatureFlag:
    """Feature flag definition"""
    name: str
    description: str
    enabled: bool = False

    # Rollout strategy
    strategy: RolloutStrategy = RolloutStrategy.NO_USERS
    rollout_percentage: float = 0.0  # 0-100

    # Targeting
    enabled_users: Set[str] = field(default_factory=set)
    enabled_domains: Set[str] = field(default_factory=set)
    disabled_users: Set[str] = field(default_factory=set)

    # Gradual rollout
    gradual_start_date: Optional[datetime] = None
    gradual_end_date: Optional[datetime] = None
    gradual_start_percentage: float = 0.0
    gradual_end_percentage: float = 100.0

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None

    # Kill switch
    kill_switch_active: bool = False
    kill_switch_reason: Optional[str] = None


@dataclass
class FeatureFlagEvaluation:
    """Result of feature flag evaluation"""
    flag_name: str
    is_enabled: bool
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class FeatureFlagManager:
    """
    Manages feature flags for gradual rollouts and A/B testing

    Features:
    - Per-user targeting
    - Per-domain targeting
    - Percentage-based rollouts
    - Gradual rollout scheduling
    - Kill switches
    - Flag analytics

    Example:
        flags = FeatureFlagManager()

        # Create a flag for new pipeline
        flags.create_flag(
            "new_nlp_pipeline",
            "Use new domain-specific NLP pipeline",
            strategy=RolloutStrategy.PERCENTAGE,
            rollout_percentage=10.0  # 10% of users
        )

        # Check if enabled for user
        if flags.is_enabled("new_nlp_pipeline", user_id="user123"):
            # Use new pipeline
            result = await new_pipeline.process(text)
        else:
            # Use old pipeline
            result = await old_nlp_processor.process(text)
    """

    def __init__(self):
        self.flags: Dict[str, FeatureFlag] = {}
        self.evaluation_log: List[Dict[str, Any]] = []

    def create_flag(
        self,
        name: str,
        description: str,
        strategy: RolloutStrategy = RolloutStrategy.NO_USERS,
        rollout_percentage: float = 0.0,
        enabled_users: Optional[Set[str]] = None,
        enabled_domains: Optional[Set[str]] = None,
        created_by: Optional[str] = None
    ) -> FeatureFlag:
        """Create a new feature flag"""

        if name in self.flags:
            raise ValueError(f"Feature flag already exists: {name}")

        flag = FeatureFlag(
            name=name,
            description=description,
            enabled=True,
            strategy=strategy,
            rollout_percentage=rollout_percentage,
            enabled_users=enabled_users or set(),
            enabled_domains=enabled_domains or set(),
            created_by=created_by
        )

        self.flags[name] = flag

        logger.info(f"Created feature flag: {name} (strategy: {strategy.value})")

        return flag

    def update_flag(
        self,
        name: str,
        **updates
    ) -> FeatureFlag:
        """Update feature flag settings"""

        if name not in self.flags:
            raise ValueError(f"Feature flag not found: {name}")

        flag = self.flags[name]

        # Update fields
        for key, value in updates.items():
            if hasattr(flag, key):
                setattr(flag, key, value)

        flag.updated_at = datetime.utcnow()

        logger.info(f"Updated feature flag: {name}")

        return flag

    def delete_flag(self, name: str):
        """Delete a feature flag"""
        if name in self.flags:
            del self.flags[name]
            logger.info(f"Deleted feature flag: {name}")

    def is_enabled(
        self,
        name: str,
        user_id: Optional[str] = None,
        domain: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Check if feature flag is enabled for user/domain

        Args:
            name: Feature flag name
            user_id: User identifier
            domain: Domain identifier
            context: Additional context for evaluation

        Returns:
            True if feature is enabled, False otherwise
        """
        evaluation = self.evaluate(name, user_id, domain, context)
        return evaluation.is_enabled

    def evaluate(
        self,
        name: str,
        user_id: Optional[str] = None,
        domain: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> FeatureFlagEvaluation:
        """
        Evaluate feature flag with detailed reasoning

        Args:
            name: Feature flag name
            user_id: User identifier
            domain: Domain identifier
            context: Additional context

        Returns:
            FeatureFlagEvaluation with decision and reasoning
        """
        # Flag not found
        if name not in self.flags:
            result = FeatureFlagEvaluation(
                flag_name=name,
                is_enabled=False,
                reason="Flag not found"
            )
            self._log_evaluation(result, user_id, domain, context)
            return result

        flag = self.flags[name]

        # Flag disabled globally
        if not flag.enabled:
            result = FeatureFlagEvaluation(
                flag_name=name,
                is_enabled=False,
                reason="Flag globally disabled"
            )
            self._log_evaluation(result, user_id, domain, context)
            return result

        # Kill switch active
        if flag.kill_switch_active:
            result = FeatureFlagEvaluation(
                flag_name=name,
                is_enabled=False,
                reason=f"Kill switch active: {flag.kill_switch_reason}"
            )
            self._log_evaluation(result, user_id, domain, context)
            return result

        # Check if user is explicitly disabled
        if user_id and user_id in flag.disabled_users:
            result = FeatureFlagEvaluation(
                flag_name=name,
                is_enabled=False,
                reason="User explicitly disabled"
            )
            self._log_evaluation(result, user_id, domain, context)
            return result

        # Evaluate based on strategy
        result = self._evaluate_strategy(flag, user_id, domain, context)

        self._log_evaluation(result, user_id, domain, context)

        return result

    def _evaluate_strategy(
        self,
        flag: FeatureFlag,
        user_id: Optional[str],
        domain: Optional[str],
        context: Optional[Dict[str, Any]]
    ) -> FeatureFlagEvaluation:
        """Evaluate based on rollout strategy"""

        if flag.strategy == RolloutStrategy.ALL_USERS:
            return FeatureFlagEvaluation(
                flag_name=flag.name,
                is_enabled=True,
                reason="Enabled for all users"
            )

        elif flag.strategy == RolloutStrategy.NO_USERS:
            return FeatureFlagEvaluation(
                flag_name=flag.name,
                is_enabled=False,
                reason="Disabled for all users"
            )

        elif flag.strategy == RolloutStrategy.USER_LIST:
            if user_id and user_id in flag.enabled_users:
                return FeatureFlagEvaluation(
                    flag_name=flag.name,
                    is_enabled=True,
                    reason="User in enabled list"
                )
            else:
                return FeatureFlagEvaluation(
                    flag_name=flag.name,
                    is_enabled=False,
                    reason="User not in enabled list"
                )

        elif flag.strategy == RolloutStrategy.DOMAIN_LIST:
            if domain and domain in flag.enabled_domains:
                return FeatureFlagEvaluation(
                    flag_name=flag.name,
                    is_enabled=True,
                    reason="Domain in enabled list"
                )
            else:
                return FeatureFlagEvaluation(
                    flag_name=flag.name,
                    is_enabled=False,
                    reason="Domain not in enabled list"
                )

        elif flag.strategy == RolloutStrategy.PERCENTAGE:
            # Deterministic percentage-based rollout
            if user_id:
                user_hash = self._hash_user_id(flag.name, user_id)
                user_percentage = user_hash % 100

                if user_percentage < flag.rollout_percentage:
                    return FeatureFlagEvaluation(
                        flag_name=flag.name,
                        is_enabled=True,
                        reason=f"User in rollout ({user_percentage:.0f} < {flag.rollout_percentage:.0f}%)",
                        metadata={'user_percentage': user_percentage}
                    )
                else:
                    return FeatureFlagEvaluation(
                        flag_name=flag.name,
                        is_enabled=False,
                        reason=f"User not in rollout ({user_percentage:.0f} >= {flag.rollout_percentage:.0f}%)",
                        metadata={'user_percentage': user_percentage}
                    )
            else:
                return FeatureFlagEvaluation(
                    flag_name=flag.name,
                    is_enabled=False,
                    reason="No user ID for percentage rollout"
                )

        elif flag.strategy == RolloutStrategy.GRADUAL:
            # Calculate current percentage based on time
            current_percentage = self._calculate_gradual_percentage(flag)

            if user_id:
                user_hash = self._hash_user_id(flag.name, user_id)
                user_percentage = user_hash % 100

                if user_percentage < current_percentage:
                    return FeatureFlagEvaluation(
                        flag_name=flag.name,
                        is_enabled=True,
                        reason=f"User in gradual rollout ({user_percentage:.0f} < {current_percentage:.0f}%)",
                        metadata={
                            'user_percentage': user_percentage,
                            'current_rollout_percentage': current_percentage
                        }
                    )
                else:
                    return FeatureFlagEvaluation(
                        flag_name=flag.name,
                        is_enabled=False,
                        reason=f"User not in gradual rollout ({user_percentage:.0f} >= {current_percentage:.0f}%)",
                        metadata={
                            'user_percentage': user_percentage,
                            'current_rollout_percentage': current_percentage
                        }
                    )
            else:
                return FeatureFlagEvaluation(
                    flag_name=flag.name,
                    is_enabled=False,
                    reason="No user ID for gradual rollout"
                )

        # Unknown strategy
        return FeatureFlagEvaluation(
            flag_name=flag.name,
            is_enabled=False,
            reason=f"Unknown strategy: {flag.strategy}"
        )

    def _hash_user_id(self, flag_name: str, user_id: str) -> int:
        """Deterministic hash of user ID for consistent bucketing"""
        combined = f"{flag_name}:{user_id}"
        hash_bytes = hashlib.sha256(combined.encode()).digest()
        return int.from_bytes(hash_bytes[:4], byteorder='big')

    def _calculate_gradual_percentage(self, flag: FeatureFlag) -> float:
        """Calculate current rollout percentage for gradual strategy"""
        if not flag.gradual_start_date or not flag.gradual_end_date:
            return flag.gradual_start_percentage

        now = datetime.utcnow()

        # Before start date
        if now < flag.gradual_start_date:
            return flag.gradual_start_percentage

        # After end date
        if now >= flag.gradual_end_date:
            return flag.gradual_end_percentage

        # During gradual rollout
        total_duration = (flag.gradual_end_date - flag.gradual_start_date).total_seconds()
        elapsed = (now - flag.gradual_start_date).total_seconds()
        progress = elapsed / total_duration

        percentage_range = flag.gradual_end_percentage - flag.gradual_start_percentage
        current_percentage = flag.gradual_start_percentage + (progress * percentage_range)

        return current_percentage

    def activate_kill_switch(self, name: str, reason: str):
        """Activate kill switch for immediate rollback"""
        if name not in self.flags:
            raise ValueError(f"Feature flag not found: {name}")

        flag = self.flags[name]
        flag.kill_switch_active = True
        flag.kill_switch_reason = reason
        flag.updated_at = datetime.utcnow()

        logger.warning(f"Kill switch activated for {name}: {reason}")

    def deactivate_kill_switch(self, name: str):
        """Deactivate kill switch"""
        if name not in self.flags:
            raise ValueError(f"Feature flag not found: {name}")

        flag = self.flags[name]
        flag.kill_switch_active = False
        flag.kill_switch_reason = None
        flag.updated_at = datetime.utcnow()

        logger.info(f"Kill switch deactivated for {name}")

    def set_gradual_rollout(
        self,
        name: str,
        start_date: datetime,
        end_date: datetime,
        start_percentage: float = 0.0,
        end_percentage: float = 100.0
    ):
        """Configure gradual rollout schedule"""
        if name not in self.flags:
            raise ValueError(f"Feature flag not found: {name}")

        flag = self.flags[name]
        flag.strategy = RolloutStrategy.GRADUAL
        flag.gradual_start_date = start_date
        flag.gradual_end_date = end_date
        flag.gradual_start_percentage = start_percentage
        flag.gradual_end_percentage = end_percentage
        flag.updated_at = datetime.utcnow()

        logger.info(
            f"Configured gradual rollout for {name}: "
            f"{start_percentage}% → {end_percentage}% "
            f"from {start_date} to {end_date}"
        )

    def _log_evaluation(
        self,
        evaluation: FeatureFlagEvaluation,
        user_id: Optional[str],
        domain: Optional[str],
        context: Optional[Dict[str, Any]]
    ):
        """Log feature flag evaluation for analytics"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'flag_name': evaluation.flag_name,
            'is_enabled': evaluation.is_enabled,
            'reason': evaluation.reason,
            'user_id': user_id,
            'domain': domain,
            'context': context,
            'metadata': evaluation.metadata
        }

        self.evaluation_log.append(log_entry)

        # Keep only recent evaluations (last 10000)
        if len(self.evaluation_log) > 10000:
            self.evaluation_log = self.evaluation_log[-10000:]

    def get_flag_analytics(self, name: str) -> Dict[str, Any]:
        """Get analytics for a feature flag"""
        if name not in self.flags:
            raise ValueError(f"Feature flag not found: {name}")

        # Filter evaluations for this flag
        flag_evaluations = [
            e for e in self.evaluation_log
            if e['flag_name'] == name
        ]

        if not flag_evaluations:
            return {
                'flag_name': name,
                'total_evaluations': 0,
                'enabled_percentage': 0.0,
                'message': 'No evaluations yet'
            }

        total = len(flag_evaluations)
        enabled_count = sum(1 for e in flag_evaluations if e['is_enabled'])
        enabled_percentage = (enabled_count / total) * 100

        # User breakdown
        user_ids = set(e['user_id'] for e in flag_evaluations if e['user_id'])
        enabled_users = set(
            e['user_id'] for e in flag_evaluations
            if e['is_enabled'] and e['user_id']
        )

        # Domain breakdown
        domains = set(e['domain'] for e in flag_evaluations if e['domain'])
        enabled_domains = set(
            e['domain'] for e in flag_evaluations
            if e['is_enabled'] and e['domain']
        )

        return {
            'flag_name': name,
            'total_evaluations': total,
            'enabled_count': enabled_count,
            'disabled_count': total - enabled_count,
            'enabled_percentage': enabled_percentage,
            'unique_users': len(user_ids),
            'enabled_users': len(enabled_users),
            'unique_domains': len(domains),
            'enabled_domains': len(enabled_domains),
            'recent_evaluations': flag_evaluations[-100:]  # Last 100
        }

    def get_all_flags(self) -> Dict[str, FeatureFlag]:
        """Get all feature flags"""
        return self.flags.copy()

    def export_config(self) -> Dict[str, Any]:
        """Export feature flags configuration"""
        return {
            'flags': {
                name: {
                    'description': flag.description,
                    'enabled': flag.enabled,
                    'strategy': flag.strategy.value,
                    'rollout_percentage': flag.rollout_percentage,
                    'enabled_users': list(flag.enabled_users),
                    'enabled_domains': list(flag.enabled_domains),
                    'disabled_users': list(flag.disabled_users),
                    'kill_switch_active': flag.kill_switch_active,
                    'kill_switch_reason': flag.kill_switch_reason,
                    'created_at': flag.created_at.isoformat(),
                    'updated_at': flag.updated_at.isoformat()
                }
                for name, flag in self.flags.items()
            }
        }

    def import_config(self, config: Dict[str, Any]):
        """Import feature flags configuration"""
        for name, flag_data in config.get('flags', {}).items():
            if name not in self.flags:
                self.create_flag(
                    name=name,
                    description=flag_data['description'],
                    strategy=RolloutStrategy(flag_data['strategy']),
                    rollout_percentage=flag_data.get('rollout_percentage', 0.0),
                    enabled_users=set(flag_data.get('enabled_users', [])),
                    enabled_domains=set(flag_data.get('enabled_domains', []))
                )
            else:
                self.update_flag(
                    name=name,
                    **flag_data
                )

        logger.info(f"Imported {len(config.get('flags', {}))} feature flags")


# Global feature flag manager
_global_flag_manager: Optional[FeatureFlagManager] = None


def get_feature_flags() -> FeatureFlagManager:
    """Get or create global feature flag manager"""
    global _global_flag_manager

    if _global_flag_manager is None:
        _global_flag_manager = FeatureFlagManager()

        # Initialize default flags
        _global_flag_manager.create_flag(
            "new_nlp_pipeline",
            "Use new domain-specific NLP pipeline with model ensemble and KB enrichment",
            strategy=RolloutStrategy.PERCENTAGE,
            rollout_percentage=0.0  # Start at 0%, gradually increase
        )

        logger.info("Initialized global feature flag manager")

    return _global_flag_manager

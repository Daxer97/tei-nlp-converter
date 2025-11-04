"""
Deployment Module

Provides production rollout capabilities including feature flags,
gradual rollout, A/B testing, and rollback procedures.

Quick Start:
    from deployment import FeatureFlagManager, RolloutStrategy

    # Initialize feature flags
    flags = FeatureFlagManager()
    flags.set_flag("new_ner_model", enabled=True, rollout_percentage=10)

    # Check if feature is enabled for user
    if flags.is_enabled("new_ner_model", user_id="user123"):
        # Use new feature
        pass
"""

from .feature_flags import (
    FeatureFlagManager,
    FeatureFlag,
    FlagStatus
)

from .rollout import (
    RolloutStrategy,
    RolloutManager,
    RolloutPhase,
    RolloutResult
)

from .ab_testing import (
    ABTestManager,
    ABTest,
    TestVariant,
    TestResult
)

from .rollback import (
    RollbackManager,
    RollbackStrategy,
    RollbackResult
)

__all__ = [
    # Feature flags
    "FeatureFlagManager",
    "FeatureFlag",
    "FlagStatus",

    # Rollout
    "RolloutStrategy",
    "RolloutManager",
    "RolloutPhase",
    "RolloutResult",

    # A/B testing
    "ABTestManager",
    "ABTest",
    "TestVariant",
    "TestResult",

    # Rollback
    "RollbackManager",
    "RollbackStrategy",
    "RollbackResult",
]

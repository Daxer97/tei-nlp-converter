"""
Feature Flag System

Controls feature rollout with percentage-based targeting, user/group targeting,
and kill switches for emergency rollback.
"""
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import hashlib
import json
from pathlib import Path

from logger import get_logger

logger = get_logger(__name__)


class FlagStatus(Enum):
    """Feature flag status"""
    ENABLED = "enabled"           # Feature is enabled
    DISABLED = "disabled"         # Feature is disabled
    PERCENTAGE = "percentage"     # Enabled for percentage of users
    TARGETED = "targeted"         # Enabled for specific users/groups


@dataclass
class FeatureFlag:
    """
    Feature flag configuration

    Controls whether a feature is enabled for users/requests.
    """
    name: str
    status: FlagStatus
    description: str = ""

    # Percentage rollout (0-100)
    rollout_percentage: float = 0.0

    # User/group targeting
    enabled_users: Set[str] = field(default_factory=set)
    enabled_groups: Set[str] = field(default_factory=set)
    disabled_users: Set[str] = field(default_factory=set)

    # Conditions
    conditions: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = ""

    # Rollout tracking
    enabled_count: int = 0
    disabled_count: int = 0


class FeatureFlagManager:
    """
    Manages feature flags for gradual rollout

    Features:
    - Percentage-based rollout (e.g., enable for 10% of users)
    - User/group targeting
    - Condition-based enabling
    - Kill switches (emergency disable)
    - Flag persistence
    - Audit logging

    Example:
        manager = FeatureFlagManager()

        # Create flag
        manager.set_flag(
            "new_ner_model",
            enabled=True,
            rollout_percentage=10,
            description="New BioBERT model"
        )

        # Check if enabled for user
        if manager.is_enabled("new_ner_model", user_id="user123"):
            # Use new feature
            result = new_ner_model.process(text)
        else:
            # Use old feature
            result = old_ner_model.process(text)

        # Gradually increase rollout
        manager.set_rollout_percentage("new_ner_model", 25)
        manager.set_rollout_percentage("new_ner_model", 50)
        manager.set_rollout_percentage("new_ner_model", 100)
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize feature flag manager

        Args:
            config_path: Path to feature flag configuration file
        """
        self.config_path = config_path or Path("config/feature_flags.json")
        self._flags: Dict[str, FeatureFlag] = {}

        # Load flags from config
        self._load_flags()

    def set_flag(
        self,
        name: str,
        enabled: bool = True,
        rollout_percentage: float = 0.0,
        description: str = "",
        enabled_users: Optional[Set[str]] = None,
        enabled_groups: Optional[Set[str]] = None,
        conditions: Optional[Dict[str, Any]] = None
    ):
        """
        Set/update a feature flag

        Args:
            name: Flag name
            enabled: Whether flag is enabled
            rollout_percentage: Percentage of users to enable (0-100)
            description: Flag description
            enabled_users: Specific users to enable
            enabled_groups: Specific groups to enable
            conditions: Conditions for enabling
        """
        # Determine status
        if not enabled:
            status = FlagStatus.DISABLED
        elif rollout_percentage > 0 and rollout_percentage < 100:
            status = FlagStatus.PERCENTAGE
        elif enabled_users or enabled_groups:
            status = FlagStatus.TARGETED
        else:
            status = FlagStatus.ENABLED

        # Create or update flag
        if name in self._flags:
            flag = self._flags[name]
            flag.status = status
            flag.rollout_percentage = rollout_percentage
            flag.description = description
            flag.updated_at = datetime.utcnow()

            if enabled_users:
                flag.enabled_users = enabled_users
            if enabled_groups:
                flag.enabled_groups = enabled_groups
            if conditions:
                flag.conditions = conditions
        else:
            flag = FeatureFlag(
                name=name,
                status=status,
                description=description,
                rollout_percentage=rollout_percentage,
                enabled_users=enabled_users or set(),
                enabled_groups=enabled_groups or set(),
                conditions=conditions or {}
            )
            self._flags[name] = flag

        logger.info(
            f"Set feature flag: {name} "
            f"(status={status.value}, rollout={rollout_percentage}%)"
        )

        # Persist flags
        self._save_flags()

    def is_enabled(
        self,
        name: str,
        user_id: Optional[str] = None,
        groups: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Check if feature is enabled

        Args:
            name: Flag name
            user_id: User identifier
            groups: User groups
            context: Additional context for condition evaluation

        Returns:
            True if feature is enabled
        """
        if name not in self._flags:
            # Flag doesn't exist, default to disabled
            logger.debug(f"Feature flag not found: {name}, defaulting to disabled")
            return False

        flag = self._flags[name]

        # Check status
        if flag.status == FlagStatus.DISABLED:
            flag.disabled_count += 1
            return False

        if flag.status == FlagStatus.ENABLED:
            flag.enabled_count += 1
            return True

        # Check user blacklist
        if user_id and user_id in flag.disabled_users:
            flag.disabled_count += 1
            return False

        # Check user whitelist
        if user_id and user_id in flag.enabled_users:
            flag.enabled_count += 1
            return True

        # Check group whitelist
        if groups:
            for group in groups:
                if group in flag.enabled_groups:
                    flag.enabled_count += 1
                    return True

        # Check percentage rollout
        if flag.status == FlagStatus.PERCENTAGE:
            if user_id:
                # Use consistent hashing for user
                if self._is_in_rollout_percentage(name, user_id, flag.rollout_percentage):
                    flag.enabled_count += 1
                    return True
                else:
                    flag.disabled_count += 1
                    return False
            else:
                # No user_id, can't determine rollout
                flag.disabled_count += 1
                return False

        # Check conditions
        if flag.conditions and context:
            if self._evaluate_conditions(flag.conditions, context):
                flag.enabled_count += 1
                return True

        # Default to disabled
        flag.disabled_count += 1
        return False

    def _is_in_rollout_percentage(
        self,
        flag_name: str,
        user_id: str,
        percentage: float
    ) -> bool:
        """
        Determine if user is in rollout percentage using consistent hashing

        Args:
            flag_name: Flag name
            user_id: User identifier
            percentage: Rollout percentage (0-100)

        Returns:
            True if user is in rollout
        """
        # Create hash of flag_name + user_id
        hash_input = f"{flag_name}:{user_id}".encode('utf-8')
        hash_value = int(hashlib.md5(hash_input).hexdigest(), 16)

        # Convert to percentage (0-100)
        user_percentage = (hash_value % 100)

        return user_percentage < percentage

    def _evaluate_conditions(
        self,
        conditions: Dict[str, Any],
        context: Dict[str, Any]
    ) -> bool:
        """
        Evaluate conditions against context

        Supports:
        - Equality: {"key": "value"}
        - Comparison: {"key": {">=": 10}}
        - In: {"key": {"in": [1, 2, 3]}}
        """
        for key, condition in conditions.items():
            if key not in context:
                return False

            value = context[key]

            # Simple equality
            if not isinstance(condition, dict):
                if value != condition:
                    return False
                continue

            # Comparison operators
            for op, expected in condition.items():
                if op == "==":
                    if value != expected:
                        return False
                elif op == "!=":
                    if value == expected:
                        return False
                elif op == ">":
                    if value <= expected:
                        return False
                elif op == ">=":
                    if value < expected:
                        return False
                elif op == "<":
                    if value >= expected:
                        return False
                elif op == "<=":
                    if value > expected:
                        return False
                elif op == "in":
                    if value not in expected:
                        return False
                elif op == "not_in":
                    if value in expected:
                        return False

        return True

    def enable_flag(self, name: str):
        """Fully enable a flag (100% rollout)"""
        self.set_flag(name, enabled=True, rollout_percentage=100)

    def disable_flag(self, name: str):
        """Fully disable a flag (kill switch)"""
        self.set_flag(name, enabled=False)

    def set_rollout_percentage(self, name: str, percentage: float):
        """Update rollout percentage"""
        if name in self._flags:
            flag = self._flags[name]
            flag.rollout_percentage = percentage
            flag.status = FlagStatus.PERCENTAGE if 0 < percentage < 100 else (
                FlagStatus.ENABLED if percentage >= 100 else FlagStatus.DISABLED
            )
            flag.updated_at = datetime.utcnow()

            logger.info(f"Updated rollout percentage for {name}: {percentage}%")
            self._save_flags()
        else:
            self.set_flag(name, enabled=True, rollout_percentage=percentage)

    def add_user_to_flag(self, name: str, user_id: str):
        """Add user to flag whitelist"""
        if name in self._flags:
            self._flags[name].enabled_users.add(user_id)
            self._flags[name].updated_at = datetime.utcnow()
            self._save_flags()
            logger.info(f"Added user {user_id} to flag {name}")

    def remove_user_from_flag(self, name: str, user_id: str):
        """Remove user from flag whitelist"""
        if name in self._flags:
            self._flags[name].enabled_users.discard(user_id)
            self._flags[name].updated_at = datetime.utcnow()
            self._save_flags()
            logger.info(f"Removed user {user_id} from flag {name}")

    def add_group_to_flag(self, name: str, group: str):
        """Add group to flag whitelist"""
        if name in self._flags:
            self._flags[name].enabled_groups.add(group)
            self._flags[name].updated_at = datetime.utcnow()
            self._save_flags()
            logger.info(f"Added group {group} to flag {name}")

    def get_flag(self, name: str) -> Optional[FeatureFlag]:
        """Get flag configuration"""
        return self._flags.get(name)

    def list_flags(self) -> List[FeatureFlag]:
        """List all feature flags"""
        return list(self._flags.values())

    def get_enabled_flags(self) -> List[str]:
        """Get names of all enabled flags"""
        return [
            name for name, flag in self._flags.items()
            if flag.status != FlagStatus.DISABLED
        ]

    def get_flag_stats(self, name: str) -> Dict[str, Any]:
        """Get statistics for a flag"""
        if name not in self._flags:
            return {}

        flag = self._flags[name]

        total_checks = flag.enabled_count + flag.disabled_count
        enabled_percentage = (
            flag.enabled_count / total_checks * 100
            if total_checks > 0 else 0
        )

        return {
            "name": name,
            "status": flag.status.value,
            "rollout_percentage": flag.rollout_percentage,
            "enabled_count": flag.enabled_count,
            "disabled_count": flag.disabled_count,
            "total_checks": total_checks,
            "actual_enabled_percentage": enabled_percentage,
            "enabled_users": len(flag.enabled_users),
            "enabled_groups": len(flag.enabled_groups)
        }

    def _load_flags(self):
        """Load flags from configuration file"""
        if not self.config_path.exists():
            logger.info(f"No feature flag config found at {self.config_path}")
            return

        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)

            for flag_data in data.get("flags", []):
                flag = FeatureFlag(
                    name=flag_data["name"],
                    status=FlagStatus(flag_data["status"]),
                    description=flag_data.get("description", ""),
                    rollout_percentage=flag_data.get("rollout_percentage", 0.0),
                    enabled_users=set(flag_data.get("enabled_users", [])),
                    enabled_groups=set(flag_data.get("enabled_groups", [])),
                    disabled_users=set(flag_data.get("disabled_users", [])),
                    conditions=flag_data.get("conditions", {}),
                    created_at=datetime.fromisoformat(flag_data["created_at"]),
                    updated_at=datetime.fromisoformat(flag_data["updated_at"]),
                    created_by=flag_data.get("created_by", "")
                )
                self._flags[flag.name] = flag

            logger.info(f"Loaded {len(self._flags)} feature flags from {self.config_path}")

        except Exception as e:
            logger.error(f"Error loading feature flags: {e}")

    def _save_flags(self):
        """Save flags to configuration file"""
        try:
            # Create directory if it doesn't exist
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "flags": [
                    {
                        "name": flag.name,
                        "status": flag.status.value,
                        "description": flag.description,
                        "rollout_percentage": flag.rollout_percentage,
                        "enabled_users": list(flag.enabled_users),
                        "enabled_groups": list(flag.enabled_groups),
                        "disabled_users": list(flag.disabled_users),
                        "conditions": flag.conditions,
                        "created_at": flag.created_at.isoformat(),
                        "updated_at": flag.updated_at.isoformat(),
                        "created_by": flag.created_by
                    }
                    for flag in self._flags.values()
                ]
            }

            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving feature flags: {e}")


# Global feature flag manager instance
_global_manager: Optional[FeatureFlagManager] = None


def get_global_flag_manager() -> FeatureFlagManager:
    """Get global feature flag manager (singleton)"""
    global _global_manager

    if _global_manager is None:
        _global_manager = FeatureFlagManager()
        logger.info("Created global feature flag manager")

    return _global_manager

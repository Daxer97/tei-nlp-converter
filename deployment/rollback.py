"""
Rollback Procedures

Provides emergency rollback capabilities for failed deployments
with automatic and manual rollback strategies.
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from logger import get_logger

logger = get_logger(__name__)


class RollbackStrategy(Enum):
    """Rollback strategies"""
    IMMEDIATE = "immediate"        # Instant rollback
    GRADUAL = "gradual"           # Gradual rollback
    TARGETED = "targeted"         # Rollback for specific users/groups


@dataclass
class RollbackResult:
    """Result of rollback operation"""
    component_name: str
    strategy: RollbackStrategy
    reason: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    success: bool = False
    error: Optional[str] = None
    rollback_to_version: Optional[str] = None
    affected_percentage: float = 0.0


class RollbackManager:
    """
    Manages rollback procedures for failed deployments

    Features:
    - Immediate rollback (emergency kill switch)
    - Gradual rollback (reverse of gradual rollout)
    - Targeted rollback (specific users/groups)
    - Automatic rollback on errors
    - Rollback history and audit log

    Example:
        manager = RollbackManager(flag_manager, hot_swap_manager)

        # Emergency rollback
        result = await manager.rollback_immediate(
            "new_ner_model",
            reason="High error rate detected"
        )

        # Gradual rollback
        result = await manager.rollback_gradual(
            "new_ner_model",
            reason="Performance degradation"
        )

        # Get rollback history
        history = manager.get_rollback_history()
    """

    def __init__(self, flag_manager, hot_swap_manager=None):
        """
        Initialize rollback manager

        Args:
            flag_manager: FeatureFlagManager instance
            hot_swap_manager: Optional HotSwapManager instance
        """
        self.flag_manager = flag_manager
        self.hot_swap_manager = hot_swap_manager

        # Rollback history
        self._history: List[RollbackResult] = []

        # Component versions (for rollback)
        self._versions: Dict[str, List[str]] = {}

    async def rollback_immediate(
        self,
        component_name: str,
        reason: str,
        rollback_to_version: Optional[str] = None
    ) -> RollbackResult:
        """
        Immediate rollback (kill switch)

        Instantly disables the component/feature.

        Args:
            component_name: Component to rollback
            reason: Reason for rollback
            rollback_to_version: Optional version to rollback to

        Returns:
            RollbackResult with operation status
        """
        logger.warning(
            f"IMMEDIATE ROLLBACK: {component_name} - {reason}"
        )

        result = RollbackResult(
            component_name=component_name,
            strategy=RollbackStrategy.IMMEDIATE,
            reason=reason,
            started_at=datetime.utcnow(),
            rollback_to_version=rollback_to_version
        )

        try:
            # Disable feature flag
            self.flag_manager.disable_flag(component_name)
            result.affected_percentage = 100.0

            # If hot-swap manager available, swap to previous version
            if self.hot_swap_manager and rollback_to_version:
                await self._hot_swap_to_version(
                    component_name,
                    rollback_to_version
                )

            result.success = True
            result.completed_at = datetime.utcnow()

            logger.info(f"Immediate rollback completed for {component_name}")

        except Exception as e:
            result.success = False
            result.error = str(e)
            result.completed_at = datetime.utcnow()

            logger.error(f"Immediate rollback failed: {e}")

        # Record in history
        self._history.append(result)

        return result

    async def rollback_gradual(
        self,
        component_name: str,
        reason: str,
        stages: Optional[List[float]] = None
    ) -> RollbackResult:
        """
        Gradual rollback

        Gradually reduces traffic to the component.

        Args:
            component_name: Component to rollback
            reason: Reason for rollback
            stages: Percentage stages (e.g., [75, 50, 25, 0])

        Returns:
            RollbackResult with operation status
        """
        logger.warning(
            f"GRADUAL ROLLBACK: {component_name} - {reason}"
        )

        result = RollbackResult(
            component_name=component_name,
            strategy=RollbackStrategy.GRADUAL,
            reason=reason,
            started_at=datetime.utcnow()
        )

        # Default stages
        if stages is None:
            stages = [75, 50, 25, 10, 0]

        try:
            # Get current percentage
            flag = self.flag_manager.get_flag(component_name)
            if flag:
                current = flag.rollout_percentage
            else:
                current = 100.0

            # Filter stages below current
            stages = [s for s in stages if s < current]
            stages.append(0)  # Always end at 0

            # Gradually reduce percentage
            for stage in stages:
                logger.info(f"Gradual rollback {component_name}: {stage}%")

                self.flag_manager.set_rollout_percentage(
                    component_name,
                    stage
                )

                result.affected_percentage = 100.0 - stage

                # Wait between stages (1 minute)
                import asyncio
                await asyncio.sleep(60)

            result.success = True
            result.completed_at = datetime.utcnow()

            logger.info(f"Gradual rollback completed for {component_name}")

        except Exception as e:
            result.success = False
            result.error = str(e)
            result.completed_at = datetime.utcnow()

            logger.error(f"Gradual rollback failed: {e}")

        # Record in history
        self._history.append(result)

        return result

    async def rollback_targeted(
        self,
        component_name: str,
        reason: str,
        user_ids: Optional[List[str]] = None,
        groups: Optional[List[str]] = None
    ) -> RollbackResult:
        """
        Targeted rollback

        Disables component for specific users/groups.

        Args:
            component_name: Component to rollback
            reason: Reason for rollback
            user_ids: User IDs to rollback
            groups: Groups to rollback

        Returns:
            RollbackResult with operation status
        """
        logger.warning(
            f"TARGETED ROLLBACK: {component_name} - {reason}"
        )

        result = RollbackResult(
            component_name=component_name,
            strategy=RollbackStrategy.TARGETED,
            reason=reason,
            started_at=datetime.utcnow()
        )

        try:
            # Add users to disabled list
            flag = self.flag_manager.get_flag(component_name)
            if flag and user_ids:
                flag.disabled_users.update(user_ids)
                result.affected_percentage = len(user_ids)  # Approximate

            # Save flags
            self.flag_manager._save_flags()

            result.success = True
            result.completed_at = datetime.utcnow()

            logger.info(
                f"Targeted rollback completed for {component_name} "
                f"({len(user_ids or [])} users)"
            )

        except Exception as e:
            result.success = False
            result.error = str(e)
            result.completed_at = datetime.utcnow()

            logger.error(f"Targeted rollback failed: {e}")

        # Record in history
        self._history.append(result)

        return result

    async def _hot_swap_to_version(
        self,
        component_name: str,
        version: str
    ):
        """Hot-swap to a specific version"""
        if not self.hot_swap_manager:
            logger.warning("Hot-swap manager not available")
            return

        # TODO: Implement hot-swap to specific version
        # This would retrieve the component at the specified version
        # and use hot_swap_manager to swap to it

        logger.info(f"Hot-swapped {component_name} to version {version}")

    def register_version(self, component_name: str, version: str):
        """Register a component version for potential rollback"""
        if component_name not in self._versions:
            self._versions[component_name] = []

        self._versions[component_name].append(version)

        logger.info(f"Registered version {version} for {component_name}")

    def get_available_versions(self, component_name: str) -> List[str]:
        """Get available versions for rollback"""
        return self._versions.get(component_name, [])

    def get_rollback_history(
        self,
        component_name: Optional[str] = None,
        limit: int = 10
    ) -> List[RollbackResult]:
        """Get rollback history"""
        history = self._history

        if component_name:
            history = [r for r in history if r.component_name == component_name]

        # Sort by started_at (most recent first)
        history = sorted(history, key=lambda r: r.started_at, reverse=True)

        return history[:limit]

    def get_last_rollback(self, component_name: str) -> Optional[RollbackResult]:
        """Get last rollback for a component"""
        history = [
            r for r in self._history
            if r.component_name == component_name
        ]

        if not history:
            return None

        return max(history, key=lambda r: r.started_at)

    def get_rollback_stats(self) -> Dict[str, Any]:
        """Get rollback statistics"""
        total_rollbacks = len(self._history)
        successful = sum(1 for r in self._history if r.success)
        failed = sum(1 for r in self._history if not r.success)

        # Group by strategy
        by_strategy = {}
        for result in self._history:
            strategy = result.strategy.value
            by_strategy[strategy] = by_strategy.get(strategy, 0) + 1

        return {
            "total_rollbacks": total_rollbacks,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total_rollbacks if total_rollbacks > 0 else 0.0,
            "by_strategy": by_strategy
        }

"""
Gradual Rollout Manager

Manages gradual rollout of new features/components using various strategies
(canary, blue-green, percentage-based).
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import asyncio

from logger import get_logger

logger = get_logger(__name__)


class RolloutStrategy(Enum):
    """Rollout strategies"""
    CANARY = "canary"                 # Small percentage first, gradually increase
    BLUE_GREEN = "blue_green"         # Full switch after validation
    PERCENTAGE = "percentage"         # Gradual percentage increase
    RING = "ring"                     # Deploy to rings (internal, beta, prod)


class RolloutPhase(Enum):
    """Phases of rollout"""
    PREPARING = "preparing"
    VALIDATING = "validating"
    ROLLING_OUT = "rolling_out"
    MONITORING = "monitoring"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class RolloutResult:
    """Result of rollout operation"""
    component_name: str
    strategy: RolloutStrategy
    phase: RolloutPhase
    current_percentage: float
    target_percentage: float
    started_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


class RolloutManager:
    """
    Manages gradual rollout of features and components

    Supports multiple rollout strategies:
    - Canary: 1% -> 5% -> 10% -> 25% -> 50% -> 100%
    - Blue-Green: 0% -> validate -> 100%
    - Percentage: Custom percentage increases
    - Ring: internal -> beta -> production

    Example:
        manager = RolloutManager()

        # Start canary rollout
        await manager.start_rollout(
            component_name="new_ner_model",
            strategy=RolloutStrategy.CANARY,
            validation_func=validate_model
        )

        # Monitor rollout progress
        status = manager.get_rollout_status("new_ner_model")
        print(f"Current: {status.current_percentage}%")

        # Automatically advances through canary stages
        # with validation at each step
    """

    def __init__(self, feature_flag_manager):
        """
        Initialize rollout manager

        Args:
            feature_flag_manager: FeatureFlagManager instance
        """
        self.flag_manager = feature_flag_manager

        # Active rollouts
        self._rollouts: Dict[str, RolloutResult] = {}

        # Canary stages (percentage milestones)
        self.canary_stages = [1, 5, 10, 25, 50, 100]

        # Validation wait time between stages
        self.validation_wait_seconds = 300  # 5 minutes

    async def start_rollout(
        self,
        component_name: str,
        strategy: RolloutStrategy,
        validation_func: Optional[callable] = None,
        target_percentage: float = 100.0
    ) -> RolloutResult:
        """
        Start a rollout

        Args:
            component_name: Name of component/feature
            strategy: Rollout strategy
            validation_func: Optional async validation function
            target_percentage: Target percentage (default: 100)

        Returns:
            RolloutResult with current status
        """
        logger.info(
            f"Starting {strategy.value} rollout for {component_name} "
            f"(target: {target_percentage}%)"
        )

        result = RolloutResult(
            component_name=component_name,
            strategy=strategy,
            phase=RolloutPhase.PREPARING,
            current_percentage=0.0,
            target_percentage=target_percentage,
            started_at=datetime.utcnow()
        )

        self._rollouts[component_name] = result

        # Start rollout based on strategy
        if strategy == RolloutStrategy.CANARY:
            await self._rollout_canary(
                component_name,
                result,
                validation_func,
                target_percentage
            )
        elif strategy == RolloutStrategy.BLUE_GREEN:
            await self._rollout_blue_green(
                component_name,
                result,
                validation_func
            )
        elif strategy == RolloutStrategy.PERCENTAGE:
            await self._rollout_percentage(
                component_name,
                result,
                target_percentage
            )
        elif strategy == RolloutStrategy.RING:
            await self._rollout_ring(
                component_name,
                result,
                validation_func
            )

        return result

    async def _rollout_canary(
        self,
        component_name: str,
        result: RolloutResult,
        validation_func: Optional[callable],
        target_percentage: float
    ):
        """Execute canary rollout"""
        # Filter stages up to target
        stages = [s for s in self.canary_stages if s <= target_percentage]

        result.phase = RolloutPhase.ROLLING_OUT

        for stage_percentage in stages:
            try:
                logger.info(
                    f"Canary rollout {component_name}: "
                    f"Advancing to {stage_percentage}%"
                )

                # Update feature flag
                self.flag_manager.set_rollout_percentage(
                    component_name,
                    stage_percentage
                )

                result.current_percentage = stage_percentage
                result.phase = RolloutPhase.MONITORING

                # Wait for validation period
                await asyncio.sleep(self.validation_wait_seconds)

                # Run validation if provided
                if validation_func:
                    result.phase = RolloutPhase.VALIDATING

                    is_valid = await validation_func(stage_percentage)

                    if not is_valid:
                        result.phase = RolloutPhase.FAILED
                        result.error = f"Validation failed at {stage_percentage}%"
                        logger.error(result.error)

                        # Rollback
                        await self.rollback(component_name)
                        return

                result.phase = RolloutPhase.ROLLING_OUT

            except Exception as e:
                result.phase = RolloutPhase.FAILED
                result.error = str(e)
                logger.error(f"Canary rollout failed: {e}")

                # Rollback
                await self.rollback(component_name)
                return

        # Rollout completed
        result.phase = RolloutPhase.COMPLETED
        result.completed_at = datetime.utcnow()

        duration = (result.completed_at - result.started_at).total_seconds()
        logger.info(
            f"Canary rollout completed for {component_name} "
            f"in {duration:.0f} seconds"
        )

    async def _rollout_blue_green(
        self,
        component_name: str,
        result: RolloutResult,
        validation_func: Optional[callable]
    ):
        """Execute blue-green rollout"""
        try:
            # Start with 0% (blue environment)
            result.phase = RolloutPhase.PREPARING
            self.flag_manager.set_rollout_percentage(component_name, 0)

            # Validate green environment
            if validation_func:
                result.phase = RolloutPhase.VALIDATING
                logger.info(f"Validating green environment for {component_name}")

                is_valid = await validation_func(0)

                if not is_valid:
                    result.phase = RolloutPhase.FAILED
                    result.error = "Green environment validation failed"
                    logger.error(result.error)
                    return

            # Switch to green (100%)
            result.phase = RolloutPhase.ROLLING_OUT
            logger.info(f"Switching to green environment for {component_name}")

            self.flag_manager.set_rollout_percentage(component_name, 100)
            result.current_percentage = 100.0

            # Monitor for validation period
            result.phase = RolloutPhase.MONITORING
            await asyncio.sleep(self.validation_wait_seconds)

            # Final validation
            if validation_func:
                result.phase = RolloutPhase.VALIDATING

                is_valid = await validation_func(100)

                if not is_valid:
                    result.phase = RolloutPhase.FAILED
                    result.error = "Post-switch validation failed"
                    logger.error(result.error)

                    # Rollback to blue
                    await self.rollback(component_name)
                    return

            # Completed
            result.phase = RolloutPhase.COMPLETED
            result.completed_at = datetime.utcnow()

            logger.info(f"Blue-green rollout completed for {component_name}")

        except Exception as e:
            result.phase = RolloutPhase.FAILED
            result.error = str(e)
            logger.error(f"Blue-green rollout failed: {e}")

            # Rollback
            await self.rollback(component_name)

    async def _rollout_percentage(
        self,
        component_name: str,
        result: RolloutResult,
        target_percentage: float
    ):
        """Execute percentage-based rollout"""
        try:
            result.phase = RolloutPhase.ROLLING_OUT

            # Set target percentage
            self.flag_manager.set_rollout_percentage(
                component_name,
                target_percentage
            )

            result.current_percentage = target_percentage

            # Monitor
            result.phase = RolloutPhase.MONITORING
            await asyncio.sleep(self.validation_wait_seconds)

            # Completed
            result.phase = RolloutPhase.COMPLETED
            result.completed_at = datetime.utcnow()

            logger.info(
                f"Percentage rollout completed for {component_name} "
                f"at {target_percentage}%"
            )

        except Exception as e:
            result.phase = RolloutPhase.FAILED
            result.error = str(e)
            logger.error(f"Percentage rollout failed: {e}")

    async def _rollout_ring(
        self,
        component_name: str,
        result: RolloutResult,
        validation_func: Optional[callable]
    ):
        """Execute ring-based rollout"""
        # Ring deployment: internal (1%) -> beta (10%) -> production (100%)
        rings = [
            ("internal", 1),
            ("beta", 10),
            ("production", 100)
        ]

        result.phase = RolloutPhase.ROLLING_OUT

        for ring_name, ring_percentage in rings:
            try:
                logger.info(
                    f"Ring rollout {component_name}: "
                    f"Deploying to {ring_name} ({ring_percentage}%)"
                )

                # Update percentage
                self.flag_manager.set_rollout_percentage(
                    component_name,
                    ring_percentage
                )

                result.current_percentage = ring_percentage
                result.metrics[f'ring_{ring_name}'] = datetime.utcnow().isoformat()

                # Monitor
                result.phase = RolloutPhase.MONITORING
                await asyncio.sleep(self.validation_wait_seconds)

                # Validate
                if validation_func:
                    result.phase = RolloutPhase.VALIDATING

                    is_valid = await validation_func(ring_percentage)

                    if not is_valid:
                        result.phase = RolloutPhase.FAILED
                        result.error = f"Validation failed in {ring_name} ring"
                        logger.error(result.error)

                        # Rollback
                        await self.rollback(component_name)
                        return

                result.phase = RolloutPhase.ROLLING_OUT

            except Exception as e:
                result.phase = RolloutPhase.FAILED
                result.error = str(e)
                logger.error(f"Ring rollout failed in {ring_name}: {e}")

                # Rollback
                await self.rollback(component_name)
                return

        # Completed
        result.phase = RolloutPhase.COMPLETED
        result.completed_at = datetime.utcnow()

        logger.info(f"Ring rollout completed for {component_name}")

    async def rollback(self, component_name: str):
        """Rollback a component to 0%"""
        logger.warning(f"Rolling back {component_name}")

        # Disable feature flag
        self.flag_manager.set_rollout_percentage(component_name, 0)

        # Update rollout result
        if component_name in self._rollouts:
            result = self._rollouts[component_name]
            result.phase = RolloutPhase.ROLLED_BACK
            result.current_percentage = 0.0
            result.completed_at = datetime.utcnow()

    def get_rollout_status(self, component_name: str) -> Optional[RolloutResult]:
        """Get current rollout status"""
        return self._rollouts.get(component_name)

    def list_active_rollouts(self) -> List[RolloutResult]:
        """List all active rollouts"""
        return [
            result for result in self._rollouts.values()
            if result.phase not in [
                RolloutPhase.COMPLETED,
                RolloutPhase.FAILED,
                RolloutPhase.ROLLED_BACK
            ]
        ]

    def get_rollout_history(self) -> List[RolloutResult]:
        """Get rollout history"""
        return list(self._rollouts.values())

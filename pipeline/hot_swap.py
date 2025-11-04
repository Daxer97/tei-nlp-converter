"""
Hot-Swapping Infrastructure

Enables zero-downtime updates of models and knowledge bases.
Supports graceful switchover with rollback capabilities.
"""
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import asyncio
from contextlib import asynccontextmanager

from logger import get_logger

logger = get_logger(__name__)


class ComponentType(Enum):
    """Types of components that can be hot-swapped"""
    NER_MODEL = "ner_model"
    KNOWLEDGE_BASE = "knowledge_base"
    PATTERN_MATCHER = "pattern_matcher"


class SwapStatus(Enum):
    """Status of a swap operation"""
    PENDING = "pending"         # Swap initiated
    PREPARING = "preparing"     # New component loading
    READY = "ready"            # New component ready
    SWAPPING = "swapping"      # Switching over
    COMPLETED = "completed"    # Successfully swapped
    FAILED = "failed"          # Swap failed
    ROLLED_BACK = "rolled_back"  # Rolled back to previous


@dataclass
class SwapResult:
    """Result of a swap operation"""
    component_type: ComponentType
    component_id: str
    old_version: Optional[str]
    new_version: str
    status: SwapStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


class HotSwapManager:
    """
    Manages hot-swapping of components with zero downtime

    Features:
    - Graceful switchover (wait for in-flight requests)
    - Health checks before activating new component
    - Automatic rollback on failure
    - Version tracking
    - Metrics collection

    Example:
        manager = HotSwapManager()

        # Prepare new model
        await manager.prepare_swap(
            ComponentType.NER_MODEL,
            "medical-ner",
            new_component=new_model,
            version="2.0"
        )

        # Perform swap
        result = await manager.execute_swap(
            ComponentType.NER_MODEL,
            "medical-ner"
        )
    """

    def __init__(self):
        # Active components
        self._active: Dict[str, Any] = {}
        self._versions: Dict[str, str] = {}

        # Components being prepared for swap
        self._pending: Dict[str, Any] = {}
        self._pending_versions: Dict[str, str] = {}

        # Swap operations
        self._swaps: Dict[str, SwapResult] = {}

        # In-flight request tracking
        self._request_counts: Dict[str, int] = {}
        self._request_locks: Dict[str, asyncio.Lock] = {}

    async def prepare_swap(
        self,
        component_type: ComponentType,
        component_id: str,
        new_component: Any,
        version: str,
        health_check: Optional[Callable[[Any], Awaitable[bool]]] = None
    ) -> SwapResult:
        """
        Prepare a component for hot-swapping

        Args:
            component_type: Type of component
            component_id: Unique identifier
            new_component: New component instance
            version: Version identifier
            health_check: Optional async function to validate component

        Returns:
            SwapResult with operation status
        """
        key = f"{component_type.value}:{component_id}"

        logger.info(f"Preparing swap for {key} to version {version}")

        # Create swap result
        swap_result = SwapResult(
            component_type=component_type,
            component_id=component_id,
            old_version=self._versions.get(key),
            new_version=version,
            status=SwapStatus.PREPARING,
            started_at=datetime.utcnow()
        )

        self._swaps[key] = swap_result

        try:
            # Store pending component
            self._pending[key] = new_component
            self._pending_versions[key] = version

            # Run health check if provided
            if health_check:
                logger.debug(f"Running health check for {key}")
                healthy = await health_check(new_component)

                if not healthy:
                    swap_result.status = SwapStatus.FAILED
                    swap_result.error = "Health check failed"
                    swap_result.completed_at = datetime.utcnow()
                    logger.error(f"Health check failed for {key}")
                    return swap_result

            swap_result.status = SwapStatus.READY
            logger.info(f"Component {key} ready for swap")

        except Exception as e:
            swap_result.status = SwapStatus.FAILED
            swap_result.error = str(e)
            swap_result.completed_at = datetime.utcnow()
            logger.error(f"Failed to prepare swap for {key}: {e}")

        return swap_result

    async def execute_swap(
        self,
        component_type: ComponentType,
        component_id: str,
        grace_period_seconds: float = 5.0,
        max_wait_seconds: float = 30.0
    ) -> SwapResult:
        """
        Execute hot-swap of a prepared component

        Args:
            component_type: Type of component
            component_id: Unique identifier
            grace_period_seconds: Wait time for in-flight requests
            max_wait_seconds: Maximum wait time before forcing swap

        Returns:
            SwapResult with operation status
        """
        key = f"{component_type.value}:{component_id}"

        if key not in self._swaps:
            raise ValueError(f"No swap prepared for {key}")

        swap_result = self._swaps[key]

        if swap_result.status != SwapStatus.READY:
            raise ValueError(f"Component {key} not ready for swap (status: {swap_result.status.value})")

        logger.info(f"Executing swap for {key}")
        swap_result.status = SwapStatus.SWAPPING

        try:
            # Save old component for rollback
            old_component = self._active.get(key)

            # Wait for in-flight requests to complete
            await self._wait_for_requests(key, grace_period_seconds, max_wait_seconds)

            # Perform atomic swap
            new_component = self._pending[key]
            new_version = self._pending_versions[key]

            self._active[key] = new_component
            self._versions[key] = new_version

            # Clean up pending
            del self._pending[key]
            del self._pending_versions[key]

            # Mark as completed
            swap_result.status = SwapStatus.COMPLETED
            swap_result.completed_at = datetime.utcnow()

            # Calculate metrics
            swap_duration = (swap_result.completed_at - swap_result.started_at).total_seconds()
            swap_result.metrics['swap_duration_seconds'] = swap_duration
            swap_result.metrics['old_component_released'] = old_component is not None

            logger.info(
                f"Successfully swapped {key} from {swap_result.old_version} to {swap_result.new_version} "
                f"in {swap_duration:.2f}s"
            )

        except Exception as e:
            swap_result.status = SwapStatus.FAILED
            swap_result.error = str(e)
            swap_result.completed_at = datetime.utcnow()
            logger.error(f"Failed to execute swap for {key}: {e}")

            # Attempt rollback
            try:
                await self._rollback(key, old_component, swap_result.old_version)
                swap_result.status = SwapStatus.ROLLED_BACK
                logger.info(f"Rolled back {key} to {swap_result.old_version}")
            except Exception as rollback_error:
                logger.error(f"Rollback failed for {key}: {rollback_error}")

        return swap_result

    async def _wait_for_requests(
        self,
        key: str,
        grace_period: float,
        max_wait: float
    ):
        """Wait for in-flight requests to complete"""
        logger.debug(f"Waiting for in-flight requests to complete for {key}")

        # Wait grace period
        await asyncio.sleep(grace_period)

        # Check if there are still active requests
        request_count = self._request_counts.get(key, 0)

        if request_count == 0:
            logger.debug(f"No in-flight requests for {key}")
            return

        logger.info(f"Waiting for {request_count} in-flight requests for {key}")

        # Wait for requests to complete (with timeout)
        start = asyncio.get_event_loop().time()

        while request_count > 0:
            elapsed = asyncio.get_event_loop().time() - start

            if elapsed > max_wait:
                logger.warning(
                    f"Force proceeding with swap for {key} "
                    f"({request_count} requests still in flight)"
                )
                break

            await asyncio.sleep(0.5)
            request_count = self._request_counts.get(key, 0)

        logger.debug(f"In-flight requests completed for {key}")

    async def _rollback(
        self,
        key: str,
        old_component: Optional[Any],
        old_version: Optional[str]
    ):
        """Rollback to previous component"""
        if old_component is None:
            raise ValueError(f"No previous component to rollback to for {key}")

        logger.warning(f"Rolling back {key} to {old_version}")

        self._active[key] = old_component
        if old_version:
            self._versions[key] = old_version

    @asynccontextmanager
    async def use_component(
        self,
        component_type: ComponentType,
        component_id: str
    ):
        """
        Context manager for using a component safely during swaps

        Example:
            async with manager.use_component(ComponentType.NER_MODEL, "medical-ner") as model:
                entities = await model.extract_entities(text)
        """
        key = f"{component_type.value}:{component_id}"

        # Acquire lock
        if key not in self._request_locks:
            self._request_locks[key] = asyncio.Lock()

        async with self._request_locks[key]:
            # Increment request count
            self._request_counts[key] = self._request_counts.get(key, 0) + 1

            try:
                # Yield component
                component = self._active.get(key)
                if component is None:
                    raise ValueError(f"Component {key} not found")

                yield component

            finally:
                # Decrement request count
                self._request_counts[key] -= 1

    def get_component(
        self,
        component_type: ComponentType,
        component_id: str
    ) -> Optional[Any]:
        """
        Get active component (without request tracking)

        Use use_component() context manager for safe access during swaps.
        """
        key = f"{component_type.value}:{component_id}"
        return self._active.get(key)

    def register_component(
        self,
        component_type: ComponentType,
        component_id: str,
        component: Any,
        version: str
    ):
        """
        Register a component (initial registration, not a swap)

        Args:
            component_type: Type of component
            component_id: Unique identifier
            component: Component instance
            version: Version identifier
        """
        key = f"{component_type.value}:{component_id}"

        logger.info(f"Registering component {key} version {version}")

        self._active[key] = component
        self._versions[key] = version

    def get_version(
        self,
        component_type: ComponentType,
        component_id: str
    ) -> Optional[str]:
        """Get current version of a component"""
        key = f"{component_type.value}:{component_id}"
        return self._versions.get(key)

    def get_swap_status(
        self,
        component_type: ComponentType,
        component_id: str
    ) -> Optional[SwapResult]:
        """Get status of latest swap operation"""
        key = f"{component_type.value}:{component_id}"
        return self._swaps.get(key)

    def list_components(self) -> List[Dict[str, Any]]:
        """List all active components"""
        components = []

        for key, component in self._active.items():
            component_type_str, component_id = key.split(":", 1)
            components.append({
                "type": component_type_str,
                "id": component_id,
                "version": self._versions.get(key),
                "in_flight_requests": self._request_counts.get(key, 0)
            })

        return components

    def list_pending_swaps(self) -> List[Dict[str, Any]]:
        """List all pending swap operations"""
        swaps = []

        for key, swap_result in self._swaps.items():
            if swap_result.status in [SwapStatus.PENDING, SwapStatus.PREPARING, SwapStatus.READY]:
                swaps.append({
                    "type": swap_result.component_type.value,
                    "id": swap_result.component_id,
                    "old_version": swap_result.old_version,
                    "new_version": swap_result.new_version,
                    "status": swap_result.status.value,
                    "started_at": swap_result.started_at.isoformat()
                })

        return swaps

    async def cancel_swap(
        self,
        component_type: ComponentType,
        component_id: str
    ) -> bool:
        """
        Cancel a pending swap

        Args:
            component_type: Type of component
            component_id: Unique identifier

        Returns:
            True if canceled, False if not found or already completed
        """
        key = f"{component_type.value}:{component_id}"

        if key not in self._swaps:
            return False

        swap_result = self._swaps[key]

        if swap_result.status not in [SwapStatus.PENDING, SwapStatus.PREPARING, SwapStatus.READY]:
            return False

        logger.info(f"Canceling swap for {key}")

        # Remove pending component
        if key in self._pending:
            del self._pending[key]
            del self._pending_versions[key]

        # Update swap result
        swap_result.status = SwapStatus.FAILED
        swap_result.error = "Canceled by user"
        swap_result.completed_at = datetime.utcnow()

        return True

    def get_metrics(self) -> Dict[str, Any]:
        """Get hot-swap metrics"""
        total_swaps = len(self._swaps)
        successful_swaps = sum(
            1 for swap in self._swaps.values()
            if swap.status == SwapStatus.COMPLETED
        )
        failed_swaps = sum(
            1 for swap in self._swaps.values()
            if swap.status == SwapStatus.FAILED
        )
        rolled_back_swaps = sum(
            1 for swap in self._swaps.values()
            if swap.status == SwapStatus.ROLLED_BACK
        )

        # Calculate average swap duration
        completed_swaps = [
            swap for swap in self._swaps.values()
            if swap.status == SwapStatus.COMPLETED and swap.completed_at
        ]

        avg_duration = 0.0
        if completed_swaps:
            durations = [
                (swap.completed_at - swap.started_at).total_seconds()
                for swap in completed_swaps
            ]
            avg_duration = sum(durations) / len(durations)

        return {
            "total_swaps": total_swaps,
            "successful_swaps": successful_swaps,
            "failed_swaps": failed_swaps,
            "rolled_back_swaps": rolled_back_swaps,
            "success_rate": successful_swaps / total_swaps if total_swaps > 0 else 0.0,
            "average_swap_duration_seconds": avg_duration,
            "active_components": len(self._active),
            "pending_swaps": len(self._pending)
        }

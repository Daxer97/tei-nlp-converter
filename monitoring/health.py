"""
Health Check System

Monitors the health of all system components with periodic checks
and status reporting.
"""
from typing import Dict, List, Optional, Callable, Awaitable, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import asyncio

from logger import get_logger

logger = get_logger(__name__)


class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"           # Component is functioning normally
    DEGRADED = "degraded"         # Component has issues but is functional
    UNHEALTHY = "unhealthy"       # Component is not functioning
    UNKNOWN = "unknown"           # Health status unknown


@dataclass
class ComponentHealth:
    """Health status of a component"""
    component_name: str
    status: HealthStatus
    message: str = ""
    last_check: datetime = field(default_factory=datetime.utcnow)
    check_duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthCheck:
    """Configuration for a health check"""
    name: str
    check_func: Callable[[], Awaitable[ComponentHealth]]
    interval_seconds: int = 60
    timeout_seconds: int = 10
    enabled: bool = True


class HealthCheckManager:
    """
    Manages health checks for all system components

    Performs periodic health checks and maintains current status for:
    - Database connectivity
    - Redis cache
    - External APIs (UMLS, RxNorm, USC, CourtListener)
    - Models (can load and predict)
    - Knowledge bases (can query)
    - Pattern matchers (can extract)

    Example:
        manager = HealthCheckManager()

        # Register health check
        async def check_database():
            try:
                # Test database connection
                await db.execute("SELECT 1")
                return ComponentHealth(
                    component_name="database",
                    status=HealthStatus.HEALTHY,
                    message="Connection OK"
                )
            except Exception as e:
                return ComponentHealth(
                    component_name="database",
                    status=HealthStatus.UNHEALTHY,
                    message=str(e)
                )

        manager.register_check("database", check_database, interval_seconds=30)

        # Start health checks
        await manager.start()

        # Get current status
        status = await manager.get_health_status()
        print(f"System status: {status['overall_status']}")
    """

    def __init__(self):
        self._checks: Dict[str, HealthCheck] = {}
        self._status: Dict[str, ComponentHealth] = {}
        self._check_tasks: Dict[str, asyncio.Task] = {}
        self._running = False

    def register_check(
        self,
        name: str,
        check_func: Callable[[], Awaitable[ComponentHealth]],
        interval_seconds: int = 60,
        timeout_seconds: int = 10,
        enabled: bool = True
    ):
        """
        Register a health check

        Args:
            name: Unique name for the check
            check_func: Async function that returns ComponentHealth
            interval_seconds: How often to run the check
            timeout_seconds: Timeout for the check
            enabled: Whether check is enabled
        """
        if name in self._checks:
            logger.warning(f"Overwriting existing health check: {name}")

        self._checks[name] = HealthCheck(
            name=name,
            check_func=check_func,
            interval_seconds=interval_seconds,
            timeout_seconds=timeout_seconds,
            enabled=enabled
        )

        logger.info(
            f"Registered health check: {name} "
            f"(interval={interval_seconds}s, timeout={timeout_seconds}s)"
        )

    def unregister_check(self, name: str):
        """Unregister a health check"""
        if name in self._checks:
            del self._checks[name]
            if name in self._status:
                del self._status[name]
            logger.info(f"Unregistered health check: {name}")

    async def start(self):
        """Start running health checks"""
        if self._running:
            logger.warning("Health check manager already running")
            return

        self._running = True

        # Start check tasks
        for name, check in self._checks.items():
            if check.enabled:
                task = asyncio.create_task(self._run_check_loop(check))
                self._check_tasks[name] = task

        logger.info(f"Started health check manager with {len(self._check_tasks)} checks")

    async def stop(self):
        """Stop running health checks"""
        if not self._running:
            return

        self._running = False

        # Cancel all check tasks
        for task in self._check_tasks.values():
            task.cancel()

        # Wait for cancellation
        await asyncio.gather(*self._check_tasks.values(), return_exceptions=True)

        self._check_tasks.clear()

        logger.info("Stopped health check manager")

    async def _run_check_loop(self, check: HealthCheck):
        """Run a health check in a loop"""
        logger.debug(f"Starting health check loop: {check.name}")

        while self._running:
            try:
                # Run check with timeout
                start_time = asyncio.get_event_loop().time()

                try:
                    result = await asyncio.wait_for(
                        check.check_func(),
                        timeout=check.timeout_seconds
                    )
                except asyncio.TimeoutError:
                    result = ComponentHealth(
                        component_name=check.name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Health check timed out after {check.timeout_seconds}s"
                    )
                except Exception as e:
                    result = ComponentHealth(
                        component_name=check.name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Health check failed: {str(e)}"
                    )

                # Calculate duration
                duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                result.check_duration_ms = duration_ms
                result.last_check = datetime.utcnow()

                # Store result
                self._status[check.name] = result

                logger.debug(
                    f"Health check {check.name}: {result.status.value} "
                    f"({duration_ms:.2f}ms)"
                )

            except Exception as e:
                logger.error(f"Error in health check loop {check.name}: {e}")

            # Wait for next check
            await asyncio.sleep(check.interval_seconds)

    async def run_check_now(self, name: str) -> ComponentHealth:
        """Run a specific health check immediately"""
        if name not in self._checks:
            raise ValueError(f"Health check not found: {name}")

        check = self._checks[name]

        try:
            start_time = asyncio.get_event_loop().time()

            result = await asyncio.wait_for(
                check.check_func(),
                timeout=check.timeout_seconds
            )

            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            result.check_duration_ms = duration_ms
            result.last_check = datetime.utcnow()

            self._status[name] = result

            return result

        except asyncio.TimeoutError:
            result = ComponentHealth(
                component_name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check timed out"
            )
            self._status[name] = result
            return result

        except Exception as e:
            result = ComponentHealth(
                component_name=name,
                status=HealthStatus.UNHEALTHY,
                message=str(e)
            )
            self._status[name] = result
            return result

    async def get_health_status(self) -> Dict[str, Any]:
        """
        Get overall health status

        Returns:
            Dict with overall status and component details
        """
        # Get current status for all components
        components = {}
        for name, health in self._status.items():
            components[name] = {
                "status": health.status.value,
                "message": health.message,
                "last_check": health.last_check.isoformat(),
                "check_duration_ms": health.check_duration_ms,
                "metadata": health.metadata
            }

        # Determine overall status
        if not self._status:
            overall_status = HealthStatus.UNKNOWN
        elif all(h.status == HealthStatus.HEALTHY for h in self._status.values()):
            overall_status = HealthStatus.HEALTHY
        elif any(h.status == HealthStatus.UNHEALTHY for h in self._status.values()):
            overall_status = HealthStatus.UNHEALTHY
        else:
            overall_status = HealthStatus.DEGRADED

        # Count by status
        status_counts = {
            "healthy": sum(1 for h in self._status.values() if h.status == HealthStatus.HEALTHY),
            "degraded": sum(1 for h in self._status.values() if h.status == HealthStatus.DEGRADED),
            "unhealthy": sum(1 for h in self._status.values() if h.status == HealthStatus.UNHEALTHY),
            "unknown": sum(1 for h in self._status.values() if h.status == HealthStatus.UNKNOWN)
        }

        return {
            "overall_status": overall_status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "components": components,
            "summary": {
                "total_components": len(self._status),
                **status_counts
            }
        }

    def get_component_status(self, name: str) -> Optional[ComponentHealth]:
        """Get status of a specific component"""
        return self._status.get(name)

    def list_checks(self) -> List[str]:
        """List all registered health checks"""
        return list(self._checks.keys())

    def enable_check(self, name: str):
        """Enable a health check"""
        if name in self._checks:
            self._checks[name].enabled = True
            logger.info(f"Enabled health check: {name}")

    def disable_check(self, name: str):
        """Disable a health check"""
        if name in self._checks:
            self._checks[name].enabled = False

            # Cancel running task
            if name in self._check_tasks:
                self._check_tasks[name].cancel()
                del self._check_tasks[name]

            logger.info(f"Disabled health check: {name}")


# Common health check implementations

async def check_database_health(db_pool) -> ComponentHealth:
    """Health check for database"""
    try:
        # Test simple query
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

        return ComponentHealth(
            component_name="database",
            status=HealthStatus.HEALTHY,
            message="Connection OK"
        )
    except Exception as e:
        return ComponentHealth(
            component_name="database",
            status=HealthStatus.UNHEALTHY,
            message=f"Connection failed: {str(e)}"
        )


async def check_redis_health(redis_client) -> ComponentHealth:
    """Health check for Redis"""
    try:
        # Test ping
        await redis_client.ping()

        return ComponentHealth(
            component_name="redis",
            status=HealthStatus.HEALTHY,
            message="Connection OK"
        )
    except Exception as e:
        return ComponentHealth(
            component_name="redis",
            status=HealthStatus.UNHEALTHY,
            message=f"Connection failed: {str(e)}"
        )


async def check_external_api_health(
    api_name: str,
    api_url: str,
    timeout_seconds: int = 5
) -> ComponentHealth:
    """Health check for external API"""
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=timeout_seconds) as response:
                if response.status == 200:
                    return ComponentHealth(
                        component_name=api_name,
                        status=HealthStatus.HEALTHY,
                        message="API accessible"
                    )
                else:
                    return ComponentHealth(
                        component_name=api_name,
                        status=HealthStatus.DEGRADED,
                        message=f"API returned status {response.status}"
                    )
    except asyncio.TimeoutError:
        return ComponentHealth(
            component_name=api_name,
            status=HealthStatus.DEGRADED,
            message="API timeout"
        )
    except Exception as e:
        return ComponentHealth(
            component_name=api_name,
            status=HealthStatus.UNHEALTHY,
            message=f"API unreachable: {str(e)}"
        )


async def check_model_health(model_id: str, model) -> ComponentHealth:
    """Health check for NER model"""
    try:
        # Test model with simple text
        test_text = "Test entity extraction"
        entities = await model.extract_entities(test_text)

        return ComponentHealth(
            component_name=f"model_{model_id}",
            status=HealthStatus.HEALTHY,
            message="Model loaded and functioning",
            metadata={"test_entities": len(entities)}
        )
    except Exception as e:
        return ComponentHealth(
            component_name=f"model_{model_id}",
            status=HealthStatus.UNHEALTHY,
            message=f"Model error: {str(e)}"
        )


async def check_kb_health(kb_id: str, kb_provider) -> ComponentHealth:
    """Health check for knowledge base"""
    try:
        # Test KB with simple lookup
        result = await kb_provider.lookup_entity("test")

        return ComponentHealth(
            component_name=f"kb_{kb_id}",
            status=HealthStatus.HEALTHY,
            message="KB accessible",
            metadata={"test_lookup": result is not None}
        )
    except Exception as e:
        return ComponentHealth(
            component_name=f"kb_{kb_id}",
            status=HealthStatus.DEGRADED,
            message=f"KB warning: {str(e)}"
        )

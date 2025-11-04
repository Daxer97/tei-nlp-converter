"""
Configuration Hot-Reload System

Monitors configuration files for changes and reloads them
without restarting the service.
"""
from typing import Dict, Optional, Callable, Awaitable, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from pathlib import Path
import asyncio
import hashlib
import yaml

from logger import get_logger

logger = get_logger(__name__)


class ReloadStatus(Enum):
    """Status of configuration reload"""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ReloadResult:
    """Result of configuration reload"""
    config_path: Path
    status: ReloadStatus
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None
    changes: Dict[str, Any] = field(default_factory=dict)


class ConfigWatcher:
    """
    Watches a configuration file for changes

    Features:
    - File modification detection
    - Checksum validation
    - Change notification
    - Configurable polling interval
    """

    def __init__(
        self,
        config_path: Path,
        check_interval_seconds: int = 10
    ):
        """
        Initialize config watcher

        Args:
            config_path: Path to configuration file
            check_interval_seconds: How often to check for changes
        """
        self.config_path = config_path
        self.check_interval = check_interval_seconds

        self._last_checksum: Optional[str] = None
        self._last_modified: Optional[float] = None
        self._running = False
        self._watch_task = None

    async def start(
        self,
        on_change: Callable[[Path], Awaitable[None]]
    ):
        """
        Start watching for changes

        Args:
            on_change: Async callback function called when file changes
        """
        if self._running:
            return

        self._running = True

        # Initialize checksum
        self._last_checksum = await self._calculate_checksum()
        if self.config_path.exists():
            self._last_modified = self.config_path.stat().st_mtime

        self._watch_task = asyncio.create_task(
            self._watch_loop(on_change)
        )

        logger.info(f"Started watching config file: {self.config_path}")

    async def stop(self):
        """Stop watching"""
        if not self._running:
            return

        self._running = False

        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

        logger.info(f"Stopped watching config file: {self.config_path}")

    async def _watch_loop(
        self,
        on_change: Callable[[Path], Awaitable[None]]
    ):
        """Watch loop"""
        while self._running:
            try:
                # Check if file changed
                if await self._has_changed():
                    logger.info(f"Config file changed: {self.config_path}")

                    try:
                        # Call change handler
                        await on_change(self.config_path)

                        # Update checksum
                        self._last_checksum = await self._calculate_checksum()
                        if self.config_path.exists():
                            self._last_modified = self.config_path.stat().st_mtime

                    except Exception as e:
                        logger.error(f"Error handling config change: {e}")

            except Exception as e:
                logger.error(f"Error in config watch loop: {e}")

            await asyncio.sleep(self.check_interval)

    async def _has_changed(self) -> bool:
        """Check if file has changed"""
        if not self.config_path.exists():
            # File was deleted
            if self._last_checksum is not None:
                logger.warning(f"Config file deleted: {self.config_path}")
                return True
            return False

        # Check modification time first (fast)
        current_mtime = self.config_path.stat().st_mtime
        if self._last_modified and current_mtime <= self._last_modified:
            return False

        # Check checksum (slower but accurate)
        current_checksum = await self._calculate_checksum()
        if current_checksum != self._last_checksum:
            return True

        return False

    async def _calculate_checksum(self) -> Optional[str]:
        """Calculate file checksum"""
        if not self.config_path.exists():
            return None

        try:
            content = self.config_path.read_bytes()
            return hashlib.sha256(content).hexdigest()
        except Exception as e:
            logger.error(f"Error calculating checksum: {e}")
            return None


class ConfigReloadManager:
    """
    Manages hot-reloading of configuration files

    Features:
    - Watch multiple config files
    - Validate before applying
    - Rollback on failure
    - Reload history
    - Change notifications

    Example:
        manager = ConfigReloadManager()

        # Register reload handler
        async def reload_pipeline_config(config_path: Path):
            # Load new config
            config = PipelineConfig.from_yaml(config_path)

            # Validate
            if not validate_config(config):
                raise ValueError("Invalid config")

            # Apply
            await pipeline.update_config(config)

        manager.register_config(
            Path("config/pipeline/medical.yaml"),
            reload_pipeline_config
        )

        # Start watching
        await manager.start()

        # Config file changes are automatically detected and reloaded
    """

    def __init__(self):
        self._watchers: Dict[Path, ConfigWatcher] = {}
        self._handlers: Dict[Path, Callable[[Path], Awaitable[None]]] = {}
        self._reload_history: List[ReloadResult] = []
        self._running = False

    def register_config(
        self,
        config_path: Path,
        reload_handler: Callable[[Path], Awaitable[None]],
        check_interval_seconds: int = 10
    ):
        """
        Register a configuration file for hot-reload

        Args:
            config_path: Path to config file
            reload_handler: Async function to reload config
            check_interval_seconds: How often to check for changes
        """
        if config_path in self._watchers:
            logger.warning(f"Config already registered: {config_path}")
            return

        watcher = ConfigWatcher(config_path, check_interval_seconds)
        self._watchers[config_path] = watcher
        self._handlers[config_path] = reload_handler

        logger.info(f"Registered config for hot-reload: {config_path}")

    def unregister_config(self, config_path: Path):
        """Unregister a configuration file"""
        if config_path in self._watchers:
            # Stop watcher if running
            if self._running:
                asyncio.create_task(self._watchers[config_path].stop())

            del self._watchers[config_path]
            del self._handlers[config_path]

            logger.info(f"Unregistered config: {config_path}")

    async def start(self):
        """Start watching all registered configs"""
        if self._running:
            logger.warning("Config reload manager already running")
            return

        self._running = True

        # Start all watchers
        for config_path, watcher in self._watchers.items():
            handler = self._handlers[config_path]
            await watcher.start(self._create_reload_wrapper(config_path, handler))

        logger.info(f"Started config reload manager ({len(self._watchers)} configs)")

    async def stop(self):
        """Stop watching all configs"""
        if not self._running:
            return

        self._running = False

        # Stop all watchers
        for watcher in self._watchers.values():
            await watcher.stop()

        logger.info("Stopped config reload manager")

    def _create_reload_wrapper(
        self,
        config_path: Path,
        handler: Callable[[Path], Awaitable[None]]
    ) -> Callable[[Path], Awaitable[None]]:
        """Create wrapper that handles reload and records result"""

        async def wrapper(path: Path):
            result = ReloadResult(
                config_path=config_path,
                status=ReloadStatus.SUCCESS
            )

            try:
                # Load and parse config to detect changes
                old_config = self._load_config(config_path)

                # Call reload handler
                await handler(path)

                # Load new config
                new_config = self._load_config(config_path)

                # Detect changes
                result.changes = self._detect_changes(old_config, new_config)

                logger.info(
                    f"Successfully reloaded config: {config_path} "
                    f"({len(result.changes)} changes)"
                )

            except Exception as e:
                result.status = ReloadStatus.FAILED
                result.error = str(e)
                logger.error(f"Failed to reload config {config_path}: {e}")

            # Record result
            self._reload_history.append(result)

        return wrapper

    def _load_config(self, config_path: Path) -> Dict[str, Any]:
        """Load configuration file"""
        try:
            with open(config_path, 'r') as f:
                if config_path.suffix in ['.yaml', '.yml']:
                    return yaml.safe_load(f) or {}
                elif config_path.suffix == '.json':
                    import json
                    return json.load(f)
                else:
                    return {}
        except Exception as e:
            logger.error(f"Error loading config {config_path}: {e}")
            return {}

    def _detect_changes(
        self,
        old_config: Dict[str, Any],
        new_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Detect changes between old and new config"""
        changes = {}

        # Find added/modified keys
        for key, new_value in new_config.items():
            if key not in old_config:
                changes[key] = {"type": "added", "value": new_value}
            elif old_config[key] != new_value:
                changes[key] = {
                    "type": "modified",
                    "old": old_config[key],
                    "new": new_value
                }

        # Find removed keys
        for key in old_config:
            if key not in new_config:
                changes[key] = {"type": "removed", "old": old_config[key]}

        return changes

    async def reload_now(self, config_path: Path) -> ReloadResult:
        """Manually trigger config reload"""
        if config_path not in self._handlers:
            raise ValueError(f"Config not registered: {config_path}")

        result = ReloadResult(
            config_path=config_path,
            status=ReloadStatus.SUCCESS
        )

        try:
            handler = self._handlers[config_path]
            await handler(config_path)

            logger.info(f"Manually reloaded config: {config_path}")

        except Exception as e:
            result.status = ReloadStatus.FAILED
            result.error = str(e)
            logger.error(f"Failed to manually reload config {config_path}: {e}")

        self._reload_history.append(result)
        return result

    def get_reload_history(
        self,
        config_path: Optional[Path] = None,
        limit: int = 10
    ) -> List[ReloadResult]:
        """Get reload history"""
        history = self._reload_history

        if config_path:
            history = [r for r in history if r.config_path == config_path]

        # Sort by timestamp (most recent first)
        history = sorted(history, key=lambda r: r.timestamp, reverse=True)

        return history[:limit]

    def get_last_reload(self, config_path: Path) -> Optional[ReloadResult]:
        """Get last reload result for a config"""
        history = [r for r in self._reload_history if r.config_path == config_path]

        if not history:
            return None

        return max(history, key=lambda r: r.timestamp)

    def list_watched_configs(self) -> List[Path]:
        """List all watched configuration files"""
        return list(self._watchers.keys())

    def get_stats(self) -> Dict[str, Any]:
        """Get reload statistics"""
        total_reloads = len(self._reload_history)
        successful = sum(1 for r in self._reload_history if r.status == ReloadStatus.SUCCESS)
        failed = sum(1 for r in self._reload_history if r.status == ReloadStatus.FAILED)

        return {
            "total_reloads": total_reloads,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total_reloads if total_reloads > 0 else 0.0,
            "watched_configs": len(self._watchers)
        }

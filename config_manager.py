"""
Configuration Hot-Reload Manager

Manages dynamic configuration with support for:
- File-based configuration with watch
- Remote configuration sources (HTTP polling)
- Environment variable overrides
- Hot-reload without restart
- Configuration validation
"""
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass
from pathlib import Path
from enum import Enum
import asyncio
import yaml
import json
import os
from datetime import datetime
import hashlib
import aiohttp
from logger import get_logger

logger = get_logger(__name__)


class ConfigSource(Enum):
    """Configuration source types"""
    FILE = "file"
    REMOTE = "remote"
    ENVIRONMENT = "environment"


@dataclass
class ConfigChange:
    """Represents a configuration change"""
    source: ConfigSource
    changed_at: datetime
    old_value: Optional[Any]
    new_value: Any
    path: str  # Dot-notation path (e.g., "pipeline.ner_models")


class ConfigurationManager:
    """
    Manages dynamic configuration with hot-reload

    Features:
    - Watch local configuration files
    - Poll remote configuration sources
    - Environment variable overrides
    - Hot-reload without restart
    - Configuration validation
    - Change callbacks

    Example:
        config_manager = ConfigurationManager(
            config_files=[
                "config/pipeline.yaml",
                "config/models.yaml"
            ],
            remote_sources=[
                "https://config.example.com/nlp/config.json"
            ]
        )

        # Register callback for configuration changes
        config_manager.register_callback(
            "pipeline",
            lambda old, new: pipeline.update_config(new)
        )

        await config_manager.start_watch()
    """

    def __init__(
        self,
        config_files: Optional[List[str]] = None,
        remote_sources: Optional[List[str]] = None,
        poll_interval_seconds: int = 60,
        enable_env_overrides: bool = True
    ):
        self.config_files = [Path(f) for f in (config_files or [])]
        self.remote_sources = remote_sources or []
        self.poll_interval = poll_interval_seconds
        self.enable_env_overrides = enable_env_overrides

        # Current configuration
        self.config: Dict[str, Any] = {}

        # File hashes for change detection
        self.file_hashes: Dict[Path, str] = {}

        # Remote ETags for change detection
        self.remote_etags: Dict[str, str] = {}

        # Change callbacks: path -> list of callbacks
        self.callbacks: Dict[str, List[Callable]] = {}

        # Watch tasks
        self.watch_tasks: List[asyncio.Task] = []

        self._running = False

    async def start_watch(self):
        """Start watching configuration sources"""
        if self._running:
            logger.warning("Configuration manager already watching")
            return

        logger.info("Starting configuration watch")

        # Load initial configuration
        await self._load_all_configs()

        # Start file watchers
        for config_file in self.config_files:
            task = asyncio.create_task(self._watch_file(config_file))
            self.watch_tasks.append(task)

        # Start remote pollers
        for remote_url in self.remote_sources:
            task = asyncio.create_task(self._poll_remote(remote_url))
            self.watch_tasks.append(task)

        # Start environment variable watcher
        if self.enable_env_overrides:
            task = asyncio.create_task(self._watch_environment())
            self.watch_tasks.append(task)

        self._running = True
        logger.info("Configuration watch started")

    async def stop_watch(self):
        """Stop watching configuration sources"""
        if not self._running:
            return

        logger.info("Stopping configuration watch")

        # Cancel all watch tasks
        for task in self.watch_tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self.watch_tasks, return_exceptions=True)

        self.watch_tasks.clear()
        self._running = False

        logger.info("Configuration watch stopped")

    async def _load_all_configs(self):
        """Load configuration from all sources"""
        logger.info("Loading configuration from all sources")

        # Load from files (in order)
        for config_file in self.config_files:
            await self._load_config_file(config_file)

        # Load from remote sources
        for remote_url in self.remote_sources:
            await self._load_remote_config(remote_url)

        # Apply environment overrides
        if self.enable_env_overrides:
            self._apply_env_overrides()

        logger.info("Configuration loaded successfully")

    async def _load_config_file(self, config_file: Path):
        """Load configuration from a file"""
        if not config_file.exists():
            logger.warning(f"Configuration file not found: {config_file}")
            return

        try:
            # Read file content
            with open(config_file, 'r') as f:
                content = f.read()

            # Calculate hash
            file_hash = hashlib.sha256(content.encode()).hexdigest()
            self.file_hashes[config_file] = file_hash

            # Parse based on file extension
            if config_file.suffix in ['.yaml', '.yml']:
                new_config = yaml.safe_load(content)
            elif config_file.suffix == '.json':
                new_config = json.loads(content)
            else:
                logger.warning(f"Unsupported config file format: {config_file}")
                return

            # Merge into existing config
            self._merge_config(new_config, source=ConfigSource.FILE)

            logger.info(f"Loaded configuration from: {config_file}")

        except Exception as e:
            logger.error(f"Failed to load config file {config_file}: {e}")

    async def _load_remote_config(self, remote_url: str):
        """Load configuration from remote source"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {}

                # Add If-None-Match header if we have an ETag
                if remote_url in self.remote_etags:
                    headers['If-None-Match'] = self.remote_etags[remote_url]

                async with session.get(remote_url, headers=headers, timeout=10) as response:
                    # Not modified
                    if response.status == 304:
                        logger.debug(f"Remote config not modified: {remote_url}")
                        return

                    if response.status != 200:
                        logger.error(f"Failed to fetch remote config: {remote_url} (status: {response.status})")
                        return

                    # Store ETag for future requests
                    if 'ETag' in response.headers:
                        self.remote_etags[remote_url] = response.headers['ETag']

                    # Parse response
                    content_type = response.headers.get('Content-Type', '')

                    if 'json' in content_type:
                        new_config = await response.json()
                    elif 'yaml' in content_type:
                        text = await response.text()
                        new_config = yaml.safe_load(text)
                    else:
                        # Try to parse as JSON
                        new_config = await response.json()

                    # Merge into existing config
                    self._merge_config(new_config, source=ConfigSource.REMOTE)

                    logger.info(f"Loaded remote configuration from: {remote_url}")

        except Exception as e:
            logger.error(f"Failed to load remote config from {remote_url}: {e}")

    def _apply_env_overrides(self):
        """Apply environment variable overrides"""
        # Environment variables in format: NLP_PIPELINE__NER_MODELS=...
        # Translates to: pipeline.ner_models

        prefix = "NLP_"
        overrides_applied = 0

        for key, value in os.environ.items():
            if not key.startswith(prefix):
                continue

            # Remove prefix and convert to path
            config_path = key[len(prefix):].lower().replace('__', '.')

            # Parse value
            try:
                # Try to parse as JSON
                parsed_value = json.loads(value)
            except json.JSONDecodeError:
                # Use as string
                parsed_value = value

            # Apply override
            self._set_config_value(config_path, parsed_value)
            overrides_applied += 1

            logger.debug(f"Applied environment override: {config_path} = {parsed_value}")

        if overrides_applied > 0:
            logger.info(f"Applied {overrides_applied} environment overrides")

    def _merge_config(self, new_config: Dict[str, Any], source: ConfigSource):
        """Merge new configuration into existing config"""
        if not new_config:
            return

        # Deep merge
        self._deep_merge(self.config, new_config)

    def _deep_merge(self, base: Dict, update: Dict):
        """Deep merge update into base"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                # Recursive merge for nested dicts
                self._deep_merge(base[key], value)
            else:
                # Direct assignment for other types
                old_value = base.get(key)

                if old_value != value:
                    base[key] = value

                    # Notify callbacks
                    asyncio.create_task(
                        self._notify_change(key, old_value, value)
                    )

    def _set_config_value(self, path: str, value: Any):
        """Set configuration value at path"""
        keys = path.split('.')
        current = self.config

        # Navigate to parent
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        # Set value
        final_key = keys[-1]
        old_value = current.get(final_key)

        if old_value != value:
            current[final_key] = value

            # Notify callbacks
            asyncio.create_task(
                self._notify_change(path, old_value, value)
            )

    async def _watch_file(self, config_file: Path):
        """Watch configuration file for changes"""
        logger.debug(f"Watching configuration file: {config_file}")

        while self._running:
            try:
                # Wait before checking
                await asyncio.sleep(5)

                if not config_file.exists():
                    continue

                # Read file and calculate hash
                with open(config_file, 'r') as f:
                    content = f.read()

                file_hash = hashlib.sha256(content.encode()).hexdigest()

                # Check if changed
                if file_hash != self.file_hashes.get(config_file):
                    logger.info(f"Configuration file changed: {config_file}")
                    await self._load_config_file(config_file)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error watching file {config_file}: {e}")
                await asyncio.sleep(10)  # Back off on error

    async def _poll_remote(self, remote_url: str):
        """Poll remote configuration source"""
        logger.debug(f"Polling remote configuration: {remote_url}")

        while self._running:
            try:
                # Wait before polling
                await asyncio.sleep(self.poll_interval)

                await self._load_remote_config(remote_url)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error polling remote {remote_url}: {e}")
                await asyncio.sleep(60)  # Back off on error

    async def _watch_environment(self):
        """Watch for environment variable changes"""
        logger.debug("Watching environment variables")

        # Take snapshot of current env vars
        env_snapshot = dict(os.environ)

        while self._running:
            try:
                # Wait before checking
                await asyncio.sleep(10)

                # Check for changes
                current_env = dict(os.environ)

                # Find changes
                for key, value in current_env.items():
                    if key.startswith("NLP_"):
                        old_value = env_snapshot.get(key)

                        if old_value != value:
                            logger.info(f"Environment variable changed: {key}")
                            self._apply_env_overrides()
                            break

                # Update snapshot
                env_snapshot = current_env

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error watching environment: {e}")
                await asyncio.sleep(10)

    async def _notify_change(self, path: str, old_value: Any, new_value: Any):
        """Notify registered callbacks about configuration change"""
        change = ConfigChange(
            source=ConfigSource.FILE,  # TODO: track actual source
            changed_at=datetime.utcnow(),
            old_value=old_value,
            new_value=new_value,
            path=path
        )

        # Find matching callbacks
        callbacks_to_call = []

        for registered_path, callback_list in self.callbacks.items():
            # Exact match or parent path match
            if path.startswith(registered_path):
                callbacks_to_call.extend(callback_list)

        # Call callbacks
        for callback in callbacks_to_call:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(old_value, new_value)
                else:
                    callback(old_value, new_value)

                logger.debug(f"Notified callback for config change: {path}")

            except Exception as e:
                logger.error(f"Callback failed for {path}: {e}")

    def register_callback(
        self,
        path: str,
        callback: Callable[[Any, Any], Any]
    ):
        """
        Register a callback for configuration changes

        Args:
            path: Configuration path in dot notation (e.g., "pipeline.ner_models")
            callback: Function called with (old_value, new_value) when config changes
        """
        if path not in self.callbacks:
            self.callbacks[path] = []

        self.callbacks[path].append(callback)

        logger.debug(f"Registered callback for config path: {path}")

    def unregister_callback(self, path: str, callback: Callable):
        """Unregister a callback"""
        if path in self.callbacks and callback in self.callbacks[path]:
            self.callbacks[path].remove(callback)
            logger.debug(f"Unregistered callback for config path: {path}")

    def get(self, path: str, default: Any = None) -> Any:
        """Get configuration value at path"""
        keys = path.split('.')
        current = self.config

        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return default

    def get_all(self) -> Dict[str, Any]:
        """Get complete configuration"""
        return self.config.copy()

    def validate(self, schema: Optional[Dict[str, Any]] = None) -> bool:
        """Validate configuration against schema"""
        # TODO: Implement schema validation using jsonschema or similar
        return True


# Global configuration manager instance
_global_config_manager: Optional[ConfigurationManager] = None


async def get_global_config_manager() -> ConfigurationManager:
    """Get or create the global configuration manager"""
    global _global_config_manager

    if _global_config_manager is None:
        _global_config_manager = ConfigurationManager(
            config_files=[
                "config/pipeline.yaml",
                "config/models.yaml",
                "config/knowledge_bases.yaml"
            ],
            remote_sources=[],  # Can be configured via environment
            enable_env_overrides=True
        )

        await _global_config_manager.start_watch()

    return _global_config_manager

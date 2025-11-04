"""
KB Sync Service

Manages scheduled synchronization of knowledge bases with background updates.
"""
from typing import Dict, Optional
import asyncio
from datetime import datetime, timedelta
from dataclasses import dataclass
import json
from pathlib import Path

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False
    logger.warning("apscheduler not available - sync scheduling disabled")

from knowledge_bases.base import KBSyncConfig
from knowledge_bases.registry import KnowledgeBaseRegistry
from knowledge_bases.streaming import KBStreamingService, StreamProgress
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class SyncStatus:
    """Track sync status for a KB"""
    kb_id: str
    last_sync: Optional[datetime] = None
    next_sync: Optional[datetime] = None
    last_status: str = "never_synced"  # never_synced, success, failed
    last_error: Optional[str] = None
    total_syncs: int = 0
    successful_syncs: int = 0
    failed_syncs: int = 0

    def to_dict(self) -> Dict:
        return {
            'kb_id': self.kb_id,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'next_sync': self.next_sync.isoformat() if self.next_sync else None,
            'last_status': self.last_status,
            'last_error': self.last_error,
            'total_syncs': self.total_syncs,
            'successful_syncs': self.successful_syncs,
            'failed_syncs': self.failed_syncs
        }


class KBSyncService:
    """
    Service for scheduled KB synchronization

    Features:
    - Scheduled full and incremental syncs
    - Configurable sync frequency per KB
    - Retry logic with exponential backoff
    - Sync status tracking and persistence
    - Manual sync triggering
    """

    def __init__(
        self,
        kb_registry: KnowledgeBaseRegistry,
        streaming_service: KBStreamingService,
        status_file: str = "data/kb_sync_status.json"
    ):
        self.kb_registry = kb_registry
        self.streaming_service = streaming_service
        self.status_file = Path(status_file)
        self.status_file.parent.mkdir(parents=True, exist_ok=True)

        self.sync_status: Dict[str, SyncStatus] = {}
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.sync_jobs: Dict[str, str] = {}  # kb_id -> job_id

        # Load persisted status
        self._load_status()

    def _load_status(self):
        """Load sync status from file"""
        try:
            if self.status_file.exists():
                with open(self.status_file, 'r') as f:
                    data = json.load(f)

                for kb_id, status_data in data.items():
                    status = SyncStatus(
                        kb_id=kb_id,
                        last_sync=datetime.fromisoformat(status_data['last_sync']) if status_data.get('last_sync') else None,
                        next_sync=datetime.fromisoformat(status_data['next_sync']) if status_data.get('next_sync') else None,
                        last_status=status_data.get('last_status', 'never_synced'),
                        last_error=status_data.get('last_error'),
                        total_syncs=status_data.get('total_syncs', 0),
                        successful_syncs=status_data.get('successful_syncs', 0),
                        failed_syncs=status_data.get('failed_syncs', 0)
                    )
                    self.sync_status[kb_id] = status

                logger.info(f"Loaded sync status for {len(self.sync_status)} KBs")

        except Exception as e:
            logger.warning(f"Could not load sync status: {e}")

    def _save_status(self):
        """Save sync status to file"""
        try:
            data = {
                kb_id: status.to_dict()
                for kb_id, status in self.sync_status.items()
            }

            with open(self.status_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)

        except Exception as e:
            logger.error(f"Error saving sync status: {e}")

    async def initialize(self) -> bool:
        """Initialize sync service and scheduler"""
        if not SCHEDULER_AVAILABLE:
            logger.error("apscheduler not available - sync service cannot start")
            return False

        try:
            # Create scheduler
            self.scheduler = AsyncIOScheduler()

            # Schedule syncs for all registered KBs
            for kb_id in self.kb_registry.list_providers():
                sync_config = self.kb_registry.get_sync_config(kb_id)

                if sync_config and sync_config.enabled:
                    self.schedule_sync(kb_id, sync_config)

            # Start scheduler
            self.scheduler.start()

            logger.info("KB sync service initialized")
            return True

        except Exception as e:
            logger.error(f"Error initializing sync service: {e}")
            return False

    def schedule_sync(self, kb_id: str, config: KBSyncConfig):
        """
        Schedule periodic sync for a KB

        Args:
            kb_id: Knowledge base identifier
            config: Sync configuration
        """
        if not self.scheduler:
            logger.error("Scheduler not initialized")
            return

        # Remove existing job if any
        if kb_id in self.sync_jobs:
            self.scheduler.remove_job(self.sync_jobs[kb_id])

        # Create trigger based on frequency
        trigger = self._create_trigger(config.sync_frequency)

        if not trigger:
            logger.warning(f"Invalid sync frequency for {kb_id}: {config.sync_frequency}")
            return

        # Schedule job
        job = self.scheduler.add_job(
            self._sync_kb,
            trigger=trigger,
            args=[kb_id, config],
            id=f"sync_{kb_id}",
            replace_existing=True,
            misfire_grace_time=3600  # 1 hour grace period
        )

        self.sync_jobs[kb_id] = job.id

        # Update status
        if kb_id not in self.sync_status:
            self.sync_status[kb_id] = SyncStatus(kb_id=kb_id)

        self.sync_status[kb_id].next_sync = job.next_run_time

        self._save_status()

        logger.info(
            f"Scheduled {config.sync_frequency} sync for {kb_id} "
            f"(next run: {job.next_run_time})"
        )

    def _create_trigger(self, frequency: str):
        """Create scheduler trigger from frequency string"""
        if frequency == "daily":
            return CronTrigger(hour=2, minute=0)  # 2 AM daily
        elif frequency == "weekly":
            return CronTrigger(day_of_week='sun', hour=2)  # Sunday 2 AM
        elif frequency == "monthly":
            return CronTrigger(day=1, hour=2)  # 1st of month 2 AM
        elif frequency == "quarterly":
            # First day of Jan, Apr, Jul, Oct
            return CronTrigger(month='1,4,7,10', day=1, hour=2)
        elif frequency.startswith("interval:"):
            # Format: "interval:2h" or "interval:30m"
            try:
                interval_str = frequency.split(':')[1]

                if interval_str.endswith('h'):
                    hours = int(interval_str[:-1])
                    return IntervalTrigger(hours=hours)
                elif interval_str.endswith('m'):
                    minutes = int(interval_str[:-1])
                    return IntervalTrigger(minutes=minutes)
            except Exception as e:
                logger.error(f"Invalid interval format: {frequency}")

        return None

    async def _sync_kb(self, kb_id: str, config: KBSyncConfig):
        """
        Perform KB synchronization

        Args:
            kb_id: Knowledge base identifier
            config: Sync configuration
        """
        logger.info(f"Starting scheduled sync for {kb_id}")

        status = self.sync_status.get(kb_id)
        if not status:
            status = SyncStatus(kb_id=kb_id)
            self.sync_status[kb_id] = status

        try:
            # Determine since timestamp for incremental sync
            since = None
            if config.incremental and status.last_sync:
                since = status.last_sync

            # Stream KB data
            progress = await self.streaming_service.stream_kb(
                kb_id=kb_id,
                entity_types=None,  # All entity types
                batch_size=config.batch_size,
                since=since
            )

            # Update status
            if progress.status == "completed":
                status.last_sync = datetime.now()
                status.last_status = "success"
                status.last_error = None
                status.successful_syncs += 1

                logger.info(
                    f"Sync completed for {kb_id}: "
                    f"{progress.entities_streamed} entities"
                )
            else:
                status.last_status = "failed"
                status.last_error = progress.error_message
                status.failed_syncs += 1

                logger.error(f"Sync failed for {kb_id}: {progress.error_message}")

            status.total_syncs += 1

            # Update next sync time
            job = self.scheduler.get_job(f"sync_{kb_id}")
            if job:
                status.next_sync = job.next_run_time

            self._save_status()

        except Exception as e:
            status.last_status = "failed"
            status.last_error = str(e)
            status.failed_syncs += 1
            status.total_syncs += 1

            self._save_status()

            logger.error(f"Error syncing {kb_id}: {e}")

    async def sync_now(self, kb_id: str, incremental: bool = True) -> StreamProgress:
        """
        Manually trigger sync for a KB

        Args:
            kb_id: Knowledge base identifier
            incremental: Whether to do incremental sync (only new data)

        Returns:
            StreamProgress object
        """
        logger.info(f"Manual sync triggered for {kb_id}")

        status = self.sync_status.get(kb_id)
        if not status:
            status = SyncStatus(kb_id=kb_id)
            self.sync_status[kb_id] = status

        # Determine since timestamp
        since = None
        if incremental and status.last_sync:
            since = status.last_sync

        # Stream KB data
        progress = await self.streaming_service.stream_kb(
            kb_id=kb_id,
            entity_types=None,
            batch_size=1000,
            since=since
        )

        # Update status
        if progress.status == "completed":
            status.last_sync = datetime.now()
            status.last_status = "success"
            status.last_error = None
            status.successful_syncs += 1
        else:
            status.last_status = "failed"
            status.last_error = progress.error_message
            status.failed_syncs += 1

        status.total_syncs += 1
        self._save_status()

        return progress

    def get_status(self, kb_id: str) -> Optional[SyncStatus]:
        """Get sync status for a KB"""
        return self.sync_status.get(kb_id)

    def get_all_status(self) -> Dict[str, SyncStatus]:
        """Get sync status for all KBs"""
        return self.sync_status.copy()

    def pause_sync(self, kb_id: str) -> bool:
        """Pause scheduled sync for a KB"""
        if kb_id not in self.sync_jobs:
            return False

        try:
            job_id = self.sync_jobs[kb_id]
            self.scheduler.pause_job(job_id)

            logger.info(f"Paused sync for {kb_id}")
            return True

        except Exception as e:
            logger.error(f"Error pausing sync for {kb_id}: {e}")
            return False

    def resume_sync(self, kb_id: str) -> bool:
        """Resume scheduled sync for a KB"""
        if kb_id not in self.sync_jobs:
            return False

        try:
            job_id = self.sync_jobs[kb_id]
            self.scheduler.resume_job(job_id)

            logger.info(f"Resumed sync for {kb_id}")
            return True

        except Exception as e:
            logger.error(f"Error resuming sync for {kb_id}: {e}")
            return False

    async def shutdown(self):
        """Shutdown sync service"""
        logger.info("Shutting down KB sync service...")

        if self.scheduler:
            self.scheduler.shutdown()

        self._save_status()

        logger.info("KB sync service shut down")

    def get_statistics(self) -> Dict:
        """Get sync statistics"""
        total_syncs = sum(s.total_syncs for s in self.sync_status.values())
        successful_syncs = sum(s.successful_syncs for s in self.sync_status.values())
        failed_syncs = sum(s.failed_syncs for s in self.sync_status.values())

        status_counts = {}
        for status in self.sync_status.values():
            status_counts[status.last_status] = status_counts.get(status.last_status, 0) + 1

        return {
            'total_kbs': len(self.sync_status),
            'scheduled_syncs': len(self.sync_jobs),
            'total_syncs': total_syncs,
            'successful_syncs': successful_syncs,
            'failed_syncs': failed_syncs,
            'success_rate': successful_syncs / total_syncs if total_syncs > 0 else 0,
            'status_counts': status_counts
        }

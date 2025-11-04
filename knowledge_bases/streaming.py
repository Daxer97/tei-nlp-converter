"""
KB Streaming Service

Manages background streaming of knowledge base data into the cache system.
"""
from typing import Dict, List, Optional
import asyncio
from datetime import datetime
from dataclasses import dataclass

from knowledge_bases.base import KnowledgeBaseProvider, KBEntity
from knowledge_bases.cache import MultiTierCacheManager
from knowledge_bases.registry import KnowledgeBaseRegistry
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class StreamProgress:
    """Track streaming progress"""
    kb_id: str
    entity_type: Optional[str]
    entities_streamed: int = 0
    batches_processed: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: str = "pending"  # pending, running, completed, failed
    error_message: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            'kb_id': self.kb_id,
            'entity_type': self.entity_type,
            'entities_streamed': self.entities_streamed,
            'batches_processed': self.batches_processed,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'status': self.status,
            'error_message': self.error_message,
            'duration_seconds': (
                (self.end_time - self.start_time).total_seconds()
                if self.start_time and self.end_time else None
            )
        }


class KBStreamingService:
    """
    Service for streaming KB data in background

    Features:
    - Parallel streaming from multiple KBs
    - Progress tracking
    - Error recovery
    - Rate limiting
    - Graceful shutdown
    """

    def __init__(
        self,
        kb_registry: KnowledgeBaseRegistry,
        cache_manager: MultiTierCacheManager,
        max_concurrent_streams: int = 3
    ):
        self.kb_registry = kb_registry
        self.cache_manager = cache_manager
        self.max_concurrent_streams = max_concurrent_streams

        self.active_streams: Dict[str, asyncio.Task] = {}
        self.stream_progress: Dict[str, StreamProgress] = {}
        self._shutdown = False
        self._semaphore = asyncio.Semaphore(max_concurrent_streams)

    async def stream_kb(
        self,
        kb_id: str,
        entity_types: Optional[List[str]] = None,
        batch_size: int = 1000,
        since: Optional[datetime] = None
    ) -> StreamProgress:
        """
        Stream KB data into cache

        Args:
            kb_id: Knowledge base identifier
            entity_types: Optional list of entity types to stream
            batch_size: Batch size for streaming
            since: Only stream entities updated since this timestamp

        Returns:
            StreamProgress object
        """
        # Create progress tracker
        progress_key = f"{kb_id}:{entity_types or 'all'}"
        progress = StreamProgress(
            kb_id=kb_id,
            entity_type=','.join(entity_types) if entity_types else None
        )
        self.stream_progress[progress_key] = progress

        try:
            progress.status = "running"
            progress.start_time = datetime.now()

            # Get KB provider
            provider = self.kb_registry.get_provider(kb_id)
            if not provider:
                raise ValueError(f"KB provider not found: {kb_id}")

            # Stream all specified entity types (or all if none specified)
            if entity_types:
                for entity_type in entity_types:
                    await self._stream_entity_type(
                        provider, entity_type, batch_size, since, progress
                    )
            else:
                await self._stream_entity_type(
                    provider, None, batch_size, since, progress
                )

            progress.status = "completed"
            progress.end_time = datetime.now()

            logger.info(
                f"Completed streaming {kb_id}: "
                f"{progress.entities_streamed} entities in "
                f"{progress.batches_processed} batches"
            )

        except Exception as e:
            progress.status = "failed"
            progress.error_message = str(e)
            progress.end_time = datetime.now()

            logger.error(f"Error streaming {kb_id}: {e}")

        return progress

    async def _stream_entity_type(
        self,
        provider: KnowledgeBaseProvider,
        entity_type: Optional[str],
        batch_size: int,
        since: Optional[datetime],
        progress: StreamProgress
    ):
        """Stream a specific entity type"""
        try:
            async for batch in provider.stream_entities(entity_type, batch_size, since):
                # Check for shutdown
                if self._shutdown:
                    logger.info(f"Streaming interrupted by shutdown: {provider.get_kb_id()}")
                    break

                # Store batch in cache
                await self.cache_manager.bulk_insert(batch)

                # Update progress
                progress.entities_streamed += len(batch)
                progress.batches_processed += 1

                if progress.batches_processed % 10 == 0:
                    logger.info(
                        f"Streamed {progress.entities_streamed} entities "
                        f"from {provider.get_kb_id()}"
                    )

        except Exception as e:
            logger.error(
                f"Error streaming entity type {entity_type} "
                f"from {provider.get_kb_id()}: {e}"
            )
            raise

    async def stream_kb_background(
        self,
        kb_id: str,
        entity_types: Optional[List[str]] = None,
        batch_size: int = 1000,
        since: Optional[datetime] = None
    ) -> str:
        """
        Stream KB data in background task

        Args:
            kb_id: Knowledge base identifier
            entity_types: Optional list of entity types to stream
            batch_size: Batch size for streaming
            since: Only stream entities updated since this timestamp

        Returns:
            Task identifier for tracking
        """
        task_id = f"{kb_id}:{entity_types or 'all'}:{datetime.now().timestamp()}"

        async def stream_task():
            async with self._semaphore:  # Limit concurrent streams
                return await self.stream_kb(kb_id, entity_types, batch_size, since)

        task = asyncio.create_task(stream_task())
        self.active_streams[task_id] = task

        logger.info(f"Started background streaming: {task_id}")
        return task_id

    def get_progress(self, task_id: str) -> Optional[StreamProgress]:
        """Get streaming progress"""
        # Find matching progress
        for key, progress in self.stream_progress.items():
            if task_id.startswith(key):
                return progress

        return None

    def get_all_progress(self) -> Dict[str, StreamProgress]:
        """Get all streaming progress"""
        return self.stream_progress.copy()

    async def wait_for_stream(self, task_id: str, timeout: Optional[float] = None):
        """Wait for a streaming task to complete"""
        task = self.active_streams.get(task_id)

        if not task:
            logger.warning(f"Stream task not found: {task_id}")
            return None

        try:
            if timeout:
                return await asyncio.wait_for(task, timeout=timeout)
            else:
                return await task

        except asyncio.TimeoutError:
            logger.warning(f"Stream task timed out: {task_id}")
            return None

    async def cancel_stream(self, task_id: str) -> bool:
        """Cancel a streaming task"""
        task = self.active_streams.get(task_id)

        if not task:
            return False

        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            logger.info(f"Cancelled stream task: {task_id}")

        # Remove from active streams
        del self.active_streams[task_id]

        # Update progress
        progress = self.get_progress(task_id)
        if progress:
            progress.status = "cancelled"
            progress.end_time = datetime.now()

        return True

    async def shutdown(self, timeout: float = 30.0):
        """Graceful shutdown of streaming service"""
        logger.info("Shutting down KB streaming service...")

        self._shutdown = True

        # Cancel all active streams
        tasks = list(self.active_streams.values())

        if tasks:
            logger.info(f"Cancelling {len(tasks)} active streams...")

            for task in tasks:
                task.cancel()

            # Wait for cancellation with timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning("Some streams did not complete within timeout")

        self.active_streams.clear()
        logger.info("KB streaming service shut down")

    def get_statistics(self) -> Dict:
        """Get streaming statistics"""
        total_entities = sum(
            p.entities_streamed for p in self.stream_progress.values()
        )

        total_batches = sum(
            p.batches_processed for p in self.stream_progress.values()
        )

        status_counts = {}
        for progress in self.stream_progress.values():
            status_counts[progress.status] = status_counts.get(progress.status, 0) + 1

        return {
            'active_streams': len(self.active_streams),
            'total_streams': len(self.stream_progress),
            'total_entities_streamed': total_entities,
            'total_batches_processed': total_batches,
            'status_counts': status_counts,
            'max_concurrent_streams': self.max_concurrent_streams
        }

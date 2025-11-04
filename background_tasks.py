"""
Background task management for async processing
"""
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import uuid
from logger import get_logger

# Import TaskStatus from storage
from storage import TaskStatus

logger = get_logger(__name__)

class Task:
    def __init__(self, task_id: str, data: Dict[str, Any]):
        self.id = task_id
        self.status = TaskStatus.PENDING
        self.data = data
        self.result = None
        self.error = None
        self.created_at = datetime.utcnow()
        self.started_at = None
        self.completed_at = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status.value,
            "data": self.data,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration": (self.completed_at - self.started_at).total_seconds() 
                       if self.completed_at and self.started_at else None
        }

class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.max_tasks = 1000
        self.task_ttl = timedelta(hours=24)
    
    def create_task(self, task_id: str, data: Dict[str, Any]) -> Task:
        """Create a new task"""
        if len(self.tasks) >= self.max_tasks:
            # Clean up old tasks
            self._cleanup_old_tasks_sync()
        
        task = Task(task_id, data)
        self.tasks[task_id] = task
        logger.info(f"Created task: {task_id}")
        return task
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task by ID"""
        task = self.tasks.get(task_id)
        return task.to_dict() if task else None
    
    def update_task(
        self, 
        task_id: str, 
        status: TaskStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        """Update task status"""
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"Task not found: {task_id}")
            return
        
        task.status = status
        
        if status == TaskStatus.PROCESSING:
            task.started_at = datetime.utcnow()
        elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            task.completed_at = datetime.utcnow()
            task.result = result
            task.error = error
        
        logger.info(f"Updated task {task_id}: {status.value}")
    
    def _cleanup_old_tasks_sync(self):
        """Synchronously clean up old tasks"""
        cutoff = datetime.utcnow() - self.task_ttl
        old_tasks = [
            task_id for task_id, task in self.tasks.items()
            if task.created_at < cutoff
        ]
        
        for task_id in old_tasks:
            del self.tasks[task_id]
        
        if old_tasks:
            logger.info(f"Cleaned up {len(old_tasks)} old tasks")
    
    async def cleanup_old_tasks(self):
        """Periodically clean up old tasks"""
        while True:
            await asyncio.sleep(3600)  # Run every hour
            self._cleanup_old_tasks_sync()

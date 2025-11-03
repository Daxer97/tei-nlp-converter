"""
storage.py - Enhanced storage with proper locking and error handling
"""
import time
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Index, Boolean, JSON, Enum, text, func, select
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.pool import QueuePool, NullPool
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from contextlib import contextmanager
import json
import uuid
import enum
from logger import get_logger
from config import settings
import threading

logger = get_logger(__name__)

Base = declarative_base()

class TaskStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStateMachine:
    """Validates task status transitions to prevent invalid state changes"""

    # Define valid transitions
    VALID_TRANSITIONS = {
        TaskStatus.PENDING: {TaskStatus.PROCESSING, TaskStatus.CANCELLED},
        TaskStatus.PROCESSING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
        TaskStatus.COMPLETED: set(),  # Terminal state - no transitions allowed
        TaskStatus.FAILED: set(),      # Terminal state - no transitions allowed
        TaskStatus.CANCELLED: set(),   # Terminal state - no transitions allowed
    }

    @classmethod
    def is_valid_transition(cls, from_status: TaskStatus, to_status: TaskStatus) -> bool:
        """
        Check if a state transition is valid

        Args:
            from_status: Current task status
            to_status: Desired new status

        Returns:
            True if transition is valid, False otherwise
        """
        # Allow same-status "transitions" (idempotent updates)
        if from_status == to_status:
            return True

        return to_status in cls.VALID_TRANSITIONS.get(from_status, set())

    @classmethod
    def is_terminal_state(cls, status: TaskStatus) -> bool:
        """Check if a status is a terminal state (no transitions allowed)"""
        return len(cls.VALID_TRANSITIONS.get(status, set())) == 0

    @classmethod
    def is_active_state(cls, status: TaskStatus) -> bool:
        """Check if a status represents an active task"""
        return status in {TaskStatus.PENDING, TaskStatus.PROCESSING}


class ProcessedText(Base):
    __tablename__ = 'processed_texts'
    
    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    domain = Column(String(50), nullable=False, index=True)
    nlp_results = Column(Text, nullable=False)
    tei_xml = Column(Text, nullable=False)
    text_hash = Column(String(64), index=True)
    processing_time = Column(Float)
    request_id = Column(String(36), index=True)
    user_id = Column(String(255), index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_domain_created', 'domain', 'created_at'),
        Index('idx_hash_domain', 'text_hash', 'domain'),
        Index('idx_user_created', 'user_id', 'created_at'),
    )

class BackgroundTask(Base):
    __tablename__ = 'background_tasks'

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(36), unique=True, nullable=False, index=True)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING)
    input_data = Column(JSON, nullable=False)
    result = Column(JSON)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    retry_count = Column(Integer, default=0)
    request_id = Column(String(36), index=True)
    version = Column(Integer, default=0, nullable=False)  # Optimistic locking

    __table_args__ = (
        Index('idx_task_status_created', 'status', 'created_at'),
        Index('idx_request_id', 'request_id'),
    )

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    # Use a safe Python attribute name, but keep DB column as "metadata"
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    request_id = Column(String(36), index=True)
    user_id = Column(String(255), index=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50))
    resource_id = Column(String(100))
    ip_address = Column(String(45))
    user_agent = Column(Text)
    status_code = Column(Integer)
    error_message = Column(Text)
    meta = Column("metadata", JSON)   # ✅ works fine    

    __table_args__ = (
        Index('idx_audit_user_timestamp', 'user_id', 'timestamp'),
        Index('idx_audit_action_timestamp', 'action', 'timestamp'),
    )


class Storage:
    def __init__(self, db_url: str = None):
        """Initialize storage with enhanced connection pooling and thread safety"""
        self.db_url = db_url or settings.get('database_url')
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        
        # Determine if we're using PostgreSQL or SQLite
        self.is_postgresql = 'postgresql' in self.db_url
        self.is_sqlite = 'sqlite' in self.db_url
        
        # PostgreSQL optimized settings
        if self.is_postgresql:
            pool_class = QueuePool
            connect_args = {
                "connect_timeout": 10,
                "options": "-c statement_timeout=30000"  # 30 second statement timeout
            }
            pool_size = settings.get('database_pool_size', 20)
            max_overflow = settings.get('database_max_overflow', 40)
            pool_recycle = settings.get('database_pool_recycle', 3600)
        else:
            # SQLite settings
            pool_class = NullPool  # No pooling for SQLite
            connect_args = {
                "check_same_thread": False,
                "timeout": 30  # 30 second busy timeout
            }
            pool_size = 1
            max_overflow = 0
            pool_recycle = -1
        
        self.engine = create_engine(
            self.db_url,
            poolclass=pool_class,    # ✅ correct
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_pre_ping=True,
            echo=settings.get('debug', False),
            connect_args=connect_args
        )

        
        # Use thread-local sessions for thread safety
        self.SessionFactory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.Session = scoped_session(self.SessionFactory)
        
        logger.info(f"Storage initialized with database: {self.db_url}")
    
    def init_db(self):
        """Initialize database tables with retry logic"""
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                with self._lock:
                    Base.metadata.create_all(bind=self.engine)
                    logger.info("Database tables initialized")
                    return
            except OperationalError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Database init attempt {attempt + 1} failed: {e}")
                    time.sleep(retry_delay * (2 ** attempt))
                else:
                    logger.error(f"Database initialization failed after {max_retries} attempts: {e}")
                    raise
    
    @contextmanager
    def get_session(self) -> Session:
        """Get a database session with automatic cleanup and proper error handling"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Database integrity error: {str(e)}")
            raise
        except OperationalError as e:
            session.rollback()
            logger.error(f"Database operational error: {str(e)}")
            raise
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Database error: {str(e)}")
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Unexpected error in database session: {str(e)}")
            raise
        finally:
            session.close()
    
    @contextmanager
    def transaction(self) -> Session:
        """Explicit transaction context with proper isolation"""
        session = self.Session()
        
        # Set appropriate isolation level based on database
        if self.is_postgresql:
            session.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
        
        try:
            yield session
            session.commit()
            logger.debug("Transaction committed successfully")
        except Exception as e:
            session.rollback()
            logger.error(f"Transaction rolled back: {str(e)}")
            raise
        finally:
            session.close()
    
    def update_task(self, task_id: str, status: TaskStatus,
                   result: Optional[Dict] = None, error: Optional[str] = None,
                   expected_version: Optional[int] = None) -> Optional[Tuple[BackgroundTask, bool]]:
        """
        Update task status with optimistic locking and state machine validation

        Args:
            task_id: Task ID to update
            status: New status
            result: Task result (optional)
            error: Error message (optional)
            expected_version: Expected version for optimistic locking (optional)

        Returns:
            Tuple of (updated_task, should_decrement_counter) or None if not found
            should_decrement_counter is True if this update moved task from active to terminal

        Raises:
            ValueError: If state transition is invalid or version mismatch
        """
        with self.transaction() as session:
            # Use appropriate locking mechanism based on database
            if self.is_postgresql:
                # PostgreSQL supports FOR UPDATE
                task = session.query(BackgroundTask).filter(
                    BackgroundTask.task_id == task_id
                ).with_for_update().first()
            else:
                # SQLite doesn't support FOR UPDATE, use immediate transaction
                session.execute(text("BEGIN IMMEDIATE"))
                task = session.query(BackgroundTask).filter(
                    BackgroundTask.task_id == task_id
                ).first()

            if not task:
                logger.warning(f"Task {task_id} not found for update")
                return None

            # Optimistic locking: check version if provided
            if expected_version is not None and task.version != expected_version:
                raise ValueError(
                    f"Version mismatch for task {task_id}: "
                    f"expected {expected_version}, got {task.version}. "
                    f"Task was modified by another process."
                )

            # State machine validation
            old_status = task.status
            if not TaskStateMachine.is_valid_transition(old_status, status):
                raise ValueError(
                    f"Invalid state transition for task {task_id}: "
                    f"{old_status.value} → {status.value}. "
                    f"Valid transitions from {old_status.value}: "
                    f"{[s.value for s in TaskStateMachine.VALID_TRANSITIONS.get(old_status, set())]}"
                )

            # Determine if we should decrement active task counter
            # Only decrement if transitioning from active state to terminal state
            was_active = TaskStateMachine.is_active_state(old_status)
            is_now_terminal = TaskStateMachine.is_terminal_state(status)
            should_decrement = was_active and is_now_terminal

            # Update task fields
            task.status = status
            task.version += 1  # Increment version for optimistic locking

            if status == TaskStatus.PROCESSING:
                task.started_at = datetime.utcnow()
            elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                task.completed_at = datetime.utcnow()
                task.result = result
                task.error = error[:1000] if error else None  # Limit error message length

            session.flush()
            logger.info(
                f"Updated task {task_id}: {old_status.value} → {status.value} "
                f"(version {task.version - 1} → {task.version}, decrement={should_decrement})"
            )
            return (task, should_decrement)
    
    def get_tasks_by_status(self, status: TaskStatus) -> List[BackgroundTask]:
        """Get tasks by status with proper handling"""
        with self.get_session() as session:
            return session.query(BackgroundTask).filter(
                BackgroundTask.status == status
            ).all()
    
    def check_connection(self) -> bool:
        """Check database connection health"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False
    
    # Text Processing Methods
    def get_texts_by_domain_and_user(self, domain: str, user_id: str, 
                                     limit: int = 50, offset: int = 0) -> List[ProcessedText]:
        """Get texts filtered by domain and user"""
        with self.get_session() as session:
            return session.query(ProcessedText)\
                         .filter(ProcessedText.domain == domain, 
                                ProcessedText.user_id == user_id)\
                         .order_by(ProcessedText.created_at.desc())\
                         .limit(limit)\
                         .offset(offset)\
                         .all()
    
    def get_recent_texts_by_user(self, user_id: str, limit: int = 50, 
                                 offset: int = 0) -> List[ProcessedText]:
        """Get recent texts for a specific user"""
        with self.get_session() as session:
            return session.query(ProcessedText)\
                         .filter(ProcessedText.user_id == user_id)\
                         .order_by(ProcessedText.created_at.desc())\
                         .limit(limit)\
                         .offset(offset)\
                         .all()
    
    def count_texts_by_user(self, user_id: str, domain: Optional[str] = None) -> int:
        """Count texts for a specific user"""
        with self.get_session() as session:
            query = session.query(func.count(ProcessedText.id))\
                          .filter(ProcessedText.user_id == user_id)
            if domain:
                query = query.filter(ProcessedText.domain == domain)
            return query.scalar() or 0
    
    def save_processed_text(self, text: str, domain: str, nlp_results: dict, 
                           tei_xml: str, text_hash: str = None,
                           processing_time: float = None, request_id: str = None, 
                           user_id: str = None) -> ProcessedText:
        """Save processed text with transaction management"""
        with self.transaction() as session:
            try:
                processed_text = ProcessedText(
                    text=text,
                    domain=domain,
                    nlp_results=json.dumps(nlp_results),
                    tei_xml=tei_xml,
                    text_hash=text_hash,
                    processing_time=processing_time,
                    request_id=request_id,
                    user_id=user_id or "anonymous"
                )
                session.add(processed_text)
                session.flush()
                session.refresh(processed_text)
                
                # Log successful save
                logger.info(f"Saved processed text {processed_text.id} for user {user_id}")
                return processed_text
                
            except IntegrityError as e:
                logger.error(f"Integrity error saving text: {e}")
                raise ValueError("Duplicate text or constraint violation")
    
    def get_processed_text(self, text_id: int) -> Optional[ProcessedText]:
        """Get processed text by ID"""
        with self.get_session() as session:
            return session.query(ProcessedText).filter(ProcessedText.id == text_id).first()
    
    def delete_text(self, text_id: int, user_id: Optional[str] = None) -> bool:
        """Delete text with optional user verification"""
        with self.transaction() as session:
            query = session.query(ProcessedText).filter(ProcessedText.id == text_id)
            if user_id:
                query = query.filter(ProcessedText.user_id == user_id)
            
            text = query.first()
            if text:
                session.delete(text)
                logger.info(f"Deleted text {text_id}")
                return True
            return False
    
    # Task Management Methods
    def create_task(self, task_id: str, input_data: Dict[str, Any], 
                   request_id: Optional[str] = None) -> BackgroundTask:
        """Create a new background task"""
        with self.transaction() as session:
            task = BackgroundTask(
                task_id=task_id,
                status=TaskStatus.PENDING,
                input_data=input_data,
                request_id=request_id
            )
            session.add(task)
            session.flush()
            session.refresh(task)
            logger.info(f"Created task {task_id}")
            return task
    
    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Get task by ID"""
        with self.get_session() as session:
            return session.query(BackgroundTask).filter(
                BackgroundTask.task_id == task_id
            ).first()
    
    def get_stale_tasks(self, hours: int = 24) -> List[BackgroundTask]:
        """Get tasks older than specified hours"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        with self.get_session() as session:
            return session.query(BackgroundTask).filter(
                BackgroundTask.created_at < cutoff,
                BackgroundTask.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING])
            ).all()
    
    def cleanup_old_tasks(self, days: int = None) -> int:
        """Clean up old completed/failed tasks"""
        days = days or settings.task_retention_days
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        with self.transaction() as session:
            deleted = session.query(BackgroundTask).filter(
                BackgroundTask.completed_at < cutoff,
                BackgroundTask.status.in_([TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED])
            ).delete(synchronize_session=False)
            
            logger.info(f"Cleaned up {deleted} old tasks")
            return deleted
    
    # Audit Logging Methods
    def log_audit(self, action: str, request_id: str = None, user_id: str = None,
                 resource_type: str = None, resource_id: str = None,
                 ip_address: str = None, user_agent: str = None,
                 status_code: int = None, error_message: str = None,
                 metadata: Dict = None):
        """Create audit log entry"""
        if not settings.enable_audit_log:
            return
        
        try:
            with self.get_session() as session:
                audit = AuditLog(
                    request_id=request_id,
                    user_id=user_id or "anonymous",
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    status_code=status_code,
                    error_message=error_message,
                    metadata=metadata
                )
                session.add(audit)
        except Exception as e:
            # Don't fail the main operation if audit logging fails
            logger.error(f"Audit logging failed: {e}")
    
    def get_audit_logs(self, user_id: str = None, action: str = None,
                      start_date: datetime = None, end_date: datetime = None,
                      limit: int = 100) -> List[AuditLog]:
        """Query audit logs"""
        with self.get_session() as session:
            query = session.query(AuditLog)
            
            if user_id:
                query = query.filter(AuditLog.user_id == user_id)
            if action:
                query = query.filter(AuditLog.action == action)
            if start_date:
                query = query.filter(AuditLog.timestamp >= start_date)
            if end_date:
                query = query.filter(AuditLog.timestamp <= end_date)
            
            return query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    
    # Data Retention
    def cleanup_old_data(self, days: int = None) -> Dict[str, int]:
        """Clean up old data based on retention policy"""
        days = days or settings.data_retention_days
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        with self.transaction() as session:
            # Clean processed texts
            deleted_texts = session.query(ProcessedText).filter(
                ProcessedText.created_at < cutoff
            ).delete(synchronize_session=False)
            
            # Clean audit logs (keep longer)
            audit_cutoff = datetime.utcnow() - timedelta(days=days * 2)
            deleted_audits = session.query(AuditLog).filter(
                AuditLog.timestamp < audit_cutoff
            ).delete(synchronize_session=False)
            
            # Clean old tasks
            task_cutoff = datetime.utcnow() - timedelta(days=days // 2)
            deleted_tasks = session.query(BackgroundTask).filter(
                BackgroundTask.completed_at < task_cutoff,
                BackgroundTask.status.in_([TaskStatus.COMPLETED, TaskStatus.FAILED])
            ).delete(synchronize_session=False)
            
            logger.info(f"Data cleanup: {deleted_texts} texts, {deleted_audits} audit logs, {deleted_tasks} tasks")
            
            return {
                "texts": deleted_texts,
                "audit_logs": deleted_audits,
                "tasks": deleted_tasks
            }
    
    # Statistics
    def get_statistics(self) -> Dict[str, Any]:
        """Get application statistics"""
        with self.get_session() as session:
            total_texts = session.query(func.count(ProcessedText.id)).scalar() or 0
            total_tasks = session.query(func.count(BackgroundTask.id)).scalar() or 0
            active_tasks = session.query(func.count(BackgroundTask.id)).filter(
                BackgroundTask.status == TaskStatus.PROCESSING
            ).scalar() or 0
            
            # Get domain distribution
            domain_stats = session.query(
                ProcessedText.domain,
                func.count(ProcessedText.id).label('count')
            ).group_by(ProcessedText.domain).all()
            
            return {
                "total_texts": total_texts,
                "total_tasks": total_tasks,
                "active_tasks": active_tasks,
                "domains": {domain: count for domain, count in domain_stats}
            }
    
    def close(self):
        """Close all database connections"""
        self.Session.remove()
        self.engine.dispose()
        logger.info("Database connections closed")

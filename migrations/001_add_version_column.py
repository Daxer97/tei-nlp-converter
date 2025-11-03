"""
Migration: Add version column to background_tasks for optimistic locking

This migration adds a version column to the background_tasks table to support
optimistic locking and prevent race conditions in concurrent task updates.

Date: 2025-11-03
"""
from sqlalchemy import create_engine, text, inspect
from config import settings
from logger import get_logger

logger = get_logger(__name__)


def upgrade(engine):
    """Add version column to background_tasks table"""
    logger.info("Running migration: Add version column to background_tasks")

    with engine.connect() as conn:
        # Check if column already exists
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('background_tasks')]

        if 'version' in columns:
            logger.info("Column 'version' already exists, skipping migration")
            return

        # Add version column with default value of 0
        if engine.dialect.name == 'postgresql':
            conn.execute(text(
                "ALTER TABLE background_tasks "
                "ADD COLUMN version INTEGER NOT NULL DEFAULT 0"
            ))
        elif engine.dialect.name == 'sqlite':
            conn.execute(text(
                "ALTER TABLE background_tasks "
                "ADD COLUMN version INTEGER NOT NULL DEFAULT 0"
            ))
        else:
            raise ValueError(f"Unsupported database dialect: {engine.dialect.name}")

        conn.commit()
        logger.info("Successfully added version column to background_tasks")


def downgrade(engine):
    """Remove version column from background_tasks table"""
    logger.info("Running migration rollback: Remove version column from background_tasks")

    with engine.connect() as conn:
        # Check if column exists
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('background_tasks')]

        if 'version' not in columns:
            logger.info("Column 'version' does not exist, skipping rollback")
            return

        # Drop version column
        if engine.dialect.name == 'postgresql':
            conn.execute(text(
                "ALTER TABLE background_tasks DROP COLUMN version"
            ))
        elif engine.dialect.name == 'sqlite':
            # SQLite doesn't support DROP COLUMN directly, need to recreate table
            logger.warning(
                "SQLite doesn't support DROP COLUMN. "
                "Manual table recreation required for rollback."
            )
            # For SQLite, you would need to:
            # 1. Create new table without version column
            # 2. Copy data
            # 3. Drop old table
            # 4. Rename new table
            # This is complex and risky, so we just log a warning
            return
        else:
            raise ValueError(f"Unsupported database dialect: {engine.dialect.name}")

        conn.commit()
        logger.info("Successfully removed version column from background_tasks")


def run_migration():
    """Run the migration on the configured database"""
    from storage import Storage

    storage = Storage()
    try:
        upgrade(storage.engine)
        logger.info("Migration completed successfully")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    run_migration()

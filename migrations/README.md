# Database Migrations

This directory contains database migration scripts for the TEI NLP Converter.

## Available Migrations

### 001_add_version_column.py
Adds a `version` column to the `background_tasks` table to support optimistic locking and prevent race conditions in concurrent task updates.

**Date**: 2025-11-03
**Type**: Schema change
**Impact**: Fixes critical race condition in task status updates

## Running Migrations

### Automatic (Recommended)

The migration will be applied automatically on application startup if the column doesn't exist.

### Manual

To run a specific migration manually:

```bash
python migrations/001_add_version_column.py
```

### Using Python API

```python
from migrations.migration_001_add_version_column import run_migration

run_migration()
```

## Migration Safety

- All migrations check if changes are already applied before running
- PostgreSQL and SQLite are supported
- Migrations are wrapped in transactions for safety
- Rollback functions are provided (where supported)

## Creating New Migrations

1. Create a new file: `migrations/00X_description.py`
2. Implement `upgrade(engine)` and `downgrade(engine)` functions
3. Add migration documentation to this README
4. Test with both PostgreSQL and SQLite

### Migration Template

```python
"""
Migration: Description of what this migration does

Date: YYYY-MM-DD
"""
from sqlalchemy import create_engine, text, inspect
from logger import get_logger

logger = get_logger(__name__)


def upgrade(engine):
    """Apply the migration"""
    logger.info("Running migration: Description")

    with engine.connect() as conn:
        # Check if already applied
        inspector = inspect(engine)
        # ... check logic ...

        # Apply migration
        if engine.dialect.name == 'postgresql':
            # PostgreSQL-specific SQL
            pass
        elif engine.dialect.name == 'sqlite':
            # SQLite-specific SQL
            pass

        conn.commit()
        logger.info("Migration completed successfully")


def downgrade(engine):
    """Rollback the migration"""
    logger.info("Rolling back migration: Description")

    with engine.connect() as conn:
        # Check if can rollback
        # ...

        # Rollback migration
        if engine.dialect.name == 'postgresql':
            # PostgreSQL-specific SQL
            pass
        elif engine.dialect.name == 'sqlite':
            # SQLite-specific SQL (may not support all operations)
            pass

        conn.commit()
        logger.info("Rollback completed successfully")


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
```

## Troubleshooting

### "Column already exists" error
The migration has already been applied. This is safe to ignore.

### "Permission denied" error
Ensure the database user has ALTER TABLE permissions.

### SQLite rollback limitations
SQLite doesn't support all ALTER TABLE operations. Some rollbacks may require manual intervention.

## Database Compatibility

- ✅ PostgreSQL 12+
- ✅ SQLite 3.8+
- ❌ MySQL (not tested)
- ❌ MariaDB (not tested)

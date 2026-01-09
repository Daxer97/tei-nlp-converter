"""
tests/test_storage_pool.py - Tests for SQLAlchemy pool configuration

Validates that the Storage class correctly configures create_engine() based on
database type (SQLite vs PostgreSQL), ensuring pool arguments are only passed
when the pool class supports them.

Fixes: TypeError: Invalid argument(s) 'pool_size','max_overflow' sent to
create_engine() when using SQLite with NullPool
"""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.pool import NullPool, QueuePool


class TestStoragePoolConfiguration:
    """Test Storage class pool configuration based on database type"""

    def test_sqlite_uses_nullpool_without_pool_args(self):
        """SQLite should use NullPool without pool_size/max_overflow arguments"""
        from storage import Storage

        # Create storage with SQLite URL - this should NOT raise TypeError
        storage = Storage("sqlite:///test_pool.db")

        # Verify NullPool is used
        assert storage.engine.pool.__class__ == NullPool
        assert storage.is_sqlite is True
        assert storage.is_postgresql is False

        storage.close()

    def test_sqlite_memory_database(self):
        """In-memory SQLite database should work with NullPool"""
        from storage import Storage

        # Create storage with in-memory SQLite
        storage = Storage("sqlite:///:memory:")

        assert storage.engine.pool.__class__ == NullPool
        assert storage.is_sqlite is True

        # Verify database is functional
        storage.init_db()
        assert storage.check_connection() is True

        storage.close()

    def test_sqlite_file_database(self, tmp_path):
        """File-based SQLite database should work with NullPool"""
        from storage import Storage

        db_path = tmp_path / "test.db"
        storage = Storage(f"sqlite:///{db_path}")

        assert storage.engine.pool.__class__ == NullPool
        assert storage.is_sqlite is True

        # Verify database is functional
        storage.init_db()
        assert storage.check_connection() is True

        storage.close()

    @patch('storage.create_engine')
    def test_postgresql_uses_queuepool_with_pool_args(self, mock_create_engine):
        """PostgreSQL should use QueuePool with pool_size/max_overflow arguments"""
        from storage import Storage

        # Mock the engine to avoid actual PostgreSQL connection
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        # Create storage with PostgreSQL URL
        storage = Storage("postgresql://user:pass@localhost/dbname")

        # Verify create_engine was called with pool arguments
        call_kwargs = mock_create_engine.call_args[1]

        assert call_kwargs['poolclass'] == QueuePool
        assert 'pool_size' in call_kwargs
        assert 'max_overflow' in call_kwargs
        assert 'pool_recycle' in call_kwargs
        assert 'pool_pre_ping' in call_kwargs
        assert call_kwargs['pool_pre_ping'] is True

        # Verify PostgreSQL-specific connect_args
        assert 'connect_args' in call_kwargs
        assert 'connect_timeout' in call_kwargs['connect_args']

        storage.close()

    @patch('storage.create_engine')
    def test_sqlite_does_not_pass_pool_size_args(self, mock_create_engine):
        """SQLite should NOT pass pool_size/max_overflow to create_engine"""
        from storage import Storage

        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        Storage("sqlite:///test.db")

        call_kwargs = mock_create_engine.call_args[1]

        # These should NOT be in kwargs for SQLite
        assert 'pool_size' not in call_kwargs
        assert 'max_overflow' not in call_kwargs
        assert 'pool_recycle' not in call_kwargs
        assert 'pool_pre_ping' not in call_kwargs

        # But should have NullPool
        assert call_kwargs['poolclass'] == NullPool

        # And SQLite-specific connect_args
        assert 'connect_args' in call_kwargs
        assert call_kwargs['connect_args']['check_same_thread'] is False

    def test_storage_initialization_does_not_raise_typeerror(self):
        """
        Regression test: Storage initialization should not raise TypeError
        about invalid pool arguments when using SQLite.

        This was the original production bug where SQLite with NullPool
        received pool_size/max_overflow arguments it doesn't accept.
        """
        from storage import Storage

        # This should NOT raise:
        # TypeError: Invalid argument(s) 'pool_size','max_overflow' sent to
        # create_engine(), using configuration SQLiteDialect_pysqlite/NullPool/Engine
        try:
            storage = Storage("sqlite:///regression_test.db")
            storage.close()
        except TypeError as e:
            if "pool_size" in str(e) or "max_overflow" in str(e):
                pytest.fail(
                    f"Regression: SQLite still receiving invalid pool arguments: {e}"
                )
            raise

    def test_multiple_sqlite_storage_instances(self, tmp_path):
        """Multiple SQLite Storage instances should work independently"""
        from storage import Storage

        db1 = tmp_path / "db1.db"
        db2 = tmp_path / "db2.db"

        storage1 = Storage(f"sqlite:///{db1}")
        storage2 = Storage(f"sqlite:///{db2}")

        storage1.init_db()
        storage2.init_db()

        assert storage1.check_connection() is True
        assert storage2.check_connection() is True

        storage1.close()
        storage2.close()

    @patch('storage.settings')
    @patch('storage.create_engine')
    def test_custom_pool_settings_applied_to_postgresql(
        self, mock_create_engine, mock_settings
    ):
        """Custom pool settings from config should be applied to PostgreSQL"""
        from storage import Storage

        # Configure custom pool settings
        mock_settings.get.side_effect = lambda key, default=None: {
            'database_pool_size': 50,
            'database_max_overflow': 100,
            'database_pool_recycle': 7200,
            'debug': False,
        }.get(key, default)

        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        Storage("postgresql://user:pass@localhost/dbname")

        call_kwargs = mock_create_engine.call_args[1]

        assert call_kwargs['pool_size'] == 50
        assert call_kwargs['max_overflow'] == 100
        assert call_kwargs['pool_recycle'] == 7200


class TestStorageDatabaseOperations:
    """Test that database operations work correctly after pool fix"""

    def test_save_and_retrieve_processed_text(self, tmp_path):
        """Verify basic CRUD operations work with SQLite after pool fix"""
        from storage import Storage

        db_path = tmp_path / "crud_test.db"
        storage = Storage(f"sqlite:///{db_path}")
        storage.init_db()

        # Save a processed text
        saved = storage.save_processed_text(
            text="Test text for pool fix verification",
            domain="default",
            nlp_results={"entities": [], "sentences": []},
            tei_xml="<TEI><text>Test</text></TEI>",
            text_hash="abc123",
            processing_time=0.5,
            request_id="req-123",
            user_id="test-user"
        )

        assert saved.id is not None
        assert saved.text == "Test text for pool fix verification"

        # Retrieve the text
        retrieved = storage.get_processed_text(saved.id)
        assert retrieved is not None
        assert retrieved.domain == "default"

        storage.close()

    def test_concurrent_operations_with_sqlite(self, tmp_path):
        """Test concurrent database operations with SQLite NullPool"""
        import threading
        from storage import Storage

        db_path = tmp_path / "concurrent_test.db"
        storage = Storage(f"sqlite:///{db_path}")
        storage.init_db()

        results = []
        errors = []

        def save_text(index):
            try:
                storage.save_processed_text(
                    text=f"Concurrent text {index}",
                    domain="default",
                    nlp_results={},
                    tei_xml=f"<TEI>{index}</TEI>",
                    user_id="concurrent-user"
                )
                results.append(index)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=save_text, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All operations should succeed
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 5

        storage.close()

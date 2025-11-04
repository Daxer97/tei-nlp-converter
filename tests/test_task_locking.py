"""
Test task locking and race condition fixes
"""
import pytest
from storage import Storage, TaskStatus, TaskStateMachine, BackgroundTask
from datetime import datetime
import threading
import time


def test_state_machine_valid_transitions():
    """Test that valid state transitions are allowed"""
    # PENDING can go to PROCESSING or CANCELLED
    assert TaskStateMachine.is_valid_transition(TaskStatus.PENDING, TaskStatus.PROCESSING)
    assert TaskStateMachine.is_valid_transition(TaskStatus.PENDING, TaskStatus.CANCELLED)

    # PROCESSING can go to COMPLETED, FAILED, or CANCELLED
    assert TaskStateMachine.is_valid_transition(TaskStatus.PROCESSING, TaskStatus.COMPLETED)
    assert TaskStateMachine.is_valid_transition(TaskStatus.PROCESSING, TaskStatus.FAILED)
    assert TaskStateMachine.is_valid_transition(TaskStatus.PROCESSING, TaskStatus.CANCELLED)

    # Same status is always valid (idempotent)
    for status in TaskStatus:
        assert TaskStateMachine.is_valid_transition(status, status)


def test_state_machine_invalid_transitions():
    """Test that invalid state transitions are blocked"""
    # PENDING cannot go directly to COMPLETED or FAILED
    assert not TaskStateMachine.is_valid_transition(TaskStatus.PENDING, TaskStatus.COMPLETED)
    assert not TaskStateMachine.is_valid_transition(TaskStatus.PENDING, TaskStatus.FAILED)

    # Terminal states cannot transition to anything
    assert not TaskStateMachine.is_valid_transition(TaskStatus.COMPLETED, TaskStatus.PROCESSING)
    assert not TaskStateMachine.is_valid_transition(TaskStatus.FAILED, TaskStatus.PROCESSING)
    assert not TaskStateMachine.is_valid_transition(TaskStatus.CANCELLED, TaskStatus.PROCESSING)


def test_state_machine_terminal_states():
    """Test terminal state identification"""
    assert TaskStateMachine.is_terminal_state(TaskStatus.COMPLETED)
    assert TaskStateMachine.is_terminal_state(TaskStatus.FAILED)
    assert TaskStateMachine.is_terminal_state(TaskStatus.CANCELLED)

    assert not TaskStateMachine.is_terminal_state(TaskStatus.PENDING)
    assert not TaskStateMachine.is_terminal_state(TaskStatus.PROCESSING)


def test_state_machine_active_states():
    """Test active state identification"""
    assert TaskStateMachine.is_active_state(TaskStatus.PENDING)
    assert TaskStateMachine.is_active_state(TaskStatus.PROCESSING)

    assert not TaskStateMachine.is_active_state(TaskStatus.COMPLETED)
    assert not TaskStateMachine.is_active_state(TaskStatus.FAILED)
    assert not TaskStateMachine.is_active_state(TaskStatus.CANCELLED)


@pytest.fixture
def storage():
    """Create a test storage instance"""
    # Use in-memory SQLite for testing
    import os
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    storage = Storage()
    storage.init_db()
    yield storage
    # Cleanup
    storage.engine.dispose()


def test_version_column_exists(storage):
    """Test that version column is added to BackgroundTask"""
    task = storage.create_task("test-task-1", {"text": "test"})
    assert hasattr(task, 'version')
    assert task.version == 0


def test_optimistic_locking_version_increment(storage):
    """Test that version is incremented on each update"""
    task = storage.create_task("test-task-2", {"text": "test"})
    assert task.version == 0

    # First update
    result = storage.update_task("test-task-2", TaskStatus.PROCESSING)
    assert result is not None
    updated_task, _ = result
    assert updated_task.version == 1

    # Second update
    result = storage.update_task("test-task-2", TaskStatus.COMPLETED)
    assert result is not None
    updated_task, _ = result
    assert updated_task.version == 2


def test_optimistic_locking_version_mismatch(storage):
    """Test that version mismatch raises error"""
    task = storage.create_task("test-task-3", {"text": "test"})

    # Update to PROCESSING (version becomes 1)
    storage.update_task("test-task-3", TaskStatus.PROCESSING)

    # Try to update with wrong version (expect version 0, but it's actually 1)
    with pytest.raises(ValueError, match="Version mismatch"):
        storage.update_task("test-task-3", TaskStatus.COMPLETED, expected_version=0)


def test_should_decrement_counter(storage):
    """Test that should_decrement flag is set correctly"""
    task = storage.create_task("test-task-4", {"text": "test"})

    # PENDING → PROCESSING: should NOT decrement (still active)
    result = storage.update_task("test-task-4", TaskStatus.PROCESSING)
    task, should_decrement = result
    assert not should_decrement

    # PROCESSING → COMPLETED: should decrement (active → terminal)
    result = storage.update_task("test-task-4", TaskStatus.COMPLETED)
    task, should_decrement = result
    assert should_decrement


def test_should_not_decrement_terminal_to_terminal(storage):
    """Test that terminal → terminal doesn't decrement"""
    task = storage.create_task("test-task-5", {"text": "test"})

    # Go to terminal state
    storage.update_task("test-task-5", TaskStatus.PROCESSING)
    result = storage.update_task("test-task-5", TaskStatus.COMPLETED)
    task, should_decrement = result
    assert should_decrement  # First time entering terminal

    # Try to update terminal state again (should fail due to state machine)
    with pytest.raises(ValueError, match="Invalid state transition"):
        storage.update_task("test-task-5", TaskStatus.FAILED)


def test_invalid_state_transition_raises_error(storage):
    """Test that invalid transitions raise ValueError"""
    task = storage.create_task("test-task-6", {"text": "test"})

    # Try to go directly from PENDING to COMPLETED (invalid)
    with pytest.raises(ValueError, match="Invalid state transition"):
        storage.update_task("test-task-6", TaskStatus.COMPLETED)


def test_concurrent_updates_with_locking(storage):
    """Test that concurrent updates don't cause race conditions"""
    task = storage.create_task("test-task-7", {"text": "test"})

    # Move to PROCESSING
    storage.update_task("test-task-7", TaskStatus.PROCESSING)

    results = []
    errors = []

    def try_complete():
        try:
            result = storage.update_task("test-task-7", TaskStatus.COMPLETED)
            results.append(result)
        except Exception as e:
            errors.append(e)

    def try_fail():
        try:
            result = storage.update_task("test-task-7", TaskStatus.FAILED, error="Test error")
            results.append(result)
        except Exception as e:
            errors.append(e)

    # Try to complete and fail simultaneously
    t1 = threading.Thread(target=try_complete)
    t2 = threading.Thread(target=try_fail)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # One should succeed, one should fail (or get None due to already completed)
    # The important thing is that the task ends up in a valid state
    final_task = storage.get_task("test-task-7")
    assert final_task is not None
    assert final_task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]

    # Check that version was incremented correctly
    # Should be 2 (PENDING→PROCESSING) + 1 (PROCESSING→COMPLETED/FAILED) = 3
    assert final_task.version == 2


def test_idempotent_updates(storage):
    """Test that updating to same status is idempotent"""
    task = storage.create_task("test-task-8", {"text": "test"})

    # Update to PROCESSING
    result1 = storage.update_task("test-task-8", TaskStatus.PROCESSING)
    task1, should_dec1 = result1
    version1 = task1.version

    # Update to PROCESSING again (idempotent)
    result2 = storage.update_task("test-task-8", TaskStatus.PROCESSING)
    task2, should_dec2 = result2
    version2 = task2.version

    # Both should succeed
    assert result1 is not None
    assert result2 is not None

    # Version should increment even for idempotent updates
    assert version2 == version1 + 1

    # Should not decrement counter (still active)
    assert not should_dec1
    assert not should_dec2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

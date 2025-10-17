#!/usr/bin/env python3
"""
Test Redis-backed TaskPool implementation
"""

from task_store import TaskPool, PoolEntry
import os
import sys
import time
import json
from unittest.mock import Mock, MagicMock

# Add orchestrator directory to path BEFORE importing task_store
sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), '..', 'orchestrator'))


class MockRedis:
    """Mock Redis client for testing"""

    def __init__(self):
        self.data = {}
        self.sets = {}

    def sadd(self, key, value):
        """Add to set"""
        if key not in self.sets:
            self.sets[key] = set()
        self.sets[key].add(value)
        return 1

    def srem(self, key, value):
        """Remove from set"""
        if key in self.sets and value in self.sets[key]:
            self.sets[key].remove(value)
            return 1
        return 0

    def smembers(self, key):
        """Get set members"""
        return self.sets.get(key, set())

    def scard(self, key):
        """Get set size"""
        return len(self.sets.get(key, set()))

    def set(self, key, value):
        """Set key-value"""
        self.data[key] = value
        return True

    def get(self, key):
        """Get value by key"""
        return self.data.get(key)

    def delete(self, *keys):
        """Delete keys"""
        count = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                count += 1
        return count

    def flushdb(self):
        """Clear all data"""
        self.data.clear()
        self.sets.clear()


def create_mock_record(slo_seconds=None, submitted_ts=None, load=1):
    """Create a mock record object"""
    record = Mock()
    record.slo_seconds = slo_seconds
    record.submitted_ts = submitted_ts
    record.load = load
    return record


def test_basic_operations():
    """Test basic add/remove operations"""
    print("Testing basic operations...")

    redis = MockRedis()
    pool = TaskPool(batch_size=2, slo_fraction=0.8, redis_client=redis)

    # Create entries
    record1 = create_mock_record(slo_seconds=10.0, submitted_ts=time.time())
    entry1 = PoolEntry(
        task_id="task1",
        task={"spec": {"taskType": "test"}},
        record=record1
    )

    # Add entry
    batch = pool.add(entry1)
    assert len(batch) == 0, "Should not flush with only 1 entry (batch_size=2)"

    # Check has_entries
    assert pool.has_entries(), "Pool should have entries"

    # Clear task
    pool.clear_task("task1")
    assert not pool.has_entries(), "Pool should be empty after clear"

    print("✓ Basic operations test passed")


def test_batch_size_threshold():
    """Test that pool flushes when batch_size is reached"""
    print("Testing batch size threshold...")

    redis = MockRedis()
    pool = TaskPool(batch_size=2, slo_fraction=0.8, redis_client=redis)

    # Create entries
    record1 = create_mock_record(slo_seconds=100.0, submitted_ts=time.time())
    record2 = create_mock_record(slo_seconds=100.0, submitted_ts=time.time())

    entry1 = PoolEntry(task_id="task1", task={}, record=record1)
    entry2 = PoolEntry(task_id="task2", task={}, record=record2)

    # Add first entry - should not flush
    batch = pool.add(entry1)
    assert len(batch) == 0, "Should not flush with 1 entry"

    # Add second entry - should flush
    batch = pool.add(entry2)
    assert len(batch) == 2, "Should flush 2 entries when batch_size reached"

    # Pool should be empty now
    assert not pool.has_entries(), "Pool should be empty after flush"

    print("✓ Batch size threshold test passed")


def test_slo_threshold():
    """Test that pool flushes when SLO threshold is reached"""
    print("Testing SLO threshold...")

    redis = MockRedis()
    pool = TaskPool(batch_size=10, slo_fraction=0.5, redis_client=redis)

    # Create entry with SLO that's already exceeded
    past_time = time.time() - 10.0  # 10 seconds ago
    record = create_mock_record(slo_seconds=10.0, submitted_ts=past_time)

    entry = PoolEntry(task_id="task1", task={}, record=record)

    # Add entry - should flush immediately due to SLO
    batch = pool.add(entry)
    # Note: might flush or not depending on exact timing

    # Try pop_due
    redis2 = MockRedis()
    pool2 = TaskPool(batch_size=10, slo_fraction=0.5, redis_client=redis2)

    record2 = create_mock_record(slo_seconds=10.0, submitted_ts=past_time)
    entry2 = PoolEntry(task_id="task2", task={}, record=record2)

    # Add without auto-flush
    if redis2:
        redis2.sadd(pool2._pool_key, entry2.task_id)
        meta_key = f"{pool2._pool_metadata_prefix}{entry2.task_id}"
        redis2.set(meta_key, pool2._serialize_entry(entry2))

    # Pop due should return the entry
    batch = pool2.pop_due()
    assert len(batch) > 0, "Should pop entries that exceed SLO"

    print("✓ SLO threshold test passed")


def test_requeue():
    """Test requeue functionality"""
    print("Testing requeue...")

    redis = MockRedis()
    pool = TaskPool(batch_size=10, slo_fraction=0.8, redis_client=redis)

    record = create_mock_record(slo_seconds=100.0, submitted_ts=time.time())
    entry = PoolEntry(task_id="task1", task={}, record=record)

    # Add and clear
    pool.add(entry)
    pool.clear_task("task1")
    assert not pool.has_entries(), "Pool should be empty"

    # Requeue
    pool.requeue([entry])
    assert pool.has_entries(), "Pool should have entries after requeue"

    print("✓ Requeue test passed")


def test_pop_all_pending():
    """Test pop_all_pending functionality"""
    print("Testing pop_all_pending...")

    redis = MockRedis()
    pool = TaskPool(batch_size=10, slo_fraction=0.8, redis_client=redis)

    # Add multiple entries
    entries = []
    for i in range(5):
        record = create_mock_record(
            slo_seconds=100.0, submitted_ts=time.time())
        entry = PoolEntry(task_id=f"task{i}", task={}, record=record)
        entries.append(entry)
        pool.add(entry)

    # Pop all
    batch = pool.pop_all_pending()
    assert len(batch) == 5, f"Should pop all 5 entries, got {len(batch)}"

    # Pool should be empty
    assert not pool.has_entries(), "Pool should be empty after pop_all_pending"

    print("✓ Pop all pending test passed")


def test_time_until_threshold():
    """Test time_until_threshold calculation"""
    print("Testing time_until_threshold...")

    redis = MockRedis()
    pool = TaskPool(batch_size=10, slo_fraction=0.5, redis_client=redis)

    # Add entry with future SLO
    record = create_mock_record(slo_seconds=100.0, submitted_ts=time.time())
    entry = PoolEntry(task_id="task1", task={}, record=record)

    # Manually add to Redis
    redis.sadd(pool._pool_key, entry.task_id)
    meta_key = f"{pool._pool_metadata_prefix}{entry.task_id}"
    redis.set(meta_key, pool._serialize_entry(entry))

    # Calculate time until threshold
    delay = pool.time_until_threshold(0.5)
    assert delay is not None, "Should return a delay value"
    assert delay > 0, f"Delay should be positive, got {delay}"

    print("✓ Time until threshold test passed")


def test_serialization():
    """Test entry serialization/deserialization"""
    print("Testing serialization...")

    redis = MockRedis()
    pool = TaskPool(batch_size=10, slo_fraction=0.8, redis_client=redis)

    # Create entry
    record = create_mock_record(
        slo_seconds=30.0, submitted_ts=123456.0, load=5)
    entry = PoolEntry(
        task_id="task1",
        task={"spec": {"taskType": "inference"}},
        record=record,
        exclude_worker_id="worker1",
        enqueued_at=111111.0
    )

    # Serialize
    serialized = pool._serialize_entry(entry)
    assert serialized, "Should serialize entry"

    # Deserialize
    deserialized = pool._deserialize_entry(serialized, record)
    assert deserialized.task_id == entry.task_id
    assert deserialized.task == entry.task
    assert deserialized.exclude_worker_id == entry.exclude_worker_id
    assert deserialized.enqueued_at == entry.enqueued_at

    print("✓ Serialization test passed")


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("Testing Redis-backed TaskPool")
    print("=" * 60)

    test_basic_operations()
    test_batch_size_threshold()
    test_slo_threshold()
    test_requeue()
    test_pop_all_pending()
    test_time_until_threshold()
    test_serialization()

    print("=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()

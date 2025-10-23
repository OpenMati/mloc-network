#!/usr/bin/env python3
"""Debug script to check taskpool status."""

import redis
import json

REDIS_URL = "redis://localhost:6379/0"
rds = redis.from_url(REDIS_URL, decode_responses=True)

pool_key = "taskpool:entries"
pool_metadata_prefix = "taskpool:meta:"

print("=== TaskPool Debug ===")
print(f"Redis URL: {REDIS_URL}")
print()

# Get all task IDs from the set
task_ids = rds.smembers(pool_key)
print(f"Tasks in pool: {len(task_ids)}")
print(f"Task IDs: {list(task_ids)}")
print()

# Check each task's metadata
for task_id in task_ids:
    meta_key = f"{pool_metadata_prefix}{task_id}"
    data = rds.get(meta_key)
    if data:
        try:
            obj = json.loads(data)
            print(f"Task: {task_id}")
            print(f"  Enqueued at: {obj.get('enqueued_at')}")
            print(f"  Exclude worker: {obj.get('exclude_worker_id')}")
            record_data = obj.get('record_data', {})
            print(f"  SLO seconds: {record_data.get('slo_seconds')}")
            print(f"  Load: {record_data.get('load')}")
            print()
        except Exception as e:
            print(f"Task: {task_id} - ERROR: {e}")
            print()
    else:
        print(f"Task: {task_id} - NO METADATA")
        print()

print("=== Checking PoolManager state ===")
print("Note: This requires orchestrator to be running with debug logging enabled")

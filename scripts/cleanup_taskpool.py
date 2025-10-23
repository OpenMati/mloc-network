#!/usr/bin/env python3
"""Clean up orphaned taskpool entries in Redis."""

import redis

REDIS_URL = "redis://localhost:6379/0"
rds = redis.from_url(REDIS_URL, decode_responses=True)

pool_key = "taskpool:entries"
pool_metadata_prefix = "taskpool:meta:"

print("=== Cleaning Orphaned TaskPool Entries ===")

# Get all task IDs from the pool
task_ids = list(rds.smembers(pool_key))
print(f"Found {len(task_ids)} entries in task pool")

if task_ids:
    confirm = input(f"Remove all {len(task_ids)} entries? (yes/no): ")
    if confirm.lower() == 'yes':
        # Remove all entries
        rds.delete(pool_key)
        for task_id in task_ids:
            meta_key = f"{pool_metadata_prefix}{task_id}"
            rds.delete(meta_key)
        print(f"✓ Removed {len(task_ids)} entries from task pool")
    else:
        print("Cancelled")
else:
    print("No entries to clean")

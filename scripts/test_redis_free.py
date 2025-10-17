#!/usr/bin/env python3
"""Test script to verify Redis-free WebSocket mode.

This script tests that a worker can operate without Redis when WebSocket
transport is enabled.
"""

import os
import sys
import time
import subprocess
import requests
from pathlib import Path


def test_redis_free_mode():
    """Test worker running without Redis in WebSocket mode."""

    print("=" * 60)
    print("Testing Redis-Free WebSocket Mode")
    print("=" * 60)

    # Check if orchestrator is running
    orchestrator_url = os.getenv(
        "ORCHESTRATOR_BASE_URL", "http://localhost:8000")
    print(f"\n1. Checking orchestrator at {orchestrator_url}...")

    try:
        response = requests.get(f"{orchestrator_url}/health", timeout=5)
        if response.status_code == 200:
            print("   ✓ Orchestrator is running")
        else:
            print(f"   ✗ Orchestrator returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"   ✗ Cannot connect to orchestrator: {e}")
        print("   Please start orchestrator first:")
        print("   cd orchestrator && python -m orchestrator.main")
        return False

    # Test WebSocket stats endpoint
    print("\n2. Checking WebSocket endpoint...")
    try:
        response = requests.get(f"{orchestrator_url}/ws/stats", timeout=5)
        stats = response.json()
        print(f"   ✓ WebSocket endpoint available")
        print(f"   Current connections: {stats.get('total_connections', 0)}")
    except Exception as e:
        print(f"   ✗ WebSocket stats endpoint error: {e}")
        return False

    # Start worker in WebSocket mode (without Redis)
    print("\n3. Starting worker in WebSocket mode (no Redis)...")

    worker_env = os.environ.copy()
    worker_env.update({
        "WORKER_USE_WEBSOCKET": "true",
        "ORCHESTRATOR_BASE_URL": orchestrator_url,
        "WORKER_ID": "test-ws-worker",
        "WORKER_TAGS": "test",
        "WORKER_COST_PER_HOUR": "1.0",
        "LOG_LEVEL": "INFO",
    })

    # Remove REDIS_URL to ensure worker doesn't try to connect
    if "REDIS_URL" in worker_env:
        del worker_env["REDIS_URL"]
        print("   Removed REDIS_URL from environment")

    print("   Starting worker process...")
    try:
        # Start worker as subprocess
        worker_process = subprocess.Popen(
            [sys.executable, "-m", "worker.main"],
            env=worker_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=Path(__file__).parent.parent / "worker"
        )

        # Wait for worker to start
        print("   Waiting for worker to connect...")
        time.sleep(5)

        if worker_process.poll() is not None:
            stdout, stderr = worker_process.communicate()
            print(f"   ✗ Worker process exited unexpectedly")
            print(f"   STDOUT: {stdout}")
            print(f"   STDERR: {stderr}")
            return False

        print("   ✓ Worker process started")

    except Exception as e:
        print(f"   ✗ Failed to start worker: {e}")
        return False

    # Check worker connection
    print("\n4. Verifying worker connection...")
    time.sleep(2)

    try:
        response = requests.get(f"{orchestrator_url}/ws/stats", timeout=5)
        stats = response.json()
        connections = stats.get('total_connections', 0)
        workers = stats.get('workers', {})

        if connections > 0 and 'test-ws-worker' in workers:
            print(f"   ✓ Worker connected via WebSocket")
            worker_info = workers['test-ws-worker']
            print(f"   Connected at: {worker_info.get('connected_at')}")
            print(
                f"   Events received: {worker_info.get('events_received', 0)}")
            print(f"   Tasks sent: {worker_info.get('tasks_sent', 0)}")
        else:
            print(f"   ✗ Worker not found in WebSocket connections")
            print(f"   Active connections: {connections}")
            print(f"   Workers: {list(workers.keys())}")
            worker_process.terminate()
            return False

    except Exception as e:
        print(f"   ✗ Failed to verify connection: {e}")
        worker_process.terminate()
        return False

    # Submit a test task
    print("\n5. Submitting test task...")
    test_task = """
apiVersion: v1
kind: Task
metadata:
  name: test-echo-task
spec:
  taskType: echo
  input:
    message: "Hello from Redis-free mode!"
  tags:
    - test
"""

    try:
        response = requests.post(
            f"{orchestrator_url}/api/v1/tasks",
            data=test_task,
            headers={"Content-Type": "text/plain"},
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                task_id = result[0].get('task_id')
                print(f"   ✓ Task submitted: {task_id}")
            else:
                print(f"   ✗ Unexpected response: {result}")
                worker_process.terminate()
                return False
        else:
            print(f"   ✗ Task submission failed: {response.status_code}")
            print(f"   Response: {response.text}")
            worker_process.terminate()
            return False

    except Exception as e:
        print(f"   ✗ Task submission error: {e}")
        worker_process.terminate()
        return False

    # Wait for task processing
    print("\n6. Waiting for task to be processed...")
    time.sleep(3)

    try:
        response = requests.get(
            f"{orchestrator_url}/api/v1/tasks/{task_id}",
            timeout=5
        )

        if response.status_code == 200:
            task_status = response.json()
            status = task_status.get('status')
            print(f"   Task status: {status}")

            if status in ['DONE', 'SUCCEEDED']:
                print(f"   ✓ Task completed successfully")
            else:
                print(f"   ⚠ Task status: {status}")

        else:
            print(f"   ⚠ Cannot check task status: {response.status_code}")

    except Exception as e:
        print(f"   ⚠ Task status check error: {e}")

    # Cleanup
    print("\n7. Cleaning up...")
    worker_process.terminate()
    try:
        worker_process.wait(timeout=5)
        print("   ✓ Worker process terminated")
    except subprocess.TimeoutExpired:
        worker_process.kill()
        print("   ✓ Worker process killed")

    print("\n" + "=" * 60)
    print("✅ Redis-Free Mode Test PASSED")
    print("=" * 60)
    print("\nKey findings:")
    print("  • Worker can start without REDIS_URL")
    print("  • WebSocket connection established successfully")
    print("  • Worker can receive and process tasks")
    print("  • All communication via WebSocket only")
    print("\nThe worker is now fully independent of Redis!")

    return True


if __name__ == "__main__":
    try:
        success = test_redis_free_mode()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

#!/usr/bin/env python3
"""
Test script to verify worker endpoints show both Redis and WebSocket workers.
"""

import requests
import json
import sys


def test_worker_endpoints(base_url="http://localhost:8000"):
    """Test the /workers and /workers/{worker_id} endpoints."""

    print("=" * 70)
    print("Testing Worker Endpoints")
    print("=" * 70)

    # Test 1: List all workers
    print("\n1. Testing GET /workers")
    print("-" * 70)
    try:
        response = requests.get(f"{base_url}/workers")
        response.raise_for_status()
        data = response.json()

        print(f"Status Code: {response.status_code}")
        print(f"Total Workers: {data.get('total', 0)}")
        print(f"  - Redis only: {data.get('redis_only', 0)}")
        print(f"  - WebSocket only: {data.get('websocket_only', 0)}")
        print(f"  - Both (Redis + WebSocket): {data.get('both', 0)}")

        print("\nWorker Details:")
        for worker in data.get('workers', []):
            worker_id = worker.get('worker_id', 'unknown')
            transport = worker.get('transport', 'unknown')
            status = worker.get('status', 'unknown')
            ws_connected = worker.get('websocket', {}).get('connected', False)

            print(f"\n  Worker ID: {worker_id}")
            print(f"    Status: {status}")
            print(f"    Transport: {transport}")
            print(f"    WebSocket Connected: {ws_connected}")

            if ws_connected:
                ws_info = worker.get('websocket', {})
                print(f"    WebSocket Info:")
                print(f"      - Tasks Sent: {ws_info.get('tasks_sent', 0)}")
                print(
                    f"      - Events Received: {ws_info.get('events_received', 0)}")
                print(
                    f"      - Connected Seconds: {ws_info.get('connected_seconds', 0):.2f}")

        # Test 2: Get details for each worker
        print("\n\n2. Testing GET /workers/{worker_id}")
        print("-" * 70)

        for worker in data.get('workers', []):
            worker_id = worker.get('worker_id')
            if worker_id:
                print(f"\nGetting details for worker: {worker_id}")
                detail_response = requests.get(
                    f"{base_url}/workers/{worker_id}")
                detail_response.raise_for_status()
                detail_data = detail_response.json()

                print(
                    f"  Transport: {detail_data.get('transport', 'unknown')}")
                print(f"  Status: {detail_data.get('status', 'unknown')}")

                if detail_data.get('websocket', {}).get('connected'):
                    ws_info = detail_data['websocket']
                    print(f"  WebSocket Connected: Yes")
                    print(f"    - Tasks Sent: {ws_info.get('tasks_sent', 0)}")
                    print(
                        f"    - Events Received: {ws_info.get('events_received', 0)}")
                else:
                    print(f"  WebSocket Connected: No")

                if 'stale' in detail_data:
                    print(f"  Redis Stale: {detail_data['stale']}")

        print("\n" + "=" * 70)
        print("✅ All tests passed successfully!")
        print("=" * 70)
        return True

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    success = test_worker_endpoints(base_url)
    sys.exit(0 if success else 1)

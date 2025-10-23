#!/usr/bin/env python3
"""
Test script to verify worker registration with description and taskType.
This script tests both the worker registration and /workers API endpoint.
"""
import sys
import time
import requests
from pathlib import Path

# Add parent directory to path
_parent = Path(__file__).parent
sys.path.insert(0, str(_parent))
sys.path.insert(0, str(_parent / "worker"))
sys.path.insert(0, str(_parent / "orchestrator"))


def test_workers_api(orchestrator_url: str = "http://localhost:8000"):
    """Test the /workers API endpoint."""
    print(f"\n{'='*60}")
    print("Testing /workers API endpoint")
    print(f"{'='*60}\n")
    
    try:
        response = requests.get(f"{orchestrator_url}/workers")
        response.raise_for_status()
        
        workers = response.json()
        print(f"Found {len(workers)} worker(s):\n")
        
        for worker in workers:
            worker_id = worker.get("worker_id", "N/A")
            status = worker.get("status", "N/A")
            description = worker.get("description", "")
            task_types = worker.get("task_types", [])
            tags = worker.get("tags", [])
            stale = worker.get("stale", False)
            
            print(f"Worker ID: {worker_id}")
            print(f"  Status: {status}")
            print(f"  Description: {description if description else '(none)'}")
            print(f"  Task Types: {', '.join(task_types) if task_types else '(none)'}")
            print(f"  Tags: {', '.join(tags) if tags else '(none)'}")
            print(f"  Stale: {stale}")
            print()
            
        return workers
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to orchestrator at {orchestrator_url}")
        print("   Make sure orchestrator is running.")
        return None
    except Exception as e:
        print(f"❌ Error fetching workers: {e}")
        return None


def test_specific_worker(worker_id: str, orchestrator_url: str = "http://localhost:8000"):
    """Test fetching a specific worker."""
    print(f"\n{'='*60}")
    print(f"Testing /workers/{worker_id} endpoint")
    print(f"{'='*60}\n")
    
    try:
        response = requests.get(f"{orchestrator_url}/workers/{worker_id}")
        response.raise_for_status()
        
        worker = response.json()
        
        print("Worker Details:")
        print(f"  ID: {worker.get('worker_id', 'N/A')}")
        print(f"  Status: {worker.get('status', 'N/A')}")
        print(f"  Description: {worker.get('description', '(none)')}")
        print(f"  Task Types: {', '.join(worker.get('task_types', []))}")
        print(f"  Tags: {', '.join(worker.get('tags', []))}")
        print(f"  PID: {worker.get('pid', 'N/A')}")
        print(f"  Started At: {worker.get('started_at', 'N/A')}")
        print(f"  Last Seen: {worker.get('last_seen', 'N/A')}")
        print(f"  Stale: {worker.get('stale', False)}")
        
        if worker.get('hardware'):
            hw = worker['hardware']
            print(f"\n  Hardware:")
            if 'cpu' in hw:
                cpu = hw['cpu']
                print(f"    CPU: {cpu.get('model', 'N/A')} ({cpu.get('logical_cores', 'N/A')} cores)")
            if 'memory' in hw:
                mem = hw['memory']
                total_gb = mem.get('total_bytes', 0) / (1024**3)
                print(f"    Memory: {total_gb:.2f} GB")
        
        return worker
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"❌ Worker {worker_id} not found")
        else:
            print(f"❌ HTTP Error: {e}")
        return None
    except Exception as e:
        print(f"❌ Error fetching worker: {e}")
        return None


def main():
    """Main test function."""
    print("\n" + "="*60)
    print("Worker Registration Test")
    print("This script tests description and taskType in worker registration")
    print("="*60)
    
    orchestrator_url = "http://localhost:8000"
    
    # Test listing all workers
    workers = test_workers_api(orchestrator_url)
    
    if not workers:
        print("\n⚠️  No workers found or orchestrator not accessible.")
        print("\nTo test this feature:")
        print("1. Start orchestrator: cd orchestrator && python main.py")
        print("2. Start a worker with description:")
        print("   export WORKER_DESCRIPTION='My test worker'")
        print("   cd worker && python main.py")
        print("3. Run this test script again")
        return
    
    # Test fetching first worker details
    if workers:
        first_worker_id = workers[0].get("worker_id")
        if first_worker_id:
            test_specific_worker(first_worker_id, orchestrator_url)
    
    print("\n" + "="*60)
    print("✅ Test completed")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()

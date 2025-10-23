#!/usr/bin/env python3
"""Test script to verify automatic task_types detection from executors."""

import time
import requests
import json

# Test the simple API
def test_simple_api():
    print("Testing simple task submission API...")
    
    # Submit a hello-world task using the simple API
    response = requests.post(
        "http://localhost:8000/api/v1/tasks/simple",
        json={
            "taskType": "hello-world",
            "input": {
                "name": "SDK User"
            },
            "tags": []
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Task submitted successfully!")
        print(f"   Task ID: {result['tasks'][0]['task_id']}")
        print(f"   Status: {result['tasks'][0]['status']}")
        print(f"   Assigned Worker: {result['tasks'][0]['assigned_worker']}")
        
        task_id = result['tasks'][0]['task_id']
        
        # Wait for task completion
        print("\n⏳ Waiting for task to complete...")
        time.sleep(3)
        
        # Get result
        result_response = requests.get(
            f"http://localhost:8000/api/v1/results/{task_id}"
        )
        
        if result_response.status_code == 200:
            result_data = result_response.json()
            print(f"\n✅ Task completed successfully!")
            print(f"   Result: {json.dumps(result_data.get('result', {}), indent=2)}")
        else:
            print(f"\n❌ Failed to get result: {result_response.status_code}")
            print(f"   {result_response.text}")
    else:
        print(f"❌ Failed to submit task: {response.status_code}")
        print(f"   {response.text}")

# Check worker registration
def check_workers():
    print("\n" + "="*60)
    print("Checking registered workers...")
    print("="*60)
    
    response = requests.get("http://localhost:8000/workers")
    
    if response.status_code == 200:
        workers = response.json()
        print(f"\n✅ Found {len(workers)} worker(s):")
        
        for worker in workers:
            print(f"\n  Worker ID: {worker['worker_id']}")
            print(f"  Status: {worker['status']}")
            print(f"  Tags: {worker.get('tags', [])}")
            
            # Parse task_types from JSON string
            task_types_json = worker.get('task_types_json', '[]')
            try:
                task_types = json.loads(task_types_json)
                print(f"  Task Types: {task_types}")
            except:
                print(f"  Task Types: (parse error)")
                
            print(f"  Last Seen: {worker.get('last_seen', 'N/A')}")
    else:
        print(f"❌ Failed to get workers: {response.status_code}")
        print(f"   {response.text}")

if __name__ == "__main__":
    print("="*60)
    print("Task Type Auto-Detection Test")
    print("="*60)
    
    # First check workers
    check_workers()
    
    # Then test task submission
    print("\n" + "="*60)
    print("Testing Simple Task API")
    print("="*60 + "\n")
    test_simple_api()
    
    print("\n" + "="*60)
    print("Test Complete!")
    print("="*60)

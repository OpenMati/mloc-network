# Worker Description and Task Types Feature

## Overview

Workers can now register with a description and automatically report their supported task types. This information is displayed via the `/workers` API endpoint, making it easier to discover and understand worker capabilities.

## Features

### 1. Worker Description
Workers can provide a human-readable description of their purpose and capabilities.

### 2. Task Types
Workers automatically report which task types they support based on their registered executors.

## Configuration

### Environment Variables

#### `WORKER_DESCRIPTION`
Optional description for the worker.

**Example:**
```bash
export WORKER_DESCRIPTION="GPU worker for inference tasks"
```

### In Worker Code

#### Standard Worker (worker/main.py)
The description is read from the environment variable `WORKER_DESCRIPTION`:

```bash
export WORKER_DESCRIPTION="My custom worker"
export WORKER_TAGS="gpu,inference"
export WORKER_COST_PER_HOUR=5.0
cd worker && python main.py
```

Task types are automatically detected from initialized executors.

#### SDK-based Worker (mloc_sdk)
For SDK-based workers, you can pass the description to the WorkerSDK constructor:

```python
from mloc_sdk import WorkerSDK, BaseExecutor

class MyExecutor(BaseExecutor):
    taskType = "my-task"
    description = "My custom executor"
    
    def execute(self, task_spec, output_dir):
        return {"status": "success"}

if __name__ == "__main__":
    sdk = WorkerSDK(
        worker_id="my-worker",
        orchestrator_url="ws://localhost:8000/ws/worker",
        description="SDK worker for custom tasks",  # Worker description
        tags=["custom", "sdk"]
    )
    
    sdk.register_executor(MyExecutor())
    sdk.run()
```

Task types are automatically collected from registered executors.

## API Usage

### List All Workers

**Endpoint:** `GET /workers`

**Example:**
```bash
curl http://localhost:8000/workers
```

**Response:**
```json
[
  {
    "worker_id": "worker-123",
    "status": "IDLE",
    "description": "GPU worker for inference tasks",
    "task_types": ["default", "echo", "vllm"],
    "tags": ["gpu", "inference"],
    "started_at": "2025-10-23T10:30:00Z",
    "last_seen": "2025-10-23T10:35:00Z",
    "stale": false,
    "hardware": {
      "cpu": {
        "model": "Intel Core i9",
        "logical_cores": 16
      },
      "memory": {
        "total_bytes": 68719476736
      }
    }
  }
]
```

### Get Specific Worker

**Endpoint:** `GET /workers/{worker_id}`

**Example:**
```bash
curl http://localhost:8000/workers/worker-123
```

**Response:**
```json
{
  "worker_id": "worker-123",
  "status": "IDLE",
  "description": "GPU worker for inference tasks",
  "task_types": ["default", "echo", "vllm"],
  "tags": ["gpu", "inference"],
  "pid": 12345,
  "started_at": "2025-10-23T10:30:00Z",
  "last_seen": "2025-10-23T10:35:00Z",
  "stale": false,
  "env": {},
  "hardware": {
    "cpu": {
      "model": "Intel Core i9",
      "logical_cores": 16
    },
    "memory": {
      "total_bytes": 68719476736
    }
  }
}
```

## Testing

### Quick Test Script

Run the provided test script to verify the feature:

```bash
python test_worker_description.py
```

This script will:
1. Query the `/workers` endpoint
2. Display all registered workers with their descriptions and task types
3. Fetch detailed information for the first worker

### Manual Testing

1. **Start Orchestrator:**
   ```bash
   cd orchestrator
   python main.py
   ```

2. **Start Worker with Description:**
   ```bash
   export WORKER_DESCRIPTION="Test worker for development"
   export WORKER_TAGS="test,dev"
   export WORKER_COST_PER_HOUR=1.0
   cd worker
   python main.py
   ```

3. **Check Workers API:**
   ```bash
   # List all workers
   curl http://localhost:8000/workers | jq
   
   # Get specific worker (replace with actual worker_id)
   curl http://localhost:8000/workers/worker-abc123 | jq
   ```

### Using SDK Worker

1. **Create SDK Worker:**
   ```python
   # my_worker.py
   from mloc_sdk import WorkerSDK, BaseExecutor
   from pathlib import Path
   
   class EchoExecutor(BaseExecutor):
       taskType = "echo"
       description = "Echoes back input"
       
       def execute(self, task_spec, output_dir):
           input_text = task_spec.get("input", {}).get("text", "")
           return {"echo": input_text}
   
   if __name__ == "__main__":
       sdk = WorkerSDK(
           orchestrator_url="ws://localhost:8000/ws/worker",
           description="Echo service worker",
           tags=["echo", "test"]
       )
       sdk.register_executor(EchoExecutor())
       sdk.run()
   ```

2. **Run Worker:**
   ```bash
   python my_worker.py
   ```

3. **Verify:**
   ```bash
   curl http://localhost:8000/workers | jq
   ```

## Implementation Details

### Data Flow

1. **Worker Registration:**
   - Worker reads `WORKER_DESCRIPTION` from environment
   - Worker detects supported task types from initialized executors
   - Worker sends REGISTER event with description and task_types via transport (Redis or WebSocket)

2. **Orchestrator Storage:**
   - Orchestrator receives REGISTER event
   - Stores description and task_types in Redis worker hash
   - Fields: `description`, `task_types_json`

3. **API Response:**
   - `/workers` endpoint reads worker data from Redis
   - Deserializes task_types from JSON
   - Returns full worker info including description and task_types

### Files Modified

- `worker/config.py`: Added `description` field
- `worker/lifecycle.py`: Added `description` parameter to `start()`
- `worker/main.py`: Pass description and task_types to lifecycle
- `worker/worker_transport.py`: Added `description` to `register()` method
- `orchestrator/worker_cls.py`: Added `description` and `task_types` to Worker model
- `orchestrator/main.py`: Extract and store description in worker registration
- `mloc_sdk/worker.py`: Added `description` parameter to WorkerSDK

## Benefits

1. **Discoverability:** Easily identify worker capabilities through API
2. **Documentation:** Self-documenting workers with descriptions
3. **Task Routing:** Can route tasks based on worker's supported task types
4. **Monitoring:** Better visibility into worker fleet composition

## Future Enhancements

- Filter workers by task type in `/workers` endpoint
- Worker capability matching in scheduler
- Auto-generated worker documentation from descriptions
- Health dashboard showing worker types and capabilities

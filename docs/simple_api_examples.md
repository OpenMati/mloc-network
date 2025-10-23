# Simple Task API - cURL Examples

## Basic Usage

### 1. Submit a Simple Task

```bash
curl -X POST http://localhost:8000/api/v1/tasks/simple \
  -H "Content-Type: application/json" \
  -d '{
    "taskType": "hello-world",
    "input": {
      "name": "World"
    }
  }'
```

**Response:**
```json
{
  "ok": true,
  "count": 1,
  "tasks": [{
    "task_id": "abc123...",
    "status": "DISPATCHED",
    "assigned_worker": "hello-worker",
    "topic": "tasks",
    "waiting_on": [],
    "retries": 0,
    "max_retries": 3,
    "load": 1
  }],
  "generated_yaml": "apiVersion: v1\nkind: Task\n..."
}
```

---

### 2. Submit Task with Tags

```bash
curl -X POST http://localhost:8000/api/v1/tasks/simple \
  -H "Content-Type: application/json" \
  -d '{
    "taskType": "hello-world",
    "input": {
      "name": "Alice"
    },
    "tags": ["gpu", "production"]
  }'
```

Tags are used to match specific workers that have those tags.

---

### 3. Submit Task with SLO (Service Level Objective)

```bash
curl -X POST http://localhost:8000/api/v1/tasks/simple \
  -H "Content-Type: application/json" \
  -d '{
    "taskType": "hello-world",
    "input": {
      "name": "Bob"
    },
    "sloSeconds": 60
  }'
```

The task should complete within 60 seconds.

---

### 4. Submit Task with All Options

```bash
curl -X POST http://localhost:8000/api/v1/tasks/simple \
  -H "Content-Type: application/json" \
  -d '{
    "taskType": "hello-world",
    "input": {
      "name": "Charlie",
      "greeting": "Hi",
      "metadata": {
        "version": "1.0",
        "timestamp": "2025-01-23T10:00:00Z"
      }
    },
    "tags": ["high-priority", "gpu"],
    "sloSeconds": 30
  }'
```

---

### 5. With Authentication

If `ORCHESTRATOR_TOKEN` is set:

```bash
curl -X POST http://localhost:8000/api/v1/tasks/simple \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-token-here" \
  -d '{
    "taskType": "hello-world",
    "input": {
      "name": "Dave"
    }
  }'
```

---

## Check Task Status

### Get Task Details

```bash
curl http://localhost:8000/api/v1/tasks/{task_id}
```

**Example:**
```bash
curl http://localhost:8000/api/v1/tasks/abc123-def456-ghi789
```

---

## Retrieve Results

### Get Task Result

```bash
curl http://localhost:8000/api/v1/results/{task_id}
```

**Example:**
```bash
curl http://localhost:8000/api/v1/results/abc123-def456-ghi789
```

**Response:**
```json
{
  "task_id": "abc123-def456-ghi789",
  "worker_id": "hello-worker",
  "metadata": null,
  "received_at": "2025-01-23T10:15:30.123456+00:00",
  "result": {
    "message": "Hello, World!",
    "status": "success",
    "name_used": "World"
  }
}
```

---

## List Operations

### List All Tasks

```bash
curl http://localhost:8000/api/v1/tasks
```

### List All Workers

```bash
curl http://localhost:8000/workers
```

**Response shows worker capabilities:**
```json
[{
  "worker_id": "hello-worker",
  "status": "IDLE",
  "tags_json": "[\"cpu-only\", \"development\"]",
  "task_types_json": "[\"hello-world\"]",
  "last_seen": "2025-01-23T10:15:45.123456+00:00"
}]
```

---

## Advanced Examples

### Custom LLM Task (Example)

```bash
curl -X POST http://localhost:8000/api/v1/tasks/simple \
  -H "Content-Type: application/json" \
  -d '{
    "taskType": "llm",
    "input": {
      "model": "gpt-4",
      "prompt": "Explain quantum computing",
      "max_tokens": 500,
      "temperature": 0.7
    },
    "tags": ["gpu", "nvidia"],
    "sloSeconds": 120
  }'
```

### Data Processing Task (Example)

```bash
curl -X POST http://localhost:8000/api/v1/tasks/simple \
  -H "Content-Type: application/json" \
  -d '{
    "taskType": "data-processor",
    "input": {
      "dataset_url": "https://example.com/data.csv",
      "operations": ["normalize", "filter", "aggregate"]
    },
    "tags": ["high-memory"],
    "sloSeconds": 300
  }'
```

---

## Error Handling

### Invalid Request (Missing taskType)

```bash
curl -X POST http://localhost:8000/api/v1/tasks/simple \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "name": "Test"
    }
  }'
```

**Response:**
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "taskType"],
      "msg": "Field required"
    }
  ]
}
```

### Invalid Request (Missing input)

```bash
curl -X POST http://localhost:8000/api/v1/tasks/simple \
  -H "Content-Type: application/json" \
  -d '{
    "taskType": "hello-world"
  }'
```

**Response:**
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "input"],
      "msg": "Field required"
    }
  ]
}
```

---

## Complete Workflow Example

```bash
#!/bin/bash

# 1. Submit task
RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/tasks/simple \
  -H "Content-Type: application/json" \
  -d '{
    "taskType": "hello-world",
    "input": {"name": "World"}
  }')

# 2. Extract task ID
TASK_ID=$(echo $RESPONSE | jq -r '.tasks[0].task_id')
echo "Task ID: $TASK_ID"

# 3. Wait for completion
sleep 2

# 4. Get result
curl -s http://localhost:8000/api/v1/results/$TASK_ID | jq .

# 5. Check task status
curl -s http://localhost:8000/api/v1/tasks/$TASK_ID | jq .
```

---

## Using with Python

```python
import requests
import time

# Submit task
response = requests.post(
    "http://localhost:8000/api/v1/tasks/simple",
    json={
        "taskType": "hello-world",
        "input": {"name": "Python User"},
        "tags": ["python-client"],
        "sloSeconds": 60
    }
)

result = response.json()
task_id = result["tasks"][0]["task_id"]
print(f"Task submitted: {task_id}")

# Wait for completion
time.sleep(2)

# Get result
result_response = requests.get(
    f"http://localhost:8000/api/v1/results/{task_id}"
)

print("Result:", result_response.json())
```

---

## Monitoring

### Check System Health

```bash
curl http://localhost:8000/healthz
```

### Get Metrics

```bash
curl http://localhost:8000/metrics
```

### WebSocket Statistics

```bash
curl http://localhost:8000/ws/stats
```

---

## Notes

- **taskType**: Must match a taskType registered by a worker's executor
- **tags**: Used for worker matching (AND logic - worker must have ALL specified tags)
- **sloSeconds**: Optional deadline for task completion
- **input**: Custom data structure specific to your executor implementation
- Results are stored in `./results_host/{task_id}/responses.json`

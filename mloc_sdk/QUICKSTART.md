# MLOC SDK Quick Start Guide

This guide will help you create and deploy your first custom executor using the MLOC SDK in just 5 minutes.

## Prerequisites

- Python 3.8+
- Orchestrator running (WebSocket mode)
- MLOC project installed

## Step 1: Install Dependencies

```bash
# From the kv.run project root
cd /path/to/kv.run
pip install websockets
```

## Step 2: Create Your First Executor

Create a file `my_first_executor.py`:

```python
from pathlib import Path
from typing import Any, Dict
from mloc_sdk import BaseExecutor, WorkerSDK

class HelloWorldExecutor(BaseExecutor):
    """My first executor - says hello!"""
    
    name = "hello-world"
    description = "A simple hello world executor"
    version = "1.0.0"
    
    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        # Get the name from task spec
        name = task_spec.get("name", "World")
        message = f"Hello, {name}!"
        
        # Save to file
        self.save_text(output_dir / "hello.txt", message)
        
        # Return result
        return {
            "message": message,
            "status": "success"
        }

if __name__ == "__main__":
    # Create SDK
    sdk = WorkerSDK(
        worker_id="hello-worker",
        orchestrator_url="ws://localhost:8000/ws/worker",
        log_level="INFO"
    )
    
    # Register executor
    sdk.register_executor(HelloWorldExecutor())
    
    # Start worker
    print("Starting Hello World worker...")
    sdk.run()
```

## Step 3: Start the Orchestrator

```bash
# In terminal 1
python -m orchestrator.main
```

## Step 4: Run Your Worker

```bash
# In terminal 2
python my_first_executor.py
```

You should see:
```
Starting Hello World worker...
2025-10-20 12:00:00 - mloc_sdk - INFO - WorkerSDK initialized: worker_id=hello-worker, transport=WebSocket
2025-10-20 12:00:00 - mloc_sdk - INFO - Registered executor: hello-world (version: 1.0.0)
2025-10-20 12:00:00 - mloc_sdk - INFO - WebSocket transport initialized: ws://localhost:8000/ws/worker
2025-10-20 12:00:00 - mloc_sdk - INFO - Worker ready, waiting for tasks...
```

## Step 5: Create a Test Task

Create `test_hello.yaml`:

```yaml
apiVersion: mloc/v1
kind: Task
metadata:
  id: hello-test-1
spec:
  taskType: hello-world
  name: Alice
```

## Step 6: Submit the Task

Submit your task:

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/x-yaml" \
  --data-binary @test_hello.yaml
```

## Step 7: Check Results

```bash
# View results directory
ls -la results_workers/hello-test-1/

# Read the output
cat results_workers/hello-test-1/hello.txt
cat results_workers/hello-test-1/responses.json
```

You should see:
```json
{
  "message": "Hello, Alice!",
  "status": "success"
}
```

## Next Steps

### Try the Decorator Style

```python
from mloc_sdk import executor, WorkerSDK

@executor(name="my-calculator", description="Does math")
def calculate(task_spec, output_dir):
    a = task_spec.get("a", 0)
    b = task_spec.get("b", 0)
    return {"sum": a + b}

if __name__ == "__main__":
    sdk = WorkerSDK(orchestrator_url="ws://localhost:8000/ws/worker")
    sdk.register_executor(calculate)
    sdk.run()
```

### Explore Examples

```bash
cd examples/sdk
ls -la
# example_01_simple_executor.py
# example_02_decorator_executor.py
# example_03_lifecycle_hooks.py
# example_04_multi_executor.py
# example_05_ml_inference.py
```

### Add Lifecycle Hooks

```python
class AdvancedExecutor(BaseExecutor):
    name = "advanced"
    
    def prepare(self):
        """Load models, connect to databases, etc."""
        print("Loading resources...")
        self.model = load_my_model()
    
    def execute(self, task_spec, output_dir):
        """Process each task"""
        result = self.model.predict(task_spec["input"])
        return {"prediction": result}
    
    def cleanup(self):
        """Clean up after each task"""
        clear_cache()
    
    def teardown(self):
        """Release resources on shutdown"""
        print("Shutting down gracefully...")
        self.model = None
```

### Register Multiple Executors

```python
sdk = WorkerSDK(orchestrator_url="ws://localhost:8000/ws/worker")
sdk.register_executor(CalculatorExecutor())
sdk.register_executor(GreetingExecutor())
sdk.register_executor(DataProcessorExecutor(), as_default=True)
sdk.run()
```

## Common Issues

### "No module named 'mloc_sdk'"

Add the project root to PYTHONPATH:

```bash
export PYTHONPATH=/path/to/kv.run:$PYTHONPATH
python my_first_executor.py
```

### "Failed to connect to Orchestrator"

Check orchestrator is running:

```bash
curl http://localhost:8000/health
# Or start orchestrator
python -m orchestrator.main
```

Or specify a different orchestrator URL:

```bash
ORCHESTRATOR_URL=ws://your-orchestrator-host:8000/ws/worker python my_first_executor.py
```

### Worker Not Receiving Tasks

1. Check taskType matches executor name
2. Verify worker is running and connected
3. Check orchestrator logs
4. Ensure task was successfully submitted
5. Verify WebSocket connection is established

## Configuration Options

### Environment Variables

```bash
# WebSocket mode (required)
export ORCHESTRATOR_URL=ws://localhost:8000/ws/worker
export WORKER_ID=my-custom-worker
export WORKER_TAGS=ml,production
export LOG_LEVEL=DEBUG

# Run worker
python my_executor.py
```

### Programmatic Configuration

```python
sdk = WorkerSDK(
    worker_id="my-worker",
    orchestrator_url="ws://localhost:8000/ws/worker",
    results_dir=Path("./custom_results"),
    log_level="DEBUG",
    tags=["custom", "ml"],
)
```

## What's Next?

- 📖 Read the full [SDK README](./README.md)
- 🔍 Explore [examples](../../examples/sdk/)
- 🛠️ Check the [main documentation](../../docs/)
- 💡 Build your own custom executor!

## Support

Need help? Check:
- SDK README: `mloc_sdk/README.md`
- Main docs: `docs/`
- Examples: `examples/sdk/`
- Project README: `README.md`

Happy coding! 🚀

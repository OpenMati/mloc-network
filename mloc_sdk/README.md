# MLOC SDK - Python SDK for Custom Executors

A simplified Python SDK for building and deploying custom executor workers in the MLOC (Modular LLM Operations Container) system via WebSocket transport.

## Overview

The MLOC SDK provides a high-level interface for developers to create custom task executors without dealing with infrastructure concerns like WebSocket handling, lifecycle management, and result serialization.

## Features

- ✨ **Simple API**: Inherit from `BaseExecutor` or use decorators
- 🔄 **Lifecycle Management**: Automatic handling of prepare, execute, cleanup, and teardown
- 🚀 **WebSocket Transport**: Real-time communication with orchestrator (Redis-free)
- 📦 **Built-in Utilities**: JSON/text file helpers, logging, validation
- 🎯 **Type Safe**: Full type hints for better IDE support
- 🔌 **Pluggable**: Register multiple executors in a single worker

## Installation

```bash
# Install dependencies
pip install websockets

# From the kv.run project root (optional, for development)
pip install -e .
```

## Quick Start

### Example 1: Simple Executor (Class-Based)

```python
from pathlib import Path
from typing import Any, Dict
from mloc_sdk import BaseExecutor, WorkerSDK

class GreetingExecutor(BaseExecutor):
    name = "greeting"
    description = "Generates personalized greetings"
    version = "1.0.0"
    
    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        # Extract parameters
        name = task_spec.get("name", "World")
        language = task_spec.get("language", "en")
        
        # Generate greeting
        greetings = {
            "en": f"Hello, {name}!",
            "es": f"¡Hola, {name}!",
            "zh": f"你好, {name}!",
        }
        
        greeting = greetings.get(language, greetings["en"])
        
        # Save result
        result = {"greeting": greeting, "name": name, "language": language}
        self.save_json(output_dir / "greeting.json", result)
        
        return result

# Create and run worker
if __name__ == "__main__":
    sdk = WorkerSDK(orchestrator_url="ws://localhost:8000/ws/worker")
    sdk.register_executor(GreetingExecutor())
    sdk.run()
```

### Example 2: Decorator-Based Executor

```python
from mloc_sdk import executor, WorkerSDK

@executor(name="calculator", description="Performs arithmetic")
def calculate(task_spec, output_dir):
    a = task_spec.get("a", 0)
    b = task_spec.get("b", 0)
    operation = task_spec.get("operation", "add")
    
    result = {
        "a": a,
        "b": b,
        "operation": operation,
        "result": a + b if operation == "add" else a - b
    }
    
    return result

if __name__ == "__main__":
    sdk = WorkerSDK(orchestrator_url="ws://localhost:8000/ws/worker")
    sdk.register_executor(calculate)
    sdk.run()
```

### Example 3: Multiple Executors

```python
from mloc_sdk import BaseExecutor, WorkerSDK, executor

class ValidatorExecutor(BaseExecutor):
    name = "validator"
    
    def execute(self, task_spec, output_dir):
        # Validation logic
        return {"valid": True}

@executor(name="transformer")
def transform_data(task_spec, output_dir):
    # Transformation logic
    return {"transformed": True}

if __name__ == "__main__":
    sdk = WorkerSDK(orchestrator_url="ws://localhost:8000/ws/worker")
    sdk.register_executor(ValidatorExecutor())
    sdk.register_executor(transform_data, as_default=True)
    sdk.run()
```

## Core Concepts

### BaseExecutor

The base class for all executors. Provides:

- `execute(task_spec, output_dir)`: Main execution method (required)
- `prepare()`: One-time initialization (optional)
- `cleanup()`: Per-task cleanup (optional)
- `teardown()`: Shutdown hook (optional)
- Helper methods: `save_json()`, `load_json()`, `save_text()`, etc.

### WorkerSDK

Main class for managing the worker lifecycle:

- `register_executor(executor)`: Register custom executors
- `run()`: Start processing tasks
- `shutdown()`: Graceful shutdown

## Configuration

### Environment Variables

```bash
# WebSocket configuration (required)
ORCHESTRATOR_URL=ws://localhost:8000/ws/worker  # WebSocket URL

# Worker configuration
WORKER_ID=my-worker-1                       # Unique worker identifier
WORKER_TAGS=ml,production                   # Comma-separated tags
LOG_LEVEL=INFO                              # DEBUG, INFO, WARNING, ERROR
RESULTS_DIR=./results_workers               # Output directory

# Advanced
HEARTBEAT_INTERVAL_SEC=30                   # Heartbeat frequency
COST_PER_HOUR=0.0                          # Cost tracking
```

### Programmatic Configuration

```python
from pathlib import Path
from mloc_sdk import WorkerSDK

sdk = WorkerSDK(
    worker_id="my-worker-1",
    orchestrator_url="ws://localhost:8000/ws/worker",
    results_dir=Path("./results"),
    log_level="INFO",
    tags=["ml", "production"],
)
```

## Lifecycle Hooks

Executors can implement lifecycle hooks for resource management:

```python
class MLModelExecutor(BaseExecutor):
    name = "ml-model"
    
    def prepare(self):
        """Called once at startup - load models here"""
        self.model = load_large_model()
    
    def execute(self, task_spec, output_dir):
        """Called for each task"""
        result = self.model.predict(task_spec["input"])
        return {"prediction": result}
    
    def cleanup(self):
        """Called after each task - clear caches, temp files"""
        clear_cache()
    
    def teardown(self):
        """Called at shutdown - release resources"""
        self.model = None
```

## Task Specification

Tasks are received as dictionaries with this structure:

```python
{
    "task_id": "unique-task-id",
    "spec": {
        "taskType": "greeting",  # Matches executor name
        "name": "Alice",         # Custom parameters
        "language": "en"
    }
}
```

Your executor receives `task_spec` (the `spec` field) and should return a JSON-serializable dictionary.

## Output Directory

Each task gets an isolated output directory. Results are automatically saved:

```
results_workers/
└── task-123/
    ├── responses.json      # Your executor's return value
    ├── manifest.json       # Auto-generated file manifest
    └── ...                 # Custom output files
```

## Error Handling

Use `ExecutionError` for expected failures:

```python
from mloc_sdk.base import ExecutionError

class MyExecutor(BaseExecutor):
    def execute(self, task_spec, output_dir):
        if "required_field" not in task_spec:
            raise ExecutionError("Missing required_field")
        
        # Or use built-in validation
        self.validate_task_spec(task_spec, required_fields=["required_field"])
        
        return {"status": "success"}
```

## Examples

See the `examples/sdk/` directory for complete examples:

- `example_01_simple_executor.py` - Basic class-based executor
- `example_02_decorator_executor.py` - Function decorators
- `example_03_lifecycle_hooks.py` - Resource management
- `example_04_multi_executor.py` - Multiple executors
- `example_05_ml_inference.py` - Realistic ML inference example
- `example_06_websocket_mode.py` - WebSocket transport example

### Running Examples

```bash
# Start orchestrator
python -m orchestrator.main

# In another terminal, run an example
cd examples/sdk
python example_06_websocket_mode.py

# Or with custom configuration
ORCHESTRATOR_URL=ws://localhost:8000/ws/worker \
LOG_LEVEL=DEBUG \
WORKER_TAGS=example,demo \
python example_01_simple_executor.py
```

## Testing Your Executor

### 1. Start the Orchestrator

```bash
# In terminal 1
python -m orchestrator.main
```

### 2. Start Your Worker

```bash
# In terminal 2
cd examples/sdk
python example_01_simple_executor.py
```

### 3. Create a Test Task

```yaml
# test_greeting.yaml
apiVersion: mloc/v1
kind: Task
metadata:
  id: test-greeting-1
spec:
  taskType: greeting
  name: Alice
  language: en
```

### 4. Submit via Orchestrator API

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/x-yaml" \
  --data-binary @test_greeting.yaml
```

### 5. Check Results

```bash
# Results are in the output directory
ls results_workers/test-greeting-1/
cat results_workers/test-greeting-1/responses.json
```

## Advanced Features

### Custom Logger

```python
from mloc_sdk.utils import get_logger

class MyExecutor(BaseExecutor):
    def __init__(self):
        super().__init__()
        self.logger = get_logger("my-executor", level="DEBUG")
    
    def execute(self, task_spec, output_dir):
        self.logger.info("Processing task...")
        return {"status": "done"}
```

### Nested Value Access

```python
from mloc_sdk.utils import get_nested_value

task_spec = {"model": {"config": {"name": "llama"}}}
model_name = get_nested_value(task_spec, "model.config.name", default="default")
```

### GPU Requirements

```python
class GPUExecutor(BaseExecutor):
    name = "gpu-inference"
    requires_gpu = True  # SDK checks GPU availability
    
    def prepare(self):
        import torch
        assert torch.cuda.is_available()
        self.device = "cuda"
```

## Best Practices

1. **Use `prepare()` for expensive initialization** - Load models once, not per-task
2. **Validate inputs early** - Use `validate_task_spec()` at the start of `execute()`
3. **Save intermediate outputs** - Use output_dir for debugging and analysis
4. **Clean up resources** - Implement `cleanup()` and `teardown()`
5. **Use descriptive names** - Make executor names match their purpose
6. **Log appropriately** - INFO for progress, DEBUG for details, ERROR for failures
7. **Handle errors gracefully** - Use `ExecutionError` for expected failures

## Troubleshooting

### Worker Not Connecting

```bash
# Check orchestrator is running
curl http://localhost:8000/health

# Check WebSocket endpoint
curl http://localhost:8000/docs
```

### Tasks Not Being Received

- Verify `taskType` in task YAML matches executor `name`
- Check worker logs for registration messages
- Ensure orchestrator is running and accessible
- Check WebSocket connection in worker logs

### Import Errors

```bash
# Install missing dependencies
pip install websockets

# Or install from project root
pip install -e .
```

## API Reference

### BaseExecutor

```python
class BaseExecutor:
    name: str              # Executor identifier
    description: str       # Human-readable description
    version: str           # Version string
    requires_gpu: bool     # GPU requirement flag
    
    def prepare() -> None
    def execute(task_spec, output_dir) -> Dict
    def cleanup() -> None
    def teardown() -> None
    
    # Helpers
    @staticmethod
    def save_json(path, data)
    @staticmethod
    def load_json(path)
    @staticmethod
    def save_text(path, text)
    @staticmethod
    def load_text(path)
    def validate_task_spec(task_spec, required_fields)
```

### WorkerSDK

```python
class WorkerSDK:
    def __init__(
        worker_id=None,
        orchestrator_url=None,
        results_dir=None,
        log_level="INFO",
        tags=None,
    )
    
    def register_executor(executor, as_default=False) -> WorkerSDK
    def list_executors() -> List[str]
    def get_executor(name) -> BaseExecutor
    def run(blocking=True) -> None
    def shutdown() -> None
    
    @classmethod
    def from_env() -> WorkerSDK
```

## Contributing

Contributions welcome! Please ensure:

- New features include examples
- Code follows existing style
- Documentation is updated

## License

Same license as the parent kv.run project.

## Support

- 📖 Documentation: See `docs/` in the main project
- 💬 Issues: Open a GitHub issue
- 📧 Email: Contact the maintainers

---

Built with ❤️ for the MLOC project

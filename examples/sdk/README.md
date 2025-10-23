# Examples Index

This directory contains example implementations using the MLOC SDK.

## Examples

### 1. Simple Executor (`example_01_simple_executor.py`)
A basic class-based executor that demonstrates:
- Inheriting from `BaseExecutor`
- Implementing the `execute()` method
- Validating input with `validate_task_spec()`
- Saving results with helper methods

**Use case**: Personalized greetings in multiple languages

### 2. Decorator Executor (`example_02_decorator_executor.py`)
Shows decorator-based executors:
- Using `@executor` decorator for simple functions
- Registering multiple executors in one worker
- Word counting and arithmetic calculations

**Use case**: Quick function-based executors without writing full classes

### 3. Lifecycle Hooks (`example_03_lifecycle_hooks.py`)
Demonstrates lifecycle management:
- `prepare()`: One-time initialization (load models)
- `execute()`: Process each task
- `cleanup()`: Per-task cleanup
- `teardown()`: Graceful shutdown

**Use case**: Image processing with model loading/unloading

### 4. Multi-Executor Worker (`example_04_multi_executor.py`)
Shows advanced configuration:
- Registering multiple executors
- Environment variable configuration
- Redis vs WebSocket modes
- Custom tags and metadata

**Use case**: Data processing pipeline with multiple operations

### 5. ML Inference (`example_05_ml_inference.py`)
A realistic ML inference executor:
- Model management
- Batch processing
- Multiple model types (sentiment, NER, summarization)
- Performance tracking
- Error handling

**Use case**: Production ML inference service

## Running Examples

### Setup

```bash
# Install dependencies
pip install redis

# Start Redis (if using Redis mode)
docker-compose up -d redis

# Or start orchestrator (if using WebSocket mode)
python -m orchestrator.main
```

### Run an Example

```bash
cd examples/sdk

# Run with default configuration
python example_01_simple_executor.py

# Run with custom configuration
REDIS_URL=redis://localhost:6379/0 \
LOG_LEVEL=DEBUG \
WORKER_TAGS=example,test \
python example_01_simple_executor.py

# Run with WebSocket mode
USE_WEBSOCKET=true \
ORCHESTRATOR_URL=ws://localhost:8000/ws/worker \
python example_04_multi_executor.py
```

### Test an Example

1. Start the worker:
```bash
python example_01_simple_executor.py
```

2. Create a test task YAML:
```yaml
# test_greeting.yaml
apiVersion: mloc/v1
kind: Task
metadata:
  id: test-1
spec:
  taskType: greeting
  name: Alice
  language: en
```

3. Submit the task:
```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/x-yaml" \
  --data-binary @test_greeting.yaml
```

4. Check results:
```bash
cat results_workers/test-1/responses.json
```

## Customization

Each example can be customized by:

1. **Changing executor parameters**:
```python
sdk = WorkerSDK(
    worker_id="custom-worker",
    log_level="DEBUG",
    tags=["custom", "demo"],
)
```

2. **Modifying executor logic**:
```python
def execute(self, task_spec, output_dir):
    # Your custom logic here
    pass
```

3. **Adding new executors**:
```python
sdk.register_executor(MyCustomExecutor())
sdk.register_executor(AnotherExecutor())
```

## Best Practices

1. **Start simple**: Begin with `example_01` or `example_02`
2. **Add lifecycle hooks**: See `example_03` for resource management
3. **Scale up**: Use `example_04` for multiple executors
4. **Production ready**: Follow `example_05` for production patterns

## Next Steps

- Read the [SDK README](../../mloc_sdk/README.md)
- Check the [Quick Start Guide](../../mloc_sdk/QUICKSTART.md)
- Review the [main documentation](../../docs/)

## Support

Questions or issues? Open a GitHub issue or check the documentation.

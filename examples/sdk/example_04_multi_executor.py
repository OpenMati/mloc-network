"""
Example 4: Multiple Executors with Environment Configuration

This example shows:
- Registering multiple executors
- Using environment variables for configuration
- WebSocket vs Redis transport
- Custom tags and worker metadata
"""
import os
from pathlib import Path
from typing import Any, Dict

from mloc_sdk import BaseExecutor, WorkerSDK, executor


# Simple executor using decorator
@executor(
    name="data-transformer",
    description="Transforms data between formats",
    version="1.0.0"
)
def transform_data(task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    """Transform data from one format to another."""
    input_format = task_spec.get("input_format", "json")
    output_format = task_spec.get("output_format", "json")
    data = task_spec.get("data", {})

    # In a real implementation, perform actual transformation
    result = {
        "transformed": True,
        "input_format": input_format,
        "output_format": output_format,
        "data": data,
    }

    return result


# Class-based executor
class DataValidatorExecutor(BaseExecutor):
    """Validates data against schemas."""

    name = "data-validator"
    description = "Validates data against JSON schemas"
    version = "1.0.0"

    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        data = task_spec.get("data", {})
        schema = task_spec.get("schema", {})

        # Mock validation
        is_valid = True
        errors = []

        result = {
            "valid": is_valid,
            "errors": errors,
            "data_keys": list(data.keys()),
            "schema_required": schema.get("required", []),
        }

        self.save_json(output_dir / "validation.json", result)
        return result


class DataEnricherExecutor(BaseExecutor):
    """Enriches data with additional information."""

    name = "data-enricher"
    description = "Enriches data from external sources"
    version = "1.0.0"

    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        data = task_spec.get("data", {})
        sources = task_spec.get("enrichment_sources", ["default"])

        # Mock enrichment
        enriched_data = {
            **data,
            "enriched": True,
            "sources": sources,
            "timestamp": "2025-10-20T12:00:00Z",
        }

        result = {
            "original_data": data,
            "enriched_data": enriched_data,
            "sources_used": sources,
        }

        self.save_json(output_dir / "enriched.json", result)
        return result


def main():
    """
    Run a worker with multiple data processing executors.

    Environment Variables:
    - REDIS_URL: Redis connection (e.g., redis://localhost:6379/0)
    - ORCHESTRATOR_URL: WebSocket URL (e.g., ws://localhost:8000/ws/worker)
    - USE_WEBSOCKET: "true" to use WebSocket instead of Redis
    - WORKER_ID: Custom worker identifier
    - WORKER_TAGS: Comma-separated tags (e.g., "data,production")
    - LOG_LEVEL: DEBUG, INFO, WARNING, ERROR
    - RESULTS_DIR: Output directory path
    """

    # Option 1: Create from environment variables
    # sdk = WorkerSDK.from_env()

    # Option 2: Explicit configuration (overrides environment)
    sdk = WorkerSDK(
        worker_id=os.getenv("WORKER_ID", "data-worker-1"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        orchestrator_url=os.getenv(
            "ORCHESTRATOR_URL", "ws://localhost:8000/ws/worker"),
        use_websocket=os.getenv("USE_WEBSOCKET", "false").lower() == "true",
        results_dir=Path(os.getenv("RESULTS_DIR", "./results_workers")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        tags=["data-processing", "multi-executor", "example"],
    )

    # Register multiple executors
    sdk.register_executor(transform_data)
    sdk.register_executor(DataValidatorExecutor())
    sdk.register_executor(DataEnricherExecutor(), as_default=True)

    # Print configuration
    print("=" * 60)
    print("Worker Configuration")
    print("=" * 60)
    print(f"Worker ID: {sdk.worker_id}")
    print(f"Transport: {'WebSocket' if sdk.use_websocket else 'Redis'}")
    if sdk.use_websocket:
        print(f"Orchestrator URL: {sdk.orchestrator_url}")
    else:
        print(f"Redis URL: {sdk.redis_url}")
    print(f"Results Dir: {sdk.results_dir}")
    print(f"Log Level: {sdk.log_level}")
    print(f"Tags: {', '.join(sdk.tags)}")
    print(f"Registered Executors: {', '.join(sdk.list_executors())}")
    print("=" * 60)
    print()

    # Start worker
    print("Starting multi-executor worker...")
    print("Executors available:")
    for executor_name in sdk.list_executors():
        executor = sdk.get_executor(executor_name)
        print(f"  - {executor_name}: {executor.description}")
    print()

    sdk.run()


if __name__ == "__main__":
    main()

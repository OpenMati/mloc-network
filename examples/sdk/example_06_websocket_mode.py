"""
Example 6: WebSocket Mode (Redis-Free Worker)

This example demonstrates running a worker using WebSocket transport,
which eliminates the need for Redis on the worker side.

Use cases:
- Edge computing environments
- Simplified deployment
- Security isolation (worker doesn't need Redis access)

Note: The orchestrator still requires Redis for task management,
      but workers connect via WebSocket only.
"""
from pathlib import Path
from typing import Any, Dict
import os

from mloc_sdk import BaseExecutor, WorkerSDK


class EdgeComputeExecutor(BaseExecutor):
    """
    Example executor for edge computing scenarios.

    This executor runs on edge devices and communicates with the
    orchestrator via WebSocket, without requiring local Redis.
    """

    name = "edge-compute"
    description = "Edge computing executor for distributed processing"
    version = "1.0.0"
    requires_gpu = False

    def __init__(self):
        super().__init__()
        self.processed_count = 0

    def prepare(self) -> None:
        """Initialize edge compute resources."""
        print(f"[{self.name}] Initializing edge compute executor...")
        print(f"[{self.name}] Running in WebSocket mode (no Redis required)")
        # In real implementation: initialize edge-specific resources
        # - Local models
        # - Sensor interfaces
        # - Local storage

    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        """
        Process data on edge device.

        Expected task_spec:
        {
            "data_source": "sensor1",
            "processing_type": "filter|transform|analyze",
            "parameters": {...}
        }
        """
        self.processed_count += 1

        # Extract task parameters
        data_source = task_spec.get("data_source", "default")
        processing_type = task_spec.get("processing_type", "analyze")
        parameters = task_spec.get("parameters", {})

        print(f"[{self.name}] Processing data from {data_source}")
        print(f"[{self.name}] Type: {processing_type}")

        # Simulate edge processing
        result = {
            "data_source": data_source,
            "processing_type": processing_type,
            "processed": True,
            "task_number": self.processed_count,
            "edge_metadata": {
                "device_id": os.getenv("WORKER_ID", "edge-device-1"),
                "location": parameters.get("location", "unknown"),
            }
        }

        # Save results locally
        self.save_json(output_dir / "edge_result.json", result)

        print(f"[{self.name}] Task completed (total: {self.processed_count})")

        return result

    def teardown(self) -> None:
        """Cleanup edge resources."""
        print(f"[{self.name}] Shutting down...")
        print(f"[{self.name}] Total tasks processed: {self.processed_count}")


class DataCollectorExecutor(BaseExecutor):
    """Collects data from various sources in edge environment."""

    name = "data-collector"
    description = "Collects and preprocesses data from edge sources"
    version = "1.0.0"

    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        """Collect data from specified sources."""
        sources = task_spec.get("sources", [])
        interval = task_spec.get("interval_seconds", 1)

        collected_data = {
            "sources": sources,
            "interval": interval,
            "samples": len(sources) * 10,  # Mock data
            "timestamp": "2025-10-20T12:00:00Z"
        }

        self.save_json(output_dir / "collected_data.json", collected_data)

        return {
            "status": "collected",
            "samples": collected_data["samples"],
            "sources": len(sources)
        }


def main():
    """
    Run worker in WebSocket mode (no Redis required).

    Environment Variables:
    - ORCHESTRATOR_URL: WebSocket URL (required)
    - WORKER_ID: Worker identifier
    - WORKER_TAGS: Comma-separated tags
    - LOG_LEVEL: Logging level
    - RESULTS_DIR: Output directory

    Note: REDIS_URL is NOT required in WebSocket mode
    """

    # Get configuration from environment
    orchestrator_url = os.getenv(
        "ORCHESTRATOR_URL",
        "ws://localhost:8000/ws/worker"
    )

    worker_id = os.getenv("WORKER_ID", "edge-worker-1")
    log_level = os.getenv("LOG_LEVEL", "INFO")
    tags = os.getenv("WORKER_TAGS", "edge,websocket,redis-free").split(",")
    results_dir = Path(os.getenv("RESULTS_DIR", "./results_workers"))

    # Create SDK in WebSocket mode
    sdk = WorkerSDK(
        worker_id=worker_id,
        orchestrator_url=orchestrator_url,
        use_websocket=True,  # Enable WebSocket mode
        results_dir=results_dir,
        log_level=log_level,
        tags=tags,
    )

    # Register executors
    sdk.register_executor(EdgeComputeExecutor(), as_default=True)
    sdk.register_executor(DataCollectorExecutor())

    # Print configuration
    print("=" * 70)
    print("WebSocket Worker (Redis-Free Mode)")
    print("=" * 70)
    print(f"Worker ID:        {sdk.worker_id}")
    print(f"Transport:        WebSocket (Redis-free)")
    print(f"Orchestrator URL: {sdk.orchestrator_url}")
    print(f"Results Dir:      {sdk.results_dir}")
    print(f"Log Level:        {sdk.log_level}")
    print(f"Tags:             {', '.join(sdk.tags)}")
    print(f"Executors:        {', '.join(sdk.list_executors())}")
    print("=" * 70)
    print()
    print("Benefits of WebSocket Mode:")
    print("  ✓ No Redis required on worker side")
    print("  ✓ Simplified deployment")
    print("  ✓ Better for edge/remote workers")
    print("  ✓ Centralized task management")
    print("=" * 70)
    print()
    print("Starting worker...")

    # Start worker
    sdk.run()


if __name__ == "__main__":
    main()

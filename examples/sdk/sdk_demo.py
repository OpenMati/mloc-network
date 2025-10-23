#!/usr/bin/env python3
"""
Quick demo script showing how to use the MLOC SDK without Redis.

This script demonstrates:
1. Creating a simple executor
2. Configuring WebSocket transport
3. Running the worker

Usage:
    # Start orchestrator first
    python -m orchestrator.main
    
    # Then run this demo
    python sdk_demo.py
"""

from pathlib import Path
from typing import Any, Dict

from mloc_sdk import BaseExecutor, WorkerSDK, executor


# Method 1: Class-based executor
class GreetingExecutor(BaseExecutor):
    """A simple greeting executor."""

    name = "greeting"
    description = "Generates greetings in multiple languages"
    version = "1.0.0"

    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        # Validate inputs
        self.validate_task_spec(task_spec, required_fields=["name"])

        name = task_spec["name"]
        language = task_spec.get("language", "en")

        # Generate greeting
        greetings = {
            "en": f"Hello, {name}!",
            "es": f"¡Hola, {name}!",
            "fr": f"Bonjour, {name}!",
            "zh": f"你好, {name}!",
            "ja": f"こんにちは, {name}!",
        }

        greeting = greetings.get(language, greetings["en"])

        # Save result
        result = {
            "greeting": greeting,
            "name": name,
            "language": language,
            "available_languages": list(greetings.keys())
        }

        self.save_json(output_dir / "greeting.json", result)
        self.save_text(output_dir / "greeting.txt", greeting)

        return result


# Method 2: Decorator-based executor
@executor(
    name="calculator",
    description="Performs basic arithmetic operations",
    version="1.0.0"
)
def calculate(task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    """Simple calculator executor."""
    operation = task_spec.get("operation", "add")
    a = float(task_spec.get("a", 0))
    b = float(task_spec.get("b", 0))

    operations = {
        "add": a + b,
        "subtract": a - b,
        "multiply": a * b,
        "divide": a / b if b != 0 else None,
    }

    result_value = operations.get(operation)

    result = {
        "operation": operation,
        "a": a,
        "b": b,
        "result": result_value,
        "error": "Division by zero" if result_value is None and operation == "divide" else None,
    }

    # Save to file
    (output_dir / "calculation.json").write_text(
        str(result)
    )

    return result


def main():
    """Run the demo worker."""
    import os

    # Get orchestrator URL from environment or use default
    orchestrator_url = os.getenv(
        "ORCHESTRATOR_URL",
        "ws://localhost:8000/ws/worker"
    )

    print("=" * 60)
    print("MLOC SDK Demo - WebSocket Mode (No Redis)")
    print("=" * 60)
    print(f"Orchestrator URL: {orchestrator_url}")
    print()

    # Create SDK instance
    sdk = WorkerSDK(
        worker_id="demo-worker",
        orchestrator_url=orchestrator_url,
        log_level="INFO",
        tags=["demo", "sdk"],
    )

    # Register executors
    print("Registering executors...")
    sdk.register_executor(GreetingExecutor())
    sdk.register_executor(calculate, as_default=True)

    # Show registered executors
    print(f"\nRegistered executors: {', '.join(sdk.list_executors())}")
    print()

    # Print example tasks
    print("Example tasks to submit:")
    print()
    print("1. Greeting task:")
    print("---")
    print("apiVersion: mloc/v1")
    print("kind: Task")
    print("metadata:")
    print("  id: greeting-test")
    print("spec:")
    print("  taskType: greeting")
    print("  name: Alice")
    print("  language: zh")
    print()
    print("2. Calculator task:")
    print("---")
    print("apiVersion: mloc/v1")
    print("kind: Task")
    print("metadata:")
    print("  id: calc-test")
    print("spec:")
    print("  taskType: calculator")
    print("  operation: multiply")
    print("  a: 7")
    print("  b: 8")
    print()
    print("=" * 60)
    print("Starting worker... (Press Ctrl+C to stop)")
    print("=" * 60)
    print()

    # Start the worker
    try:
        sdk.run()
    except KeyboardInterrupt:
        print("\n\nShutting down gracefully...")
    except Exception as e:
        print(f"\n\nError: {e}")
        print("\nMake sure the orchestrator is running:")
        print("  python -m orchestrator.main")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())

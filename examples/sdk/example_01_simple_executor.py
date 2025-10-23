"""
Example 1: Simple Class-Based Executor

This example shows how to create a basic executor by inheriting from BaseExecutor.
"""
from pathlib import Path
from typing import Any, Dict

from mloc_sdk import BaseExecutor, WorkerSDK


class GreetingExecutor(BaseExecutor):
    """A simple executor that generates personalized greetings."""

    name = "greeting"
    description = "Generates personalized greetings"
    version = "1.0.0"

    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        """
        Execute a greeting task.

        Expected task_spec format:
        {
            "name": "Alice",
            "language": "en"  # optional
        }
        """
        # Validate required fields
        self.validate_task_spec(task_spec, required_fields=["name"])

        # Extract parameters
        name = task_spec["name"]
        language = task_spec.get("language", "en")

        # Generate greeting
        greetings = {
            "en": f"Hello, {name}!",
            "es": f"¡Hola, {name}!",
            "fr": f"Bonjour, {name}!",
            "zh": f"你好, {name}!",
        }

        greeting = greetings.get(language, greetings["en"])

        # Prepare result
        result = {
            "greeting": greeting,
            "name": name,
            "language": language,
        }

        # Save to output directory
        self.save_json(output_dir / "greeting.json", result)
        self.save_text(output_dir / "greeting.txt", greeting)

        return result


def main():
    """Run the greeting executor worker."""
    # Create SDK instance
    sdk = WorkerSDK(
        worker_id="greeting-worker-1",
        log_level="INFO",
        tags=["example", "greeting"],
    )

    # Register executor
    sdk.register_executor(GreetingExecutor())

    # Start worker
    print("Starting greeting executor worker...")
    print("Registered executors:", sdk.list_executors())
    sdk.run()


if __name__ == "__main__":
    main()

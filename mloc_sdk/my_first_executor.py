# Setup path before imports - DO NOT REORDER
import sys; from pathlib import Path; _r = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(_r)); sys.path.insert(0, str(_r / "worker")); sys.path.insert(0, str(_r / "orchestrator"))  # noqa: E702

from typing import Any, Dict
from mloc_sdk.base import BaseExecutor
from mloc_sdk.worker import WorkerSDK


class HelloWorldExecutor(BaseExecutor):
    """My first executor - says hello!"""

    taskType = "hello-world"
    description = "A simple hello world executor"
    version = "1.0.0"

    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        # Get the name from task spec's input field
        input_data = task_spec.get("input", {})
        name = input_data.get("name", "World")
        message = f"Hello, {name}!"

        # Save to file
        self.save_text(output_dir / "hello.txt", message)

        # Return result
        return {
            "message": message,
            "status": "success",
            "name_used": name
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

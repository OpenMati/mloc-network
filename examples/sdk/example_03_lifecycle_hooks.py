"""
Example 3: Advanced Executor with Lifecycle Hooks

This example demonstrates using prepare(), cleanup(), and teardown() lifecycle hooks.
"""
from pathlib import Path
from typing import Any, Dict
import time
import json

from mloc_sdk import BaseExecutor, WorkerSDK


class ImageProcessorExecutor(BaseExecutor):
    """
    Simulates an image processing executor with model loading.

    Demonstrates:
    - prepare(): Load model once at startup
    - execute(): Process each task
    - cleanup(): Clean up after each task
    - teardown(): Release resources on shutdown
    """

    name = "image-processor"
    description = "Processes images with a pretrained model"
    version = "1.0.0"
    requires_gpu = False

    def __init__(self):
        super().__init__()
        self.model = None
        self.task_count = 0
        self.total_processing_time = 0.0

    def prepare(self) -> None:
        """
        Load the model once when worker starts.
        This is called before the first task execution.
        """
        print(f"[{self.name}] Loading model...")
        time.sleep(1)  # Simulate model loading
        self.model = {"name": "imagenet-resnet50", "loaded": True}
        print(f"[{self.name}] Model loaded successfully")

    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        """
        Process an image.

        Expected task_spec:
        {
            "image_url": "https://example.com/image.jpg",
            "operations": ["resize", "enhance", "classify"]
        }
        """
        self.task_count += 1
        start_time = time.time()

        # Validate input
        self.validate_task_spec(task_spec, required_fields=["image_url"])

        image_url = task_spec["image_url"]
        operations = task_spec.get("operations", ["classify"])

        # Simulate processing
        print(f"[{self.name}] Processing image: {image_url}")
        time.sleep(0.5)  # Simulate processing time

        # Generate mock results
        results = {
            "image_url": image_url,
            "operations_performed": operations,
            "classifications": [
                {"label": "cat", "confidence": 0.95},
                {"label": "domestic_cat", "confidence": 0.87},
                {"label": "tabby", "confidence": 0.76},
            ],
            "processing_time": time.time() - start_time,
            "model": self.model["name"],
        }

        # Save results
        self.save_json(output_dir / "results.json", results)

        # Update stats
        self.total_processing_time += results["processing_time"]

        return results

    def cleanup(self) -> None:
        """
        Called after each task execution.
        Use for clearing temporary data, caches, etc.
        """
        # In a real implementation, you might clear GPU memory, temp files, etc.
        print(f"[{self.name}] Task {self.task_count} complete, cleaning up...")

    def teardown(self) -> None:
        """
        Called when worker is shutting down.
        Use for releasing resources, saving state, etc.
        """
        print(f"[{self.name}] Shutting down...")
        print(f"[{self.name}] Total tasks processed: {self.task_count}")
        print(
            f"[{self.name}] Total processing time: {self.total_processing_time:.2f}s")
        print(f"[{self.name}] Average time per task: {self.total_processing_time / max(self.task_count, 1):.2f}s")

        # Unload model
        self.model = None
        print(f"[{self.name}] Model unloaded")


class TextAnalyzerExecutor(BaseExecutor):
    """Analyzes text with sentiment analysis and entity extraction."""

    name = "text-analyzer"
    description = "Analyzes text for sentiment and entities"
    version = "1.0.0"

    def __init__(self):
        super().__init__()
        self.analyzer = None

    def prepare(self) -> None:
        """Load NLP models."""
        print(f"[{self.name}] Initializing NLP models...")
        time.sleep(0.5)
        self.analyzer = {"sentiment": True, "entities": True}
        print(f"[{self.name}] NLP models ready")

    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        """Analyze text."""
        text = task_spec.get("text", "")

        # Simulate analysis
        result = {
            "text_length": len(text),
            "word_count": len(text.split()),
            "sentiment": {
                "label": "positive",
                "score": 0.85
            },
            "entities": [
                {"text": "example", "type": "ORG", "start": 0, "end": 7}
            ],
        }

        self.save_json(output_dir / "analysis.json", result)
        return result

    def teardown(self) -> None:
        """Release analyzer resources."""
        print(f"[{self.name}] Releasing analyzer resources...")
        self.analyzer = None


def main():
    """Run the lifecycle-aware executors worker."""
    sdk = WorkerSDK(
        worker_id="lifecycle-worker-1",
        log_level="INFO",
        tags=["example", "lifecycle"],
    )

    # Register executors
    sdk.register_executor(ImageProcessorExecutor(), as_default=True)
    sdk.register_executor(TextAnalyzerExecutor())

    print("Starting lifecycle-aware executors worker...")
    print("Registered executors:", sdk.list_executors())
    print("\nNote: Press Ctrl+C to trigger graceful shutdown and see teardown hooks in action")

    sdk.run()


if __name__ == "__main__":
    main()

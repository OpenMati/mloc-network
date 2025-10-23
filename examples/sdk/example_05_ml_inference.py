"""
Example 5: Real-World ML Inference Executor

This example demonstrates a more realistic ML inference executor that:
- Loads a model during prepare()
- Handles batching
- Supports different model types
- Includes error handling
"""
from pathlib import Path
from typing import Any, Dict, List
import json
import time

from mloc_sdk import BaseExecutor, WorkerSDK
from mloc_sdk.base import ExecutionError


class MLInferenceExecutor(BaseExecutor):
    """
    Machine Learning inference executor.

    Supports multiple model types and batch inference.
    """

    name = "ml-inference"
    description = "Performs ML inference with various models"
    version = "2.0.0"
    requires_gpu = False  # Set to True if GPU required

    def __init__(self):
        super().__init__()
        self.models = {}
        self.inference_count = 0

    def prepare(self) -> None:
        """Load models and initialize inference engine."""
        self.logger.info("Initializing ML inference engine...")

        # Simulate loading multiple models
        # In real implementation, load actual models here
        self.models = {
            "sentiment": {
                "type": "text-classification",
                "loaded": True,
                "labels": ["positive", "negative", "neutral"]
            },
            "ner": {
                "type": "token-classification",
                "loaded": True,
                "labels": ["PER", "ORG", "LOC"]
            },
            "summarization": {
                "type": "text-generation",
                "loaded": True,
            }
        }

        self.logger.info(f"Loaded {len(self.models)} models")

    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        """
        Perform ML inference.

        Expected task_spec:
        {
            "model": "sentiment",  # or "ner", "summarization"
            "inputs": [
                "This is great!",
                "Not bad at all."
            ],
            "parameters": {
                "max_length": 512,
                "batch_size": 8
            }
        }
        """
        # Validate inputs
        self.validate_task_spec(task_spec, required_fields=["model", "inputs"])

        model_name = task_spec["model"]
        inputs = task_spec["inputs"]
        parameters = task_spec.get("parameters", {})

        # Check model availability
        if model_name not in self.models:
            raise ExecutionError(
                f"Model '{model_name}' not available. "
                f"Available models: {', '.join(self.models.keys())}"
            )

        model_info = self.models[model_name]
        batch_size = parameters.get("batch_size", 8)

        self.logger.info(
            f"Running inference with model '{model_name}' on {len(inputs)} inputs"
        )

        # Process inputs in batches
        results = []
        start_time = time.time()

        for i in range(0, len(inputs), batch_size):
            batch = inputs[i:i + batch_size]
            batch_results = self._process_batch(
                model_name, model_info, batch, parameters)
            results.extend(batch_results)

        inference_time = time.time() - start_time
        self.inference_count += len(inputs)

        # Prepare output
        output = {
            "model": model_name,
            "model_type": model_info["type"],
            "num_inputs": len(inputs),
            "results": results,
            "inference_time": inference_time,
            "avg_time_per_input": inference_time / len(inputs),
            "parameters": parameters,
        }

        # Save results
        self.save_json(output_dir / "predictions.json", output)

        # Save detailed results
        detailed_results = []
        for idx, (inp, result) in enumerate(zip(inputs, results)):
            detailed_results.append({
                "index": idx,
                "input": inp,
                "output": result,
            })
        self.save_json(output_dir / "detailed_results.json", detailed_results)

        self.logger.info(
            f"Inference complete: {len(inputs)} inputs in {inference_time:.2f}s"
        )

        return output

    def _process_batch(
        self,
        model_name: str,
        model_info: Dict[str, Any],
        batch: List[str],
        parameters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Process a batch of inputs with the specified model."""
        model_type = model_info["type"]

        # Simulate inference
        time.sleep(0.1)  # Simulate processing time

        results = []

        if model_type == "text-classification":
            # Sentiment analysis
            for text in batch:
                results.append({
                    "label": "positive",
                    "score": 0.95,
                })

        elif model_type == "token-classification":
            # Named Entity Recognition
            for text in batch:
                results.append({
                    "entities": [
                        {"text": "example", "label": "ORG", "start": 0, "end": 7}
                    ]
                })

        elif model_type == "text-generation":
            # Summarization
            max_length = parameters.get("max_length", 128)
            for text in batch:
                results.append({
                    "summary": f"Summary of: {text[:50]}...",
                    "length": max_length,
                })

        return results

    def cleanup(self) -> None:
        """Clean up after each inference run."""
        # In real implementation: clear GPU cache, temp files, etc.
        pass

    def teardown(self) -> None:
        """Release models and resources."""
        self.logger.info("Shutting down ML inference engine...")
        self.logger.info(f"Total inferences performed: {self.inference_count}")

        # Unload models
        self.models.clear()
        self.logger.info("Models unloaded")


def main():
    """Run the ML inference worker."""
    sdk = WorkerSDK(
        worker_id="ml-inference-worker",
        log_level="INFO",
        tags=["ml", "inference", "nlp"],
    )

    # Register executor
    executor = MLInferenceExecutor()
    sdk.register_executor(executor, as_default=True)

    print("=" * 60)
    print("ML Inference Worker")
    print("=" * 60)
    print(f"Executor: {executor.name} v{executor.version}")
    print(f"Description: {executor.description}")
    print(f"GPU Required: {executor.requires_gpu}")
    print("=" * 60)
    print("\nStarting worker...")
    print("Ready to process ML inference tasks")
    print()

    sdk.run()


if __name__ == "__main__":
    main()

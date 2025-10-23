"""
Example 2: Decorator-Based Executor

This example shows how to create executors using decorators for simpler code.
"""
from pathlib import Path
from typing import Any, Dict
import json

from mloc_sdk import executor, async_executor, WorkerSDK


@executor(
    name="word-counter",
    description="Counts words in text",
    version="1.0.0"
)
def count_words(task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    """Count words in provided text."""
    text = task_spec.get("text", "")

    # Count words
    words = text.split()
    word_count = len(words)

    # Count unique words
    unique_words = len(set(words))

    result = {
        "word_count": word_count,
        "unique_words": unique_words,
        "text_length": len(text),
    }

    # Save result
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "word_count.json").write_text(
        json.dumps(result, indent=2)
    )

    return result


@executor(
    name="calculator",
    description="Performs basic arithmetic operations",
    version="1.0.0"
)
def calculate(task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    """
    Perform arithmetic calculations.

    Expected task_spec:
    {
        "operation": "add|subtract|multiply|divide",
        "a": <number>,
        "b": <number>
    }
    """
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

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "calculation.json").write_text(
        json.dumps(result, indent=2)
    )

    return result


def main():
    """Run the decorator-based executors worker."""
    sdk = WorkerSDK(
        worker_id="decorator-worker-1",
        log_level="INFO",
        tags=["example", "decorator"],
    )

    # Register multiple executors
    sdk.register_executor(count_words)
    sdk.register_executor(calculate, as_default=True)

    print("Starting decorator-based executors worker...")
    print("Registered executors:", sdk.list_executors())
    sdk.run()


if __name__ == "__main__":
    main()

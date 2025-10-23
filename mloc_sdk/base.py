"""
Base executor interface for MLOC SDK.

This module provides the core BaseExecutor class that developers should inherit
from to create custom executors.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, List


@dataclass
class ExecutorConfig:
    """Configuration for an executor.

    Attributes:
        taskType: Unique identifier for the executor (matches task spec taskType)
        description: Human-readable description of what the executor does
        version: Version string for the executor
        requires_gpu: Whether this executor requires GPU support
        required_dependencies: List of Python packages required
        tags: Optional tags for filtering/discovery
    """
    taskType: str
    description: str = ""
    version: str = "1.0.0"
    requires_gpu: bool = False
    required_dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


class ExecutionError(RuntimeError):
    """Raised when an executor fails in an expected/controlled way."""
    pass


class BaseExecutor(ABC):
    """
    Base class for all MLOC executors.

    Developers should inherit from this class and implement the `execute` method.
    The SDK handles all infrastructure concerns (transport, lifecycle, etc.).

    Example:
        ```python
        from mloc_sdk import BaseExecutor
        from pathlib import Path

        class MyExecutor(BaseExecutor):
            taskType = "my-executor"
            description = "Does something useful"

            def execute(self, task_spec, output_dir):
                # Your custom logic
                input_data = task_spec.get("input", {})
                result = process_data(input_data)

                # Save results
                self.save_json(output_dir / "result.json", result)

                return {"status": "success", "data": result}
        ```
    """

    # Class attributes that can be overridden
    taskType: str = "base-executor"
    description: str = ""
    version: str = "1.0.0"
    requires_gpu: bool = False

    def __init__(self, config: Optional[ExecutorConfig] = None):
        """
        Initialize the executor.

        Args:
            config: Optional executor configuration. If not provided, uses class attributes.
        """
        if config:
            self.taskType = config.taskType
            self.description = config.description
            self.version = config.version
            self.requires_gpu = config.requires_gpu

        self._prepared = False

    def get_config(self) -> ExecutorConfig:
        """Get the executor configuration."""
        return ExecutorConfig(
            taskType=self.taskType,
            description=self.description,
            version=self.version,
            requires_gpu=self.requires_gpu,
        )

    def prepare(self) -> None:
        """
        Optional lifecycle hook called once before the first execution.

        Use this for:
        - Loading models
        - Initializing connections
        - Warming up caches
        - Any expensive one-time setup

        This method is called automatically by the SDK before the first task.
        """
        pass

    @abstractmethod
    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        """
        Execute a task and return results.

        This is the main method that must be implemented by all executors.

        Args:
            task_spec: The task specification from the orchestrator.
                      This is the 'spec' field from the task YAML.
            output_dir: Directory where outputs should be saved.
                       The SDK creates this directory before calling execute.

        Returns:
            A JSON-serializable dictionary with execution results.
            This will be saved as responses.json and sent to the orchestrator.

        Raises:
            ExecutionError: For expected failures (will be reported to orchestrator)
            Exception: For unexpected errors (will be logged and reported)

        Example:
            ```python
            def execute(self, task_spec, output_dir):
                model_name = task_spec.get("model", "default")
                inputs = task_spec.get("inputs", [])

                results = []
                for inp in inputs:
                    output = self.process(model_name, inp)
                    results.append(output)

                # Save detailed results to file
                self.save_json(output_dir / "results.json", results)

                # Return summary
                return {
                    "status": "success",
                    "count": len(results),
                    "model": model_name
                }
            ```
        """
        raise NotImplementedError

    def run(self, task: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        """
        Adapter method for worker compatibility.

        The worker expects a `run` method, but SDK uses `execute`.
        This method extracts the spec and calls execute().

        Args:
            task: Full task object with 'spec' field
            output_dir: Output directory path

        Returns:
            Execution results from execute()
        """
        task_spec = task.get("spec", {})
        return self.execute(task_spec, output_dir)

    def cleanup(self) -> None:
        """
        Optional lifecycle hook called after each task execution.

        Use this for:
        - Clearing temporary data
        - Releasing resources
        - Resetting state between tasks

        This is called even if execute() raises an exception.
        """
        pass

    def teardown(self) -> None:
        """
        Optional lifecycle hook called when the worker is shutting down.

        Use this for:
        - Closing connections
        - Saving state
        - Final cleanup
        """
        pass

    # Convenience helper methods

    @staticmethod
    def ensure_dir(path: Path) -> None:
        """Create directory if it doesn't exist."""
        path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def save_json(path: Path, data: Dict[str, Any], indent: int = 2) -> None:
        """
        Save data as JSON file.

        Args:
            path: File path to save to
            data: Dictionary to serialize
            indent: JSON indentation (default: 2)
        """
        BaseExecutor.ensure_dir(path.parent)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)

    @staticmethod
    def load_json(path: Path) -> Dict[str, Any]:
        """
        Load JSON file.

        Args:
            path: File path to load from

        Returns:
            Parsed dictionary
        """
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save_text(path: Path, text: str) -> None:
        """
        Save text to file.

        Args:
            path: File path to save to
            text: Text content to write
        """
        BaseExecutor.ensure_dir(path.parent)
        path.write_text(text, encoding="utf-8")

    @staticmethod
    def load_text(path: Path) -> str:
        """
        Load text from file.

        Args:
            path: File path to load from

        Returns:
            File contents as string
        """
        return path.read_text(encoding="utf-8")

    def validate_task_spec(self, task_spec: Dict[str, Any], required_fields: List[str]) -> None:
        """
        Validate that required fields are present in task spec.

        Args:
            task_spec: Task specification to validate
            required_fields: List of required field names

        Raises:
            ExecutionError: If any required field is missing
        """
        missing = [f for f in required_fields if f not in task_spec]
        if missing:
            raise ExecutionError(
                f"Missing required fields in task spec: {', '.join(missing)}"
            )

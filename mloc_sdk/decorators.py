"""
Decorators for simplified executor creation.

This module provides decorator-based APIs for creating executors without
needing to write full class definitions.
"""
from __future__ import annotations

import asyncio
import inspect
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from mloc_sdk.base import BaseExecutor, ExecutorConfig


def executor(
    taskType: str,
    description: str = "",
    version: str = "1.0.0",
    requires_gpu: bool = False,
):
    """
    Decorator to create an executor from a simple function.

    The decorated function should accept (task_spec, output_dir) and return
    a dictionary result.

    Args:
        taskType: Executor task type identifier
        description: Human-readable description
        version: Version string
        requires_gpu: Whether GPU is required

    Returns:
        Decorator function

    Example:
        ```python
        from mloc_sdk import executor, WorkerSDK

        @executor(taskType="math-calculator", description="Does math")
        def calculate(task_spec, output_dir):
            a = task_spec.get("a", 0)
            b = task_spec.get("b", 0)
            result = a + b
            return {"sum": result}

        if __name__ == "__main__":
            sdk = WorkerSDK()
            sdk.register_executor(calculate)
            sdk.run()
        ```
    """
    def decorator(func: Callable) -> BaseExecutor:
        # Check if function is async
        if asyncio.iscoroutinefunction(func):
            raise TypeError(
                f"Function {func.__name__} is async. Use @async_executor instead."
            )

        # Create executor class dynamically
        class DecoratedExecutor(BaseExecutor):
            pass

        DecoratedExecutor.taskType = taskType
        DecoratedExecutor.description = description or func.__doc__ or ""
        DecoratedExecutor.version = version
        DecoratedExecutor.requires_gpu = requires_gpu

        # Override execute method
        def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
            return func(task_spec, output_dir)

        DecoratedExecutor.execute = execute

        # Return an instance
        return DecoratedExecutor()

    return decorator


def async_executor(
    taskType: str,
    description: str = "",
    version: str = "1.0.0",
    requires_gpu: bool = False,
):
    """
    Decorator to create an executor from an async function.

    The decorated function should be async and accept (task_spec, output_dir)
    and return a dictionary result.

    Args:
        taskType: Executor task type identifier
        description: Human-readable description
        version: Version string
        requires_gpu: Whether GPU is required

    Returns:
        Decorator function

    Example:
        ```python
        from mloc_sdk import async_executor, WorkerSDK
        import asyncio

        @async_executor(taskType="async-processor")
        async def process_async(task_spec, output_dir):
            await asyncio.sleep(1)  # Simulate async work
            return {"status": "completed"}

        if __name__ == "__main__":
            sdk = WorkerSDK()
            sdk.register_executor(process_async)
            sdk.run()
        ```
    """
    def decorator(func: Callable) -> BaseExecutor:
        # Check if function is actually async
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(
                f"Function {func.__name__} is not async. Use @executor for sync functions."
            )

        # Create executor class dynamically
        class AsyncDecoratedExecutor(BaseExecutor):
            pass

        AsyncDecoratedExecutor.taskType = taskType
        AsyncDecoratedExecutor.description = description or func.__doc__ or ""
        AsyncDecoratedExecutor.version = version
        AsyncDecoratedExecutor.requires_gpu = requires_gpu

        # Override execute method to handle async
        def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
            # Run async function in event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            return loop.run_until_complete(func(task_spec, output_dir))

        AsyncDecoratedExecutor.execute = execute

        # Return an instance
        return AsyncDecoratedExecutor()

    return decorator


def stateful_executor(
    taskType: str,
    description: str = "",
    version: str = "1.0.0",
    requires_gpu: bool = False,
):
    """
    Decorator to create a stateful executor from a class.

    The decorated class should have an `execute` method. The class instance
    will be preserved between executions, allowing state to be maintained.

    Args:
        taskType: Executor task type identifier
        description: Human-readable description
        version: Version string
        requires_gpu: Whether GPU is required

    Returns:
        Decorator function

    Example:
        ```python
        from mloc_sdk import stateful_executor, WorkerSDK

        @stateful_executor(taskType="counter", description="Counts executions")
        class Counter:
            def __init__(self):
                self.count = 0

            def execute(self, task_spec, output_dir):
                self.count += 1
                return {"execution_count": self.count}

        if __name__ == "__main__":
            sdk = WorkerSDK()
            sdk.register_executor(Counter())
            sdk.run()
        ```
    """
    def decorator(cls: type) -> BaseExecutor:
        # Check if class has execute method
        if not hasattr(cls, 'execute'):
            raise TypeError(
                f"Class {cls.__name__} must have an 'execute' method"
            )

        # Create executor wrapper
        class StatefulExecutor(BaseExecutor):
            pass

        StatefulExecutor.taskType = taskType
        StatefulExecutor.description = description or cls.__doc__ or ""
        StatefulExecutor.version = version
        StatefulExecutor.requires_gpu = requires_gpu

        # Create instance of wrapped class
        instance = cls()

        # Override execute to call instance method
        def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
            return instance.execute(task_spec, output_dir)

        StatefulExecutor.execute = execute

        # Copy lifecycle methods if they exist
        for method_name in ['prepare', 'cleanup', 'teardown']:
            if hasattr(instance, method_name):
                method = getattr(instance, method_name)
                setattr(StatefulExecutor, method_name,
                        lambda self, m=method: m())

        # Return executor instance
        return StatefulExecutor()

    return decorator

"""
MLOC SDK - Simplified Python SDK for building custom executors and workers.

This SDK provides a high-level interface for developers to create custom
executor workers without dealing with the underlying infrastructure details
like Redis connections, WebSocket handling, lifecycle management, etc.

Key Features:
- Simple executor interface: inherit from BaseExecutor or use @executor decorator
- Automatic worker lifecycle management
- Support for both Redis and WebSocket transports
- Built-in error handling and logging
- Easy deployment and configuration

Example:
    ```python
    from mloc_sdk import BaseExecutor, WorkerSDK
    
    class MyExecutor(BaseExecutor):
        name = "my-custom-executor"
        
        def execute(self, task_spec, output_dir):
            # Your custom logic here
            return {"status": "success", "result": "Hello World"}
    
    if __name__ == "__main__":
        sdk = WorkerSDK()
        sdk.register_executor(MyExecutor())
        sdk.run()
    ```
"""

from .base import BaseExecutor, ExecutorConfig
from .worker import WorkerSDK
from .decorators import executor, async_executor
from .utils import get_logger, validate_task_spec

__version__ = "0.1.0"

__all__ = [
    "BaseExecutor",
    "ExecutorConfig",
    "WorkerSDK",
    "executor",
    "async_executor",
    "get_logger",
    "validate_task_spec",
]

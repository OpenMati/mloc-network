"""
Worker SDK - Main class for running custom executor workers.

This module provides the WorkerSDK class that handles all infrastructure
concerns for running custom executors via WebSocket transport.
"""
from __future__ import annotations
from mloc_sdk.utils import get_logger
from mloc_sdk.base import BaseExecutor, ExecutorConfig

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path to import worker modules
_parent = Path(__file__).parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))


class WorkerSDK:
    """
    Main SDK class for running custom executor workers.

    This class handles:
    - Executor registration and management
    - Worker lifecycle (heartbeat, shutdown)
    - WebSocket transport layer
    - Task execution and result handling
    - Configuration from environment variables

    Example:
        ```python
        from mloc_sdk import WorkerSDK, BaseExecutor

        class MyExecutor(BaseExecutor):
            name = "my-executor"
            def execute(self, task_spec, output_dir):
                return {"status": "success"}

        if __name__ == "__main__":
            sdk = WorkerSDK(orchestrator_url="ws://localhost:8000/ws/worker")
            sdk.register_executor(MyExecutor())
            sdk.run()
        ```
    """

    def __init__(
        self,
        worker_id: Optional[str] = None,
        orchestrator_url: Optional[str] = None,
        results_dir: Optional[Path] = None,
        log_level: str = "INFO",
        tags: Optional[List[str]] = None,
    ):
        """
        Initialize the Worker SDK.

        Args:
            worker_id: Unique worker identifier (auto-generated if not provided)
            orchestrator_url: Orchestrator WebSocket URL (required)
            results_dir: Directory for task outputs (default: ./results_workers)
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            tags: Optional tags for worker filtering/discovery
        """
        # Configuration
        self.worker_id = worker_id or os.getenv(
            "WORKER_ID") or os.urandom(8).hex()
        self.orchestrator_url = orchestrator_url or os.getenv(
            "ORCHESTRATOR_URL")
        self.results_dir = results_dir or Path(
            os.getenv("RESULTS_DIR", "./results_workers"))
        self.log_level = log_level or os.getenv("LOG_LEVEL", "INFO")
        self.tags = tags or [t.strip() for t in os.getenv(
            "WORKER_TAGS", "").split(",") if t.strip()]

        # Ensure results directory exists
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Setup logging
        self.logger = get_logger("mloc_sdk", level=self.log_level)

        # Executor registry
        self._executors: Dict[str, BaseExecutor] = {}
        self._default_executor: Optional[BaseExecutor] = None

        # Worker infrastructure (initialized in run())
        self._lifecycle = None
        self._runner = None
        self._transport = None
        self._ws_client = None

        self.logger.info(
            "WorkerSDK initialized: worker_id=%s, transport=WebSocket",
            self.worker_id
        )

    def register_executor(
        self,
        executor: BaseExecutor,
        as_default: bool = False
    ) -> "WorkerSDK":
        """
        Register a custom executor.

        Args:
            executor: Instance of BaseExecutor subclass
            as_default: Whether to use this as the default executor for tasks
                       without a specific taskType (default: False)

        Returns:
            Self for method chaining

        Example:
            ```python
            sdk = WorkerSDK()
            sdk.register_executor(MyExecutor())
            sdk.register_executor(AnotherExecutor(), as_default=True)
            ```
        """
        if not isinstance(executor, BaseExecutor):
            raise TypeError(
                f"Executor must be instance of BaseExecutor, got {type(executor)}")

        if executor.name in self._executors:
            self.logger.warning(
                "Overwriting existing executor: %s", executor.name
            )

        self._executors[executor.name] = executor
        self.logger.info(
            "Registered executor: %s (version: %s)",
            executor.name,
            executor.version
        )

        if as_default or not self._default_executor:
            self._default_executor = executor
            self.logger.info("Set default executor: %s", executor.name)

        return self

    def list_executors(self) -> List[str]:
        """
        Get list of registered executor names.

        Returns:
            List of executor names
        """
        return list(self._executors.keys())

    def get_executor(self, name: str) -> Optional[BaseExecutor]:
        """
        Get a registered executor by name.

        Args:
            name: Executor name

        Returns:
            Executor instance or None if not found
        """
        return self._executors.get(name)

    def run(self, blocking: bool = True) -> None:
        """
        Start the worker and begin processing tasks.

        This method:
        1. Validates configuration
        2. Initializes WebSocket transport layer
        3. Starts worker lifecycle (heartbeat)
        4. Begins processing tasks from orchestrator

        Args:
            blocking: Whether to block until interrupted (default: True)
                     If False, returns immediately (useful for testing)

        Raises:
            SystemExit: If configuration is invalid or startup fails

        Example:
            ```python
            sdk = WorkerSDK(orchestrator_url="ws://localhost:8000/ws/worker")
            sdk.register_executor(MyExecutor())
            sdk.run()  # Blocks until Ctrl+C
            ```
        """
        if not self._executors:
            self.logger.error(
                "No executors registered! Call register_executor() first.")
            raise SystemExit(1)

        if not self._default_executor:
            # Use first registered executor as default
            self._default_executor = next(iter(self._executors.values()))
            self.logger.info("Using %s as default executor",
                             self._default_executor.name)

        self.logger.info("Starting worker with %d executor(s): %s",
                         len(self._executors), ", ".join(self._executors.keys()))

        # Initialize infrastructure
        self._init_transport()
        # Note: lifecycle.start() will be called after WebSocket connects
        self._init_lifecycle_deferred()
        self._init_runner()

        # Start processing
        try:
            self.logger.info("Worker ready, waiting for tasks...")
            if blocking:
                self._runner.start()
        except KeyboardInterrupt:
            self.logger.info("KeyboardInterrupt received, shutting down...")
        finally:
            self.shutdown()

    def _init_lifecycle_deferred(self) -> None:
        """Initialize lifecycle but defer start() until WebSocket connects."""
        from worker.lifecycle import Lifecycle
        from worker.power import PowerMonitor
        from worker.hw import collect_hw

        hb_interval = int(os.getenv("HEARTBEAT_INTERVAL_SEC", "30"))
        hb_ttl = max(hb_interval * 4, 120)
        cost_per_hour = float(os.getenv("COST_PER_HOUR", "0.0"))

        self._lifecycle = Lifecycle(
            self._transport,
            hb_interval,
            hb_ttl,
            cost_per_hour=cost_per_hour,
            power_monitor=PowerMonitor(),
            websocket_client=self._ws_client,
        )

        # Set up callback to start lifecycle after WebSocket connects
        if self._ws_client:
            hw_info = collect_hw()
            original_on_connect = getattr(
                self._ws_client, '_on_connect_callback', None)

            def on_connect_with_lifecycle():
                # Start lifecycle (sends REGISTER event)
                self._lifecycle.start(env={}, hardware=hw_info, tags=self.tags)
                self.logger.info("Worker lifecycle started")
                # Call original callback if exists
                if original_on_connect and callable(original_on_connect):
                    original_on_connect()

            self._ws_client._on_connect_callback = on_connect_with_lifecycle

    def shutdown(self) -> None:
        """
        Gracefully shutdown the worker.

        This method:
        - Stops accepting new tasks
        - Completes current task (if any)
        - Calls teardown() on all executors
        - Closes transport connections
        """
        self.logger.info("Shutting down worker...")

        # Teardown executors
        for name, executor in self._executors.items():
            try:
                executor.teardown()
                self.logger.info("Executor %s teardown complete", name)
            except Exception as e:
                self.logger.warning("Error during %s teardown: %s", name, e)

        # Shutdown lifecycle
        if self._lifecycle:
            try:
                self._lifecycle.shutdown()
            except Exception as e:
                self.logger.warning("Error during lifecycle shutdown: %s", e)

        self.logger.info("Worker shutdown complete")

    def _init_transport(self) -> None:
        """Initialize WebSocket transport layer."""
        from worker.worker_transport import WebSocketTransport

        if not self.orchestrator_url:
            self.logger.error("ORCHESTRATOR_URL is required")
            raise SystemExit(1)

        try:
            from worker.websocket_client import WebSocketClient
            self._ws_client = WebSocketClient(
                orchestrator_url=self.orchestrator_url,
                worker_id=self.worker_id,
                logger=self.logger,
            )
            self._transport = WebSocketTransport(
                self.worker_id, self._ws_client)
            self.logger.info(
                "WebSocket transport initialized: %s", self.orchestrator_url)
        except ImportError as e:
            self.logger.error(
                "websockets package required: %s. Install with: pip install websockets", e)
            raise SystemExit(1)

    def _init_lifecycle(self) -> None:
        """Initialize worker lifecycle management."""
        from worker.lifecycle import Lifecycle
        from worker.power import PowerMonitor
        from worker.hw import collect_hw

        hb_interval = int(os.getenv("HEARTBEAT_INTERVAL_SEC", "30"))
        hb_ttl = max(hb_interval * 4, 120)
        cost_per_hour = float(os.getenv("COST_PER_HOUR", "0.0"))

        self._lifecycle = Lifecycle(
            self._transport,
            hb_interval,
            hb_ttl,
            cost_per_hour=cost_per_hour,
            power_monitor=PowerMonitor(),
            websocket_client=self._ws_client,
        )

        # Start lifecycle (heartbeat, etc.)
        hw_info = collect_hw()
        self._lifecycle.start(env={}, hardware=hw_info, tags=self.tags)
        self.logger.info("Worker lifecycle started")

    def _init_runner(self) -> None:
        """Initialize task runner with custom executors."""
        from worker.runner import Runner

        # Convert SDK executors to worker executors
        executor_dict = dict(self._executors)

        self._runner = Runner(
            self._lifecycle,
            None,  # No Redis in WebSocket mode
            "",  # No topic needed in WebSocket mode
            self.results_dir,
            executor_dict,
            self._default_executor,
            self.logger,
            use_websocket=True,
        )

        self.logger.info("Task runner initialized")

    @classmethod
    def from_env(cls) -> "WorkerSDK":
        """
        Create WorkerSDK instance from environment variables.

        Environment variables:
        - WORKER_ID: Worker identifier
        - ORCHESTRATOR_URL: Orchestrator WebSocket URL (required)
        - RESULTS_DIR: Output directory path
        - LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR)
        - WORKER_TAGS: Comma-separated tags

        Returns:
            Configured WorkerSDK instance

        Example:
            ```python
            # Set environment variables
            os.environ["ORCHESTRATOR_URL"] = "ws://localhost:8000/ws/worker"
            os.environ["LOG_LEVEL"] = "DEBUG"

            # Create SDK from env
            sdk = WorkerSDK.from_env()
            sdk.register_executor(MyExecutor())
            sdk.run()
            ```
        """
        return cls()

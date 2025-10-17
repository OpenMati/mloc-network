"""WebSocket client for worker-orchestrator communication.

Provides an alternative to Redis Pub/Sub for task reception and event sending.
When enabled, the worker uses a persistent WebSocket connection to receive tasks
and send heartbeats/events instead of Redis channels.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional, Callable
from urllib.parse import urlparse, urlunparse

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
    WEBSOCKETS_AVAILABLE = True
    WebSocketType = WebSocketClientProtocol
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    WebSocketClientProtocol = None
    WebSocketType = Any  # type: ignore


class WebSocketClient:
    """WebSocket client for worker to connect to orchestrator.

    Maintains a persistent connection for receiving tasks and sending events.
    Handles reconnection with exponential backoff on connection failures.
    """

    def __init__(
        self,
        orchestrator_url: str,
        worker_id: str,
        logger: logging.Logger,
        *,
        reconnect_interval: float = 5.0,
        max_reconnect_interval: float = 60.0,
    ):
        """Initialize WebSocket client.

        Args:
            orchestrator_url: Base URL of orchestrator (e.g., http://localhost:8000)
            worker_id: Unique worker identifier
            logger: Logger instance
            reconnect_interval: Initial reconnect delay in seconds
            max_reconnect_interval: Maximum reconnect delay in seconds
        """
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError(
                "websockets package is required for WebSocket transport. "
                "Install it with: pip install websockets"
            )

        self._orchestrator_url = orchestrator_url
        self._worker_id = worker_id
        self._logger = logger
        self._reconnect_interval = reconnect_interval
        self._max_reconnect_interval = max_reconnect_interval

        self._ws: Optional[Any] = None
        self._connected = False
        self._should_stop = False
        self._task_callback: Optional[Callable] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._current_reconnect_delay = reconnect_interval

    def _get_ws_url(self) -> str:
        """Convert HTTP orchestrator URL to WebSocket URL."""
        parsed = urlparse(self._orchestrator_url)

        # Convert http/https to ws/wss
        if parsed.scheme in ("http", "https"):
            ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        else:
            ws_scheme = parsed.scheme

        # Build WebSocket URL
        ws_path = f"/ws/worker/{self._worker_id}"
        ws_url = urlunparse((
            ws_scheme,
            parsed.netloc,
            ws_path,
            "",  # params
            "",  # query
            "",  # fragment
        ))

        return ws_url

    async def connect(self) -> bool:
        """Establish WebSocket connection to orchestrator.

        Returns:
            True if connected successfully, False otherwise
        """
        if self._connected and self._ws:
            return True

        ws_url = self._get_ws_url()

        try:
            self._logger.info(
                "Connecting to orchestrator via WebSocket: %s", ws_url)
            # Add additional headers and connection parameters for compatibility
            # Disable proxy to avoid python-socks requirement for local connections
            additional_headers = {
                "User-Agent": "mloc-worker/0.1.0",
            }
            self._ws = await websockets.connect(
                ws_url,
                additional_headers=additional_headers,
                proxy=None,  # Disable proxy for local connections
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10,
            )
            self._connected = True
            self._current_reconnect_delay = self._reconnect_interval
            self._logger.info("WebSocket connected successfully")
            return True
        except Exception as exc:
            self._logger.warning("Failed to connect WebSocket: %s", exc)
            self._logger.debug("Full exception:", exc_info=True)
            self._connected = False
            self._ws = None
            return False

    async def disconnect(self):
        """Close the WebSocket connection gracefully."""
        self._should_stop = True

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            finally:
                self._ws = None
                self._connected = False

    async def send_event(self, event: Dict[str, Any]) -> bool:
        """Send an event (heartbeat, status update) to orchestrator.

        Args:
            event: Event data dictionary

        Returns:
            True if sent successfully, False otherwise
        """
        if not self._connected or not self._ws:
            return False

        try:
            await self._ws.send(json.dumps(event))
            return True
        except Exception as exc:
            self._logger.warning("Failed to send event via WebSocket: %s", exc)
            self._connected = False
            return False

    def set_task_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Set callback function to handle received tasks.

        Args:
            callback: Function that takes a task message dict
        """
        self._task_callback = callback

    async def _receive_loop(self):
        """Main loop to receive messages from orchestrator."""
        while not self._should_stop:
            if not self._connected:
                # Try to reconnect
                success = await self.connect()
                if not success:
                    await asyncio.sleep(self._current_reconnect_delay)
                    # Exponential backoff
                    self._current_reconnect_delay = min(
                        self._current_reconnect_delay * 2,
                        self._max_reconnect_interval
                    )
                    continue

            try:
                # Receive message from orchestrator
                message = await self._ws.recv()

                if isinstance(message, bytes):
                    message = message.decode("utf-8")

                data = json.loads(message)

                # Process the task
                if self._task_callback:
                    try:
                        self._task_callback(data)
                    except Exception as exc:
                        self._logger.exception(
                            "Error in task callback: %s", exc)

            except websockets.exceptions.ConnectionClosed:
                self._logger.warning(
                    "WebSocket connection closed, will reconnect")
                self._connected = False
                self._ws = None
                await asyncio.sleep(self._current_reconnect_delay)
                self._current_reconnect_delay = min(
                    self._current_reconnect_delay * 2,
                    self._max_reconnect_interval
                )
            except Exception as exc:
                self._logger.exception(
                    "Error in WebSocket receive loop: %s", exc)
                await asyncio.sleep(1)

    async def start_receiving(self):
        """Start the background task to receive messages."""
        if self._receive_task and not self._receive_task.done():
            return

        self._should_stop = False
        self._receive_task = asyncio.create_task(self._receive_loop())
        self._logger.info("Started WebSocket receive loop")

    async def run(self):
        """Run the WebSocket client (connect and receive messages).

        This is the main entry point for running the WebSocket client.
        It handles the receive loop until stopped.
        """
        await self.start_receiving()
        if self._receive_task:
            await self._receive_task

    async def wait_until_stopped(self):
        """Wait until the receive loop is stopped."""
        if self._receive_task:
            await self._receive_task

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is currently connected."""
        return self._connected

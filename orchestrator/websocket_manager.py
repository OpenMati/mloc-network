"""WebSocket connection manager for orchestrator-worker communication.

Provides an alternative to Redis Pub/Sub for task delivery and worker events.
Workers can optionally use WebSocket long connections instead of subscribing
to Redis topics.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional, Set
from fastapi import WebSocket, WebSocketDisconnect


class WorkerConnection:
    """Represents a single WebSocket connection from a worker."""

    def __init__(self, worker_id: str, websocket: WebSocket):
        self.worker_id = worker_id
        self.websocket = websocket
        self.connected_at = time.time()
        self.last_seen = time.time()
        self.tasks_sent = 0
        self.events_received = 0

    async def send_task(self, message: Dict[str, Any]) -> bool:
        """Send a task message to the worker via WebSocket.

        Returns True if successful, False if connection is broken.
        """
        try:
            await self.websocket.send_json(message)
            self.tasks_sent += 1
            self.last_seen = time.time()
            return True
        except Exception:
            return False

    async def close(self):
        """Close the WebSocket connection gracefully."""
        try:
            await self.websocket.close()
        except Exception:
            pass


class WebSocketManager:
    """Manages WebSocket connections from workers.

    Workers register their WebSocket connection on startup. The orchestrator
    uses these connections to push tasks directly to workers instead of using
    Redis Pub/Sub.
    """

    def __init__(self, logger: logging.Logger):
        self._logger = logger
        self._connections: Dict[str, WorkerConnection] = {}
        self._lock = asyncio.Lock()

    async def register_worker(self, worker_id: str, websocket: WebSocket) -> None:
        """Register a new worker WebSocket connection."""
        async with self._lock:
            if worker_id in self._connections:
                # Close old connection if exists
                old_conn = self._connections[worker_id]
                await old_conn.close()
                self._logger.warning(
                    "Worker %s reconnected, closing old connection", worker_id
                )

            conn = WorkerConnection(worker_id, websocket)
            self._connections[worker_id] = conn
            self._logger.info(
                "Worker %s registered via WebSocket (total: %d)",
                worker_id, len(self._connections)
            )

    async def unregister_worker(self, worker_id: str) -> None:
        """Remove a worker connection."""
        async with self._lock:
            conn = self._connections.pop(worker_id, None)
            if conn:
                await conn.close()
                self._logger.info(
                    "Worker %s unregistered from WebSocket (total: %d)",
                    worker_id, len(self._connections)
                )

    def is_worker_connected(self, worker_id: str) -> bool:
        """Check if a worker is connected via WebSocket."""
        return worker_id in self._connections

    async def send_task_to_worker(
        self, worker_id: str, message: Dict[str, Any]
    ) -> bool:
        """Send a task to a specific worker via WebSocket.

        Returns True if the message was sent successfully, False otherwise.
        If the connection is broken, it will be automatically removed.
        """
        conn = self._connections.get(worker_id)
        if not conn:
            return False

        success = await conn.send_task(message)
        if not success:
            # Connection is broken, remove it
            await self.unregister_worker(worker_id)
        return success

    async def handle_worker_connection(
        self,
        worker_id: str,
        websocket: WebSocket,
        event_callback: Optional[Any] = None,
    ) -> None:
        """Handle a worker's WebSocket connection lifecycle.

        This coroutine manages the connection, receives events from the worker,
        and processes them using the provided callback.

        Args:
            worker_id: The worker's unique identifier
            websocket: The WebSocket connection
            event_callback: Optional async function(event_data) to handle worker events
        """
        await self.register_worker(worker_id, websocket)

        try:
            while True:
                # Receive messages from worker (heartbeats, status updates, etc.)
                data = await websocket.receive_json()

                async with self._lock:
                    conn = self._connections.get(worker_id)
                    if conn:
                        conn.last_seen = time.time()
                        conn.events_received += 1

                # Process worker event
                if event_callback:
                    try:
                        if asyncio.iscoroutinefunction(event_callback):
                            await event_callback(data)
                        else:
                            event_callback(data)
                    except Exception as exc:
                        self._logger.exception(
                            "Error processing worker %s event: %s", worker_id, exc
                        )

        except WebSocketDisconnect:
            self._logger.info("Worker %s disconnected", worker_id)
        except Exception as exc:
            self._logger.warning(
                "WebSocket error for worker %s: %s", worker_id, exc
            )
        finally:
            await self.unregister_worker(worker_id)

    def get_connected_workers(self) -> Set[str]:
        """Get the set of currently connected worker IDs."""
        return set(self._connections.keys())

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get statistics about active connections."""
        stats = {
            "total_connections": len(self._connections),
            "workers": {}
        }

        for worker_id, conn in self._connections.items():
            stats["workers"][worker_id] = {
                "connected_at": conn.connected_at,
                "last_seen": conn.last_seen,
                "tasks_sent": conn.tasks_sent,
                "events_received": conn.events_received,
                "connected_seconds": time.time() - conn.connected_at,
            }

        return stats

# worker/worker_transport.py
"""Transport abstraction for worker-orchestrator communication.

Provides a unified interface for Redis and WebSocket transports, allowing
workers to operate with or without Redis when WebSocket mode is enabled.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from event_schema import WorkerEvent, TaskEvent, serialize_event


class WorkerTransport(ABC):
    """Abstract base class for worker transport mechanisms."""

    def __init__(self, worker_id: str):
        self.worker_id = worker_id

    @abstractmethod
    def register(
        self,
        status: str,
        started_at: str,
        pid: int,
        env: Dict[str, Any],
        hardware: Dict[str, Any],
        tags: List[str],
        *,
        task_types: Optional[List[str]] = None,
        cost_per_hour: float,
        power_metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register worker with orchestrator."""
        pass

    @abstractmethod
    def heartbeat(
        self,
        ts: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        ttl_sec: int = 120,
    ) -> None:
        """Send heartbeat to orchestrator."""
        pass

    @abstractmethod
    def set_status(
        self, status: str, extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update worker status."""
        pass

    @abstractmethod
    def unregister(
        self,
        *,
        cost_per_hour: Optional[float] = None,
        uptime_sec: Optional[float] = None,
        power_summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Unregister worker from orchestrator."""
        pass

    @abstractmethod
    def task_started(
        self,
        task_id: str,
        *,
        task_type: Optional[str] = None,
        dispatched_at: Optional[str] = None,
        started_at: Optional[str] = None,
    ) -> None:
        """Notify orchestrator that task has started."""
        pass

    @abstractmethod
    def task_succeeded(
        self, task_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Notify orchestrator that task succeeded."""
        pass

    @abstractmethod
    def task_failed(
        self, task_id: str, error: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Notify orchestrator that task failed."""
        pass


class RedisTransport(WorkerTransport):
    """Redis-based transport using Pub/Sub and key-value storage."""

    WORKERS_SET = "workers:ids"

    def __init__(self, rds, worker_id: str):
        super().__init__(worker_id)
        self.rds = rds

    def _key(self) -> str:
        return f"worker:{self.worker_id}"

    def _hb_key(self) -> str:
        return f"worker:{self.worker_id}:hb"

    def register(
        self,
        status: str,
        started_at: str,
        pid: int,
        env: Dict[str, Any],
        hardware: Dict[str, Any],
        tags: List[str],
        *,
        task_types: Optional[List[str]] = None,
        cost_per_hour: float,
        power_metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        data = {
            "worker_id": self.worker_id,
            "status": status,
            "started_at": started_at,
            "pid": str(pid),
            "env_json": json.dumps(env, ensure_ascii=False),
            "hardware_json": json.dumps(hardware, ensure_ascii=False),
            "tags_json": json.dumps(tags, ensure_ascii=False),
            "task_types_json": json.dumps(task_types or [], ensure_ascii=False),
            "last_seen": started_at,
            "cost_per_hour": f"{cost_per_hour}",
        }
        with self.rds.pipeline() as p:
            p.sadd(self.WORKERS_SET, self.worker_id)
            p.hset(self._key(), mapping=data)
            payload = {
                "env": env,
                "hardware": hardware,
                "cost_per_hour": cost_per_hour,
                "task_types": task_types or [],
            }
            if power_metrics:
                payload["power_metrics"] = power_metrics
            evt = WorkerEvent(
                type="REGISTER",
                worker_id=self.worker_id,
                status=status,
                ts=started_at,
                tags=tags,
                payload=payload,
            )
            p.publish(
                "workers.events", json.dumps(
                    serialize_event(evt), ensure_ascii=False)
            )
            p.execute()

    def heartbeat(
        self,
        ts: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        ttl_sec: int = 120,
    ) -> None:
        ts = ts or datetime.now(timezone.utc).isoformat()
        with self.rds.pipeline() as p:
            p.setex(self._hb_key(), ttl_sec, ts)
            p.hset(self._key(), mapping={"last_seen": ts})
            evt = WorkerEvent(
                type="HEARTBEAT",
                worker_id=self.worker_id,
                ts=ts,
                metrics=metrics or {},
            )
            p.publish(
                "workers.events", json.dumps(
                    serialize_event(evt), ensure_ascii=False)
            )
            p.execute()

    def set_status(
        self, status: str, extra: Optional[Dict[str, Any]] = None
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        mapping = {"status": status, "last_seen": now}
        if extra:
            mapping.update({f"extra_{k}": str(v) for k, v in extra.items()})
        with self.rds.pipeline() as p:
            p.hset(self._key(), mapping=mapping)
            evt = WorkerEvent(
                type="STATUS",
                worker_id=self.worker_id,
                status=status,
                ts=now,
                payload=extra or {},
            )
            p.publish(
                "workers.events", json.dumps(
                    serialize_event(evt), ensure_ascii=False)
            )
            p.execute()

    def unregister(
        self,
        *,
        cost_per_hour: Optional[float] = None,
        uptime_sec: Optional[float] = None,
        power_summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self.rds.pipeline() as p:
            p.srem(self.WORKERS_SET, self.worker_id)
            p.delete(self._key())
            p.delete(self._hb_key())
            payload: Dict[str, Any] = {}
            if cost_per_hour is not None:
                payload["cost_per_hour"] = cost_per_hour
            if uptime_sec is not None:
                payload["uptime_sec"] = uptime_sec
            if power_summary is not None:
                payload["power_summary"] = power_summary
            evt = WorkerEvent(
                type="UNREGISTER", worker_id=self.worker_id, payload=payload
            )
            p.publish(
                "workers.events", json.dumps(
                    serialize_event(evt), ensure_ascii=False)
            )
            p.execute()

    def task_failed(
        self, task_id: str, error: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        evt = TaskEvent(
            type="TASK_FAILED",
            worker_id=self.worker_id,
            task_id=task_id,
            error=error,
            payload=metadata or {},
            ts=now,
        )
        self.rds.publish(
            "tasks.events", json.dumps(
                serialize_event(evt), ensure_ascii=False)
        )

    def task_succeeded(
        self, task_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        evt = TaskEvent(
            type="TASK_SUCCEEDED",
            worker_id=self.worker_id,
            task_id=task_id,
            payload=metadata or {},
            ts=now,
        )
        self.rds.publish(
            "tasks.events", json.dumps(
                serialize_event(evt), ensure_ascii=False)
        )

    def task_started(
        self,
        task_id: str,
        *,
        task_type: Optional[str] = None,
        dispatched_at: Optional[str] = None,
        started_at: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload: Dict[str, Any] = {}
        if task_type is not None:
            payload["taskType"] = task_type
        if dispatched_at is not None:
            payload["dispatched_at"] = dispatched_at
        if started_at is not None:
            payload["started_at"] = started_at
        evt = TaskEvent(
            type="TASK_STARTED",
            worker_id=self.worker_id,
            task_id=task_id,
            payload=payload,
            ts=now,
        )
        self.rds.publish(
            "tasks.events", json.dumps(
                serialize_event(evt), ensure_ascii=False)
        )


class WebSocketTransport(WorkerTransport):
    """WebSocket-based transport that doesn't require Redis."""

    def __init__(self, worker_id: str, websocket_client):
        super().__init__(worker_id)
        self.ws_client = websocket_client
        self._cached_state: Dict[str, Any] = {}
        self._cached_events: List[Dict[str, Any]] = []
        # Use a queue and dedicated thread to avoid asyncio.run() conflicts
        import queue
        import threading
        self._event_queue: queue.Queue = queue.Queue()
        self._stop_sender = threading.Event()
        self._send_thread: Optional[threading.Thread] = None
        self._start_sender_thread()

    def _start_sender_thread(self):
        """Start a background thread with its own event loop to send queued events."""
        import threading
        if self._send_thread and self._send_thread.is_alive():
            return

        def sender_loop():
            import asyncio
            import time
            # Create a dedicated event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                while not self._stop_sender.is_set():
                    try:
                        # Get event with timeout to allow checking stop signal
                        event = self._event_queue.get(timeout=0.1)
                        # Send event asynchronously
                        if self.ws_client and self.ws_client.is_connected:
                            try:
                                loop.run_until_complete(
                                    self.ws_client.send_event(event))
                            except Exception:
                                # If send fails, put back in queue for retry
                                self._event_queue.put(event)
                                time.sleep(0.5)
                    except:  # queue.Empty or other exceptions
                        continue
            finally:
                loop.close()

        self._send_thread = threading.Thread(
            target=sender_loop, daemon=True, name="ws-event-sender")
        self._send_thread.start()

    def _send_event_sync(self, event: Dict[str, Any]) -> None:
        """Send event via WebSocket using dedicated sender thread."""
        try:
            # Queue the event for immediate sending by background thread
            # This returns immediately without blocking
            self._event_queue.put(event, block=False)
        except Exception:
            # If queue is full or other error, cache the event
            if event not in self._cached_events:
                self._cached_events.append(event)

    def register(
        self,
        status: str,
        started_at: str,
        pid: int,
        env: Dict[str, Any],
        hardware: Dict[str, Any],
        tags: List[str],
        *,
        task_types: Optional[List[str]] = None,
        cost_per_hour: float,
        power_metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        # Cache registration info
        self._cached_state = {
            "worker_id": self.worker_id,
            "status": status,
            "started_at": started_at,
            "pid": pid,
            "env": env,
            "hardware": hardware,
            "tags": tags,
            "task_types": task_types or [],
            "cost_per_hour": cost_per_hour,
        }

        payload = {
            "env": env,
            "hardware": hardware,
            "cost_per_hour": cost_per_hour,
            "task_types": task_types or [],
        }
        if power_metrics:
            payload["power_metrics"] = power_metrics

        event = {
            "type": "REGISTER",
            "worker_id": self.worker_id,
            "status": status,
            "ts": started_at,
            "tags": tags,
            "payload": payload,
        }
        self._send_event_sync(event)

    def heartbeat(
        self,
        ts: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        ttl_sec: int = 120,
    ) -> None:
        ts = ts or datetime.now(timezone.utc).isoformat()
        self._cached_state["last_seen"] = ts

        event = {
            "type": "HEARTBEAT",
            "worker_id": self.worker_id,
            "timestamp": ts,
            "metrics": metrics or {},
        }
        self._send_event_sync(event)

    def set_status(
        self, status: str, extra: Optional[Dict[str, Any]] = None
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._cached_state["status"] = status
        self._cached_state["last_seen"] = now

        event = {
            "type": "STATUS",
            "worker_id": self.worker_id,
            "status": status,
            "ts": now,
            "payload": extra or {},
        }
        self._send_event_sync(event)

    def unregister(
        self,
        *,
        cost_per_hour: Optional[float] = None,
        uptime_sec: Optional[float] = None,
        power_summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload: Dict[str, Any] = {}
        if cost_per_hour is not None:
            payload["cost_per_hour"] = cost_per_hour
        if uptime_sec is not None:
            payload["uptime_sec"] = uptime_sec
        if power_summary is not None:
            payload["power_summary"] = power_summary

        event = {
            "type": "UNREGISTER",
            "worker_id": self.worker_id,
            "payload": payload,
        }
        self._send_event_sync(event)

    def task_started(
        self,
        task_id: str,
        *,
        task_type: Optional[str] = None,
        dispatched_at: Optional[str] = None,
        started_at: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload: Dict[str, Any] = {}
        if task_type is not None:
            payload["taskType"] = task_type
        if dispatched_at is not None:
            payload["dispatched_at"] = dispatched_at
        if started_at is not None:
            payload["started_at"] = started_at

        event = {
            "type": "TASK_STARTED",
            "worker_id": self.worker_id,
            "task_id": task_id,
            "payload": payload,
            "ts": now,
        }
        self._send_event_sync(event)

    def task_succeeded(
        self, task_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        event = {
            "type": "TASK_SUCCEEDED",
            "worker_id": self.worker_id,
            "task_id": task_id,
            "payload": metadata or {},
            "ts": now,
        }
        self._send_event_sync(event)

    def task_failed(
        self, task_id: str, error: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        event = {
            "type": "TASK_FAILED",
            "worker_id": self.worker_id,
            "task_id": task_id,
            "error": error,
            "payload": metadata or {},
            "ts": now,
        }
        self._send_event_sync(event)

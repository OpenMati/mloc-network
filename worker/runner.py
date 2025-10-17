# worker/runner.py
"""Pub/Sub runner that executes assigned tasks using pluggable executors."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import time
from datetime import datetime, timezone

import requests
from manifest_utils import prepare_output_dir, sync_manifest


class Runner:
    def __init__(
        self,
        lifecycle,
        rds,
        topic: str,
        results_dir: Path,
        executors: Dict[str, Any],
        default_executor: Any,
        logger: Any,
        use_websocket: bool = False,
    ):
        self.lifecycle = lifecycle
        self.redis = rds  # Can be None in WebSocket-only mode
        self.topic = topic
        self.results_dir = results_dir
        self.executors = executors
        self.logger = logger
        self.default_executor = default_executor
        self.use_websocket = use_websocket

    def _resolve_output_dir(self, task_id: str, task: Dict[str, Any]) -> Path:
        """Pick the destination directory for task outputs.

        Priority: spec.output.destination.path -> default RESULTS_DIR.
        Relative paths under spec are resolved against the configured RESULTS_DIR
        so users can safely provide per-task subfolders.
        """
        spec = (task or {}).get("spec") or {}
        output_cfg = spec.get("output") or {}
        dest = (output_cfg.get("destination") or {})
        dest_type = str(dest.get("type") or "local").lower()
        dest_path = dest.get("path")

        if dest_type == "local" and dest_path:
            chosen = Path(dest_path)
            if not chosen.is_absolute():
                chosen = self.results_dir / chosen
        else:
            chosen = self.results_dir / task_id

        # Ensure each task still gets an isolated directory
        if chosen.name != task_id:
            chosen = chosen / task_id
        prepare_output_dir(chosen)
        return chosen

    def _write_results(self, task_id: str, task: Dict[str, Any], out_dir: Path, result: Optional[Dict[str, Any]]):
        if result is None:
            return
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "responses.json").write_text(json.dumps(result,
                                                           ensure_ascii=False, indent=2))
        expected = ((task or {}).get("spec") or {}).get(
            "output", {}).get("artifacts", []) or []
        sync_manifest(out_dir, task_id, expected)
        self._maybe_emit_http(task_id, task, result)

    def _maybe_emit_http(self, task_id: str, task: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Send task results to an HTTP endpoint when requested by the spec."""
        spec = (task or {}).get("spec") or {}
        output_cfg = spec.get("output") or {}
        destination = output_cfg.get("destination") or {}

        dest_type = str(destination.get("type") or "local").lower()
        if dest_type != "http":
            return

        url = destination.get("url")
        if not url:
            raise RuntimeError(
                "spec.output.destination.url is required when type is 'http'")

        method = str(destination.get("method") or "POST").upper()
        headers = destination.get("headers") or {}
        timeout = float(destination.get("timeoutSec") or 15)

        # Get worker_id from transport (supports both Redis and WebSocket)
        worker_id = getattr(self.lifecycle.transport, 'worker_id', None)

        payload = {
            "task_id": task_id,
            "result": result,
            "worker_id": worker_id,
        }

        try:
            response = requests.request(
                method, url, json=payload, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Failed to deliver task {task_id} result to {url}: {exc}") from exc

        if response.status_code >= 400:
            snippet = response.text[:200]
            raise RuntimeError(
                f"HTTP delivery for task {task_id} returned status {response.status_code}: {snippet}"
            )

        self.logger.info("Task %s result delivered to %s (%s)",
                         task_id, url, response.status_code)

    def _process_task_message(self, data: Dict[str, Any]):
        """Process a task message (from Redis or WebSocket).

        This method contains the core task processing logic that can be called
        from either the Redis Pub/Sub listener or the WebSocket message handler.
        """
        # Get worker_id from transport (supports both Redis and WebSocket)
        worker_id = getattr(self.lifecycle.transport, 'worker_id', None)

        assigned_worker = data.get("assigned_worker")
        if assigned_worker != worker_id:
            self.logger.info(
                "Skipping task %s assigned to %s (this worker id=%s)",
                data.get("task_id"),
                assigned_worker,
                worker_id,
            )
            return

        task_id = str(data.get("task_id"))
        task = data.get("task") or {}
        task.setdefault("task_id", task_id)
        task_type = (task.get("spec") or {}).get("taskType")
        parent_task_id = data.get("parent_task_id")
        shard_index = data.get("shard_index")
        shard_total = data.get("shard_total")
        dispatched_at = data.get("dispatched_at")

        extra = []
        if parent_task_id:
            extra.append(f"parent={parent_task_id}")
        if shard_index is not None and shard_total is not None:
            extra.append(f"shard={shard_index}/{shard_total}")
        extra_info = ", ".join(extra) if extra else "no-parent"

        self.logger.info(
            "Received task %s (type=%s, %s) with spec keys %s",
            task_id,
            task_type or "unknown",
            extra_info,
            sorted((task.get("spec") or {}).keys()),
        )

        out_dir = self._resolve_output_dir(task_id, task)
        self.lifecycle.set_running(task_id)
        start_iso = datetime.now(timezone.utc).isoformat()
        start_wall = time.time()
        self.lifecycle.notify_task_started(
            task_id,
            task_type=task_type,
            dispatched_at=dispatched_at,
            started_at=start_iso,
        )
        executor = None
        try:
            if task_type == "inference":
                enforce_cpu = bool(
                    (task.get("spec") or {}).get("enforce_cpu", False))
                if enforce_cpu:
                    executor = self.default_executor
                else:
                    executor = self.executors.get(
                        "vllm", self.default_executor)
            else:
                executor = self.executors.get(task_type, self.default_executor)

            out = None
            if executor:
                out = executor.run(task, out_dir)
            self._write_results(task_id, task, out_dir, out)
            finished_iso = datetime.now(timezone.utc).isoformat()
            runtime_sec = max(0.0, time.time() - start_wall)
            metadata = {
                "taskType": task_type,
                "runtime_sec": runtime_sec,
                "started_at": start_iso,
                "finished_at": finished_iso,
            }
            if dispatched_at:
                metadata["dispatched_at"] = dispatched_at
            self.lifecycle.set_succeeded(task_id, metadata=metadata)
            self.logger.info("Task %s completed successfully", task_id)
        except Exception as e:
            finished_iso = datetime.now(timezone.utc).isoformat()
            runtime_sec = max(0.0, time.time() - start_wall)
            metadata = {
                "taskType": task_type,
                "runtime_sec": runtime_sec,
                "started_at": start_iso,
                "finished_at": finished_iso,
            }
            if dispatched_at:
                metadata["dispatched_at"] = dispatched_at
            self.lifecycle.set_failed(task_id, str(e), metadata=metadata)
            self.logger.exception("Task %s failed", task_id)
        finally:
            try:
                if executor:
                    executor.cleanup()
            except Exception:
                pass
            self.lifecycle.set_idle(task_id)

    def start(self):
        """Start the runner to receive and process tasks.

        If use_websocket is True and WebSocket client is configured in lifecycle,
        uses WebSocket transport. Otherwise falls back to Redis Pub/Sub.
        """
        if self.use_websocket and hasattr(self.lifecycle, 'websocket_client') and self.lifecycle.websocket_client:
            self.logger.info("Starting runner with WebSocket transport")
            self._start_websocket()
        else:
            if not self.redis:
                raise RuntimeError(
                    "Redis transport requested but Redis client not available. "
                    "Set WORKER_USE_WEBSOCKET=true to use WebSocket mode without Redis."
                )
            self.logger.info("Starting runner with Redis Pub/Sub transport")
            self._start_redis_pubsub()

    def _start_websocket(self):
        """Run in WebSocket mode - tasks come via WebSocket connection."""
        import asyncio

        async def run_websocket():
            """Async wrapper to run WebSocket client."""
            # Set the task callback
            self.lifecycle.websocket_client.set_task_callback(
                self._process_task_message)

            try:
                # Run the WebSocket client (connect and receive messages)
                await self.lifecycle.websocket_client.run()
            except KeyboardInterrupt:
                self.logger.info(
                    "Runner interrupted by user; shutting down WebSocket")
            finally:
                await self.lifecycle.websocket_client.disconnect()

        # Run the async function
        try:
            asyncio.run(run_websocket())
        except KeyboardInterrupt:
            self.logger.info("WebSocket runner stopped by user")
        except Exception as exc:
            self.logger.exception("WebSocket runner error: %s", exc)
            raise

    def _start_redis_pubsub(self):
        """Run in Redis Pub/Sub mode - tasks come via Redis channels."""
        pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
        try:
            pubsub.subscribe(self.topic)
            for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue

                raw = msg.get("data")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="ignore")
                try:
                    data = json.loads(raw)
                except Exception:
                    continue

                self._process_task_message(data)

        except KeyboardInterrupt:
            self.logger.info(
                "Runner interrupted by user; shutting down pubsub loop")
        finally:
            try:
                pubsub.close()
            except Exception:
                pass

# MLOC - Modular LLM Operations Container

MLOC provides a scalable control plane for Large Language Model workloads. The
system consists of an **Orchestrator** (FastAPI), a fleet of **Workers**, and
flexible transport layers (Redis pub/sub or WebSocket) for dispatch and status 
tracking. Tasks can be submitted via YAML or Simple Task API and can run spectrum 
from single-shot inference to multi-stage PPO/DPO training pipelines.

```
+-------------+    HTTP API    +--------------+    Redis/WebSocket    +-------------+
|   Client    | -------------> | Orchestrator | ------------------> |   Worker    |
|             |                |              |                      | (built-in   |
+-------------+                +--------------+                      |  or SDK)    |
                                      |                              +-------------+
                                      |                                    |
                                      v                                    v
                              +-------------+                      +-------------+
                              |    Redis    |                      |  Executors  |
                              | (Optional)  |                      | (vLLM, TRL) |
                              +-------------+                      +-------------+
```

## Components
- **Orchestrator** – Parses YAML or Simple Task API requests, manages dependencies, 
  schedules work, aggregates results/events, and provides WebSocket support for 
  real-time worker communication.
- **Workers** – Connect via Redis topics or WebSocket, pick executors (vLLM, 
  Hugging Face Transformers, PPO/DPO, custom SDK executors), and write outputs.
- **MLOC SDK** – Python SDK for building custom executors with minimal boilerplate,
  supporting both class-based and decorator-based patterns.
- **Redis** – Optional message bus plus lightweight state store for worker metadata 
  and task status notifications (can be replaced by WebSocket transport).

## Key Capabilities
- **Dual Transport Modes**: Redis pub/sub for distributed deployments or WebSocket 
  for simplified, real-time communication without Redis dependency.
- **Simple Task API**: Submit tasks via JSON payload (`/api/v1/tasks/simple`) for 
  quick integration without YAML template knowledge.
- **MLOC SDK**: Build custom executors with a high-level Python SDK supporting 
  lifecycle hooks, decorators, and automatic result serialization.
- Declarative task definitions with optional `spec.stages` pipelines (YAML mode).
- Resource-aware scheduling with optional data-parallel fan-out when
  `spec.parallel.enabled=true` for inference jobs.
- Flexible artifact delivery: Workers can persist to shared storage or upload
  binaries (for example, fine-tuned checkpoints) back to the orchestrator over
  HTTP after every training run.
- Per-task output directory overrides via `spec.output.destination.path`
  (relative paths resolve under the worker `RESULTS_DIR`).
- Shared storage ready: Docker Compose sample mounts an NFS export so all
  workers write to the same location.

## Quick Start (local)

### Option A: WebSocket Mode (No Redis Required)

The simplest way to get started with a single orchestrator and worker.

#### 1. Install dependencies (via uv)
```bash
# Install uv (skip if already installed, see https://docs.astral.sh/uv)
pip install uv

# Create and activate virtual environment
uv venv .venv
source .venv/bin/activate

# Sync orchestrator + default worker dependencies (includes transformers/torch)
uv sync --extra inference

# For additional capabilities, add extras:
# uv sync --extra inference --extra rag       # Enable RAG
# uv sync --extra inference --extra agent     # Enable Agent executors
# uv sync --all-extras                        # Install all optional components
```
See `docs/executors.md` for each `taskType` and its corresponding executor dependencies. 
`uv sync` reads the repo's `uv.lock` to ensure consistent dependency versions across machines.

#### 2. Run the Orchestrator
```bash
export ORCHESTRATOR_TOKEN="dev-token"  # optional auth
export ORCHESTRATOR_RESULTS_DIR=./results_host
uv run python orchestrator/main.py
# listens on 0.0.0.0:8000 (override with PORT)
```

#### 3. Run a Worker (WebSocket mode)
```bash
export RESULTS_DIR=./results_workers    # or an NFS mount
export ORCHESTRATOR_BASE_URL="http://127.0.0.1:8000"
export WORKER_TRANSPORT="websocket"     # Use WebSocket transport
uv run python worker/main.py
```

Workers connect to the orchestrator via WebSocket (`ws://127.0.0.1:8000/ws/worker`),
register their capabilities, and receive tasks in real-time.

---

### Option B: Redis Mode (Distributed Deployment)

For multi-orchestrator or distributed setups, use Redis as the message bus.

#### 1. Install dependencies (same as Option A)

#### 2. Start Redis
```bash
redis-server
# or use docker:
docker compose -f docker-compose.redis.yml up
```

#### 3. Run the Orchestrator
```bash
export REDIS_URL="redis://localhost:6379/0"
export ORCHESTRATOR_TOKEN="dev-token"  # optional auth
export ORCHESTRATOR_RESULTS_DIR=./results_host
uv run python orchestrator/main.py
# listens on 0.0.0.0:8000 (override with PORT)
```

#### 4. Run a Worker (Redis mode)
```bash
export REDIS_URL="redis://localhost:6379/0"
export RESULTS_DIR=./results_workers    # or an NFS mount
export ORCHESTRATOR_BASE_URL="http://127.0.0.1:8000"  # enable HTTP artifact uploads
uv run python worker/main.py
```

Workers register with Redis, stream heartbeats, and execute incoming tasks.
If the YAML sets `spec.output.destination.path`, results go there; otherwise
`RESULTS_DIR/<task_id>/responses.json` is used.

---

### Common Steps for Both Modes

#### 5. Inspect built-in metrics
```bash
curl http://127.0.0.1:8000/metrics
```
The response aggregates event counters (tasks succeeded/failed/requeued, active
workers, heartbeat counts) and is refreshed whenever the orchestrator receives
Redis events or WebSocket messages.

#### 6. Submit a task

**Option 1: Simple Task API (JSON)**
```bash
curl -X POST "http://localhost:8000/api/v1/tasks/simple" \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{
    "taskType": "hello-world",
    "input": {
      "name": "World",
      "message": "Hello from MLOC!"
    },
    "tags": ["demo"],
    "sloSeconds": 60
  }'
```

**Option 2: YAML Template**
```bash
curl -X POST "http://localhost:8000/api/v1/tasks" \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: text/yaml" \
  --data-binary @templates/inference_vllm_mistral.yaml
```

See `docs/simple_api_examples.md` for more Simple Task API examples and patterns.

---

## MLOC SDK - Build Custom Executors

The MLOC SDK provides a simplified interface for creating custom task executors
without dealing with infrastructure concerns like transport, lifecycle management,
or result serialization.

### Quick Example: Class-Based Executor

```python
from pathlib import Path
from typing import Any, Dict
from mloc_sdk import BaseExecutor, WorkerSDK

class GreetingExecutor(BaseExecutor):
    name = "greeting"
    description = "Generates personalized greetings"
    version = "1.0.0"
    
    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        name = task_spec.get("name", "World")
        language = task_spec.get("language", "en")
        
        greetings = {
            "en": f"Hello, {name}!",
            "es": f"¡Hola, {name}!",
            "zh": f"你好, {name}!",
        }
        
        greeting = greetings.get(language, greetings["en"])
        result = {"greeting": greeting, "name": name, "language": language}
        
        self.save_json(output_dir / "greeting.json", result)
        return result

# Create and run worker
if __name__ == "__main__":
    sdk = WorkerSDK(orchestrator_url="ws://localhost:8000/ws/worker")
    sdk.register_executor(GreetingExecutor())
    sdk.run()
```

### Decorator-Based Executor

```python
from mloc_sdk import executor, WorkerSDK

@executor(name="calculator", description="Performs arithmetic")
def calculate(task_spec, output_dir):
    a = task_spec.get("a", 0)
    b = task_spec.get("b", 0)
    operation = task_spec.get("operation", "add")
    
    result = a + b if operation == "add" else a - b
    return {"a": a, "b": b, "operation": operation, "result": result}

if __name__ == "__main__":
    sdk = WorkerSDK(orchestrator_url="ws://localhost:8000/ws/worker")
    sdk.register_executor(calculate)
    sdk.run()
```

### Features
- ✨ **Simple API**: Inherit from `BaseExecutor` or use `@executor` decorator
- 🔄 **Lifecycle Management**: Automatic prepare, execute, cleanup, and teardown
- 🚀 **WebSocket Transport**: Real-time communication (Redis-free)
- 📦 **Built-in Utilities**: JSON/text helpers, logging, validation
- 🎯 **Type Safe**: Full type hints for IDE support
- 🔌 **Pluggable**: Register multiple executors in a single worker

See `mloc_sdk/README.md` and `mloc_sdk/QUICKSTART.md` for comprehensive guides and examples.

---

## YAML Primer
```yaml
spec:
  taskType: "inference"
  resources: { ... }
  model: { ... }
  data:  { ... }
  output:
    destination:
      type: http
      url: http://127.0.0.1:8000/api/v1/results
      headers:
        Authorization: "Bearer dev-token"
```
- Enable automatic sharding by setting `spec.parallel.enabled: true` with an
  appropriate dataset split.
- Define multi-stage flows using `spec.stages`; the orchestrator chains them via
  dependencies.
- When `spec.output.destination.type` is `http`, the worker will upload the
  final model artifacts to the orchestrator (in addition to local persistence)
  so that downstream stages can fetch them by ID.

## Artifact Handling Overview

- **Worker output root** defaults to `./results_workers`. Each task receives its
  own subdirectory containing `responses.json`, `manifest.json`, `logs/` and
  `artifacts/`.
- **Orchestrator output root** defaults to `./results_host`. Results ingested by
  `/api/v1/results` are stored under this tree; upload endpoint automatically
  persists to `artifacts/<filename>` and refreshes manifest.
- Stage-to-stage pipelines can reference uploaded archives using
  `checkpoint.load.url`, for example
  `url: "${stage1.result.final_model_archive_url}"`.
- If you prefer classic shared storage, point both `RESULTS_DIR` variables at a
  common mount and skip HTTP uploads.

Each task run invokes `orchestrator.manifest_utils.sync_manifest` to sync `manifest.json`,
marking artifacts declared in `spec.output.artifacts` as `present` or `missing` for
easy validation of deliverables.

## State & Metrics

- `StateManager` is disabled by default; set `ORCHESTRATOR_STATE_ENABLED=1` to
  periodically write `TaskStore`, task records, and parent-child shard info to
  `${ORCHESTRATOR_STATE_DIR:-./state}/task_state.json` with auto-recovery on restart.
- Metrics snapshot defaults to `${ORCHESTRATOR_METRICS_DIR:-./metrics}/metrics.json`,
  also exposed via `/metrics` HTTP endpoint for real-time monitoring. Raw events
  are written to `${ORCHESTRATOR_METRICS_DIR:-./metrics}/events.log` in JSONL format.

### Key environment variables

| Variable | Default | Description |
| ---- | ------ | ---- |
| `ORCHESTRATOR_STATE_ENABLED` | `0` | Enable state snapshot and recovery |
| `ORCHESTRATOR_STATE_DIR` | `./state` | State snapshot directory (when enabled) |
| `ORCHESTRATOR_METRICS_DIR` | Depends on `STATE_ENABLED` (default `./metrics`) | Metrics output directory |
| `STATE_FLUSH_INTERVAL_SEC` | `5` | State flush interval in seconds |
| `RESULTS_DIR` | `./results_host` | Orchestrator results directory |
| `ORCHESTRATOR_TOKEN` | none | Optional Bearer token for API protection |
| `WORKER_TRANSPORT` | `redis` | Transport mode: `redis` or `websocket` |

## Testing

Lightweight unit tests cover task pool, manifest, aggregation, and metrics logic:

```bash
uv run pytest tests/test_core_flow.py
```

Test results are recorded in `.codex/testing.md` and `verification.md` for traceability.

## Docker Compose Deployment

Provides `docker-compose.yml`, `docker-compose.redis.yml`, and `docker-compose.websocket.yml` 
with `.env.example` for one-command deployment of Redis, Orchestrator, and Workers:

```bash
cp .env.example .env
# For Redis mode:
docker compose -f docker-compose.redis.yml up --build
# For WebSocket mode:
docker compose -f docker-compose.websocket.yml up --build
```

By default, results and state are written to `./data/` directory. Adjust paths
or add extras (training, RAG, etc.) in `.env` as needed.

## Shared Storage via NFS (optional)
1. Export an NFS directory on the orchestrator or storage host (instructions in
   `orchestrator/README.md`).
2. Mount the export on every worker and set `RESULTS_DIR` to the mountpoint.
3. Docker users can rely on `worker/docker-compose.yml`, which mounts an NFS
   volume at `/mnt/mloc-results` inside the container.

## Repository Layout
```
README.md                 # Top-level overview
orchestrator/             # Scheduling service + docs
worker/                   # Worker process, executors, docker assets
mloc_sdk/                 # Python SDK for custom executors
templates/                # YAML task examples
docs/                     # Additional documentation
  simple_api_examples.md  # Simple Task API usage examples
  executors.md            # Executor types and dependencies
  runbook.md              # Operations runbook
examples/                 # SDK usage examples
```

See also:
- `orchestrator/README.md` for API and scheduling internals.
- `worker/README.md` for worker configuration and runtime flow.
- `mloc_sdk/README.md` for SDK comprehensive guide.
- `mloc_sdk/QUICKSTART.md` for getting started with custom executors.
- `docs/simple_api_examples.md` for Simple Task API patterns.

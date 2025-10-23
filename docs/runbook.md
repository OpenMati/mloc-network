# MLOC Runbook (2025-10-09, Author: Codex)

## Startup Sequence
1. **Redis**: `redis-server`, ensure `REDIS_URL` points to an accessible instance.
2. **Orchestrator**:
   ```bash
   export REDIS_URL="redis://localhost:6379/0"
   export ORCHESTRATOR_STATE_DIR=./state
   python orchestrator/main.py
   ```
3. **Worker** (multiple instances as needed):
   ```bash
   export RESULTS_DIR=./results_workers
   pip install mloc[inference]  # Or install other extras as needed
   python worker/main.py
   ```

> When using Docker Compose, run `docker compose up`, the orchestration script will automatically install dependencies and mount the `./data/` directory to save state and results.

## State and Recovery
- Snapshots are written to `${ORCHESTRATOR_STATE_DIR}/task_state.json`, on restart the task pool, parent-child shards, and TaskRecord state are automatically recovered.
- Metrics are written to `${ORCHESTRATOR_STATE_DIR}/metrics/metrics.json`, raw events are recorded in `events.log`.
- For forced cleanup, safely delete the `state/` directory and restart, the system will start from a blank state.

## Common Diagnostics
| Target | Command |
| ---- | ---- |
| View metrics | `curl http://127.0.0.1:8000/metrics` |
| Check manifest | `cat results_host/<task_id>/manifest.json` |
| Check dead letters | `curl http://127.0.0.1:8000/api/v1/dead_letters` |
| Quick requeue task | `curl -X POST http://127.0.0.1:8000/admin/cleanup` |

## Validation Scripts
- `scripts/validate_echo_local.sh`: Validate local result persistence (EchoExecutor + Local output).
- `scripts/validate_echo_http.sh`: Validate HTTP upload and orchestrator aggregation.
- Both depend on `ORCHESTRATOR_URL` and `ORCHESTRATOR_TOKEN` environment variables, see `scripts/worker_validate.py --help` for more options.
- `scripts/replay_task.py`: Replay specified `task_id` based on `task_state.json`.
- `scripts/export_results.py` / `scripts/task_profile_report.py`: Export `responses.json` and generate task profile report.

## Troubleshooting Tips
- **Task stuck**: Check `tasks_requeued` count in `/metrics` and `dead_letters` API to confirm if retry limit exceeded.
- **Missing artifacts**: Review manifest entries with `status == "missing"` and check if executor has correct extras installed.
- **Worker offline**: When `active_workers` in `metrics.json` is empty, check `metrics/events.log` for last heartbeat time, and ensure Redis permissions and network are normal.

## Routine Maintenance
- Recommend periodic backups of `state/` and `results_host/` for disaster recovery.
- Clean up old tasks: Delete corresponding directories then run `curl -X POST /admin/cleanup` to remove invalid worker associations.
- Upgrade dependencies: Run `pip install --upgrade mloc[<extras>]` as needed, read `docs/executors.md` for dependency layers before upgrading.
- Upgrade with Docker Compose: After code updates, run `docker compose build --no-cache` to reinstall dependencies.

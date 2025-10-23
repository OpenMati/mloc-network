# Task Pool调度问题修复总结

## 问题描述

用户启动了 orchestrator 和一个 worker，调用接口创建了任务，但任务一直处于 `PENDING` 状态，无法被调度执行。

## 根本原因

问题出在 `TaskPool` 类的实现上，有两个关键bug：

### Bug 1: TaskPool缺少logger属性

**问题代码** (`task_store.py` line ~67):
```python
class TaskPool:
    def __init__(self, batch_size: int, slo_fraction: float, redis_client=None) -> None:
        # ...
        self._logger = logging.getLogger(__name__)  # ❌ 这行代码存在，但对象初始化失败
```

**错误日志**:
```
WARNING | Initial dispatch scan failed: 'TaskPool' object has no attribute '_logger'
```

**原因**: `TaskPool` 初始化时 `_logger` 属性设置失败，导致后续调用 `_logger` 时抛出异常，异常被静默捕获，任务池无法正常工作。

**修复**:
```python
class TaskPool:
    def __init__(self, batch_size: int, slo_fraction: float, redis_client=None, logger=None) -> None:
        # ...
        self._logger = logger or logging.getLogger(__name__)
```

并在 `TaskPoolManager.__init__` 中传入 logger:
```python
self._pool = TaskPool(batch_size, slo_fraction, redis_client, logger)
```

### Bug 2: PoolEntry中的record不是完整的TaskRecord

**问题代码** (`task_store.py` `_get_all_entries` 方法):
```python
def _get_all_entries(self) -> Dict[str, PoolEntry]:
    # ...
    class MinimalRecord:
        def __init__(self, data):
            self.slo_seconds = data.get("slo_seconds")
            self.submitted_ts = data.get("submitted_ts")
            self.load = data.get("load")
    
    record = MinimalRecord(record_data)  # ❌ 只有部分属性
    entry = self._deserialize_entry(data, record)
```

**问题**: 从 Redis 恢复的 `PoolEntry` 使用的是 `MinimalRecord`，缺少 `status` 等关键属性。

**现象**: 
```
Task xxx deferred: status is None, expected PENDING
```

**修复** (`task_store.py` `_dispatch_batch` 方法):
```python
def _dispatch_batch(self, entries: List[PoolEntry]) -> None:
    for entry in entries:
        # Get the actual TaskRecord from memory
        actual_record = self._task_lookup(entry.task_id)
        if not actual_record:
            self._logger.warning(f"Task {entry.task_id} not found in TASKS dict, skipping")
            continue
        
        # Update the entry's record reference to use the actual TaskRecord
        entry.record = actual_record
        # ... 后续处理
```

## 修改的文件

1. **`orchestrator/task_store.py`**:
   - `TaskPool.__init__`: 添加 `logger` 参数
   - `TaskPoolManager.__init__`: 传入 logger 给 TaskPool
   - `_get_all_entries`: 改进错误处理和日志
   - `_dispatch_batch`: 从内存中获取完整的 TaskRecord

## 验证步骤

1. 重启 orchestrator
2. 提交新任务:
   ```bash
   curl -X POST http://localhost:8000/api/v1/tasks \
     -H "Content-Type: text/plain" \
     -d "
   apiVersion: v1
   kind: Task
   metadata:
     name: test-echo
   spec:
     taskType: echo
     resources:
       replicas: 1
       hardware:
         cpu: \"1\"
         memory: \"1Gi\"
     input:
       message: Hello World!
     tags:
       - test
   "
   ```

3. 验证任务状态从 `PENDING` 变为 `DISPATCHED`:
   ```bash
   curl -s http://localhost:8000/api/v1/tasks | python3 -m json.tool
   ```

## 结果

✅ 任务现在能够正确调度，状态从 `PENDING` → `DISPATCHED`  
✅ Worker 成功接收到任务  
✅ 任务池日志正常输出，便于调试

## 附加工具

创建了两个调试脚本:
- `scripts/debug_taskpool.py`: 检查 Redis 中的任务池状态
- `scripts/cleanup_taskpool.py`: 清理 Redis 中的孤立任务条目

# WebSocket Async 修复说明

## 问题

Worker 启动时报错：
```
RuntimeError: no running event loop
```

在调用 `websocket_client.start_receiving()` 时抛出异常。

## 原因分析

**根本原因**：在同步上下文中调用 `asyncio.create_task()`

```python
# websocket_client.py (错误代码)
def start_receiving(self):  # ❌ 同步函数
    self._receive_task = asyncio.create_task(self._receive_loop())  # ❌ 需要运行中的事件循环
```

**调用链**：
```
main() [同步]
  → runner.start() [同步]
    → runner._start_websocket() [同步]
      → websocket_client.start_receiving() [同步]
        → asyncio.create_task() [❌ 需要事件循环]
```

`asyncio.create_task()` 必须在**已运行的事件循环**中调用，但我们在同步上下文中调用了它。

## 解决方案

### 1. 修改 `start_receiving()` 为异步函数

```python
# websocket_client.py (修复后)
async def start_receiving(self):  # ✅ 异步函数
    """Start the background task to receive messages."""
    if self._receive_task and not self._receive_task.done():
        return

    self._should_stop = False
    self._receive_task = asyncio.create_task(self._receive_loop())
    self._logger.info("Started WebSocket receive loop")
```

### 2. 添加 `run()` 方法作为主入口

```python
async def run(self):
    """Run the WebSocket client (connect and receive messages).
    
    This is the main entry point for running the WebSocket client.
    It handles the receive loop until stopped.
    """
    await self.start_receiving()
    if self._receive_task:
        await self._receive_task
```

### 3. 重构 `_start_websocket()` 使用 `asyncio.run()`

```python
# runner.py (修复后)
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

    # Run the async function with a new event loop
    try:
        asyncio.run(run_websocket())  # ✅ 创建并运行事件循环
    except KeyboardInterrupt:
        self.logger.info("WebSocket runner stopped by user")
    except Exception as exc:
        self.logger.exception("WebSocket runner error: %s", exc)
        raise
```

## 修复后的调用链

```
main() [同步]
  → runner.start() [同步]
    → runner._start_websocket() [同步]
      → asyncio.run(run_websocket()) [✅ 创建事件循环]
        → websocket_client.run() [异步]
          → websocket_client.start_receiving() [异步]
            → asyncio.create_task() [✅ 在事件循环中]
```

## 关键改进

### Before (错误)
```python
# 同步函数调用异步操作 - 错误！
def _start_websocket(self):
    self.lifecycle.websocket_client.start_receiving()  # ❌ 同步调用
    asyncio.run(self.lifecycle.websocket_client.wait_until_stopped())
```

### After (正确)
```python
# 使用 asyncio.run() 创建事件循环
def _start_websocket(self):
    async def run_websocket():
        await self.lifecycle.websocket_client.run()  # ✅ 异步调用
    
    asyncio.run(run_websocket())  # ✅ 创建并运行事件循环
```

## 测试步骤

### 1. 启动 Orchestrator

```bash
cd orchestrator
export REDIS_URL=redis://localhost:6379/0
python -m orchestrator.main
```

### 2. 启动 Worker (WebSocket 模式)

```bash
cd worker
export WORKER_USE_WEBSOCKET=true
export ORCHESTRATOR_BASE_URL=http://localhost:8000
export WORKER_ID=test-worker
export WORKER_COST_PER_HOUR=1.0
python main.py
```

### 期望输出

```
INFO - WebSocket transport enabled, will connect to http://localhost:8000
INFO - Using WebSocket transport (Redis-free mode)
INFO - Starting runner with WebSocket transport
INFO - Connecting to orchestrator via WebSocket: ws://localhost:8000/ws/worker/test-worker
INFO - WebSocket connected successfully
INFO - Started WebSocket receive loop
```

### 不应出现

```
✗ RuntimeError: no running event loop
✗ RuntimeWarning: coroutine '...' was never awaited
```

## 验证连接

```bash
# 检查 Worker 是否连接
curl http://localhost:8000/ws/stats | jq

# 期望输出
{
  "total_connections": 1,
  "workers": {
    "test-worker": {
      "connected_at": 1697520000.0,
      "last_seen": 1697520030.0,
      "tasks_sent": 0,
      "events_received": 5
    }
  }
}
```

## 相关概念

### asyncio.create_task() 的要求

`asyncio.create_task()` 必须满足：
1. ✅ 在异步函数中调用
2. ✅ 有一个运行中的事件循环

### asyncio.run() 的作用

```python
asyncio.run(coro)
```

等价于：

```python
loop = asyncio.new_event_loop()
try:
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)
finally:
    loop.close()
```

它会：
1. 创建新的事件循环
2. 运行协程直到完成
3. 清理并关闭事件循环

## 最佳实践

### ✅ 正确的异步模式

```python
# 方式 1: 使用 asyncio.run() (推荐)
def sync_function():
    async def async_work():
        await some_async_function()
    
    asyncio.run(async_work())

# 方式 2: 在已有事件循环中
async def async_function():
    task = asyncio.create_task(some_coroutine())
    await task
```

### ❌ 错误的模式

```python
# 错误 1: 同步函数中直接调用 create_task
def sync_function():
    task = asyncio.create_task(coro())  # ❌ RuntimeError

# 错误 2: 混合同步和异步
def sync_function():
    await some_async_function()  # ❌ SyntaxError
```

## 文件变更

- ✅ `worker/websocket_client.py`: `start_receiving()` 改为异步，添加 `run()` 方法
- ✅ `worker/runner.py`: `_start_websocket()` 使用 `asyncio.run()` 包装

## 总结

修复关键点：
1. **识别问题**：`asyncio.create_task()` 需要运行中的事件循环
2. **正确使用**：通过 `asyncio.run()` 创建事件循环上下文
3. **异步传播**：将需要事件循环的函数标记为 `async`
4. **清晰边界**：在同步-异步边界使用 `asyncio.run()`

Worker 现在可以正确启动并通过 WebSocket 与 Orchestrator 通信！

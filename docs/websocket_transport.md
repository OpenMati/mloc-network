# WebSocket 长连接通信功能

## 概述

本文档介绍 worker 和 orchestrator 之间的 WebSocket 长连接通信功能。当启用 WebSocket 时，worker 通过持久化的 WebSocket 连接接收任务，替代 Redis Pub/Sub 方式。

**关键特性：**
- ✅ 可选启用（通过环境变量配置）
- ✅ 任务接收通过 WebSocket（替代 Redis Pub/Sub）
- ✅ 任务提交和结果回传仍使用 HTTP POST（保持不变）
- ✅ 自动重连机制（指数退避）
- ✅ 兼容现有 Redis 模式（未启用 WebSocket 时回退到 Redis）

## 架构变化

### 通信方式对比

#### 原架构（仅 Redis）
```
┌─────────────┐                  ┌──────────────┐
│Orchestrator │─────Redis────────▶│   Worker     │
│             │   Pub/Sub tasks   │              │
│             │◀─────Redis────────│              │
│             │   workers.events  │              │
└─────────────┘                  └──────────────┘
      │                                   │
      └────────HTTP POST (results)───────┘
```

#### 新架构（WebSocket 可选）
```
┌─────────────┐                  ┌──────────────┐
│Orchestrator │══════WebSocket═══▶│   Worker     │
│             │   (tasks + events)│   (启用WS)   │
│             │◀══════WebSocket═══│              │
└─────────────┘                  └──────────────┘
      │                                   │
      └────────HTTP POST (results)───────┘

┌─────────────┐                  ┌──────────────┐
│Orchestrator │─────Redis────────▶│   Worker     │
│             │   Pub/Sub tasks   │  (未启用WS)  │
│             │◀─────Redis────────│              │
└─────────────┘                  └──────────────┘
```

## 配置方法

### Worker 端配置

#### 环境变量

```bash
# 启用 WebSocket 传输
export WORKER_USE_WEBSOCKET=true

# Orchestrator 地址（WebSocket 必需）
export ORCHESTRATOR_BASE_URL=http://localhost:8000

# 其他配置保持不变
export WORKER_ID=worker-001
export REDIS_URL=redis://localhost:6379/0
export WORKER_COST_PER_HOUR=3.5
```

#### Docker Compose 示例

```yaml
services:
  worker-websocket:
    build: ./worker
    environment:
      # 启用 WebSocket
      WORKER_USE_WEBSOCKET: "true"
      ORCHESTRATOR_BASE_URL: "http://orchestrator:8000"
      
      # 标准配置
      WORKER_ID: "worker-ws-001"
      REDIS_URL: "redis://redis:6379/0"
      WORKER_COST_PER_HOUR: "3.5"
      WORKER_TAGS: "gpu,inference"
    depends_on:
      - orchestrator
      - redis

  worker-redis:
    build: ./worker
    environment:
      # 不启用 WebSocket，使用 Redis
      WORKER_USE_WEBSOCKET: "false"
      
      # 标准配置
      WORKER_ID: "worker-redis-001"
      REDIS_URL: "redis://redis:6379/0"
      WORKER_COST_PER_HOUR: "2.5"
    depends_on:
      - redis
```

### Orchestrator 端配置

Orchestrator 自动支持两种模式，无需额外配置：
- 对 WebSocket 连接的 worker：通过 `/ws/worker/{worker_id}` 端点接收连接
- 对 Redis 连接的 worker：继续使用 Redis Pub/Sub

## API 端点

### WebSocket 端点

#### `GET /ws/worker/{worker_id}`

Worker 连接到 orchestrator 的 WebSocket 端点。

**WebSocket URL 示例：**
```
ws://orchestrator:8000/ws/worker/worker-001
```

**连接流程：**
1. Worker 启动时建立 WebSocket 连接
2. Orchestrator 注册该 worker 的连接
3. Orchestrator 通过 WebSocket 推送任务
4. Worker 通过 WebSocket 发送心跳和状态更新

**消息格式（Orchestrator → Worker - 任务）：**
```json
{
  "task_id": "task-abc-123",
  "task": {
    "spec": {
      "taskType": "inference",
      "model": "meta-llama/Llama-3.2-1B",
      "inputs": [
        {"prompt": "Hello, world!"}
      ]
    }
  },
  "assigned_worker": "worker-001",
  "dispatched_at": "2025-10-15T10:30:00Z"
}
```

**消息格式（Worker → Orchestrator - 事件）：**
```json
{
  "type": "HEARTBEAT",
  "worker_id": "worker-001",
  "timestamp": "2025-10-15T10:30:05Z",
  "metrics": {
    "loadavg": {"1m": 0.5, "5m": 0.3, "15m": 0.2},
    "power": {"watts": 150.0}
  }
}
```

#### `GET /ws/stats`

获取 WebSocket 连接统计信息。

**需要认证：** 是（Bearer Token）

**响应示例：**
```json
{
  "total_connections": 2,
  "workers": {
    "worker-001": {
      "connected_at": 1697365800.0,
      "last_seen": 1697365900.0,
      "tasks_sent": 15,
      "events_received": 30,
      "connected_seconds": 100.0
    },
    "worker-002": {
      "connected_at": 1697365850.0,
      "last_seen": 1697365920.0,
      "tasks_sent": 8,
      "events_received": 16,
      "connected_seconds": 70.0
    }
  }
}
```

## 实现细节

### 组件说明

#### 1. `orchestrator/websocket_manager.py`
WebSocket 连接管理器，维护所有 worker 的 WebSocket 连接。

**主要功能：**
- 管理 worker WebSocket 连接生命周期
- 发送任务到指定 worker
- 接收 worker 事件（心跳、状态更新）
- 提供连接统计信息

#### 2. `worker/websocket_client.py`
Worker 端 WebSocket 客户端，连接到 orchestrator。

**主要功能：**
- 建立和维护 WebSocket 连接
- 接收任务消息
- 发送心跳和事件
- 自动重连（指数退避）

#### 3. `orchestrator/dispatch.py` 修改
任务分发器现在支持两种传输方式：

```python
def _publish_task(self, topic: str, message: Dict[str, Any]) -> int:
    worker_id = message.get("assigned_worker")
    
    # 优先尝试 WebSocket
    if self._websocket_manager and worker_id:
        if self._websocket_manager.is_worker_connected(worker_id):
            # 通过 WebSocket 发送
            success = await self._websocket_manager.send_task_to_worker(...)
            if success:
                return 1
    
    # 回退到 Redis Pub/Sub
    return self._redis.publish(topic, payload)
```

#### 4. `worker/runner.py` 修改
Runner 支持两种接收模式：

```python
def start(self):
    if self.use_websocket:
        self._start_websocket()  # WebSocket 模式
    else:
        self._start_redis_pubsub()  # Redis 模式
```

### 重连机制

Worker 端 WebSocket 客户端具有健壮的重连机制：

```python
# 初始重连延迟：5 秒
# 最大重连延迟：60 秒
# 策略：指数退避

连接失败后：
- 第 1 次重试：5 秒后
- 第 2 次重试：10 秒后
- 第 3 次重试：20 秒后
- 第 4 次重试：40 秒后
- 第 5 次及以后：60 秒后
```

### 兼容性

- ✅ **向后兼容**：未启用 WebSocket 的 worker 继续使用 Redis
- ✅ **混合部署**：同一 orchestrator 可以同时服务 WebSocket 和 Redis worker
- ✅ **无缝切换**：可以随时启用/禁用 WebSocket（重启 worker）

## 性能对比

### WebSocket 优势

| 特性 | Redis Pub/Sub | WebSocket |
|------|--------------|-----------|
| 连接方式 | 每个 worker 订阅一个 topic | 每个 worker 一个持久连接 |
| 延迟 | 低（~1-5ms） | 极低（~0.5-2ms） |
| 可靠性 | 依赖 Redis | 直接连接，更简单 |
| 扩展性 | 优秀（Redis 集群） | 良好（单机连接数限制） |
| 资源消耗 | Redis 内存和CPU | Orchestrator 内存和连接数 |
| 消息顺序 | 保证 | 保证 |
| 依赖 | 需要 Redis | 仅需 HTTP 服务器 |

### 推荐使用场景

**使用 WebSocket：**
- Worker 数量较少（< 1000）
- 需要极低延迟
- 希望简化架构（减少对 Redis 的依赖）
- 有稳定的网络连接

**使用 Redis：**
- Worker 数量很多（> 1000）
- 需要横向扩展 orchestrator
- 已有 Redis 集群基础设施
- 网络不稳定（Redis 有更好的容错）

## 故障排查

### Worker 无法连接 WebSocket

**症状：**
```
Failed to connect WebSocket: Connection refused
```

**解决方法：**
1. 检查 `ORCHESTRATOR_BASE_URL` 是否正确
2. 确认 orchestrator 正在运行
3. 检查网络连通性：`curl http://orchestrator:8000/healthz`

### Worker 频繁重连

**症状：**
```
WebSocket connection closed, will reconnect
```

**可能原因：**
- Orchestrator 重启
- 网络不稳定
- Orchestrator 负载过高

**解决方法：**
- 检查 orchestrator 日志
- 增加 orchestrator 资源
- 考虑使用 Redis 模式

### 任务未收到

**症状：**
Worker 已连接但不执行任务

**排查步骤：**
1. 检查 worker 是否在 orchestrator 注册：
   ```bash
   curl -H "Authorization: Bearer $TOKEN" http://orchestrator:8000/workers
   ```

2. 检查 WebSocket 连接状态：
   ```bash
   curl -H "Authorization: Bearer $TOKEN" http://orchestrator:8000/ws/stats
   ```

3. 查看 orchestrator 日志确认任务分发：
   ```
   Sent task task-123 to worker worker-001 via WebSocket
   ```

## 依赖项

### 新增依赖

```toml
[project]
dependencies = [
    ...
    "websockets>=14.0",
]
```

### 安装

```bash
# 开发环境
pip install websockets

# 或使用 uv
uv pip install websockets

# Docker 构建会自动安装
```

## 测试

### 单元测试（待补充）

```bash
pytest tests/test_websocket_manager.py
pytest tests/test_websocket_client.py
```

### 集成测试

1. 启动 orchestrator：
   ```bash
   python -m orchestrator.main
   ```

2. 启动 WebSocket worker：
   ```bash
   export WORKER_USE_WEBSOCKET=true
   export ORCHESTRATOR_BASE_URL=http://localhost:8000
   python -m worker.main
   ```

3. 提交任务：
   ```bash
   curl -X POST http://localhost:8000/api/v1/tasks \
     -H "Content-Type: application/yaml" \
     --data-binary @templates/inference_vllm_llama.yaml
   ```

4. 检查日志确认通过 WebSocket 传输

## 总结

WebSocket 长连接功能提供了一种可选的、低延迟的 worker-orchestrator 通信方式，适合需要简化架构或追求极致性能的场景。同时保持了与现有 Redis 方式的完全兼容性，可以根据实际需求灵活选择。

# Worker API Enhancement - WebSocket Support

## 概述

增强了 FastAPI 的 `/workers` 和 `/workers/{worker_id}` 接口，使其能够同时展示通过 Redis 注册的 worker 和通过 WebSocket 连接的 worker。

## 改进内容

### 1. `/workers` 接口增强

**之前:** 只返回从 Redis 注册的 worker 列表

**现在:** 返回完整的 worker 信息，包括：
- Redis 注册的 worker
- WebSocket 连接的 worker
- 同时使用 Redis 和 WebSocket 的 worker

#### 返回格式

```json
{
  "total": 3,
  "redis_only": 1,
  "websocket_only": 1,
  "both": 1,
  "workers": [
    {
      "worker_id": "worker-001",
      "status": "IDLE",
      "transport": "redis+websocket",
      "websocket": {
        "connected": true,
        "connected_at": 1697520000.0,
        "last_seen": 1697520100.0,
        "tasks_sent": 5,
        "events_received": 10,
        "connected_seconds": 100.5
      },
      // ... 其他 Redis 字段
    },
    {
      "worker_id": "worker-002",
      "status": "RUNNING",
      "transport": "redis",
      "websocket": {
        "connected": false
      },
      // ... 其他 Redis 字段
    },
    {
      "worker_id": "worker-003",
      "status": "CONNECTED",
      "transport": "websocket",
      "websocket": {
        "connected": true,
        "connected_at": 1697520050.0,
        "last_seen": 1697520150.0,
        "tasks_sent": 2,
        "events_received": 5,
        "connected_seconds": 100.0
      }
    }
  ]
}
```

#### 字段说明

- `total`: 总 worker 数量
- `redis_only`: 仅使用 Redis 注册的 worker 数量
- `websocket_only`: 仅使用 WebSocket 连接的 worker 数量
- `both`: 同时使用 Redis 和 WebSocket 的 worker 数量
- `workers`: worker 列表数组

##### Worker 对象字段

- `worker_id`: Worker 唯一标识
- `status`: Worker 状态（IDLE/RUNNING/CONNECTED/UNKNOWN）
- `transport`: 传输方式
  - `"redis"`: 仅 Redis 注册
  - `"websocket"`: 仅 WebSocket 连接
  - `"redis+websocket"`: 两者都使用
- `websocket`: WebSocket 连接信息
  - `connected`: 是否通过 WebSocket 连接
  - `connected_at`: 连接时间戳（仅在 connected=true 时）
  - `last_seen`: 最后活跃时间戳
  - `tasks_sent`: 通过 WebSocket 发送的任务数
  - `events_received`: 通过 WebSocket 接收的事件数
  - `connected_seconds`: 已连接时长（秒）

### 2. `/workers/{worker_id}` 接口增强

**之前:** 只返回 Redis 中的 worker 信息，如果 worker 不在 Redis 中则返回 404

**现在:** 返回 worker 的完整信息，包括 Redis 和 WebSocket 状态

#### 行为变化

1. 如果 worker 在 Redis 中注册：返回 Redis 信息 + WebSocket 状态
2. 如果 worker 仅通过 WebSocket 连接：返回 WebSocket 信息
3. 如果 worker 既不在 Redis 也不在 WebSocket：返回 404

#### 返回格式示例

**Redis + WebSocket:**
```json
{
  "worker_id": "worker-001",
  "status": "IDLE",
  "transport": "redis+websocket",
  "stale": false,
  "websocket": {
    "connected": true,
    "connected_at": 1697520000.0,
    "last_seen": 1697520100.0,
    "tasks_sent": 5,
    "events_received": 10,
    "connected_seconds": 100.5
  },
  // ... 其他 Redis 字段（hardware, env, tags 等）
}
```

**仅 WebSocket:**
```json
{
  "worker_id": "worker-003",
  "status": "CONNECTED",
  "transport": "websocket",
  "websocket": {
    "connected": true,
    "connected_at": 1697520050.0,
    "last_seen": 1697520150.0,
    "tasks_sent": 2,
    "events_received": 5,
    "connected_seconds": 100.0
  }
}
```

## 使用示例

### 获取所有 worker 列表

```bash
curl http://localhost:8000/workers
```

### 获取特定 worker 详情

```bash
curl http://localhost:8000/workers/worker-001
```

### 过滤仅显示 WebSocket 连接的 worker

```bash
curl http://localhost:8000/workers | jq '.workers[] | select(.websocket.connected == true)'
```

### 统计各种传输方式的 worker

```bash
curl http://localhost:8000/workers | jq '{redis_only, websocket_only, both, total}'
```

## 测试

使用提供的测试脚本验证功能：

```bash
python scripts/test_worker_endpoints.py
```

或指定其他地址：

```bash
python scripts/test_worker_endpoints.py http://your-server:8000
```

## 兼容性

此改进向后兼容：
- 现有依赖 `/workers` 接口的客户端仍可正常工作
- 返回格式扩展，不会破坏现有字段
- WebSocket 为可选功能，不影响仅使用 Redis 的部署

## 技术实现

### 修改的文件

- `orchestrator/main.py`: 更新 `/workers` 和 `/workers/{worker_id}` 接口

### 依赖的组件

- `WebSocketManager`: 管理 WebSocket 连接，提供连接状态和统计信息
- `worker_cls.py`: Redis worker 数据模型和辅助函数

### 主要逻辑

1. **列表接口 (`/workers`)**:
   - 从 Redis 获取所有注册的 worker
   - 从 WebSocketManager 获取所有 WebSocket 连接
   - 合并两个来源的数据
   - 标记每个 worker 的传输方式
   - 添加 WebSocket 连接统计

2. **详情接口 (`/workers/{worker_id}`)**:
   - 尝试从 Redis 获取 worker 信息
   - 检查 worker 是否有 WebSocket 连接
   - 如果两者都不存在，返回 404
   - 合并可用的信息并返回

## 优势

1. **完整性**: 提供所有 worker 的完整视图，无论使用何种传输方式
2. **灵活性**: 支持 worker 使用 Redis、WebSocket 或两者兼用
3. **可观测性**: 清晰显示每个 worker 的连接状态和活跃度
4. **兼容性**: 不破坏现有 API 契约
5. **扩展性**: 为未来支持更多传输方式打下基础

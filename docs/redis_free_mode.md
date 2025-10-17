# Redis-Free Worker Mode

## 概述

kv.run 现在支持 Worker 在 WebSocket 模式下完全脱离 Redis 运行。这使得部署更加灵活，特别适合以下场景：

- **边缘计算环境**：Worker 部署在边缘节点，无需本地 Redis 实例
- **简化部署**：减少基础设施依赖，降低运维复杂度
- **安全隔离**：Worker 只需连接 Orchestrator WebSocket，无需访问 Redis

## 架构变更

### 传统 Redis 模式
```
┌──────────────┐      ┌───────┐      ┌──────────────┐
│ Orchestrator │◄────►│ Redis │◄────►│    Worker    │
└──────────────┘      └───────┘      └──────────────┘
                          ▲
                          │
                    Pub/Sub + KV
```

### WebSocket 无 Redis 模式
```
┌──────────────┐                    ┌──────────────┐
│ Orchestrator │◄─── WebSocket ────►│    Worker    │
│   (+ Redis)  │                    │  (No Redis)  │
└──────────────┘                    └──────────────┘
       ▲
       │ Redis (仅 Orchestrator 使用)
       ▼
   ┌───────┐
   │ Redis │
   └───────┘
```

## 配置说明

### Worker 配置

启用 WebSocket 模式并移除 Redis 依赖：

```bash
# 必需：启用 WebSocket 传输
export WORKER_USE_WEBSOCKET=true

# 必需：Orchestrator 基础 URL
export ORCHESTRATOR_BASE_URL=http://orchestrator-host:8000

# 可选：移除 REDIS_URL（WebSocket 模式下不需要）
# export REDIS_URL=redis://localhost:6379/0  # 可以注释掉

# Worker 标识和配置
export WORKER_ID=worker-001
export WORKER_TAGS=gpu,inference
export WORKER_COST_PER_HOUR=3.5

# 其他配置
export HEARTBEAT_INTERVAL_SEC=30
export LOG_LEVEL=INFO
```

### Orchestrator 配置

Orchestrator 仍然需要 Redis（用于任务存储和状态管理）：

```bash
# Redis 配置（Orchestrator 必需）
export REDIS_URL=redis://redis-host:6379/0

# Orchestrator 配置
export ORCHESTRATOR_BASE_URL=http://0.0.0.0:8000
export LOG_LEVEL=INFO

# 可选：认证令牌
export ORCHESTRATOR_TOKEN=your-secure-token
```

## 功能支持

### ✅ 完整支持（无 Redis）

| 功能 | WebSocket 模式 | 说明 |
|------|---------------|------|
| Worker 注册 | ✅ | 通过 WebSocket 发送注册事件 |
| 心跳机制 | ✅ | 定期通过 WebSocket 发送心跳 |
| 任务接收 | ✅ | Orchestrator 通过 WebSocket 推送任务 |
| 任务状态上报 | ✅ | Worker 通过 WebSocket 发送状态事件 |
| 优雅退出 | ✅ | 发送 UNREGISTER 事件 |
| 错误处理 | ✅ | 自动重连机制 |
| 元数据同步 | ✅ | 实时 metrics 和 hardware 信息 |

### 🔄 自动处理

- **重连机制**：WebSocket 断开后自动重连（指数退避）
- **状态缓存**：连接断开期间缓存事件，重连后同步
- **并发控制**：与 Redis 模式相同的并发处理能力

## 部署示例

### Docker Compose

```yaml
version: '3.8'

services:
  orchestrator:
    build: ./orchestrator
    environment:
      - REDIS_URL=redis://redis:6379/0
      - ORCHESTRATOR_BASE_URL=http://0.0.0.0:8000
    ports:
      - "8000:8000"
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  worker-websocket:
    build: ./worker
    environment:
      # WebSocket 模式 - 无需 Redis
      - WORKER_USE_WEBSOCKET=true
      - ORCHESTRATOR_BASE_URL=http://orchestrator:8000
      - WORKER_ID=ws-worker-001
      - WORKER_TAGS=gpu,inference
      - WORKER_COST_PER_HOUR=3.5
    deploy:
      replicas: 3
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: worker-websocket
spec:
  replicas: 5
  selector:
    matchLabels:
      app: worker
      mode: websocket
  template:
    metadata:
      labels:
        app: worker
        mode: websocket
    spec:
      containers:
      - name: worker
        image: kv.run/worker:latest
        env:
        - name: WORKER_USE_WEBSOCKET
          value: "true"
        - name: ORCHESTRATOR_BASE_URL
          value: "http://orchestrator-service:8000"
        - name: WORKER_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: WORKER_COST_PER_HOUR
          value: "3.5"
        # 注意：无需 REDIS_URL
```

## 代码实现

### Worker Transport 抽象

系统引入了 `WorkerTransport` 抽象类：

```python
# worker/worker_transport.py

class WorkerTransport(ABC):
    """Transport abstraction for worker-orchestrator communication."""
    
    @abstractmethod
    def register(self, status, started_at, pid, env, hardware, tags, ...):
        pass
    
    @abstractmethod
    def heartbeat(self, ts, metrics, ttl_sec):
        pass
    
    @abstractmethod
    def task_started/succeeded/failed(self, task_id, ...):
        pass
```

### 实现类

1. **RedisTransport**：传统 Redis Pub/Sub + KV 模式
2. **WebSocketTransport**：纯 WebSocket 模式，无 Redis 依赖

```python
# worker/main.py

if cfg.use_websocket:
    # WebSocket 模式 - 无 Redis
    transport = WebSocketTransport(cfg.worker_id, websocket_client)
    rds = None  # Redis 可选
else:
    # Redis 模式
    rds = redis.from_url(redis_url)
    transport = RedisTransport(rds, cfg.worker_id)
```

## 性能考虑

### WebSocket vs Redis Pub/Sub

| 指标 | Redis Pub/Sub | WebSocket |
|------|--------------|-----------|
| 延迟 | ~1-5ms | ~5-20ms |
| 吞吐量 | 高 | 中高 |
| 连接开销 | 低 | 中 |
| 扩展性 | 优秀 | 良好 |
| 依赖 | Redis 必需 | 无额外依赖 |

### 适用场景

**推荐使用 WebSocket 模式：**
- Worker 数量 < 100
- 任务提交频率 < 1000 tasks/s
- 需要简化部署
- 边缘计算场景

**推荐使用 Redis 模式：**
- Worker 数量 > 100
- 任务提交频率 > 1000 tasks/s
- 需要最低延迟
- 已有 Redis 基础设施

## 故障排查

### Worker 无法连接

```bash
# 检查 Orchestrator URL
curl http://orchestrator-host:8000/health

# 检查 WebSocket 端点
wscat -c ws://orchestrator-host:8000/ws/worker/test-worker
```

### 事件丢失

WebSocket 模式在连接断开期间可能丢失部分事件。系统提供：

1. **心跳超时检测**：Orchestrator 检测 Worker 离线
2. **任务重调度**：自动将任务重新分配给其他 Worker
3. **状态同步**：重连后同步状态

### 日志查看

```bash
# Worker 日志
tail -f /var/log/worker.log | grep -i websocket

# Orchestrator 日志
tail -f /var/log/orchestrator.log | grep -i "ws/worker"
```

## 迁移指南

### 从 Redis 模式迁移到 WebSocket

1. **更新 Worker 配置**：
   ```bash
   export WORKER_USE_WEBSOCKET=true
   export ORCHESTRATOR_BASE_URL=http://your-orchestrator:8000
   # 移除或注释 REDIS_URL
   ```

2. **安装 WebSocket 依赖**：
   ```bash
   pip install websockets
   ```

3. **重启 Worker**：
   ```bash
   python -m worker.main
   ```

4. **验证连接**：
   ```bash
   curl http://your-orchestrator:8000/ws/stats
   ```

### 混合模式

可以同时运行 Redis 和 WebSocket Worker：

```yaml
services:
  worker-redis:
    environment:
      - REDIS_URL=redis://redis:6379/0
      # WORKER_USE_WEBSOCKET 未设置，使用 Redis

  worker-websocket:
    environment:
      - WORKER_USE_WEBSOCKET=true
      - ORCHESTRATOR_BASE_URL=http://orchestrator:8000
      # 无需 REDIS_URL
```

## 安全建议

1. **使用 TLS**：生产环境启用 `wss://`
   ```bash
   export ORCHESTRATOR_BASE_URL=https://orchestrator:8443
   ```

2. **认证令牌**：
   ```bash
   export ORCHESTRATOR_TOKEN=your-secure-token
   ```

3. **网络隔离**：
   - Worker 只需访问 Orchestrator WebSocket 端口
   - Orchestrator 访问 Redis（内部网络）

## 未来增强

- [ ] 支持 Worker 端事件队列（离线缓冲）
- [ ] WebSocket 连接池（多路复用）
- [ ] gRPC 传输支持
- [ ] 端到端加密（E2E）

## 参考资料

- [WebSocket Implementation](./WEBSOCKET_IMPLEMENTATION.md)
- [WebSocket Transport](./websocket_transport.md)
- [Worker Configuration](../worker/config.py)
- [Transport Abstraction](../worker/worker_transport.py)

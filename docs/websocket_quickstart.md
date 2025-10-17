# WebSocket 快速开始指南

## 5 分钟快速体验 WebSocket 长连接

### 前置条件

```bash
# 安装依赖
pip install websockets

# 或使用 uv
uv pip install websockets
```

### 方式 1: 本地测试（单机）

#### 步骤 1: 启动 Orchestrator

```bash
# 终端 1
cd /Users/kaleb/Documents/labs/kv.run

export REDIS_URL=redis://localhost:6379/0
export RESULTS_DIR=./results_host
export LOG_LEVEL=INFO

python -m orchestrator.main
```

等待看到：
```
INFO: Connected to Redis: redis://localhost:6379/0
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8000
```

#### 步骤 2: 启动 WebSocket Worker

```bash
# 终端 2
cd /Users/kaleb/Documents/labs/kv.run

# 启用 WebSocket 模式
export WORKER_USE_WEBSOCKET=true
export ORCHESTRATOR_BASE_URL=http://localhost:8000

# Worker 基础配置
export WORKER_ID=worker-ws-test-001
export REDIS_URL=redis://localhost:6379/0
export WORKER_COST_PER_HOUR=3.5
export WORKER_TAGS=test,websocket
export RESULTS_DIR=./results_workers
export LOG_LEVEL=INFO

python -m worker.main
```

预期日志：
```
INFO: Starting runner with WebSocket transport
INFO: Connecting to orchestrator via WebSocket: ws://localhost:8000/ws/worker/worker-ws-test-001
INFO: WebSocket connected successfully
```

#### 步骤 3: 提交测试任务

```bash
# 终端 3
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/yaml" \
  --data-binary @templates/inference_vllm_llama.yaml
```

#### 步骤 4: 验证 WebSocket 通信

在 orchestrator 日志中查找：
```
INFO: Worker worker-ws-test-001 connected via WebSocket
INFO: Sent task task-xxx to worker worker-ws-test-001 via WebSocket
```

在 worker 日志中查找：
```
INFO: Received task task-xxx (type=inference, no-parent)
INFO: Task task-xxx completed successfully
```

#### 步骤 5: 检查连接状态

```bash
curl http://localhost:8000/ws/stats | jq
```

输出：
```json
{
  "total_connections": 1,
  "workers": {
    "worker-ws-test-001": {
      "connected_at": 1697365800.0,
      "last_seen": 1697365900.0,
      "tasks_sent": 1,
      "events_received": 3,
      "connected_seconds": 100.0
    }
  }
}
```

### 方式 2: Docker Compose（推荐）

#### 步骤 1: 构建镜像

```bash
# 构建 orchestrator
docker build -t kv-orchestrator -f Dockerfile.orchestrator .

# 构建 worker
docker build -t kv-worker -f Dockerfile.worker .
```

#### 步骤 2: 启动服务

```bash
docker-compose -f docker-compose.websocket.yml up -d
```

#### 步骤 3: 查看日志

```bash
# Orchestrator
docker-compose -f docker-compose.websocket.yml logs -f orchestrator

# WebSocket Worker
docker-compose -f docker-compose.websocket.yml logs -f worker-websocket-1

# Redis Worker
docker-compose -f docker-compose.websocket.yml logs -f worker-redis-1
```

#### 步骤 4: 提交任务

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/yaml" \
  --data-binary @templates/inference_vllm_llama.yaml
```

#### 步骤 5: 检查状态

```bash
# WebSocket 连接
curl http://localhost:8000/ws/stats

# 所有 Workers
curl http://localhost:8000/workers
```

### 对比测试：Redis vs WebSocket

#### 测试 1: 启动延迟

```bash
# Redis 模式
time docker-compose up -d worker-redis-1
# 预期：2-3 秒

# WebSocket 模式
time docker-compose up -d worker-websocket-1
# 预期：2-3 秒（相当）
```

#### 测试 2: 任务延迟

```bash
# 提交任务并测量端到端延迟
time curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/yaml" \
  --data-binary @templates/inference_vllm_llama.yaml
```

查看日志中的时间戳：
- `dispatched_at`: 任务分发时间
- `started_at`: Worker 接收时间
- 延迟 = started_at - dispatched_at

典型结果：
- Redis: 5-20 ms
- WebSocket: 1-5 ms

#### 测试 3: 重连速度

```bash
# 重启 orchestrator
docker-compose restart orchestrator

# 观察 worker 日志
docker-compose logs -f worker-websocket-1
```

预期：5-10 秒内自动重连

### 故障排查

#### 问题 1: Worker 无法连接

```bash
# 症状
ERROR: Failed to connect WebSocket: Connection refused

# 检查
curl http://localhost:8000/healthz

# 解决
# 1. 确认 orchestrator 已启动
# 2. 检查 ORCHESTRATOR_BASE_URL 是否正确
# 3. 检查防火墙设置
```

#### 问题 2: 任务不执行

```bash
# 检查 worker 是否注册
curl http://localhost:8000/workers | jq '.[] | select(.worker_id == "worker-ws-test-001")'

# 检查 WebSocket 连接
curl http://localhost:8000/ws/stats

# 查看 orchestrator 日志
docker-compose logs orchestrator | grep "worker-ws-test-001"
```

#### 问题 3: 频繁断连

```bash
# 症状
WARNING: WebSocket connection closed, will reconnect

# 可能原因
# 1. Orchestrator 重启
# 2. 网络不稳定
# 3. 负载过高

# 临时解决：切换到 Redis 模式
export WORKER_USE_WEBSOCKET=false
```

### 性能测试

#### 并发任务测试

```bash
# 提交 100 个任务
for i in {1..100}; do
  curl -X POST http://localhost:8000/api/v1/tasks \
    -H "Content-Type: application/yaml" \
    --data-binary @templates/inference_vllm_llama.yaml &
done
wait

# 查看完成情况
curl http://localhost:8000/ws/stats
```

#### 连接稳定性测试

```bash
# 运行 1 小时
timeout 3600 docker-compose logs -f worker-websocket-1 | grep "disconnected"

# 预期：0 次断连（正常情况下）
```

### 清理

```bash
# 停止所有服务
docker-compose -f docker-compose.websocket.yml down

# 删除数据
rm -rf results_host results_workers

# 清理 Redis
redis-cli FLUSHALL
```

## 下一步

- 📖 阅读完整文档：[`docs/websocket_transport.md`](./websocket_transport.md)
- 🔧 查看配置示例：[`worker/.env.websocket.example`](../worker/.env.websocket.example)
- 🐳 查看 Docker 配置：[`docker-compose.websocket.yml`](../docker-compose.websocket.yml)
- 📝 查看实现细节：[`docs/WEBSOCKET_IMPLEMENTATION.md`](./WEBSOCKET_IMPLEMENTATION.md)

## 常见问题

**Q: 必须使用 WebSocket 吗？**  
A: 不，WebSocket 是可选的。不启用时自动使用 Redis Pub/Sub。

**Q: 可以混合使用吗？**  
A: 可以！同一 orchestrator 可以同时服务 WebSocket 和 Redis worker。

**Q: WebSocket 更快吗？**  
A: 延迟稍低（1-5ms vs 5-20ms），但对大多数场景影响不大。

**Q: 哪种方式更稳定？**  
A: 两种方式都很稳定。Redis 更适合大规模部署，WebSocket 更适合小规模或低延迟场景。

**Q: 如何切换？**  
A: 修改 `WORKER_USE_WEBSOCKET` 环境变量并重启 worker 即可。

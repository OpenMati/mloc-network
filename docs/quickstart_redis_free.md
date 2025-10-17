# Quick Start: Redis-Free Worker Mode

快速体验 Worker 在无 Redis 环境下运行。

## 前置条件

```bash
# 安装 WebSocket 依赖
pip install websockets

# 确保 Orchestrator 可访问（需要 Redis）
# Orchestrator 仍需要 Redis 进行任务管理
```

## 方式一：本地测试

### 1. 启动 Orchestrator

```bash
# 终端 1: 启动 Redis
redis-server

# 终端 2: 启动 Orchestrator
cd orchestrator
export REDIS_URL=redis://localhost:6379/0
export LOG_LEVEL=INFO
python -m orchestrator.main
```

### 2. 启动 WebSocket Worker（无 Redis）

```bash
# 终端 3: 启动 Worker
cd worker
export WORKER_USE_WEBSOCKET=true
export ORCHESTRATOR_BASE_URL=http://localhost:8000
export WORKER_ID=my-ws-worker
export WORKER_TAGS=test,echo
export WORKER_COST_PER_HOUR=1.0
export LOG_LEVEL=INFO
# 注意：不设置 REDIS_URL

python -m worker.main
```

### 3. 提交测试任务

```bash
# 终端 4: 提交任务
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
    message: Hello Redis-Free World!
  tags:
    - test
"
```

### 4. 查看 Worker 连接

```bash
# 查看 WebSocket 连接状态
curl http://localhost:8000/ws/stats | jq
```

## 方式二：Docker Compose

创建 `docker-compose.redis-free.yml`:

```yaml
version: '3.8'

services:
  # Orchestrator (需要 Redis)
  orchestrator:
    build: ./orchestrator
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
      - LOG_LEVEL=INFO
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  # WebSocket Worker (无需 Redis)
  worker-ws:
    build: ./worker
    environment:
      - WORKER_USE_WEBSOCKET=true
      - ORCHESTRATOR_BASE_URL=http://orchestrator:8000
      - WORKER_ID=docker-ws-worker
      - WORKER_TAGS=docker,websocket
      - WORKER_COST_PER_HOUR=2.0
      - LOG_LEVEL=INFO
      # 注意：没有 REDIS_URL
    depends_on:
      - orchestrator
    deploy:
      replicas: 3  # 运行 3 个 Worker 实例
```

启动：

```bash
docker-compose -f docker-compose.redis-free.yml up
```

## 验证

### 检查 Worker 连接

```bash
curl http://localhost:8000/ws/stats
```

期望输出：

```json
{
  "total_connections": 3,
  "workers": {
    "docker-ws-worker-1": {
      "connected_at": 1697520000.0,
      "last_seen": 1697520030.0,
      "tasks_sent": 0,
      "events_received": 10,
      "connected_seconds": 30.0
    },
    ...
  }
}
```

### 提交并查询任务

```bash
# 提交任务
TASK_ID=$(curl -X POST http://localhost:8000/api/v1/tasks \
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
    message: Hello Redis-Free World!
  tags:
    - test
" | jq -r '.[0].task_id')

# 查询任务状态
curl http://localhost:8000/api/v1/tasks/$TASK_ID | jq
```

## 日志验证

### Worker 日志应显示

```
INFO - Worker using WebSocket transport (Redis-free mode)
INFO - Starting runner with WebSocket transport
INFO - WebSocket connected successfully
INFO - Received task abc123 (type=echo, no-parent)
INFO - Task abc123 completed successfully
```

### 不应出现

```
✗ 连接 Redis 错误
✗ Redis URL 未配置
✗ redis.exceptions.*
```

## 对比测试

### Redis 模式 Worker

```bash
# 同时运行 Redis 模式的 Worker
cd worker
export REDIS_URL=redis://localhost:6379/0
export WORKER_ID=redis-worker
export WORKER_TAGS=redis,test
export WORKER_COST_PER_HOUR=1.0
# 不设置 WORKER_USE_WEBSOCKET

python -m worker.main
```

### 查看混合模式

```bash
# Redis Worker 不会出现在 WebSocket stats 中
curl http://localhost:8000/ws/stats

# 但会出现在 Worker 列表中
curl http://localhost:8000/api/v1/workers | jq
```

## 常见问题

### Q: Worker 无法连接？

**A:** 检查 Orchestrator URL 和网络连通性：

```bash
# 测试连通性
curl http://localhost:8000/health

# 检查 WebSocket 端点
wscat -c ws://localhost:8000/ws/worker/test
```

### Q: 任务没有被分配？

**A:** 检查 Worker tags 是否匹配：

```bash
# 查看 Worker 状态
curl http://localhost:8000/api/v1/workers | jq '.[] | {id, tags, status}'

# 确保任务 tags 包含在 Worker tags 中
```

### Q: WebSocket 频繁断开？

**A:** 可能是防火墙或负载均衡器问题：

```bash
# 增加心跳间隔
export HEARTBEAT_INTERVAL_SEC=60

# 检查 WebSocket 超时配置
```

## 性能测试

### 简单压测

```bash
# 提交 100 个任务
for i in {1..100}; do
  curl -X POST http://localhost:8000/api/v1/tasks \
    -H "Content-Type: text/plain" \
    -d "
apiVersion: v1
kind: Task
metadata:
  name: test-echo-$i
spec:
  taskType: echo
  resources:
    replicas: 1
    hardware:
      cpu: \"1\"
      memory: \"1Gi\"
  input:
    message: Test $i
  tags:
    - test
" &
done
wait

# 监控完成情况
watch -n 1 'curl -s http://localhost:8000/api/v1/tasks | jq ".[] | select(.status==\"DONE\") | .task_id" | wc -l'
```

## 清理

```bash
# Docker Compose
docker-compose -f docker-compose.redis-free.yml down -v

# 本地进程
pkill -f "worker.main"
pkill -f "orchestrator.main"
redis-cli shutdown
```

## 下一步

- 阅读 [详细文档](./redis_free_mode.md)
- 查看 [实现细节](./REDIS_FREE_IMPLEMENTATION.md)
- 运行 [自动化测试](../scripts/test_redis_free.py)

---

**提示**: WebSocket 模式适合 < 100 Worker 的部署。大规模部署请使用 Redis 模式。

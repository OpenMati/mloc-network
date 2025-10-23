#!/bin/bash
# 
# 启动WebSocket模式Worker（无Redis）
# 
# 用法:
#   ./start_websocket_worker.sh [worker_id] [orchestrator_url]
#
# 示例:
#   ./start_websocket_worker.sh my-worker ws://localhost:8000/ws/worker
#

set -e

# 默认配置
WORKER_ID=${1:-"ws-worker-$(date +%s)"}
ORCHESTRATOR_URL=${2:-"ws://localhost:8000/ws/worker"}
LOG_LEVEL=${LOG_LEVEL:-"INFO"}
RESULTS_DIR=${RESULTS_DIR:-"./results_workers"}
WORKER_TAGS=${WORKER_TAGS:-"websocket,sdk"}

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   WebSocket Worker 启动脚本${NC}"
echo -e "${BLUE}   (无需Redis)${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到python3${NC}"
    exit 1
fi

# 检查websockets包
if ! python3 -c "import websockets" 2>/dev/null; then
    echo -e "${YELLOW}警告: websockets包未安装${NC}"
    echo -e "${YELLOW}正在安装...${NC}"
    pip install websockets
fi

# 检查Orchestrator连接
echo -e "${BLUE}检查Orchestrator连接...${NC}"
HTTP_URL=$(echo "$ORCHESTRATOR_URL" | sed 's/ws:/http:/' | sed 's|/ws/worker||')

if curl -s -f "${HTTP_URL}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Orchestrator可访问: ${HTTP_URL}${NC}"
else
    echo -e "${RED}✗ 无法连接到Orchestrator: ${HTTP_URL}${NC}"
    echo -e "${YELLOW}请确保Orchestrator正在运行${NC}"
    echo -e "${YELLOW}提示: cd orchestrator && python -m orchestrator.main${NC}"
    exit 1
fi

# 创建结果目录
mkdir -p "$RESULTS_DIR"

# 显示配置
echo ""
echo -e "${BLUE}Worker配置:${NC}"
echo -e "  Worker ID:        ${GREEN}${WORKER_ID}${NC}"
echo -e "  传输模式:         ${GREEN}WebSocket (无Redis)${NC}"
echo -e "  Orchestrator URL: ${GREEN}${ORCHESTRATOR_URL}${NC}"
echo -e "  日志级别:         ${GREEN}${LOG_LEVEL}${NC}"
echo -e "  结果目录:         ${GREEN}${RESULTS_DIR}${NC}"
echo -e "  Worker标签:       ${GREEN}${WORKER_TAGS}${NC}"
echo ""

# 导出环境变量
export WORKER_ID
export ORCHESTRATOR_URL
export USE_WEBSOCKET=true
export LOG_LEVEL
export RESULTS_DIR
export WORKER_TAGS

# 查找示例脚本
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLE_SCRIPT="${SCRIPT_DIR}/example_06_websocket_mode.py"

if [ ! -f "$EXAMPLE_SCRIPT" ]; then
    echo -e "${YELLOW}警告: 未找到示例脚本 ${EXAMPLE_SCRIPT}${NC}"
    echo -e "${YELLOW}使用自定义worker脚本...${NC}"
    
    # 创建临时worker脚本
    TEMP_WORKER="/tmp/websocket_worker_${WORKER_ID}.py"
    cat > "$TEMP_WORKER" << 'EOF'
from pathlib import Path
from typing import Any, Dict
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from mloc_sdk import BaseExecutor, WorkerSDK

class SimpleExecutor(BaseExecutor):
    name = "websocket-executor"
    description = "WebSocket模式简单执行器"
    version = "1.0.0"
    
    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        message = task_spec.get("message", "Hello WebSocket!")
        
        result = {
            "message": message,
            "mode": "websocket",
            "redis_required": False,
            "worker_id": os.getenv("WORKER_ID")
        }
        
        self.save_json(output_dir / "result.json", result)
        print(f"处理任务: {message}")
        
        return result

if __name__ == "__main__":
    sdk = WorkerSDK(
        worker_id=os.getenv("WORKER_ID"),
        orchestrator_url=os.getenv("ORCHESTRATOR_URL"),
        use_websocket=True,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        tags=os.getenv("WORKER_TAGS", "").split(","),
    )
    
    sdk.register_executor(SimpleExecutor())
    
    print("=" * 60)
    print("WebSocket Worker 已启动")
    print("按 Ctrl+C 停止")
    print("=" * 60)
    
    sdk.run()
EOF
    
    WORKER_SCRIPT="$TEMP_WORKER"
else
    WORKER_SCRIPT="$EXAMPLE_SCRIPT"
fi

# 启动worker
echo -e "${GREEN}启动Worker...${NC}"
echo -e "${YELLOW}按 Ctrl+C 停止${NC}"
echo ""

# 使用trap捕获退出信号
trap 'echo -e "\n${YELLOW}停止Worker...${NC}"; exit 0' INT TERM

# 运行worker
python3 "$WORKER_SCRIPT"

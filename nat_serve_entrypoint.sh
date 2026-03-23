#!/bin/bash
# -----------------------------------------------------------------------
# nat_serve_entrypoint.sh
# 通用 NAT Agent Serve 启动脚本
# 读取环境变量 WORKFLOW_FILE 和 SERVE_PORT，启动对应的 nat serve 服务。
#
# 用法（docker-compose command）：
#   command: ["/app/nat_serve_entrypoint.sh"]
# 配合环境变量：
#   WORKFLOW_FILE=workflow_agent_life.yaml
#   SERVE_PORT=8101
# -----------------------------------------------------------------------

set -e

WORKFLOW_FILE="${WORKFLOW_FILE:-workflow_rag.yaml}"
SERVE_PORT="${SERVE_PORT:-8000}"
SERVE_HOST="${SERVE_HOST:-0.0.0.0}"

echo "================================================"
echo "  NAT Agent Server 启动"
echo "  Workflow: ${WORKFLOW_FILE}"
echo "  Port:     ${SERVE_PORT}"
echo "  Host:     ${SERVE_HOST}"
echo "================================================"

# 等待 Milvus 健康（若 MILVUS_HOST 已设置）
if [ -n "${MILVUS_HOST}" ]; then
    echo "等待 Milvus (${MILVUS_HOST}:${MILVUS_PORT:-19530}) 就绪..."
    for i in $(seq 1 30); do
        if curl -sf "http://${MILVUS_HOST}:9091/healthz" > /dev/null 2>&1; then
            echo "Milvus 已就绪"
            break
        fi
        echo "  等待中 (${i}/30)..."
        sleep 5
    done
fi

exec nat serve \
    --config_file "${WORKFLOW_FILE}" \
    --port "${SERVE_PORT}" \
    --host "${SERVE_HOST}"

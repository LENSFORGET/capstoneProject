#!/bin/bash
# -----------------------------------------------------------------------
# ingest_all.sh
# 批量将 /app/PDF/ 目录中的所有保险产品手册 PDF 向量化入库到 Milvus。
#
# 用法（在 nat-app 容器中运行）：
#   docker exec -it nat-app bash /app/ingest_all.sh
#
# 或在 docker exec 中使用 --no-mineru 快速模式：
#   PDF_OPTS="--no-mineru" bash /app/ingest_all.sh
#
# 环境变量：
#   PDF_DIR     - PDF 目录路径（默认：/app/PDF）
#   PDF_OPTS    - 额外的 rag_ingest.py 参数（如 "--no-mineru"）
#   CLEAR_FIRST - 设为 "1" 则首个 PDF 前清空 collection（默认：1）
# -----------------------------------------------------------------------

set -e

PDF_DIR="${PDF_DIR:-/app/PDF}"
PDF_OPTS="${PDF_OPTS:-}"
CLEAR_FIRST="${CLEAR_FIRST:-1}"

echo "============================================================"
echo "  宏利保险知识库批量入库"
echo "  PDF 目录：${PDF_DIR}"
echo "  选项：${PDF_OPTS}"
echo "  首次清空：${CLEAR_FIRST}"
echo "============================================================"

# 检查目录是否存在
if [ ! -d "${PDF_DIR}" ]; then
    echo "错误：PDF 目录 '${PDF_DIR}' 不存在"
    exit 1
fi

# 统计 PDF 文件数量
PDF_COUNT=$(find "${PDF_DIR}" -name "*.pdf" -type f | wc -l)
echo "发现 ${PDF_COUNT} 个 PDF 文件"
echo ""

FIRST=1
PROCESSED=0
FAILED=0

for f in "${PDF_DIR}"/*.pdf; do
    [ -f "$f" ] || continue
    BASENAME=$(basename "$f")
    echo "------------------------------------------------------------"
    echo "[${PROCESSED}/${PDF_COUNT}] 处理：${BASENAME}"

    if [ "${FIRST}" -eq 1 ] && [ "${CLEAR_FIRST}" -eq 1 ]; then
        echo "  → 首个 PDF，清空已有 collection..."
        python /app/rag_ingest.py --pdf-path "$f" --clear --no-mineru ${PDF_OPTS} \
            && PROCESSED=$((PROCESSED + 1)) \
            || { echo "  警告：${BASENAME} 入库失败，继续下一个"; FAILED=$((FAILED + 1)); }
        FIRST=0
    else
        python /app/rag_ingest.py --pdf-path "$f" --no-mineru ${PDF_OPTS} \
            && PROCESSED=$((PROCESSED + 1)) \
            || { echo "  警告：${BASENAME} 入库失败，继续下一个"; FAILED=$((FAILED + 1)); }
    fi
done

echo ""
echo "============================================================"
echo "  批量入库完成"
echo "  成功：${PROCESSED} 个"
echo "  失败：${FAILED} 个"
echo "============================================================"
echo ""
echo "运行以下命令查看入库结果："
echo "  python /app/check_categories.py"

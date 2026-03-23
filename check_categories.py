"""
check_categories.py
-------------------
查询 Milvus 知识库，显示当前已入库的保险产品分类统计。
用于验证 rag_ingest.py 批量入库后的结果，并辅助调整 Agent 分类配置。

运行方式（在 nat-app 容器中）：
    python check_categories.py

依赖环境变量：
    MILVUS_HOST  - Milvus 主机（默认 localhost）
    MILVUS_PORT  - Milvus 端口（默认 19530）
"""

import os
import sys
from collections import defaultdict

from pymilvus import MilvusClient


COLLECTION_NAME = "insurance_docs"


def main():
    host = os.environ.get("MILVUS_HOST", "localhost")
    port = os.environ.get("MILVUS_PORT", "19530")
    uri = f"http://{host}:{port}"

    print(f"连接 Milvus：{uri}")
    try:
        client = MilvusClient(uri=uri)
    except Exception as e:
        print(f"连接失败：{e}")
        sys.exit(1)

    collections = client.list_collections()
    if COLLECTION_NAME not in collections:
        print(f"Collection '{COLLECTION_NAME}' 不存在，请先运行 rag_ingest.py 入库。")
        sys.exit(1)

    # 获取总数
    stats = client.get_collection_stats(COLLECTION_NAME)
    total = stats.get("row_count", 0)
    print(f"\n知识库总文档块数：{total}")
    print("=" * 60)

    # 查询所有文档的 source 字段（分批获取）
    source_counts = defaultdict(int)
    content_type_counts = defaultdict(int)
    BATCH = 1000
    offset = 0

    while True:
        try:
            results = client.query(
                collection_name=COLLECTION_NAME,
                filter="id >= 0",
                output_fields=["source", "content_type"],
                limit=BATCH,
                offset=offset,
            )
        except Exception as e:
            print(f"查询失败（offset={offset}）：{e}")
            break

        if not results:
            break

        for row in results:
            source = row.get("source", "unknown")
            ctype = row.get("content_type", "text")
            # 提取文件名（去掉 "pdf_mineru:" 或 "pdf_pypdf:" 前缀）
            if ":" in source:
                source_file = source.split(":", 1)[1]
            else:
                source_file = source
            source_counts[source_file] += 1
            content_type_counts[ctype] += 1

        offset += len(results)
        if len(results) < BATCH:
            break

    # 按类别分组显示
    CATEGORY_MAP = {
        "life": ("寿险", ["manu-term", "universal-life", "manucentury", "la-vie-2"]),
        "savings": ("储蓄与年金险", [
            "flexifortune", "genesis-centurion", "genesis", "harvest-saver",
            "manuglobal-saver", "manuleisure", "prestige-achiever",
            "prestige-preserver", "future-assure",
        ]),
        "medical": ("医疗险与VHIS", [
            "vhis", "manulife-first-vhis", "manulife-shelter", "manulife-supreme",
            "manulife-policy-services", "medical-referral", "prescribed-diagnostic",
            "prc-and-worldwide", "emergency-assistance", "list-of-designated",
            "the-list-of-designated",
        ]),
        "critical": ("危疾与综合保障", [
            "manupremier-protector", "whole-in-one-prime", "manudelight", "incapacity-care",
        ]),
    }

    print("\n按险种分类统计：")
    print("=" * 60)

    assigned = set()
    for cat_key, (cat_name, keywords) in CATEGORY_MAP.items():
        print(f"\n【{cat_name}】（Agent: {cat_key}）")
        cat_total = 0
        for source_file, count in sorted(source_counts.items()):
            if any(kw in source_file.lower() for kw in keywords):
                print(f"  {source_file:50s} {count:5d} 块")
                cat_total += count
                assigned.add(source_file)
        if cat_total == 0:
            print("  （暂无入库文档）")
        else:
            print(f"  {'小计':50s} {cat_total:5d} 块")

    # 未分类的
    unassigned = {k: v for k, v in source_counts.items() if k not in assigned}
    if unassigned:
        print("\n【未分类文档】（需手动检查并更新 CATEGORY_MAP）")
        for source_file, count in sorted(unassigned.items()):
            print(f"  {source_file:50s} {count:5d} 块")

    print("\n按内容类型统计：")
    print("=" * 60)
    for ctype, count in sorted(content_type_counts.items(), key=lambda x: -x[1]):
        print(f"  {ctype:20s} {count:5d} 块")

    print("\n" + "=" * 60)
    print("如需调整险种分类，请修改以下文件中的 CATEGORY_MAP：")
    print("  /app/rag_mcp.py")


if __name__ == "__main__":
    main()

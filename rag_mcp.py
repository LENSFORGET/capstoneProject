"""
rag_mcp.py
----------
基于 NAT MilvusRetriever + NVIDIA NIM Embedding 的 RAG 知识库 FastMCP 服务。
暴露以下工具供 NAT react_agent / 多 Agent 系统调用：
  - search_insurance(query, category)  : 在保险知识库中检索相关内容，支持按险种过滤
  - get_collection_stats()             : 查询知识库统计信息
  - list_insurance_categories()        : 列出知识库中已收录的保险产品分类

运行方式（NAT 通过 workflow_*.yaml 自动管理，通常不需手动运行）：
    python rag_mcp.py

依赖环境变量：
    NVIDIA_API_KEY  - NVIDIA NIM API 密钥（embedding + LLM 共用）
    MILVUS_HOST     - Milvus 主机（默认 localhost）
    MILVUS_PORT     - Milvus 端口（默认 19530）
    RAG_CATEGORY    - 可选：预设的险种过滤（专业 Agent 启动时注入，如 "life"）
"""

import asyncio
import logging
import os
from typing import Optional

from langchain_core.embeddings import Embeddings
from llama_index.embeddings.nvidia import NVIDIAEmbedding
from mcp.server.fastmcp import FastMCP
from pymilvus import MilvusClient

from nat.retriever.milvus.retriever import MilvusRetriever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# 常量配置
# -----------------------------------------------------------------------
COLLECTION_NAME = "insurance_docs"
EMBEDDING_MODEL = "nvidia/nv-embedqa-e5-v5"
NVIDIA_API_BASE = "https://integrate.api.nvidia.com/v1"
DEFAULT_TOP_K = 5

# 险种关键词映射 → 对应的 Milvus source 前缀过滤表达式
# key: 险种标识符, value: (中文名称, source 关键词列表)
CATEGORY_MAP: dict[str, tuple[str, list[str]]] = {
    "life": (
        "寿险",
        [
            "manu-term",
            "universal-life",
            "manucentury",
            "la-vie-2",
        ],
    ),
    "savings": (
        "储蓄与年金险",
        [
            "flexifortune",
            "genesis-centurion",
            "genesis",
            "harvest-saver",
            "manuglobal-saver",
            "manuleisure",
            "prestige-achiever",
            "prestige-preserver",
            "future-assure",
        ],
    ),
    "medical": (
        "医疗险与VHIS",
        [
            "vhis",
            "manulife-first-vhis",
            "manulife-shelter-vhis",
            "manulife-supreme",
            "manulife-policy-services",
            "medical-referral",
            "prescribed-diagnostic",
            "prc-and-worldwide-emergency",
            "emergency-assistance",
            "list-of-designated",
            "the-list-of-designated",
        ],
    ),
    "critical": (
        "危疾与综合保障",
        [
            "manupremier-protector",
            "whole-in-one-prime",
            "manudelight",
            "incapacity-care",
        ],
    ),
}

# 险种中文别名 → 标准键映射（用于 query 中的模糊匹配）
CATEGORY_ALIAS: dict[str, str] = {
    "寿险": "life",
    "人寿": "life",
    "定期寿险": "life",
    "万能寿险": "life",
    "终身寿险": "life",
    "life": "life",
    "储蓄": "savings",
    "年金": "savings",
    "退休": "savings",
    "储蓄险": "savings",
    "savings": "savings",
    "annuity": "savings",
    "医疗": "medical",
    "vhis": "medical",
    "健康险": "medical",
    "住院": "medical",
    "medical": "medical",
    "health": "medical",
    "危疾": "critical",
    "重疾": "critical",
    "重大疾病": "critical",
    "癌症": "critical",
    "critical": "critical",
    "综合保障": "critical",
}


# -----------------------------------------------------------------------
# LangChain Embeddings 适配器
# 将 LlamaIndex NVIDIAEmbedding 包装为 LangChain Embeddings 接口，
# 因为 NAT MilvusRetriever 内部使用 langchain_core.embeddings.Embeddings
# -----------------------------------------------------------------------
class NVIDIAEmbeddingAdapter(Embeddings):
    """将 llama_index NVIDIAEmbedding 包装为 LangChain Embeddings 接口。"""

    def __init__(self, nvidia_embedding: NVIDIAEmbedding) -> None:
        self._embedder = nvidia_embedding

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.get_text_embedding_batch(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embedder.get_text_embedding(text)

    async def aembed_query(self, text: str) -> list[float]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_query, text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_documents, texts)


# -----------------------------------------------------------------------
# 全局单例（延迟初始化，避免启动时连接失败）
# -----------------------------------------------------------------------
_retriever: MilvusRetriever | None = None
_milvus_client: MilvusClient | None = None
_nvidia_embedding: NVIDIAEmbeddingAdapter | None = None


def _get_retriever() -> tuple[MilvusRetriever, MilvusClient, NVIDIAEmbeddingAdapter]:
    """获取或初始化 MilvusRetriever 单例，返回 (retriever, client, embedder)。"""
    global _retriever, _milvus_client, _nvidia_embedding

    if _retriever is not None:
        return _retriever, _milvus_client, _nvidia_embedding

    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError("环境变量 NVIDIA_API_KEY 未设置，RAG 服务无法初始化。")

    host = os.environ.get("MILVUS_HOST", "localhost")
    port = os.environ.get("MILVUS_PORT", "19530")
    uri = f"http://{host}:{port}"

    logger.info("初始化 Milvus 客户端：%s", uri)
    _milvus_client = MilvusClient(uri=uri)

    logger.info("初始化 NVIDIA NIM Embedding：%s", EMBEDDING_MODEL)
    nvidia_emb = NVIDIAEmbedding(
        model=EMBEDDING_MODEL,
        api_key=api_key,
        base_url=NVIDIA_API_BASE,
    )
    _nvidia_embedding = NVIDIAEmbeddingAdapter(nvidia_emb)

    _retriever = MilvusRetriever(
        client=_milvus_client,
        embedder=_nvidia_embedding,
        content_field="text",
    )
    _retriever.bind(
        collection_name=COLLECTION_NAME,
        top_k=DEFAULT_TOP_K,
    )

    logger.info("MilvusRetriever 初始化完成，collection：%s", COLLECTION_NAME)
    return _retriever, _milvus_client, _nvidia_embedding


def _build_source_filter(category_key: str) -> Optional[str]:
    """
    根据险种键构建 Milvus 过滤表达式。
    返回形如 `(source like "pdf%manu-term%" or source like "pdf%universal-life%")` 的字符串。
    若 category_key 无效则返回 None（全库检索）。
    """
    if category_key not in CATEGORY_MAP:
        return None

    _, source_keywords = CATEGORY_MAP[category_key]
    conditions = [f'source like "%{kw}%"' for kw in source_keywords]
    return "(" + " or ".join(conditions) + ")"


def _resolve_category(category: str) -> Optional[str]:
    """
    将用户传入的 category 字符串解析为标准键（life/savings/medical/critical）。
    支持英文键、中文别名。若无法识别返回 None。
    """
    if not category:
        return None
    lower = category.lower().strip()
    # 直接匹配标准键
    if lower in CATEGORY_MAP:
        return lower
    # 中文别名匹配
    for alias, key in CATEGORY_ALIAS.items():
        if alias in category or alias == lower:
            return key
    return None


# -----------------------------------------------------------------------
# FastMCP 服务定义
# -----------------------------------------------------------------------
mcp = FastMCP("Insurance RAG")


@mcp.tool()
async def search_insurance(query: str, category: str = "") -> str:
    """
    在宏利保险知识库中检索与问题最相关的内容片段。
    支持按险种过滤，提高检索精准度。

    Args:
        query: 用户的保险相关问题或关键词，例如"重疾险怎么选""VHIS理赔流程"
        category: 险种分类过滤（可选）。支持：
            - "life" / "寿险" / "人寿"
            - "savings" / "储蓄" / "年金" / "退休"
            - "medical" / "医疗" / "vhis" / "健康险"
            - "critical" / "危疾" / "重疾"
            留空则检索全部保险产品知识库。
    """
    # 优先使用环境变量预设的险种（专业 Agent 启动时注入）
    effective_category = category or os.environ.get("RAG_CATEGORY", "")
    category_key = _resolve_category(effective_category)

    if category_key:
        cat_name = CATEGORY_MAP[category_key][0]
        logger.info("RAG 检索：query=%s, category=%s(%s)", query, category_key, cat_name)
    else:
        logger.info("RAG 检索（全库）：query=%s", query)

    try:
        retriever, client, embedder = _get_retriever()
    except Exception as exc:
        error_msg = f"RAG 服务初始化失败：{exc}"
        logger.error(error_msg)
        return error_msg

    # 构建增强查询（在 query 前添加险种上下文）
    if category_key:
        cat_name = CATEGORY_MAP[category_key][0]
        augmented_query = f"{cat_name} {query}"
    else:
        augmented_query = query

    # 尝试使用 Milvus 过滤表达式进行精准检索
    filter_expr = _build_source_filter(category_key) if category_key else None

    try:
        if filter_expr:
            # 直接使用 MilvusClient 进行带过滤的向量检索
            query_vector = await embedder.aembed_query(augmented_query)
            raw_results = client.search(
                collection_name=COLLECTION_NAME,
                data=[query_vector],
                limit=DEFAULT_TOP_K,
                filter=filter_expr,
                output_fields=["text", "title", "source", "url", "scraped_at", "content_type"],
            )
            # 若过滤后结果不足，回退到全库检索
            if not raw_results or not raw_results[0]:
                logger.info("分类过滤无结果，回退全库检索")
                result = await retriever.search(query=augmented_query)
                docs = result.results if result.results else []
                use_filtered = False
            else:
                docs = raw_results[0]
                use_filtered = True
        else:
            result = await retriever.search(query=augmented_query)
            docs = result.results if result.results else []
            use_filtered = False
    except Exception as exc:
        error_msg = f"检索失败：{exc}"
        logger.error(error_msg)
        return error_msg

    if not docs:
        return (
            "知识库中未找到相关内容。\n"
            "请确认知识库已建立：python rag_ingest.py --pdf-path PDF/<filename>.pdf"
        )

    # 格式化返回结果
    cat_label = f"[{CATEGORY_MAP[category_key][0]}] " if category_key else ""
    output_parts = [f"从{cat_label}保险知识库中检索到 {len(docs)} 条相关内容：\n"]

    for i, doc in enumerate(docs, 1):
        if use_filtered:
            # MilvusClient 直接搜索结果格式
            entity = doc.get("entity", doc)
            title = entity.get("title", "（无标题）")
            url = entity.get("url", "")
            source = entity.get("source", "manulife")
            content = entity.get("text", "")
        else:
            # MilvusRetriever 结果格式
            title = doc.metadata.get("title", "（无标题）")
            url = doc.metadata.get("url", "")
            source = doc.metadata.get("source", "manulife")
            content = doc.page_content

        output_parts.append(f"--- 第 {i} 条 ---")
        output_parts.append(f"标题：{title}")
        if url:
            output_parts.append(f"链接：{url}")
        output_parts.append(f"来源：{source}")
        output_parts.append(f"内容：{content}")
        output_parts.append("")

    return "\n".join(output_parts)


@mcp.tool()
def get_collection_stats() -> str:
    """
    查询保险知识库的统计信息，包括文档数量、collection 状态等。
    用于了解当前知识库是否已建立以及数据量大小。
    """
    try:
        _, client, _ = _get_retriever()
    except Exception as exc:
        return f"RAG 服务不可用：{exc}"

    try:
        collections = client.list_collections()

        if COLLECTION_NAME not in collections:
            return (
                f"知识库 collection '{COLLECTION_NAME}' 尚未创建。\n"
                "请运行：python rag_ingest.py --pdf-path PDF/<filename>.pdf"
            )

        stats = client.get_collection_stats(COLLECTION_NAME)
        row_count = stats.get("row_count", "未知")

        return (
            f"知识库状态：正常\n"
            f"Collection 名称：{COLLECTION_NAME}\n"
            f"文档块数量：{row_count}\n"
            f"Embedding 模型：{EMBEDDING_MODEL}\n"
            f"向量维度：1024\n"
            f"\n支持的险种分类：\n"
            + "\n".join(
                f"  - {key}: {name}"
                for key, (name, _) in CATEGORY_MAP.items()
            )
        )
    except Exception as exc:
        return f"查询统计信息失败：{exc}"


@mcp.tool()
def list_insurance_categories() -> str:
    """
    列出本知识库支持的保险产品分类及对应的产品列表。
    用于了解各专业 Agent 的职责范围。
    """
    lines = ["宏利保险知识库 - 险种分类说明：\n"]
    for key, (name, sources) in CATEGORY_MAP.items():
        lines.append(f"## {name}（category='{key}'）")
        lines.append(f"涵盖产品：{', '.join(sources)}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()

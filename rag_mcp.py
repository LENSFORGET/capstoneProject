"""
rag_mcp.py
----------
基于 NAT MilvusRetriever + NVIDIA NIM Embedding 的 RAG 知识库 FastMCP 服务。
暴露两个工具供 NAT react_agent 调用：
  - search_insurance(query) : 在保险知识库中检索相关内容
  - get_collection_stats()  : 查询知识库统计信息

运行方式（NAT 通过 workflow_rag.yaml 自动管理，通常不需手动运行）：
    python rag_mcp.py

依赖环境变量：
    NVIDIA_API_KEY  - NVIDIA NIM API 密钥（embedding + LLM 共用）
    MILVUS_HOST     - Milvus 主机（默认 localhost）
    MILVUS_PORT     - Milvus 端口（默认 19530）
"""

import asyncio
import logging
import os

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


# -----------------------------------------------------------------------
# LangChain Embeddings 适配器
# 将 LlamaIndex NVIDIAEmbedding 包装为 LangChain Embeddings 接口，
# 因为 NAT MilvusRetriever 内部使用 langchain_core.embeddings.Embeddings
# -----------------------------------------------------------------------
class NVIDIAEmbeddingAdapter(Embeddings):
    """
    将 llama_index NVIDIAEmbedding 包装为 LangChain Embeddings 接口，
    以兼容 NAT MilvusRetriever 所需的 embedder 类型。
    """

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


def _get_retriever() -> MilvusRetriever:
    """获取或初始化 MilvusRetriever 单例。"""
    global _retriever, _milvus_client

    if _retriever is not None:
        return _retriever

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
    embedder = NVIDIAEmbeddingAdapter(nvidia_emb)

    _retriever = MilvusRetriever(
        client=_milvus_client,
        embedder=embedder,
        content_field="text",
    )
    # 绑定默认参数：collection_name 和 top_k
    _retriever.bind(
        collection_name=COLLECTION_NAME,
        top_k=DEFAULT_TOP_K,
    )

    logger.info("MilvusRetriever 初始化完成，collection：%s", COLLECTION_NAME)
    return _retriever


# -----------------------------------------------------------------------
# FastMCP 服务定义
# -----------------------------------------------------------------------
mcp = FastMCP("Insurance RAG")


@mcp.tool()
async def search_insurance(query: str) -> str:
    """
    在小红书保险知识库中检索与问题最相关的内容片段。
    返回相关内容的文本，可直接用于回答保险相关问题。

    Args:
        query: 用户的保险相关问题或关键词，例如"重疾险怎么选""车险理赔流程"
    """
    logger.info("收到 RAG 检索请求：%s", query)

    try:
        retriever = _get_retriever()
    except Exception as exc:
        error_msg = f"RAG 服务初始化失败：{exc}"
        logger.error(error_msg)
        return error_msg

    try:
        result = await retriever.search(query=query)
    except Exception as exc:
        error_msg = f"检索失败：{exc}"
        logger.error(error_msg)
        return error_msg

    if not result.results:
        return "知识库中未找到相关内容。请先运行爬虫采集数据（nat run workflow_scraper.yaml），然后运行入库脚本（python rag_ingest.py）。"

    # 格式化返回结果
    output_parts = [f"从保险知识库中检索到 {len(result.results)} 条相关内容：\n"]
    for i, doc in enumerate(result.results, 1):
        title = doc.metadata.get("title", "（无标题）")
        url = doc.metadata.get("url", "")
        source = doc.metadata.get("source", "xiaohongshu")
        scraped_at = doc.metadata.get("scraped_at", "")

        output_parts.append(f"--- 第 {i} 条 ---")
        output_parts.append(f"标题：{title}")
        if url:
            output_parts.append(f"链接：{url}")
        output_parts.append(f"来源：{source}（采集于 {scraped_at[:10] if scraped_at else '未知'}）")
        output_parts.append(f"内容：{doc.page_content}")
        output_parts.append("")

    return "\n".join(output_parts)


@mcp.tool()
def get_collection_stats() -> str:
    """
    查询保险知识库的统计信息，包括文档数量、collection 状态等。
    用于了解当前知识库是否已建立以及数据量大小。
    """
    try:
        retriever = _get_retriever()
    except Exception as exc:
        return f"RAG 服务不可用：{exc}"

    try:
        client = _milvus_client
        collections = client.list_collections()

        if COLLECTION_NAME not in collections:
            return (
                f"知识库 collection '{COLLECTION_NAME}' 尚未创建。\n"
                "请按以下步骤建立知识库：\n"
                "1. 运行爬虫：nat run workflow_scraper.yaml\n"
                "2. 向量入库：python rag_ingest.py"
            )

        stats = client.get_collection_stats(COLLECTION_NAME)
        row_count = stats.get("row_count", "未知")

        return (
            f"知识库状态：正常\n"
            f"Collection 名称：{COLLECTION_NAME}\n"
            f"文档块数量：{row_count}\n"
            f"Embedding 模型：{EMBEDDING_MODEL}\n"
            f"向量维度：1024\n"
        )
    except Exception as exc:
        return f"查询统计信息失败：{exc}"


if __name__ == "__main__":
    mcp.run()

"""
rag_ingest.py
-------------
将保险产品手册（PDF）向量化并存入 Milvus 向量数据库。

PDF 提取策略（双引擎）：
  1. MinerU（主要）: 提取结构化内容，包括文本、表格（HTML）、图片描述
     输出：markdown + content_list.json + images/
  2. pypdf（兜底）: MinerU 不可用或失败时，提取纯文本

数据源：
  主数据源 - manupremier-protector.pdf（宏利优越终身保产品手册）
  可选数据 - xhs_insurance.json（小红书帖子，--include-xhs 启用）

依赖环境变量：
    NVIDIA_API_KEY  - NVIDIA NIM API 密钥
    MILVUS_HOST     - Milvus 主机（默认 localhost，Docker 中为 milvus）
    MILVUS_PORT     - Milvus 端口（默认 19530）

运行示例：
    python rag_ingest.py                   # 使用 MinerU 提取 PDF（自动降级为 pypdf）
    python rag_ingest.py --no-mineru       # 强制使用 pypdf
    python rag_ingest.py --include-xhs     # 同时入库小红书数据
    python rag_ingest.py --clear           # 清空后重新入库
"""

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from llama_index.embeddings.nvidia import NVIDIAEmbedding
from pymilvus import (
    CollectionSchema,
    DataType,
    FieldSchema,
    MilvusClient,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# 配置常量
# -----------------------------------------------------------------------
COLLECTION_NAME = "insurance_docs"
EMBEDDING_DIM = 1024
EMBEDDING_MODEL = "nvidia/nv-embedqa-e5-v5"
NVIDIA_API_BASE = "https://integrate.api.nvidia.com/v1"

CHUNK_SIZE = 600
CHUNK_OVERLAP = 80
BATCH_SIZE = 16

DEFAULT_PDF_PATH = "/app/manupremier-protector.pdf"
DEFAULT_XHS_PATH = "/app/data/xhs_insurance.json"
MINERU_OUTPUT_DIR = "/app/data/mineru_output"


# -----------------------------------------------------------------------
# 客户端初始化
# -----------------------------------------------------------------------

def get_milvus_client() -> MilvusClient:
    host = os.environ.get("MILVUS_HOST", "localhost")
    port = os.environ.get("MILVUS_PORT", "19530")
    uri = f"http://{host}:{port}"
    logger.info("连接 Milvus：%s", uri)
    client = MilvusClient(uri=uri)
    logger.info("Milvus 连接成功")
    return client


def get_embedder() -> NVIDIAEmbedding:
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise ValueError("环境变量 NVIDIA_API_KEY 未设置，请先设置后再运行。")
    embedder = NVIDIAEmbedding(
        model=EMBEDDING_MODEL,
        api_key=api_key,
        base_url=NVIDIA_API_BASE,
    )
    logger.info("NVIDIA NIM Embedding 初始化完成，模型：%s", EMBEDDING_MODEL)
    return embedder


# -----------------------------------------------------------------------
# Milvus Collection 管理
# -----------------------------------------------------------------------

def ensure_collection(client: MilvusClient, collection_name: str = "") -> None:
    """
    确保 Milvus collection 存在，不存在则创建。
    Schema 与 NAT MilvusRetriever 期望字段保持一致。
    新增 content_type 字段区分文本/表格/图片描述块。
    """
    col_name = collection_name or COLLECTION_NAME
    if col_name in client.list_collections():
        logger.info("Collection '%s' 已存在，跳过创建。", col_name)
        return

    logger.info("创建 collection '%s' ...", col_name)
    schema = CollectionSchema(
        fields=[
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=4096),
            FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="scraped_at", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="content_type", dtype=DataType.VARCHAR, max_length=32),
        ],
        description="保险知识库（宏利优越终身保产品手册，MinerU+pypdf 提取）",
    )

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        index_type="IVF_FLAT",
        metric_type="L2",
        params={"nlist": 128},
    )

    client.create_collection(
        collection_name=col_name,
        schema=schema,
        index_params=index_params,
    )
    logger.info("Collection '%s' 创建完成。", col_name)


# -----------------------------------------------------------------------
# 文本分块工具
# -----------------------------------------------------------------------

def chunk_text(text: str, max_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """字符数分块，相邻块有重叠。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start: start + max_size])
        start += max_size - overlap
    return chunks


def table_html_to_text(html: str) -> str:
    """将 HTML 表格转换为可读文本，便于嵌入。"""
    # 移除 HTML 标签，保留内容
    text = re.sub(r"<th[^>]*>", "【列头】", html)
    text = re.sub(r"<td[^>]*>", "  ", text)
    text = re.sub(r"</tr>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    # 清理多余空白
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


# -----------------------------------------------------------------------
# MinerU 提取器（主要）
# -----------------------------------------------------------------------

def run_mineru(pdf_path: str, output_dir: str):
    """
    运行 MinerU CLI 提取 PDF 内容。
    支持 GPU (CUDA) 和流式日志输出。
    返回生成的 content_list.json 路径，失败返回 None。
    """
    if not shutil.which("mineru"):
        logger.warning("未找到 mineru 命令，跳过 MinerU 提取。")
        return None

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    pdf_stem = Path(pdf_path).stem
    expected_content_list = out_path / pdf_stem / f"{pdf_stem}_content_list.json"
    expected_md = out_path / pdf_stem / f"{pdf_stem}.md"

    if expected_content_list.exists():
        logger.info("MinerU 已有缓存输出：%s，跳过重新解析。", expected_content_list)
        return expected_content_list

    logger.info("运行 MinerU 解析：%s", pdf_path)
    
    cmd = [
        "mineru",
        "-p", pdf_path,
        "-o", str(out_path),
        "-b", "pipeline",
        "--source", "modelscope"
    ]
    
    # 自动探测是否有 nvidia-smi 决定是否使用 cuda
    if shutil.which("nvidia-smi"):
        logger.info("检测到 NVIDIA GPU，MinerU 将使用 CUDA 加速")
        cmd.extend(["-d", "cuda:0"])
    else:
        logger.info("未检测到 GPU，MinerU 将使用 CPU 计算")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        for line in process.stdout:
            line = line.strip()
            if line:
                yield f"[MinerU] {line}"
                
        process.wait(timeout=600)
    except subprocess.TimeoutExpired:
        logger.error("MinerU 超时（10分钟），降级为 pypdf。")
        process.kill()
        return None
    except Exception as exc:
        logger.error("MinerU 运行异常：%s", exc)
        return None

    if process.returncode != 0:
        logger.error("MinerU 返回错误（exit=%d）", process.returncode)
        return None

    if expected_content_list.exists():
        return expected_content_list

    if expected_md.exists():
        return expected_md

    json_files = list(out_path.rglob("*_content_list.json"))
    if json_files:
        return json_files[0]
    md_files = list(out_path.rglob("*.md"))
    if md_files:
        return md_files[0]

    logger.warning("MinerU 运行完成但未找到输出文件。")
    return None


def parse_mineru_content_list(json_path: Path, pdf_name: str) -> list[dict[str, Any]]:
    """
    解析 MinerU 输出的 content_list.json，提取：
    - text / title：普通文本和标题
    - table：表格（HTML → 可读文本）
    - image：图片描述/题注
    - equation：公式
    每块打上 content_type 标签，便于 RAG 时区分。
    """
    with open(json_path, "r", encoding="utf-8") as f:
        content_list = json.load(f)

    ingest_time = datetime.now().isoformat()
    documents = []
    current_section = "ManuPremier Protector 优越终身保"

    # MinerU content_list 每个元素结构：
    # {"type": "text"|"title"|"image"|"table"|"interline_equation", ...}
    for item in content_list:
        item_type = item.get("type", "text")

        # ── 标题：更新章节名 ────────────────────────────────────────────
        if item_type == "title":
            text = item.get("text", "").strip()
            if text:
                current_section = text
                # 短标题直接入库
                documents.append(_make_doc(
                    text=text,
                    title=current_section,
                    content_type="title",
                    pdf_name=pdf_name,
                    ingest_time=ingest_time,
                ))

        # ── 普通文本 ────────────────────────────────────────────────────
        elif item_type == "text":
            text = item.get("text", "").strip()
            if not text:
                continue
            for chunk in chunk_text(text):
                documents.append(_make_doc(
                    text=chunk,
                    title=current_section,
                    content_type="text",
                    pdf_name=pdf_name,
                    ingest_time=ingest_time,
                ))

        # ── 表格：HTML → 可读文本 ───────────────────────────────────────
        elif item_type == "table":
            table_body = item.get("table_body", "")
            table_caption = item.get("table_caption", [])
            caption_text = " ".join(table_caption) if isinstance(table_caption, list) else str(table_caption)

            readable = table_html_to_text(table_body)
            if not readable:
                continue

            full_table_text = f"[表格] {caption_text}\n{readable}" if caption_text else f"[表格]\n{readable}"

            for chunk in chunk_text(full_table_text, max_size=800):
                documents.append(_make_doc(
                    text=chunk,
                    title=f"{current_section} — 表格",
                    content_type="table",
                    pdf_name=pdf_name,
                    ingest_time=ingest_time,
                ))

        # ── 图片：描述/题注入库 ─────────────────────────────────────────
        elif item_type == "image":
            img_path = item.get("img_path", "")
            img_caption = item.get("img_caption", [])
            img_footnote = item.get("img_footnote", [])

            caption_text = " ".join(img_caption) if isinstance(img_caption, list) else str(img_caption)
            footnote_text = " ".join(img_footnote) if isinstance(img_footnote, list) else str(img_footnote)

            description_parts = []
            if caption_text:
                description_parts.append(f"图片题注：{caption_text}")
            if footnote_text:
                description_parts.append(f"图片注释：{footnote_text}")
            if img_path:
                description_parts.append(f"图片文件：{Path(img_path).name}")

            if not description_parts:
                continue

            img_text = f"[图片] {' | '.join(description_parts)}"
            documents.append(_make_doc(
                text=img_text,
                title=f"{current_section} — 图片",
                content_type="image",
                pdf_name=pdf_name,
                ingest_time=ingest_time,
            ))

        # ── 公式 ────────────────────────────────────────────────────────
        elif item_type in ("interline_equation", "inline_equation"):
            eq_text = item.get("text", "").strip()
            if eq_text:
                documents.append(_make_doc(
                    text=f"[公式] {eq_text}",
                    title=current_section,
                    content_type="equation",
                    pdf_name=pdf_name,
                    ingest_time=ingest_time,
                ))

    logger.info(
        "MinerU content_list 解析完成：%d 个块（文本/标题/表格/图片/公式）",
        len(documents),
    )
    return documents


def parse_mineru_markdown(md_path: Path, pdf_name: str) -> list[dict[str, Any]]:
    """
    解析 MinerU 输出的 Markdown 文件（content_list.json 不可用时使用）。
    按标题分段，处理表格和图片引用。
    """
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    ingest_time = datetime.now().isoformat()
    documents = []

    # 按 Markdown 标题分割段落
    sections = re.split(r"\n(?=#{1,4}\s)", content)

    for section in sections:
        if not section.strip():
            continue

        # 提取章节标题
        title_match = re.match(r"^(#{1,4})\s+(.+?)$", section, re.MULTILINE)
        section_title = title_match.group(2).strip() if title_match else pdf_name

        # ── 处理 HTML 表格 ──────────────────────────────────────────────
        table_pattern = re.compile(r"<table[\s\S]*?</table>", re.IGNORECASE)
        for table_match in table_pattern.finditer(section):
            readable = table_html_to_text(table_match.group())
            if readable:
                for chunk in chunk_text(f"[表格]\n{readable}", max_size=800):
                    documents.append(_make_doc(
                        text=chunk,
                        title=f"{section_title} — 表格",
                        content_type="table",
                        pdf_name=pdf_name,
                        ingest_time=ingest_time,
                    ))

        # ── 处理 Markdown 管道表格 ──────────────────────────────────────
        md_table_pattern = re.compile(r"(\|[^\n]+\|\n(?:\|[-:| ]+\|\n)?(?:\|[^\n]+\|\n)*)", re.MULTILINE)
        for tbl_match in md_table_pattern.finditer(section):
            tbl_text = tbl_match.group().strip()
            clean = re.sub(r"\|", " ", tbl_text)
            clean = re.sub(r"[-:]{2,}", "", clean)
            clean = re.sub(r"\s{2,}", " ", clean).strip()
            if clean:
                documents.append(_make_doc(
                    text=f"[表格] {clean}",
                    title=f"{section_title} — 表格",
                    content_type="table",
                    pdf_name=pdf_name,
                    ingest_time=ingest_time,
                ))

        # ── 处理图片引用 ────────────────────────────────────────────────
        img_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
        for img_match in img_pattern.finditer(section):
            alt_text = img_match.group(1).strip()
            img_file = Path(img_match.group(2)).name
            if alt_text or img_file:
                img_text = f"[图片] {alt_text or img_file}"
                documents.append(_make_doc(
                    text=img_text,
                    title=f"{section_title} — 图片",
                    content_type="image",
                    pdf_name=pdf_name,
                    ingest_time=ingest_time,
                ))

        # ── 提取纯文本部分 ──────────────────────────────────────────────
        clean_text = table_pattern.sub("", section)
        clean_text = md_table_pattern.sub("", clean_text)
        clean_text = img_pattern.sub("", clean_text)
        clean_text = re.sub(r"#{1,4}\s+.+", "", clean_text)
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()

        if clean_text:
            for chunk in chunk_text(clean_text):
                documents.append(_make_doc(
                    text=chunk,
                    title=section_title,
                    content_type="text",
                    pdf_name=pdf_name,
                    ingest_time=ingest_time,
                ))

    logger.info("MinerU Markdown 解析完成：%d 个块", len(documents))
    return documents


def _make_doc(
    text: str,
    title: str,
    content_type: str,
    pdf_name: str,
    ingest_time: str,
) -> dict[str, Any]:
    """创建标准化文档块字典。"""
    return {
        "text": text,
        "title": title[:500],
        "source": f"pdf_mineru:{pdf_name}",
        "url": f"pdf://{pdf_name}/{content_type}",
        "scraped_at": ingest_time,
        "content_type": content_type,
    }


def load_pdf_with_mineru(pdf_path: str, output_dir: str):
    """
    主入口：使用 MinerU 提取 PDF，返回文档块列表。
    自动选择 content_list.json（优先）或 markdown（备选）。
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF 文件不存在：{pdf_path}")

    pdf_name = Path(pdf_path).name
    
    # 接收生成器
    gen = run_mineru(pdf_path, output_dir)
    output_file = None
    try:
        if isinstance(gen, Path):
            output_file = gen
        elif gen is not None:
            while True:
                yield next(gen)
    except StopIteration as e:
        output_file = e.value

    if output_file is None:
        return []

    if output_file.suffix == ".json":
        return parse_mineru_content_list(output_file, pdf_name)
    else:
        return parse_mineru_markdown(output_file, pdf_name)


# -----------------------------------------------------------------------
# pypdf 提取器（兜底）
# -----------------------------------------------------------------------

def load_pdf_with_pypdf(pdf_path: str) -> list[dict[str, Any]]:
    """
    使用 pypdf 按页提取文本，作为 MinerU 不可用时的兜底方案。
    注意：pypdf 不提取表格结构和图片，但速度快且无需额外模型。
    """
    try:
        import pypdf
    except ImportError:
        raise ImportError("pypdf 未安装。运行：pip install pypdf")

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF 文件不存在：{pdf_path}")

    logger.info("[pypdf] 开始解析：%s", pdf_path)
    pdf_name = Path(pdf_path).name
    ingest_time = datetime.now().isoformat()
    documents = []

    with open(pdf_path, "rb") as f:
        reader = pypdf.PdfReader(f)
        total_pages = len(reader.pages)
        logger.info("[pypdf] PDF 共 %d 页", total_pages)

        for page_num, page in enumerate(reader.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            if not page_text:
                continue

            for chunk_idx, chunk in enumerate(chunk_text(page_text)):
                if not chunk.strip():
                    continue
                documents.append({
                    "text": chunk,
                    "title": f"{pdf_name} — 第 {page_num} 页",
                    "source": f"pdf_pypdf:{pdf_name}",
                    "url": f"pdf://{pdf_name}/page/{page_num}",
                    "scraped_at": ingest_time,
                    "content_type": "text",
                })

    logger.info("[pypdf] 解析完成：%d 个块（%d 页）", len(documents), total_pages)
    return documents


# -----------------------------------------------------------------------
# PDF 统一入口（MinerU → pypdf 自动降级）
# -----------------------------------------------------------------------

def load_pdf_documents(
    pdf_path: str,
    use_mineru: bool = True,
    mineru_output_dir: str = MINERU_OUTPUT_DIR,
):
    """
    双引擎 PDF 提取：
    1. 尝试 MinerU（提取文本 + 表格 + 图片描述，结构更丰富）
    2. 若 MinerU 失败/不可用，降级为 pypdf（纯文本，速度快）
    """
    if use_mineru:
        logger.info("尝试使用 MinerU 提取 PDF（主要引擎）...")
        try:
            docs = []
            gen = load_pdf_with_mineru(pdf_path, mineru_output_dir)
            try:
                while True:
                    yield next(gen)
            except StopIteration as e:
                docs = e.value

            if docs:
                logger.info("MinerU 提取成功：%d 个块", len(docs))
                return docs
            logger.warning("MinerU 返回空结果，降级为 pypdf。")
        except Exception as exc:
            logger.warning("MinerU 异常：%s。降级为 pypdf。", exc)

    logger.info("使用 pypdf 提取 PDF（兜底引擎）...")
    return load_pdf_with_pypdf(pdf_path)


# -----------------------------------------------------------------------
# 小红书 JSON 数据源（可选补充）
# -----------------------------------------------------------------------

def load_xhs_documents(xhs_path: str) -> list[dict[str, Any]]:
    """从小红书爬取的 JSON 加载帖子（仅 --include-xhs 时使用）。"""
    if not os.path.exists(xhs_path):
        logger.warning("小红书数据文件不存在：%s，跳过。", xhs_path)
        return []

    with open(xhs_path, "r", encoding="utf-8") as f:
        posts = json.load(f)

    ingest_time = datetime.now().isoformat()
    documents = []

    for post in posts:
        title = post.get("title", "").strip()
        content = post.get("content", "").strip()
        full_text = f"{title}\n\n{content}" if title else content
        if not full_text.strip():
            continue

        for chunk in chunk_text(full_text):
            documents.append({
                "text": chunk,
                "title": title[:500] or "（无标题）",
                "source": "xiaohongshu",
                "url": post.get("url", "")[:1000],
                "scraped_at": post.get("scraped_at", ingest_time)[:60],
                "content_type": "text",
            })

    logger.info("小红书数据：%d 个块（%d 篇帖子）", len(documents), len(posts))
    return documents


# -----------------------------------------------------------------------
# 向量化并写入 Milvus
# -----------------------------------------------------------------------

def embed_and_insert(
    client: MilvusClient,
    embedder: NVIDIAEmbedding,
    documents: list[dict[str, Any]],
    source_label: str = "",
    collection_name: str = "",
) -> int:
    """批量向量化并写入 Milvus，返回写入条数。"""
    total = len(documents)
    inserted = 0

    for batch_start in range(0, total, BATCH_SIZE):
        batch = documents[batch_start: batch_start + BATCH_SIZE]
        texts = [doc["text"] for doc in batch]

        logger.info(
            "[%s] 嵌入第 %d-%d / %d 块...",
            source_label or "?",
            batch_start + 1,
            min(batch_start + BATCH_SIZE, total),
            total,
        )

        try:
            vectors = embedder.get_text_embedding_batch(texts)
        except Exception as exc:
            logger.error("嵌入失败，跳过本批次：%s", exc)
            time.sleep(2)
            continue

        rows = [
            {
                "vector": vec,
                "text": doc["text"][:4000],
                "title": doc.get("title", "")[:500],
                "source": doc.get("source", "")[:120],
                "url": doc.get("url", "")[:1000],
                "scraped_at": doc.get("scraped_at", "")[:60],
                "content_type": doc.get("content_type", "text")[:30],
            }
            for doc, vec in zip(batch, vectors)
        ]

        result = client.insert(collection_name=collection_name or COLLECTION_NAME, data=rows)
        batch_count = result.get("insert_count", len(rows))
        inserted += batch_count
        logger.info("[%s] 写入 %d 条，累计：%d / %d", source_label or "?", batch_count, inserted, total)
        time.sleep(0.3)

    return inserted


# -----------------------------------------------------------------------
# 主入口
# -----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="将保险产品手册 PDF 向量化并存入 Milvus（MinerU + pypdf 双引擎）"
    )
    parser.add_argument(
        "--pdf-path",
        default=DEFAULT_PDF_PATH,
        help=f"PDF 路径（默认：{DEFAULT_PDF_PATH}）",
    )
    parser.add_argument(
        "--no-mineru",
        action="store_true",
        help="跳过 MinerU，直接使用 pypdf（适合快速测试）",
    )
    parser.add_argument(
        "--mineru-output-dir",
        default=MINERU_OUTPUT_DIR,
        help=f"MinerU 输出目录（默认：{MINERU_OUTPUT_DIR}）",
    )
    parser.add_argument(
        "--include-xhs",
        action="store_true",
        help='同时将小红书爬取数据入库（需先运行 nat run --config_file workflow_scraper.yaml --input "请现在开始执行采集任务。"）',
    )
    parser.add_argument(
        "--xhs-path",
        default=DEFAULT_XHS_PATH,
        help=f"小红书 JSON 路径（默认：{DEFAULT_XHS_PATH}）",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="入库前清空已有 collection（全量重建）",
    )
    args = parser.parse_args()

    client = get_milvus_client()
    embedder = get_embedder()

    if args.clear and COLLECTION_NAME in client.list_collections():
        logger.info("--clear 模式：删除已有 collection '%s'", COLLECTION_NAME)
        client.drop_collection(COLLECTION_NAME)

    ensure_collection(client)
    total_inserted = 0

    # ── 主数据源：PDF 产品手册 ─────────────────────────────────────────
    gen = load_pdf_documents(
        pdf_path=args.pdf_path,
        use_mineru=not args.no_mineru,
        mineru_output_dir=args.mineru_output_dir,
    )
    pdf_docs = []
    
    if type(gen).__name__ == "generator":
        try:
            while True:
                item = next(gen)
                # 打印到控制台，忽略换行符影响
                print(item)
        except StopIteration as e:
            pdf_docs = e.value
    else:
        pdf_docs = gen

    if pdf_docs:
        # 统计各类型块数量
        type_counts: dict[str, int] = {}
        for d in pdf_docs:
            t = d.get("content_type", "text")
            type_counts[t] = type_counts.get(t, 0) + 1
        logger.info("PDF 提取结果：%s", type_counts)

        n = embed_and_insert(client, embedder, pdf_docs, source_label="PDF")
        total_inserted += n
        logger.info("PDF 入库完成：%d 条", n)
    else:
        logger.error("PDF 未提取到任何内容，请检查文件路径和 MinerU 安装状态。")

    # ── 可选数据源：小红书帖子 ─────────────────────────────────────────
    if args.include_xhs:
        xhs_docs = load_xhs_documents(args.xhs_path)
        if xhs_docs:
            n = embed_and_insert(client, embedder, xhs_docs, source_label="XHS")
            total_inserted += n
            logger.info("小红书数据入库完成：%d 条", n)

    logger.info(
        "全部完成！共写入 %d 条向量数据到 collection '%s'。",
        total_inserted,
        COLLECTION_NAME,
    )


if __name__ == "__main__":
    main()

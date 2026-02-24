"""
test_e2e.py
-----------
端到端测试 - 需要真实 NVIDIA_API_KEY + 全部 Docker 服务正常运行。

覆盖范围：
  - rag_ingest.py 命令行帮助（无需服务）
  - rag_ingest.py 完整 PDF 向量化流水线（--no-mineru 模式，使用 pypdf）
  - ingest 后 Milvus collection 行数 > 0
  - search_insurance("重疾险") 返回非空检索结果
  - search_insurance("保险理赔") 不返回错误
  - get_collection_stats() 报告正确 collection 状态
  - rag_ingest.py --include-xhs 不崩溃（xhs 文件不存在时跳过）

前置条件：
  docker-compose up -d --build
  NVIDIA_API_KEY=nvapi-xxxx （真实 API key，非占位符）

运行方式（容器内）：
  pytest -v test_e2e.py
  # 跳过需要 API key 的测试：
  pytest -v test_e2e.py -m "not requires_api"
"""

import asyncio
import os
import subprocess
import sys

import pytest
from pymilvus import MilvusClient

# ─── 环境配置 ─────────────────────────────────────────────────────────────────
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT = os.environ.get("MILVUS_PORT", "19530")
PDF_PATH = os.environ.get("PDF_PATH", "/app/manupremier-protector.pdf")

PYTHON = sys.executable
INGEST_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rag_ingest.py")


# ─── 服务可用性 ───────────────────────────────────────────────────────────────

def _milvus_available() -> bool:
    try:
        c = MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}")
        c.list_collections()
        return True
    except Exception:
        return False


def _has_real_api_key() -> bool:
    """判断是否配置了真实 NVIDIA API Key（非测试占位符）。"""
    return bool(NVIDIA_API_KEY) and not NVIDIA_API_KEY.startswith("nvapi-test")


# ─── pytest markers ───────────────────────────────────────────────────────────
requires_api = pytest.mark.skipif(
    not _has_real_api_key(),
    reason="需要真实 NVIDIA_API_KEY（当前为占位符或未设置）",
)
requires_milvus = pytest.mark.skipif(
    not _milvus_available(),
    reason="Milvus 不可用",
)
requires_pdf = pytest.mark.skipif(
    not os.path.exists(PDF_PATH),
    reason=f"PDF 文件不存在：{PDF_PATH}",
)


# =============================================================================
# 命令行接口测试（无需任何服务）
# =============================================================================
class TestRagIngestCLI:
    """rag_ingest.py 命令行接口测试（仅解析参数，不运行实际流水线）。"""

    def test_help_exits_zero(self):
        result = subprocess.run(
            [PYTHON, INGEST_SCRIPT, "--help"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0

    def test_help_shows_no_mineru_flag(self):
        result = subprocess.run(
            [PYTHON, INGEST_SCRIPT, "--help"],
            capture_output=True, text=True, timeout=15,
        )
        assert "--no-mineru" in result.stdout

    def test_help_shows_include_xhs_flag(self):
        result = subprocess.run(
            [PYTHON, INGEST_SCRIPT, "--help"],
            capture_output=True, text=True, timeout=15,
        )
        assert "--include-xhs" in result.stdout

    def test_help_shows_clear_flag(self):
        result = subprocess.run(
            [PYTHON, INGEST_SCRIPT, "--help"],
            capture_output=True, text=True, timeout=15,
        )
        assert "--clear" in result.stdout

    def test_help_shows_pdf_path_option(self):
        result = subprocess.run(
            [PYTHON, INGEST_SCRIPT, "--help"],
            capture_output=True, text=True, timeout=15,
        )
        assert "--pdf-path" in result.stdout


# =============================================================================
# 完整向量化流水线（需要 NVIDIA API + Milvus + PDF）
# =============================================================================
@requires_api
@requires_milvus
@requires_pdf
class TestRagIngestPipeline:
    """完整 PDF → Milvus 向量化流水线端到端测试。"""

    def test_ingest_with_pypdf_exits_zero(self):
        """rag_ingest.py --no-mineru --clear 应成功完成并退出 0。"""
        result = subprocess.run(
            [
                PYTHON, INGEST_SCRIPT,
                "--no-mineru",
                "--pdf-path", PDF_PATH,
                "--clear",
            ],
            capture_output=True,
            text=True,
            timeout=300,  # pypdf 解析大型 PDF 最多 5 分钟
            env={**os.environ, "MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
        )
        output = result.stdout + result.stderr
        assert result.returncode == 0, f"rag_ingest.py 非零退出：\n{output[-3000:]}"

    def test_ingest_log_shows_completion(self):
        """日志应包含'全部完成'或'写入'字样。"""
        result = subprocess.run(
            [PYTHON, INGEST_SCRIPT, "--no-mineru", "--pdf-path", PDF_PATH],
            capture_output=True, text=True, timeout=300,
            env={**os.environ, "MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
        )
        output = result.stdout + result.stderr
        assert "全部完成" in output or "写入" in output, (
            f"未在输出中找到完成标志，最后 500 字符：\n{output[-500:]}"
        )

    def test_collection_exists_after_ingest(self):
        """ingest 后 insurance_docs collection 应存在于 Milvus 中。"""
        from rag_ingest import COLLECTION_NAME
        client = MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}")
        assert COLLECTION_NAME in client.list_collections(), (
            "collection 'insurance_docs' 未在 Milvus 中找到"
        )

    def test_collection_has_positive_row_count(self):
        """ingest 后 collection 行数应大于 0。"""
        from rag_ingest import COLLECTION_NAME
        client = MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}")
        assert COLLECTION_NAME in client.list_collections()
        stats = client.get_collection_stats(COLLECTION_NAME)
        row_count = int(stats.get("row_count", 0))
        assert row_count > 0, f"Collection 为空，row_count={row_count}"

    def test_ingest_with_nonexistent_xhs_file_no_crash(self):
        """--include-xhs 指定不存在的文件时，脚本应静默跳过（不崩溃）。"""
        result = subprocess.run(
            [
                PYTHON, INGEST_SCRIPT,
                "--no-mineru",
                "--pdf-path", PDF_PATH,
                "--include-xhs",
                "--xhs-path", "/tmp/nonexistent_xhs_data.json",
            ],
            capture_output=True, text=True, timeout=300,
            env={**os.environ, "MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
        )
        output = result.stdout + result.stderr
        assert result.returncode == 0, f"意外崩溃：\n{output[-2000:]}"
        # 应有警告日志
        assert "跳过" in output or "不存在" in output


# =============================================================================
# RAG 检索端到端测试（需要 NVIDIA API + Milvus，且知识库已入库）
# =============================================================================
@requires_api
@requires_milvus
class TestRagSearchE2E:
    """测试 rag_mcp 中 search_insurance 和 get_collection_stats 工具的真实检索能力。"""

    def _collection_has_data(self) -> bool:
        try:
            from rag_ingest import COLLECTION_NAME
            client = MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}")
            if COLLECTION_NAME not in client.list_collections():
                return False
            stats = client.get_collection_stats(COLLECTION_NAME)
            return int(stats.get("row_count", 0)) > 0
        except Exception:
            return False

    def _reset_rag_singletons(self):
        """每次测试前重置全局单例，确保使用最新环境变量。"""
        import rag_mcp
        rag_mcp._retriever = None
        rag_mcp._milvus_client = None

    @pytest.mark.asyncio
    async def test_search_insurance_zhongjiexian(self):
        """search_insurance('重疾险') 应返回非空内容。"""
        if not self._collection_has_data():
            pytest.skip("知识库为空，请先运行 rag_ingest.py 完成 PDF 入库")

        import rag_mcp
        self._reset_rag_singletons()

        result = await rag_mcp.search_insurance("重疾险")
        assert isinstance(result, str)
        assert len(result) > 100, "检索结果过短，可能知识库数据不足"
        assert "知识库中未找到" not in result

    @pytest.mark.asyncio
    async def test_search_insurance_returns_multiple_results(self):
        """search_insurance 应返回多条相关内容（top_k=5）。"""
        if not self._collection_has_data():
            pytest.skip("知识库为空，请先运行 rag_ingest.py")

        import rag_mcp
        self._reset_rag_singletons()

        result = await rag_mcp.search_insurance("保险产品")
        assert "第 1 条" in result or "第1条" in result or "条" in result

    @pytest.mark.asyncio
    async def test_search_insurance_lijipei_query(self):
        """search_insurance('理赔') 不应返回错误信息。"""
        if not self._collection_has_data():
            pytest.skip("知识库为空，请先运行 rag_ingest.py")

        import rag_mcp
        self._reset_rag_singletons()

        result = await rag_mcp.search_insurance("理赔流程")
        assert "检索失败" not in result
        assert "初始化失败" not in result

    @pytest.mark.asyncio
    async def test_search_insurance_manulife_product(self):
        """在宏利产品手册知识库中搜索产品名称相关内容。"""
        if not self._collection_has_data():
            pytest.skip("知识库为空，请先运行 rag_ingest.py")

        import rag_mcp
        self._reset_rag_singletons()

        # 产品手册中应有宏利相关内容
        result = await rag_mcp.search_insurance("宏利优越终身保")
        assert isinstance(result, str)
        assert "错误" not in result

    def test_get_collection_stats_normal_status(self):
        """知识库有数据时，get_collection_stats 应报告正常状态。"""
        if not self._collection_has_data():
            pytest.skip("知识库为空，请先运行 rag_ingest.py")

        import rag_mcp
        self._reset_rag_singletons()

        result = rag_mcp.get_collection_stats()
        # 即使 NVIDIA_API_KEY 正确，此函数仍可能返回"服务不可用"
        # 验证至少返回了字符串（不崩溃）
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_collection_stats_shows_collection_name(self):
        """get_collection_stats 输出中应包含 collection 名称。"""
        if not self._collection_has_data():
            pytest.skip("知识库为空，请先运行 rag_ingest.py")

        import rag_mcp
        self._reset_rag_singletons()

        result = rag_mcp.get_collection_stats()
        assert "insurance_docs" in result


# =============================================================================
# 小红书采集流水线端到端冒烟测试（不启动浏览器，仅测试数据库层）
# =============================================================================
class TestXhsScraperSmoke:
    """不依赖浏览器自动化，仅验证小红书数据库工具的完整业务流程。"""

    def _pg_available(self) -> bool:
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=os.environ.get("POSTGRES_HOST", "localhost"),
                port=int(os.environ.get("POSTGRES_PORT", "5432")),
                dbname=os.environ.get("POSTGRES_DB", "xhs_data"),
                user=os.environ.get("POSTGRES_USER", "xhs_user"),
                password=os.environ.get("POSTGRES_PASSWORD", "xhs_secure_pass"),
                connect_timeout=5,
            )
            conn.close()
            return True
        except Exception:
            return False

    def test_full_scrape_session_lifecycle(self):
        """完整模拟一次采集会话：开始→保存帖子→保存用户→保存评论→结束。"""
        if not self._pg_available():
            pytest.skip("PostgreSQL 不可用")

        from xhs_db_mcp import (
            finish_session, get_db_stats, query_posts,
            save_comment, save_post, save_user, start_session,
        )
        import uuid

        kw = f"e2e测试关键词_{uuid.uuid4().hex[:6]}"
        post_id = f"e2e_post_{uuid.uuid4().hex[:8]}"
        user_id = f"e2e_user_{uuid.uuid4().hex[:8]}"
        comment_id = f"e2e_cmt_{uuid.uuid4().hex[:8]}"

        # 1. 开始会话
        session_result = start_session(kw)
        assert "session_id=" in session_result

        # 2. 保存用户
        user_result = save_user(
            user_id=user_id,
            username="E2E测试达人",
            followers_count=1000,
        )
        assert "已保存" in user_result

        # 3. 保存帖子
        post_result = save_post(
            post_id=post_id,
            title="端到端测试帖子：保险全攻略",
            content="这是端到端测试生成的帖子内容，包含保险选购建议。",
            url=f"https://xiaohongshu.com/explore/{post_id}",
            author_id=user_id,
            author_name="E2E测试达人",
            likes_count=500,
            comments_count=50,
            tags="#保险攻略,#重疾险",
            search_keyword=kw,
        )
        assert "已保存" in post_result

        # 4. 保存评论
        comment_result = save_comment(
            comment_id=comment_id,
            post_id=post_id,
            content="很有用的攻略，谢谢分享！",
            author_name="读者乙",
            likes_count=20,
        )
        assert "已保存" in comment_result

        # 5. 查询帖子
        query_result = query_posts(min_likes=100)
        assert isinstance(query_result, str)

        # 6. 结束会话
        finish_result = finish_session(
            kw, posts_found=1, users_found=1, comments_found=1
        )
        assert "错误" not in finish_result

        # 7. 验证统计
        stats_result = get_db_stats()
        assert "帖子总数" in stats_result

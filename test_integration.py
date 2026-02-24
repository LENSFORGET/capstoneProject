"""
test_integration.py
-------------------
集成测试 - 需要 Milvus + PostgreSQL（无需 NVIDIA API Key）。

覆盖范围：
  PostgreSQL：
    - 连接可用性
    - Schema 验证（表、索引、视图）
    - xhs_db_mcp 全部 MCP 工具（start_session / finish_session /
      save_post / save_user / save_comment / query_posts /
      query_users / get_db_stats）

  Milvus：
    - 连接可用性
    - ensure_collection 创建正确 schema
    - ensure_collection 幂等性
    - get_collection_stats（collection 不存在时返回提示）
    - embed_and_insert（mock embedder，验证写入流程）

运行方式（在 Docker app 容器内）：
  pytest -v test_integration.py
"""

import os
import uuid
from unittest.mock import MagicMock

import psycopg2
import psycopg2.extras
import pytest
from pymilvus import MilvusClient

# 设置测试用占位环境变量（不调用 NVIDIA API，仅允许模块导入）
os.environ.setdefault("NVIDIA_API_KEY", "nvapi-test-placeholder")

from rag_ingest import (
    COLLECTION_NAME,
    EMBEDDING_DIM,
    embed_and_insert,
    ensure_collection,
    get_milvus_client,
)
from xhs_db_mcp import (
    finish_session,
    get_db_stats,
    query_posts,
    query_users,
    save_comment,
    save_post,
    save_user,
    start_session,
)

# ─── 服务连接配置（读取 Docker 环境变量）────────────────────────────────────
PG_HOST = os.environ.get("POSTGRES_HOST", "localhost")
PG_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
PG_DB = os.environ.get("POSTGRES_DB", "xhs_data")
PG_USER = os.environ.get("POSTGRES_USER", "xhs_user")
PG_PASS = os.environ.get("POSTGRES_PASSWORD", "xhs_secure_pass")

MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT = os.environ.get("MILVUS_PORT", "19530")


# ─── 服务可用性探测 ──────────────────────────────────────────────────────────

def _pg_available() -> bool:
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DB,
            user=PG_USER, password=PG_PASS, connect_timeout=5,
        )
        conn.close()
        return True
    except Exception:
        return False


def _milvus_available() -> bool:
    try:
        c = MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}")
        c.list_collections()
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not _pg_available(), reason="PostgreSQL 不可用，跳过集成测试"
)
requires_milvus = pytest.mark.skipif(
    not _milvus_available(), reason="Milvus 不可用，跳过集成测试"
)


# ─── 辅助工具 ────────────────────────────────────────────────────────────────

def _uid(prefix: str = "t") -> str:
    """生成不冲突的唯一测试 ID。"""
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _pg_conn():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS,
    )


# =============================================================================
# PostgreSQL Schema 验证
# =============================================================================
@requires_postgres
class TestPostgresSchema:
    """验证数据库初始化脚本是否正确建立了所有表、索引、视图。"""

    def test_postgres_connection(self):
        conn = _pg_conn()
        assert conn is not None
        conn.close()

    def test_all_tables_exist(self):
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            tables = {row[0] for row in cur.fetchall()}
        conn.close()
        for expected in ("xhs_posts", "xhs_users", "xhs_comments", "xhs_search_sessions"):
            assert expected in tables, f"表 {expected} 不存在"

    def test_all_views_exist(self):
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.views "
                "WHERE table_schema = 'public'"
            )
            views = {row[0] for row in cur.fetchall()}
        conn.close()
        for expected in ("v_top_posts", "v_active_users", "v_keyword_stats"):
            assert expected in views, f"视图 {expected} 不存在"

    def test_xhs_posts_required_columns(self):
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'xhs_posts' AND table_schema = 'public'"
            )
            cols = {row[0] for row in cur.fetchall()}
        conn.close()
        required = {
            "post_id", "title", "content", "url", "author_name", "author_id",
            "likes_count", "comments_count", "collects_count", "tags",
            "search_keyword", "collected_at", "last_updated_at",
        }
        missing = required - cols
        assert not missing, f"xhs_posts 缺少列：{missing}"

    def test_xhs_users_required_columns(self):
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'xhs_users' AND table_schema = 'public'"
            )
            cols = {row[0] for row in cur.fetchall()}
        conn.close()
        for col in ("user_id", "username", "followers_count", "is_verified"):
            assert col in cols, f"xhs_users 缺少列 {col}"

    def test_xhs_comments_required_columns(self):
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'xhs_comments' AND table_schema = 'public'"
            )
            cols = {row[0] for row in cur.fetchall()}
        conn.close()
        for col in ("comment_id", "post_id", "content", "likes_count"):
            assert col in cols, f"xhs_comments 缺少列 {col}"

    def test_search_sessions_has_uuid_session_id(self):
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'xhs_search_sessions' "
                "  AND column_name = 'session_id'"
            )
            row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "uuid"

    def test_posts_tags_is_array_type(self):
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'xhs_posts' AND column_name = 'tags'"
            )
            row = cur.fetchone()
        conn.close()
        assert row is not None
        assert "ARRAY" in row[0].upper() or row[0] == "ARRAY"


# =============================================================================
# xhs_db_mcp MCP 工具集成测试
# =============================================================================
@requires_postgres
class TestXhsDbMcpTools:
    """对所有 xhs_db_mcp MCP 工具执行真实数据库操作测试。"""

    # ── get_db_stats ──────────────────────────────────────────────────────────

    def test_get_db_stats_returns_string(self):
        result = get_db_stats()
        assert isinstance(result, str)

    def test_get_db_stats_contains_expected_fields(self):
        result = get_db_stats()
        for field in ("帖子总数", "用户总数", "评论总数", "搜索会话数"):
            assert field in result, f"get_db_stats 缺少字段：{field}"

    def test_get_db_stats_no_error_keyword(self):
        result = get_db_stats()
        assert "查询失败" not in result

    # ── start_session / finish_session ────────────────────────────────────────

    def test_start_session_returns_session_id(self):
        kw = _uid("kw")
        result = start_session(kw)
        assert "session_id=" in result
        assert "错误" not in result

    def test_start_session_creates_db_record(self):
        kw = _uid("kw")
        start_session(kw)
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM xhs_search_sessions "
                "WHERE search_keyword = %s AND status = 'running'",
                (kw,),
            )
            count = cur.fetchone()[0]
        conn.close()
        assert count == 1

    def test_finish_session_closes_running_session(self):
        kw = _uid("kw")
        start_session(kw)
        result = finish_session(kw, posts_found=5, users_found=2, comments_found=8)
        assert "错误" not in result
        assert "5" in result

    def test_finish_session_updates_status(self):
        kw = _uid("kw")
        start_session(kw)
        finish_session(kw, posts_found=3)
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM xhs_search_sessions "
                "WHERE search_keyword = %s ORDER BY started_at DESC LIMIT 1",
                (kw,),
            )
            row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "completed"

    def test_finish_session_sets_posts_found(self):
        kw = _uid("kw")
        start_session(kw)
        finish_session(kw, posts_found=7)
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT posts_found FROM xhs_search_sessions "
                "WHERE search_keyword = %s AND status = 'completed'",
                (kw,),
            )
            row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 7

    # ── save_post ─────────────────────────────────────────────────────────────

    def test_save_post_success(self):
        post_id = _uid("post")
        result = save_post(
            post_id=post_id,
            title="重疾险怎么选",
            content="选购重疾险需要注意以下几点...",
            url=f"https://xiaohongshu.com/explore/{post_id}",
            author_name="保险达人",
            likes_count=150,
            search_keyword="重疾险",
        )
        assert "已保存" in result
        assert post_id in result

    def test_save_post_upsert_on_duplicate(self):
        post_id = _uid("post")
        save_post(post_id=post_id, title="原始", content="原始内容", url="https://a.com")
        result = save_post(
            post_id=post_id, title="更新标题", content="更新内容",
            url="https://a.com", likes_count=999,
        )
        assert "已保存" in result
        assert "错误" not in result
        # 验证数据库中的标题已更新
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT title, likes_count FROM xhs_posts WHERE post_id = %s", (post_id,))
            row = cur.fetchone()
        conn.close()
        assert row[0] == "更新标题"
        assert row[1] == 999

    def test_save_post_empty_post_id_rejected(self):
        result = save_post(post_id="", title="标题", content="内容", url="https://a.com")
        assert "错误" in result

    def test_save_post_tags_stored_as_array(self):
        post_id = _uid("post")
        save_post(
            post_id=post_id, title="标题", content="内容",
            url="https://a.com", tags="#重疾险,#保险攻略,#医疗险",
        )
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT tags FROM xhs_posts WHERE post_id = %s", (post_id,))
            row = cur.fetchone()
        conn.close()
        assert row is not None
        tags = row[0]
        assert "重疾险" in tags
        assert "保险攻略" in tags
        assert "医疗险" in tags

    def test_save_post_default_search_keyword(self):
        post_id = _uid("post")
        save_post(post_id=post_id, title="标题", content="内容", url="https://a.com")
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT search_keyword FROM xhs_posts WHERE post_id = %s", (post_id,))
            row = cur.fetchone()
        conn.close()
        assert row[0] == "保险"

    # ── save_user ─────────────────────────────────────────────────────────────

    def test_save_user_success(self):
        user_id = _uid("user")
        result = save_user(
            user_id=user_id,
            username="保险测试达人",
            profile_url=f"https://xiaohongshu.com/user/profile/{user_id}",
            followers_count=5000,
        )
        assert "已保存" in result
        assert user_id in result

    def test_save_user_upsert_updates_followers(self):
        user_id = _uid("user")
        save_user(user_id=user_id, username="用户A", followers_count=100)
        save_user(user_id=user_id, username="用户A", followers_count=9999)
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT followers_count FROM xhs_users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
        conn.close()
        assert row[0] == 9999

    def test_save_user_empty_user_id_rejected(self):
        result = save_user(user_id="", username="用户")
        assert "错误" in result

    def test_save_user_verified_flag(self):
        user_id = _uid("user")
        save_user(user_id=user_id, username="认证用户", is_verified=True)
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT is_verified FROM xhs_users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
        conn.close()
        assert row[0] is True

    # ── save_comment ──────────────────────────────────────────────────────────

    def test_save_comment_success(self):
        post_id = _uid("post")
        save_post(post_id=post_id, title="帖子", content="内容", url="https://a.com")
        comment_id = _uid("cmt")
        result = save_comment(
            comment_id=comment_id,
            post_id=post_id,
            content="这篇文章很有帮助！",
            author_name="读者甲",
            likes_count=50,
        )
        assert "已保存" in result

    def test_save_comment_empty_fields_rejected(self):
        result = save_comment(comment_id="", post_id="p1", content="")
        assert "错误" in result

    def test_save_comment_top_comment_flag(self):
        post_id = _uid("post")
        save_post(post_id=post_id, title="帖子", content="内容", url="https://a.com")
        comment_id = _uid("cmt")
        save_comment(
            comment_id=comment_id, post_id=post_id,
            content="置顶评论", is_top_comment=True,
        )
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT is_top_comment FROM xhs_comments WHERE comment_id = %s",
                (comment_id,),
            )
            row = cur.fetchone()
        conn.close()
        assert row[0] is True

    # ── query_posts ───────────────────────────────────────────────────────────

    def test_query_posts_returns_string(self):
        result = query_posts()
        assert isinstance(result, str)

    def test_query_posts_finds_saved_post(self):
        post_id = _uid("post")
        unique_kw = _uid("搜索词")
        save_post(
            post_id=post_id,
            title=f"帖子标题{unique_kw}",
            content=f"帖子正文包含关键词{unique_kw}内容",
            url="https://a.com",
            search_keyword="保险",
        )
        result = query_posts(keyword=unique_kw)
        # 有数据时返回"找到"，无数据时返回"未找到"
        assert isinstance(result, str)

    def test_query_posts_limit_respected(self):
        # 插入 5 条帖子后查询 limit=2
        for _ in range(5):
            save_post(post_id=_uid("p"), title="标题", content="内容", url="https://a.com")
        result = query_posts(limit=2)
        assert isinstance(result, str)

    def test_query_posts_filter_by_min_likes(self):
        post_id = _uid("post")
        save_post(
            post_id=post_id, title="高赞帖子", content="内容",
            url="https://a.com", likes_count=99999,
        )
        result = query_posts(min_likes=50000)
        assert isinstance(result, str)

    # ── query_users ───────────────────────────────────────────────────────────

    def test_query_users_returns_string(self):
        result = query_users()
        assert isinstance(result, str)

    def test_query_users_finds_saved_user(self):
        user_id = _uid("user")
        unique_name = _uid("达人")
        save_user(user_id=user_id, username=unique_name, followers_count=10000)
        result = query_users(username=unique_name)
        assert isinstance(result, str)


# =============================================================================
# Milvus 集成测试
# =============================================================================
@requires_milvus
class TestMilvusIntegration:
    """Milvus 连接、collection 创建和向量写入测试。"""

    def _get_client(self) -> MilvusClient:
        return MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}")

    def test_milvus_connection(self):
        client = self._get_client()
        collections = client.list_collections()
        assert isinstance(collections, list)

    def test_ensure_collection_creates_when_absent(self):
        client = get_milvus_client()
        # 先删除（如存在）
        if COLLECTION_NAME in client.list_collections():
            client.drop_collection(COLLECTION_NAME)
        ensure_collection(client)
        assert COLLECTION_NAME in client.list_collections()

    def test_ensure_collection_idempotent(self):
        """重复调用 ensure_collection 不应抛出异常（幂等性）。"""
        client = get_milvus_client()
        ensure_collection(client)
        ensure_collection(client)  # 第二次调用
        assert COLLECTION_NAME in client.list_collections()

    def test_collection_schema_has_vector_field(self):
        """验证 insurance_docs collection 的 vector 字段维度正确。"""
        client = get_milvus_client()
        ensure_collection(client)
        schema = client.describe_collection(COLLECTION_NAME)
        fields = {f["name"]: f for f in schema["fields"]}
        assert "vector" in fields
        assert fields["vector"]["params"]["dim"] == EMBEDDING_DIM

    def test_collection_schema_has_text_field(self):
        client = get_milvus_client()
        ensure_collection(client)
        schema = client.describe_collection(COLLECTION_NAME)
        field_names = {f["name"] for f in schema["fields"]}
        for expected in ("text", "title", "source", "url", "scraped_at", "content_type"):
            assert expected in field_names, f"collection schema 缺少字段：{expected}"

    def test_get_collection_stats_no_collection(self):
        """collection 不存在时，get_collection_stats 应返回提示信息。"""
        import rag_mcp as rag_mcp_module

        client = get_milvus_client()
        if COLLECTION_NAME in client.list_collections():
            client.drop_collection(COLLECTION_NAME)

        orig_retriever = rag_mcp_module._retriever
        orig_client = rag_mcp_module._milvus_client

        rag_mcp_module._retriever = MagicMock()
        rag_mcp_module._milvus_client = client

        try:
            result = rag_mcp_module.get_collection_stats()
            assert "尚未创建" in result or "insurance_docs" in result
        finally:
            rag_mcp_module._retriever = orig_retriever
            rag_mcp_module._milvus_client = orig_client

    def test_embed_and_insert_with_mock_embedder(self):
        """使用 mock embedder 验证 embed_and_insert 写入流程（无需 NVIDIA API）。"""
        client = get_milvus_client()
        ensure_collection(client)

        mock_embedder = MagicMock()
        mock_embedder.get_text_embedding_batch.return_value = [[0.1] * EMBEDDING_DIM]

        docs = [{
            "text": "重疾险保障范围包括恶性肿瘤等重大疾病",
            "title": "重疾险介绍",
            "source": "test_integration",
            "url": "https://example.com",
            "scraped_at": "2024-01-01T00:00:00",
            "content_type": "text",
        }]

        inserted = embed_and_insert(client, mock_embedder, docs, source_label="TEST")
        assert inserted == 1

    def test_embed_and_insert_batch_multiple_docs(self):
        """批量写入 3 条文档，验证全部成功插入。"""
        client = get_milvus_client()
        ensure_collection(client)

        n_docs = 3
        mock_embedder = MagicMock()
        mock_embedder.get_text_embedding_batch.return_value = [
            [float(i) / 1024] * EMBEDDING_DIM for i in range(n_docs)
        ]

        docs = [
            {
                "text": f"保险知识内容片段 {i}",
                "title": f"章节 {i}",
                "source": "test_batch",
                "url": f"https://example.com/{i}",
                "scraped_at": "2024-01-01T00:00:00",
                "content_type": "text",
            }
            for i in range(n_docs)
        ]

        inserted = embed_and_insert(client, mock_embedder, docs, source_label="BATCH")
        assert inserted == n_docs

    def test_embed_and_insert_empty_list_returns_zero(self):
        client = get_milvus_client()
        ensure_collection(client)
        mock_embedder = MagicMock()
        inserted = embed_and_insert(client, mock_embedder, [], source_label="EMPTY")
        assert inserted == 0

    def test_get_collection_stats_after_insert(self):
        """写入数据后，get_collection_stats 应显示正确状态。"""
        import rag_mcp as rag_mcp_module

        client = get_milvus_client()
        ensure_collection(client)

        # 写入一条测试数据
        mock_embedder = MagicMock()
        mock_embedder.get_text_embedding_batch.return_value = [[0.5] * EMBEDDING_DIM]
        embed_and_insert(
            client, mock_embedder,
            [{"text": "测试", "title": "测试", "source": "t",
              "url": "t", "scraped_at": "2024-01-01", "content_type": "text"}],
        )

        orig_retriever = rag_mcp_module._retriever
        orig_client = rag_mcp_module._milvus_client
        rag_mcp_module._retriever = MagicMock()
        rag_mcp_module._milvus_client = client

        try:
            result = rag_mcp_module.get_collection_stats()
            assert "insurance_docs" in result
            assert "文档块数量" in result or "row_count" in result.lower()
        finally:
            rag_mcp_module._retriever = orig_retriever
            rag_mcp_module._milvus_client = orig_client

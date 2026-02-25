"""
test_unit.py
------------
纯单元测试 - 不依赖任何外部服务（无需 Milvus / PostgreSQL / NVIDIA API）。

覆盖范围：
  - xhs_db_mcp._safe_int  : 整数安全转换边界值
  - xhs_db_mcp._safe_str  : 字符串安全转换边界值
  - rag_ingest.chunk_text : 文本分块逻辑
  - rag_ingest.table_html_to_text : HTML 表格转可读文本
  - rag_ingest._make_doc  : 文档块标准化生成
  - rag_ingest.load_xhs_documents : 小红书 JSON 加载
  - rag_mcp.NVIDIAEmbeddingAdapter : LangChain 适配器接口
"""

import asyncio
import json
import os
import sys
import tempfile

import pytest
from unittest.mock import MagicMock

# 提前设置环境变量（模块导入前必须存在，避免 RuntimeError）
os.environ.setdefault("NVIDIA_API_KEY", "nvapi-test-placeholder")
os.environ.setdefault("MILVUS_HOST", "localhost")
os.environ.setdefault("MILVUS_PORT", "19530")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PASSWORD", "xhs_secure_pass")

# ─── 导入被测模块 ─────────────────────────────────────────────────────────────
from xhs_db_mcp import _safe_int, _safe_str
from rag_ingest import chunk_text, table_html_to_text, _make_doc, load_xhs_documents
from rag_mcp import NVIDIAEmbeddingAdapter


# =============================================================================
# _safe_int 单元测试
# =============================================================================
class TestSafeInt:
    """xhs_db_mcp._safe_int 的边界值测试。"""

    def test_integer_value(self):
        assert _safe_int(42) == 42

    def test_string_integer(self):
        assert _safe_int("123") == 123

    def test_comma_formatted_number(self):
        assert _safe_int("1,200") == 1200

    def test_large_comma_number(self):
        assert _safe_int("12,000") == 12000

    def test_none_returns_default(self):
        assert _safe_int(None) == 0

    def test_empty_string_returns_default(self):
        assert _safe_int("") == 0

    def test_custom_default(self):
        assert _safe_int(None, default=-1) == -1

    def test_float_string_returns_default(self):
        # "3.5" 无法被 int() 直接转换
        assert _safe_int("3.5") == 0

    def test_wan_suffix_returns_default(self):
        # "1.2万" 非纯数字，无法转换
        assert _safe_int("1.2万") == 0

    def test_negative_integer(self):
        assert _safe_int(-5) == -5

    def test_whitespace_around_number(self):
        assert _safe_int("  99  ") == 99

    def test_zero_string(self):
        assert _safe_int("0") == 0

    def test_zero_int_returns_default(self):
        # 已知边界：_safe_int(0) 因 `if value` 判断，0 被认为是 falsy
        # 实际返回 default（0），结果偶然正确；default 非 0 时会暴露此 bug
        result = _safe_int(0, default=99)
        # 文档化当前行为：0 被视为 falsy，返回 default
        assert result == 99  # 注意：这是已知设计缺陷


# =============================================================================
# _safe_str 单元测试
# =============================================================================
class TestSafeStr:
    """xhs_db_mcp._safe_str 的边界值测试。"""

    def test_normal_string(self):
        assert _safe_str("hello") == "hello"

    def test_none_returns_default(self):
        assert _safe_str(None) == ""

    def test_empty_string_returns_default(self):
        assert _safe_str("") == ""

    def test_custom_default(self):
        assert _safe_str(None, default="N/A") == "N/A"

    def test_strips_surrounding_whitespace(self):
        assert _safe_str("  hello world  ") == "hello world"

    def test_truncation_applied(self):
        long_str = "保" * 300
        result = _safe_str(long_str, max_len=50)
        assert len(result) == 50

    def test_no_truncation_when_shorter_than_max(self):
        assert _safe_str("短字符串", max_len=100) == "短字符串"

    def test_exact_length_not_truncated(self):
        s = "abc"
        assert _safe_str(s, max_len=3) == "abc"

    def test_integer_converted_to_string(self):
        assert _safe_str(42) == "42"

    def test_zero_int_returns_default(self):
        # 已知边界：_safe_str(0) 因 `if value`，0 被视为 falsy
        result = _safe_str(0, default="zero")
        assert result == "zero"  # 文档化当前行为

    def test_unicode_preserved(self):
        assert _safe_str("重疾险攻略") == "重疾险攻略"

    def test_max_len_none_no_truncation(self):
        long_str = "x" * 1000
        assert _safe_str(long_str) == long_str


# =============================================================================
# chunk_text 单元测试
# =============================================================================
class TestChunkText:
    """rag_ingest.chunk_text 文本分块逻辑测试。"""

    def test_empty_string_returns_empty_list(self):
        assert chunk_text("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert chunk_text("   \n  ") == []

    def test_short_text_no_split(self):
        text = "这是一段短于 max_size 的文本"
        result = chunk_text(text, max_size=600)
        assert result == [text]

    def test_exactly_max_size_single_chunk(self):
        text = "a" * 600
        result = chunk_text(text, max_size=600)
        assert len(result) == 1
        assert result[0] == text

    def test_long_text_splits_into_multiple_chunks(self):
        text = "a" * 1200
        result = chunk_text(text, max_size=600, overlap=80)
        assert len(result) == 3  # [0:600], [520:1120], [1040:1200]

    def test_overlap_content_shared_between_adjacent_chunks(self):
        text = "a" * 600 + "b" * 600
        result = chunk_text(text, max_size=600, overlap=80)
        # 第一块尾部 80 字符 == 第二块头部 80 字符
        assert result[0][-80:] == result[1][:80]

    def test_chunks_match_expected_positions(self):
        text = "x" * 700
        result = chunk_text(text, max_size=600, overlap=80)
        step = 600 - 80
        expected = []
        start = 0
        while start < len(text):
            expected.append(text[start: start + 600])
            start += step
        assert result == expected

    def test_default_parameters_split_long_text(self):
        text = "保险内容" * 200  # ~800 chars > default max_size=600
        result = chunk_text(text)
        assert len(result) > 1

    def test_each_chunk_max_size_respected(self):
        text = "x" * 2000
        result = chunk_text(text, max_size=600, overlap=80)
        for chunk in result:
            assert len(chunk) <= 600

    def test_single_char_text(self):
        result = chunk_text("A")
        assert result == ["A"]


# =============================================================================
# table_html_to_text 单元测试
# =============================================================================
class TestTableHtmlToText:
    """rag_ingest.table_html_to_text HTML 表格转可读文本测试。"""

    def test_simple_table_preserves_data(self):
        html = (
            "<table>"
            "<tr><td>重疾险</td><td>1000元</td></tr>"
            "</table>"
        )
        result = table_html_to_text(html)
        assert "重疾险" in result
        assert "1000元" in result

    def test_no_html_tags_in_output(self):
        html = "<table><tr><td>文本内容</td></tr></table>"
        result = table_html_to_text(html)
        assert "<" not in result
        assert ">" not in result

    def test_th_replaced_with_column_header_marker(self):
        html = "<table><tr><th>保险名称</th><th>保费</th></tr></table>"
        result = table_html_to_text(html)
        assert "【列头】" in result

    def test_tr_becomes_newline(self):
        html = (
            "<table>"
            "<tr><td>行1</td></tr>"
            "<tr><td>行2</td></tr>"
            "</table>"
        )
        result = table_html_to_text(html)
        lines = [l for l in result.split("\n") if l.strip()]
        assert len(lines) >= 2

    def test_empty_table_returns_empty_string(self):
        result = table_html_to_text("<table></table>")
        assert result == ""

    def test_multicolumn_table(self):
        html = (
            "<table>"
            "<tr><th>产品</th><th>保额</th><th>年缴保费</th></tr>"
            "<tr><td>宏利优越终身保</td><td>100万</td><td>5000元</td></tr>"
            "</table>"
        )
        result = table_html_to_text(html)
        assert "宏利优越终身保" in result
        assert "100万" in result

    def test_no_extra_blank_lines(self):
        html = "<table><tr><td>A</td></tr><tr><td>B</td></tr></table>"
        result = table_html_to_text(html)
        # 不应有超过 2 个连续换行
        assert "\n\n\n" not in result


# =============================================================================
# _make_doc 单元测试
# =============================================================================
class TestMakeDoc:
    """rag_ingest._make_doc 文档块标准化生成测试。"""

    def _make(self, **kwargs):
        defaults = dict(
            text="测试内容",
            title="测试标题",
            content_type="text",
            pdf_name="test.pdf",
            ingest_time="2024-01-01T00:00:00",
        )
        defaults.update(kwargs)
        return _make_doc(**defaults)

    def test_returns_dict(self):
        doc = self._make()
        assert isinstance(doc, dict)

    def test_text_field_preserved(self):
        doc = self._make(text="重疾险条款说明")
        assert doc["text"] == "重疾险条款说明"

    def test_title_field_preserved_when_short(self):
        doc = self._make(title="保险概要")
        assert doc["title"] == "保险概要"

    def test_title_truncated_to_500(self):
        long_title = "标" * 600
        doc = self._make(title=long_title)
        assert len(doc["title"]) == 500

    def test_url_contains_pdf_name(self):
        doc = self._make(pdf_name="insurance.pdf", content_type="table")
        assert "insurance.pdf" in doc["url"]

    def test_url_contains_content_type(self):
        doc = self._make(content_type="table")
        assert "table" in doc["url"]

    def test_source_is_pdf_mineru(self):
        doc = self._make()
        assert doc["source"] == "pdf_mineru"

    def test_scraped_at_preserved(self):
        doc = self._make(ingest_time="2024-06-15T08:30:00")
        assert doc["scraped_at"] == "2024-06-15T08:30:00"

    def test_content_type_stored(self):
        doc = self._make(content_type="image")
        assert doc["content_type"] == "image"

    def test_required_keys_present(self):
        doc = self._make()
        for key in ("text", "title", "source", "url", "scraped_at", "content_type"):
            assert key in doc


# =============================================================================
# load_xhs_documents 单元测试
# =============================================================================
class TestLoadXhsDocuments:
    """rag_ingest.load_xhs_documents 小红书 JSON 加载测试。"""

    def _write_tmp_json(self, data) -> str:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(data, f, ensure_ascii=False)
        f.close()
        return f.name

    def test_nonexistent_file_returns_empty(self):
        result = load_xhs_documents("/tmp/nonexistent_xhs_file_xyz.json")
        assert result == []

    def test_empty_array_returns_empty(self):
        path = self._write_tmp_json([])
        assert load_xhs_documents(path) == []

    def test_single_post_loaded(self):
        posts = [{"title": "重疾险怎么选", "content": "选购攻略...", "url": "https://example.com"}]
        path = self._write_tmp_json(posts)
        result = load_xhs_documents(path)
        assert len(result) >= 1
        assert result[0]["source"] == "xiaohongshu"

    def test_post_title_included_in_text(self):
        posts = [{"title": "重疾险选购", "content": "正文内容", "url": ""}]
        path = self._write_tmp_json(posts)
        result = load_xhs_documents(path)
        assert any("重疾险选购" in doc["text"] for doc in result)

    def test_long_post_splits_into_multiple_chunks(self):
        long_content = "保险内容详解" * 200  # 超过 CHUNK_SIZE=600
        posts = [{"title": "长文章", "content": long_content, "url": ""}]
        path = self._write_tmp_json(posts)
        result = load_xhs_documents(path)
        assert len(result) > 1

    def test_post_without_title_uses_placeholder(self):
        posts = [{"title": "", "content": "无标题帖子内容", "url": ""}]
        path = self._write_tmp_json(posts)
        result = load_xhs_documents(path)
        assert len(result) >= 1
        assert result[0]["title"] == "（无标题）"

    def test_empty_content_post_skipped(self):
        posts = [{"title": "", "content": "", "url": ""}]
        path = self._write_tmp_json(posts)
        result = load_xhs_documents(path)
        assert result == []

    def test_url_stored_in_doc(self):
        url = "https://www.xiaohongshu.com/explore/abc123"
        posts = [{"title": "标题", "content": "内容", "url": url}]
        path = self._write_tmp_json(posts)
        result = load_xhs_documents(path)
        assert result[0]["url"] == url

    def test_scraped_at_from_post(self):
        posts = [{"title": "标", "content": "内", "url": "", "scraped_at": "2024-03-01T00:00:00"}]
        path = self._write_tmp_json(posts)
        result = load_xhs_documents(path)
        assert result[0]["scraped_at"] == "2024-03-01T00:00:00"

    def test_multiple_posts_all_loaded(self):
        posts = [
            {"title": f"帖子{i}", "content": f"内容{i}", "url": ""}
            for i in range(5)
        ]
        path = self._write_tmp_json(posts)
        result = load_xhs_documents(path)
        assert len(result) == 5

    def test_content_type_is_text(self):
        posts = [{"title": "测试", "content": "内容", "url": ""}]
        path = self._write_tmp_json(posts)
        result = load_xhs_documents(path)
        assert result[0]["content_type"] == "text"


# =============================================================================
# NVIDIAEmbeddingAdapter 单元测试
# =============================================================================
class TestNVIDIAEmbeddingAdapter:
    """rag_mcp.NVIDIAEmbeddingAdapter LangChain 适配器接口测试。"""

    def setup_method(self):
        """每个测试前创建 mock embedder 和 adapter 实例。"""
        self.mock_nvidia = MagicMock()
        self.mock_nvidia.get_text_embedding.return_value = [0.1] * 1024
        self.mock_nvidia.get_text_embedding_batch.return_value = [
            [0.1] * 1024,
            [0.2] * 1024,
        ]
        self.adapter = NVIDIAEmbeddingAdapter(self.mock_nvidia)

    # ── 同步接口 ──────────────────────────────────────────────────────────────

    def test_embed_query_returns_list(self):
        result = self.adapter.embed_query("重疾险问题")
        assert isinstance(result, list)

    def test_embed_query_returns_1024_dims(self):
        result = self.adapter.embed_query("测试查询")
        assert len(result) == 1024

    def test_embed_query_delegates_to_underlying(self):
        self.adapter.embed_query("保险查询")
        self.mock_nvidia.get_text_embedding.assert_called_once_with("保险查询")

    def test_embed_documents_returns_list_of_vectors(self):
        result = self.adapter.embed_documents(["文本1", "文本2"])
        assert isinstance(result, list)
        assert len(result) == 2

    def test_embed_documents_each_vector_1024_dims(self):
        result = self.adapter.embed_documents(["文本A", "文本B"])
        for vec in result:
            assert len(vec) == 1024

    def test_embed_documents_calls_batch_method(self):
        texts = ["文本A", "文本B"]
        self.adapter.embed_documents(texts)
        self.mock_nvidia.get_text_embedding_batch.assert_called_once_with(texts)

    def test_embed_single_document(self):
        self.mock_nvidia.get_text_embedding_batch.return_value = [[0.5] * 1024]
        result = self.adapter.embed_documents(["单文本"])
        assert len(result) == 1
        assert len(result[0]) == 1024

    # ── 异步接口 ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_aembed_query_returns_list(self):
        result = await self.adapter.aembed_query("异步查询")
        assert isinstance(result, list)
        assert len(result) == 1024

    @pytest.mark.asyncio
    async def test_aembed_query_delegates_to_sync(self):
        await self.adapter.aembed_query("保险异步")
        self.mock_nvidia.get_text_embedding.assert_called_once_with("保险异步")

    @pytest.mark.asyncio
    async def test_aembed_documents_returns_list_of_vectors(self):
        result = await self.adapter.aembed_documents(["异步文本1", "异步文本2"])
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_aembed_documents_calls_batch(self):
        texts = ["异步A", "异步B"]
        await self.adapter.aembed_documents(texts)
        self.mock_nvidia.get_text_embedding_batch.assert_called_once_with(texts)

    @pytest.mark.asyncio
    async def test_aembed_query_is_awaitable(self):
        # 验证返回值是 coroutine（已被 await）
        coro = self.adapter.aembed_query("测试可等待")
        # 如果不可 await，以下会抛出 TypeError
        result = await coro
        assert isinstance(result, list)


# =============================================================================
# agent_browser_mcp 会话工具单元测试
# =============================================================================
class TestAgentBrowserSessionTools:
    """
    验证 agent_browser_mcp 中新增的 state_load / state_save 工具
    以及 --session-name xhs 注入是否正确。
    不依赖真实浏览器，全部使用 mock subprocess。
    """

    def setup_method(self):
        """每个测试前重置 mock。"""
        import unittest.mock as mock
        self._mock_patcher = mock.patch("agent_browser_mcp.subprocess.run")
        self.mock_run = self._mock_patcher.start()
        # 默认返回成功结果
        self.mock_run.return_value = mock.MagicMock(
            stdout="OK",
            stderr="",
            returncode=0,
        )

    def teardown_method(self):
        self._mock_patcher.stop()

    def _get_call_args(self) -> list[str]:
        """获取最后一次 subprocess.run 调用的命令参数列表。"""
        return self.mock_run.call_args[0][0]

    def test_navigate_includes_session_name(self):
        """navigate 工具必须包含 --session-name xhs。"""
        from agent_browser_mcp import navigate
        navigate("https://www.xiaohongshu.com")
        args = self._get_call_args()
        assert "--session-name" in args
        assert "xhs" in args
        assert "open" in args
        assert "https://www.xiaohongshu.com" in args

    def test_snapshot_includes_session_name(self):
        """snapshot 工具必须包含 --session-name xhs。"""
        from agent_browser_mcp import snapshot
        snapshot()
        args = self._get_call_args()
        assert "--session-name" in args
        assert "xhs" in args
        assert "snapshot" in args

    def test_click_includes_session_name(self):
        """click 工具必须包含 --session-name xhs。"""
        from agent_browser_mcp import click
        click("@e1")
        args = self._get_call_args()
        assert "--session-name" in args
        assert "xhs" in args
        assert "click" in args
        assert "@e1" in args

    def test_type_text_includes_session_name(self):
        """type_text 工具必须包含 --session-name xhs。"""
        from agent_browser_mcp import type_text
        type_text("@e2", "保险")
        args = self._get_call_args()
        assert "--session-name" in args
        assert "xhs" in args
        assert "type" in args
        assert "保险" in args

    def test_press_key_includes_session_name(self):
        """press_key 工具必须包含 --session-name xhs。"""
        from agent_browser_mcp import press_key
        press_key("Enter")
        args = self._get_call_args()
        assert "--session-name" in args
        assert "xhs" in args
        assert "press" in args
        assert "Enter" in args

    def test_state_save_correct_args(self):
        """state_save 工具必须以正确参数调用 agent-browser。"""
        from agent_browser_mcp import state_save
        state_save("/tmp/test_state.json")
        args = self._get_call_args()
        assert "--session-name" in args
        assert "xhs" in args
        assert "state" in args
        assert "save" in args
        assert "/tmp/test_state.json" in args

    def test_state_load_file_not_exist_returns_warning(self):
        """state_load 在文件不存在时应返回提示信息而非异常。"""
        from agent_browser_mcp import state_load
        result = state_load("/tmp/nonexistent_xhs_state_xyz.json")
        assert isinstance(result, str)
        assert "不存在" in result or "not exist" in result.lower() or "文件" in result

    def test_state_load_with_existing_file(self, tmp_path):
        """state_load 在文件存在时调用 agent-browser state load。"""
        import unittest.mock as mock
        state_file = tmp_path / "xhs_state.json"
        state_file.write_text('{"cookies": []}')

        # state_load 不使用 _run（不带 session args），直接调用
        self.mock_run.return_value = mock.MagicMock(
            stdout="Loaded state from file",
            stderr="",
            returncode=0,
        )
        from agent_browser_mcp import state_load
        result = state_load(str(state_file))
        assert isinstance(result, str)
        # 确认调用了 agent-browser state load
        args = self._get_call_args()
        assert "state" in args
        assert "load" in args
        assert str(state_file) in args


# =============================================================================
# OpenAI-Compatible API Endpoints 单元测试
# =============================================================================
class TestOpenAIChatEndpoints:
    """测试 api.py 中为 NeMo Agent Toolkit UI 添加的 OpenAI 兼容端点。

    使用 FastAPI TestClient，不依赖外部服务（通过 mock LLM 和 Milvus）。
    """

    @pytest.fixture(autouse=True)
    def setup_test_client(self):
        """Set up TestClient with mocked dependencies."""
        from unittest.mock import patch, MagicMock
        import api as api_module

        # Mock the LLM client
        mock_llm = MagicMock()
        self._mock_llm = mock_llm

        # Mock NVIDIA_API_KEY to pass validation, and _search_knowledge_base to avoid Milvus
        with patch.object(api_module, "llm_client", mock_llm), \
             patch.object(api_module, "NVIDIA_API_KEY", "nvapi-real-key-for-test"), \
             patch.object(api_module, "_search_knowledge_base", return_value=""):
            from fastapi.testclient import TestClient
            self.client = TestClient(api_module.app)
            self._patches = [
                patch.object(api_module, "llm_client", mock_llm),
                patch.object(api_module, "NVIDIA_API_KEY", "nvapi-real-key-for-test"),
                patch.object(api_module, "_search_knowledge_base", return_value=""),
            ]
            for p in self._patches:
                p.start()
            yield
            for p in self._patches:
                p.stop()

    def test_chat_stream_endpoint_exists(self):
        """POST /chat/stream 端点应当存在并接受 OpenAI 格式请求。"""
        from unittest.mock import MagicMock

        # Mock streaming response
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta.content = "Hello"

        mock_done = MagicMock()
        mock_done.choices = [MagicMock()]
        mock_done.choices[0].delta.content = ""

        self._mock_llm.chat.completions.create.return_value = [mock_chunk, mock_done]

        response = self.client.post("/chat/stream", json={
            "messages": [{"role": "user", "content": "什么是保险？"}],
            "model": "test-model",
            "stream": True,
        })
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    def test_chat_endpoint_exists(self):
        """POST /chat 端点应当存在并返回 OpenAI 格式的响应。"""
        from unittest.mock import MagicMock

        # Mock non-streaming response
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "保险是一种风险管理工具。"
        self._mock_llm.chat.completions.create.return_value = mock_resp

        response = self.client.post("/chat", json={
            "messages": [{"role": "user", "content": "什么是保险？"}],
            "model": "test-model",
            "stream": False,
        })
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert "保险" in data["choices"][0]["message"]["content"]

    def test_chat_endpoint_empty_messages(self):
        """POST /chat 应当对空消息列表返回 400 错误。"""
        response = self.client.post("/chat", json={
            "messages": [],
            "model": "test-model",
        })
        assert response.status_code == 400

    def test_chat_stream_empty_messages(self):
        """POST /chat/stream 应当对空消息列表返回 400 错误。"""
        response = self.client.post("/chat/stream", json={
            "messages": [],
            "model": "test-model",
        })
        assert response.status_code == 400

    def test_chat_response_has_openai_structure(self):
        """验证 /chat 响应符合 OpenAI Chat Completions 格式。"""
        from unittest.mock import MagicMock

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "Test response"
        self._mock_llm.chat.completions.create.return_value = mock_resp

        response = self.client.post("/chat", json={
            "messages": [{"role": "user", "content": "test"}],
        })
        data = response.json()
        assert "id" in data
        assert data["id"].startswith("chatcmpl-")
        assert data["object"] == "chat.completion"
        assert data["choices"][0]["finish_reason"] == "stop"

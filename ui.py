"""
ui.py  ·  保险 RAG 智能问答系统 - 稳定版 (Gradio)
访问地址：http://localhost:8080
"""

import os
import shutil
import time
from pathlib import Path
import gradio as gr
from openai import OpenAI
import rag_ingest as ri

# ─── 环境配置 ─────────────────────────────────────────────────────────────────
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
MILVUS_HOST   = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT   = os.environ.get("MILVUS_PORT", "19530")

UPLOAD_DIR = Path("/app/data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_KB = "insurance_docs"

llm_client = OpenAI(
    api_key=NVIDIA_API_KEY,
    base_url="https://integrate.api.nvidia.com/v1",
)

# ─── 国际化 (i18n) ─────────────────────────────────────────────────────────────
TRANSLATIONS = {
    "EN": {
        "app_title": "# 🛡️ Insurance RAG Q&A System",
        "tab_chat": "💬 Chat",
        "tab_kb": "📚 Knowledge Base",
        "send_btn": "Send",
        "clear_btn": "Clear",
        "kb_select": "Select KB",
        "kb_upload": "Upload PDF",
        "kb_ingest": "Start Ingest",
        "kb_refresh": "Refresh",
        "kb_status": "KB Status",
        "kb_docs": "Documents",
        "kb_delete": "Delete Selected",
    },
    "繁中": {
        "app_title": "# 🛡️ 保險 RAG 智能問答系統",
        "tab_chat": "💬 智能對話",
        "tab_kb": "📚 知識庫管理",
        "send_btn": "發送",
        "clear_btn": "清除",
        "kb_select": "選擇知識庫",
        "kb_upload": "上傳 PDF",
        "kb_ingest": "開始入庫",
        "kb_refresh": "刷新狀態",
        "kb_status": "知識库狀態",
        "kb_docs": "已存檔文件",
        "kb_delete": "刪除所選",
    },
    "简中": {
        "app_title": "# 🛡️ 保险 RAG 智能问答系统",
        "tab_chat": "💬 智能对话",
        "tab_kb": "📚 知识库管理",
        "send_btn": "发送",
        "clear_btn": "清除",
        "kb_select": "选择知识库",
        "kb_upload": "上传 PDF",
        "kb_ingest": "开始入库",
        "kb_refresh": "刷新状态",
        "kb_status": "知识库状态",
        "kb_docs": "已存档文件",
        "kb_delete": "删除所选",
    }
}

# ─── 后端逻辑 ─────────────────────────────────────────────────────────────────

def list_kb_collections():
    try:
        client = ri.get_milvus_client()
        cols = client.list_collections()
        return cols if cols else [DEFAULT_KB]
    except:
        return [DEFAULT_KB]

def get_kb_status(collection):
    try:
        client = ri.get_milvus_client()
        stats = client.get_collection_stats(collection)
        row_count = stats.get("row_count", 0)
        return f"Collection: {collection}\nRows: {row_count}"
    except Exception as e:
        return f"Error: {str(e)}"

def list_kb_documents(collection):
    try:
        client = ri.get_milvus_client()
        res = client.query(
            collection_name=collection,
            filter="pk >= 0",
            output_fields=["source"],
            limit=10000,
        )
        if not res:
            return []
        # 兼容 list of dict 或 list of 其他结构
        sources = set()
        for r in res:
            if isinstance(r, dict):
                s = r.get("source") or r.get("entity", {}).get("source")
            else:
                s = getattr(r, "source", None)
            if s:
                sources.add(s)
        return [[s] for s in sorted(sources)]
    except Exception:
        return []

def upload_and_ingest(files, collection, use_mineru, clear_first):
    if not files:
        yield "❌ No files uploaded."
        return

    client = ri.get_milvus_client()
    embedder = ri.get_embedder()
    
    if clear_first:
        yield f"🧹 Clearing collection {collection}..."
        try:
            client.drop_collection(collection_name=collection)
        except: pass

    ri.ensure_collection(client, collection_name=collection)

    for f in files:
        fname = os.path.basename(f.name)
        yield f"📖 Processing {fname}..."
        target_path = UPLOAD_DIR / fname
        shutil.copy(f.name, target_path)
        
        # 调用入库
        try:
            if use_mineru:
                gen = ri.load_pdf_documents(str(target_path), use_mineru=True)
                docs = None
                try:
                    while True:
                        next(gen)
                except StopIteration as e:
                    docs = e.value if e.value is not None else []
                if not docs:
                    docs = ri.load_pdf_with_pypdf(str(target_path))
            else:
                docs = ri.load_pdf_with_pypdf(str(target_path))
            ri.embed_and_insert(
                client, embedder, docs,
                source_label=fname,
                collection_name=collection,
            )
            yield f"✅ {fname} ingested successfully."
        except Exception as e:
            yield f"❌ Error processing {fname}: {str(e)}"

def chat_stream(message, history, collection):
    try:
        client = ri.get_milvus_client()
        embedder = ri.get_embedder()
    except Exception as e:
        yield f"⚠️ 初始化失败：{e}"
        return

    try:
        query_vec = embedder.get_text_embedding(message)
        search_res = client.search(
            collection_name=collection,
            data=[query_vec],
            limit=25,
            output_fields=["text", "source", "title"],
        )
    except Exception as e:
        yield f"⚠️ 检索失败：{e}"
        return

    # PyMilvus 2.x: 返回 List[List[dict]]，每个 dict 含 output_fields（如 text）及 distance
    hits = search_res[0] if search_res else []
    def get_text(h):
        t = h.get("text")
        if t is not None and str(t).strip():
            return str(t).strip()
        ent = h.get("entity") or {}
        t = ent.get("text") if isinstance(ent, dict) else None
        return str(t).strip() if t else ""

    # 过滤低质量片段：页眉/页脚、过短碎片、纯产品代码（这些会导致“信息有限且模糊”）
    MIN_CHUNK_LEN = 80
    def is_useful(chunk):
        if not chunk or len(chunk) < MIN_CHUNK_LEN:
            return False
        s = chunk.strip()
        if s.lower() in ("ia", "um paid)"):
            return False
        if s in ("One Prime 3 - Essence", "MKTPP151E (11/2025)"):
            return False
        words = s.split()
        if len(words) <= 5 and len(set(words)) <= 2:
            return False
        return True

    raw_parts = [get_text(h) for h in hits]
    context_parts = [p for p in raw_parts if is_useful(p)]
    if not context_parts and raw_parts:
        context_parts = [p for p in raw_parts if len(p) >= 30]
    context = "\n\n".join(context_parts).strip() if context_parts else "（知识库中暂无与问题相关的保险条款内容。建议：1）在「知识库管理」中勾选「使用 MinerU 解析」后重新上传 manupremier-protector.pdf 并入库；2）若曾用 pypdf 入库，页眉页脚会重复导致质量差，请清空后改用 MinerU 重新入库。）"

    prompt = (
        "你是一名保险知识助手。请**仅根据**下面「知识库」中的内容（来自 ManuPremier Protector 等保险产品资料）回答用户问题。\n"
        "若知识库中有相关内容，请用简洁清晰的语言作答；若没有相关内容，请说明知识库中暂无该信息，不要编造。\n\n"
        "【知识库】\n" + context + "\n\n【用户问题】" + message + "\n\n【回答】"
    )

    try:
        response = llm_client.chat.completions.create(
            model="minimaxai/minimax-m2.1",
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            top_p=0.95,
            max_tokens=8192,
            stream=True,
        )
    except Exception as e:
        yield f"⚠️ 模型调用失败：{e}"
        return

    full_resp = ""
    for chunk in response:
        if not getattr(chunk, "choices", None) or not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta is not None and getattr(delta, "content", None) is not None:
            full_resp += delta.content
            yield full_resp

# ─── UI 界面 ──────────────────────────────────────────────────────────────────

with gr.Blocks(title="Insurance RAG") as demo:
    lang_state = gr.State("简中")
    kb_state = gr.State(DEFAULT_KB)

    with gr.Row():
        title = gr.Markdown(TRANSLATIONS["简中"]["app_title"])
        lang_radio = gr.Radio(choices=["EN", "繁中", "简中"], value="简中", label="Language", container=False)

    with gr.Tabs() as tabs:
        # Chat Tab
        with gr.Tab(TRANSLATIONS["简中"]["tab_chat"], id="chat_tab") as chat_tab:
            chatbot = gr.Chatbot(height=500)
            with gr.Row():
                msg = gr.Textbox(placeholder="Ask me anything...", scale=9)
                send = gr.Button("Send", scale=1)
            clear = gr.Button("Clear Chat")
            
            def user(user_message, history):
                return "", history + [[user_message, None]]

            def bot(history, kb):
                user_message = history[-1][0]
                bot_message = chat_stream(user_message, history[:-1], kb)
                history[-1][1] = ""
                for character in bot_message:
                    history[-1][1] = character
                    yield history

            msg.submit(user, [msg, chatbot], [msg, chatbot], queue=False).then(bot, [chatbot, kb_state], chatbot)
            send.click(user, [msg, chatbot], [msg, chatbot], queue=False).then(bot, [chatbot, kb_state], chatbot)
            clear.click(lambda: None, None, chatbot, queue=False)

        # KB Tab
        with gr.Tab(TRANSLATIONS["简中"]["tab_kb"], id="kb_tab") as kb_tab:
            with gr.Row():
                with gr.Column(scale=1):
                    kb_selector = gr.Dropdown(choices=list_kb_collections(), value=DEFAULT_KB, label="Knowledge Base")
                    kb_refresh = gr.Button("Refresh")
                    kb_status = gr.Textbox(label="Status", lines=3)
                
                with gr.Column(scale=2):
                    file_upload = gr.File(label="Upload PDF", file_count="multiple", file_types=[".pdf"])
                    with gr.Row():
                        use_mineru = gr.Checkbox(label="Use MinerU", value=False)
                        clear_first = gr.Checkbox(label="Clear KB First", value=False)
                    ingest_btn = gr.Button("🚀 Start Ingestion", variant="primary")
                    log_output = gr.Textbox(label="Ingestion Log", lines=5)

            with gr.Row():
                doc_list = gr.Dataframe(headers=["Document Name"], label="Documents in KB")
                doc_refresh = gr.Button("🔄 Refresh List")

            # KB Events
            kb_refresh.click(get_kb_status, inputs=kb_selector, outputs=kb_status)
            kb_selector.change(lambda x: x, inputs=kb_selector, outputs=kb_state)
            ingest_btn.click(upload_and_ingest, [file_upload, kb_selector, use_mineru, clear_first], log_output)
            doc_refresh.click(list_kb_documents, inputs=kb_selector, outputs=doc_list)

    # Language Switcher
    def change_language(lang):
        t = TRANSLATIONS[lang]
        return [
            lang,
            gr.update(value=t["app_title"]),
            gr.update(label=t["tab_chat"]),
            gr.update(label=t["tab_kb"]),
            gr.update(value=t["send_btn"]),
            gr.update(value=t["clear_btn"]),
            gr.update(label=t["kb_select"]),
            gr.update(value=t["kb_refresh"]),
            gr.update(label=t["kb_status"]),
            gr.update(label=t["kb_upload"]),
            gr.update(value=t["kb_ingest"]),
            gr.update(label=t["kb_docs"]),
            gr.update(value=t["kb_refresh"]),
        ]

    lang_radio.change(change_language, inputs=lang_radio, outputs=[
        lang_state, title, chat_tab, kb_tab, send, clear, kb_selector, kb_refresh, kb_status, file_upload, ingest_btn, doc_list, doc_refresh
    ])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=7860)

import os
import shutil
import sys
import json
import subprocess
import threading
import traceback
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import OpenAI

# ─── 环境配置 ─────────────────────────────────────────────────────────────────
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
MILVUS_HOST   = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT   = os.environ.get("MILVUS_PORT", "19530")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_DB   = os.environ.get("POSTGRES_DB", "xhs_data")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "xhs_user")
POSTGRES_PASS = os.environ.get("POSTGRES_PASSWORD", "xhs_secure_pass")

UPLOAD_DIR = Path("/app/data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_KB = "insurance_docs"

llm_client = OpenAI(
    api_key=NVIDIA_API_KEY,
    base_url="https://integrate.api.nvidia.com/v1",
)

app = FastAPI(title="Insurance RAG API", description="Backend API for Insurance RAG Q&A System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """将未捕获异常转为 500 JSON 响应，便于前端展示 detail。HTTPException 交给 FastAPI 默认处理。"""
    from fastapi import HTTPException as HTTPEx
    from fastapi.responses import JSONResponse
    if isinstance(exc, HTTPEx):
        raise exc
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


# ─── Milvus & Postgres Helpers ────────────────────────────────────────────────
def _milvus():
    from pymilvus import MilvusClient
    return MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}")

def _pg_conn():
    import psycopg2
    return psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        dbname=POSTGRES_DB, user=POSTGRES_USER,
        password=POSTGRES_PASS, connect_timeout=5,
    )

def get_file_metadata(collection: str, filename: str) -> dict:
    try:
        import psycopg2.extras
        conn = _pg_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT display_name, summary FROM kb_documents WHERE collection_name = %s AND filename = %s",
                (collection, filename)
            )
            row = cur.fetchone()
        conn.close()
        if row:
            return dict(row)
    except Exception as e:
        print(f"Error reading metadata from pg: {e}")
    return {"display_name": filename, "summary": "Waiting for summary..."}

def update_file_metadata(collection: str, filename: str, display_name: str, summary: str):
    try:
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO kb_documents (collection_name, filename, display_name, summary, created_at, updated_at)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (collection_name, filename) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    summary = EXCLUDED.summary,
                    updated_at = NOW();
            """, (collection, filename, display_name, summary))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating metadata in pg: {e}")

def generate_summary_with_glm(text: str) -> str:
    try:
        prompt = "Please summarize the core content of the following document in a concise paragraph (within 50 words) based on the text. If the text is Chinese, use Chinese. Text:\n" + text[:3000]
        resp = llm_client.chat.completions.create(
            model="minimaxai/minimax-m2.1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1024,
        )
        msg = resp.choices[0].message
        content = msg.content or getattr(msg, "reasoning", "") or ""
        return content.strip() or "No summary generated."
    except Exception as e:
        return f"Summary failed: {e}"

# ─── API Models ───────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    lang: str = "简中"
    kb_name: str = DEFAULT_KB
    selected_docs: Optional[List[str]] = None

class CreateCollectionRequest(BaseModel):
    name: str

class UpdateMetadataRequest(BaseModel):
    filename: str
    display_name: str
    summary: str

class DeleteDocumentsRequest(BaseModel):
    filenames: List[str]

# ─── Chat Endpoints ───────────────────────────────────────────────────────────
def _get_hit_field(hit: dict, field: str) -> str:
    """兼容 hit 顶层与 entity 内两种结构（MilvusClient 不同版本）。"""
    v = hit.get(field)
    if v is not None and str(v).strip():
        return str(v).strip()
    e = hit.get("entity") or {}
    v = e.get(field) if isinstance(e, dict) else None
    return str(v).strip() if v is not None else ""


def _search_knowledge_base(query: str, collection: str = DEFAULT_KB, selected_docs: list[str] = None) -> str:
    try:
        from llama_index.embeddings.nvidia import NVIDIAEmbedding
        client = _milvus()
        if collection not in client.list_collections():
            return ""
        embedder = NVIDIAEmbedding(
            model="nvidia/nv-embedqa-e5-v5",
            api_key=NVIDIA_API_KEY,
            base_url="https://integrate.api.nvidia.com/v1",
        )
        vec = embedder.get_text_embedding(query)
        
        search_params = {
            "collection_name": collection,
            "data": [vec],
            "limit": 25,
            "output_fields": ["text", "title", "source"],
        }
        
        if selected_docs:
            filters = []
            for doc in selected_docs:
                filters.append(f'(source like "%:{doc}" or source == "{doc}")')
            expr = " or ".join(filters)
            search_params["filter"] = expr
            
        results = client.search(**search_params)
        
        if not results or not results[0]:
            return ""
        parts = []
        for i, hit in enumerate(results[0], 1):
            title = _get_hit_field(hit, "title")
            source = _get_hit_field(hit, "source")
            text = _get_hit_field(hit, "text")
            parts.append(f"【{i}】{title}（来源：{source}）\n{text}")
        return "\n\n".join(parts)
    except Exception as exc:
        return f"[检索异常: {exc}]"

@app.post("/api/chat")
async def chat_stream_api(req: ChatRequest):
    try:
        if not NVIDIA_API_KEY or NVIDIA_API_KEY.startswith("nvapi-test"):
            raise HTTPException(status_code=400, detail="No valid NVIDIA_API_KEY configured.")

        if not req.messages:
            raise HTTPException(status_code=400, detail="messages 不能为空")

        user_msg = req.messages[-1].content
        history = req.messages[:-1]

        import asyncio
        loop = asyncio.get_event_loop()
        context = await loop.run_in_executor(
            None, _search_knowledge_base, user_msg, req.kb_name, req.selected_docs
        )
        ctx_len = len(context)
        ctx_ok = bool(context) and not context.startswith("[检索异常")
        print(f"[chat] kb={req.kb_name} retrieval_ok={ctx_ok} context_len={ctx_len}")

        system_prompt = (
            "你是一位专业的保险顾问 AI，擅长解读保险条款和提供保险建议。\n"
            "请根据提供的参考资料回答用户的保险问题。\n\n"
            "要求：\n"
            "- 结构清晰（适当使用标题和列表）\n"
            "- 优先基于参考资料回答，并注明出处\n"
            "- 不要虚构保险条款或数据\n"
            "- 涉及产品推荐时，说明仅供参考，建议咨询专业顾问"
        )
        if req.lang == "EN":
            system_prompt = (
                "You are a professional insurance advisor AI. Answer insurance questions in English.\n"
                "Requirements:\n"
                "- Use English, structured and clear (use headings and bullet points)\n"
                "- Prioritise answers based on reference materials, cite sources\n"
                "- Do not fabricate insurance clauses or data\n"
                "- For product recommendations, note they are for reference only"
            )
        elif req.lang == "繁中":
            system_prompt = (
                "你是一位專業的保險顧問 AI，擅長解讀保險條款和提供保險建議。\n"
                "請根據提供的參考資料，以繁體中文回答用戶的保險問題。\n\n"
                "要求：\n"
                "- 使用繁體中文，結構清晰（適當使用標題和列表）\n"
                "- 優先基於參考資料回答，並注明出處\n"
                "- 不要虛構保險條款或數據\n"
                "- 涉及產品推薦時，說明僅供參考，建議咨詢專業顧問"
            )

        api_messages = [{"role": "system", "content": system_prompt}]
        for msg in history[-12:]:
            api_messages.append({"role": msg.role, "content": msg.content})

        if context and not context.startswith("[检索异常"):
            pfx = "以下是从保险知识库检索到的相关内容，请参考回答："
            if req.lang == "EN":
                pfx = "Reference materials from KB:"
            elif req.lang == "繁中":
                pfx = "以下是從保險知識庫檢索到的相關內容，請參考回答："
            user_content = f"{pfx}\n\n{context}\n\n---\n\n{user_msg}"
        else:
            user_content = user_msg

        api_messages.append({"role": "user", "content": user_content})

        async def generate():
            try:
                import asyncio
                import threading
                loop = asyncio.get_event_loop()
                queue: asyncio.Queue = asyncio.Queue()

                def _stream_to_queue():
                    try:
                        stream = llm_client.chat.completions.create(
                            model="minimaxai/minimax-m2.1",
                            messages=api_messages,
                            temperature=0.2,
                            stream=True,
                            max_tokens=2048,
                        )
                        for chunk in stream:
                            if not getattr(chunk, "choices", None):
                                continue
                            d = chunk.choices[0].delta
                            delta = (d.content or getattr(d, "reasoning", None) or "").__str__()
                            if delta:
                                asyncio.run_coroutine_threadsafe(queue.put(("content", delta)), loop)
                    except Exception as exc:
                        asyncio.run_coroutine_threadsafe(queue.put(("error", str(exc))), loop)
                    finally:
                        asyncio.run_coroutine_threadsafe(queue.put(("done", None)), loop)

                thread = threading.Thread(target=_stream_to_queue, daemon=True)
                thread.start()

                while True:
                    kind, value = await queue.get()
                    if kind == "done":
                        break
                    elif kind == "error":
                        print(f"[chat] llm_error: {value}")
                        yield f"data: {json.dumps({'error': value})}\n\n"
                    else:
                        yield f"data: {json.dumps({'content': value})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as exc:
                print(f"[chat] llm_error: {exc}")
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))

# ─── Knowledge Base Endpoints ─────────────────────────────────────────────────
@app.get("/api/kb/collections")
def list_collections():
    try:
        cols = _milvus().list_collections()
        if not cols:
            cols = [DEFAULT_KB]
        return {"collections": cols}
    except Exception as e:
        return {"collections": [DEFAULT_KB], "error": str(e)}

@app.post("/api/kb/collections")
def create_collection(req: CreateCollectionRequest):
    name = req.name.strip()
    if not name or not name.replace("_", "").isalnum():
        raise HTTPException(400, "Invalid collection name")
    try:
        sys.path.insert(0, "/app")
        from rag_ingest import ensure_collection
        client = _milvus()
        if name in client.list_collections():
            return {"message": f"Knowledge base '{name}' already exists", "status": "exists"}
        ensure_collection(client, collection_name=name)
        return {"message": f"Knowledge base '{name}' created", "status": "created"}
    except Exception as exc:
        raise HTTPException(500, str(exc))

@app.get("/api/kb/collections/{collection}/status")
def get_status(collection: str):
    try:
        client = _milvus()
        if collection not in client.list_collections():
            return {"status": "Not Found", "message": f"Collection '{collection}' does not exist."}
        stats  = client.get_collection_stats(collection)
        schema = client.describe_collection(collection)
        row_count = int(stats.get("row_count", 0))
        dim = next((f["params"]["dim"] for f in schema["fields"] if f["name"] == "vector"), "?")
        status = "Active" if row_count > 0 else "Empty"
        return {
            "status": status,
            "collection": collection,
            "vectors": row_count,
            "dimension": dim,
            "embedding": "nvidia/nv-embedqa-e5-v5",
            "milvus": f"{MILVUS_HOST}:{MILVUS_PORT}"
        }
    except Exception as exc:
        raise HTTPException(500, str(exc))

@app.get("/api/kb/collections/{collection}/documents")
def get_documents(collection: str):
    try:
        client = _milvus()
        if collection not in client.list_collections():
            return {"documents": []}
        results = client.query(
            collection_name=collection,
            filter="id >= 0",
            output_fields=["source"],
            limit=16384,
        )
        if not results:
            return {"documents": []}

        doc_set = set()
        for r in results:
            src = r.get("source", "unknown")
            if ":" in src:
                _, fname = src.split(":", 1)
            else:
                fname = src
            doc_set.add(fname)

        rows = []
        for fname in sorted(doc_set):
            fmeta = get_file_metadata(collection, fname)
            disp_name = fmeta.get("display_name", fname)
            summary = fmeta.get("summary", "No summary")
            rows.append({"filename": fname, "display_name": disp_name, "summary": summary})
        return {"documents": rows}
    except Exception as exc:
        raise HTTPException(500, str(exc))

@app.delete("/api/kb/collections/{collection}/documents")
def delete_documents(collection: str, req: DeleteDocumentsRequest):
    filenames = [f.strip() for f in req.filenames if f.strip()]
    if not filenames:
        raise HTTPException(400, "No filenames provided")
    try:
        client = _milvus()
        if collection not in client.list_collections():
            raise HTTPException(404, f"Knowledge base '{collection}' does not exist")
        deleted_total = 0
        for fname in filenames:
            for engine in ("pdf_mineru", "pdf_pypdf", "xiaohongshu"):
                src = f"{engine}:{fname}"
                try:
                    client.delete(collection_name=collection, filter=f'source == "{src}"')
                    deleted_total += 1
                except Exception:
                    pass
            # optionally delete from pg metadata as well
            try:
                conn = _pg_conn()
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM kb_documents WHERE collection_name = %s AND filename = %s", (collection, fname))
                    conn.commit()
                conn.close()
            except:
                pass
        return {"message": f"Deleted vectors for {len(filenames)} files", "deleted": deleted_total}
    except Exception as exc:
        raise HTTPException(500, str(exc))

@app.post("/api/kb/collections/{collection}/documents/metadata")
def update_metadata(collection: str, req: UpdateMetadataRequest):
    try:
        update_file_metadata(collection, req.filename, req.display_name, req.summary)
        return {"message": "Metadata updated successfully"}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/kb/collections/{collection}/documents/summarize")
async def generate_summaries(collection: str):
    async def generate():
        try:
            client = _milvus()
            if collection not in client.list_collections():
                yield f"data: {json.dumps({'error': f'Collection {collection} not found'})}\n\n"
                return
                
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT filename FROM kb_documents WHERE collection_name = %s AND (summary = '' OR summary = 'Waiting for summary...' OR summary = 'No summary generated.')",
                    (collection,)
                )
                rows = cur.fetchall()
                cur.execute("SELECT filename FROM kb_documents WHERE collection_name = %s", (collection,))
                existing_pg_files = {r[0] for r in cur.fetchall()}
            conn.close()

            results = client.query(
                collection_name=collection,
                filter="id >= 0",
                output_fields=["source"],
                limit=16384,
            )
            milvus_files = set()
            for r in results:
                src = r.get("source", "")
                if ":" in src:
                    _, fname = src.split(":", 1)
                    milvus_files.add(fname)
                else:
                    milvus_files.add(src)

            missing_summary_files = {r[0] for r in rows}.union(milvus_files - existing_pg_files)
            
            if not missing_summary_files:
                yield f"data: {json.dumps({'message': 'All documents have summaries.', 'status': 'done'})}\n\n"
                return

            yield f"data: {json.dumps({'message': f'Found {len(missing_summary_files)} documents missing summaries, starting...'})}\n\n"

            for fname in missing_summary_files:
                yield f"data: {json.dumps({'message': f'Extracting content for {fname}...'})}\n\n"
                res = client.query(
                    collection_name=collection,
                    filter=f'source like "%:{fname}" or source == "{fname}"',
                    output_fields=["text"],
                    limit=10,
                )
                if not res:
                    yield f"data: {json.dumps({'message': f'No text blocks found for {fname}, skipping.'})}\n\n"
                    continue
                    
                combined_text = "\n".join([d.get("text", "") for d in res])
                yield f"data: {json.dumps({'message': f'Generating AI summary for {fname}...'})}\n\n"
                summary_text = generate_summary_with_glm(combined_text)
                
                update_file_metadata(collection, fname, fname, summary_text)
                yield f"data: {json.dumps({'message': f'{fname} summary generated successfully.'})}\n\n"
                
            yield f"data: {json.dumps({'message': 'All missing summaries generated.', 'status': 'done'})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/api/kb/collections/{collection}/documents/upload")
async def upload_documents(collection: str, files: List[UploadFile] = File(...), use_mineru: bool = Form(False), clear_first: bool = Form(False)):
    import asyncio

    async def generate():
        if not files:
            yield f"data: {json.dumps({'error': 'No files selected'})}\n\n"
            return

        yield f"data: {json.dumps({'message': f'Target knowledge base: {collection}'})}\n\n"

        saved_paths = []
        for f in files:
            dest = UPLOAD_DIR / f.filename
            with open(dest, "wb") as out_f:
                content = await f.read()
                out_f.write(content)
            saved_paths.append(str(dest))
            yield f"data: {json.dumps({'message': f'Saved: {f.filename}'})}\n\n"

        yield f"data: {json.dumps({'message': 'Initializing Milvus and Embedding...'})}\n\n"

        try:
            sys.path.insert(0, "/app")
            import rag_ingest as ri

            loop = asyncio.get_event_loop()

            def _init_clients():
                c = ri.get_milvus_client()
                e = ri.get_embedder()
                return c, e

            client, embedder = await loop.run_in_executor(None, _init_clients)

            if clear_first and collection in client.list_collections():
                await loop.run_in_executor(None, client.drop_collection, collection)
                yield f"data: {json.dumps({'message': f'Cleared knowledge base {collection}'})}\n\n"

            await loop.run_in_executor(None, lambda: ri.ensure_collection(client, collection_name=collection))

            total_inserted = 0
            for pdf_path in saved_paths:
                fname = Path(pdf_path).name
                yield f"data: {json.dumps({'message': f'Parsing {fname}...'})}\n\n"

                def _load_docs():
                    gen = ri.load_pdf_documents(
                        pdf_path=pdf_path,
                        use_mineru=use_mineru,
                        mineru_output_dir="/app/data/mineru_output",
                    )
                    d = []
                    msgs = []
                    if type(gen).__name__ == "generator":
                        try:
                            while True:
                                item = next(gen)
                                if isinstance(item, str):
                                    msgs.append(item)
                        except StopIteration as e:
                            d = e.value
                    else:
                        d = gen
                    return d, msgs

                docs, parse_msgs = await loop.run_in_executor(None, _load_docs)
                for m in parse_msgs:
                    yield f"data: {json.dumps({'message': m})}\n\n"

                if not docs:
                    yield f"data: {json.dumps({'message': f'Warning: No content extracted from {fname}, skipping'})}\n\n"
                    continue

                yield f"data: {json.dumps({'message': f'Extracted {len(docs)} text chunks, starting vectorization...'})}\n\n"

                n = await loop.run_in_executor(
                    None,
                    lambda: ri.embed_and_insert(client, embedder, docs, source_label=fname, collection_name=collection),
                )

                total_inserted += n
                yield f"data: {json.dumps({'message': f'Inserted {n} vectors for {fname}'})}\n\n"

                yield f"data: {json.dumps({'message': f'Generating AI summary for {fname}...'})}\n\n"
                if docs:
                    combined_text = "\n".join([d.get("text", "") for d in docs[:10]])
                    summary_text = await loop.run_in_executor(
                        None, generate_summary_with_glm, combined_text
                    )
                    await loop.run_in_executor(
                        None, update_file_metadata, collection, fname, fname, summary_text
                    )
                    yield f"data: {json.dumps({'message': f'Summary generated for {fname}'})}\n\n"

            yield f"data: {json.dumps({'message': f'All done! Total {total_inserted} vectors inserted.', 'status': 'done'})}\n\n"

        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

# ─── Xiaohongshu Endpoints ────────────────────────────────────────────────────
@app.get("/api/xhs/stats")
def xhs_stats():
    try:
        conn = _pg_conn()
        stats: dict = {}
        kw_rows = []
        with conn.cursor() as cur:
            for tbl, label in [
                ("xhs_posts",           "total_posts"),
                ("xhs_users",           "total_users"),
                ("xhs_comments",        "total_comments"),
                ("xhs_search_sessions", "total_sessions"),
            ]:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                stats[label] = cur.fetchone()[0]
            cur.execute("SELECT MAX(collected_at) FROM xhs_posts")
            latest = cur.fetchone()[0]
            stats["latest_collected_at"] = str(latest)[:19] if latest else None
            cur.execute("SELECT search_keyword, COUNT(*) FROM xhs_posts GROUP BY search_keyword ORDER BY 2 DESC LIMIT 8")
            kw_rows = [{"keyword": kw, "count": cnt} for kw, cnt in cur.fetchall()]
            stats["top_keywords"] = kw_rows
        conn.close()
        return stats
    except Exception as exc:
        import traceback
        print(f"[xhs/stats] {traceback.format_exc()}")
        return {
            "total_posts": 0,
            "total_users": 0,
            "total_comments": 0,
            "total_sessions": 0,
            "latest_collected_at": None,
            "top_keywords": [],
            "error": str(exc),
        }

@app.get("/api/xhs/posts")
def xhs_posts(keyword: str = "", min_likes: int = 0, limit: int = 10, page: int = 1):
    try:
        import psycopg2.extras
        conn = _pg_conn()
        conds, params = ["1=1"], []
        if keyword.strip():
            conds.append("to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(content,'')) @@ plainto_tsquery('simple', %s)")
            params.append(keyword.strip())
        if min_likes > 0:
            conds.append("likes_count >= %s")
            params.append(int(min_likes))
            
        # Count total
        count_sql = f"SELECT COUNT(*) FROM xhs_posts WHERE {' AND '.join(conds)}"
        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()[0]
            
        limit = min(int(limit), 50)
        offset = (page - 1) * limit
        params.extend([limit, offset])
        
        sql = (
            f"SELECT post_id, title, author_name, likes_count, comments_count, tags, search_keyword, "
            f"LEFT(content,200) AS content, collected_at::text, url "
            f"FROM xhs_posts WHERE {' AND '.join(conds)} ORDER BY likes_count DESC LIMIT %s OFFSET %s"
        )
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        conn.close()
        
        return {
            "posts": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "limit": limit
        }
    except Exception as exc:
        import traceback
        print(f"[xhs/posts] {traceback.format_exc()}")
        return {
            "posts": [],
            "total": 0,
            "page": 1,
            "limit": limit,
            "error": str(exc),
        }

# ─── 小红书：登录态、采集任务、定时、报告 ─────────────────────────────────────
def _xhs_data_dir() -> Path:
    """使用可用的数据目录，避免 /app/data 未挂载时 500。"""
    candidates = [Path("/app/data")]
    if os.environ.get("XHS_DATA_DIR"):
        candidates.append(Path(os.environ.get("XHS_DATA_DIR")))
    candidates.append(Path(".").resolve() / "data")
    for base in candidates:
        if base and str(base) and base.exists():
            return base
    return Path(".").resolve()

def _xhs_path(name: str) -> Path:
    return _xhs_data_dir() / name

XHS_STATE_PATH = _xhs_path("xhs_state.json")
XHS_SCRAPER_STATUS_PATH = _xhs_path("xhs_scraper_status.json")
XHS_SCHEDULES_PATH = _xhs_path("xhs_schedules.json")

_scraper_lock = threading.Lock()

def _read_scraper_status() -> dict:
    try:
        if XHS_SCRAPER_STATUS_PATH.exists():
            with open(XHS_SCRAPER_STATUS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"running": False, "started_at": None, "finished_at": None, "message": None}

def _write_scraper_status(obj: dict):
    try:
        _xhs_data_dir().mkdir(parents=True, exist_ok=True)
        with open(XHS_SCRAPER_STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[xhs] write scraper status error: {e}")

def _run_scraper_background():
    """在后台线程中执行 nat run workflow_scraper.yaml，结束后更新状态。"""
    _write_scraper_status({"running": True, "started_at": datetime.utcnow().isoformat() + "Z", "finished_at": None, "message": "采集已启动"})
    try:
        with open(_xhs_path("scraper_full_log.txt"), "w", encoding="utf-8") as f:
            proc = subprocess.Popen(
                ["nat", "run", "--config_file", "workflow_scraper.yaml", "--input", "请现在开始执行采集任务。"],
                cwd="/app",
                env=os.environ.copy(),
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
            )
            # 等待进程结束（带超时）
            proc.wait(timeout=3600)
        
        # 结束后读取一下日志尾部用来更新状态
        out = ""
        try:
            with open(_xhs_path("scraper_full_log.txt"), "r", encoding="utf-8") as f:
                content = f.read()
                out = content[-2000:] if content else ""
        except Exception:
            pass

        _write_scraper_status({
            "running": False,
            "started_at": _read_scraper_status().get("started_at"),
            "finished_at": datetime.utcnow().isoformat() + "Z",
            "message": "采集完成" if proc.returncode == 0 else f"采集异常退出 code={proc.returncode}",
            "returncode": proc.returncode,
            "log_tail": out,
        })
    except subprocess.TimeoutExpired:
        _write_scraper_status({"running": False, "started_at": _read_scraper_status().get("started_at"), "finished_at": datetime.utcnow().isoformat() + "Z", "message": "采集超时"})
    except Exception as e:
        _write_scraper_status({"running": False, "started_at": _read_scraper_status().get("started_at"), "finished_at": datetime.utcnow().isoformat() + "Z", "message": str(e)})
    finally:
        # 兜底清理：如果进程异常退出，确保把所有 running 状态置为 failed，避免前端卡死
        try:
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute("UPDATE xhs_search_sessions SET status='failed' WHERE status='running';")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[xhs] failed to cleanup running sessions: {e}")

@app.get("/api/xhs/login-status")
def xhs_login_status():
    """返回小红书登录态文件是否存在及基本信息，便于前端展示与持久化校验。"""
    try:
        if not XHS_STATE_PATH.exists():
            return {
                "has_state_file": False,
                "path": str(XHS_STATE_PATH),
                "size_bytes": 0,
                "modified": None,
                "hint": "请先运行：docker-compose --profile login up xhs-login，在 http://localhost:6080 完成登录后执行 docker exec xhs-login touch /app/data/xhs_login_trigger",
            }
        st = XHS_STATE_PATH.stat()
        return {
            "has_state_file": True,
            "path": str(XHS_STATE_PATH),
            "size_bytes": st.st_size,
            "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
            "hint": "登录态已存在，可直接手动启动采集。",
        }
    except Exception as exc:
        import traceback
        print(f"[xhs/login-status] {traceback.format_exc()}")
        return {
            "has_state_file": False,
            "path": str(XHS_STATE_PATH),
            "size_bytes": 0,
            "modified": None,
            "hint": f"检查失败: {exc}。请确认 api 容器已挂载 app_data 卷（/app/data）。",
        }

@app.post("/api/xhs/run-scraper")
def xhs_run_scraper():
    """手动触发一次小红书采集（后台执行 workflow_scraper.yaml）。"""
    with _scraper_lock:
        status = _read_scraper_status()
        if status.get("running"):
            raise HTTPException(409, "采集任务正在运行中，请稍后再试")
        t = threading.Thread(target=_run_scraper_background, daemon=True)
        t.start()
    return {"message": "采集任务已启动", "started_at": datetime.utcnow().isoformat() + "Z"}

@app.get("/api/xhs/scraper-status")
def xhs_scraper_status():
    """返回当前采集任务状态（是否运行中、开始/结束时间、最近日志）。"""
    try:
        return _read_scraper_status()
    except Exception as exc:
        import traceback
        print(f"[xhs/scraper-status] {traceback.format_exc()}")
        return {"running": False, "started_at": None, "finished_at": None, "message": str(exc)}

@app.get("/api/xhs/sessions")
def xhs_sessions(limit: int = 50):
    """返回采集会话列表，用于前端表格展示。"""
    try:
        import psycopg2.extras
        conn = _pg_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT session_id::text, search_keyword, posts_found, users_found, comments_found, status, started_at::text, finished_at::text FROM xhs_search_sessions ORDER BY started_at DESC LIMIT %s",
                (min(int(limit), 100),),
            )
            rows = cur.fetchall()
        conn.close()
        return {"sessions": [dict(r) for r in rows]}
    except Exception as exc:
        import traceback
        print(f"[xhs/sessions] {traceback.format_exc()}")
        return {"sessions": [], "error": str(exc)}

def _read_schedules() -> list:
    try:
        if XHS_SCHEDULES_PATH.exists():
            with open(XHS_SCHEDULES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _write_schedules(schedules: list):
    _xhs_data_dir().mkdir(parents=True, exist_ok=True)
    with open(XHS_SCHEDULES_PATH, "w", encoding="utf-8") as f:
        json.dump(schedules, f, ensure_ascii=False, indent=2)

@app.get("/api/xhs/schedules")
def xhs_schedules_list():
    """定时任务列表（持久化在 app_data 卷）。"""
    try:
        return {"schedules": _read_schedules()}
    except Exception as exc:
        import traceback
        print(f"[xhs/schedules] {traceback.format_exc()}")
        return {"schedules": [], "error": str(exc)}

class ScheduleCreate(BaseModel):
    name: Optional[str] = "未命名"
    cron: Optional[str] = "0 9 * * *"
    enabled: bool = True

@app.post("/api/xhs/schedules")
def xhs_schedules_add(body: ScheduleCreate):
    """新增一条定时任务配置。"""
    try:
        schedules = _read_schedules()
        new_id = str(datetime.utcnow().timestamp())
        schedules.append({
            "id": new_id,
            "name": body.name or "未命名",
            "cron": body.cron or "0 9 * * *",
            "enabled": body.enabled,
            "last_run": None,
            "next_run": None,
        })
        _write_schedules(schedules)
        return {"message": "已添加", "id": new_id}
    except Exception as exc:
        raise HTTPException(500, str(exc))

@app.delete("/api/xhs/schedules/{schedule_id}")
def xhs_schedules_remove(schedule_id: str):
    schedules = [s for s in _read_schedules() if s.get("id") != schedule_id]
    _write_schedules(schedules)
    return {"message": "已删除"}

class ReportRequest(BaseModel):
    keywords: Optional[List[str]] = None
    max_posts: int = 50

@app.post("/api/xhs/report")
def xhs_report(req: ReportRequest):
    """基于当前库内小红书数据生成 AI 分析报告（摘要与洞察）。"""
    try:
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT title, content, author_name, likes_count, comments_count, tags, search_keyword, collected_at FROM xhs_posts ORDER BY collected_at DESC LIMIT %s",
                (min(req.max_posts, 200),),
            )
            rows = cur.fetchall()
        conn.close()
        if not rows:
            return {"report": "暂无采集数据，请先执行一次采集再生成报告。", "posts_used": 0}
        columns = ["title", "content", "author_name", "likes_count", "comments_count", "tags", "search_keyword", "collected_at"]
        posts_text = []
        for r in rows:
            post = dict(zip(columns, r))
            posts_text.append(
                f"标题: {post['title']}\n内容摘要: {(post['content'] or '')[:500]}\n作者: {post['author_name']} 点赞: {post['likes_count']} 评论: {post['comments_count']}\n关键词: {post['search_keyword']} 标签: {post['tags']}"
            )
        prompt = "以下是从小红书采集的保险相关帖子摘要。请用中文写一份简洁的分析报告（约 300–500 字），包含：1) 数据概览；2) 用户关注点与热点话题；3) 对保险产品/运营的简要建议。\n\n" + "\n\n---\n\n".join(posts_text[:50])
        resp = llm_client.chat.completions.create(
            model="minimaxai/minimax-m2.1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2048,
        )
        report = (resp.choices[0].message.content or "").strip()
        return {"report": report, "posts_used": len(rows)}
    except Exception as exc:
        raise HTTPException(500, str(exc))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
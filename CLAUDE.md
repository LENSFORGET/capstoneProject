# CLAUDE.md

This file provides guidance to AI coding assistants when working with this repository.

## Project Overview

This is a capstone project: **宏利保险 AI 智能顾问系统** (Manulife HK Insurance AI Advisor)
built on NVIDIA NeMo Agent Toolkit (NAT).

The system provides an AI-powered insurance Q&A service backed by:
- **33 official Manulife HK product PDFs** (2,438 semantic chunks in Milvus)
- **qwen-plus** LLM via Alibaba Cloud Bailian (DashScope) for generation
- **NVIDIA NIM nv-embedqa-e5-v5** for vector embeddings
- **NeMo Agent Toolkit UI** as the chat frontend

## Architecture

```
User → nat-ui (port 4000) → nat-orchestrator (port 8100)
                                    ↓  tool_calling_agent + qwen-plus
                               rag_mcp.py (FastMCP, stdio)
                                    ↓  category-aware vector search
                               Milvus insurance_docs collection
                               (33 PDFs, 2438 chunks, 1024-dim vectors)
```

### Docker Services

| Service | Purpose | Port |
|---------|---------|-------|
| `nat-ui` | NeMo Agent Toolkit UI (Next.js) | 4000 |
| `nat-orchestrator` | Main agent (tool_calling_agent + qwen-plus) | 8100 |
| `milvus-standalone` | Vector database | 19530 |
| `milvus-minio` | Milvus object storage | — |
| `milvus-etcd` | Milvus metadata | — |
| `nat-api` | FastAPI backend (KB management) | 8000 |
| `nat-agent-life` | Specialist agent - life insurance (standby) | 8101 |
| `nat-agent-savings` | Specialist agent - savings/annuity (standby) | 8102 |
| `nat-agent-medical` | Specialist agent - medical/VHIS (standby) | 8103 |
| `nat-agent-critical` | Specialist agent - critical illness (standby) | 8104 |

## Common Commands

### Start Services

```bash
# Start all services
docker-compose up -d

# Check health
docker-compose ps

# View orchestrator logs (most important)
docker-compose logs -f nat-orchestrator

# Restart orchestrator after YAML changes
docker-compose restart nat-orchestrator
```

### RAG Knowledge Base Management

```bash
# Check current KB status and category breakdown
docker exec nat-orchestrator python check_categories.py

# Ingest all PDFs from /app/PDF/ directory
docker exec nat-orchestrator bash /app/ingest_all.sh

# Ingest single PDF (recommended: --no-mineru for speed)
docker exec nat-orchestrator python rag_ingest.py --pdf-path /app/PDF/file.pdf --no-mineru

# Clear and rebuild entire KB
docker exec nat-orchestrator python rag_ingest.py --clear
```

### Test the RAG API

```bash
# Quick test via curl
curl -X POST http://localhost:8100/generate \
  -H "Content-Type: application/json" \
  -d '{"input_message": "什么是ManuTerm定期寿险？"}'

# Check health
curl http://localhost:8100/health
```

## Code Structure

### Key Application Files

| File | Purpose |
|------|---------|
| `workflow_orchestrator.yaml` | Main agent config (tool_calling_agent + qwen-plus) |
| `rag_mcp.py` | FastMCP RAG tools (search_insurance, get_collection_stats, list_insurance_categories) |
| `agent_router_mcp.py` | HTTP routing MCP tools for specialist agents (currently unused) |
| `rag_ingest.py` | PDF parsing + vectorization into Milvus |
| `ingest_all.sh` | Batch ingest all PDFs in /app/PDF/ |
| `check_categories.py` | Diagnose KB content by insurance category |
| `api.py` | FastAPI backend (port 8000) |
| `workflow_agent_*.yaml` | Specialist agent configs (life/savings/medical/critical) |

### NAT Packages (packages/)

Installed in editable mode:
- **nvidia_nat_core** - Core framework (builders, CLI, LLM configs)
- **nvidia_nat_mcp** - MCP client/server implementation
- **nvidia_nat_fastmcp** - FastMCP wrapper
- **nvidia_nat_langchain** - LangChain integrations (tool_calling_agent, react_agent)
- **nvidia_nat_llama_index** - LlamaIndex integrations (MilvusRetriever)

### Frontend (nat-ui/)

NeMo Agent Toolkit UI - Next.js 14 app:
- `nat-ui/.env` - UI configuration (backend URL, feature flags)
- `nat-ui/public/content/welcome.md` - Welcome page markdown
- `nat-ui/public/content/promptSuggestions.json` - Suggested prompts
- Connects to orchestrator at `http://nat-orchestrator:8100`

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NVIDIA_API_KEY` | Yes | NVIDIA NIM key for embedding (nv-embedqa-e5-v5) |
| `DASHSCOPE_API_KEY` | Yes | Alibaba Cloud Bailian key for qwen-plus LLM |
| `MILVUS_HOST` | No | Milvus host (Docker default: `milvus`) |
| `MILVUS_PORT` | No | Milvus port (default: `19530`) |
| `RAG_CATEGORY` | No | Pre-set category for specialist agents (life/savings/medical/critical) |

## Milvus Collection Schema

Collection: `insurance_docs`

| Field | Type | Description |
|-------|------|-------------|
| `id` | INT64 (auto PK) | — |
| `vector` | FLOAT_VECTOR (dim=1024) | Embedding from nv-embedqa-e5-v5 |
| `text` | VARCHAR 4096 | Content chunk |
| `title` | VARCHAR 512 | Document section title |
| `source` | VARCHAR 128 | e.g., `pdf_mineru:manu-term.pdf` |
| `url` | VARCHAR 1024 | Source URL (if any) |
| `scraped_at` | VARCHAR 64 | Ingestion timestamp |
| `content_type` | VARCHAR 32 | text / table / title / image / equation |

## Insurance Category Map

```python
CATEGORY_MAP = {
    "life":     ("寿险",       ["manu-term", "universal-life", "manucentury", "la-vie-2"]),
    "savings":  ("储蓄与年金险", ["flexifortune", "genesis", "harvest-saver",
                                  "manuglobal-saver", "manuleisure", "prestige-achiever",
                                  "prestige-preserver", "future-assure"]),
    "medical":  ("医疗险与VHIS", ["vhis", "manulife-first", "manulife-shelter",
                                   "manulife-supreme", "medical-referral",
                                   "prescribed-diagnostic", "emergency-assistance"]),
    "critical": ("危疾与综合保障", ["manupremier-protector", "whole-in-one-prime",
                                    "manudelight", "incapacity-care"]),
}
```

## Key Architectural Decisions

### 1. Single Orchestrator (not multi-agent routing)

The orchestrator handles intent recognition AND RAG retrieval directly, reducing latency from 4-6 LLM calls to 1. The specialist nat-agent-* services exist but are stopped by default.

### 2. tool_calling_agent over react_agent

`tool_calling_agent` uses native function calling (OpenAI tool_call format), more reliable than text-parsed ReAct format for qwen-plus.

### 3. category-aware RAG

`rag_mcp.py` accepts a `category` parameter to filter Milvus results by `source` field. The orchestrator detects intent and passes the appropriate category to improve retrieval precision.

### 4. Volume-mounted configs

`workflow_orchestrator.yaml` and `rag_mcp.py` are volume-mounted (not baked into image), allowing config changes without image rebuild.

## Important Notes

1. **Two separate API keys**: NVIDIA (embedding) + DashScope (LLM). Both required.
2. **nat-app container**: Currently stopped. Its image (`capstoneproject-app`) is reused by nat-orchestrator and specialist agents.
3. **No MinerU in agents**: Agent containers use `--no-mineru` flag for ingestion to avoid CUDA dependency.
4. **UI env vars baked at build**: NEXT_PUBLIC_* vars in `nat-ui/.env` require image rebuild when changed.
5. **Specialist agents**: nat-agent-life/savings/medical/critical are configured but stopped. Start with `docker-compose start nat-agent-life` etc. if needed for debugging.

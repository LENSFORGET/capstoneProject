# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a capstone project: **NAT 小红书保险 RAG 系统** (Xiaohongshu Insurance RAG System) built on NVIDIA NeMo Agent Toolkit (NAT). The system combines:

1. **RAG Q&A System** - Insurance knowledge base with PDF content using NVIDIA NIM for embeddings and Milvus for vector storage
2. **Web Scraper** - Agent-browser powered Xiaohongshu content scraper using GLM 5 LLM
3. **Frontend** - Next.js UI with Pinecone-style SaaS design

## Architecture

The system uses Docker Compose with the following services:

| Service | Purpose | Port |
|---------|---------|-------|
| etcd | Milvus metadata storage | - |
| minio | Milvus object storage | - |
| milvus | Vector database (standalone) | 19530 |
| postgres | Xiaohongshu scraped data storage | 5432 |
| app | NAT application (workflows, MCP tools) | - |
| api | FastAPI backend for chat & KB management | 8000 |
| frontend | Next.js UI | 4000（Windows 上 3000 可能被保留） |
| test | Test container (on-demand) | - |

### Two Data Pipelines

**Pipeline 1: PDF Knowledge Base (RAG data source)**
```
python rag_ingest.py
  → pypdf/MinerU parses manupremier-protector.pdf
  → NVIDIA NIM nv-embedqa-e5-v5 embedding
  → pymilvus → Milvus insurance_docs collection
```

**Pipeline 2: Xiaohongshu User Insights (independent, NOT for RAG)**
```
run_zeroclaw_scraper.ps1
 → ZeroClaw Agent uses playwright-npx (headful mode)
 → xhs-db-tool writes to PostgreSQL
 → /app/data/xhs_user_insights.md
```

**Pipeline 3: RAG Insurance Q&A**
```
nat run --config_file workflow_rag.yaml
  → GLM 5 calls tools:
    - search_insurance() → MilvusRetriever (PDF KB)
    - browser tools → Real-time web queries (fallback)
```

## Common Commands

### Docker Environment

```bash
# Build and start all services
docker-compose up -d --build

# Check service health
docker-compose ps

# Stop services
docker-compose down

# Stop and remove volumes
docker-compose down -v

# View logs
docker-compose logs -f [service_name]
```

### Entering App Container

```bash
docker exec -it nat-app bash
```

### RAG Knowledge Base Management

```bash
# Ingest PDF into Milvus (uses MinerU → pypdf fallback)
python rag_ingest.py

# Clear and rebuild knowledge base
python rag_ingest.py --clear

# Force pypdf only (skip MinerU)
python rag_ingest.py --no-mineru

# Include Xiaohongshu data as supplement (requires scraper to run first)
python rag_ingest.py --include-xhs
```

### NAT Workflow Execution

```bash
# Run RAG Q&A workflow
nat run --config_file workflow_rag.yaml

# Run Xiaohongshu scraper workflow
run_zeroclaw_scraper.ps1

# Run generic browser workflow
nat run --config_file workflow_browser.yaml
```

### Running Tests

```bash
# Run unit and integration tests (no API key needed)
docker-compose run --rm test

# Run specific test file
docker-compose run --rm test pytest test_unit.py -v

# Run e2e tests (requires NVIDIA_API_KEY)
docker-compose run --rm test pytest test_e2e.py -v
```

### Frontend Development

```bash
# Frontend dev server runs automatically in container
# Access at http://localhost:4000（若 3000 被 Windows 保留则使用 4000）

# For local dev (without Docker):
cd frontend
npm install
npm run dev
```

### API Server

```bash
# API runs at http://localhost:8000
# Auto-started by docker-compose with --reload flag

# Key endpoints:
# POST /api/chat           - Streaming chat with RAG
# GET  /api/kb/collections - List knowledge bases
# POST /api/kb/collections/{collection}/documents/upload - Upload PDF
# GET  /api/xhs/stats      - Xiaohongshu scraped data stats
```

## Code Structure

### NAT Packages (packages/)

The project contains local NAT packages installed in editable mode:

- **nvidia_nat_core** - Core NAT framework (builders, CLI, LLM, retriever, evaluator)
- **nvidia_nat_mcp** - MCP (Model Context Protocol) server implementation
- **nvidia_nat_fastmcp** - FastMCP wrapper for easier MCP tool creation
- **nvidia_nat_llama_index** - LlamaIndex integrations including MilvusRetriever

### Root Application Files

| File | Purpose |
|------|---------|
| `rag_ingest.py` | PDF parsing (MinerU/pypdf) and vectorization into Milvus |
| `rag_mcp.py` | FastMCP server exposing MilvusRetriever tools for RAG |
| `run_zeroclaw_scraper.ps1` | Batch script to run the ZeroClaw XHS scraper |
| `xhs_db_mcp.py` | FastMCP server for PostgreSQL storage of scraped data |
| `workflow_rag.yaml` | NAT react_agent workflow for insurance Q&A |
| `zeroclaw_scraper_agent.toml` | ZeroClaw Agent configuration and system prompt for XHS scraper |
| `workflow_browser.yaml` | Generic browser workflow |
| `api.py` | FastAPI backend for chat, KB management, XHS data |
| `xhs_db_init.sql` | PostgreSQL schema initialization |
| `Dockerfile` | Multi-stage Python 3.11 image with NAT, Node.js, agent-browser, MinerU |

### Frontend (frontend/)

- **src/app/** - Next.js 16 App Router pages (chat, indexes, xhs)
- **src/components/** - Reusable components (Navbar, Card, Sidebar)
- Uses React 19, Tailwind CSS 4, Framer Motion, lucide-react icons

## Key Architectural Patterns

### MCP (Model Context Protocol) Tools

The project uses FastMCP to expose tools to NAT workflows:

1. **MCP servers are Python scripts** that define tools with `@mcp.tool()` decorator
2. **NAT workflows connect via stdio** - see `function_groups._type: mcp_client`
3. **Tool adapter pattern** - `rag_mcp.py` wraps NVIDIAEmbedding in LangChain Embeddings interface for MilvusRetriever compatibility

### NAT Workflows

Workflows are YAML files defining:
- `function_groups` - MCP tool connections
- `llms` - LLM configuration (uses z-ai/glm5 via NVIDIA API)
- `workflow` - react_agent configuration with system_prompt

### NAT Builder Pattern

The NAT core uses a builder pattern:
- Component builders in `packages/nvidia_nat_core/src/nat/builder/`
- LLMs, retrievers, embedders are built from YAML config
- Entry points defined in `nvidia_nat_core/pyproject.toml` under `[project.entry-points]`

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NVIDIA_API_KEY` | Yes | NVIDIA NIM API key for GLM 5 + embedding |
| `XHS_COOKIES` | No | Xiaohongshu login cookies for better scraping |
| `MILVUS_HOST` | No (default: localhost) | Milvus host (Docker: milvus) |
| `MILVUS_PORT` | No (default: 19530) | Milvus port |
| `POSTGRES_*` | No | PostgreSQL connection settings |

## Milvus Collection Schema

The `insurance_docs` collection has these fields:
- `id` (INT64, auto, primary)
- `vector` (FLOAT_VECTOR, dim=1024)
- `text` (VARCHAR 4096) - Content chunk
- `title` (VARCHAR 512) - Document title/section
- `source` (VARCHAR 128) - Source identifier (e.g., "pdf_mineru:file.pdf")
- `url` (VARCHAR 1024) - Source URL
- `scraped_at` (VARCHAR 64) - Timestamp
- `content_type` (VARCHAR 32) - "text"|"table"|"image"|"equation"|"title"

## PostgreSQL Schema (xhs_data)

- `xhs_search_sessions` - Scraper session tracking
- `xhs_posts` - Post data with tags, engagement metrics
- `xhs_users` - User profiles and stats
- `xhs_comments` - Comment data
- `kb_documents` - File metadata for PDF uploads

## Important Notes

1. **MinerU vs pypdf**: MinerU provides richer extraction (tables, images, equations) but is slower. pypdf is the fallback for simple text extraction.

2. **NVIDIA NIM Models**: Both GLM 5 LLM and nv-embedqa-e5-v5 embedding use the same API key from `https://integrate.api.nvidia.com/v1`.

3. **XHS Data is Separate**: Xiaohongshu scraped data goes to PostgreSQL, NOT to the RAG knowledge base. It's used for user insights analysis only. Use `--include-xhs` flag to optionally add XHS data to RAG.

4. **Cross-platform Commands**: `agent_browser_mcp.py` handles Windows vs Linux agent-browser command detection automatically.

5. **Editable NAT Packages**: The NAT packages are installed in editable mode (`-e`) for easier development, requiring `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_*` env vars to bypass git version detection.

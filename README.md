# Manulife Insurance AI Advisor System

A Manulife Hong Kong insurance RAG Q&A system built with **NVIDIA NeMo Agent Toolkit (NAT)**.

The system uses **33 official product PDFs** as its knowledge base and combines Alibaba Cloud Bailian `qwen-plus` with NVIDIA NIM embeddings to provide professional insurance advisory answers across life, savings, medical, and critical illness products.

**Web access:** http://localhost:14000  
**Email auto-reply:** Monitors Gmail inbox and generates RAG-based replies automatically.

---

## System Architecture

```text
[Web]
User query
  │
  ▼
nat-ui (NeMo Agent Toolkit UI, port 14000)
  │  HTTP
  ▼
nat-orchestrator (tool_calling_agent, port 8100)
  │  ← qwen-plus (Alibaba Cloud Bailian DashScope)
  │  MCP stdio
  ▼
rag_mcp.py (FastMCP)
  │  category-aware vector retrieval
  ▼
Milvus (vector database, port 19530)
  └─ insurance_docs collection (33 PDFs, 2,438 semantic chunks)

[Email Auto-Reply]
Gmail inbox (customer emails)
  │  gws gmail polling (every 30 seconds)
  ▼
nat-email-agent (email_agent.py)
  │  HTTP POST /generate
  ▼
nat-orchestrator:8100 (RAG retrieval + qwen-plus generation)
  │
  ▼
gws gmail +reply → automatic customer reply
```

### Docker Services

| Service | Description | Port |
|---------|-------------|------|
| `nat-ui` | NeMo Agent Toolkit UI frontend | 14000 |
| `nat-orchestrator` | Main orchestrator agent (`qwen-plus` + RAG) | 8100 |
| `nat-email-agent` | Gmail auto-reply service | — |
| `milvus-standalone` | Vector database (auto-restart) | 19530 |
| `milvus-minio` | Milvus object storage (auto-restart) | — |
| `milvus-etcd` | Milvus metadata storage (auto-restart) | — |
| `nat-api` | FastAPI backend (knowledge base management) | 8000 |
| `nat-agent-life` | Life insurance specialist agent (standby) | 8101 |
| `nat-agent-savings` | Savings/annuity specialist agent (standby) | 8102 |
| `nat-agent-medical` | Medical/VHIS specialist agent (standby) | 8103 |
| `nat-agent-critical` | Critical illness specialist agent (standby) | 8104 |

---

## Knowledge Base

The knowledge base contains **33 official Manulife HK PDFs** and **2,438 semantic chunks**, grouped by category:

| Insurance Type | `category` Value | Main Products |
|----------------|------------------|---------------|
| Life | `life` | ManuTerm, Universal Life, La Vie 2, ManuCentury |
| Savings & Annuity | `savings` | FlexiFortune, Genesis / Genesis Centurion, Harvest Saver, ManuGlobal Saver, ManuLeisure, Prestige Achiever / Preserver, Future Assure |
| Medical & VHIS | `medical` | VHIS First, VHIS Shelter, Supreme VHIS Premium / Lite, medical referral, diagnostic imaging guidance, hospital list |
| Critical Illness & Comprehensive | `critical` | ManuPremier Protector, Whole-in-One Prime 3, ManuDelight HK, incapacity care service |
| General Add-ons | `""` | Death benefit details, emergency assistance, continuity rights |

---

## Quick Start

### Prerequisites

- Docker Desktop (installed and running)
- NVIDIA NIM API Key (for embeddings): https://build.nvidia.com
- Alibaba Cloud Bailian API Key (for `qwen-plus`)

### Step 1: Configure Environment Variables

Edit the `.env` file in the project root:

```env
# NVIDIA NIM API Key (required for nv-embedqa-e5-v5 embedding)
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxx

# Alibaba Cloud Bailian API Key (required for qwen-plus LLM)
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
```

### Step 2: Start All Services

```bash
docker-compose up -d
```

Wait about 30–60 seconds, then check service status:

```bash
docker-compose ps
# Expected: nat-ui, nat-orchestrator, milvus-standalone (healthy), nat-api are running
```

### Step 3: Open the System

Open: **http://localhost:14000**

Example prompts:
- "What does ManuTerm cover?"
- "What is the difference between VHIS and standard medical insurance?"
- "How can annuity products support retirement planning?"
- "Compare ManuPremier Protector and Whole-in-One Prime"

---

## Gmail Auto-Reply

The `nat-email-agent` service monitors the Gmail inbox and generates professional insurance replies using the RAG knowledge base.

### One-Time Authentication Setup

> Requires Node.js 18+ on your local machine.

```bash
# 1) Install Google Workspace CLI
npm install -g @googleworkspace/cli

# 2) Create a GCP project (requires gcloud CLI) and enable Gmail API
gws auth setup

# If gcloud is unavailable, create OAuth credentials manually in Google Cloud Console:
#   https://console.cloud.google.com/apis/credentials
#   Application type: "Desktop app"
#   Save JSON to:
#   C:\Users\<YourUser>\.config\gws\client_secret.json

# 3) Authorize Gmail read/write scope
gws auth login -s gmail

# 4) Export credentials to project root
gws auth export --unmasked > gws_credentials.json
```

> `gws_credentials.json` includes OAuth tokens and is already in `.gitignore`. Do not commit it.

### Start Email Service

```bash
docker-compose up -d --build nat-email-agent

# Real-time logs
docker-compose logs -f nat-email-agent
```

### How It Works

1. Poll unread emails without `AI-Processed` label every 30 seconds
2. Parse sender, subject, and body
3. Call `nat-orchestrator:8100/generate` for RAG response generation
4. Detect incoming language (Chinese/English) and reply in the same language
5. Send formal reply via `gws gmail +reply` (thread preserved)
6. Add `AI-Processed` label to avoid duplicate processing

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` | `/app/gws_credentials.json` | OAuth credentials path |
| `ORCHESTRATOR_URL` | `http://nat-orchestrator:8100` | Orchestrator endpoint |
| `POLL_INTERVAL_SECONDS` | `30` | Polling interval (seconds) |

---

## PDF Knowledge Base Management

### Check Current Knowledge Base Status

```bash
docker exec nat-orchestrator python check_categories.py
```

### Re-ingest All PDFs

```bash
# Batch ingest all PDFs in /app/PDF/
docker exec nat-orchestrator bash /app/ingest_all.sh

# Or ingest manually inside container
docker exec -it nat-orchestrator bash
python rag_ingest.py --pdf-path /app/PDF/your-file.pdf --no-mineru
```

---

## Project Structure

```text
capstoneProject/
├── docker-compose.yml              # Docker orchestration (includes nat-email-agent)
├── Dockerfile                      # Main app image (Python 3.11 + NAT)
├── Dockerfile.email                # Email agent image (Node.js 20 + Python 3 + gws)
│
├── workflow_orchestrator.yaml      # Main orchestrator (tool_calling_agent + qwen-plus)
├── workflow_agent_life.yaml        # Life specialist agent config (standby)
├── workflow_agent_savings.yaml     # Savings specialist agent config (standby)
├── workflow_agent_medical.yaml     # Medical specialist agent config (standby)
├── workflow_agent_critical.yaml    # Critical illness specialist agent config (standby)
│
├── email_agent.py                  # Gmail auto-reply service
├── rag_mcp.py                      # RAG MCP service (category-aware Milvus retrieval)
├── agent_router_mcp.py             # Agent routing MCP tool (HTTP routing)
├── rag_ingest.py                   # PDF ingestion and vectorization script
├── ingest_all.sh                   # Batch PDF ingestion script
├── check_categories.py             # Category statistics/diagnostics script
│
├── api.py                          # FastAPI backend (KB management, port 8000)
│
├── gws_credentials.json            # Gmail OAuth credentials (generated locally, ignored)
│
├── nat-ui/                         # NeMo Agent Toolkit UI (Next.js frontend)
│   ├── .env                        # UI environment config
│   └── public/content/
│       ├── welcome.md              # Welcome page content
│       └── promptSuggestions.json  # Prompt suggestions
│
├── PDF/                            # Manulife HK insurance PDFs (33 files)
│
└── packages/                       # Local NVIDIA NAT packages
    ├── nvidia_nat_core/
    ├── nvidia_nat_mcp/
    ├── nvidia_nat_fastmcp/
    ├── nvidia_nat_langchain/
    └── nvidia_nat_llama_index/
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NVIDIA_API_KEY` | Yes | NVIDIA NIM key for `nv-embedqa-e5-v5` embeddings |
| `DASHSCOPE_API_KEY` | Yes | Alibaba DashScope key for `qwen-plus` generation |
| `MILVUS_HOST` | No | Milvus host (default in Docker: `milvus`) |
| `MILVUS_PORT` | No | Milvus port (default: `19530`) |
| `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` | Required for email | gws OAuth credentials path (default: `/app/gws_credentials.json`) |
| `ORCHESTRATOR_URL` | No | Orchestrator endpoint used by email agent (default: `http://nat-orchestrator:8100`) |
| `POLL_INTERVAL_SECONDS` | No | Gmail polling interval in seconds (default: `30`) |

---

## Tech Stack

| Layer | Technology | Version / Notes |
|-------|------------|-----------------|
| **LLM** | `qwen-plus` (Alibaba DashScope) | OpenAI-compatible API |
| **Embedding** | NVIDIA NIM `nv-embedqa-e5-v5` | 1024-dim vectors |
| **Vector DB** | Milvus Standalone | 2,438 chunks with category filters |
| **Agent Framework** | NVIDIA NeMo Agent Toolkit | `tool_calling_agent` workflow |
| **MCP Tools** | FastMCP | RAG retrieval tool service |
| **Frontend** | NeMo Agent Toolkit UI | Next.js 14 |
| **Backend** | FastAPI | Knowledge base management API |
| **Container Orchestration** | Docker Compose | One-command startup |

---

## 2026 Maintenance Notes (Important)

As this is the final stable 2026 capstone release, future maintainers should follow these rules:

1. **Core framework is locked**
   - NVIDIA NeMo Agent Toolkit packages are locked to `v0.0.1` in `packages/`.
   - **Do not upgrade** to `v1.5.0` or newer. NAT introduces major breaking changes that can break `workflow_orchestrator.yaml` and `rag_mcp.py`.
   - The current `qwen-plus` + category-aware RAG architecture is stable; prioritize knowledge updates and prompt tuning.

2. **nat-ui is heavily customized**
   - The frontend has deep localization and custom behavior using `next-i18next`.
   - Major customizations include zh-HK/en bilingual support and persistence migration from `sessionStorage` to `localStorage`.
   - **Do not overwrite with upstream nat-ui**, or these custom features will be lost.

---

## FAQ

**Q: The system is slow or times out.**  
A: First response from `qwen-plus` may take 15–25 seconds. Verify `DASHSCOPE_API_KEY` and network access to `dashscope.aliyuncs.com`.

**Q: The system says no relevant knowledge base content was found.**  
A: PDFs may not be ingested. Run `docker exec nat-orchestrator python check_categories.py`. If empty, run `ingest_all.sh`.

**Q: Milvus health check fails.**  
A: Milvus may need 2–3 minutes to fully start. Check logs: `docker-compose logs milvus-standalone`.

**Q: How do I switch to a stronger model (for example `qwen-max`)?**  
A: Change `model_name: qwen-plus` to `qwen-max` in `workflow_orchestrator.yaml`, then run `docker-compose restart nat-orchestrator`.

**Q: How do I add a new insurance PDF?**  
A: Put the file in `PDF/`, then run:
```bash
docker exec nat-orchestrator python rag_ingest.py --pdf-path /app/PDF/new-product.pdf --no-mineru
```

**Q: Email service shows `gws command failed`.**  
A: OAuth token may be expired. Re-run:
```bash
gws auth login -s gmail
gws auth export --unmasked > gws_credentials.json
docker-compose restart nat-email-agent
```

**Q: Email replies still include Markdown symbols.**  
A: `email_agent.py` includes `_clean_reply()` to remove Markdown formatting. Check logs if needed: `docker-compose logs nat-email-agent`.

**Q: Milvus does not auto-start after Docker restart.**  
A: The setup already uses `restart: unless-stopped`. If needed, run:
```bash
docker-compose up -d etcd minio milvus
```

---

## Development Notes

### Update Workflow Locally (No Image Rebuild)

All `workflow_*.yaml` files and `rag_mcp.py` are volume-mounted. After edits, just restart the container:

```bash
docker-compose restart nat-orchestrator
```

### View Agent Logs

```bash
docker-compose logs -f nat-orchestrator
```

### API Docs

FastAPI backend (port 8000): http://localhost:8000/docs  
NAT Orchestrator OpenAPI: http://localhost:8100/openapi.json

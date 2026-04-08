# 宏利保险 AI 智能顾问系统

基于 **NVIDIA NeMo Agent Toolkit (NAT)** 构建的宏利香港保险 RAG 问答系统。
系统以 33 份官方产品手册 PDF 为知识库，通过阿里云百炼 `qwen-plus` 大模型 + NVIDIA NIM 向量检索，
提供覆盖寿险、储蓄险、医疗险、危疾险全险种的专业中文保险咨询服务。

**Web 端访问：http://localhost:4000**
**邮件自动回复：监听 Gmail 收件箱，自动 RAG 回复客户来信**

---

## 系统架构

```
[ Web 端 ]
用户问题
  │
  ▼
nat-ui（NeMo Agent Toolkit UI，端口 4000）
  │  HTTP
  ▼
nat-orchestrator（tool_calling_agent，端口 8100）
  │  ← qwen-plus（阿里云百炼 DashScope）
  │  MCP stdio
  ▼
rag_mcp.py（FastMCP）
  │  category-aware 向量检索
  ▼
Milvus（向量数据库，端口 19530）
  └─ insurance_docs 集合（33 份 PDF，2,438 个语义分块）

[ 邮件自动回复 ]
Gmail 收件箱（客户来信）
  │  gws gmail 轮询（每 30 秒）
  ▼
nat-email-agent（email_agent.py）
  │  HTTP POST /generate
  ▼
nat-orchestrator:8100（RAG 检索 + qwen-plus 生成）
  │
  ▼
gws gmail +reply → 自动回信给客户
```

### Docker 服务列表

| 服务 | 说明 | 端口 |
|------|------|------|
| `nat-ui` | NeMo Agent Toolkit UI 前端 | 4000 |
| `nat-orchestrator` | 主调度 Agent（qwen-plus + RAG） | 8100 |
| `nat-email-agent` | Gmail 邮件自动回复服务 | — |
| `milvus-standalone` | 向量数据库（自动重启） | 19530 |
| `milvus-minio` | Milvus 对象存储（自动重启） | — |
| `milvus-etcd` | Milvus 元数据存储（自动重启） | — |
| `nat-api` | FastAPI 后端（知识库管理接口） | 8000 |
| `nat-agent-life` | 寿险专业 Agent（备用，端口 8101） | 8101 |
| `nat-agent-savings` | 储蓄险专业 Agent（备用） | 8102 |
| `nat-agent-medical` | 医疗险专业 Agent（备用） | 8103 |
| `nat-agent-critical` | 危疾险专业 Agent（备用） | 8104 |

---

## 知识库内容

共 **33 份宏利香港官方 PDF**，**2,438 个语义分块**，按险种分类：

| 险种 | category 值 | 主要产品 |
|------|-------------|----------|
| 寿险 | `life` | ManuTerm 定期寿险、Universal Life 万能寿险、La Vie 2、ManuCentury |
| 储蓄与年金 | `savings` | FlexiFortune、Genesis / Genesis Centurion、Harvest Saver、ManuGlobal Saver、ManuLeisure 退休年金、Prestige Achiever / Preserver、Future Assure |
| 医疗 & VHIS | `medical` | VHIS First 灵活计划、VHIS Shelter 标准计划、Supreme VHIS Premium / Lite、医疗转介、诊断影像指引、医院名单 |
| 危疾 & 综合 | `critical` | ManuPremier Protector、Whole-in-One Prime 3、ManuDelight HK、失能护理服务 |
| 通用附件 | `""` | 身故赔偿、紧急援助条款、连续保单持有人权益 |

---

## 快速开始

### 前置条件

- Docker Desktop（已安装并运行）
- NVIDIA NIM API Key（用于向量 embedding，获取：https://build.nvidia.com）
- 阿里云百炼 API Key（用于 qwen-plus LLM）

### 第一步：配置环境变量

编辑项目根目录的 `.env` 文件：

```env
# NVIDIA NIM API Key（向量模型 nv-embedqa-e5-v5 必需）
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxx

# 阿里云百炼 API Key（qwen-plus LLM 必需）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
```

### 第二步：启动所有服务

```bash
docker-compose up -d
```

等待所有服务就绪（约 30-60 秒），检查状态：

```bash
docker-compose ps
# 期望：nat-ui、nat-orchestrator、milvus-standalone(healthy)、nat-api 全部运行
```

### 第三步：访问系统

打开浏览器：**http://localhost:4000**

直接提问即可，例如：
- "ManuTerm 定期寿险的保障内容是什么？"
- "VHIS 自愿医保和普通医保有什么区别？"
- "年金险如何帮助退休规划？"
- "比较 ManuPremier Protector 和 Whole-in-One Prime"

---

## Gmail 邮件自动回复

`nat-email-agent` 服务会自动监控 Gmail 收件箱，对客户来信用 RAG 知识库生成专业保险回复。

### 一次性认证设置

> 前提：需在本机安装 Node.js 18+

```bash
# 1. 安装 Google Workspace CLI
npm install -g @googleworkspace/cli

# 2. 创建 GCP 项目（需要 gcloud CLI）并设置 Gmail API
gws auth setup

# 若无 gcloud，可手动在 Google Cloud Console 创建 OAuth 凭据：
#   https://console.cloud.google.com/apis/credentials
#   应用类型选 "Desktop app"，下载 JSON 放到：
#   C:\Users\<用户名>\.config\gws\client_secret.json

# 3. 授权 Gmail 读写权限
gws auth login -s gmail

# 4. 导出凭据到项目根目录
gws auth export --unmasked > gws_credentials.json
```

> `gws_credentials.json` 包含 OAuth token，已加入 `.gitignore`，请勿提交到版本库。

### 启动邮件服务

```bash
docker-compose up -d --build nat-email-agent

# 查看实时日志
docker-compose logs -f nat-email-agent
```

### 工作原理

1. 每 30 秒轮询 Gmail 收件箱中未读且未标记 `AI-Processed` 的邮件
2. 解析来信内容（发件人、主题、正文）
3. 调用 `nat-orchestrator:8100/generate` 通过 RAG 生成专业回复
4. 自动检测来信语言（中文 / 英文），以相同语言回复
5. 使用 `gws gmail +reply` 发送正式邮件回复（自动维护邮件线程）
6. 为原邮件添加 `AI-Processed` 标签，防止重复处理

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` | `/app/gws_credentials.json` | OAuth 凭据路径 |
| `ORCHESTRATOR_URL` | `http://nat-orchestrator:8100` | Orchestrator 地址 |
| `POLL_INTERVAL_SECONDS` | `30` | 轮询间隔（秒） |

---

## PDF 知识库管理

### 查看当前知识库状态

```bash
# 进入 orchestrator 容器执行检查
docker exec nat-orchestrator python check_categories.py
```

### 重新入库所有 PDF

```bash
# 批量入库 PDF 目录下所有产品手册
docker exec nat-orchestrator bash /app/ingest_all.sh

# 或进入容器手动执行
docker exec -it nat-orchestrator bash
python rag_ingest.py --pdf-path /app/PDF/your-file.pdf --no-mineru
```

---

## 文件结构

```
capstoneProject/
├── docker-compose.yml              # Docker 编排（含 nat-email-agent 服务）
├── Dockerfile                      # 主应用镜像（Python 3.11 + NAT）
├── Dockerfile.email                # 邮件 Agent 镜像（Node.js 20 + Python 3 + gws）
│
├── workflow_orchestrator.yaml      # 主调度 Agent（tool_calling_agent + qwen-plus）
├── workflow_agent_life.yaml        # 寿险专业 Agent（tool_calling_agent，备用）
├── workflow_agent_savings.yaml     # 储蓄险专业 Agent（备用）
├── workflow_agent_medical.yaml     # 医疗险专业 Agent（备用）
├── workflow_agent_critical.yaml    # 危疾险专业 Agent（备用）
│
├── email_agent.py                  # Gmail 邮件自动回复服务（gws + orchestrator）
├── rag_mcp.py                      # RAG 检索 MCP 服务（category-aware Milvus 检索）
├── agent_router_mcp.py             # Agent 路由 MCP 工具（HTTP 路由到专业 Agent）
├── rag_ingest.py                   # PDF 向量化入库脚本
├── ingest_all.sh                   # 批量 PDF 入库脚本
├── check_categories.py             # 知识库分类统计诊断脚本
│
├── api.py                          # FastAPI 后端（知识库管理接口，端口 8000）
│
├── gws_credentials.json            # Gmail OAuth 凭据（本地生成，已加入 .gitignore）
│
├── nat-ui/                         # NeMo Agent Toolkit UI（Next.js 前端）
│   ├── .env                        # UI 环境变量配置
│   └── public/content/
│       ├── welcome.md              # 欢迎页内容
│       └── promptSuggestions.json  # 提示词建议
│
├── PDF/                            # 宏利香港保险产品 PDF（33 份）
│
└── packages/                       # NVIDIA NAT 本地包
    ├── nvidia_nat_core/
    ├── nvidia_nat_mcp/
    ├── nvidia_nat_fastmcp/
    ├── nvidia_nat_langchain/
    └── nvidia_nat_llama_index/
```

---

## 环境变量说明

| 变量 | 必需 | 说明 |
|------|------|------|
| `NVIDIA_API_KEY` | 是 | NVIDIA NIM 密钥，用于向量模型 `nv-embedqa-e5-v5`（embedding） |
| `DASHSCOPE_API_KEY` | 是 | 阿里云百炼密钥，用于 `qwen-plus` LLM（问答生成） |
| `MILVUS_HOST` | 否 | Milvus 主机（Docker 内默认 `milvus`） |
| `MILVUS_PORT` | 否 | Milvus 端口（默认 `19530`） |
| `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` | 邮件功能必需 | gws OAuth 凭据路径，容器内默认 `/app/gws_credentials.json` |
| `ORCHESTRATOR_URL` | 否 | Email Agent 调用的 Orchestrator 地址（默认 `http://nat-orchestrator:8100`） |
| `POLL_INTERVAL_SECONDS` | 否 | Gmail 轮询间隔秒数（默认 `30`） |

---

## 技术栈

| 层级 | 技术选型 | 版本/说明 |
|------|----------|-----------|
| **LLM** | `qwen-plus`（阿里云百炼） | OpenAI 兼容接口，中文最优 |
| **Embedding** | NVIDIA NIM `nv-embedqa-e5-v5` | 1024 维向量，语义检索 |
| **向量数据库** | Milvus Standalone | 2,438 个分块，category 过滤 |
| **Agent 框架** | NVIDIA NeMo Agent Toolkit | `tool_calling_agent` 工作流 |
| **MCP 工具** | FastMCP | RAG 检索工具服务 |
| **前端** | NeMo Agent Toolkit UI | Next.js 14，OpenAI 兼容接入 |
| **后端** | FastAPI | 知识库管理 REST API |
| **容器编排** | Docker Compose | 一键启动全部服务 |

---

## 2026 版本维护与升级须知（重要！）

作为该 Capstone Project 的最终稳定版（2026 年定档），请后继维护者严格遵守以下约定：

1. **核心框架锁定**
   - 当前底层使用的 NVIDIA NeMo Agent Toolkit (NAT) 核心包版本被严格锁定在 `v0.0.1`（存放于 `packages/` 内）。
   - **强烈警告**：切勿尝试将其升级至 `v1.5.0` 或更新版本。NAT 的新版包含了大量的破坏性重构（包含路由与核心机制的变化），强行升级将导致 `workflow_orchestrator.yaml` 瘫痪以及 `rag_mcp.py` 检索逻辑完全崩溃。
   - 现有的 `qwen-plus` 意图识别 + category-aware RAG 架构已通过大量测试，状态极为稳定，建议优先投入精力在知识库更新（PDF扩充）与业务 Prompt 优化上，而非盲目追求框架版本号。

2. **前端 UI (nat-ui) 高度本地化说明**
   - 本项目的前端已脱离了原始英文脚手架，经过了彻底的本地化与定制化改造（使用原生的 `next-i18next`）。
   - **核心改动包括**：全站繁体中文 / 英文双语支持、状态数据持久化（从 `sessionStorage` 整体迁移至 `localStorage` 以解决页面刷新后记录丢失的问题）、强制隐藏了不必要且冗余的用户系统/登录按钮以及历史切换开关。
   - **强烈警告**：切勿直接拉取官方最新的 `nat-ui` 代码覆盖现有代码，这会导致上述深度定制的本地化多语言资源与界面精简逻辑被完全冲掉。

---

## 常见问题

**Q: 系统访问很慢或超时**  
A: `qwen-plus` 首次响应约 15-25 秒。若超时，检查 `DASHSCOPE_API_KEY` 是否正确，以及网络是否可访问 `dashscope.aliyuncs.com`。

**Q: 回答说"知识库未找到相关内容"**  
A: PDF 可能未入库。执行 `docker exec nat-orchestrator python check_categories.py` 检查知识库状态，如为空则运行 `ingest_all.sh` 重新入库。

**Q: Milvus 健康检查失败**  
A: Milvus Standalone 启动较慢，等待约 2-3 分钟。查看日志：`docker-compose logs milvus-standalone`。

**Q: 如何更换为更强的模型（如 qwen-max）？**  
A: 修改 `workflow_orchestrator.yaml` 中的 `model_name: qwen-plus` 为 `qwen-max`，然后执行 `docker-compose restart nat-orchestrator`。

**Q: 如何添加新的保险产品 PDF？**  
A: 将 PDF 放入 `PDF/` 目录，执行：
```bash
docker exec nat-orchestrator python rag_ingest.py --pdf-path /app/PDF/new-product.pdf --no-mineru
```

**Q: 邮件自动回复服务提示 "gws command failed"**  
A: OAuth token 可能已过期。在宿主机重新执行：
```bash
gws auth login -s gmail
gws auth export --unmasked > gws_credentials.json
docker-compose restart nat-email-agent
```

**Q: 邮件回复内容包含 Markdown 符号（**加粗**、## 标题等）**  
A: `email_agent.py` 内置了 `_clean_reply()` 清理函数，会自动移除 Markdown 格式。若仍有问题，查看日志：`docker-compose logs nat-email-agent`。

**Q: Docker 重启后 Milvus 不自动启动**  
A: 已通过 `restart: unless-stopped` 策略解决。若仍有问题，手动执行：
```bash
docker-compose up -d etcd minio milvus
```

---

## 开发说明

### 本地修改 Workflow（无需重建镜像）

所有 `workflow_*.yaml` 和 `rag_mcp.py` 均通过 Docker volume 挂载，修改后直接重启容器即可：

```bash
# 修改 workflow_orchestrator.yaml 后
docker-compose restart nat-orchestrator
```

### 查看 Agent 运行日志

```bash
docker-compose logs -f nat-orchestrator
```

### API 文档

FastAPI 后端（端口 8000）提供 Swagger 文档：http://localhost:8000/docs

NAT Orchestrator OpenAPI：http://localhost:8100/openapi.json

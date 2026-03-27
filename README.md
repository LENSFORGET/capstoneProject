# 宏利保险 AI 智能顾问系统

基于 **NVIDIA NeMo Agent Toolkit (NAT)** 构建的宏利香港保险 RAG 问答系统。
系统以 33 份官方产品手册 PDF 为知识库，通过阿里云百炼 `qwen-plus` 大模型 + NVIDIA NIM 向量检索，
提供覆盖寿险、储蓄险、医疗险、危疾险全险种的专业中文保险咨询服务。

**访问地址：http://localhost:4000**

---

## 系统架构

```
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
  └─ insurance_docs 集合
       ├─ 33 份宏利香港 PDF 手册
       ├─ 2,438 个语义分块
       └─ NVIDIA NIM nv-embedqa-e5-v5 向量化
```

### Docker 服务列表

| 服务 | 说明 | 端口 |
|------|------|------|
| `nat-ui` | NeMo Agent Toolkit UI 前端 | 4000 |
| `nat-orchestrator` | 主调度 Agent（qwen-plus + RAG） | 8100 |
| `milvus-standalone` | 向量数据库 | 19530 |
| `milvus-minio` | Milvus 对象存储 | — |
| `milvus-etcd` | Milvus 元数据存储 | — |
| `nat-api` | FastAPI 后端（知识库管理接口） | 8000 |

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
├── docker-compose.yml              # Docker 编排
├── Dockerfile                      # 主应用镜像（Python 3.11 + NAT）
│
├── workflow_orchestrator.yaml      # 主调度 Agent（tool_calling_agent + qwen-plus）
├── workflow_agent_life.yaml        # 寿险专业 Agent（备用）
├── workflow_agent_savings.yaml     # 储蓄险专业 Agent（备用）
├── workflow_agent_medical.yaml     # 医疗险专业 Agent（备用）
├── workflow_agent_critical.yaml    # 危疾险专业 Agent（备用）
│
├── rag_mcp.py                      # RAG 检索 MCP 服务（category-aware Milvus 检索）
├── agent_router_mcp.py             # Agent 路由 MCP 工具（HTTP 路由到专业 Agent）
├── rag_ingest.py                   # PDF 向量化入库脚本
├── ingest_all.sh                   # 批量 PDF 入库脚本
├── check_categories.py             # 知识库分类统计诊断脚本
│
├── api.py                          # FastAPI 后端（知识库管理接口，端口 8000）
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

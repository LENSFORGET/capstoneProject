# NAT 小红书保险 RAG 系统

基于 **NVIDIA NeMo Agent Toolkit (NAT)** 构建的保险知识 RAG 问答系统。
通过 LLM 驱动 agent-browser 自动采集小红书保险内容，利用 NVIDIA NIM 向量化后存入 Milvus，支持 RAG 增强的智能保险问答。

---

## 系统架构

```
Docker Compose
├── etcd           - Milvus 元数据存储
├── minio          - Milvus 对象存储
├── milvus         - 向量数据库（Standalone 模式，端口 19530）
└── app            - NAT 应用容器
    ├── agent_browser_mcp.py   (FastMCP) 浏览器自动化工具
    ├── rag_mcp.py             (FastMCP) RAG 检索工具
    ├── workflow_scraper.yaml  (NAT)     小红书爬虫 Workflow
    ├── rag_ingest.py          (Python)  向量入库脚本
    └── workflow_rag.yaml      (NAT)     RAG 问答 Workflow
```

### 两条独立管道

**管道一：PDF 知识库构建（主 RAG 数据源）**
```
python rag_ingest.py
  └─ pypdf 解析 manupremier-protector.pdf
       └─ NVIDIA NIM nv-embedqa-e5-v5 向量化
            └─ pymilvus → Milvus insurance_docs collection

# 可选：同时入库小红书数据作为补充
python rag_ingest.py --include-xhs
```

**管道二：小红书用户洞察（完全独立，不向 RAG 入库）**
```
nat run workflow_scraper.yaml
  └─ GLM 5 理解用户发帖（不是简单提取）
       ├─ 分析用户需求、痛点、情感倾向
       ├─ 洞察活跃用户真实关注点
       └─ 生成用户洞察报告 → /app/data/xhs_user_insights.md
```

**管道三：RAG 保险问答**
```
nat run workflow_rag.yaml
  └─ GLM 5 调用工具：
       ├─ search_insurance()  → MilvusRetriever 检索 PDF 知识库
       └─ browser tools       → 实时查询最新信息（兜底补充）
```

### 使用的 NAT 核心组件

| 组件 | 来源 | 用途 |
|------|------|------|
| `MilvusRetriever` | `nat.retriever.milvus` | 向量检索 |
| `FastMCP` | `nvidia_nat_fastmcp` | MCP 服务框架 |
| `react_agent` | `nvidia_nat_core` | LLM 驱动 Agent |
| `NVIDIAEmbedding` | `llama-index-embeddings-nvidia` | 文本向量化 |

---

## 快速开始

### 前置条件

- Docker Desktop 已安装并运行
- 拥有 NVIDIA API Key（注册：https://build.nvidia.com）
- （可选）小红书账号 Cookie（用于爬取完整内容）

### 第一步：配置环境变量

在项目根目录创建 `.env` 文件：

```bash
# .env
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxx
XHS_COOKIES=               # 可选，小红书登录 Cookie
```

### 第二步：构建并启动所有服务

```bash
docker-compose up -d --build
```

等待所有服务健康（约 2-3 分钟）：

```bash
docker-compose ps
# 期望所有服务状态为 healthy 或 running
```

### 第三步：进入应用容器

```bash
docker exec -it nat-app bash
```

### 第四步：将 PDF 产品手册向量化入库（RAG 主数据源）

```bash
# 将 manupremier-protector.pdf 解析并入库
python rag_ingest.py

# 清空旧数据后重新入库（全量更新）
python rag_ingest.py --clear

# 同时入库小红书数据作为补充（需先运行洞察 workflow）
python rag_ingest.py --include-xhs
```

### 第五步：小红书内容采集

#### 5a. 首次登录（仅需执行一次）

采用 **Docker 内 noVNC** 方案，无需宿主机图形界面：

```bash
# 启动登录助手容器（会自动构建镜像，约 2-3 分钟）
docker-compose --profile login up xhs-login --build
```

启动后：
1. 用浏览器打开 **http://localhost:6080**
2. 在网页中可以看到 Chromium 浏览器，手动完成小红书登录（扫码或账号密码）
3. 确认登录成功后，回到终端按 **Enter**
4. 会话自动保存至共享卷 `/app/data/xhs_state.json`

> 会话有效期通常为 30 天，过期后重复此步骤即可，无需修改代码。

#### 5b. 运行爬虫（登录后每次使用）

```bash
# 进入 nat-app 容器
docker exec -it nat-app bash

# 运行爬虫（NAT React Agent 自动加载登录态、采集帖子/用户/评论）
nat run workflow_scraper.yaml
```

爬虫会：
- 自动加载 `/app/data/xhs_state.json` 恢复登录状态
- 依次搜索：保险、重疾险、医疗险、寿险推荐、买保险踩坑
- 每个关键词采集 5-10 篇帖子（含正文、评论、互动数、作者信息）
- 将结果结构化存入 PostgreSQL（xhs_posts / xhs_users / xhs_comments）

### 第六步：启动 RAG 问答

```bash
nat run workflow_rag.yaml
```

GLM 5 将等待你的问题，例如：
- "重疾险和医疗险有什么区别？"
- "车险理赔流程是什么？"
- "年轻人第一份保险应该买什么？"

---

## 文件结构

```
capstoneProject/
├── docker-compose.yml          # Docker 编排（etcd + minio + milvus + app + api + frontend + xhs-login）
├── Dockerfile                  # 主应用镜像（Python 3.11 + Node.js + NAT + agent-browser）
├── Dockerfile.login            # 登录助手镜像（主镜像 + Xvfb + x11vnc + noVNC）
├── agent_browser_mcp.py        # 浏览器 FastMCP 服务（--session-name xhs，含 state_load/state_save）
├── xhs_login_helper.py         # 小红书登录助手脚本（配合 xhs-login 容器使用）
├── rag_mcp.py                  # RAG 检索 FastMCP 服务（MilvusRetriever）
├── rag_ingest.py               # 数据向量化入库脚本
├── workflow_browser.yaml       # 通用浏览器 Workflow
├── workflow_scraper.yaml       # 小红书爬虫 Workflow（NAT React Agent + GLM-5）
├── workflow_rag.yaml           # RAG 保险问答 Workflow
├── api.py                      # FastAPI 后端（RAG + 知识库管理 + 小红书数据接口）
├── frontend/                   # Next.js 前端（Pinecone 风格 SaaS UI）
├── packages/                   # NVIDIA NAT 本地包
│   ├── nvidia_nat_core/
│   ├── nvidia_nat_mcp/
│   ├── nvidia_nat_fastmcp/
│   ├── nvidia_nat_llama_index/
│   └── ...（其他 NAT 包）
└── README.md
```

---

## 环境变量说明

| 变量 | 必需 | 说明 |
|------|------|------|
| `NVIDIA_API_KEY` | 是 | NVIDIA NIM API 密钥（GLM 5 + 向量模型共用） |
| `XHS_COOKIES` | 否 | 小红书登录 Cookie（提升爬取质量） |
| `MILVUS_HOST` | 否 | Milvus 主机（Docker 内默认 `milvus`） |
| `MILVUS_PORT` | 否 | Milvus 端口（默认 `19530`） |

---

## 数据更新

当需要更新知识库中的保险内容时，重新执行采集和入库流程：

```bash
# 进入容器
docker exec -it nat-app bash

# 重新爬取（覆盖旧 JSON）
nat run workflow_scraper.yaml

# 清空旧向量数据并重新入库
python rag_ingest.py --clear
```

---

## 常见问题

**Q: docker-compose up 后 milvus 服务一直不健康**
A: Milvus Standalone 启动较慢，等待约 2-3 分钟后再检查。如果仍有问题，运行 `docker-compose logs milvus` 查看日志。

**Q: nat run workflow_scraper.yaml 提示需要登录小红书 / state 文件不存在**
A: 请先执行登录步骤：`docker-compose --profile login up xhs-login --build`，打开 http://localhost:6080 完成登录并按 Enter 保存会话，之后再运行爬虫。

**Q: rag_ingest.py 提示数据文件不存在**
A: 请先运行 `nat run workflow_scraper.yaml` 完成爬取，再运行入库脚本。

**Q: RAG 回答时提示知识库未找到相关内容**
A: 确认已完成入库步骤。可运行 `get_collection_stats()` 工具检查知识库状态。

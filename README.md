# NAT 小红书保险 RAG 系统

基于 **NVIDIA NeMo Agent Toolkit (NAT)** 构建的保险知识 RAG 问答系统。
通过 LLM 驱动 agent-browser 自动采集小红书保险内容，利用 NVIDIA NIM 向量化后存入 Milvus，支持 RAG 增强的智能保险问答，并提供 Web 可视化界面。

---

## 系统架构

### 服务总览

```
Docker Compose（docker-compose.yml）
│
├── 基础设施层
│   ├── etcd        (milvus-etcd)       Milvus 元数据存储
│   ├── minio       (milvus-minio)      Milvus 对象存储
│   ├── milvus      (milvus-standalone) 向量数据库，端口 19530
│   └── postgres    (xhs-postgres)      小红书数据结构化存储，端口 5432
│
├── 应用层
│   ├── app         (nat-app)           NAT 核心容器（CLI 交互、爬虫、RAG 命令行）
│   ├── api         (nat-api)           FastAPI 后端，端口 8000
│   ├── ui          (nat-ui)            Gradio Web UI，端口 8080
│   └── frontend    (nat-frontend)      Next.js 前端，端口 3000
│
└── 按需服务（profiles）
    ├── xhs-login   (xhs-login)         小红书登录助手（noVNC），端口 6080
    └── test        (nat-test)          自动化测试容器
```

### 访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| **Next.js 前端** | http://localhost:3000 | 主 Web 界面（Pinecone 风格 SaaS UI） |
| **FastAPI 后端** | http://localhost:8000 | REST API（RAG 问答 / 知识库管理 / 小红书数据） |
| **Gradio UI** | http://localhost:8080 | 备用 Web 界面（稳定原始界面） |
| **小红书登录** | http://localhost:6080 | noVNC 浏览器界面（按需启动） |
| **Milvus** | localhost:19530 | 向量数据库直连（容器内使用） |

### 三条数据管道

```
管道一：PDF 知识库构建（主 RAG 数据源）
─────────────────────────────────────
manupremier-protector.pdf
  → MinerU（主引擎）或 pypdf（兜底）解析
  → NVIDIA NIM nv-embedqa-e5-v5（1024维）向量化
  → Milvus insurance_docs collection
  → 供 RAG 问答检索使用

管道二：小红书内容采集（独立管道，存入 PostgreSQL）
──────────────────────────────────────────────────
workflow_scraper.yaml（NAT tool_calling_agent）
  → agent_browser_mcp.py：驱动 Chromium 访问小红书
  → 采集帖子/用户/评论
  → xhs_db_mcp.py：写入 PostgreSQL
     ├── xhs_posts（帖子数据）
     ├── xhs_users（用户数据）
     └── xhs_comments（评论数据）

管道三：RAG 保险问答
────────────────────
用户提问 → FastAPI /api/chat 或 workflow_rag.yaml
  → NVIDIA NIM nv-embedqa-e5-v5 向量化问题
  → Milvus 相似度检索（Top-5 召回）
  → 组装 Context 注入 Prompt
  → MiniMax M2.1（via NVIDIA NIM）生成回答
  → 流式返回给前端
```

### 核心技术组件

| 组件 | 来源 / 版本 | 用途 |
|------|------------|------|
| `MilvusRetriever` | `nat.retriever.milvus` | 向量检索 |
| `FastMCP` | `nvidia_nat_fastmcp` | MCP 服务框架 |
| `react_agent` / `tool_calling_agent` | `nvidia_nat_core` | LLM 驱动 Agent |
| `NVIDIAEmbedding` | `llama-index-embeddings-nvidia` | 文本向量化（nv-embedqa-e5-v5） |
| `MiniMax M2.1` | NVIDIA NIM via OpenAI API | 生成模型 |
| `agent-browser` | npm 全局包 | Playwright 浏览器自动化 |
| `FastAPI` | Python | 后端 REST API |
| `Next.js 20` | Node.js | 前端框架 |
| `Milvus 2.5` | milvusdb/milvus:v2.5.0 | 向量数据库 |
| `PostgreSQL 16` | postgres:16-bookworm | 结构化数据存储 |

---

## 快速开始

### 前置条件

- **Docker Desktop** 已安装并运行（推荐 Desktop 4.x+）
- 拥有 **NVIDIA API Key**（注册：https://build.nvidia.com）
- （可选）小红书账号，用于采集内容

### 第一步：配置环境变量

在项目根目录创建 `.env` 文件：

```bash
# .env
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxx
XHS_COOKIES=               # 可选，小红书登录 Cookie
POSTGRES_PASSWORD=xhs_secure_pass   # 可选，默认值已足够
```

### 第二步：构建并启动所有服务

```bash
docker-compose up -d --build
```

等待所有服务健康（约 3-5 分钟，Milvus 启动较慢）：

```bash
docker-compose ps
# 期望所有服务状态为 healthy 或 running
```

启动成功后可直接访问：
- **http://localhost:3000** — Next.js 主界面（推荐）
- **http://localhost:8080** — Gradio 备用界面
- **http://localhost:8000** — FastAPI Swagger 文档（/docs）

### 第三步：将 PDF 产品手册向量化入库

> 此步骤为使用 RAG 问答的必要前提。

**方式一（推荐）：通过前端 Web 界面上传**

1. 打开 http://localhost:3000/indexes
2. 选择或新建知识库（如 `insurance_docs`）
3. 点击"上传文档"，选择 PDF 文件
4. 等待向量化完成（进度实时显示）

**方式二：通过命令行入库**

```bash
# 进入应用容器
docker exec -it nat-app bash

# 将 manupremier-protector.pdf 解析并入库（MinerU + pypdf 双引擎）
python rag_ingest.py

# 清空旧数据后重新入库（全量更新）
python rag_ingest.py --clear

# 强制使用 pypdf（跳过 MinerU，速度更快）
python rag_ingest.py --no-mineru

# 同时入库小红书数据作为补充（需先运行采集 workflow）
python rag_ingest.py --include-xhs
```

### 第四步：使用 RAG 问答

**方式一：通过 Web 界面（推荐）**

1. 打开 http://localhost:3000
2. 在聊天界面选择知识库
3. 直接输入保险问题即可

**方式二：通过命令行**

```bash
docker exec -it nat-app bash
nat run --config_file workflow_rag.yaml
```

GLM 5 将等待你的问题，例如：
- "重疾险和医疗险有什么区别？"
- "车险理赔流程是什么？"
- "年轻人第一份保险应该买什么？"

---

## 小红书采集功能

### 第一步：首次登录（仅需执行一次）

采用 **Docker 内 noVNC** 方案，无需宿主机图形界面：

```bash
# 启动登录助手容器（会自动构建镜像，约 2-3 分钟）
docker-compose --profile login up xhs-login --build
```

启动后：
1. 用浏览器打开 **http://localhost:6080**
2. 在网页中可以看到 Chromium 浏览器，手动完成小红书登录（扫码或账号密码）
3. 确认登录成功后，**在另一终端**执行：

   ```bash
   docker exec xhs-login touch /app/data/xhs_login_trigger
   ```

4. 会话自动保存至共享卷 `/app/data/xhs_state.json`

> 详细步骤与常见问题见 [docs/xhs-login.md](docs/xhs-login.md)。会话有效期通常为 30 天，过期后重复此步骤即可。

### 第二步：运行采集

**方式一：通过前端 Web 界面触发**

1. 打开 http://localhost:3000/xhs
2. 确认登录状态（页面显示 `xhs_state.json` 文件信息）
3. 点击"手动采集"按钮，后台自动执行

**方式二：通过命令行**

```bash
# 进入 nat-app 容器
docker exec -it nat-app bash

# 运行爬虫（NAT Agent 自动加载登录态、采集帖子/用户/评论）
nat run --config_file workflow_scraper.yaml --input "请现在开始执行采集任务。"
```

采集结果将自动存入 PostgreSQL（`xhs_posts` / `xhs_users` / `xhs_comments`），可在前端 http://localhost:3000/xhs 查看。

---

## Web 界面说明

### Next.js 前端（http://localhost:3000）

| 页面 | 路径 | 功能 |
|------|------|------|
| **聊天** | `/` | RAG 保险问答（流式回答，支持多语言） |
| **知识库** | `/indexes` | 知识库管理（上传 PDF、查看文档、生成摘要、删除） |
| **小红书** | `/xhs` | 采集管理（登录状态、手动触发、帖子数据浏览、AI 分析报告） |

### Gradio UI（http://localhost:8080）

备用 Web 界面，功能与 Next.js 前端类似，适合快速测试。

---

## API 接口文档

FastAPI 后端运行在 http://localhost:8000，Swagger 文档访问 http://localhost:8000/docs。

### 问答接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat` | 流式 RAG 问答（SSE，支持历史消息、多知识库、文档过滤） |

**请求体示例：**
```json
{
  "messages": [{"role": "user", "content": "重疾险和医疗险有什么区别？"}],
  "lang": "简中",
  "kb_name": "insurance_docs",
  "selected_docs": ["manupremier-protector.pdf"]
}
```

### 知识库管理接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/kb/collections` | 列出所有知识库 |
| `POST` | `/api/kb/collections` | 新建知识库 |
| `GET` | `/api/kb/collections/{collection}/status` | 查看知识库状态（文档数量、维度等） |
| `GET` | `/api/kb/collections/{collection}/documents` | 列出知识库中的文档 |
| `POST` | `/api/kb/collections/{collection}/documents/upload` | 上传 PDF 并向量化（流式进度） |
| `DELETE` | `/api/kb/collections/{collection}/documents` | 删除文档 |
| `POST` | `/api/kb/collections/{collection}/documents/metadata` | 更新文档元数据 |
| `POST` | `/api/kb/collections/{collection}/documents/summarize` | AI 生成文档摘要（流式） |

### 小红书数据接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/xhs/stats` | 数据库统计（帖子数/用户数/评论数） |
| `GET` | `/api/xhs/posts` | 帖子列表（支持关键词过滤、点赞数过滤、分页） |
| `GET` | `/api/xhs/login-status` | 登录状态检查（`xhs_state.json` 是否存在） |
| `POST` | `/api/xhs/run-scraper` | 手动触发采集任务（后台执行） |
| `GET` | `/api/xhs/scraper-status` | 当前采集任务状态 |
| `GET` | `/api/xhs/sessions` | 采集会话历史列表 |
| `GET` | `/api/xhs/schedules` | 定时任务列表 |
| `POST` | `/api/xhs/schedules` | 新建定时任务 |
| `DELETE` | `/api/xhs/schedules/{id}` | 删除定时任务 |
| `POST` | `/api/xhs/report` | 基于现有数据生成 AI 分析报告 |

---

## 文件结构

```
capstoneProject/
├── docker-compose.yml          # Docker 编排（9 个服务）
├── Dockerfile                  # 主应用镜像（Python 3.11 + Node.js + NAT + agent-browser）
├── Dockerfile.login            # 登录助手镜像（主镜像 + Xvfb + x11vnc + noVNC）
│
├── agent_browser_mcp.py        # 浏览器 FastMCP 服务（含 state_load/state_save）
├── xhs_db_mcp.py               # PostgreSQL FastMCP 服务（xhs_posts/users/comments CRUD）
├── xhs_login_helper.py         # 小红书登录助手脚本（配合 xhs-login 容器使用）
├── rag_mcp.py                  # RAG 检索 FastMCP 服务（MilvusRetriever）
├── rag_ingest.py               # 数据向量化入库脚本（MinerU + pypdf 双引擎）
│
├── workflow_browser.yaml       # 通用浏览器 Workflow
├── workflow_scraper.yaml       # 小红书爬虫 Workflow（NAT tool_calling_agent + MiniMax M2.1）
├── workflow_rag.yaml           # RAG 保险问答 Workflow（NAT react_agent + MiniMax M2.1）
│
├── api.py                      # FastAPI 后端（RAG + 知识库管理 + 小红书数据接口）
├── ui.py                       # Gradio Web UI（备用界面，端口 8080）
│
├── manupremier-protector.pdf   # 宏利优越终身保产品手册（主 RAG 数据源）
├── xhs_db_init.sql             # PostgreSQL 初始化 SQL（表结构定义）
│
├── frontend/                   # Next.js 前端（Pinecone 风格 SaaS UI）
│   └── src/app/
│       ├── page.tsx            # 聊天页面
│       ├── indexes/            # 知识库管理页面
│       └── xhs/                # 小红书数据页面
│
├── packages/                   # NVIDIA NAT 本地包（editable 模式安装）
│   ├── nvidia_nat_core/        # 核心框架（builders, CLI, LLM, retriever）
│   ├── nvidia_nat_mcp/         # MCP 协议实现
│   ├── nvidia_nat_fastmcp/     # FastMCP 服务框架
│   ├── nvidia_nat_llama_index/ # LlamaIndex 集成（含 MilvusRetriever）
│   └── ...（其他 NAT 扩展包）
│
├── docs/
│   └── xhs-login.md            # 小红书登录详细指南
│
├── test_unit.py                # 单元测试（无需 API Key）
├── test_integration.py         # 集成测试（无需 API Key）
├── test_e2e.py                 # 端到端测试（需要 NVIDIA_API_KEY）
└── pytest.ini                  # pytest 配置
```

---

## 环境变量说明

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `NVIDIA_API_KEY` | **是** | — | NVIDIA NIM API 密钥（GLM 5 + 向量模型共用） |
| `XHS_COOKIES` | 否 | — | 小红书登录 Cookie（可选，提升爬取质量） |
| `MILVUS_HOST` | 否 | `milvus` | Milvus 主机（Docker 内默认 `milvus`） |
| `MILVUS_PORT` | 否 | `19530` | Milvus 端口 |
| `POSTGRES_HOST` | 否 | `postgres` | PostgreSQL 主机 |
| `POSTGRES_PORT` | 否 | `5432` | PostgreSQL 端口 |
| `POSTGRES_DB` | 否 | `xhs_data` | 数据库名 |
| `POSTGRES_USER` | 否 | `xhs_user` | 数据库用户名 |
| `POSTGRES_PASSWORD` | 否 | `xhs_secure_pass` | 数据库密码 |

---

## 数据库结构

### Milvus（向量知识库）— `insurance_docs` Collection

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INT64（自增主键） | 唯一标识 |
| `vector` | FLOAT_VECTOR(1024) | 文本向量 |
| `text` | VARCHAR(4096) | 文本块内容 |
| `title` | VARCHAR(512) | 标题 / 章节 |
| `source` | VARCHAR(128) | 来源（如 `pdf_mineru:file.pdf`） |
| `url` | VARCHAR(1024) | 来源 URL |
| `scraped_at` | VARCHAR(64) | 入库时间戳 |
| `content_type` | VARCHAR(32) | 内容类型：`text`/`table`/`image`/`title` |

### PostgreSQL（小红书结构化数据）— `xhs_data`

| 表名 | 说明 |
|------|------|
| `xhs_search_sessions` | 采集会话记录（关键词、状态、时间） |
| `xhs_posts` | 帖子数据（标题、正文、标签、互动数） |
| `xhs_users` | 用户数据（昵称、粉丝数、主页链接） |
| `xhs_comments` | 评论数据（内容、点赞数、所属帖子） |
| `kb_documents` | 知识库文档元数据（文件名、摘要） |

---

## 测试

```bash
# 运行单元 + 集成测试（无需 NVIDIA_API_KEY）
docker-compose run --rm test

# 运行指定测试文件
docker-compose run --rm test pytest test_unit.py -v
docker-compose run --rm test pytest test_integration.py -v

# 运行端到端测试（需要 NVIDIA_API_KEY）
docker-compose run --rm test pytest test_e2e.py -v
```

---

## 数据更新

当需要更新知识库中的保险内容时，重新执行采集和入库流程：

```bash
# 进入容器
docker exec -it nat-app bash

# 重新爬取（自动存入 PostgreSQL）
nat run --config_file workflow_scraper.yaml --input "请现在开始执行采集任务。"

# 清空旧向量数据并重新入库
python rag_ingest.py --clear
```

---

## 常见问题

**Q: docker-compose up 后 milvus 服务一直不健康**  
A: Milvus Standalone 启动较慢，等待约 3-5 分钟后再检查。如果仍有问题，运行 `docker-compose logs milvus` 查看日志。

**Q: nat run --config_file workflow_scraper.yaml 提示需要登录小红书 / state 文件不存在**  
A: 请先执行登录步骤：`docker-compose --profile login up xhs-login --build`，打开 http://localhost:6080 完成登录后，在另一终端执行 `docker exec xhs-login touch /app/data/xhs_login_trigger` 保存会话，详见 [docs/xhs-login.md](docs/xhs-login.md)。

**Q: rag_ingest.py 提示数据文件不存在**  
A: 请先运行 `nat run --config_file workflow_scraper.yaml --input "请现在开始执行采集任务。"` 完成爬取，再运行入库脚本。

**Q: RAG 回答时提示知识库未找到相关内容**  
A: 确认已完成入库步骤（第三步）。可访问 http://localhost:8000/api/kb/collections/insurance_docs/status 检查向量数量。

**Q: 前端 http://localhost:3000 打开白屏或报错**  
A: 前端容器在首次启动时会执行 `npm install`，需要等待 1-2 分钟完成依赖安装后才能正常访问。可运行 `docker-compose logs frontend` 查看进度。

**Q: API 返回 "No valid NVIDIA_API_KEY configured"**  
A: 请确认 `.env` 文件中已设置有效的 `NVIDIA_API_KEY`，且执行了 `docker-compose up -d` 重新加载环境变量。

**Q: 小红书采集时出现"安全限制 IP 存在风险，请切换可靠网络环境后重试 300012"**  
A: 小红书检测到当前网络为风险 IP。建议：①关闭 VPN/代理；②使用家庭宽带或手机热点；③等待 30 分钟后重试。详见 [docs/xhs-login.md](docs/xhs-login.md)。

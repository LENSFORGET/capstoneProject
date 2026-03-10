# NAT 小红书保险 RAG 系统 - 项目报告

---

## 一、项目介绍 (Introduction of Project)

### 1.1 背景

本项目为基于 **NVIDIA NeMo Agent Toolkit (NAT)** 构建的保险知识 RAG 问答系统，正式名称为 **NAT 小红书保险 RAG 系统**（Xiaohongshu Insurance RAG System）。系统旨在将大语言模型（LLM）驱动的智能体、向量检索增强生成（RAG）技术与社交媒体数据采集相结合，为保险领域提供可检索、可问答、可洞察的综合解决方案。

保险行业信息密度高、更新频繁，用户常通过小红书等社交平台获取保险相关经验与建议。传统检索系统难以兼顾结构化产品手册与非结构化用户讨论。本项目通过以下三条数据管道解决这一问题：PDF 产品手册向量化入库、小红书用户内容自动采集、以及基于 Milvus 的 RAG 检索与 LLM 问答。

### 1.2 目标

- **RAG Q&A 系统**：以保险产品 PDF（如 manupremier-protector.pdf）为主数据源，通过 NVIDIA NIM 向量模型（nv-embedqa-e5-v5）与 Milvus 向量库实现语义检索，结合 GLM-5 等 LLM 提供结构化、可追溯的保险问答。
- **智能采集系统**：利用 agent-browser 与 NAT 工具调用 Agent，自动登录、搜索、浏览小红书保险相关内容，将帖子、用户、评论存入 PostgreSQL，并可选地作为 RAG 补充数据源。
- **统一 Web 前端**：提供 Next.js 16 + Pinecone 风格 SaaS UI，支持知识库管理、流式聊天、小红书数据浏览与采集控制，便于运营与演示。

### 1.3 技术栈概览

| 层级 | 技术选型 |
|------|----------|
| 向量存储 | Milvus (Standalone)，辅以 etcd、MinIO |
| 关系数据库 | PostgreSQL 16 |
| embedding | NVIDIA NIM nv-embedqa-e5-v5 |
| LLM | NVIDIA API 上的 minimaxai/minimax-m2.1（兼容 GLM 系） |
| Agent 框架 | NVIDIA NAT（tool_calling_agent / react_agent） |
| MCP 协议 | FastMCP 封装 rag_mcp、agent_browser_mcp、xhs_db_mcp |
| 后端 | FastAPI（api.py） |
| 前端 | Next.js 16、React 19、Tailwind CSS 4 |

---

## 二、当前进度 (Current Progress)

### 2.1 基础设施与部署

- **Docker Compose 编排**：已完成 etcd、minio、milvus、postgres、app、api、frontend、ui、xhs-login、test 等多服务配置，网络与卷均已打通。
- **主应用镜像**：Dockerfile 集成 Python 3.11、Node.js、NAT 包、agent-browser、MinerU，支持 PDF 解析与浏览器自动化。
- **登录助手镜像**：Dockerfile.login 提供 noVNC 图形界面，用户可在浏览器中完成小红书登录，会话持久化至 app_data 卷，供 nat-app 复用。

### 2.2 RAG 知识库管道

- **PDF 解析**：`rag_ingest.py` 支持 MinerU（结构化提取）与 pypdf（兜底）双引擎，可解析表格、图片描述等内容。
- **向量入库**：NVIDIA NIM embedding + pymilvus 实现文本分块、向量化与 Milvus 入库，支持 `--clear`、`--no-mineru`、`--include-xhs` 等参数。
- **Milvus 集合**：`insurance_docs` 集合含 vector(1024 维)、text、title、source、url、content_type 等字段，支持按 source 过滤检索。
- **rag_mcp.py**：FastMCP 服务暴露 `search_insurance()`、`get_collection_stats()` 等工具，供 NAT workflow 调用。

### 2.3 小红书采集管道

- **workflow_scraper.yaml**：采用 `tool_calling_agent`（非 react_agent），结合 browser 与 xhs_db 两组 MCP 工具，实现登录态恢复、搜索、帖子与评论采集。
- **agent_browser_mcp.py**：封装 agent-browser CLI，提供 navigate、snapshot、click、type_text、press_key、state_load、state_save 等工具，并加入 `time.sleep(3)` 节流以规避 429 限流。
- **xhs_db_mcp.py**：提供 start_session、finish_session、save_post、save_user、save_comment、get_db_stats 等工具，将结构化数据写入 PostgreSQL。
- **PostgreSQL Schema**：xhs_posts、xhs_users、xhs_comments、xhs_search_sessions、kb_documents 等表及全文搜索、热门帖视图已就绪。
- **突破性改进**：根据 docs/xhs-scraper-breakthrough.md，已完成从 react_agent 到 tool_calling_agent 的切换、Prompt 硬编码选择器、MCP 层节流、后台采集生命周期管理（finally 块回滚 running 状态）等关键修复，实现采集链路闭环。

### 2.4 API 与前端

- **api.py**：提供 `/api/chat`（流式 RAG 对话）、`/api/kb/*`（知识库 CRUD、PDF 上传、文档元数据、摘要生成）、`/api/xhs/*`（登录态、采集触发、会话列表、定时任务、AI 报告）等接口。
- **Chat 页面**：支持多知识库、文档过滤、多语言（简中/繁中/EN），流式渲染回复。
- **Indexes 页面**：集合管理、PDF 上传、文档删除、元数据编辑、AI 摘要批量生成。
- **XHS 页面**：登录态展示、手动采集、采集状态轮询、会话表格、关键词统计、帖子搜索、定时任务配置、AI 分析报告生成。
- **其他页面**：Dashboard、NAT Chat、Workflows、Settings、API Docs 等占位或入口已存在。

### 2.5 测试

- **test_unit.py**：覆盖 xhs_db_mcp 的 _safe_int/_safe_str、rag_ingest 的 chunk_text、table_html_to_text、_make_doc、load_xhs_documents、rag_mcp 的 NVIDIAEmbeddingAdapter 等单元逻辑，无需外部服务。
- **test_integration.py** / **test_e2e.py**：集成与端到端测试，e2e 需 NVIDIA_API_KEY。

### 2.6 文档与配置

- **CLAUDE.md**：项目架构、命令、环境变量、数据管道说明。
- **README.md**：快速开始、常见问题。
- **docs/xhs-login.md**：小红书登录助手使用指南。
- **docs/xhs-scraper-breakthrough.md**：采集架构突破与技术复盘。

---

## 三、面临的问题 (Issues Faced)

### 3.1 小红书采集相关

- **DOM 与 Token 爆炸**：小红书首页为无限瀑布流，snapshot 返回可达 20,000+ Token，导致 LLM 推理缓慢或挂起。当前通过 Prompt 硬编码选择器（如 @e2）绕开首页 snapshot，但扩展性有限。
- **网络与风控**：云服务器、办公网、VPN 等环境易触发小红书「IP 存在风险」错误（300012），需更换为家庭宽带或手机热点，或考虑住宅代理。
- **登录态维护**：xhs_state.json 依赖手动登录与 noVNC 流程，会话约 30 天有效，过期需重新执行登录步骤。
- **定时任务未自动执行**：定时任务配置保存在 xhs_schedules.json，但实际执行需依赖系统 cron 或外部调度调用 `POST /api/xhs/run-scraper`，目前无内置调度器。

### 3.2 LLM 与 API 相关

- **模型与 API 变更**：文档多处提及 GLM-5，实际 api.py 与 workflow 使用 minimaxai/minimax-m2.1，存在命名与文档不一致；NVIDIA API 限流（429）已通过节流缓解，但仍需关注配额与成本。
- **摘要与报告质量**：文档摘要与 XHS 报告依赖 LLM 生成，易受模型输出稳定性影响，需人工抽查与迭代 Prompt。

### 3.3 架构与运维

- **采集与 RAG 数据分离**：小红书数据默认存入 PostgreSQL，不入 RAG；需显式 `--include-xhs` 才会向量化入库，容易造成理解偏差。
- **Windows 环境适配**：端口 3000 可能被保留，前端使用 4000；docker-compose 中 api 启用 WATCHFILES_FORCE_POLLING 以应对挂载 I/O 问题。
- **GPU 预留**：ui、api 服务配置了 GPU 预留，在无 GPU 环境下可能影响启动，需根据实际环境调整。
- **NAT 包可编辑安装**：packages 下 NAT 包以 -e 安装，需 SETUPTOOLS_SCM_PRETEND_VERSION 等环境变量，对新人上手有一定门槛。

### 3.4 前端与体验

- **API 代理配置**：Next.js 通过 rewrites 将 /api 代理到后端，Docker 内使用 API_UPSTREAM；本地开发需确保后端可达。
- **错误展示**：部分接口错误通过 hint 或 message 传递，前端需统一错误处理与用户提示。
- **capstone-nat-ui**：git status 显示存在另一套 capstone-nat-ui 目录，与 frontend 关系需澄清，避免冗余维护。

---

## 四、未来计划 (Future Plan)

### 4.1 短期（1–2 个月）

- **轻量级采集工具**：在 agent_browser_mcp.py 中实现专用工具（如 `xhs_search_and_get_links(keyword)`），用 Playwright/BeautifulSoup 直接提取帖子链接，以精简 JSON 返回给 LLM，减少 snapshot 依赖与 Token 消耗。
- **定时采集调度**：在 api 或独立服务中实现内置 cron/APScheduler，按 xhs_schedules.json 配置定期调用 run-scraper，或提供 Webhook 供外部调度触发。
- **RAG 检索与 Prompt 优化**：调整 chunk 大小与 overlap、优化 system prompt，提升回答准确性与引用可追溯性；评估是否需要混合检索（关键词 + 向量）。
- **文档与模型统一**：统一 README、CLAUDE 与代码中的模型名称（GLM-5 vs minimax-m2.1），并补充环境变量与部署检查清单。

### 4.2 中期（3–6 个月）

- **XHS 数据深度整合**：默认或可选地将高质量小红书内容向量化入库，与 PDF 知识库混合检索；增加来源标识与去重策略。
- **反爬与稳定性**：探索住宅代理、请求频率自适应、登录态自动续期等方案，降低「风险 IP」与封禁概率。
- **前端体验**：完善 NAT Chat、Workflows 页面功能；增加知识库健康检查、采集日志流式展示、错误恢复指引。
- **测试与 CI**：扩充集成测试覆盖，增加 API 契约测试；在 CI 中运行 test_unit 与 test_integration，e2e 作为可选流水线。

### 4.3 长期（6 个月以上）

- **多租户与权限**：若面向多团队使用，引入用户/租户隔离、API Key 管理、操作审计。
- **评估与监控**：引入 RAG 评估指标（如 faithfulness、relevance）、采集成功率监控、告警与运维仪表盘。
- **产品化**：考虑将系统打包为可交付的 SaaS 或私有化部署方案，提供一键部署脚本与运维文档。

---

## 附录：关键文件与命令速查

| 类型 | 路径 / 命令 |
|------|-------------|
| RAG 入库 | `python rag_ingest.py` / `--clear` / `--include-xhs` |
| 小红书采集 | `nat run --config_file workflow_scraper.yaml --input "请现在开始执行采集任务。"` |
| RAG 问答 | `nat run --config_file workflow_rag.yaml` |
| 登录助手 | `docker-compose --profile login up xhs-login`，http://localhost:6080 |
| 前端 | http://localhost:4000 |
| API | http://localhost:8000 |
| 测试 | `docker-compose run --rm test` |

---

**文档说明**：本报告基于项目根目录下的 CLAUDE.md、README.md、api.py、docker-compose.yml、workflow_*.yaml、frontend 目录、docs 文档及测试文件分析整理，力求准确反映当前实现与已知问题。具体实施时以实际代码为准。

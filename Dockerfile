# --------------------------------------------------------------------------------------
# 使用 Python 3.11 (Debian Bookworm) 作为基础镜像，满足 nvidia-nat-core 的要求 (>=3.11)
FROM python:3.11-bookworm

# 设置环境变量，确保 Python 行为符合预期
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# 设置工作目录
WORKDIR /app

# --------------------------------------------------------------------------------------
# 1. 安装系统依赖 (Node.js, 浏览器依赖)
# 这些库是 Chromium/Agent-Browser 运行所需的
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    git \
    build-essential \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------------------------
# 2. 安装 Node.js (v20 LTS)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g npm@latest

# --------------------------------------------------------------------------------------
# 3. 安装 agent-browser
# 全局安装，方便通过命令行调用
RUN npm install -g agent-browser

# 初始化 agent-browser (这通常会安装 Playwright 浏览器二进制)
# 如果失败，可能需要手动运行 install
RUN npx playwright install-deps chromium && npx playwright install chromium || echo "Playwright dependencies may need manual installation"

# --------------------------------------------------------------------------------------
# 4. 设置 Python 环境和依赖
# 升级 pip
RUN pip install --no-cache-dir "pip>=23.0"

# 复制本地 packages 目录 (假设构建上下文包含此目录)
COPY packages /app/packages

# 安装 nvidia-nat 包 (以 editable 模式，方便调试)
# 使用 --no-deps 避免它自动升级 numpy，手动管理依赖
# 修复 setuptools-scm 无法检测版本的问题
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NVIDIA_NAT_CORE=0.0.1 \
    SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NVIDIA_NAT_MCP=0.0.1 \
    SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NVIDIA_NAT_FASTMCP=0.0.1 \
    SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NVIDIA_NAT_LLAMA_INDEX=0.0.1

ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NVIDIA_NAT_LANGCHAIN=0.0.1

RUN pip install --no-cache-dir -e /app/packages/nvidia_nat_core \
    && pip install --no-cache-dir -e /app/packages/nvidia_nat_mcp \
    && pip install --no-cache-dir -e /app/packages/nvidia_nat_fastmcp \
    && pip install --no-cache-dir -e /app/packages/nvidia_nat_llama_index \
    && pip install --no-deps -e /app/packages/nvidia_nat_langchain

# 安装 MCP、RAG、数据库及基础依赖
RUN pip install --no-cache-dir \
    "mcp[cli]" \
    "uv" \
    "requests" \
    "pymilvus~=2.5" \
    "llama-index-embeddings-nvidia" \
    "langchain-core" \
    "pypdf>=4.0" \
    "psycopg2-binary>=2.9" \
    "fastapi" \
    "uvicorn" \
    "python-multipart"

# 安装测试框架（pytest + asyncio 支持）
RUN pip install --no-cache-dir \
    "pytest>=8.0" \
    "pytest-asyncio>=0.23"

# --------------------------------------------------------------------------------------
# 安装 MinerU（主要 PDF 解析引擎：文本 + 表格 + 图片）
# 使用 pipeline 后端（纯 CPU，无需 GPU，兼容性最佳）
# mineru[all] 包含所有可选后端；pipeline 是 CPU 模式
RUN pip install --no-cache-dir "mineru[all]"

# 配置 MinerU 模型目录（持久化到 Docker volume，避免重复下载）
ENV MINERU_MODEL_DIR=/app/data/mineru_models \
    MINERU_DEVICE_MODE=cpu

# 预创建模型目录
RUN mkdir -p /app/data/mineru_models

# 验证 MinerU 安装（单行，避免 BuildKit 多行解析问题）
RUN python -c "import mineru; print('MinerU version:', mineru.__version__)" 2>/dev/null || echo "MinerU will initialize on first use"

# --------------------------------------------------------------------------------------
# 5. 复制应用代码
COPY agent_browser_mcp.py /app/
COPY workflow_browser.yaml /app/
COPY workflow_scraper.yaml /app/
COPY rag_ingest.py /app/
COPY rag_mcp.py /app/
COPY workflow_rag.yaml /app/
COPY xhs_db_mcp.py /app/
COPY xhs_db_init.sql /app/
COPY ui.py /app/

# 多 Agent 系统 Workflow 文件
COPY workflow_orchestrator.yaml /app/
COPY workflow_agent_life.yaml /app/
COPY workflow_agent_savings.yaml /app/
COPY workflow_agent_medical.yaml /app/
COPY workflow_agent_critical.yaml /app/

# UI 依赖（Gradio + OpenAI 兼容接口）
RUN pip install --no-cache-dir "gradio>=4.0" "openai>=1.0"

# 复制保险产品手册 PDF 目录（多产品 RAG 知识源）
# 注意：docker-compose 中通过 volume mount ./PDF:/app/PDF:ro 使用
RUN mkdir -p /app/PDF

# 确保数据目录存在（mineru 输出、向量数据、洞察报告）
RUN mkdir -p /app/data/mineru_output /app/data/mineru_models

# 6. (已移除) 修正 Windows 特有的命令
# 脚本已修改为跨平台，无需 sed 替换
# RUN sed -i 's/agent-browser.cmd/agent-browser/g' /app/agent_browser_mcp.py

# 7. 设置入口点
# 默认进入 bash，方便调试和运行命令
CMD ["/bin/bash"]

# --------------------------------------------------------------------------------------
# Use Python 3.11 (Debian Bookworm) as base image to meet nvidia-nat-core requirements (>=3.11)
FROM python:3.11-bookworm

# Set environment variables to ensure predictable Python behavior
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# --------------------------------------------------------------------------------------
# 1. Install system dependencies (Node.js, browser dependencies)
# These libraries are required for Chromium/Agent-Browser to run
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
# 2. Install Node.js (v20 LTS)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g npm@latest

# --------------------------------------------------------------------------------------
# 3. Install agent-browser
# Install globally for easy command-line access
RUN npm install -g agent-browser

# Initialize agent-browser (this usually installs Playwright browser binaries)
# If it fails, manual installation might be required
RUN npx playwright install-deps chromium && npx playwright install chromium || echo "Playwright dependencies may need manual installation"

# --------------------------------------------------------------------------------------
# 4. Setup Python environment and dependencies
# Upgrade pip
RUN pip install --no-cache-dir "pip>=23.0"

# Copy local packages directory (assuming build context includes this directory)
COPY packages /app/packages

# Install nvidia-nat packages (in editable mode for easy debugging)
# Use --no-deps to prevent automatic numpy upgrades, managing dependencies manually
# Fix setuptools-scm failing to detect versions
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

# Install MCP, RAG, database, and base dependencies
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

# Install testing framework (pytest + asyncio support)
RUN pip install --no-cache-dir \
    "pytest>=8.0" \
    "pytest-asyncio>=0.23"

# --------------------------------------------------------------------------------------
# Install MinerU (Primary PDF parsing engine: text + tables + images)
# Use pipeline backend (pure CPU, no GPU required, best compatibility)
# mineru[all] includes all optional backends; pipeline is CPU mode
RUN pip install --no-cache-dir "mineru[all]"

# Configure MinerU model directory (persist to Docker volume to avoid re-downloading)
ENV MINERU_MODEL_DIR=/app/data/mineru_models \
    MINERU_DEVICE_MODE=cpu

# Pre-create model directory
RUN mkdir -p /app/data/mineru_models

# Verify MinerU installation (single line to avoid BuildKit multi-line parsing issues)
RUN python -c "import mineru; print('MinerU version:', mineru.__version__)" 2>/dev/null || echo "MinerU will initialize on first use"

# --------------------------------------------------------------------------------------
# 5. Copy application code
COPY agent_browser_mcp.py /app/
COPY workflow_browser.yaml /app/
COPY workflow_scraper.yaml /app/
COPY rag_ingest.py /app/
COPY rag_mcp.py /app/
COPY workflow_rag.yaml /app/
COPY xhs_db_mcp.py /app/
COPY xhs_db_init.sql /app/
COPY ui.py /app/

# Multi-Agent System Workflow files
COPY workflow_orchestrator.yaml /app/
COPY workflow_agent_life.yaml /app/
COPY workflow_agent_savings.yaml /app/
COPY workflow_agent_medical.yaml /app/
COPY workflow_agent_critical.yaml /app/

# UI dependencies (Gradio + OpenAI compatible interface)
RUN pip install --no-cache-dir "gradio>=4.0" "openai>=1.0"

# Copy insurance product manual PDF directory (multi-product RAG knowledge source)
# Note: Used via volume mount ./PDF:/app/PDF:ro in docker-compose
RUN mkdir -p /app/PDF

# Ensure data directories exist (mineru output, vector data, insight reports)
RUN mkdir -p /app/data/mineru_output /app/data/mineru_models

# 6. (Removed) Fix Windows-specific commands
# Scripts have been modified to be cross-platform, no need for sed replacement
# RUN sed -i 's/agent-browser.cmd/agent-browser/g' /app/agent_browser_mcp.py

# 7. Set entrypoint
# Default to bash for easy debugging and command execution
CMD ["/bin/bash"]

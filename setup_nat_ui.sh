#!/usr/bin/env bash
# =============================================================================
# Setup NeMo Agent Toolkit UI for Capstone Project
# =============================================================================
# This script clones the NVIDIA NeMo Agent Toolkit UI and configures it
# to work with the Insurance RAG backend API.
#
# Usage:
#   chmod +x setup_nat_ui.sh
#   ./setup_nat_ui.sh
# =============================================================================

set -euo pipefail

NAT_UI_DIR="capstone-nat-ui"
NAT_UI_REPO="https://github.com/NVIDIA/NeMo-Agent-Toolkit-UI.git"

echo "============================================="
echo " NeMo Agent Toolkit UI Setup"
echo "============================================="

# ── 1. Clone / Update NAT UI ─────────────────────────────────────────────────
if [ -d "$NAT_UI_DIR/.git" ]; then
    echo "[INFO] NAT UI already cloned at $NAT_UI_DIR, pulling latest..."
    cd "$NAT_UI_DIR"
    git pull --ff-only || echo "[WARN] Pull failed (may have local changes), continuing..."
    cd ..
else
    echo "[INFO] Cloning NeMo Agent Toolkit UI..."
    # Remove empty directory if it exists
    [ -d "$NAT_UI_DIR" ] && rmdir "$NAT_UI_DIR" 2>/dev/null || true
    git clone "$NAT_UI_REPO" "$NAT_UI_DIR"
fi

# ── 2. Write .env for NAT UI ─────────────────────────────────────────────────
ENV_FILE="$NAT_UI_DIR/.env"
echo "[INFO] Writing $ENV_FILE ..."

cat > "$ENV_FILE" << 'ENVEOF'
# =============================================================================
# NeMo Agent Toolkit UI - Capstone Insurance RAG Configuration
# =============================================================================

# Application Settings
NEXT_PUBLIC_NAT_WORKFLOW=Insurance RAG Q&A
NEXT_PUBLIC_NAT_GREETING_TITLE=保险智能问答系统
NEXT_PUBLIC_NAT_GREETING_SUBTITLE=我是您的专业保险顾问 AI，请问有什么可以帮助您？
NEXT_PUBLIC_NAT_INPUT_PLACEHOLDER=输入您的保险问题...
NEXT_PUBLIC_NAT_WELCOME_MESSAGE_ON=false
NEXT_PUBLIC_NAT_PROMPT_SUGGESTIONS_ON=true
NEXT_PUBLIC_NAT_WEB_SOCKET_DEFAULT_ON=false
NEXT_PUBLIC_NAT_CHAT_HISTORY_DEFAULT_ON=true
NEXT_PUBLIC_NAT_RIGHT_MENU_OPEN=false
NEXT_PUBLIC_NAT_ENABLE_INTERMEDIATE_STEPS=false
NEXT_PUBLIC_NAT_SHOW_DATA_STREAM_DEFAULT_ON=false
NEXT_PUBLIC_NAT_ADDITIONAL_VIZ_DEFAULT_ON=false

# Backend Configuration - Points to the FastAPI service
NAT_BACKEND_URL=http://api:8000

# Proxy Configuration
PORT=3001
NEXT_INTERNAL_URL=http://localhost:3099
HTTP_PUBLIC_PATH=/api
WS_PUBLIC_PATH=/ws

# Other
NODE_ENV=development
NAT_DEFAULT_MODEL=minimaxai/minimax-m2.1
NAT_MAX_FILE_SIZE_STRING=10mb
NEXT_TELEMETRY_DISABLED=1
ENVEOF

# ── 3. Install dependencies ──────────────────────────────────────────────────
echo "[INFO] Installing NAT UI dependencies..."
cd "$NAT_UI_DIR"
npm ci || npm install
cd ..

echo ""
echo "============================================="
echo " Setup Complete!"
echo "============================================="
echo ""
echo " To start NAT UI standalone:"
echo "   cd $NAT_UI_DIR && npm run dev"
echo ""
echo " To start with Docker Compose:"
echo "   docker-compose up -d nat-ui-toolkit"
echo ""
echo " NAT UI will be available at: http://localhost:3001"
echo " Backend API at: http://localhost:8000"
echo "============================================="

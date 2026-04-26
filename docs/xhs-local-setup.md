# 小红书爬取组件 - 本地运行指南

本文档说明如何在本地 Windows 环境运行小红书爬取链路，无需完整 Docker 编排。

---

## 架构概览

本地模式下，采集链路由以下组件构成：

- **workflow_scraper.yaml**：NAT 工作流配置
- **agent_browser_mcp.py**：浏览器自动化 MCP（封装 agent-browser）
- **xhs_db_mcp.py**：PostgreSQL 数据存储 MCP
- **PostgreSQL**：存储爬取数据
- **agent-browser + Chromium**：浏览器自动化
- **NVIDIA API**：LLM（minimax-m2.1）调用

---

## 1. 环境准备

### 1.1 Node.js 20

安装 [Node.js 20 LTS](https://nodejs.org/)，并在项目内本地安装 agent-browser（无需 -g，避免 EPERM）：

```powershell
cd 项目根目录
npm install
npx agent-browser install
```

验证：`npx agent-browser --version`

### 1.2 Python 3.11+

确认已安装 Python 3.11 或更高版本：

```powershell
python --version
```

### 1.3 PostgreSQL

**方案 A：本地安装**

安装 [PostgreSQL 16](https://www.postgresql.org/download/windows/)，创建数据库并执行初始化：

```powershell
psql -U postgres -c "CREATE DATABASE xhs_data;"
psql -U postgres -d xhs_data -f xhs_db_init.sql
```

需创建用户 `xhs_user`，或修改 `xhs_db_mcp.py` 使用的连接参数。

**方案 B：仅运行 Postgres 容器（推荐）**

Windows 上端口 5358-5557 常被系统保留，5432 无法绑定。使用项目提供的脚本（映射到 15432）：

```powershell
.\scripts\start-xhs-postgres.ps1
```

或手动：

```powershell
docker-compose -f docker-compose.xhs-local.yml up -d
```

初始化 SQL 会自动执行。确保 `.env` 中有 `POSTGRES_PORT=15432`。

### 1.4 一键配置脚本（推荐）

在项目根目录执行：

```powershell
.\scripts\setup-xhs-local.ps1
```

该脚本会：

- 检查 Node.js、Python
- 安装 agent-browser 和 Playwright Chromium
- 创建虚拟环境 `.venv-xhs`
- 安装 Python 依赖及 NAT 包
- 创建 `data/` 目录

---

## 2. 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `NVIDIA_API_KEY` | 是 | - | NVIDIA API 密钥 |
| `XHS_STATE_PATH` | 否 | `./data/xhs_state.json` | 会话文件路径 |
| `POSTGRES_HOST` | 否 | `localhost` | PostgreSQL 主机 |
| `POSTGRES_PORT` | 否 | 本地用 `15432`（`start-xhs-postgres.ps1`） | PostgreSQL 端口 |
| `POSTGRES_DB` | 否 | `xhs_data` | 数据库名 |
| `POSTGRES_USER` | 否 | `xhs_user` | 用户名 |
| `POSTGRES_PASSWORD` | 否 | `xhs_secure_pass` | 密码 |

示例：

```powershell
$env:NVIDIA_API_KEY = "你的API密钥"
```

---

## 3. 登录小红书

本地模式使用 Chromium 直接显示窗口，无需 noVNC。

```powershell
# 使用项目封装脚本，沿用当前 Anaconda / Shell 环境
.\scripts\xhs_login_local.ps1
```

**操作流程：**

1. Chromium 窗口会自动打开并访问小红书
2. 在窗口中完成登录（扫码或账号密码）
3. 登录成功后，在**另一个终端**执行以下命令触发保存：

   ```powershell
   New-Item -Path ".\data\xhs_login_trigger" -ItemType File -Force
   ```

4. 返回登录助手终端，确认出现「会话已保存」

---

## 4. 运行采集

确保在**项目根目录**执行（MCP 脚本通过相对路径查找）：

```powershell
# 使用项目封装脚本，沿用当前 Anaconda / Shell 环境中的 NAT
.\scripts\run-xhs-scraper.ps1
```

---

## 5. 常见问题

### agent-browser 未找到 / npm -g EPERM

使用项目本地安装（无需 `-g`）：在项目根目录执行 `npm install`，agent-browser 会安装到 `node_modules/`。

### PostgreSQL 连接失败

- 确认 PostgreSQL 已启动
- 检查 `POSTGRES_HOST`、`POSTGRES_PORT` 等环境变量
- 使用 `psql` 测试连接
- **端口 5432 被占用或无权绑定**：Windows 常保留 5358-5557，使用 `scripts\start-xhs-postgres.ps1`（端口 15432），`.env` 中设置 `POSTGRES_PORT=15432`

### 会话文件不存在

说明尚未完成登录。请先运行 `xhs_login_helper.py` 或 `scripts\xhs_login_local.ps1` 完成登录并保存会话。

### MCP 脚本找不到

必须从项目根目录执行采集命令，否则 `agent_browser_mcp.py` 和 `xhs_db_mcp.py` 无法被正确加载。本地模式不再安装 `packages/` 下的 editable NAT 包，NAT 由当前 Anaconda 环境提供，避免双版本互相干扰。

---

## 6. 与 Docker 模式对比

| 项目 | Docker 模式 | 本地模式 |
|------|-------------|----------|
| 登录 | noVNC (http://localhost:6080) | Chromium 直接窗口 |
| 会话路径 | `/app/data/xhs_state.json` | `./data/xhs_state.json` |
| 触发保存 | `docker exec xhs-login touch ...` | `New-Item -Path ... -ItemType File` |
| 采集命令 | `docker exec -it nat-app bash -c "nat run ..."` | `.\scripts\run-xhs-scraper.ps1` |

本地模式与 Docker 模式共用同一套 `agent_browser_mcp.py`、`xhs_db_mcp.py`、`workflow_scraper.yaml`，通过环境变量 `XHS_STATE_PATH` 和 `POSTGRES_HOST` 等区分运行环境。

# 小红书爬取 - 本地启动清单（逐步引导）

按顺序完成以下步骤即可在本地启动小红书爬取功能。

---

## 零、环境问题说明（可跳过，遇问题时回看）

### 1. Windows 端口 5432 无法绑定

**现象**：`bind: An attempt was made to access a socket in a way forbidden by its access permissions`

**原因**：Windows Hyper-V / Docker 会预留 5358–5557 等端口段，5432 在其中。

**本方案**：已改用端口 **15432**，避开预留段。使用 `scripts\start-xhs-postgres.ps1` 即可。

**可选：让 5432 可用**（需管理员权限）：
```powershell
# 以管理员身份运行 PowerShell，预留 5432 给本机使用
netsh int ipv4 add excludedportrange protocol=tcp startport=5432 numberofports=1 store=persistent
```
执行后**重启电脑**，再改为使用 5432。

### 2. NAT 依赖缺失（aiorwlock）

**现象**：`ModuleNotFoundError: No module named 'aiorwlock'`

**处理**：
```powershell
.\.venv-xhs\Scripts\pip.exe install aiorwlock~=1.5
```

`requirements-xhs-local.txt` 已包含此依赖，新执行 `setup-xhs-local.ps1` 时会自动安装。

### 3. pip 缓存权限错误

**现象**：`Permission denied` 在 pip 安装时出现

**处理**：使用 `--no-cache-dir` 安装，或清理缓存：
```powershell
pip cache purge
```

---

## 一、前置条件检查

在 PowerShell 中执行：

```powershell
# 1. 进入项目根目录
cd c:\Dev\capstoneProject

# 2. 检查 Node.js（需 v18+）
node --version

# 3. 检查 Python（需 3.11+）
python --version

# 4. 检查 Docker（用于运行 Postgres）
docker --version
```

如缺少任一工具，请先安装：  
- Node.js：https://nodejs.org/  
- Python：https://www.python.org/downloads/  
- Docker Desktop：https://www.docker.com/products/docker-desktop/

---

## 二、步骤 1：安装 agent-browser（项目本地，无需管理员）

```powershell
cd c:\Dev\capstoneProject
npm install
npx agent-browser install
```

验证：`npx agent-browser --version` 应能正常运行。

---

## 三、步骤 2：配置 Python 环境

```powershell
cd c:\Dev\capstoneProject
.\scripts\setup-xhs-local.ps1
```

若失败，可逐项手动执行：

```powershell
# 创建虚拟环境
python -m venv .venv-xhs
.\.venv-xhs\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements-xhs-local.txt

# 安装 aiorwlock（若仍报错）
pip install aiorwlock~=1.5
```

本地模式不再安装 `packages/` 下的 editable NAT 包。NAT 由当前 Anaconda 环境提供，避免本地包与 Anaconda 依赖互相干扰。

---

## 四、步骤 3：启动 PostgreSQL

```powershell
cd c:\Dev\capstoneProject
.\scripts\start-xhs-postgres.ps1
```

确认容器运行：`docker ps` 中能看到 `xhs-postgres-local` 且状态为 healthy。

---

## 五、步骤 4：配置 .env

确认 `.env` 中包含：

```
NVIDIA_API_KEY=你的API密钥
POSTGRES_PORT=15432
POSTGRES_PASSWORD=xhs_secure_pass
```

`run-xhs-scraper.ps1` 会从 `.env` 读取这些变量。

---

## 六、步骤 5：登录小红书

```powershell
cd c:\Dev\capstoneProject
.\scripts\xhs_login_local.ps1
```

1. 等待 Chromium 窗口打开并进入小红书  
2. 在 Chromium 中完成登录  
3. 另开一个 PowerShell，在项目根目录执行：  
   `New-Item -Path ".\data\xhs_login_trigger" -ItemType File -Force`  
4. 回到登录脚本所在终端，确认输出 “会话已保存”

---

## 七、步骤 6：运行采集

```powershell
cd c:\Dev\capstoneProject
.\scripts\run-xhs-scraper.ps1
```

建议统一使用 `.\scripts\run-xhs-scraper.ps1`，该脚本会在项目根目录加载环境变量，并沿用当前 Anaconda / Shell 环境中的 NAT。

---

## 八、快速检查清单

| 序号 | 项目 | 命令 / 检查 |
|------|------|-------------|
| 1 | 项目根目录 | `cd c:\Dev\capstoneProject` |
| 2 | Node.js | `node --version` |
| 3 | Python 3.11+ | `python --version` |
| 4 | agent-browser | `npx agent-browser --version` |
| 5 | 虚拟环境 | `.\.venv-xhs\Scripts\Activate.ps1` |
| 6 | PostgreSQL | `docker ps` 显示 xhs-postgres-local |
| 7 | .env | 含 NVIDIA_API_KEY、POSTGRES_PORT=15432 |
| 8 | 登录态 | `Test-Path .\data\xhs_state.json` 为 True |
| 9 | 采集 | `.\scripts\run-xhs-scraper.ps1` |

---

## 九、常见错误速查

| 错误 | 处理 |
|------|------|
| `npm -g EPERM` | 改用项目本地安装：`npm install`（无 -g） |
| `bind: access forbidden` | 使用 `start-xhs-postgres.ps1`（端口 15432） |
| `No module named 'aiorwlock'` | `pip install aiorwlock~=1.5` |
| `mcp_client not found` | 确认 nvidia_nat_mcp 已安装且 aiorwlock 存在 |
| `文件不存在: xhs_state.json` | 执行步骤 5 登录并保存会话 |
| `PostgreSQL 连接失败` | 确认 Postgres 容器运行，`.env` 中 POSTGRES_PORT=15432 |

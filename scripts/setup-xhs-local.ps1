# -----------------------------------------------------------------------
# 小红书爬取组件 - 本地环境一键配置脚本
# 用法：在项目根目录执行 .\scripts\setup-xhs-local.ps1
# -----------------------------------------------------------------------

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

Write-Host "=== 小红书爬取组件 - 本地环境配置 ===" -ForegroundColor Cyan
Write-Host "项目根目录: $ProjectRoot`n" -ForegroundColor Gray

# 1. 检查 Node.js
Write-Host "[1/5] 检查 Node.js..." -ForegroundColor Yellow
$nodeVersion = $null
try {
    $nodeVersion = node --version 2>$null
} catch {}
if (-not $nodeVersion) {
    Write-Host "  Node.js 未安装。请安装 Node.js 20 LTS: https://nodejs.org/" -ForegroundColor Red
    exit 1
}
Write-Host "  已安装: $nodeVersion" -ForegroundColor Green

# 2. 安装 agent-browser（项目本地，无需 -g 避免 EPERM 权限问题）
Write-Host "`n[2/5] 安装 agent-browser（项目本地）..." -ForegroundColor Yellow
$localAb = Join-Path $ProjectRoot "node_modules\agent-browser"
if (-not (Test-Path $localAb)) {
    npm install
    npx agent-browser install
    Write-Host "  agent-browser 已安装到 node_modules" -ForegroundColor Green
} else {
    Write-Host "  agent-browser 已存在" -ForegroundColor Green
}

# 3. 检查 Python 3.11+
Write-Host "`n[3/5] 检查 Python..." -ForegroundColor Yellow
$pyVersion = python --version 2>&1
if ($pyVersion -notmatch "3\.1[1-9]|3\.[2-9]") {
    Write-Host "  需要 Python 3.11 或更高版本，当前: $pyVersion" -ForegroundColor Red
    exit 1
}
Write-Host "  已安装: $pyVersion" -ForegroundColor Green

# 4. 创建虚拟环境（可选，若不存在）
$venvPath = Join-Path $ProjectRoot ".venv-xhs"
if (-not (Test-Path $venvPath)) {
    Write-Host "`n[4/5] 创建虚拟环境 .venv-xhs..." -ForegroundColor Yellow
    python -m venv $venvPath
    Write-Host "  已创建: $venvPath" -ForegroundColor Green
} else {
    Write-Host "`n[4/5] 虚拟环境已存在: .venv-xhs" -ForegroundColor Green
}

# 激活虚拟环境并安装依赖
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    $activateScript = Join-Path $venvPath "bin/activate"
}
& $activateScript

# 5. 安装 Python 依赖
Write-Host "`n[5/5] 安装 Python 依赖..." -ForegroundColor Yellow
& "$(Join-Path $venvPath 'Scripts\python.exe')" -m pip install --upgrade pip -q 2>$null
pip install -r requirements-xhs-local.txt -q

# 安装 NAT 包（editable，需版本变量；依赖包用 --no-deps 避免从 PyPI 拉取冲突版本）
$env:SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NVIDIA_NAT_CORE = "0.0.1"
$env:SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NVIDIA_NAT_MCP = "0.0.1"
$env:SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NVIDIA_NAT_FASTMCP = "0.0.1"
$env:SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NVIDIA_NAT_LLAMA_INDEX = "0.0.1"
$env:SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NVIDIA_NAT_LANGCHAIN = "0.0.1"

$packagesDir = Join-Path $ProjectRoot "packages"
# 先安装 core（--no-cache-dir 避免 pip 缓存权限问题），再安装依赖它的包（--no-deps 使用已安装的 core）
pip install -e (Join-Path $packagesDir "nvidia_nat_core") --no-cache-dir -q
pip install --no-deps -e (Join-Path $packagesDir "nvidia_nat_mcp") -q
pip install --no-deps -e (Join-Path $packagesDir "nvidia_nat_fastmcp") -q
pip install --no-deps -e (Join-Path $packagesDir "nvidia_nat_llama_index") -q
pip install --no-deps -e (Join-Path $packagesDir "nvidia_nat_langchain") -q

Write-Host "  Python 依赖已安装" -ForegroundColor Green

# 创建数据目录
$dataDir = Join-Path $ProjectRoot "data"
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
    Write-Host "`n  已创建数据目录: data\" -ForegroundColor Green
}

Write-Host "`n=== 配置完成 ===" -ForegroundColor Cyan
Write-Host @"

后续步骤：
1. 确保 PostgreSQL 已运行（端口 5432），并执行 xhs_db_init.sql 初始化数据库
2. 设置环境变量: `$env:NVIDIA_API_KEY = "你的API密钥"
3. 登录小红书: .\scripts\xhs_login_local.ps1
4. 运行采集: nat run --config_file workflow_scraper.yaml --input "请现在开始执行采集任务。"

详见 docs\xhs-local-setup.md
"@ -ForegroundColor Gray

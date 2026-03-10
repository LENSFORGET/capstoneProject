# -----------------------------------------------------------------------
# 小红书采集 - 本地运行封装
# 用法：在项目根目录执行 .\scripts\run-xhs-scraper.ps1
# 前置：已执行 setup-xhs-local.ps1，已登录（xhs_login_local.ps1），PostgreSQL 运行中
#       使用 scripts\start-xhs-postgres.ps1 时 .env 中 POSTGRES_PORT=15432
# -----------------------------------------------------------------------

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

# 加载 .env（NVIDIA_API_KEY、POSTGRES_PORT 等）
$envFile = Join-Path $ProjectRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $val = $matches[2].Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

$venvActivate = Join-Path $ProjectRoot ".venv-xhs\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    Write-Host "请先运行 .\scripts\setup-xhs-local.ps1 完成环境配置" -ForegroundColor Red
    exit 1
}
& $venvActivate

if (-not $env:NVIDIA_API_KEY) {
    Write-Host "请设置 NVIDIA_API_KEY 或在 .env 中配置" -ForegroundColor Yellow
    exit 1
}

# 本地 Postgres 端口：确保 MCP 子进程能拿到正确端口（NAT 可能未继承 .env）
if (-not $env:POSTGRES_PORT) { $env:POSTGRES_PORT = "15432" }
$env:POSTGRES_HOST = "localhost"
Write-Host "Postgres: $env:POSTGRES_HOST`:$env:POSTGRES_PORT" -ForegroundColor Gray

Write-Host "启动小红书采集（项目根: $ProjectRoot）..." -ForegroundColor Cyan
nat run --config_file workflow_scraper.yaml --input "请现在开始执行采集任务。"

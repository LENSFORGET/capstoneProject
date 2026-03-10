# -----------------------------------------------------------------------
# 启动仅供本地 XHS 爬取使用的 PostgreSQL 容器（端口 15432）
# 用法：.\scripts\start-xhs-postgres.ps1
# -----------------------------------------------------------------------

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

Write-Host "启动 XHS PostgreSQL（端口 15432）..." -ForegroundColor Cyan
docker-compose -f docker-compose.xhs-local.yml up -d

if ($LASTEXITCODE -eq 0) {
    Write-Host "PostgreSQL 已启动。.env 中已配置 POSTGRES_PORT=15432" -ForegroundColor Green
} else {
    Write-Host "启动失败，请检查 Docker 是否运行" -ForegroundColor Red
    exit 1
}

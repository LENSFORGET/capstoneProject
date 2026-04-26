# -----------------------------------------------------------------------
# 小红书登录助手 - 本地运行封装脚本
# 用法：在项目根目录执行 .\scripts\xhs_login_local.ps1
# -----------------------------------------------------------------------

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

# 设置本地会话文件路径
$dataDir = Join-Path $ProjectRoot "data"
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
}
$statePath = Join-Path $dataDir "xhs_state.json"
$env:XHS_STATE_PATH = $statePath

Write-Host "=== 小红书登录助手（本地模式） ===" -ForegroundColor Cyan
Write-Host "会话将保存至: $statePath`n" -ForegroundColor Gray

# 运行登录助手（使用当前环境 Python，避免本地 NAT editable 包干扰 Anaconda）
python xhs_login_helper.py
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host "`n登录完成。运行采集命令：" -ForegroundColor Green
    Write-Host '  .\scripts\run-xhs-scraper.ps1' -ForegroundColor Gray
}

exit $exitCode

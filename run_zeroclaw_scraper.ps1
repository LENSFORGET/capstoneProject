Write-Host "======================================================="
Write-Host "Starting ZeroClaw XHS Scraper Agent..."
Write-Host "Using native ZeroClaw agent runtime with headful browser"
Write-Host "======================================================="

$env:CHCP = 65001
$env:OPENROUTER_API_KEY="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"

.\zeroclaw.exe agent -m "请严格按照 IDENTITY.md 中要求的四个步骤，开始执行小红书保险相关内容的采集任务。你还没有抓取任何数据，请不要直接返回成功。"

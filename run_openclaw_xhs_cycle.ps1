$ErrorActionPreference = "Stop"

$lockPath = "C:\tmp\openclaw\xhs-cycle.lock"
$logDir = "C:\tmp\openclaw"
$logPath = Join-Path $logDir "xhs-cycle.log"

if (!(Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# Prevent overlapping runs when one cycle takes too long.
if (Test-Path $lockPath) {
    Add-Content -Path $logPath -Value "$(Get-Date -Format s) [WARN] Previous cycle still running, skip this round."
    exit 0
}

New-Item -ItemType File -Path $lockPath -Force | Out-Null

try {
    Add-Content -Path $logPath -Value "$(Get-Date -Format s) [INFO] Cycle start."

    $message = "只在小红书执行一轮采集：读取 IDENTITY.md 与 MEMORY.md；使用已登录浏览器会话执行关键词搜索；每帖必须先进入评论区并扫描至少10条评论，再识别活跃评论用户潜客；严禁把发帖作者当潜客。进入帖子/评论区必须走增强回退链路：1) snapshot -i 点击ref；2) 失败则 screenshot --annotate 后重试；3) 仍失败则随机滚动 600-1200px 后重抓 snapshot 再试；4) 再失败则尝试从卡片链接提取 post_id 并 open explore 直达详情页；5) 详情页内评论区也按同链路执行。反爬稳态：每步随机等待 1.2-3.8 秒，点击顺序避免固定，连续2帖 COMMENT_BLOCKED 时强制退避 45-90 秒并切换下一候选帖。硬规则：如果无法进入评论区或无法读取评论（COMMENT_BLOCKED），本帖 users_found=0，禁止保存任何用户和lead，只允许保存帖子摘要与阻塞原因。最多点赞3条且先检查是否已点赞；保存帖子/评论/潜客到数据库；禁止关注评论。每帖必须输出结构化结果（post_id, entry_method, retry_count, comment_access, block_reason, users_found, leads_saved）；本轮结束必须输出结构化汇总（posts_total, comment_success_rate, comment_blocked_rate, lead_from_comments_count, login_required_count）。若遇到登录弹窗或未登录状态，直接记录 LOGIN_REQUIRED 并结束本轮，不要等待人工回复。"

    $stdoutPath = Join-Path $logDir "xhs-cycle.stdout.log"
    $stderrPath = Join-Path $logDir "xhs-cycle.stderr.log"
    $nodeExe = "C:\nvm4w\nodejs\node.exe"
    $openclawMjs = "C:\nvm4w\nodejs\node_modules\openclaw\openclaw.mjs"
    $escapedMessage = $message.Replace('"', '\"')
    $argLine = "`"$openclawMjs`" agent --agent main --message `"$escapedMessage`""

    $proc = Start-Process -FilePath $nodeExe -ArgumentList $argLine -NoNewWindow -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    $finished = $proc.WaitForExit(600000) # 10 minutes hard timeout

    if (-not $finished) {
        Stop-Process -Id $proc.Id -Force
        Add-Content -Path $logPath -Value "$(Get-Date -Format s) [WARN] Agent timeout(10m), process killed."
    } else {
        Add-Content -Path $logPath -Value "$(Get-Date -Format s) [INFO] ExitCode=$($proc.ExitCode)"
    }

    if (Test-Path $stdoutPath) {
        $stdout = (Get-Content $stdoutPath -Raw)
        if ($stdout) {
            $snippet = $stdout.Substring(0, [Math]::Min(8000, $stdout.Length)).Replace("`r"," ").Replace("`n"," ")
            Add-Content -Path $logPath -Value "$(Get-Date -Format s) [INFO] STDOUT=$snippet"
        }
    }
    if (Test-Path $stderrPath) {
        $stderr = (Get-Content $stderrPath -Raw)
        if ($stderr) {
            $snippet = $stderr.Substring(0, [Math]::Min(8000, $stderr.Length)).Replace("`r"," ").Replace("`n"," ")
            Add-Content -Path $logPath -Value "$(Get-Date -Format s) [WARN] STDERR=$snippet"
        }
    }
}
catch {
    Add-Content -Path $logPath -Value "$(Get-Date -Format s) [ERROR] $($_.Exception.Message)"
}
finally {
    if (Test-Path $lockPath) {
        Remove-Item $lockPath -Force
    }
    Add-Content -Path $logPath -Value "$(Get-Date -Format s) [INFO] Cycle end."
}

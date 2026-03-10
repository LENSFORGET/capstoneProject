$ErrorActionPreference = "Stop"

$lockPath = "C:\tmp\openclaw\social-cycle.lock"
$logDir = "C:\tmp\openclaw"
$logPath = Join-Path $logDir "social-cycle.log"
$scriptPath = "C:\Dev\capstoneProject\multi_platform_scheduler.py"

if (!(Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

if (Test-Path $lockPath) {
    Add-Content -Path $logPath -Value "$(Get-Date -Format s) [WARN] Previous social cycle still running, skip this round."
    exit 0
}

New-Item -ItemType File -Path $lockPath -Force | Out-Null

try {
    Add-Content -Path $logPath -Value "$(Get-Date -Format s) [INFO] Social cycle start."

    $stdoutPath = Join-Path $logDir "social-cycle.stdout.log"
    $stderrPath = Join-Path $logDir "social-cycle.stderr.log"

    $py = "python"
    $argLine = "`"$scriptPath`" --wave all --max-platforms 2 --max-posts 4"
    $proc = Start-Process -FilePath $py -ArgumentList $argLine -NoNewWindow -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    $finished = $proc.WaitForExit(900000) # 15 minutes

    if (-not $finished) {
        Stop-Process -Id $proc.Id -Force
        Add-Content -Path $logPath -Value "$(Get-Date -Format s) [WARN] Scheduler timeout(15m), process killed."
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
    Add-Content -Path $logPath -Value "$(Get-Date -Format s) [INFO] Social cycle end."
}

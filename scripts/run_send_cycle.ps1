# corp-mail-outreach-v2 발송 사이클을 1회 실행하는 래퍼 스크립트 (작업 스케줄러가 호출).
# Claude 호출 없이 send_cycle.py가 대상선정~SMTP발송~로그기록을 모두 처리한다.
# 실행 결과는 logs/send_cycle.log에 한 줄씩 남기고, 오류면 exit 1로 스케줄러에도 실패를 알린다.
Set-Location -Path $PSScriptRoot\..

$logDir = Join-Path (Get-Location) "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "send_cycle.log"

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"
$output = (& python scripts/send_cycle.py 2>&1 | Out-String).Trim()
$exitCode = $LASTEXITCODE

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$status = if ($exitCode -ne 0) { "ERROR" } elseif ($output -match "^발송 성공") { "SENT" } else { "SKIP" }

$summary = $output
if ($summary.Length -gt 500) { $summary = $summary.Substring(0, 500) + "..." }
Add-Content -Path $logFile -Encoding UTF8 -Value "[$stamp] status=$status exit=$exitCode :: $($summary -replace '\s+', ' ')"

Write-Output $output
if ($status -eq "ERROR") { exit 1 }

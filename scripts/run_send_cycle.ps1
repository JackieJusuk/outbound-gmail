# corp-mail-outreach-v2 발송 사이클을 1회 실행하는 래퍼 스크립트.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot\..

$prompt = @"
requirements.md를 참조해서 발송 사이클을 1회 수행해줘.
1. scripts/pick_next_target.py 를 실행해서 발송 가능 여부와 대상을 확인해.
2. eligible이 false면 이유만 확인하고 아무 것도 하지 말고 종료해.
3. eligible이 true면, 대상 회사의 company_name을 {{company_name}} 자리에 채워
   메일 제목/본문을 구성하고, Gmail MCP의 send_message로 그 회사의 이메일 주소로
   1건만 발송해. 이때 반드시 bcc에 ljusibm@gmail.com을 포함해.
4. 발송 성공/실패에 따라 scripts/log_send.py 로 로그를 기록해
   (--status success 또는 failed, --template 사용한 템플릿 파일명).
5. 그 외의 파일 삭제, 다른 스크립트 실행, 코드 수정 등은 절대 하지 마.
"@

# claude 출력/종료 코드를 logs/send_cycle.log에 남기고, 사용량 한도 초과는 실패(exit 1)로 알린다.
# (이전에는 claude가 한도 메시지만 출력해도 스케줄러에는 성공(0)으로 기록되어 장애가 드러나지 않았음)
$logDir = Join-Path (Get-Location) "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "send_cycle.log"

$ErrorActionPreference = "Continue"
$output = (& claude -p $prompt --permission-mode auto 2>&1 | Out-String).Trim()
$exitCode = $LASTEXITCODE

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$limitHit = $output -match "(?i)(weekly|usage|rate)\s+limit|hit your .*limit"
$status = if ($limitHit) { "LIMIT_HIT" } elseif ($exitCode -ne 0) { "ERROR" } else { "OK" }

$summary = $output
if ($summary.Length -gt 500) { $summary = $summary.Substring(0, 500) + "..." }
Add-Content -Path $logFile -Encoding UTF8 -Value "[$stamp] status=$status exit=$exitCode :: $($summary -replace '\s+', ' ')"

Write-Output $output
if ($status -ne "OK") { exit 1 }
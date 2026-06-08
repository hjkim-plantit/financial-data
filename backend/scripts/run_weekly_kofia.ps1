# 매주 일요일 07:00 KST 실행 — KOFIA 한글명 업데이트
$BACKEND = Split-Path -Parent $PSScriptRoot
$ROOT    = Split-Path -Parent $BACKEND
$LOG_DIR = Join-Path $ROOT "logs"
$LOG_FILE = Join-Path $LOG_DIR ("weekly_kofia_" + (Get-Date -Format "yyyyMMdd") + ".log")

if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR | Out-Null }

function Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $LOG_FILE -Value $line -Encoding UTF8
}

Log "=== KOFIA 한글명 업데이트 시작 ==="

$ENV_FILE = Join-Path $BACKEND ".env"
foreach ($line in Get-Content $ENV_FILE -Encoding UTF8) {
    $line = $line.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line -match "^([^=]+)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), "Process")
    }
}

Set-Location $BACKEND

$out = python scripts/update_fund_names_kr.py 2>&1
$out | ForEach-Object { Log "  $_" }

if ($LASTEXITCODE -ne 0) {
    Log "ERROR: KOFIA 업데이트 실패 (exit $LASTEXITCODE)"
} else {
    Log "=== KOFIA 한글명 업데이트 완료 ==="
}

# 매일 06:00 KST 실행 — Morningstar 펀드 + ETF 동기화
$BACKEND = Split-Path -Parent $PSScriptRoot
$ROOT    = Split-Path -Parent $BACKEND
$LOG_DIR = Join-Path $ROOT "logs"
$LOG_FILE = Join-Path $LOG_DIR ("daily_sync_" + (Get-Date -Format "yyyyMMdd") + ".log")

if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR | Out-Null }

function Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $LOG_FILE -Value $line -Encoding UTF8
}

Log "=== Daily Sync 시작 ==="

# .env 로드
$ENV_FILE = Join-Path $BACKEND ".env"
foreach ($line in Get-Content $ENV_FILE -Encoding UTF8) {
    $line = $line.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line -match "^([^=]+)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), "Process")
    }
}

Set-Location $BACKEND

# Step 1: Morningstar 펀드 동기화
Log "Step 1: Morningstar 펀드 동기화 시작"
$out = python scripts/fetch_morningstar_funds.py 2>&1
$out | ForEach-Object { Log "  $_" }
if ($LASTEXITCODE -ne 0) {
    Log "ERROR: Step 1 실패 (exit $LASTEXITCODE)"
} else {
    Log "Step 1 완료"
}

# Step 2: ETF 동기화
Log "Step 2: ETF 동기화 시작"
$out = python scripts/sync_etf.py 2>&1
$out | ForEach-Object { Log "  $_" }
if ($LASTEXITCODE -ne 0) {
    Log "ERROR: Step 2 실패 (exit $LASTEXITCODE)"
} else {
    Log "Step 2 완료"
}

Log "=== Daily Sync 완료 ==="

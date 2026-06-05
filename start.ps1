# 국내공모펀드 플랫폼 시작 스크립트
# 실행: 우클릭 -> PowerShell로 실행

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# .env 로드
Get-Content "$root\backend\.env" | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
    }
}

$domain = [System.Environment]::GetEnvironmentVariable("NGROK_DOMAIN")

Write-Host ""
Write-Host "=== 국내공모펀드 플랫폼 시작 ===" -ForegroundColor Cyan
Write-Host ""

# 1. 백엔드 서버
Write-Host "[1/2] 백엔드 시작..." -ForegroundColor Yellow
$backend = Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000" `
    -PassThru
Start-Sleep -Seconds 3

# 2. ngrok 터널
Write-Host "[2/2] ngrok 터널 시작..." -ForegroundColor Yellow
$ngrok = Start-Process -FilePath "ngrok" `
    -ArgumentList "http", "--domain=$domain", "8000" `
    -PassThru
Start-Sleep -Seconds 2

Write-Host ""
Write-Host "===================================" -ForegroundColor Green
Write-Host " 백엔드 URL: https://$domain" -ForegroundColor Green
Write-Host " Swagger:    https://$domain/docs" -ForegroundColor Green
Write-Host "===================================" -ForegroundColor Green
Write-Host ""
Write-Host "종료하려면 이 창을 닫으세요." -ForegroundColor Gray

Wait-Process -Id $backend.Id

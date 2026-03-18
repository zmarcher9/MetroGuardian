param(
  [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"

$streamUrl = "$BaseUrl/api/v1/alerts/stream"
$outFile = Join-Path (Get-Location) "sse_out.txt"
if (Test-Path $outFile) { Remove-Item $outFile -Force }

Write-Host "Starting SSE stream..." -ForegroundColor Cyan
$p = Start-Process -FilePath "curl.exe" -ArgumentList @(
  "-N",
  "-H", "Accept:text/event-stream",
  $streamUrl
) -NoNewWindow -PassThru -RedirectStandardOutput $outFile

Start-Sleep -Seconds 2

Write-Host "Triggering ingestion..." -ForegroundColor Cyan
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/ingest/traffic" | Out-Null

Start-Sleep -Seconds 2

Write-Host "Stopping SSE stream..." -ForegroundColor Cyan
if (-not $p.HasExited) {
  Stop-Process -Id $p.Id -Force
}

Write-Host "SSE output (first 80 lines):" -ForegroundColor Cyan
Get-Content -Path $outFile -TotalCount 80


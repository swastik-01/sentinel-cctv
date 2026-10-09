# Restart the Sentinel API on Windows: wait for Postgres, stop whatever listens on the port, start uvicorn
# detached, wait until /healthz answers. Usage: powershell -File scripts/api.ps1 [-Port 8000]
# uvicorn runs as `python -m uvicorn`: the interpreter the firewall rule already names, and no .exe launcher
# for the antivirus to hold (it held sentinel-counts.exe on 7 Oct). The access log is off: it wrote every
# plate searched and every token-in-URL to %TEMP% (docs/privacy-dpdp.md).
param([int]$Port = 8000, [string]$Log = "$env:TEMP\sentinel-api.log")

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# After a reboot the database is the last thing up (Docker Desktop, the container, recovery), and the API's
# pool does not retry: wait here instead of starting it into a connection error.
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    cmd /c "docker compose exec -T postgres pg_isready -U sentinel >nul 2>&1"
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    if ($i -eq 0) { "waiting for postgres (if it is not running: docker compose up -d postgres valkey mediamtx)" }
    Start-Sleep -Seconds 2
}
if (-not $ready) { "postgres is not ready after 120 s; not starting the API"; exit 1 }

Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
for ($i = 0; $i -lt 20 -and (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue); $i++) {
    Start-Sleep -Milliseconds 250
}

$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "sentinel_api.main:app", "--host", "0.0.0.0", `
    "--port", "$Port", "--no-access-log" `
    -RedirectStandardOutput $Log -RedirectStandardError "$Log.err" -WindowStyle Hidden

# curl.exe (shipped with Windows), not Invoke-WebRequest: on this laptop PowerShell's own web client fails against
# localhost for the whole minute (proxy and IE-engine settings) while the API is in fact up.
for ($i = 0; $i -lt 60; $i++) {
    $body = & curl.exe -s -m 2 "http://localhost:$Port/healthz" 2>$null
    if ($LASTEXITCODE -eq 0 -and $body -match '"ok"\s*:\s*true') {
        $r = $body | ConvertFrom-Json
        "API up on :$Port (cameras: $($r.fleet.cameras)) - logs: $Log.err"
        exit 0
    }
    Start-Sleep -Milliseconds 500
}
"API did not come up; last log lines:"
Get-Content "$Log.err" -Tail 15
exit 1

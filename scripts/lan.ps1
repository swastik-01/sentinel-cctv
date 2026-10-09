# Laptop A on the finale LAN: find A's address, tell the relay (WebRTC) and the API (CORS) about it, restart
# both, and print what laptop B must use. Run from the repo root once the cable is in:
#   powershell -File scripts/lan.ps1                  (picks the wired adapter, else the first LAN address)
#   powershell -File scripts/lan.ps1 -Ip 10.20.30.5   (when more than one adapter is up)
# Without this, a browser on B waits 15 s per tile and falls back to HLS (the relay advertises only container
# addresses), and B's control room cannot sign in to A's API (its origin is not allowed).
param([string]$Ip = "")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not $Ip) {
    $cands = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and
                       $_.InterfaceAlias -notlike "vEthernet*" -and $_.InterfaceAlias -notlike "*WSL*" -and
                       $_.InterfaceAlias -notlike "*Loopback*" } |
        Sort-Object InterfaceMetric
    $wired = $cands | Where-Object { $_.InterfaceAlias -like "Ethernet*" } | Select-Object -First 1
    if ($wired) { $Ip = $wired.IPAddress }
    elseif ($cands) { $Ip = ($cands | Select-Object -First 1).IPAddress; "no wired adapter: using $($cands[0].InterfaceAlias)" }
    else { throw "no LAN address found" }
}
"laptop A is $Ip"

# .env: replace or append the two lines. Written without a byte-order mark, or the first key is corrupted.
$path = ".env"
$lines = @()
if (Test-Path $path) { $lines = [System.IO.File]::ReadAllLines($path) }
$set = @{
    "WEBRTC_HOST"       = "127.0.0.1,$Ip"
    "CORS_ORIGIN_REGEX" = 'http://(10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|localhost|127\.0\.0\.1):5173'
}
foreach ($k in $set.Keys) {
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^#?\s*$k=") { $lines[$i] = "$k=$($set[$k])"; $found = $true }
    }
    if (-not $found) { $lines += "$k=$($set[$k])" }
}
[System.IO.File]::WriteAllLines((Resolve-Path $path), $lines, (New-Object System.Text.UTF8Encoding $false))
"wrote WEBRTC_HOST and CORS_ORIGIN_REGEX to .env"

"recreating the relay with the new address (its streams reconnect within seconds)"
docker compose up -d mediamtx | Out-Null
powershell -File scripts/api.ps1
""
"on laptop B (.env.b.example):"
"  API_URL=http://${Ip}:8000"
"  RELAY_HOST=$Ip"
"  control room from B: http://${Ip}:5173   (A must run: cd web; npm run dev -- --host)"
"  check from B:  Test-NetConnection $Ip -Port 8000 ; Test-NetConnection $Ip -Port 8554"

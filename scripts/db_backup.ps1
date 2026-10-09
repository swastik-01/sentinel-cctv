# Dump the live database (pg_dump custom format) and copy the evidence crops to a backup folder, so laptop B can
# take over with scripts/db_restore.ps1. Run from the repo root on laptop A, every few minutes during the finale:
#   powershell -File scripts/db_backup.ps1 -Dest E:\sentinel-backup        (a USB stick, or a folder B can reach)
#   powershell -File scripts/db_backup.ps1 -Dest E:\sentinel-backup -Loop 600   (again every 600 s until Ctrl-C)
# The dump holds real registrations and the relay's camera credentials: keep the folder private.
param(
    [Parameter(Mandatory = $true)][string]$Dest,
    [int]$Loop = 0
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

function Backup-Once {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $dump = Join-Path $Dest "sentinel-$stamp.dump"
    $t0 = Get-Date
    # pg_dump inside the container; the file lands on the host through stdout
    cmd /c "docker compose exec -T postgres pg_dump -U sentinel -d sentinel -Fc > `"$dump`""
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $dump) -or (Get-Item $dump).Length -lt 1024) {
        throw "pg_dump failed (exit $LASTEXITCODE)"
    }
    Copy-Item $dump (Join-Path $Dest "sentinel-latest.dump") -Force
    # crops: only new and changed files; the folder names are camera codes, the file names carry plates
    robocopy "data\crops" (Join-Path $Dest "crops") /E /XO /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy of data\crops failed (exit $LASTEXITCODE)" }
    # keep the last 12 timestamped dumps
    Get-ChildItem $Dest -Filter "sentinel-2*.dump" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 12 |
        Remove-Item -Force
    $secs = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
    "{0}  dumped {1:N1} MB in {2} s -> {3}" -f (Get-Date -Format "HH:mm:ss"), ((Get-Item $dump).Length / 1MB), $secs, $dump
}

Backup-Once
while ($Loop -gt 0) {
    Start-Sleep -Seconds $Loop
    try { Backup-Once } catch { "{0}  backup failed: {1}" -f (Get-Date -Format "HH:mm:ss"), $_ }
}

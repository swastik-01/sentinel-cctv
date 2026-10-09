# Laptop B takes over from A: restore the latest dump from scripts/db_backup.ps1 into B's own Postgres, copy the
# crops back, then start the API and the control room. Run from the repo root on B, with Docker running:
#   powershell -File scripts/db_restore.ps1 -Source E:\sentinel-backup
# What happens: B's database is dropped and recreated from the dump (every table: cameras, sightings, reviews,
# users, audit); the relay rebuilds every camera's path from camera_sources within about 20 s of the API starting
# (health_monitor.py), so the cameras come back without re-onboarding. B's .env must hold A's secrets
# (JWT_SECRET, INGEST_KEY, ADMIN_PASSWORD) so the workers and the saved logins still work. Then move the HDMI
# cable, open http://localhost:5173, sign in.
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [string]$Dump = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not $Dump) { $Dump = Join-Path $Source "sentinel-latest.dump" }
if (-not (Test-Path $Dump)) { throw "no dump at $Dump" }

"starting B's database, cache and relay"
docker compose up -d postgres valkey mediamtx | Out-Null
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    cmd /c "docker compose exec -T postgres pg_isready -U sentinel >nul 2>&1"
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $ready) { throw "postgres did not become ready" }

"restoring $Dump"
docker cp $Dump sentinel-postgres-1:/tmp/restore.dump
# a clean database: the dump's own schema replaces whatever B had (the init SQL ran on its empty volume)
docker compose exec -T postgres psql -U sentinel -d postgres -c "DROP DATABASE IF EXISTS sentinel_restore;" | Out-Null
docker compose exec -T postgres psql -U sentinel -d postgres -c "CREATE DATABASE sentinel_restore OWNER sentinel;" | Out-Null
docker compose exec -T postgres pg_restore -U sentinel -d sentinel_restore --no-owner --no-privileges /tmp/restore.dump
if ($LASTEXITCODE -ne 0) { "pg_restore reported warnings (exit $LASTEXITCODE); continuing if the tables are there" }
$n = docker compose exec -T postgres psql -U sentinel -d sentinel_restore -tAc "SELECT count(*) FROM cameras"
if (-not $n -or [int]$n -lt 1) { throw "the restored database has no cameras; not switching" }
# swap: nothing may hold the live database (the API is not running yet on B)
docker compose exec -T postgres psql -U sentinel -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'sentinel';" | Out-Null
docker compose exec -T postgres psql -U sentinel -d postgres -c "DROP DATABASE IF EXISTS sentinel;" | Out-Null
docker compose exec -T postgres psql -U sentinel -d postgres -c "ALTER DATABASE sentinel_restore RENAME TO sentinel;" | Out-Null
docker compose exec -T postgres rm -f /tmp/restore.dump | Out-Null
"restored: $n cameras"

$crops = Join-Path $Source "crops"
if (Test-Path $crops) {
    New-Item -ItemType Directory -Force -Path "data\crops" | Out-Null
    robocopy $crops "data\crops" /E /XO /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    "crops copied"
}

"starting the API (it applies the schema upgrades, then the relay rebuilds every camera path)"
powershell -File scripts/api.ps1
"now: (cd web && npm run dev -- --host), open http://localhost:5173, sign in; cameras come online within ~20 s"

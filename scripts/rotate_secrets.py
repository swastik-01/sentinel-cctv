"""Replace the repo's development secrets on this machine with random ones: the API's JWT secret, the workers'
ingest key, the relay's publisher credential and the database password. The repo is readable by every other
finalist, so a laptop still on the example values can be signed into, fed fake sightings, or have a camera's picture
replaced by anyone on the same network (scripts/security_checks.py tests for this).

    uv run --no-sync python scripts/rotate_secrets.py                 # rotate what is still an example value
    uv run --no-sync python scripts/rotate_secrets.py --all           # rotate all four, whatever they are
    NEW_PASSWORD=... uv run --no-sync python scripts/rotate_secrets.py --users   # and the five seeded users

What it does: ALTER USER on the live database (so the new database password works before the API restarts),
rewrites .env in place (other lines untouched; no byte-order mark), and prints the restarts still needed. The new
values are written to .env only, never printed. Afterwards every worker and laptop B need the new INGEST_KEY, and the
simulator's publisher and the relay need recreating (docker compose up -d mediamtx feedsim-publisher).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV, EXAMPLE = ROOT / ".env", ROOT / ".env.example"
KEYS = ("JWT_SECRET", "INGEST_KEY", "MEDIAMTX_PUBLISH_PASS", "POSTGRES_PASSWORD")


def read(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def rewrite(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    seen = set()
    for i, line in enumerate(lines):
        if "=" in line and not line.lstrip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in values:
                lines[i] = f"{k}={values[k]}"
                seen.add(k)
    for k, v in values.items():
        if k not in seen:
            lines.append(f"{k}={v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def psql(sql: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "sentinel", "-d", "sentinel",
                           "-v", "ON_ERROR_STOP=1", "-tAc", sql], cwd=ROOT, capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="rotate every key, not only those still at the example value")
    ap.add_argument("--users", action="store_true", help="also set the five seeded users' password from NEW_PASSWORD")
    a = ap.parse_args()
    live, example = read(ENV), read(EXAMPLE)
    todo = [k for k in KEYS if a.all or live.get(k, example.get(k)) == example.get(k)]
    new = {k: secrets.token_urlsafe(24) for k in todo}
    if "POSTGRES_PASSWORD" in new:
        r = psql(f"ALTER USER {live.get('POSTGRES_USER', 'sentinel')} PASSWORD '{new['POSTGRES_PASSWORD']}'")
        if r.returncode != 0:
            print(f"database password not changed ({r.stderr.strip()[:120]}); nothing rewritten", file=sys.stderr)
            return 1
        url = live.get("DATABASE_URL", "")
        if url and ":" in url and "@" in url:
            head, tail = url.split("@", 1)
            new["DATABASE_URL"] = head.rsplit(":", 1)[0] + ":" + new["POSTGRES_PASSWORD"] + "@" + tail
    if a.users:
        pw = os.environ.get("NEW_PASSWORD", "")
        if len(pw) < 12:
            print("--users needs NEW_PASSWORD (12 characters or more) in the environment", file=sys.stderr)
            return 2
        sys.path.insert(0, str(ROOT / "scripts"))
        from set_passwords import SEEDED, main as set_users   # noqa: E402
        if asyncio.run(set_users(SEEDED)) != 0:
            return 1
        new["ADMIN_PASSWORD"] = pw                    # so an empty database seeds the same password
    if not new:
        print("nothing to rotate: no key is at its example value (use --all to rotate anyway)")
        return 0
    rewrite(ENV, new)
    print("rotated in .env: " + ", ".join(k for k in new if k != "DATABASE_URL"))
    print("now: docker compose up -d mediamtx feedsim-publisher   (relay and simulator take the new publisher credential)")
    print("     powershell -File scripts/api.ps1                  (API: JWT secret, ingest key, database password)")
    print("     restart every worker; put the new INGEST_KEY in laptop B's .env")
    print("     export ADMIN_PASSWORD and INGEST_KEY from .env before any script; every saved login is signed out")
    return 0


if __name__ == "__main__":
    sys.exit(main())

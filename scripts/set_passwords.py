"""Set the seeded users' passwords on the live database. ADMIN_PASSWORD in .env only seeds an empty users table,
so a password chosen after the first start must be written here. The new password is read from the environment,
never from an argument (arguments show in the process list):

    NEW_PASSWORD=... uv run --no-sync python scripts/set_passwords.py            # every seeded user
    NEW_PASSWORD=... uv run --no-sync python scripts/set_passwords.py admin auditor

Then export ADMIN_PASSWORD with the same value before any script (they read it from the environment), and tell
the team: every saved login stops working.
"""
from __future__ import annotations

import asyncio
import os
import sys

import asyncpg

from sentinel_api.auth import hash_password
from sentinel_api.config import get_settings

SEEDED = ["admin", "supervisor", "operator", "gsrtc_nodal", "auditor"]


async def main(users: list[str] | None = None) -> int:
    pw = os.environ.get("NEW_PASSWORD", "")
    if len(pw) < 12:
        print("set NEW_PASSWORD to at least 12 characters", file=sys.stderr)
        return 2
    if users is None:
        users = sys.argv[1:] or SEEDED
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        n = 0
        for u in users:
            r = await conn.execute("UPDATE users SET password_hash = $1 WHERE username = $2", hash_password(pw), u)
            n += r.endswith("1")
            print(f"  {u}: {'updated' if r.endswith('1') else 'no such user'}")
    finally:
        await conn.close()
    print(f"{n} of {len(users)} passwords set; export ADMIN_PASSWORD to match before running any script")
    return 0 if n == len(users) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

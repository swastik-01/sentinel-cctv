"""Turn analytics on (or off) for every camera whose code starts with a prefix: the finale's feeds, once onboarded,
in one go. A worker reads the camera list once at start and takes only cameras with analytics enabled, so this
runs before the workers start.

    uv run --no-sync python scripts/set_analytics.py --prefix CAM --on
    uv run --no-sync python scripts/set_analytics.py --prefix CAM --off --except CAM06,CAM07

ADMIN_PASSWORD from the environment.
"""
from __future__ import annotations

import argparse
import os
import sys

import httpx

API = os.environ.get("API", "http://localhost:8000")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True, help="camera codes starting with this (upper-cased)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--on", action="store_true")
    g.add_argument("--off", action="store_true")
    ap.add_argument("--except", dest="skip", default="", help="comma-separated codes left as they are")
    a = ap.parse_args()
    skip = {c.strip().upper() for c in a.skip.split(",") if c.strip()}
    with httpx.Client(base_url=API, timeout=30) as c:
        r = c.post("/auth/login", json={"username": "admin", "password": os.environ.get("ADMIN_PASSWORD", "admin123")})
        r.raise_for_status()
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        cams = c.get("/cameras", params={"limit": 2000}, headers=h).json()["items"]
        n = changed = 0
        for cam in cams:
            code = cam["camera_code"]
            if not code.upper().startswith(a.prefix.upper()) or code.upper() in skip:
                continue
            n += 1
            if cam.get("analytics_enabled") == a.on:
                continue
            p = c.patch(f"/cameras/{code}", json={"analytics_enabled": a.on}, headers=h)
            if p.status_code == 200:
                changed += 1
            else:
                print(f"  {code}: {p.status_code} {p.text[:120]}")
        print(f"{n} cameras match {a.prefix!r}; analytics set {'on' if a.on else 'off'} on {changed} "
              f"(the rest already were){'; skipped ' + ', '.join(sorted(skip)) if skip else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

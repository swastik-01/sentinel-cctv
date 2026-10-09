"""Onboard cameras from a CSV of stream addresses through the probe -> relay -> register path (POST /onboard/stream),
one at a time: the way the organisers' feeds go in when they arrive as a list. The address with its credentials
stays in the relay's source table; the registry and every viewer get only the relay address.

CSV columns: code,name,url,department,district,lat,lon,anpr_viable  (district, lat, lon, anpr_viable optional)

    uv run --no-sync python scripts/onboard_urls.py feeds.csv --dry-run          # prints what would be registered
    uv run --no-sync python scripts/onboard_urls.py feeds.csv --analytics        # register with analytics on

Never the bulk CSV import on the Registry page for credentialed addresses: that path stores the address as given,
where every camera reader can see it, and does not relay. ADMIN_PASSWORD from the environment.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from urllib.parse import urlsplit

import httpx

API = os.environ.get("API", "http://localhost:8000")


def masked(url: str) -> str:
    p = urlsplit(url)
    return url.replace(p.password, "***") if p.password else url


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--analytics", action="store_true", help="analytics enabled from the start")
    ap.add_argument("--always-on", action="store_true", help="keep the upstream open even when nobody watches")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    with open(a.csv, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("code") or "").strip()]
    if not rows:
        sys.exit("no rows with a code")
    with httpx.Client(base_url=API, timeout=90) as c:
        h = {}
        if not a.dry_run:
            r = c.post("/auth/login", json={"username": "admin", "password": os.environ.get("ADMIN_PASSWORD", "admin123")})
            r.raise_for_status()
            h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        ok = failed = 0
        for r in rows:
            code = r["code"].strip().upper()
            body = {"camera_code": code, "name": (r.get("name") or code).strip(),
                    "department_code": (r.get("department") or "POLICE").strip().upper(),
                    "district": (r.get("district") or "").strip() or None,
                    "lat": float(r["lat"]) if (r.get("lat") or "").strip() else None,
                    "lon": float(r["lon"]) if (r.get("lon") or "").strip() else None,
                    "source_url": r["url"].strip(), "camera_class": "fixed", "mode": "ip_rtsp",
                    "anpr_viable": (r.get("anpr_viable") or "").strip().lower() in ("1", "true", "yes", "y"),
                    "analytics_enabled": a.analytics, "on_demand": not a.always_on}
            if a.dry_run:
                print(f"  {code:14} {body['department_code']:8} {str(body['district']):12} {masked(body['source_url'])}")
                continue
            t0 = time.monotonic()
            resp = c.post("/onboard/stream", json=body, headers=h)
            if resp.status_code == 200:
                p = resp.json().get("probe", {})
                print(f"  {code:14} {resp.json().get('outcome', ''):8} {p.get('codec')} {p.get('width')}x{p.get('height')} "
                      f"probe {p.get('seconds')} s", flush=True)
                ok += 1
            else:
                print(f"  {code:14} FAILED {resp.status_code} {resp.text[:160]} ({time.monotonic() - t0:.1f} s)", flush=True)
                failed += 1
            time.sleep(1)      # one at a time: each probe opens a session on the camera's server
        if not a.dry_run:
            print(f"onboarded {ok}, failed {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

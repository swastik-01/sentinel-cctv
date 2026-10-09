"""Onboard the organisers' sandbox cameras through Sentinel's own URL onboarding (probe, relay, register).

The sandbox catalogue (https://<sandbox-grid>/cameras.json, behind the team's login) lists only an
id and a name per camera. Its integrator's guide gives the RTSP address, rtsp://<email>:<password>@
<host>:8554/stream/<id>, with the @ of the email written %40. Locations and departments are not in the
catalogue: they come from a reviewed file (data/gov-sandbox/locations.json) and are recorded in each
camera's address field as approximate, so nobody mistakes them for the organisers' data. A camera the file does not
cover (or every camera, without the file) is registered unplaced, its department and district inferred from its name by
the registry's own catalogue matching (a department name or hint, a district name in the camera's name), and the
address field says so.

Cameras are onboarded one at a time and relayed on demand: the relay pulls a camera only while someone
views it or the analytics worker reads it (the guide: "open only the cameras you are processing").

    SANDBOX_EMAIL=... SANDBOX_PASSWORD=... uv run --no-sync python scripts/onboard_sandbox.py
    ... --only cam12,cam14          # a subset
    ... --dry-run                   # print what would be registered, touch nothing

The credentials are read from the environment only; the relay keeps them server-side and the audit log
masks them.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))
from sentinel_api.catalogue import match_department, match_district  # noqa: E402
DATA = ROOT / "data" / "gov-sandbox"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=os.environ.get("API", "http://localhost:8000"))
    ap.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD", "admin123"), help="Sentinel admin password")
    ap.add_argument("--cameras", default=str(DATA / "cameras.json"), help="the organisers' catalogue, saved")
    ap.add_argument("--locations", default=str(DATA / "locations.json"))
    ap.add_argument("--host", default=os.environ.get("SANDBOX_RTSP_HOST", "<sandbox-host>:8554"),
                    help="sandbox RTSP host:port (from the guide; or SANDBOX_RTSP_HOST)")
    ap.add_argument("--only", help="comma-separated camera ids")
    ap.add_argument("--analytics", action="store_true",
                    help="register with analytics enabled, so a worker started afterwards takes the cameras at once "
                         "(the counts-only worker counts every analytics camera it is not told to leave out)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pause", type=float, default=1.0,
                    help="seconds between cameras (each probe opens a stream copy on their server)")
    a = ap.parse_args()

    email, pw = os.environ.get("SANDBOX_EMAIL"), os.environ.get("SANDBOX_PASSWORD")
    if not (email and pw) and not a.dry_run:
        sys.exit("set SANDBOX_EMAIL and SANDBOX_PASSWORD (the team's portal login)")
    cams = json.loads(Path(a.cameras).read_text(encoding="utf-8"))
    if isinstance(cams, dict):                      # {"cameras": [...]} as well as a bare list
        cams = next((v for v in cams.values() if isinstance(v, list)), [])
    loc_file = Path(a.locations)
    locs = json.loads(loc_file.read_text(encoding="utf-8"))["cameras"] if loc_file.exists() else {}
    if not locs:
        print(f"no reviewed locations ({loc_file}): every camera is registered unplaced, department and district "
              "inferred from its name")
    only = {x.strip().lower() for x in a.only.split(",")} if a.only else None

    with httpx.Client(base_url=a.api, timeout=60) as c:
        tok = c.post("/auth/login", json={"username": "admin", "password": a.password}).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        depts = {d["code"]: d.get("name") or d["code"] for d in c.get("/reports/departments", headers=h).json()}
        districts = {d["district"].lower(): d["district"] for d in c.get("/gis/districts", headers=h).json()
                     if d.get("district")}

        def inferred(name: str) -> dict:
            dept, warn = match_department(name, depts, "HOME")
            district = next((d for w in re.split(r"[^A-Za-z]+", name) if len(w) > 3
                             for d in [match_district(w, districts)] if d), None)
            return {"department": dept, "district": district, "lat": None, "lon": None,
                    "loc_basis": f"not in a reviewed file; district {'from the camera name' if district else 'unknown'}",
                    "dept_basis": "from the camera name" if not warn else "not in the name, so HOME"}
        ok = failed = 0
        for cam in cams:
            cid = cam["id"].lower()
            if only and cid not in only:
                continue
            loc = locs.get(cid) or inferred(cam.get("name") or cid)
            placed = loc["lat"] is not None
            body = {
                "camera_code": cid.upper(),
                "name": cam["name"],
                "department_code": loc["department"],
                "district": loc["district"],
                "lat": loc["lat"], "lon": loc["lon"],
                "address": (f"Sandbox camera {cid}. Location {'approximate' if placed else 'unknown'}: "
                            f"{loc['loc_basis']}. Department assumed: {loc['dept_basis']}."),
                "source_url": (f"rtsp://{quote(email or 'EMAIL', safe='')}:{quote(pw or 'PASSWORD', safe='')}"
                               f"@{a.host}/stream/{cid}"),
                "camera_class": "ptz" if cid == "cam01" else "fixed",
                "mode": "ip_rtsp",
                "anpr_viable": False,
                "analytics_enabled": a.analytics,
                "on_demand": True,
            }
            where = f"{loc['lat']},{loc['lon']}" if placed else "not placed"
            if a.dry_run:
                print(f"  {body['camera_code']:6} {loc['department']:6} {str(loc['district']):12} {where:20} {cam['name']}")
                continue
            t0 = time.monotonic()
            r = c.post("/onboard/stream", json=body, headers=h)
            if r.status_code == 200:
                p = r.json()["probe"]
                print(f"  {body['camera_code']:6} {r.json()['outcome']:8} {p.get('codec')} {p.get('width')}x{p.get('height')} "
                      f"probe {p.get('seconds')} s  {where}  {cam['name']}", flush=True)
                ok += 1
            else:
                print(f"  {body['camera_code']:6} FAILED {r.status_code} {r.text[:200]} ({time.monotonic() - t0:.1f} s)", flush=True)
                failed += 1
            time.sleep(a.pause)      # one camera at a time: each probe opens a stream copy on their server
    if not a.dry_run:
        print(f"onboarded {ok}, failed {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

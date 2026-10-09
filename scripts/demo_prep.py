"""Put the stack into a known state for a demo, rehearsal or recording.

    uv run --no-sync python scripts/demo_prep.py            # reset for the recorded demo
    uv run --no-sync python scripts/demo_prep.py --keep-data # only re-sync cameras, clear outages

Reset means: alerts and sightings cleared, every watchlist entry deactivated (so the
demo can show the VAHAN / eGujCop sync raising alerts live), demo-onboarded cameras and
their relays removed, simulator outages cleared, catalogue re-synced.
"""
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
API = os.environ.get("API", "http://localhost:8000")
CATALOGUE = os.environ.get("CATALOGUE", "http://localhost:8010")
PW = os.environ.get("ADMIN_PASSWORD", "admin123")
DEMO_PREFIXES = ("DEMO-", "SMOKE-", "GNR-MUNI-1")


def psql(sql: str) -> None:
    subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "sentinel", "-d", "sentinel",
                    "-q", "-v", "ON_ERROR_STOP=1", "-c", sql], cwd=ROOT, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-data", action="store_true")
    ap.add_argument("--keep-sightings", action="store_true",
                    help="clear alerts and deactivate the watchlist, but keep plate history (re-recording)")
    ap.add_argument("--force", action="store_true",
                    help="reset even though cameras onboarded by stream address (government feeds) have sightings")
    a = ap.parse_args()
    if not a.keep_data and not a.keep_sightings and not a.force:
        # The reset deletes every sighting, alert and crop. Run by habit during or after a government-feed run
        # (the runbook's recovery steps once pointed here), it would erase the evidence the report is made from.
        n = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "sentinel", "-d", "sentinel",
                            "-tAc", "SELECT count(*) FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id "
                                    "WHERE c.tags->>'source' = 'onboard'"],
                           cwd=ROOT, capture_output=True, text=True).stdout.strip()
        if n.isdigit() and int(n) > 0:
            raise SystemExit(f"refusing: {n} sightings on cameras onboarded by stream address would be deleted. "
                             "Use --keep-sightings, or --force if that is what you want.")
    with httpx.Client(base_url=API, timeout=60) as c:
        tok = c.post("/auth/login", json={"username": "admin", "password": PW}).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        cams = c.get("/cameras", params={"limit": 2000}, headers=h).json()["items"]
        for cam in cams:
            if cam["camera_code"].startswith(DEMO_PREFIXES):
                c.delete(f"/onboard/stream/{cam['camera_code']}", headers=h)
                c.delete(f"/cameras/{cam['camera_code']}", headers=h)
                print("removed", cam["camera_code"])
        for cam in httpx.get(f"{CATALOGUE}/cameras", timeout=10).json()["items"]:
            httpx.delete(f"{CATALOGUE}/admin/outage/{cam['code']}", timeout=10)
        print("sync:", c.post("/cameras/sync-catalogue", headers=h).json())
    if not a.keep_data:
        if a.keep_sightings:
            psql("DELETE FROM alerts; UPDATE watchlist_entries SET active = false; "
                 "DELETE FROM detection_events WHERE detail->>'model' = 'smoke';")
            print("alerts and smoke-test counts cleared; watchlist deactivated; plate and count history kept")
        else:
            psql("DELETE FROM alerts; DELETE FROM vehicle_sightings; DELETE FROM detection_events; "
                 "UPDATE watchlist_entries SET active = false; "
                 "DO $$ BEGIN IF to_regclass('sighting_quality') IS NOT NULL THEN DELETE FROM sighting_quality; END IF; END $$;")
            for d in (ROOT / "data/crops").glob("*"):
                if d.is_dir():
                    for f in d.glob("*.jpg"):
                        f.unlink()
            print("alerts, sightings and crops cleared; watchlist deactivated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

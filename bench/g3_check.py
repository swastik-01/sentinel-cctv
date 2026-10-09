"""G3 confidence marking, the live part of its T block (bench/pipeline_gates.md): against the running API, with
synthetic plates on two simulator cameras, removed again at the end.

  - a sighting stored at 0.85 is marked "check the crop"; one stored at 0.90 (a REAL column) and read back is not;
  - a watchlist alert raised on a one-character match is marked; an exact one is not;
  - `reads` and `agreement` are written;
  - the alert count for the same ingests is recorded, so a run with marking off and one with it on can be compared.

    CONFIDENCE_MARKING=... (the API's setting) uv run --no-sync python bench/g3_check.py --marking on|off

Writes data/g3/check_<on|off>.json (counts and verdicts only). ADMIN_PASSWORD and INGEST_KEY come from the
environment, as scripts/security_checks.py reads them.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
API = os.environ.get("API", "http://localhost:8000")
PW = os.environ.get("ADMIN_PASSWORD", "admin123")
CAMS = ("GNR-POL-001", "MHS-POL-001")      # simulator cameras: never a government feed
fails = 0


def check(name: str, ok: bool, info: str = "") -> bool:
    global fails
    fails += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {info}")
    return ok


def login(c: httpx.Client) -> dict:
    r = c.post(f"{API}/auth/login", json={"username": "admin", "password": PW})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def psql(sql: str) -> str:
    r = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "sentinel", "-d", "sentinel",
                        "-tAc", sql], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else f"psql failed: {r.stderr.strip()[:120]}"


def synthetic() -> str:
    return f"GJ98{random.choice('CDEFHKMNPR')}{random.choice('CDEFHKMNPR')}{random.randint(1000, 9999)}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--marking", choices=["on", "off"], required=True, help="the API's CONFIDENCE_MARKING setting")
    a = ap.parse_args()
    on = a.marking == "on"
    c = httpx.Client(timeout=20)
    ha = login(c)
    ik = {"X-Ingest-Key": os.environ.get("INGEST_KEY", "dev_ingest_key_replace_me")}
    watched, low, high = synthetic(), synthetic(), synthetic()
    one_off = watched[:-1] + str((int(watched[-1]) + 1) % 10)
    plates = [watched, low, high, one_off]
    w = c.post(f"{API}/watchlist", headers=ha, json={"kind": "stolen_vehicle", "plate": watched, "severity": "high",
                                                     "source": "g3_check", "reason": "G3 gate check"}).json()
    now = datetime.now(timezone.utc)
    out: dict = {"marking": a.marking, "at": now.isoformat(timespec="seconds")}

    def sight(p, cam, conf, reads, agreement, secs_ago):
        return {"camera_code": cam, "event_ts": (now - timedelta(seconds=secs_ago)).isoformat(), "plate_text": p,
                "ocr_conf": conf, "det_conf": 0.8, "bbox": [0, 0, 40, 12], "track_id": "g3", "reads": reads,
                "agreement": agreement, "first_read_at": (now - timedelta(seconds=secs_ago + 1)).isoformat()}
    try:
        r = c.post(f"{API}/ingest/sightings", headers=ik, json=[
            sight(low, CAMS[0], 0.85, 2, 0.75, 4),         # below the band
            sight(high, CAMS[0], 0.9, 3, 1.0, 3),          # on the band, stored as REAL
            sight(one_off, CAMS[0], 0.95, 2, 1.0, 2),      # a one-character match: a fuzzy alert
            sight(watched, CAMS[1], 0.95, 2, 1.0, 1),      # an exact match on the other camera
        ]).json()
        out["ingest"] = r
        check("four synthetic sightings stored, two alerts raised", r.get("stored") == 4 and r.get("alerts") == 2,
              str(r))
        since = (now - timedelta(seconds=30)).isoformat()
        rows = c.get(f"{API}/sightings", headers=ha, params={"camera": CAMS[0], "since": since, "limit": 50}).json()
        by = {s["plate_norm"]: s for s in rows}
        out["sightings"] = {k: {"needs_review": s.get("needs_review"), "reads": s.get("reads"),
                                "agreement": s.get("agreement"), "ocr_conf": s.get("ocr_conf")}
                            for k, s in by.items() if k in plates}
        got = {k: by[k].get("needs_review") for k in (low, high, one_off) if k in by}
        if on:
            check("0.85 is marked 'check the crop'", got.get(low) is True, str(got.get(low)))
            check("0.90 stored as REAL and read back is not marked", got.get(high) is False,
                  f"{got.get(high)} (ocr_conf read back {by.get(high, {}).get('ocr_conf')})")
        else:
            check("marking off: no sighting carries a mark", all(v is None for v in got.values()), str(got))
        check("reads and agreement are written and read back",
              by.get(low, {}).get("reads") == 2 and abs((by.get(low, {}).get("agreement") or 0) - 0.75) < 1e-6
              and by.get(high, {}).get("reads") == 3,
              f"{by.get(low, {}).get('reads')}, {by.get(low, {}).get('agreement')}; {by.get(high, {}).get('reads')}")
        alerts = c.get(f"{API}/alerts", headers=ha, params={"status": "all", "limit": 200}).json()
        mine = {x["plate_norm"]: x for x in alerts if x.get("plate_norm") in (one_off, watched)}
        out["alerts"] = {k: {"needs_review": x.get("needs_review"), "exact_match": x.get("exact_match")}
                         for k, x in mine.items()}
        check("both alerts are listed", set(mine) == {one_off, watched}, str(sorted(mine)))
        if on:
            check("the one-character alert is marked", mine.get(one_off, {}).get("needs_review") is True,
                  str(mine.get(one_off, {}).get("needs_review")))
            check("the exact alert at 0.95 is not marked", mine.get(watched, {}).get("needs_review") is False,
                  str(mine.get(watched, {}).get("needs_review")))
        else:
            check("marking off: no alert carries a mark",
                  all(x.get("needs_review") is None for x in mine.values()), str(out["alerts"]))
        out["alert_count"] = r.get("alerts")
    finally:
        c.delete(f"{API}/watchlist/{w['id']}", headers=ha)
        lst = ",".join(f"'{p}'" for p in plates)
        res = psql(f"DELETE FROM alerts WHERE plate_norm IN ({lst}); "
                   f"DELETE FROM sighting_quality WHERE sighting_id IN (SELECT id FROM vehicle_sightings WHERE plate_norm IN ({lst})); "
                   f"DELETE FROM vehicle_sightings WHERE plate_norm IN ({lst})")
        if res.startswith("psql failed"):
            print(f"  [WARN] synthetic rows not removed: {res}")
    out["fails"] = fails
    d = ROOT / "data" / "g3"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"check_{a.marking}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("ALL PASSED" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

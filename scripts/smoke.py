"""End-to-end smoke test against a running stack. Safe to re-run: uses a fresh plate
each run and cleans up what it onboards.

    uv run --no-sync python scripts/smoke.py
    uv run --no-sync python scripts/smoke.py --skip-fleet   # once non-simulator cameras are registered

Three checks assume the simulator's fleet (14 catalogue cameras, 2 GSRTC cameras, the
Gandhinagar layout). With government cameras registered they would fail for the wrong
reason, so --skip-fleet reports them as SKIP instead.
"""
import datetime as dt
import os
import random
import subprocess
import sys
from pathlib import Path

import httpx

API = os.environ.get("API", "http://localhost:8000")
KEY = os.environ.get("INGEST_KEY", "dev_ingest_key_replace_me")
PW = os.environ.get("ADMIN_PASSWORD", "admin123")
fails = 0
SKIP_FLEET = "--skip-fleet" in sys.argv


def check(name, ok, info=""):
    global fails
    fails += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {info}")


def fleet_check(name, ok, info=""):
    """A check that only holds on the simulator's own fleet."""
    if SKIP_FLEET:
        print(f"  [SKIP] {name} (fleet-specific; --skip-fleet)")
    else:
        check(name, ok, info)


def login(c, user):
    r = c.post(f"{API}/auth/login", json={"username": user, "password": PW})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# A plate no camera will ever read: GJ99 + unambiguous series letters + 10NN.
rng = random.Random()


def draw() -> tuple[str, str, str]:
    series = "".join(rng.choice("CDEFHKMNPRUVWXY") for _ in range(2))
    digits = f"10{rng.randint(10, 99)}"
    return (f"GJ99{series}{digits}",
            f"GJ99{series}1O{digits[2:]}",                                # O for 0: repaired by normalisation
            f"GJ99{series}{digits[:3]}{(int(digits[3]) + 1) % 10}")      # 1 edit away: fuzzy


PLATE, NEAR_MISS, ONE_OFF = draw()
ONB = f"SMOKE-ONB-{rng.randint(100, 999)}"
# Object counts are written ~20 days back at a random second and read over that exact window,
# so they never show in the live 24 h / 7 d views and runs cannot see each other's rows.
COUNTS_TS = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=20, seconds=rng.randint(0, 86400))
             ).replace(microsecond=0)


def psql_value(sql: str) -> str:
    r = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "sentinel", "-d", "sentinel",
                        "-tAc", sql], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else f"psql failed: {r.stderr.strip()[:120]}"

with httpx.Client(timeout=60) as c:
    h = login(c, "admin")
    check("login admin", True)
    # Earlier runs leave their plates listed and seen. One within a character of this run's would be matched too (its
    # entry, its sightings, a retrospective alert when this plate is listed): draw again until the plate is clear.
    for _ in range(50):
        if not (c.get(f"{API}/watchlist/check/{PLATE}", headers=h).json()["matches"]
                or c.get(f"{API}/sightings/movement/{PLATE}", headers=h,
                         params={"purpose": "smoke test"}).json()["total_sightings"]):
            break
        PLATE, NEAR_MISS, ONE_OFF = draw()

    # ---- Model 1: registry, GIS, reports
    r = c.post(f"{API}/cameras/sync-catalogue", headers=h).json()
    fleet_check("sync-catalogue", r["inserted"] + r["updated"] == 14 and not r["errors"], str(r))
    n = c.get(f"{API}/cameras", headers=h).json()["total"]
    check("list cameras", n >= 14, f"total={n}")
    f = len(c.get(f"{API}/gis/cameras.geojson", headers=h).json()["features"])
    # every camera with a position is on the map; one registered without a position (inventory only,
    # e.g. a sandbox camera whose name could not be placed) is left off it, and the gap report lists it
    placed = sum(1 for x in c.get(f"{API}/cameras", params={"limit": 2000}, headers=h).json()["items"]
                 if x.get("lat") is not None)
    check("geojson", f == placed, f"features={f} placed={placed} of {n}")
    g = c.get(f"{API}/reports/gaps", headers=h).json()
    check("gap report", len(g["findings"]) > 0, f"findings={len(g['findings'])}")
    nb = c.get(f"{API}/gis/nearby", headers=h, params={"lat": 23.2233, "lon": 72.6503, "radius_m": 1500}).json()
    fleet_check("nearby", nb and nb[0]["camera_code"] == "GNR-POL-001", f"{[x['camera_code'] for x in nb]}")

    # ---- watchlist + ingest + alerts
    for src in ("vahan", "egujcop"):
        r = c.post(f"{API}/watchlist/sync/{src}", headers=h).json()
        check(f"watchlist sync {src}", r["synced"] > 0, f"synced={r['synced']}")
    w = c.post(f"{API}/watchlist", headers=h, json={"kind": "stolen_vehicle", "plate": PLATE, "severity": "high",
                                                    "source": "smoke", "reason": "smoke test"}).json()
    check("watchlist create", w.get("plate_norm") == PLATE, PLATE)
    m = c.get(f"{API}/watchlist/check/{PLATE}", headers=h).json()["matches"]
    check("watchlist check exact", m and m[0]["score"] == 1.0)

    now = dt.datetime.now(dt.timezone.utc)

    def sight(cam, plate, secs_ago):
        return {"camera_code": cam, "event_ts": (now - dt.timedelta(seconds=secs_ago)).isoformat(),
                "plate_text": plate, "ocr_conf": 0.91, "det_conf": 0.88, "vehicle_type": "car",
                "bbox": [100, 200, 220, 60], "track_id": "smoke"}

    ik = {"X-Ingest-Key": KEY}
    r = c.post(f"{API}/ingest/sightings", headers=ik, json=[sight("GNR-POL-001", PLATE, 300)]).json()
    check("ingest sighting -> alert", r["stored"] == 1 and r["alerts"] == 1, str(r))
    r = c.post(f"{API}/ingest/sightings", headers=ik,
               json=[sight("AMD-AMC-001", NEAR_MISS, 120), sight("AMD-AMC-001", PLATE, 118)]).json()
    check("near-miss read repaired + cooldown", r["stored"] == 2 and r["alerts"] == 1, str(r))
    r = c.post(f"{API}/ingest/sightings", headers=ik, json=[sight("MHS-POL-001", ONE_OFF, 30)]).json()
    check("fuzzy 1-char-off alert", r["alerts"] == 1, str(r))
    r = c.post(f"{API}/ingest/sightings", headers={"bad": "x"}, json=[])
    check("ingest without key rejected", r.status_code == 401)

    mv = c.get(f"{API}/sightings/movement/{PLATE}", headers=h, params={"purpose": "smoke test"}).json()
    check("movement history", mv["distinct_cameras"] == 3 and mv["total_sightings"] == 4
          and mv["route"]["geometry"]["type"] == "LineString",
          f"cams={mv['distinct_cameras']} sightings={mv['total_sightings']} matched={mv['matched_plates']}")

    al = [a for a in c.get(f"{API}/alerts", headers=h, params={"limit": 500}).json()
          if a["plate_norm"] in (PLATE, ONE_OFF)]
    check("alerts listed", len(al) == 3, f"for this plate={len(al)}")
    a = c.post(f"{API}/alerts/{al[0]['id']}/ack", headers=h).json()
    check("ack alert", a["status"] == "acknowledged")
    a = c.post(f"{API}/alerts/{al[0]['id']}/close", headers=h,
               json={"status": "false_positive", "disposition": "smoke"}).json()
    check("close alert", a["status"] == "false_positive")
    au = c.get(f"{API}/audit", headers=h, params={"action": "plate."}).json()
    check("audit has plate searches", any(x["object_id"] == PLATE for x in au), f"rows={len(au)}")

    # ---- RBAC
    hn = login(c, "gsrtc_nodal")
    n = c.get(f"{API}/cameras", headers=hn).json()["total"]
    fleet_check("dept scoping (GSRTC sees only GSRTC)", n == 2, f"total={n}")
    check("dept nodal cannot read audit", c.get(f"{API}/audit", headers=hn).status_code == 403)
    ho = login(c, "operator")
    r = c.post(f"{API}/cameras", headers=ho, json={"camera_code": "X-1", "name": "x", "department_code": "HOME"})
    check("operator cannot create camera", r.status_code == 403)
    r = c.post(f"{API}/onboard/stream", headers=ho, json={   # a valid body, so only the permission can refuse it
        "camera_code": "SMOKE-DENIED", "name": "x", "department_code": "HOME", "district": "Gandhinagar",
        "lat": 23.22, "lon": 72.64, "source_url": "rtsp://localhost:8554/GNR-POL-002"})
    check("operator cannot onboard", r.status_code == 403, str(r.status_code))

    # ---- onboarding by URL (relay through MediaMTX), then clean up
    r = c.post(f"{API}/onboard/stream", headers=h, json={
        "camera_code": ONB, "name": "smoke relay", "department_code": "HOME", "district": "Gandhinagar",
        "lat": 23.22, "lon": 72.64, "source_url": "rtsp://smoke:secret@localhost:8554/GNR-POL-002"})
    ok = r.status_code == 200
    body = r.json() if ok else {}
    check("onboard by URL", ok and body["probe"]["codec"] == "H.265" and body["on_demand"] is True,
          f"{r.status_code} {body.get('probe', r.text[:120])}")
    if ok:
        cam = body["camera"]
        check("relay endpoints + H.265 preview", cam["rtsp_url"].endswith(f"/{ONB}") and "_sub/whep" in cam["whep_url"])
        au = c.get(f"{API}/audit", headers=h, params={"action": "camera.onboarded"}).json()
        src = next((x["detail"].get("source", "") for x in au if x["object_id"] == ONB), "")
        check("credentials masked in audit", "***" in src and "secret" not in src, src)
        check("remove relay", c.delete(f"{API}/onboard/stream/{ONB}", headers=h).status_code == 204)
        c.delete(f"{API}/cameras/{ONB}", headers=h)
    r = c.post(f"{API}/onboard/probe", headers=h, json={"source_url": "ftp://nope"})
    check("bad scheme rejected", r.status_code == 422)

    fl = c.get(f"{API}/reports/fleet", headers=h).json()
    check("fleet report", fl["cameras"] >= 14, f"cameras={fl['cameras']} online={fl['online']}")

    # ---- Vehicle and person detection: counts in, occupancy out, no identity stored
    wide = c.get(f"{API}/cameras/AMD-TRAF-001", headers=h).json()
    check("catalogue-requested analytics on a wide camera", wide["analytics_enabled"] and not wide["anpr_viable"],
          f"analytics={wide['analytics_enabled']} anpr_viable={wide['anpr_viable']}")

    def window(secs, frames, det, peak):
        return {"camera_code": "AMD-TRAF-001", "event_type": "object_counts", "value": frames,
                "event_ts": (COUNTS_TS + dt.timedelta(seconds=secs)).isoformat(),
                "detail": {"window_s": 60, "frames": frames, "detections": det, "peak": peak,
                           "peak_vehicles": sum(v for k, v in peak.items() if k != "person"), "model": "smoke"}}
    r = c.post(f"{API}/ingest/events", headers=ik, json=[
        window(0, 60, {"car": 180, "person": 30, "motorcycle": 12}, {"car": 5, "person": 2, "motorcycle": 1}),
        window(1, 40, {"car": 60, "truck": 8}, {"car": 3, "truck": 1})]).json()
    check("ingest object counts", r["stored"] == 2, str(r))
    q = {"since": (COUNTS_TS - dt.timedelta(seconds=1)).isoformat(), "until": (COUNTS_TS + dt.timedelta(seconds=2)).isoformat()}
    ob = c.get(f"{API}/reports/objects", headers=h, params=q).json()
    cam = next((x for x in ob["per_camera"] if x["camera_code"] == "AMD-TRAF-001"), {})
    check("object report: average in view and peak",
          cam.get("frames") == 100 and cam["in_view"].get("car") == 2.4 and cam["peak"].get("car") == 5
          and cam["vehicles_in_view"] == 2.6 and cam["vehicle_peak"] == 6 and ob["people"]["in_view"] == 0.3,
          f"frames={cam.get('frames')} in_view={cam.get('in_view')} veh={cam.get('vehicles_in_view')}")
    r = c.get(f"{API}/reports/objects", headers=ho, params=q)
    check("operator reads object counts", r.status_code == 200, str(r.status_code))
    n = psql_value("SELECT count(*) FROM detection_events WHERE event_type = 'object_counts' "
                   "AND (bbox IS NOT NULL OR track_id IS NOT NULL OR label IS NOT NULL)")
    check("count rows carry no box, track or label", n == "0", f"rows with identity fields: {n}")

print(f"\n{'ALL PASSED' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)

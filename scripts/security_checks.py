"""Negative security checks against a running stack: what must be refused, is.

Kept apart from smoke.py (the end-to-end happy path) so each can grow on its own.
Safe to re-run: its throwaway crop files, and the synthetic sighting and review the plate-review checks
make, are removed afterwards, and its publish probe hangs up before sending any video.

    uv run --no-sync python scripts/security_checks.py
"""
import os
import random
import re
import socket
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

API = os.environ.get("API", "http://localhost:8000")
PW = os.environ.get("ADMIN_PASSWORD", "admin123")
ROOT = Path(__file__).resolve().parents[1]
JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")   # a minimal JPEG
PLATE_LIKE = re.compile(r"[A-Z]{2}\s?\d{1,2}\s?[A-Z]{0,3}\s?\d{4}|\d{2}\s?BH\s?\d{4}")
fails = 0


def check(name, ok, info=""):
    global fails
    fails += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {info}")


def login(c, user):
    r = c.post(f"{API}/auth/login", json={"username": user, "password": PW})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def psql(sql: str) -> str:
    r = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "sentinel", "-d", "sentinel",
                        "-tAc", sql], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else f"psql failed: {r.stderr.strip()[:120]}"


def lan_ip() -> str | None:
    """This machine's LAN address, to see what other machines on the network can reach."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def rtsp_announce(host: str, port: int, path: str) -> str:
    """Offer the relay a new stream without credentials, as any machine on the network could, and
    return its status line. The connection closes at once, so nothing is ever published."""
    sdp = ("v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=probe\r\nc=IN IP4 0.0.0.0\r\nt=0 0\r\n"
           "m=video 0 RTP/AVP 96\r\na=rtpmap:96 H264/90000\r\na=fmtp:96 packetization-mode=1\r\n"
           "a=control:trackID=0\r\n")
    req = (f"ANNOUNCE rtsp://{host}:{port}/{path} RTSP/1.0\r\nCSeq: 1\r\nContent-Type: application/sdp\r\n"
           f"Content-Length: {len(sdp)}\r\n\r\n{sdp}")
    try:
        with socket.create_connection((host, port), timeout=3) as s:
            s.sendall(req.encode())
            return s.recv(1024).decode(errors="replace").split("\r\n", 1)[0]
    except OSError as e:
        return f"no answer ({e.__class__.__name__})"


with httpx.Client(timeout=30) as c:
    ho, hn = login(c, "operator"), login(c, "gsrtc_nodal")

    # ---- evidence crops: token, permission and camera scope, never an open folder
    crop = ROOT / "data" / "crops" / "AMD-AMC-001" / f"seccheck_{random.randint(10**5, 10**6)}.jpg"
    crop.parent.mkdir(parents=True, exist_ok=True)
    crop.write_bytes(JPEG)
    url = f"{API}/crops/AMD-AMC-001/{crop.name}"
    try:
        # The token comes in the Authorization header only: one carried in a URL ends up in history and proxy logs.
        in_url = c.get(url, params={"token": ho["Authorization"][7:]}).status_code
        check("crop needs a token, in the header and never in the URL", c.get(url).status_code == 401 and in_url == 401,
              f"token in the URL: {in_url}")
        check("crop served to operator", c.get(url, headers=ho).status_code == 200)
        r = c.get(url, headers=hn)
        check("crop refused without search/alert permission", r.status_code == 403, str(r.status_code))
        # On Windows a backslash is a path separator: '<camera>/..\<other camera>\<file>' once reached another
        # camera's crop while the scope was checked against the first camera.
        r = c.get(f"{API}/crops/AMD-AMC-001/..%2F..%2F..%2F.env", headers=ho)
        r2 = c.get(f"{API}/crops/GNR-GSRTC-001/..%5CAMD-AMC-001%5C{crop.name}", headers=ho)
        check("crop path cannot leave the store or its camera's folder", r.status_code == 404 and r2.status_code == 404,
              f"{r.status_code}, {r2.status_code}")
    finally:
        crop.unlink(missing_ok=True)

    # ---- plate-reading quality report: signed-in users only, the caller's department only, counts only
    anon = c.get(f"{API}/reports/camera-quality").status_code
    r = c.get(f"{API}/reports/camera-quality", headers=hn)
    depts = {i.get("department") for i in r.json()} if r.status_code == 200 else {r.status_code}
    check("camera-quality report: sign-in needed, own department only, no plate text",
          anon == 401 and depts <= {"GSRTC"} and not PLATE_LIKE.search(r.text.upper()),
          f"anonymous {anon}, nodal sees {sorted(map(str, depts))}")

    # ---- department scope on write paths: a nodal officer writes only their own department's cameras
    r = c.post(f"{API}/cameras", headers=hn, json={"camera_code": "AMD-POL-001", "name": "takeover attempt",
                                                   "department_code": "GSRTC", "mode": "ip_rtsp"})
    check("nodal cannot take over another department's camera code", r.status_code == 403, str(r.status_code))
    r = c.patch(f"{API}/cameras/GNR-GSRTC-001", headers=hn, json={"department_code": "HOME"})
    dept = c.get(f"{API}/cameras/GNR-GSRTC-001", headers=hn).json().get("department_code")
    check("nodal cannot move a camera to another department", dept == "GSRTC", f"{r.status_code}, now {dept}")
    r = c.delete(f"{API}/onboard/stream/AMD-POL-001", headers=hn)
    check("nodal cannot remove another department's relay", r.status_code == 403, str(r.status_code))
    r = c.post(f"{API}/cameras/sync-catalogue", headers=hn, params={"dry_run": "true"})
    check("catalogue sync needs a statewide user", r.status_code == 403, str(r.status_code))

    # ---- ingest integrity: a replay is not stored twice; a thin read does not page anyone
    ha, ik = login(c, "admin"), {"X-Ingest-Key": os.environ.get("INGEST_KEY", "dev_ingest_key_replace_me")}
    plate = f"GJ98{random.choice('CDEFHKMNPR')}{random.choice('CDEFHKMNPR')}{random.randint(1000, 9999)}"
    one_off = plate[:-1] + str((int(plate[-1]) + 1) % 10)
    w = c.post(f"{API}/watchlist", headers=ha, json={"kind": "stolen_vehicle", "plate": plate, "severity": "high",
                                                     "source": "security_checks", "reason": "integrity check"}).json()
    now = datetime.now(timezone.utc)

    def sight(p, cam, reads, secs_ago=0):
        return {"camera_code": cam, "event_ts": (now - timedelta(seconds=secs_ago)).isoformat(), "plate_text": p,
                "ocr_conf": 0.9, "det_conf": 0.8, "bbox": [0, 0, 40, 12], "track_id": "sec", "reads": reads}
    try:
        bid = f"sec-{random.getrandbits(64):x}"
        first = c.post(f"{API}/ingest/sightings", headers=ik, params={"batch_id": bid},
                       json=[sight("MH12ZZ0001", "GNR-POL-001", 3)]).json()
        again = c.post(f"{API}/ingest/sightings", headers=ik, params={"batch_id": bid},
                       json=[sight("MH12ZZ0001", "GNR-POL-001", 3)]).json()
        check("replayed batch is not stored twice", first.get("stored") == 1 and again.get("duplicate_batch")
              and again.get("stored") == 0, f"{first} then {again}")
        r = c.post(f"{API}/ingest/sightings", headers=ik, json=[sight(one_off, "AMD-POL-001", 1)]).json()
        check("single read + one-character slip raises no alert", r.get("stored") == 1 and r.get("alerts") == 0, str(r))
        r = c.post(f"{API}/ingest/sightings", headers=ik, json=[sight(plate, "MHS-POL-001", 1)]).json()
        check("single read with an exact match still alerts", r.get("alerts") == 1, str(r))
    finally:
        c.delete(f"{API}/watchlist/{w['id']}", headers=ha)

    # ---- plate review: not for operators or nodal officers; a blind check shows no read and cannot be
    # graded by the client
    got = [f(f"{API}/reviews{p}", headers=h, **kw).status_code for h in (ho, hn) for f, p, kw in (
        (c.get, "/queue", {"params": {"mode": "blind"}}), (c.get, "/summary", {}),
        (c.post, "", {"json": {"sighting_id": 1, "mode": "blind", "seen": "?"}}))]
    check("operator and nodal officer cannot use plate review", got == [403] * 6, str(got))
    # One synthetic sighting with its own crop; it, the review of it and the crop are removed afterwards.
    cam, sid = "GNR-POL-001", None
    plate = f"GJ99{random.choice('CDEFHKMNPR')}{random.choice('CDEFHKMNPR')}{random.randint(1000, 9999)}"
    crop = ROOT / "data" / "crops" / cam / f"seccheck_{random.randint(10**5, 10**6)}.jpg"
    crop.parent.mkdir(parents=True, exist_ok=True)
    crop.write_bytes(JPEG)
    ts = datetime.now(timezone.utc)
    try:
        c.post(f"{API}/ingest/sightings", headers=ik, json=[{
            "camera_code": cam, "event_ts": ts.isoformat(), "plate_text": plate, "ocr_conf": 0.9, "det_conf": 0.8,
            "bbox": [0, 0, 40, 12], "track_id": "sec", "reads": 3, "crop_path": f"/crops/{cam}/{crop.name}"}])
        window = {"camera": cam, "since": (ts - timedelta(seconds=1)).isoformat(), "limit": 200}
        verify = c.get(f"{API}/reviews/queue", headers=ha, params={**window, "mode": "verify"}).json()
        sid = next((i["sighting_id"] for i in verify if i.get("plate_norm") == plate), None)
        blind = c.get(f"{API}/reviews/queue", headers=ha, params={**window, "mode": "blind"})
        items = blind.json() if blind.status_code == 200 else []
        keys = set().union(*(i.keys() for i in items))
        leaks = [v for i in items for v in i.values() if isinstance(v, str) and PLATE_LIKE.search(v.upper())]
        check("blind queue shows no plate text or confidence",
              any(i["sighting_id"] == sid for i in items) and not leaks and plate not in blind.text
              and keys <= {"sighting_id", "event_ts", "camera_code", "camera_name", "crop_path"},
              f"{len(items)} items, keys {sorted(keys)}, {len(leaks)} plate-like values")
        r = c.post(f"{API}/reviews", headers=ha, json={"sighting_id": sid, "mode": "blind", "seen": "?",
                                                         "verdict": "exact"})
        got = r.json().get("verdict") if r.status_code == 201 else r.status_code
        check("blind verdict is computed by the server, not taken from the client", got == "unreadable", str(got))
    finally:
        crop.unlink(missing_ok=True)
        out = psql(f"DELETE FROM plate_reviews WHERE stored_plate = '{plate}'; DELETE FROM alerts WHERE plate_norm = '{plate}'; "
                   f"DELETE FROM sighting_quality WHERE sighting_id IN (SELECT id FROM vehicle_sightings WHERE plate_norm = '{plate}'); "
                   f"DELETE FROM vehicle_sightings WHERE plate_norm = '{plate}'")
        if out.startswith("psql failed"):
            print(f"  [WARN] the review check's synthetic sighting was not removed: {out}")

    # ---- secrets: the live .env must not carry the example file's values (the repo is readable by every
    # other finalist; with the ingest key anyone on the LAN could fabricate sightings and alerts)
    def env_file(path):
        return {k.strip(): v.strip() for k, v in (line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                                                  if "=" in line and not line.lstrip().startswith("#"))}
    live, example = env_file(ROOT / ".env"), env_file(ROOT / ".env.example")
    same = [k for k in ("JWT_SECRET", "INGEST_KEY", "MEDIAMTX_PUBLISH_PASS", "POSTGRES_PASSWORD")
            if example.get(k) and live.get(k, example[k]) == example[k]]
    check("live secrets differ from .env.example (JWT, ingest key, publisher, database)", not same,
          ("still the example value: " + ", ".join(same)) if same else "all four replaced")
    check("admin password is not the dev default", PW != "admin123",
          "" if PW != "admin123" else "set one with scripts/set_passwords.py, then export ADMIN_PASSWORD")

    # ---- control plane: nothing but the API, UI and video ports is reachable from the LAN
    ip = lan_ip()
    if ip:
        for port, what in ((5432, "Postgres"), (6379, "Valkey"), (9997, "MediaMTX control API"),
                           (9998, "MediaMTX metrics"), (8010, "simulator control (outage switch)")):
            check(f"{what} not reachable from the LAN", not reachable(ip, port), f"{ip}:{port}")
        # Viewing is open on the LAN (relay auth hook: roadmap), but a stream may only be pushed in
        # with the publisher credential: otherwise anyone nearby could replace a camera's picture.
        status = rtsp_announce(ip, 8554, f"seccheck-publish-{random.randint(10**5, 10**6)}")
        check("anonymous publish from the LAN refused", " 401 " in f"{status} ", f"{ip}:8554 {status}")
    else:
        print("  [SKIP] no LAN address: exposure checks need a network interface")

print("\nALL PASSED" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)

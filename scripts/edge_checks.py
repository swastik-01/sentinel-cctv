"""Edge cases against a running stack: every endpoint answers hostile input with a 4xx, never a 5xx, and each
Model 1 / Model 2 function holds at its limits (bounds, clears, scope, Unicode, empty and oversized files).

Kept apart from smoke.py (the happy path) and security_checks.py (what must be refused). Safe to re-run: the
cameras (ZZEDGE-*), watchlist plates, sightings, alerts, plate reviews, the crop file and the scoped user it makes are
removed afterwards.

    uv run --no-sync python scripts/edge_checks.py
"""
import asyncio
import concurrent.futures as cf
import json
import os
import random
import socket
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import httpx
import websockets

API = os.environ.get("API", "http://localhost:8000")
PW = os.environ.get("ADMIN_PASSWORD", "admin123")
INGEST = {"X-Ingest-Key": os.environ.get("INGEST_KEY", "dev_ingest_key_replace_me")}
ROOT = Path(__file__).resolve().parents[1]
SCOPED = "edge_scoped_operator"        # an operator held to GSRTC, made here and removed afterwards
JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")   # a minimal JPEG, for a review's crop
fails = 0

# Query and path values no endpoint may answer with a 5xx.
HOSTILE = ["-1", "0", "99999999999999999999", "1e400", "nan", "abc", "' OR '1'='1", "%_\\", "\x00", "x" * 5000,
           "ગુજરાત", "2026-13-45T99:00:00", ""]
PATH_HOSTILE = ["ZZNOPE", "..", "%2e%2e%2f", "x" * 300, "\x00", "00000000-0000-0000-0000-000000000000", "ગુ"]
REQUIRED = {"lat": "23.02", "lon": "72.57", "purpose": "edge check"}
# Not fuzzed: sign-in (its throttle would lock the run out), and anything that reaches outside the stack.
SKIP = {("post", "/auth/login"), ("post", "/auth/token"), ("post", "/onboard/stream")}


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


class Listener(threading.Thread):
    """The control room's event socket for one user: authenticates with its first message, as the web app does, and
    keeps every event with the time it arrived. `code` is the close code when the server refuses the socket."""

    def __init__(self, headers):
        super().__init__(daemon=True)
        self.token = headers["Authorization"].split()[1]
        self.events: list[tuple[float, dict]] = []
        self.code = None
        self.ready, self.stopped = threading.Event(), threading.Event()

    def run(self):
        asyncio.run(self._run())

    async def _run(self):
        url = API.replace("http://", "ws://").replace("https://", "wss://") + "/ws/events"
        try:
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({"type": "auth", "token": self.token}))
                self.ready.set()
                while not self.stopped.is_set():
                    try:
                        self.events.append((time.monotonic(), json.loads(await asyncio.wait_for(ws.recv(), 0.5))))
                    except asyncio.TimeoutError:
                        continue
        except websockets.ConnectionClosed as e:
            self.code = e.code
        except OSError as e:
            self.code = f"no connection ({e.__class__.__name__})"
        finally:
            self.ready.set()

    def wait_for(self, kind, pred=lambda e: True, timeout=5.0):
        """Seconds from now until a matching event arrives (it may already have), or None."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for at, e in self.events:
                if e.get("type") == kind and pred(e):
                    return at
            time.sleep(0.05)
        return None


def rtsp_announce_from(src: str, relay: str, path: str) -> str:
    """Offer the relay a stream without credentials from source address `src`, and return its status line. The
    connection closes at once, so nothing is published. On Windows and Linux all of 127.0.0.0/8 is loopback, so
    127.0.0.2 reaches the relay from outside its 127.0.0.1 exemption without touching the network."""
    host, port = relay.rsplit(":", 1)
    sdp = ("v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=probe\r\nc=IN IP4 0.0.0.0\r\nt=0 0\r\n"
           "m=video 0 RTP/AVP 96\r\na=rtpmap:96 H264/90000\r\na=fmtp:96 packetization-mode=1\r\na=control:trackID=0\r\n")
    req = (f"ANNOUNCE rtsp://{host}:{port}/{path} RTSP/1.0\r\nCSeq: 1\r\nContent-Type: application/sdp\r\n"
           f"Content-Length: {len(sdp)}\r\n\r\n{sdp}")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.bind((src, 0))
            s.connect((host, int(port)))
            s.sendall(req.encode())
            return s.recv(1024).decode(errors="replace").split("\r\n", 1)[0]
    except OSError as e:
        return f"no answer ({e.__class__.__name__})"


def fuzz(c, spec, h, who):
    """Every operation in the API's own OpenAPI document, one hostile value at a time."""
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if (method, path) in SKIP or path.startswith("/ws"):
                continue
            params = op.get("parameters", [])
            base_q = {p["name"]: REQUIRED[p["name"]] for p in params if p["in"] == "query" and p.get("required")
                      and p["name"] in REQUIRED}
            path_params = [p["name"] for p in params if p["in"] == "path"]
            if path == "/cameras/sync-catalogue":
                base_q["dry_run"] = "true"            # never writes; a bad url must be a 4xx
            bad = []

            def url(val="ZZNOPE"):
                u = path
                for n in path_params:
                    u = u.replace("{" + n + "}", quote(val, safe=""))
                return API + u

            if method == "get":
                for p in (p for p in params if p["in"] == "query"):
                    for v in HOSTILE:
                        q = {**base_q, p["name"]: v}
                        r = c.get(url(), params=q, headers=h)
                        if r.status_code >= 500:
                            bad.append(f"{p['name']}={v[:20]!r}→{r.status_code}")
                for v in PATH_HOSTILE if path_params else []:
                    r = c.get(url(v), params=base_q, headers=h)
                    if r.status_code >= 500:
                        bad.append(f"path {v[:20]!r}→{r.status_code}")
            else:
                if path == "/cameras/sync-catalogue":
                    for v in ("abc", "file:///C:/Windows/win.ini", "http://[::1", "\x00", "x" * 3000):
                        r = c.post(API + path, params={**base_q, "url": v}, headers=h)
                        if r.status_code >= 500:
                            bad.append(f"url={v[:20]!r}→{r.status_code}")
                    check(f"{who}: POST {path} survives hostile catalogue URLs", not bad, "; ".join(bad[:6]))
                    continue
                for v in PATH_HOSTILE if path_params else ["ZZNOPE"]:
                    for body in (b"not json", b"null", b"[]", b"{}", b'{"x": NaN}', b"\xff\xfe"):
                        r = c.request(method.upper(), url(v), content=body, params=base_q,
                                      headers={**h, "Content-Type": "application/json"})
                        if r.status_code >= 500:
                            bad.append(f"{v[:12]!r} {body[:10]!r}→{r.status_code}")
            check(f"{who}: {method.upper()} {path} answers hostile input without a 5xx", not bad, "; ".join(bad[:6]))


def main():
    c = httpx.Client(timeout=60)
    ha, hs, ho, hn, hau = (login(c, u) for u in ("admin", "supervisor", "operator", "gsrtc_nodal", "auditor"))
    spec = c.get(f"{API}/openapi.json").json()
    suffix = f"{random.getrandbits(24):06X}"
    cams = [f"ZZEDGE-{suffix}-1", f"ZZEDGE-{suffix}-2"]
    plates = [f"GJ97{random.choice('CDEFHKMNPR')}{random.choice('CDEFHKMNPR')}{random.randint(1000, 9999)}"
              for _ in range(4)]       # the third is listed only after it has been seen; the fourth is reviewed
    review_crop = ROOT / "data" / "crops" / "GNR-POL-001" / f"edgecheck_{random.getrandbits(32):08x}.jpg"
    watch_ids: list[str] = []
    print(f"edge checks against {API} (cameras {cams[0]}, {cams[1]}; plates {', '.join(plates)})")
    try:
        # ---- scoped user: an operator held to GSRTC, sharing the seeded operator's password
        out = psql(f"""INSERT INTO users (username, full_name, password_hash, role_id, department_id)
                       SELECT '{SCOPED}', 'Edge-check scoped operator', password_hash,
                              (SELECT id FROM roles WHERE code = 'operator'),
                              (SELECT id FROM departments WHERE code = 'GSRTC')
                       FROM users WHERE username = 'operator' ON CONFLICT (username) DO NOTHING""")
        hsc = login(c, SCOPED) if not out.startswith("psql failed") else None
        check("scoped operator made for the scope checks", hsc is not None, out[:80])

        # ---- 1. every endpoint, hostile input, as the administrator and as a scoped user
        print("-- hostile input on every endpoint")
        fuzz(c, spec, ha, "admin")
        if hsc:
            fuzz(c, spec, hsc, "scoped")

        # ---- 2. registry (Model 1): create, bounds, clears, Unicode, filters
        print("-- registry")
        body = {"camera_code": cams[0], "name": "Edge <img src=x onerror=alert(1)> ગેટ 🚦", "department_code": "HOME",
                "district": "Gandhinagar", "lat": 23.2156, "lon": 72.6369, "camera_class": "bullet", "vendor": "Hikvision",
                "maintenance": "faulty", "maintenance_note": "lens cracked; ticket #4471", "install_year": 2015,
                "amc_expiry": (date.today() - timedelta(days=10)).isoformat(), "retention_days": 30}
        r = c.post(f"{API}/cameras", headers=hs, json=body)
        check("supervisor registers a camera with the maintenance fields", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
        cam = c.get(f"{API}/cameras/{cams[0]}", headers=hs).json()
        check("name with markup, Gujarati and emoji comes back exactly as sent", cam.get("name") == body["name"])
        check("maintenance, installation year and AMC are stored",
              (cam.get("maintenance"), cam.get("install_year"), cam.get("amc_expiry")) ==
              ("faulty", 2015, body["amc_expiry"]), str((cam.get("maintenance"), cam.get("install_year"), cam.get("amc_expiry"))))
        r = c.post(f"{API}/cameras", headers=hs, json={**body, "maintenance": None, "install_year": None})
        cam = c.get(f"{API}/cameras/{cams[0]}", headers=hs).json()
        check("re-posting without the maintenance fields keeps them", (cam.get("maintenance"), cam.get("install_year")) ==
              ("faulty", 2015), f"{r.status_code} {cam.get('maintenance')} {cam.get('install_year')}")
        bad = {"install_year": 1800, "amc_expiry": "31/12/2026", "maintenance": "broken", "fps": 999, "lat": 91,
               "name": "", "maintenance_note": "x" * 501, "retention_days": -5, "bearing_deg": 400, "camera_class": "tank",
               "vendor": "v" * 101, "district": "Atlantis"}
        got = {k: c.patch(f"{API}/cameras/{cams[0]}", headers=hs, json={k: v}).status_code for k, v in bad.items()}
        check("each bad field is refused with a 422", set(got.values()) == {422}, str({k: v for k, v in got.items() if v != 422}))
        r = c.patch(f"{API}/cameras/{cams[0]}", headers=hs, json={"name": "nul\x00byte"})
        check("a NUL byte in a name is a 4xx, not a database error", 400 <= r.status_code < 500, str(r.status_code))
        r = c.patch(f"{API}/cameras/{cams[0]}", headers=hs,
                    json={"install_year": None, "amc_expiry": None, "vendor": None, "maintenance_note": None})
        cam = r.json() if r.status_code == 200 else {}
        check("explicit nulls clear installation year, AMC, vendor and note",
              r.status_code == 200 and all(cam.get(k) is None for k in ("install_year", "amc_expiry", "vendor", "maintenance_note")),
              f"{r.status_code} {[(k, cam.get(k)) for k in ('install_year', 'amc_expiry', 'vendor', 'maintenance_note')]}")
        r = c.patch(f"{API}/cameras/{cams[0]}", headers=hs, json={"district": None})
        check("clearing the district clears it", r.status_code == 200 and r.json().get("district") is None,
              f"{r.status_code} {r.json().get('district') if r.status_code == 200 else r.text[:80]}")
        r = c.patch(f"{API}/cameras/{cams[0]}", headers=hs, json={"district": "Gandhinagar"})
        r = c.patch(f"{API}/cameras/{cams[0]}", headers=hs, json={"lat": None, "lon": None})
        check("clearing both coordinates removes the location", r.status_code == 200 and r.json().get("lat") is None,
              f"{r.status_code} {r.text[:100]}")
        r = c.patch(f"{API}/cameras/{cams[0]}", headers=hs, json={"lat": 23.2156, "lon": 72.6369, "install_year": 2015,
                                                                    "amc_expiry": body["amc_expiry"]})
        check("coordinates and dates can be set again", r.status_code == 200 and r.json().get("lat") is not None, str(r.status_code))
        got = [c.patch(f"{API}/cameras/{cams[0]}", headers=hs, json={k: None}).status_code
               for k in ("name", "camera_class", "maintenance", "anpr_viable")]
        check("a required field cannot be cleared (422)", got == [422] * 4
              and c.get(f"{API}/cameras/{cams[0]}", headers=hs).json().get("name"), str(got))
        r = c.patch(f"{API}/cameras/{cams[0]}", headers=hs, json={"lat": None})
        check("clearing one coordinate alone is a 422", r.status_code == 422, str(r.status_code))
        got = [c.patch(f"{API}/cameras/{x}", headers=hs, json={"name": "x"}).status_code for x in ("ZZNOPE-404", "..%2F..")]
        check("editing an unknown camera is a 404", all(s in (404, 422) for s in got), str(got))
        r = c.patch(f"{API}/cameras/{cams[0]}", headers=hn, json={"name": "taken over"})
        check("a GSRTC nodal officer cannot edit a police camera", r.status_code in (403, 404), str(r.status_code))
        r = c.patch(f"{API}/cameras/{cams[0]}", headers=ho, json={"name": "x"})
        check("an operator cannot edit the registry", r.status_code == 403, str(r.status_code))

        lst = lambda **q: c.get(f"{API}/cameras", headers=hs, params={"limit": 2000, **q})  # noqa: E731
        codes = lambda r: {x["camera_code"] for x in r.json()["items"]}  # noqa: E731
        check("filter maintenance=faulty finds it", cams[0] in codes(lst(maintenance="faulty")))
        check("filter maintenance=in_service leaves it out", cams[0] not in codes(lst(maintenance="in_service")))
        check("filter camera_class=bullet finds it", cams[0] in codes(lst(camera_class="bullet")))
        check("search by Gujarati text finds it", cams[0] in codes(lst(q="ગેટ")))
        got = [lst(**q).status_code for q in ({"maintenance": "broken"}, {"camera_class": "tank"}, {"limit": -1},
                                               {"offset": -1}, {"limit": 999999})]
        check("bad filters are a 422", got == [422] * 5, str(got))
        got = [lst(q=v).status_code for v in ("%", "_", "'", "\\", "%%%_", "a" * 1000)]
        check("search wildcards and quotes are text, not SQL", got == [200] * 6, str(got))
        check("a search for '%' does not match every camera", cams[0] not in codes(lst(q="%")))

        # ---- 3. CSV import edges
        print("-- CSV import")
        imp = lambda data, name="c.csv": c.post(f"{API}/cameras/import", headers=hs,  # noqa: E731
                                               files={"file": (name, data, "text/csv")})
        r = imp(b"")
        check("an empty file is a 422", r.status_code == 422, f"{r.status_code} {r.text[:80]}")
        r = imp(b"code,title\nX,Y\n")
        check("missing columns are named in a 422", r.status_code == 422 and "camera_code" in r.text, f"{r.status_code} {r.text[:80]}")
        r = imp(b"camera_code,name,department_code\n")
        check("a header-only file imports nothing", r.status_code == 200 and r.json()["inserted"] == 0, r.text[:80])
        rows = ("camera_code,name,department_code,district,fps,lat,lon,maintenance,install_year,amc_expiry,extra\n"
                f"{cams[1]},Caf\xe9 Gate,HOME,Gandhinagar,25,23.1,72.6,Under maintenance,2019,2027-03-31,ignored\n"
                "ZZEDGE-BAD1,Bad fps,HOME,Gandhinagar,1e400,,,,,,\n"
                "ZZEDGE-BAD2,Bad date,HOME,Gandhinagar,,,,,,31/03/2027,\n"
                "ZZEDGE-BAD3,Bad dept,NOPE,,,,,,,,\n"
                "ZZEDGE-BAD4,Bad lat,HOME,,,95,72,,,,\n"
                "../evil,Path code,HOME,,,,,,,,\n"
                ",No code,HOME,,,,,,,,\n")
        r = imp(rows.encode("cp1252"))
        j = r.json() if r.status_code == 200 else {}
        check("a cp1252 file imports its good row and reports each bad one by line",
              j.get("inserted", 0) + j.get("updated", 0) == 1 and len(j.get("errors", [])) == 6,
              f"{r.status_code} inserted={j.get('inserted')} errors={[e['line'] for e in j.get('errors', [])]}")
        cam = c.get(f"{API}/cameras/{cams[1]}", headers=hs).json()
        check("the imported row kept its accent and its maintenance state",
              cam.get("name") == "Caf\xe9 Gate" and cam.get("maintenance") == "under_maintenance", str((cam.get("name"), cam.get("maintenance"))))
        check("no bad row was written", c.get(f"{API}/cameras/ZZEDGE-BAD1", headers=hs).status_code == 404)
        r = imp(b"\xef\xbb\xbfcamera_code,name,department_code\n" + f"{cams[1]},BOM Gate,HOME\n".encode())
        check("a UTF-8 file with a byte-order mark is read", r.status_code == 200 and r.json().get("updated") == 1, r.text[:80])
        r = imp(b"camera_code,name,department_code\n" + b"ZZ,x,HOME\n" * (11 * 2**20 // 9))
        check("a file over 10 MB is a 413", r.status_code == 413, str(r.status_code))
        r = imp(b"camera_code,name,department_code\nZZEDGE-NUL,a\x00b,HOME\n")
        check("a NUL byte in a CSV cell is a row error, not a 500", r.status_code < 500, f"{r.status_code} {r.text[:100]}")
        c.delete(f"{API}/cameras/ZZEDGE-NUL", headers=ha)
        got = [c.post(f"{API}/cameras/import", headers=hs, files={"file": (f"x{n}.bin", random.Random(n).randbytes(4096),
                                                                            "application/octet-stream")}).status_code
               for n in range(25)]
        check("25 files of random bytes are each refused or imported as nothing, never a 500",
              all(s < 500 for s in got), str(sorted(set(got))))
        r = imp(b"camera_code,name,department_code\rZZEDGE-CR,Lone CR,HOME\r")
        check("a file with lone carriage-return line ends is read", r.status_code == 200 and r.json().get("inserted") == 1,
              f"{r.status_code} {r.text[:100]}")
        c.delete(f"{API}/cameras/ZZEDGE-CR", headers=ha)
        r = imp(b'camera_code,name,department_code\nZZEDGE-Q1,"broken quote,HOME\nZZEDGE-Q2,x,HOME\n' + b"x" * 140000)
        check("a broken quote or a giant field is a 422 and nothing is kept",
              r.status_code == 422 and c.get(f"{API}/cameras/ZZEDGE-Q1", headers=hs).status_code == 404,
              f"{r.status_code} {r.text[:100]}")
        r2 = c.post(f"{API}/cameras/import", headers=hn, files={"file": ("c.csv", b"camera_code,name,department_code\nZZEDGE-GS2,x,HOME\n", "text/csv")})
        j2 = r2.json() if r2.status_code == 200 else {}
        check("a nodal officer's CSV row for another department is refused", r2.status_code == 200 and j2.get("inserted") == 0
              and j2.get("errors"), f"{r2.status_code} {r2.text[:100]}")
        c.delete(f"{API}/cameras/ZZEDGE-GS", headers=ha)
        tpl = c.get(f"{API}/cameras/template.csv", headers=hs).text.splitlines()[0]
        check("the template carries the maintenance columns", all(k in tpl for k in ("maintenance", "install_year", "amc_expiry")), tpl[-60:])
        exp = c.get(f"{API}/cameras/export.csv", headers=hs)
        check("the export carries them too", exp.status_code == 200 and "amc_expiry" in exp.text.splitlines()[0])

        # ---- 4. GIS and reports
        print("-- GIS and reports")
        got = [c.get(f"{API}/gis/clusters", headers=hs, params={"bbox": b}).status_code
               for b in ("a,b,c,d", "nan,0,1,1", "0,0,1", "-200,0,1,1", "0,-95,1,1", "inf,0,1,1", "1,1,0,0")]
        check("bad bounding boxes are a 422", all(s == 422 for s in got[:6]), str(got))
        g = c.get(f"{API}/gis/cameras.geojson", headers=hs, params={"maintenance": "faulty"}).json()
        props = [f["properties"] for f in g.get("features", []) if f["properties"]["camera_code"] == cams[0]]
        check("the map's GeoJSON carries the maintenance fields and filters by them",
              props and props[0].get("maintenance") == "faulty" and props[0].get("install_year") == 2015, str(props[:1]))
        fl = c.get(f"{API}/reports/fleet", headers=hs).json()
        check("fleet report counts maintenance and ageing",
              all(k in fl for k in ("under_maintenance", "faulty", "amc_expired", "ageing", "install_year_unknown"))
              and fl["faulty"] >= 1 and fl["amc_expired"] >= 1, str({k: fl.get(k) for k in ("faulty", "amc_expired", "ageing")}))
        gp = c.get(f"{API}/reports/gaps", headers=hs).json()
        fs = [f for f in gp["findings"] if f["district"] == "Gandhinagar"]
        check("gap analysis names the expired AMC and the faulty camera",
              any("AMC" in f["finding"] and "expired" in f["finding"] for f in fs)
              and any("faulty" in f["finding"] for f in fs), str([f["finding"] for f in fs])[:200])
        check("gap analysis names cameras past the replacement age",
              any("plan replacement" in f["finding"] for f in fs), f"ageing_years={gp.get('ageing_years')}")
        check("the auditor reads reports", c.get(f"{API}/reports/gaps", headers=hau).status_code == 200)

        # ---- 5. alerts (Model 2): tags, scope, races
        print("-- alerts")
        for p in plates[:2]:
            w = c.post(f"{API}/watchlist", headers=ha, json={"kind": "stolen_vehicle", "plate": p, "severity": "high",
                                                             "source": "edge_checks", "reason": "edge check"}).json()
            watch_ids.append(w["id"])
        # The control room's live feed, open before anything is raised: the administrator (statewide), the scoped GSRTC
        # operator, and the GSRTC nodal officer (no alert permission: the socket must be refused).
        live = {"admin": Listener(ha), "nodal": Listener(hn)}
        if hsc:
            live["scoped"] = Listener(hsc)
        for x in live.values():
            x.start()
        for x in live.values():
            x.ready.wait(10)
        time.sleep(0.5)
        check("the nodal officer's event socket is refused (4403: no alert permission)",
              live["nodal"].wait_for("never", timeout=3) is None and live["nodal"].code == 4403, str(live["nodal"].code))
        now = datetime.now(timezone.utc).isoformat()
        sight = lambda p, cam: {"camera_code": cam, "event_ts": now, "plate_text": p, "ocr_conf": 0.95,  # noqa: E731
                                "det_conf": 0.9, "bbox": [0, 0, 40, 12], "track_id": "edge", "reads": 3}
        sent_at = time.monotonic()
        r1 = c.post(f"{API}/ingest/sightings", headers=INGEST, json=[sight(plates[0], "GNR-POL-001")]).json()
        r2 = c.post(f"{API}/ingest/sightings", headers=INGEST, json=[sight(plates[1], "GNR-GSRTC-001")]).json()
        is_new = lambda plate: (lambda e: (e.get("alert") or {}).get("plate_norm") == plate)  # noqa: E731
        got = [live["admin"].wait_for("alert.new", is_new(p)) for p in plates[:2]]
        check("both alerts reach the administrator's live feed within 5 s (a real broker: fakeredis drops pub/sub)",
              all(got), f"after {[round(g - sent_at, 2) if g else None for g in got]} s, code {live['admin'].code}")
        if "scoped" in live:
            check("the scoped operator's live feed gets the GSRTC alert and not the police one",
                  live["scoped"].wait_for("alert.new", is_new(plates[1])) is not None
                  and live["scoped"].wait_for("alert.new", is_new(plates[0]), timeout=1) is None)
            other = [e for _, e in live["scoped"].events if e.get("type") == "sighting.new"
                     and (e.get("sighting") or {}).get("camera_code") != "GNR-GSRTC-001"]
            check("and no sighting from another department's camera", not other, str(other[:1])[:120])
        check("two synthetic alerts raised (police and GSRTC cameras)", r1.get("alerts") == 1 and r2.get("alerts") == 1, f"{r1} {r2}")
        # Seen, then listed (a retrospective alert for that pass), then seen again at the same camera inside the alert
        # cooldown: the second pass is news and must raise its own alert.
        c.post(f"{API}/ingest/sightings", headers=INGEST, json=[sight(plates[2], "GNR-POL-001")])
        w = c.post(f"{API}/watchlist", headers=ha, json={"kind": "stolen_vehicle", "plate": plates[2], "severity": "high",
                                                         "source": "edge_checks", "reason": "edge check"}).json()
        watch_ids.append(w["id"])
        again = {**sight(plates[2], "GNR-POL-001"), "event_ts": datetime.now(timezone.utc).isoformat()}
        r3 = c.post(f"{API}/ingest/sightings", headers=INGEST, json=[again]).json()
        flags = sorted(a["retrospective"] for a in c.get(f"{API}/alerts", headers=hs, params={"status": "all", "limit": 1000}).json()
                       if a["plate_norm"] == plates[2])
        check("a retrospective alert does not hold back the live alert for the next pass at the same camera",
              r3.get("alerts") == 1 and flags == [False, True], f"{r3}, retrospective flags {flags}")
        al = {a["plate_norm"]: a for a in c.get(f"{API}/alerts", headers=hs, params={"status": "new", "limit": 1000}).json()}
        pol, gs = al.get(plates[0]), al.get(plates[1])
        if pol and gs:
            t = lambda a, tags, h=hs: c.put(f"{API}/alerts/{a['id']}/tags", headers=h, json={"tags": tags})  # noqa: E731
            r = t(pol, ["  Intercepted ", "intercepted", "case #4471", "અટકાવેલ"])
            check("tags are trimmed, de-duplicated and kept in Gujarati",
                  r.status_code == 200 and r.json()["tags"] == ["Intercepted", "case #4471", "અટકાવેલ"], r.text[:120])
            got = [c.get(f"{API}/alerts", headers=hs, params={"status": "all", "tag": v}).json() for v in ("INTERCEPTED", "case #4471")]
            check("tag filter matches ignoring case, and with '#' in the tag",
                  all(any(a["id"] == pol["id"] for a in x) for x in got))
            check("tag filter leaves out alerts without the tag",
                  not any(a["id"] == gs["id"] for a in got[0]))
            got = [t(pol, v).status_code for v in (["<script>"], ["x" * 33], [f"t{i}" for i in range(11)], ["a\x00b"])]
            check("bad tags are a 422", got == [422] * 4, str(got))
            r = c.put(f"{API}/alerts/{pol['id']}/tags", headers=hs, json={"tags": "not a list"})
            check("tags that are not a list are a 422", r.status_code == 422, str(r.status_code))
            check("the auditor cannot tag", t(pol, ["x"], hau).status_code == 403)
            check("a nodal officer cannot read alerts", c.get(f"{API}/alerts", headers=hn).status_code == 403)
            if hsc:
                mine = c.get(f"{API}/alerts", headers=hsc, params={"status": "all", "limit": 1000}).json()
                check("a scoped operator sees only their department's alerts",
                      any(a["id"] == gs["id"] for a in mine) and not any(a["id"] == pol["id"] for a in mine))
                got = [c.post(f"{API}/alerts/{pol['id']}/ack", headers=hsc).status_code, t(pol, ["mine"], hsc).status_code,
                       c.post(f"{API}/alerts/{pol['id']}/close", headers=hsc, json={"status": "closed"}).status_code]
                check("a scoped operator cannot act on another department's alert (404, not 403)", got == [404] * 3, str(got))
                check("a scoped operator tags their own department's alert", t(gs, ["patrol sent"], hsc).status_code == 200)
                summ = c.get(f"{API}/alerts/summary", headers=hsc).json()
                check("the scoped alert summary counts only their department", summ.get("new", 0) >= 1, str(summ))
            r = c.post(f"{API}/alerts/{pol['id']}/ack", headers=hs)
            r2 = c.post(f"{API}/alerts/{pol['id']}/ack", headers=ho)
            check("a second acknowledge is a 409 naming the state", r.status_code == 200 and r2.status_code == 409, f"{r.status_code} {r2.status_code}")
            check("the acknowledgement reaches other control rooms live",
                  live["admin"].wait_for("alert.updated", lambda e: (e.get("alert") or {}).get("id") == pol["id"]
                                         and e["alert"].get("status") == "acknowledged") is not None)
            r = c.post(f"{API}/alerts/{pol['id']}/close", headers=hs, json={"status": "closed", "disposition": "d" * 501})
            check("an over-long disposition is a 422", r.status_code == 422, str(r.status_code))
            r = c.post(f"{API}/alerts/{pol['id']}/close", headers=hs, json={"status": "deleted"})
            check("an unknown close status is a 422", r.status_code == 422, str(r.status_code))
            r = c.post(f"{API}/alerts/{pol['id']}/close", headers=hs, json={"status": "closed", "disposition": "Vehicle intercepted: edge"})
            r2 = c.post(f"{API}/alerts/{pol['id']}/close", headers=ho, json={"status": "false_positive"})
            check("closing twice is a 409; the first close stands", r.status_code == 200 and r2.status_code == 409
                  and r.json()["disposition"] == "Vehicle intercepted: edge", f"{r.status_code} {r2.status_code}")
            check("a closed alert can still be tagged", t(pol, ["closed case"]).status_code == 200)
            check("a tag change reaches other control rooms live",
                  live["admin"].wait_for("alert.updated", lambda e: (e.get("alert") or {}).get("id") == pol["id"]
                                         and e["alert"].get("tags") == ["closed case"]) is not None)
            check("an empty list clears the tags", t(pol, []).json().get("tags") == [])
            got = [c.post(f"{API}/alerts/{x}/ack", headers=hs).status_code
                   for x in ("00000000-0000-0000-0000-000000000000", "not-a-uuid")]
            check("unknown and malformed alert ids are 404 and 422", got == [404, 422], str(got))
            with cf.ThreadPoolExecutor(10) as ex:
                got = list(ex.map(lambda h: httpx.post(f"{API}/alerts/{gs['id']}/ack", headers=h, timeout=30).status_code,
                                  [hs, ho, ha] * 3 + [hs]))
            check("ten acknowledgements of one alert at once: exactly one wins, the rest are 409",
                  got.count(200) == 1 and got.count(409) == 9, str(sorted(got)))
        else:
            check("synthetic alerts listed", False, f"police={bool(pol)} gsrtc={bool(gs)}")
        for x in live.values():
            x.stopped.set()

        # ---- plate review: a mistyped reading is changed after the reveal; the first one stays the blind one
        print("-- plate review")
        review_crop.parent.mkdir(parents=True, exist_ok=True)
        review_crop.write_bytes(JPEG)
        seen_at = datetime.now(timezone.utc)
        c.post(f"{API}/ingest/sightings", headers=INGEST, json=[{
            "camera_code": "GNR-POL-001", "event_ts": seen_at.isoformat(), "plate_text": plates[3], "ocr_conf": 0.95,
            "det_conf": 0.9, "bbox": [0, 0, 40, 12], "track_id": "edge", "reads": 3,
            "crop_path": f"/crops/GNR-POL-001/{review_crop.name}"}])
        listed = c.get(f"{API}/reviews/queue", headers=ha, params={"mode": "verify", "camera": "GNR-POL-001", "limit": 200,
                                                                    "since": (seen_at - timedelta(seconds=1)).isoformat()}).json()
        sid = next((i["sighting_id"] for i in listed if i.get("plate_norm") == plates[3]), None)
        typo = plates[3][:-2] + f"{(int(plates[3][-2:]) + 55) % 100:02d}"     # both last digits differ: wrong
        first = c.post(f"{API}/reviews", headers=hau, json={"sighting_id": sid, "mode": "blind", "seen": typo}).json()
        changed = c.patch(f"{API}/reviews/{sid}", headers=hau, json={"mode": "blind", "seen": plates[3].lower()}).json()
        mine = next((x for x in c.get(f"{API}/reviews/mine", headers=hau, params={"mode": "blind", "camera": "GNR-POL-001"}).json()
                     if x["sighting_id"] == sid), {})
        check("a reviewer changes a saved reading: the first stays the blind one, the change is kept beside it and graded",
              sid is not None and first.get("verdict") == "wrong" and changed.get("verdict") == "wrong"
              and changed.get("seen") == typo and changed.get("corrected_verdict") == "exact" and bool(changed.get("corrected_at"))
              and mine.get("verdict") == "wrong" and mine.get("corrected_verdict") == "exact",
              f"first {first.get('verdict')}, change {changed.get('corrected_verdict')}")
        got = [c.patch(f"{API}/reviews/{sid}", headers=h, json={"mode": "blind", "seen": plates[3]}).status_code for h in (ha, ho)]
        back = c.patch(f"{API}/reviews/{sid}", headers=hau, json={"mode": "blind", "seen": typo}).json()
        check("nobody else changes it (404), an operator cannot (403), and the first reading again takes a change back",
              got == [404, 403] and back.get("corrected_verdict") is None and back.get("corrected_at") is None, str(got))
        # Results, plate by plate: a reviewer's own rows; everyone's on request, which spends the viewer's blind check
        win = {"camera": "GNR-POL-001", "since": (seen_at - timedelta(seconds=1)).isoformat()}
        row = lambda h, **p: [r for r in c.get(f"{API}/reviews/plates", headers=h, params={**win, **p}).json()  # noqa: E731
                              if r["sighting_id"] == sid]
        own = row(hau)
        check("Results plate by plate: the reviewer's own row, Sentinel's read beside their first reading",
              len(own) == 1 and own[0]["stored_plate"] == plates[3] and own[0]["seen"] == typo and own[0]["mine"] is True)
        queued = lambda: [i["sighting_id"] for i in c.get(f"{API}/reviews/queue", headers=hs,  # noqa: E731
                                                         params={**win, "mode": "blind"}).json()]
        before, theirs, everyone = queued(), row(hs), row(hs, scope="all")
        refused = c.post(f"{API}/reviews", headers=hs, json={"sighting_id": sid, "mode": "blind", "seen": plates[3]}).status_code
        check("everyone's rows name the reviewer; the crop then leaves the viewer's blind queue, a blind check of it refused",
              not theirs and len(everyone) == 1 and everyone[0]["reviewer"] == "auditor" and sid in before
              and sid not in queued() and refused == 409, f"blind check {refused}")

        # ---- 6. sign-in and tokens
        print("-- tokens")
        tok = ha["Authorization"].split()[1]
        h, p, s = tok.split(".")
        forged = {"Authorization": f"Bearer {h}.{p}.{s[:-4]}AAAA"}
        none_alg = {"Authorization": "Bearer eyJhbGciOiJub25lIn0." + p + "."}
        got = [c.get(f"{API}/auth/me", headers=x).status_code for x in
               ({"Authorization": "Bearer garbage"}, forged, none_alg, {"Authorization": "Basic YWRtaW46eA=="}, {})]
        check("garbage, tampered, alg=none and Basic tokens are a 401", got == [401] * 5, str(got))

        # ---- 6b. the relay: an anonymous publish from outside the loopback exemption is refused
        relay = os.environ.get("RELAY_RTSP", "127.0.0.1:8554")
        status = rtsp_announce_from("127.0.0.2", relay, f"zz_edge_publish_{suffix}")
        if status.startswith("no answer"):
            print(f"  [SKIP] anonymous publish from 127.0.0.2: {status} (no relay at {relay}, or 127.0.0.2 not loopback here)")
        else:
            check("the relay refuses an anonymous publish from outside its loopback exemption (401)", " 401 " in f"{status} ",
                  f"{relay}: {status}")

        # ---- 6c. concurrency: a burst of mixed requests, and simultaneous imports of the same cameras
        print("-- concurrency")
        reads = ["/cameras?limit=200", "/gis/cameras.geojson", "/alerts?status=all&limit=50", "/reports/fleet",
                 "/reports/gaps", "/alerts/summary", "/sightings/recent?limit=20", "/gis/districts"]
        with httpx.Client(timeout=60, limits=httpx.Limits(max_connections=64)) as c2, cf.ThreadPoolExecutor(64) as ex:
            def hit(i):
                try:
                    return c2.get(API + reads[i % len(reads)], headers=ha).status_code
                except httpx.HTTPError as e:
                    return e.__class__.__name__
            t0 = time.monotonic()
            got = list(ex.map(hit, range(300)))
            took = time.monotonic() - t0
        bad = [x for x in got if x != 200]
        check("300 requests, 64 at a time, every one answered 200", not bad,
              f"{len(bad)} not 200 {sorted(set(map(str, bad)))[:4]} ({took:.1f} s)")
        many = [f"ZZEDGE-CC-{suffix}-{i:02d}" for i in range(20)]
        csv_many = ("camera_code,name,department_code,district\n" +
                    "".join(f"{x},Concurrent {i},HOME,Gandhinagar\n" for i, x in enumerate(many))).encode()
        with cf.ThreadPoolExecutor(4) as ex:
            results = list(ex.map(lambda _: httpx.post(f"{API}/cameras/import", headers=hs, timeout=60,
                                                       files={"file": ("c.csv", csv_many, "text/csv")}), range(4)))
        errs = [e for r in results if r.status_code == 200 for e in r.json().get("errors", [])]
        listed = {x["camera_code"] for x in c.get(f"{API}/cameras", headers=hs,
                                                   params={"q": f"ZZEDGE-CC-{suffix}", "limit": 100}).json()["items"]}
        check("four imports of the same 20 new cameras at once: no errors, exactly 20 cameras",
              all(r.status_code == 200 for r in results) and not errs and listed == set(many),
              f"{[r.status_code for r in results]} errors {len(errs)} cameras {len(listed)}")
        for x in many:
            c.delete(f"{API}/cameras/{x}", headers=ha)

        # ---- 7. deletion
        print("-- deletion")
        check("a supervisor cannot delete a camera", c.delete(f"{API}/cameras/{cams[1]}", headers=hs).status_code == 403)
        got = [c.delete(f"{API}/cameras/{x}", headers=ha).status_code for x in (cams[1], cams[1])]
        check("the administrator deletes once; again is a 404", got == [204, 404], str(got))
    finally:
        for x in cams + ["ZZEDGE-GS", "ZZEDGE-GS2", "ZZEDGE-NUL", "ZZEDGE-CR", "ZZEDGE-Q1", "ZZEDGE-Q2"]:
            c.delete(f"{API}/cameras/{x}", headers=ha)
        pl = ", ".join(f"'{p}'" for p in plates)
        review_crop.unlink(missing_ok=True)
        out = psql(f"DELETE FROM alerts WHERE plate_norm IN ({pl}); DELETE FROM plate_reviews WHERE stored_plate IN ({pl}); "
                   f"DELETE FROM plate_review_shown WHERE sighting_id IN (SELECT id FROM vehicle_sightings WHERE plate_norm IN ({pl})); "
                   f"DELETE FROM sighting_quality WHERE sighting_id IN (SELECT id FROM vehicle_sightings WHERE plate_norm IN ({pl})); "
                   f"DELETE FROM vehicle_sightings WHERE plate_norm IN ({pl}); "
                   f"DELETE FROM watchlist_entries WHERE source = 'edge_checks'; "
                   f"DELETE FROM users WHERE username = '{SCOPED}'; "
                   f"DELETE FROM cameras WHERE camera_code LIKE 'ZZEDGE-%'")
        if out.startswith("psql failed"):
            print(f"  [WARN] clean-up incomplete: {out}")
    print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

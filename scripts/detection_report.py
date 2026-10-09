"""Detection report for a time window: the "output report showing detected vehicles or number
plates with corresponding timestamps" the live test case asks to accompany the screen recording.

Front page: one row per distinct plate (first and last seen, cameras in time order, reads, best
crop, vehicle type and colour, watchlist status), with plates one character apart shown together
as "possible same vehicle"; then a per-camera table, the vehicle/person counts and the intrusion
alerts (zone, what was inside, dwell: never an image). Appendix: every plate read, by camera, with
its frame time and crop.

    uv run --no-sync python scripts/detection_report.py --minutes 30
    uv run --no-sync python scripts/detection_report.py --since 2026-09-22T10:00 --until 2026-09-22T11:00 --camera GNR-POL-001 \
        --note "Cameras analysed in rotation, 4 at a time"

Writes <out>/<prefix>_<stamp>.html (prefix "detections" by default) (self-contained, crops embedded), .csv (plate reads),
_vehicles.csv (one row per plate), _counts.csv (vehicle/person counts per camera),
_intrusions.csv (intrusion alerts) and, when Chrome is available, .pdf.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import os
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from itertools import groupby
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
CLASSES = ["person", "car", "motorcycle", "bus", "truck", "bicycle"]
PAGE = 2000   # the API's row limit per /sightings request
ROW_CLASS = {"ALERT RAISED": "hit", "watchlisted": "watch"}


def parse_ts(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


def ist(ts: datetime) -> str:
    return ts.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")


def fetch_reads(c: httpx.Client, h: dict, cam: str, since: datetime, until: datetime, min_conf: float) -> list[dict]:
    """Every read of one camera in the window. The API returns the newest PAGE reads, so page back
    from the oldest read of each page; ids drop the reads that share that frame time."""
    reads, seen, upto = [], set(), until
    while True:
        params = {"since": since.isoformat(), "until": upto.isoformat(), "limit": PAGE, "min_conf": min_conf,
                  "camera": cam}
        page = c.get("/sightings", params=params, headers=h).json()
        new = [r for r in page if r["id"] not in seen]
        seen.update(r["id"] for r in new)
        reads += new
        if len(page) < PAGE or not new:
            return reads
        upto = datetime.fromisoformat(page[-1]["event_ts"])


def within_one(a: str, b: str) -> bool:
    """True when b is a with one character changed, missing or extra: the usual OCR slip."""
    if abs(len(a) - len(b)) > 1 or a == b:
        return a == b
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    i = next((k for k in range(len(a)) if a[k] != b[k]), len(a))
    return a[i:] == b[i + 1:]


def group_plates(plates: list[str]) -> list[list[str]]:
    """Plates linked by one-character differences, directly or through a chain of them.

    Two plates one character apart share a key (the plate itself or it with one character
    deleted), so only plates in the same key bucket are compared, not every pair.
    """
    parent = {p: p for p in plates}

    def find(p: str) -> str:
        while parent[p] != p:
            parent[p] = parent[parent[p]]
            p = parent[p]
        return p

    buckets: dict[str, set[str]] = defaultdict(set)
    for p in plates:
        buckets[p].add(p)
        for i in range(len(p)):
            buckets[p[:i] + p[i + 1:]].add(p)
    for members in buckets.values():
        ms = sorted(members)
        for i, a in enumerate(ms):
            for b in ms[i + 1:]:
                if within_one(a, b):
                    parent[find(a)] = find(b)
    groups: dict[str, list[str]] = defaultdict(list)
    for p in plates:
        groups[find(p)].append(p)
    return list(groups.values())


def by_frequency(values) -> list[str]:
    return [k for k, _ in Counter(v for v in values if v).most_common()]


def summarise_plates(rows: list[dict], status, alerts_of: dict) -> list[dict]:
    """One entry per distinct plate, in groups of possible same vehicle, groups in time order."""
    reads_of: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["ts"]):
        reads_of[r["plate_norm"]].append(r)
    plates = {}
    for plate, reads in reads_of.items():
        stops: dict[str, datetime] = {}
        for r in reads:
            stops.setdefault(r["camera_code"], r["ts"])
        raised = [al for r in reads for al in alerts_of.get(r["id"], ())]
        watched = any(status(r) for r in reads)
        plates[plate] = {
            "plate": plate, "reads": reads, "first": reads[0]["ts"], "last": reads[-1]["ts"],
            "stops": list(stops.items()),
            # a read with a crop first, so the table has evidence to show; earliest of equals
            "best": max(reads, key=lambda r: (bool(r["crop_path"]), r["ocr_conf"])),
            "types": by_frequency(r.get("vehicle_type") for r in reads),
            "colours": by_frequency(r.get("vehicle_color") for r in reads),
            "alerts": raised,
            "status": "ALERT RAISED" if raised else ("watchlisted" if watched else ""),
        }
    groups = [sorted(g, key=lambda p: (-len(plates[p]["reads"]), plates[p]["first"]))
              for g in group_plates(list(plates))]
    groups.sort(key=lambda g: min(plates[p]["first"] for p in g))
    out = []
    for n, g in enumerate(groups, 1):
        for p in g:
            out.append({**plates[p], "group": n, "others": [q for q in g if q != p]})
    return out


def summarise_cameras(rows: list[dict], objects: dict, requested: list[str]) -> list[dict]:
    reads_at: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        reads_at[r["camera_code"]].append(r)
    counted = {c["camera_code"]: c for c in objects["per_camera"]}
    out = []
    for code in sorted(set(reads_at) | set(counted) | set(requested)):
        reads, cnt = reads_at.get(code, []), counted.get(code)
        if reads:
            note = ""
        elif cnt and ((cnt.get("vehicle_peak") or 0) or cnt["vehicles_in_view"]):   # the average rounds to 0 when rare
            note = "no plate reads (wide view)"
        elif cnt:
            note = "no plate reads, no vehicles detected"
        else:
            note = "no data in window"
        out.append({
            "code": code,
            "name": reads[0]["camera_name"] if reads else (cnt["name"] if cnt else ""),
            "reads": len(reads),
            "plates": len({r["plate_norm"] for r in reads}),
            "typed": sum(1 for r in reads if r.get("vehicle_type")),
            "median_ocr": statistics.median(r["ocr_conf"] for r in reads) if reads else None,
            "frames": cnt["frames"] if cnt else None,
            "note": note,
        })
    return out


def vehicle_text(v: dict) -> str:
    return " ".join(x for x in (", ".join(v["colours"]), ", ".join(v["types"])) if x)


def late_text(alerts: list[dict]) -> str:
    """Alerts not raised as the read arrived: a watchlist entry added afterwards, or a read replayed
    from the worker's outage spool."""
    late = Counter("retrospective" if al.get("retrospective") else "raised on replay"
                   for al in alerts if al.get("retrospective") or (al.get("detail") or {}).get("replayed"))
    return ", ".join(f"{n} {k}" for k, n in sorted(late.items()))


def near_text(alerts: list[dict]) -> str:
    """Alerts on a watchlist plate the read differs from (the API's fuzzy match for OCR slips)."""
    near = [al for al in alerts if not al.get("exact_match", True)]
    plates = sorted({al["watch_plate"] for al in near if al.get("watch_plate")})   # older APIs omit it
    return ("near match" + (f" to {', '.join(plates)}" if plates else "")) if near else ""


def alert_text(v: dict) -> str:
    if not v["alerts"]:
        return v["status"]
    detail = sorted({f"{(al.get('kind') or 'watchlist').replace('_', ' ')} ({al['severity']})" for al in v["alerts"]})
    late, near = late_text(v["alerts"]), near_text(v["alerts"])
    return (f"ALERT RAISED ×{len(v['alerts'])}{f' ({late})' if late else ''} · {', '.join(detail)}"
            + (f" · {near}" if near else ""))


_sha: dict[str, str] = {}


def crop_sha256(path: str | None) -> str:
    """The evidence crop's SHA-256, so a reader can later check that a crop file is the one the report showed
    (an integrity check, not a signature: the report itself is not signed)."""
    if not path:
        return ""
    if path not in _sha:
        p = ROOT / "data" / path.lstrip("/")
        _sha[path] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""
    return _sha[path]


def write_reads_csv(path: str, rows: list[dict], status) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["event_time_ist", "camera_code", "camera_name", "district", "department", "lat", "lon",
                    "plate_read", "plate_normalised", "vehicle_type", "vehicle_color", "ocr_conf", "det_conf",
                    "watchlist_status", "crop_path", "crop_sha256"])
        for r in rows:
            w.writerow([ist(r["ts"]),
                        r["camera_code"], r["camera_name"], r["district"], r["department"], r["lat"], r["lon"],
                        r["plate_text"], r["plate_norm"], r.get("vehicle_type") or "", r.get("vehicle_color") or "",
                        f"{r['ocr_conf']:.2f}", f"{r['det_conf']:.2f}",
                        status(r),
                        r["crop_path"] or "", crop_sha256(r["crop_path"])])


def write_vehicles_csv(path: str, vehicles: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["group", "plate_normalised", "possible_same_vehicle_as", "first_seen_ist", "last_seen_ist",
                    "cameras_in_time_order", "camera_count", "reads", "vehicle_type", "vehicle_color",
                    "best_ocr_conf", "best_read_time_ist", "best_read_camera", "best_crop_path",
                    "watchlist_status", "alerts_raised", "watchlist_kind", "alert_severity",
                    "alerts_late", "alert_near_match"])
        for v in vehicles:
            b = v["best"]
            w.writerow([v["group"], v["plate"], " ".join(v["others"]), ist(v["first"]), ist(v["last"]),
                        " > ".join(code for code, _ in v["stops"]), len(v["stops"]), len(v["reads"]),
                        "; ".join(v["types"]), "; ".join(v["colours"]),
                        f"{b['ocr_conf']:.2f}", ist(b["ts"]), b["camera_code"], b["crop_path"] or "",
                        v["status"], len(v["alerts"]),
                        "; ".join(sorted({al["kind"] for al in v["alerts"] if al.get("kind")})),
                        "; ".join(sorted({al["severity"] for al in v["alerts"]})),
                        late_text(v["alerts"]), near_text(v["alerts"])])


def write_counts_csv(path: str, objects: dict) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["camera_code", "camera_name", "department", "frames_analysed", "last_window_ist",
                    *(f"{k}_avg_in_view" for k in CLASSES), *(f"{k}_peak" for k in CLASSES)])
        for cam in objects["per_camera"]:
            w.writerow([cam["camera_code"], cam["name"], cam["department"], cam["frames"],
                        ist(datetime.fromisoformat(cam["last_window"])),
                        *(cam["in_view"].get(k, 0) for k in CLASSES), *(cam["peak"].get(k, 0) for k in CLASSES)])


def in_zone_text(detail: dict) -> str:
    classes = detail.get("classes") or {}
    return ", ".join(f"{k} ×{n}" for k, n in sorted(classes.items(), key=lambda kv: -kv[1])) or str(detail.get("count", ""))


def status_text(al: dict) -> str:
    return al["status"] + (f" ({al['disposition']})" if al.get("disposition") else "")


def write_intrusions_csv(path: str, events: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["event_time_ist", "camera_code", "camera_name", "zone_id", "zone_name", "in_zone", "peak_count",
                    "first_seen_ist", "dwell_s", "severity", "status", "alert_raised_ist"])
        for al in events:
            d = al.get("detail") or {}
            first = d.get("first_seen")
            w.writerow([ist(al["ts"]), al["camera_code"], al["camera_name"], d.get("zone", ""), d.get("zone_name", ""),
                        in_zone_text(d), d.get("count", ""), ist(datetime.fromisoformat(first)) if first else "",
                        d.get("dwell_s", ""), al["severity"], status_text(al),
                        ist(datetime.fromisoformat(al["triggered_at"]))])


def intrusions_html(events: list[dict], when) -> str:
    if not events:
        return ("<section><h2>Intrusion alerts</h2><p class='muted'>No intrusion alerts in this window.</p></section>")
    def row(al: dict) -> str:
        d = al.get("detail") or {}
        first = d.get("first_seen")
        return (f"<tr><td>{when(al['ts'])}</td><td class='mono'>{html.escape(al['camera_code'])}</td>"
                f"<td>{html.escape(d.get('zone_name') or d.get('zone') or '')} <span class='muted'>{html.escape(d.get('zone', ''))}</span></td>"
                f"<td>{html.escape(in_zone_text(d))}</td><td>{when(datetime.fromisoformat(first)) if first else '—'}</td>"
                f"<td>{d.get('dwell_s', '—')} s</td><td>{html.escape(al['severity'])}</td><td>{html.escape(status_text(al))}</td></tr>")
    return (
        "<section><h2>Intrusion alerts <span>zones drawn on the camera's picture, same window</span></h2>"
        "<p class='muted'>An intrusion alert is raised when people or vehicles of a zone's watched classes stay inside "
        "the zone, while it is armed, for its minimum dwell time. It records the zone, which classes and how many were "
        "inside, when the first was seen inside and the dwell that triggered it: no image, box or track of anyone. At "
        "most one alert per zone per camera per 120 s, as for watchlist alerts. Times are frame times from the stream.</p>"
        "<table><thead><tr><th>Frame time</th><th>Camera</th><th>Zone</th><th>In the zone (peak)</th><th>First inside</th>"
        "<th>Dwell</th><th>Severity</th><th>Status</th></tr></thead>"
        f"<tbody>{''.join(row(al) for al in events)}</tbody></table></section>")


def vehicles_html(vehicles: list[dict], when, crop_img) -> str:
    if not vehicles:
        return "<section><h2>Vehicles</h2><p>No plate reads in this window.</p></section>"
    bodies = []
    for _, grp in groupby(vehicles, key=lambda v: v["group"]):
        g = list(grp)
        trs = "".join(
            f"<tr class='{'hit' if v['alerts'] else ('watch' if v['status'] else '')}'>"
            f"<td class='mono'>{html.escape(v['plate'])}</td><td>{when(v['first'])}</td><td>{when(v['last'])}</td>"
            f"<td>{' → '.join(f'<span class=stop>{html.escape(c)} <span class=muted>{when(ts)}</span></span>' for c, ts in v['stops'])}</td>"
            f"<td>{len(v['reads'])}</td><td>{html.escape(vehicle_text(v)) or '—'}</td>"
            f"<td>{html.escape(alert_text(v))}</td>"
            f"<td class='best'>{crop_img(v['best']['crop_path'])} <span class='muted'>{v['best']['ocr_conf']:.2f}</span></td></tr>"
            for v in g)
        if len(g) > 1:
            label = (f"<tr class='glabel'><td colspan='8'>Possible same vehicle · {len(g)} plates one character "
                     f"apart · {sum(len(v['reads']) for v in g)} reads · shown separately, not merged</td></tr>")
            bodies.append(f"<tbody class='grp'>{label}{trs}</tbody>")
        else:
            bodies.append(f"<tbody>{trs}</tbody>")
    return (
        "<section><h2>Vehicles <span>one row per distinct plate, in order of first read</span></h2>"
        "<p class='muted'>A row is a plate as stored (normalised), not a verified vehicle: a misread can produce "
        "a plate no vehicle carries. A read is one stored sighting, one pass of the plate through one camera's "
        "view, however many frames read it. Plates one character apart (one character different, missing or "
        "extra, or linked through a chain of such plates) are grouped as <i>possible same vehicle</i>: each "
        "keeps its own row and reads, nothing is merged or corrected; within a group the most-read plate comes "
        "first. Cameras are listed in order of the plate's first read at each. Vehicle type and colour are "
        "shown where attributed, most frequent first. Best read is the crop with the highest OCR confidence. "
        "OCR confidence is the stored value: the best frame's score, raised to at least 0.90 when three or more "
        "frames agree on every character, so it ranks reads and is not a measured accuracy. A <i>near "
        "match</i> alert matched a watchlist plate that differs from the read by a character (the fuzzy match "
        "that allows for OCR slips).</p>"
        "<table class='veh'><thead><tr><th>Plate</th><th>First seen</th><th>Last seen</th><th>Cameras, time order</th>"
        "<th>Reads</th><th>Vehicle</th><th>Watchlist</th><th>Best read (OCR conf)</th></tr></thead>"
        f"{''.join(bodies)}</table></section>")


def cameras_html(cams: list[dict]) -> str:
    if not cams:
        return ""
    def row(c: dict) -> str:
        typed = f"{100 * c['typed'] / c['reads']:.0f}%" if c["reads"] else "—"
        ocr = f"{c['median_ocr']:.2f}" if c["median_ocr"] is not None else "—"
        frames = f"{c['frames']:,}" if c["frames"] is not None else "—"
        return (f"<tr><td class='mono'>{html.escape(c['code'])}</td><td>{html.escape(c['name'])}</td>"
                f"<td>{c['reads']:,}</td><td>{c['plates']:,}</td><td>{typed}</td><td>{ocr}</td><td>{frames}</td>"
                f"<td class='muted'>{html.escape(c['note'])}</td></tr>")
    trs = "".join(row(c) for c in cams)
    return (
        "<section><h2>Cameras <span>same window</span></h2>"
        "<p class='muted'>Frames analysed comes from the per-minute vehicle and person count rows (— where the "
        "camera wrote none, e.g. plate-only analytics). Median OCR confidence is over the stored values described "
        "under Vehicles. <i>Wide view</i>: vehicles were detected but no plate was read, which usually means plates "
        "are too small or too oblique in that view to read.</p>"
        "<table><thead><tr><th>Camera</th><th>Name</th><th>Plate reads</th><th>Distinct plates</th>"
        "<th>Reads with vehicle type</th><th>Median OCR conf</th><th>Frames analysed</th><th>Note</th></tr></thead>"
        f"<tbody>{trs}</tbody></table></section>")


def counts_html(objects: dict) -> str:
    if not objects["per_camera"]:
        return "<section><h2>Vehicle and person detection</h2><p class='muted'>No object analytics in this window.</p></section>"
    rows = "".join(
        f"<tr><td class='mono'>{html.escape(cam['camera_code'])}</td><td>{html.escape(cam['name'])}</td>"
        f"<td>{cam['frames']:,}</td><td>{cam['vehicles_in_view']} <span class='muted'>/ {cam['vehicle_peak']}</span></td>"
        f"<td>{cam['in_view'].get('person', 0)} <span class='muted'>/ {cam['peak'].get('person', 0)}</span></td>"
        + "".join(f"<td>{cam['in_view'].get(k, 0)}</td>" for k in CLASSES[1:])
        + f"<td>{datetime.fromisoformat(cam['last_window']).astimezone(IST):%H:%M:%S}</td></tr>"
        for cam in objects["per_camera"])
    return (
        "<section><h2>Vehicle and person detection <span>per camera, same window</span></h2>"
        "<p class='muted'>Average number in view per analysed frame / most seen in any single frame. A detection is a "
        "box in one frame, not a unique vehicle or person: nothing is tracked or identified, and people are counted "
        "only. Vehicle type is the COCO class of the box the plate sits in; colour is a heuristic over its body "
        "panels and is left blank when unsure, on IR frames and on two-wheelers.</p>"
        "<table><thead><tr><th>Camera</th><th>Name</th><th>Frames analysed</th><th>Vehicles avg / peak</th>"
        "<th>People avg / peak</th>" + "".join(f"<th>{k} avg</th>" for k in CLASSES[1:]) +
        f"<th>Last window</th></tr></thead><tbody>{rows}</tbody></table></section>")


def reads_html(rows: list[dict], status, when, crop_img, crops: bool) -> str:
    by_cam: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cam[r["camera_code"]].append(r)
    sections = []
    for cam, items in by_cam.items():
        first = items[0]
        where = f"{first['lat']:.5f}, {first['lon']:.5f}" if first["lat"] is not None else "no coordinates"
        trs = "".join(
            f"<tr class='{ROW_CLASS.get(status(r), '')}'><td>{when(r['ts'])}</td>"
            f"<td class='mono'>{html.escape(r['plate_norm'])}</td><td class='mono muted'>{html.escape(r['plate_text'])}</td>"
            f"<td>{html.escape(' '.join(x for x in (r.get('vehicle_color'), r.get('vehicle_type')) if x) or '—')}</td>"
            f"<td>{r['ocr_conf']:.2f}</td><td>{r['det_conf']:.2f}</td>"
            f"<td>{status(r)}</td><td>{crop_img(r['crop_path'])}"
            + (f"<div class='mono muted' title='SHA-256 of the crop file, in full in the CSV'>sha256 {crop_sha256(r['crop_path'])[:16]}…</div>"
               if crops and r["crop_path"] else "") + "</td></tr>"
            for r in items)
        sections.append(
            f"<section><h3>{html.escape(cam)} <span>{html.escape(first['camera_name'])}</span></h3>"
            f"<p class='muted'>{html.escape(first['district'] or '')} · {html.escape(first['department'])} · "
            f"{where} · {len(items)} reads</p>"
            f"<table><thead><tr><th>Frame time (IST)</th><th>Plate</th><th>Text sent</th><th>Vehicle</th><th>OCR conf</th>"
            f"<th>Det conf</th><th>Watchlist</th><th>Evidence</th></tr></thead><tbody>{trs}</tbody></table></section>")
    evidence = ("the evidence crop" if crops else
                "no crops (left out with --no-read-crops; each plate's best crop is in the Vehicles table)")
    return (
        "<section class='appendix'><h2>Appendix A · Every plate read <span>by camera, in time order</span></h2>"
        "<p class='muted'>The reads behind the Vehicles table: one row per stored plate read, with the frame time "
        "from the stream, the plate after normalisation, the text the analytics worker sent before it, and "
        f"{evidence}. Each crop's SHA-256 (in full in the reads CSV) lets a reader check later that a crop file is "
        "the one shown here; the report itself is not signed.</p>"
        f"{''.join(sections) or '<p>No plate reads in this window.</p>'}</section>")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=os.environ.get("API", "http://localhost:8000"))
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD", "admin123"))
    ap.add_argument("--minutes", type=int, default=60, help="window ending now (ignored with --since)")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--camera", action="append", help="repeatable; default all cameras")
    ap.add_argument("--min-conf", type=float, default=0.0)
    ap.add_argument("--title", default="Detected vehicles and number plates")
    ap.add_argument("--note", action="append", default=[],
                    help='repeatable; printed under the title, e.g. "Cameras analysed in rotation"')
    ap.add_argument("--read-crops", action=argparse.BooleanOptionalAction, default=True,
                    help="embed a crop on every appendix read (--no-read-crops keeps only each plate's best crop)")
    ap.add_argument("--out", default=str(ROOT / "submission/out"))
    ap.add_argument("--prefix", default="detections", help='file name prefix, e.g. "gov_detections" for the government-feed run')
    a = ap.parse_args()
    requested = [c.upper() for c in a.camera or []]

    until = parse_ts(a.until) if a.until else datetime.now(timezone.utc)
    since = parse_ts(a.since) if a.since else until - timedelta(minutes=a.minutes)

    with httpx.Client(base_url=a.api, timeout=60) as c:
        tok = c.post("/auth/login", json={"username": a.user, "password": a.password}).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        rows = []
        # One camera at a time, paged: a single request stops at the API's row limit, which a busy
        # hour on ~50 cameras exceeds.
        cams = requested or [x["camera_code"] for x in c.get("/cameras", params={"limit": 2000}, headers=h).json()["items"]]
        for cam in cams:
            rows += fetch_reads(c, h, cam, since, until, a.min_conf)
        alerts = c.get("/alerts", params={"status": "all", "limit": 1000}, headers=h).json()
        objects = c.get("/reports/objects", params={"since": since.isoformat(), "until": until.isoformat()},
                        headers=h).json()
        if requested:
            objects["per_camera"] = [x for x in objects["per_camera"] if x["camera_code"] in requested]
            objects["frames"] = sum(x["frames"] or 0 for x in objects["per_camera"])

    notes = list(a.note)
    # /alerts has no time filter and returns the newest 1000: past that, older windows lose alerts.
    if len(alerts) >= 1000 and min(datetime.fromisoformat(al["triggered_at"]) for al in alerts) > since:
        notes.append("Watchlist status may be incomplete: only the newest 1000 alerts could be fetched, "
                     "and alerts raised before the oldest of them are not shown.")
        print("  warning: " + notes[-1])

    for r in rows:
        r["ts"] = datetime.fromisoformat(r["event_ts"])
    rows.sort(key=lambda r: (r["camera_code"], r["ts"], r["id"]))   # id: reads can share a frame time
    in_window = [al for al in alerts   # plate alerts only: an intrusion alert has no sighting
                 if al.get("sighting_id") and since <= datetime.fromisoformat(al["sighting_ts"]) <= until]
    alerts_of: dict[int, list[dict]] = defaultdict(list)   # the exact sighting that raised each alert
    for al in in_window:
        alerts_of[al["sighting_id"]].append(al)
    alert_keys = {(al["camera_code"], al["plate_norm"]) for al in in_window}   # plates watchlisted on this camera

    def status(r: dict) -> str:
        if r["id"] in alerts_of:
            return "ALERT RAISED"
        return "watchlisted" if (r["camera_code"], r["plate_norm"]) in alert_keys else ""

    vehicles = summarise_plates(rows, status, alerts_of)
    cameras = summarise_cameras(rows, objects, requested)
    intrusions = []
    for al in alerts:
        if al.get("alert_type") == "intrusion" and al.get("sighting_ts") and (
                not requested or al["camera_code"] in requested):
            al["ts"] = datetime.fromisoformat(al["sighting_ts"])
            if since <= al["ts"] <= until:
                intrusions.append(al)
    intrusions.sort(key=lambda al: al["ts"])

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    base = out / f"{a.prefix}_{stamp}"
    write_reads_csv(f"{base}.csv", rows, status)
    write_vehicles_csv(f"{base}_vehicles.csv", vehicles)
    write_counts_csv(f"{base}_counts.csv", objects)
    write_intrusions_csv(f"{base}_intrusions.csv", intrusions)

    embedded: dict[str, str] = {}

    def crop_img(path: str | None) -> str:
        if not path:
            return ""
        if path not in embedded:
            p = ROOT / "data" / path.lstrip("/")
            embedded[path] = (f'<img src="data:image/jpeg;base64,{base64.b64encode(p.read_bytes()).decode()}">'
                              if p.exists() else "")
        return embedded[path]

    one_day = since.astimezone(IST).date() == until.astimezone(IST).date()
    when = lambda ts: ts.astimezone(IST).strftime("%H:%M:%S" if one_day else "%d %b %H:%M:%S")  # noqa: E731
    read_crop = crop_img if a.read_crops else (lambda path: "")
    groups = Counter(v["group"] for v in vehicles)
    shared = [n for n, k in groups.items() if k > 1]
    typed = sum(1 for r in rows if r.get("vehicle_type"))
    raised = sum(len(alerts_of.get(r["id"], ())) for r in rows)
    note_html = "".join(f"<div class='note'>{html.escape(n)}</div>" for n in notes)

    doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(a.title)}</title>
<style>
@page {{ size: A4; margin: 14mm 12mm 16mm; }}
body {{ font: 11px/1.4 "Segoe UI", Arial, sans-serif; color: #0f172a; margin: 0; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }} h2 {{ font-size: 14px; margin: 18px 0 2px; }} h3 {{ font-size: 12.5px; margin: 14px 0 2px; }}
h2 span, h3 span {{ font-weight: 400; color: #475569; }}
.muted {{ color: #64748b; }} .mono {{ font-family: Consolas, monospace; font-weight: 700; }} td.mono {{ white-space: nowrap; }}
.note {{ border-left: 3px solid #d97706; background: #fffbeb; padding: 4px 8px; margin: 6px 0 0; }}
.summary {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 6px; }} .summary div {{ background: #f1f5f9; border-radius: 6px; padding: 6px 10px; }}
.summary b {{ display: block; font-size: 16px; }}
table {{ width: 100%; border-collapse: collapse; }} th, td {{ text-align: left; padding: 3px 6px; border-bottom: 1px solid #e2e8f0; vertical-align: middle; }}
th {{ font-size: 9.5px; text-transform: uppercase; color: #64748b; }} tr {{ page-break-inside: avoid; }}
tr.hit td {{ background: #fee2e2; font-weight: 700; }} tr.watch td {{ background: #fff7ed; }} td img {{ height: 26px; border-radius: 3px; }}
table.veh td {{ font-size: 10.5px; }} .stop {{ white-space: nowrap; }} td.best {{ white-space: nowrap; }}
tbody.grp {{ break-inside: avoid; }} tbody.grp td:first-child {{ border-left: 3px solid #6366f1; }}
tr.glabel td {{ background: #eef2ff; color: #4338ca; font-size: 9.5px; padding: 2px 6px; }}
section {{ page-break-inside: auto; }} section.appendix {{ break-before: page; }}
</style></head><body>
<h1>{html.escape(a.title)}</h1>
<div class="muted">Sentinel · window {since.astimezone(IST):%d %b %Y %H:%M:%S} – {until.astimezone(IST):{'%H:%M:%S' if one_day else '%d %b %Y %H:%M:%S'}} IST ·
generated {datetime.now(IST):%d %b %Y %H:%M:%S} IST · times are frame timestamps from the stream</div>
{note_html}
<div class="summary"><div><b>{len(rows)}</b>plate reads</div><div><b>{len(vehicles)}</b>distinct plates</div>
<div><b>{len(shared)}</b>possible-same-vehicle groups <span class="muted">({sum(groups[n] for n in shared)} plates)</span></div>
<div><b>{sum(1 for c in cameras if c['reads'])}</b>cameras with reads</div><div><b>{raised}</b>watchlist alerts raised</div>
<div><b>{sum(1 for r in rows if status(r))}</b>reads of watchlisted plates</div>
<div><b>{typed}</b>reads with vehicle type</div><div><b>{objects["frames"]:,}</b>frames analysed for objects</div>
<div><b>{len(intrusions)}</b>intrusion alerts</div></div>
<div class="muted">An alert is raised once per watchlist entry per camera per 120 s; further reads of the same plate are marked "watchlisted".</div>
{vehicles_html(vehicles, when, crop_img)}
{cameras_html(cameras)}
{counts_html(objects)}
{intrusions_html(intrusions, when)}
{reads_html(rows, status, when, read_crop, a.read_crops)}
</body></html>"""
    Path(f"{base}.html").write_text(doc, encoding="utf-8")
    print(f"{len(rows)} reads, {len(vehicles)} plates in {len(groups)} groups "
          f"({len(shared)} of possible same vehicle), {sum(1 for c in cameras if c['reads'])} cameras with reads")
    print(f"{len(objects['per_camera'])} cameras with object counts, {typed} reads with vehicle type, "
          f"{len(intrusions)} intrusion alerts")
    print("wrote", f"{base}.html", f"{base}.csv", f"{base}_vehicles.csv", f"{base}_counts.csv",
          f"{base}_intrusions.csv", sep="\n  ")

    render = ROOT / "submission/build/render.mjs"
    if render.exists():
        r = subprocess.run(["node", str(render), "pdf", f"{base}.html", f"{base}.pdf"], capture_output=True, text=True)
        print("  " + (f"{base}.pdf" if r.returncode == 0 else f"(pdf skipped: {r.stderr.strip()[:200]})"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

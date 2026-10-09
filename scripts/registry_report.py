"""Model 1 deliverables as files: the camera-metadata dataset, a gap-analysis report,
and the registry API documentation.

The portal lists these under Model 1's "expected deliverables"; this turns what the
platform already shows on screen into artefacts that can be attached to a submission.

    uv run --no-sync python scripts/registry_report.py

Writes into submission/out/:
    registry-cameras.csv          sample onboarded camera-metadata dataset
    registry-gap-analysis.{html,pdf,csv}   uncovered districts, ANPR gaps, uptime
    registry-api.json             OpenAPI description of the registry and platform API
    registry-api.md               one-line-per-endpoint summary of the same
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))


AREAS = [  # OpenAPI tag -> what a reader looks for
    ("cameras", "Registry: cameras (Model 1)"), ("zones", "Registry: intrusion zones"), ("gis", "GIS: map layers"),
    ("onboarding", "Onboarding by stream URL"), ("reports", "Reports and audit"), ("sightings", "Plate sightings and movement"),
    ("watchlist", "Watchlist"), ("alerts", "Alerts"), ("evidence", "Evidence"), ("auth", "Sign-in"),
    ("ingest", "Analytics workers (ingest key, not user tokens)"), ("meta", "Service"),
]

# One line for endpoints whose code has no docstring (a reader should not see "List Cameras").
DESCRIBE = {
    ("GET", "/alerts"): "Alerts in the caller's scope, newest first; unacknowledged ones in priority order (severity, then time)",
    ("GET", "/alerts/summary"): "Counts of unacknowledged, acknowledged and last-24-hour alerts",
    ("POST", "/alerts/{alert_id}/ack"): "Acknowledge an alert (audited)",
    ("POST", "/alerts/{alert_id}/close"): "Close an alert or mark it a false positive, with a disposition (audited)",
    ("GET", "/audit"): "The append-only audit trail, filterable by action (auditor, supervisor, admin)",
    ("POST", "/auth/login"): "Sign in with username and password; returns a bearer token and the user's role and permissions",
    ("GET", "/auth/me"): "The signed-in user, role and scope",
    ("GET", "/cameras"): "Search the registry: text, department, district, health, ANPR suitability; paged",
    ("POST", "/cameras"): "Register one camera (manual entry); department-scoped users only in their own department",
    ("GET", "/cameras/export.csv"): "The registry as CSV (the Model 1 sample dataset)",
    ("GET", "/cameras/template.csv"): "The bulk-import CSV template with every column",
    ("GET", "/cameras/{code}"): "One camera's registry record",
    ("PATCH", "/cameras/{code}"): "Update a camera's metadata or analytics setting (audited)",
    ("DELETE", "/cameras/{code}"): "Remove a camera from the registry (administrators)",
    ("GET", "/cameras/{code}/health"): "A camera's health-check history",
    ("GET", "/cameras/{code}/zones"): "A camera's intrusion zones",
    ("PUT", "/cameras/{code}/zones"): "Replace a camera's intrusion zones (polygons, classes, dwell, armed hours; audited)",
    ("GET", "/gis/districts"): "Coverage per district: cameras, online, ANPR, departments, uptime",
    ("GET", "/healthz"): "Liveness and fleet summary",
    ("POST", "/ingest/sightings"): "Plate sightings from a worker; each is matched against the watchlist and may raise an alert",
    ("POST", "/onboard/probe"): "Probe a stream URL without registering it: codec, resolution, time to first frame",
    ("POST", "/onboard/stream"): "Onboard a camera from a stream URL: probe, relay, register (credentials stay server-side)",
    ("DELETE", "/onboard/stream/{code}"): "Remove a camera's relay",
    ("GET", "/reports/departments"): "Per-department inventory: cameras, online, ANPR, districts, vendors, retention",
    ("GET", "/reports/fleet"): "Fleet totals by health, ANPR suitability and analytics",
    ("GET", "/reports/uptime"): "Per-camera uptime over a window",
    ("GET", "/sightings"): "Plate sightings by plate (substring), camera and time window (plate searches are audited)",
    ("GET", "/sightings/recent"): "The latest plate sightings",
    ("GET", "/sightings/stats"): "Sightings, distinct plates and busiest cameras over a window",
    ("GET", "/watchlist"): "Active watchlist entries, filterable by kind and plate or name",
    ("POST", "/watchlist"): "Add a watchlist entry; the reply says whether the plate was already seen in the last 24 h",
    ("GET", "/watchlist/sources"): "Government-database adapters and their status (mock, awaiting access)",
    ("DELETE", "/watchlist/{entry_id}"): "Deactivate a watchlist entry (audited)",
}

EXAMPLES = """## Examples

Sign in, then send the token as `Authorization: Bearer <token>` (all endpoints except sign-in, `/healthz` and `/ingest/*`).

```
POST /auth/login            {"username": "admin", "password": "..."}   -> {"access_token": "...", "user": {...}}
GET  /cameras?department=GSRTC&health=online&limit=100               -> {"total": 2, "items": [{camera_code, name, department_code, district, lat, lon, codec, resolution, health, anpr_viable, ...}]}
POST /cameras/sync-catalogue?url=http://<host>/api/ingest&dry_run=true -> {"rows": [{camera_code, department_code, district, lat, lon, coord_source, warnings}], ...}  (nothing written)
POST /cameras/import         multipart CSV (template: GET /cameras/template.csv) -> {"inserted": n, "updated": n, "errors": [{line, camera_code, error}]}
GET  /gis/clusters?zoom=7    -> {"total": 80000, "clusters": [{lat, lon, cameras, online, offline, anpr}]}   (state view)
GET  /gis/cameras.geojson?bbox=72.50,22.98,72.62,23.08 -> GeoJSON FeatureCollection of the cameras in view
GET  /reports/gaps           -> {"districts": [...], "findings": [{district, finding, severity}]}
GET  /sightings/movement/GJ01AB1234?purpose=FIR%20123 -> {"timeline": [...], "visits": [{n, camera_code, first_ts, last_ts, hop: {distance_m, travel_s, speed_kmh, implausible}}], "route": {...}}
```

Scope: a department or district officer sees and writes only their own cameras (enforced in the query layer and on
write paths). Every plate search and movement query is written to the audit trail with its stated purpose.
"""


def api_markdown(openapi: dict, stamp) -> str:
    by_tag: dict[str, list[str]] = {}
    for path, ops in sorted(openapi["paths"].items()):
        for method, op in ops.items():
            if method not in ("get", "post", "patch", "delete", "put"):
                continue
            desc = (op.get("description") or "").strip().split("\n\n")[0].replace("\n", " ")
            what = DESCRIBE.get((method.upper(), path)) or (desc.split(". ")[0].rstrip(".") if desc else op.get("summary", "").strip())
            auth = "ingest key" if path.startswith("/ingest") else ("public" if path in ("/auth/login", "/auth/token", "/healthz") else "token")
            tag = (op.get("tags") or ["meta"])[0]
            by_tag.setdefault(tag, []).append(f"| {method.upper()} | `{path}` | {what or '—'} | {auth} |")
    out = [f"# {openapi['info']['title']}: API reference\n",
           f"Version {openapi['info'].get('version', '')} · generated {stamp:%d %b %Y %H:%M} IST from the running API. "
           "The full machine-readable contract (every parameter and schema) is `registry-api.json` (OpenAPI 3); "
           "a running instance also serves it interactively at `/docs`.\n", EXAMPLES]
    known = [t for t, _ in AREAS]
    for tag, title in AREAS + [(t, t) for t in sorted(by_tag) if t not in known]:
        if tag in by_tag:
            out += [f"## {title}\n", "| Method | Path | What it does | Auth |", "|---|---|---|---|", *by_tag[tag], ""]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=os.environ.get("API", "http://localhost:8000"))
    ap.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD", "admin123"))
    ap.add_argument("--out", default=str(ROOT / "submission/out"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=a.api, timeout=60) as c:
        tok = c.post("/auth/login", json={"username": "admin", "password": a.password}).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        cameras_csv = c.get("/cameras/export.csv", headers=h).text
        gaps = c.get("/reports/gaps", headers=h).json()
        fleet = c.get("/reports/fleet", headers=h).json()
        depts = c.get("/reports/departments", headers=h).json()
        uptime = c.get("/reports/uptime", params={"hours": 24}, headers=h).json()
        openapi = c.get("/openapi.json").json()

    (out / "registry-cameras.csv").write_text(cameras_csv, encoding="utf-8")
    n_cams = max(0, len(cameras_csv.strip().splitlines()) - 1)

    # ---- gap analysis, as a report rather than a screen
    with open(out / "registry-gap-analysis.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["district", "total_cameras", "online", "offline", "anpr_viable", "departments_present",
                    "uptime_pct", "finding"])
        by_district = {d["district"]: d for d in gaps["districts"]}
        findings: dict[str, list[str]] = {}
        for fi in gaps["findings"]:
            findings.setdefault(fi["district"], []).append(f"{fi['severity']}: {fi['finding']}")
        for name, d in sorted(by_district.items()):
            w.writerow([name, d["total_cameras"], d["online_cameras"], d["offline_cameras"], d["anpr_cameras"],
                        d["departments_present"], d["uptime_pct"] or "", "; ".join(findings.get(name, []))])

    stamp = datetime.now(IST)
    sev_colour = {"high": "#dc2626", "medium": "#b45309"}
    rows = "".join(
        f"<tr class='{'gap' if not d['total_cameras'] else ''}'><td>{html.escape(d['district'])}</td>"
        f"<td class='n'>{d['total_cameras']}</td><td class='n'>{d['online_cameras']}</td>"
        f"<td class='n'>{d['offline_cameras']}</td><td class='n'>{d['anpr_cameras']}</td>"
        f"<td class='n'>{d['departments_present']}</td><td class='n'>{d['uptime_pct'] if d['uptime_pct'] is not None else '—'}</td></tr>"
        for d in sorted(gaps["districts"], key=lambda x: (-x["total_cameras"], x["district"])))
    find_rows = "".join(
        f"<li><b style='color:{sev_colour.get(f['severity'], '#334155')}'>{html.escape(f['severity'].upper())}</b> "
        f"{html.escape(f['district'])} — {html.escape(f['finding'])}</li>" for f in gaps["findings"])
    dept_rows = "".join(
        f"<tr><td>{html.escape(d['code'])}</td><td>{html.escape(d['name'])}</td><td class='n'>{d['cameras']}</td>"
        f"<td class='n'>{d['online']}</td><td class='n'>{d['anpr_viable']}</td><td class='n'>{d['districts']}</td>"
        f"<td class='n'>{d['vendors']}</td><td>{d['min_retention'] or '—'}–{d['max_retention'] or '—'} d</td></tr>"
        for d in depts if d["cameras"])
    up_rows = "".join(
        f"<tr><td>{html.escape(u['camera_code'])}</td><td>{html.escape(u['name'])}</td>"
        f"<td>{html.escape(u['department_code'])}</td><td class='n'>{u['checks']}</td>"
        f"<td class='n'>{u['uptime_pct'] if u['uptime_pct'] is not None else '—'}</td>"
        f"<td class='n'>{u['avg_latency_ms'] or '—'}</td></tr>" for u in uptime[:40])

    doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>Sentinel — CCTV registry gap analysis</title>
<style>
@page {{ size: A4; margin: 15mm 13mm 16mm; }}
body {{ font: 11px/1.45 "Segoe UI", Arial, sans-serif; color: #0f172a; margin: 0; }}
h1 {{ font-size: 21px; margin: 0 0 3px; }} h2 {{ font-size: 14px; margin: 20px 0 6px; }}
.muted {{ color: #64748b; }}
.summary {{ display: flex; gap: 10px; margin: 12px 0; flex-wrap: wrap; }}
.summary div {{ background: #f1f5f9; border-radius: 6px; padding: 7px 12px; }} .summary b {{ display: block; font-size: 17px; }}
table {{ width: 100%; border-collapse: collapse; page-break-inside: auto; }}
th {{ background: #0f172a; color: #fff; text-align: left; font-size: 9.5px; text-transform: uppercase; padding: 4px 6px; }}
td {{ padding: 3px 6px; border-bottom: 1px solid #e2e8f0; }} td.n {{ text-align: right; }}
tr {{ page-break-inside: avoid; }} tr.gap td {{ background: #fef2f2; }}
ul {{ padding-left: 18px; }} li {{ margin: 2px 0; }}
</style></head><body>
<h1>CCTV registry — coverage and gap analysis</h1>
<div class="muted">Sentinel · generated {stamp:%d %b %Y %H:%M} IST · Model 1 deliverable: sample gap-analysis report</div>
<div class="summary">
<div><b>{fleet['cameras']}</b>cameras registered</div><div><b>{fleet['online']}</b>online</div>
<div><b>{fleet['offline']}</b>offline</div><div><b>{fleet['anpr_viable']}</b>ANPR-viable</div>
<div><b>{fleet['departments']}</b>departments</div><div><b>{fleet['districts']}</b>districts covered</div>
<div><b>{fleet['ungeocoded']}</b>without a location</div></div>
<h2>Findings ({len(gaps['findings'])})</h2><ul>{find_rows or '<li>No findings.</li>'}</ul>
<h2>District coverage</h2>
<table><thead><tr><th>District</th><th>Cameras</th><th>Online</th><th>Offline</th><th>ANPR-viable</th>
<th>Departments</th><th>Uptime %</th></tr></thead><tbody>{rows}</tbody></table>
<h2>By department</h2>
<table><thead><tr><th>Code</th><th>Department</th><th>Cameras</th><th>Online</th><th>ANPR</th><th>Districts</th>
<th>Vendors</th><th>Retention</th></tr></thead><tbody>{dept_rows}</tbody></table>
<h2>Camera uptime (last 24 h, worst first)</h2>
<table><thead><tr><th>Camera</th><th>Name</th><th>Dept</th><th>Checks</th><th>Uptime %</th><th>Latency ms</th></tr></thead>
<tbody>{up_rows}</tbody></table>
</body></html>"""
    (out / "registry-gap-analysis.html").write_text(doc, encoding="utf-8")

    # ---- registry API documentation
    (out / "registry-api.json").write_text(json.dumps(openapi, indent=2), encoding="utf-8")
    (out / "registry-api.md").write_text(api_markdown(openapi, stamp), encoding="utf-8")
    render = ROOT / "submission/build/render.mjs"
    pdf = out / "registry-gap-analysis.pdf"
    if render.exists():
        r = subprocess.run(["node", str(render), "pdf", str(out / "registry-gap-analysis.html"), str(pdf)],
                           capture_output=True, text=True)
        if r.returncode:
            print("  (pdf skipped:", r.stderr.strip()[:160], ")")
    print(f"{n_cams} cameras · {len(gaps['findings'])} gap findings · {len(openapi['paths'])} API paths")
    for f in ("registry-cameras.csv", "registry-gap-analysis.html", "registry-gap-analysis.csv",
              "registry-gap-analysis.pdf", "registry-api.json", "registry-api.md"):
        p = out / f
        if p.exists():
            print(f"  {p}  ({p.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

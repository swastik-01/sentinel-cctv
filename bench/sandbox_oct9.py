"""The organisers' sandbox, reconnected on 9 Oct 2026 through Sentinel's own onboarding: what onboarded, what the video
wall shows, and what the two workers stored in their window. Counts, times and codecs only: no plate text, no stream
address and no credential (the audit log keeps the login name inside the masked address; it is not copied here).

    uv run --no-sync python bench/sandbox_oct9.py --since 2026-10-09T08:00+05:30 --until 2026-10-09T08:31+05:30 \\
        --workers-from 2026-10-09T08:15+05:30 [--wall]

--wall runs submission/build/wall_probe.mjs over the sandbox cameras four at a time, with a pause between batches so
the organisers' server never sees more than a handful of new sessions at once.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import statistics
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
SANDBOX = r"^CAM[0-9]{2}$"


def dsn() -> str:
    env = {k.strip(): v.strip() for k, v in (l.split("=", 1) for l in (ROOT / ".env").read_text(encoding="utf-8").splitlines()
                                              if "=" in l and not l.lstrip().startswith("#"))}
    url = os.environ.get("DATABASE_URL") or env.get("DATABASE_URL") or (
        f"postgresql://sentinel:{env.get('POSTGRES_PASSWORD', '')}@127.0.0.1:5432/sentinel")
    return url.replace("postgresql+asyncpg://", "postgresql://")       # as the API's settings do


async def gather(since: datetime, until: datetime, workers_from: datetime) -> dict:
    conn = await asyncpg.connect(dsn())
    try:
        onboard = await conn.fetch(
            """SELECT object_id AS code, action, at, (detail->>'codec') AS codec, (detail->>'seconds')::float AS seconds
               FROM audit_log WHERE object_id ~ $1 AND action LIKE 'camera.onboard%' AND at BETWEEN $2 AND $3
               ORDER BY at""", SANDBOX, since, until)
        cams = {r["camera_code"]: dict(r) for r in await conn.fetch(
            "SELECT camera_code, codec, resolution, health::text AS health FROM cameras WHERE camera_code ~ $1", SANDBOX)}
        sightings = await conn.fetch(
            """SELECT c.camera_code AS code, count(*) AS n, count(*) FILTER (WHERE s.ocr_conf >= real '0.9') AS high
               FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
               WHERE c.camera_code ~ $1 AND s.event_ts BETWEEN $2 AND $3 GROUP BY 1 ORDER BY 1""",
            SANDBOX, workers_from, until)
        counts = await conn.fetch(
            """SELECT c.camera_code AS code, count(*) AS rows, sum((e.detail->>'frames')::int) AS frames,
                      sum((e.detail->>'window_s')::float) AS window_s
               FROM detection_events e JOIN cameras c ON c.id = e.camera_id
               WHERE c.camera_code ~ $1 AND e.event_type = 'object_counts' AND e.event_ts BETWEEN $2 AND $3
               GROUP BY 1 ORDER BY 1""", SANDBOX, workers_from, until)
        alerts = await conn.fetchrow(
            """SELECT count(*) AS n, count(*) FILTER (WHERE a.retrospective) AS retro,
                      count(*) FILTER (WHERE EXISTS (SELECT 1 FROM vehicle_sightings s WHERE s.id = a.sighting_id
                                                     AND s.event_ts = a.sighting_ts AND s.crop_path IS NOT NULL)) AS crops
               FROM alerts a JOIN cameras c ON c.id = a.camera_id
               WHERE c.camera_code ~ $1 AND a.triggered_at BETWEEN $2 AND $3""", SANDBOX, since, until)
    finally:
        await conn.close()
    return {"onboard": onboard, "cams": cams, "sightings": sightings, "counts": counts, "alerts": dict(alerts)}


def _kill_probe_chrome() -> None:
    """The headless Chrome a hung wall_probe.mjs leaves behind (it debugs on port 9343)."""
    import psutil
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if "chrome" in (p.info["name"] or "").lower() and "--remote-debugging-port=9343" in " ".join(p.info["cmdline"] or []):
                p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def wall(codes: list[str], batch: int, pause_s: float) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(0, len(codes), batch):
        group = codes[i:i + batch]
        env = {**os.environ, "CAMS": ",".join(group), "WEB": os.environ.get("WEB", "http://127.0.0.1:5173"),
               "FAKE_MEDIA_UI": "0",                      # an operator's browser: no media permission granted
               # screenshots of the organisers' footage stay outside the repo
               "SHOT": str(Path(os.environ.get("SHOT_DIR", tempfile.gettempdir())) / f"sandbox_oct9_wall_{i // batch + 1}.jpg")}
        try:
            r = subprocess.run(["node", "wall_probe.mjs"], cwd=ROOT / "submission" / "build", env=env,
                               capture_output=True, text=True, timeout=150)
            for line in r.stdout.splitlines():
                m = re.match(r"(CAM\d{2}): (.+)$", line.strip())
                if m:
                    out[m.group(1)] = m.group(2)
        except subprocess.TimeoutExpired:       # the probe hung (it did once, across a laptop sleep): note it, go on
            for c in group:
                out.setdefault(c, "probe timed out")
            _kill_probe_chrome()
        print(group, "->", [out.get(c) for c in group], flush=True)
        if i + batch < len(codes):
            time.sleep(pause_s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help="start of the onboarding session (ISO time with offset)")
    ap.add_argument("--until", required=True)
    ap.add_argument("--workers-from", required=True, help="when the plate and counts workers started")
    ap.add_argument("--wall", action="store_true", help="also probe every sandbox camera on the video wall")
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--pause", type=float, default=45.0)
    ap.add_argument("--wall-log", help="take the wall results from an earlier run's output instead of probing again")
    ap.add_argument("--wall-window", help="START,END of that earlier probe (ISO times with offset)")
    ap.add_argument("--relay-log", help="MediaMTX log: per-camera source trouble during the wall probe")
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "sandbox_oct9.md"))
    a = ap.parse_args()
    since, until, wfrom = (datetime.fromisoformat(x) for x in (a.since, a.until, a.workers_from))
    d = asyncio.run(gather(since, until, wfrom))

    final: dict[str, dict] = {}
    failed_attempts = 0
    for r in d["onboard"]:
        if r["action"] == "camera.onboard_failed":
            failed_attempts += 1
            final.setdefault(r["code"], {"outcome": "failed"})
        else:
            final[r["code"]] = {"outcome": "onboarded", "codec": r["codec"], "seconds": r["seconds"]}
    ok = {c: v for c, v in final.items() if v["outcome"] == "onboarded"}
    secs = [v["seconds"] for v in ok.values() if v.get("seconds") is not None]
    codes = sorted(d["cams"])
    wall_res, wall_from, wall_to = {}, None, None
    if a.wall:
        wall_from = datetime.now().astimezone()
        wall_res = wall(codes, a.batch, a.pause)
        wall_to = datetime.now().astimezone()
    elif a.wall_log:
        wall_res = _wall_from_log(Path(a.wall_log))
        if a.wall_window:
            wall_from, wall_to = (datetime.fromisoformat(x) for x in a.wall_window.split(","))
    trouble = _relay_trouble(Path(a.relay_log), wall_from, wall_to) if (a.relay_log and wall_from) else {}

    lines = [
        "# The organisers' sandbox, reconnected (9 Oct 2026)",
        "",
        f"Session {since:%Y-%m-%d %H:%M}–{until:%H:%M} (UTC{since:%z}), by `bench/sandbox_oct9.py` from the audit log and the "
        "stored sightings and counts of a native test stack on one laptop (GTX 1650; no Docker), the API on a real broker. "
        "Cameras came from the camera grid's catalogue (`/cameras.json`: an id and a name each) and were onboarded by "
        "`scripts/onboard_sandbox.py` through Sentinel's own URL onboarding (probe, relay, register), one at a time, 10 s "
        "apart, relayed on demand over RTSP/TCP. Consume only; nothing downloaded; no crop used to train or tune. "
        "Counts, times and codecs only.",
        "",
        "## Onboarding",
        "",
        f"- **{len(ok)} of {len(codes)}** sandbox cameras onboarded; {failed_attempts} attempt(s) failed first "
        f"({', '.join(sorted(c for c, v in final.items() if any(r['code'] == c and r['action'] == 'camera.onboard_failed' for r in d['onboard'])))}"
        "; a single retry later succeeded where it now shows onboarded).",
        f"- Probe time (stream ready through the relay): median {statistics.median(secs):.1f} s, range "
        f"{min(secs):.1f}–{max(secs):.1f} s." if secs else "- No probe times.",
        f"- Codecs: {', '.join(f'{k} {v}' for k, v in sorted(_tally(v.get('codec') for v in ok.values()).items()))}; "
        f"resolutions: {', '.join(f'{k} {v}' for k, v in sorted(_tally(d['cams'][c]['resolution'] for c in ok).items()))}.",
        "",
    ]
    if wall_res:
        pictures = {c: s for c, s in wall_res.items() if s.startswith("picture")}
        when = f" ({wall_from:%H:%M}–{wall_to:%H:%M})" if wall_from and wall_to else ""
        lines += [
            f"## Video wall{when}",
            "",
            f"`submission/build/wall_probe.mjs` as an operator's browser (no media permission), {a.batch} cameras at a time "
            f"on a 2x2 wall with a pause between batches, each tile watched for 40 s: **{len(pictures)} of {len(codes)}** "
            "showed a picture in that time. The transport is the tile's badge: *webrtc* is the camera's own stream (for an "
            "H.265 camera, the registered preview); *preview* is the relay's transcoded profile, which the player tries when "
            "the camera's own stream connects but shows nothing in 15 s; *hls* is the last resort. The last three columns "
            "are the relay's own log for each camera during the probe: lost RTP packets (gaps in what the organisers' "
            "server sent; the relay reads over TCP), its connection to their server timing out, and the preview "
            "transcoder failing to start within its 20 s.",
            "",
            "| Camera | Codec | Resolution | Wall | RTP packets lost | Source timeouts | Preview start timeouts |",
            "|---|---|---|---|---|---|---|",
        ]
        for c in codes:
            t = trouble.get(c, {})
            lines.append(f"| {c} | {d['cams'][c]['codec'] or '—'} | {d['cams'][c]['resolution'] or '—'} | "
                         f"{wall_res.get(c, 'not probed')} | {t.get('lost', 0) if trouble else '—'} | "
                         f"{t.get('timeouts', 0) if trouble else '—'} | {t.get('sub_timeouts', 0) if trouble else '—'} |")
        if trouble:
            dark = [c for c in codes if not wall_res.get(c, "").startswith("picture")]
            hit = [c for c in dark if any(trouble.get(c, {}).values())]
            lines += ["", f"Of the {len(dark)} without a picture, {len(hit)} had source trouble logged by the relay in "
                      "the probe window. One probe at one time of day: the sandbox's feeds change through the day, so "
                      "this is a snapshot of them, not of every session."]
        lines.append("")
    lines += [
        "## Workers",
        "",
        f"From {wfrom:%H:%M}: the plate worker on the cameras below with sightings, the counts-only worker (keyframes) on "
        "the cameras with count rows. Sightings are counted, never read here; they wait in the Plate review page's blind "
        "queue for a person to read.",
        "",
        "| Camera | Sightings stored | of which at confidence ≥ 0.9 | Count rows | Frames analysed per minute, from the count rows |",
        "|---|---|---|---|---|",
    ]
    s_by, c_by = {r["code"]: r for r in d["sightings"]}, {r["code"]: r for r in d["counts"]}
    for c in sorted(set(s_by) | set(c_by)):
        s, k = s_by.get(c), c_by.get(c)
        fpm = (60 * k["frames"] / k["window_s"]) if k and k["window_s"] else None
        lines.append(f"| {c} | {s['n'] if s else '—'} | {s['high'] if s else '—'} | {k['rows'] if k else '—'} | "
                     f"{f'{fpm:.0f}' if fpm is not None else '—'} |")
    al = d["alerts"]
    lines += ["", f"Alerts on sandbox cameras in the session: {al['n']}, of which {al['retro']} retrospective (a plate "
              f"already read, put on the watchlist afterwards, raises one at once), {al['crops']} with the sighting's "
              "evidence crop."]
    lines += ["", "One session, one laptop, the organisers' looping replay: a check that the integration works on "
              "their feeds, not a measure of accuracy (no sighting here has been read by a person yet).", ""]
    Path(a.out).write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("written", a.out)
    return 0


def _wall_from_log(path: Path) -> dict[str, str]:
    """The results an earlier --wall run printed: "['CAM01', ...] -> ['picture after ...', ...]" per batch."""
    import ast
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        m = re.match(r"\s*(\[.*?\]) -> (\[.*\])\s*$", line)
        if m:
            out.update(zip(ast.literal_eval(m.group(1)), ast.literal_eval(m.group(2))))
    return out


def _relay_trouble(path: Path, start: datetime, end: datetime) -> dict[str, dict[str, int]]:
    """Per camera, from MediaMTX's log between start and end: RTP packets lost, source timeouts, preview start timeouts.
    MediaMTX writes local time without a zone."""
    t0, t1 = start.astimezone().replace(tzinfo=None), end.astimezone().replace(tzinfo=None)
    out: dict[str, dict[str, int]] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"(\d{4}/\d\d/\d\d \d\d:\d\d:\d\d) \w+ \[path (CAM\d{2})(_sub)?\] (.*)$", line)
        if not m:
            continue
        at = datetime.strptime(m.group(1), "%Y/%m/%d %H:%M:%S")
        if not t0 <= at <= t1:
            continue
        cam, sub, msg = m.group(2), m.group(3), m.group(4)
        row = out.setdefault(cam, {"lost": 0, "timeouts": 0, "sub_timeouts": 0})
        lost = re.search(r"(\d+) RTP packets lost", msg)
        if lost and not sub:
            row["lost"] += int(lost.group(1))
        elif "TCP timeout" in msg and not sub:
            row["timeouts"] += 1
        elif sub and "runOnDemand command stopped: timed out" in msg:
            row["sub_timeouts"] += 1
    return out


def _tally(xs) -> dict:
    out: dict = {}
    for x in xs:
        out[x or "unknown"] = out.get(x or "unknown", 0) + 1
    return out


if __name__ == "__main__":
    raise SystemExit(main())

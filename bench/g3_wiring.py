"""G3 confidence marking: the L wiring pair and the T block's live checks, written up as one results file
(bench/pipeline_gates.md, G3). Window A ran with the API's CONFIDENCE_MARKING off (the shipped behaviour), window B
with it on; the worker was the same code, restarted between windows. The gate: in B, the share of scored sightings
the API marks "check the crop" equals the share below 0.9 in anpr_eval.py's confidence table (same rows: the two
stock-footage cameras, the worker's own track ids, event_ts >= since and < until, confidence rounded to 3 decimals);
median first-read-to-alert latency B <= A + 0.2 s.

    uv run --no-sync python bench/g3_wiring.py --a 2026-10-08T09:10,2026-10-08T09:20 --b 2026-10-08T09:25,2026-10-08T09:35
        [--a-log data/g3/worker_A.log --b-log data/g3/worker_B.log] [--note "..."]

Reads data/g3/check_on.json and check_off.json (bench/g3_check.py) for the T block. ADMIN_PASSWORD from the
environment. Counts and rates only; the stock-footage plates are synthetic.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import httpx

from sentinel_api.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
API = os.environ.get("API", "http://localhost:8000")
CAMS = ["AMD-TRAF-001", "AMD-TRAF-002"]
THRESHOLD = 0.9


def ist(s: str) -> datetime:
    t = datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=IST)


def anpr_eval(arm: str, since: datetime, until: datetime) -> dict:
    """Run scripts/anpr_eval.py on the window and read its confidence table back: {band: (n, exact)}."""
    out = ROOT / "data" / "g3" / f"anpr_{arm}.md"
    cmd = [sys.executable, str(ROOT / "scripts" / "anpr_eval.py"), "--since", since.isoformat(), "--until",
           until.isoformat(), "--out", str(out), "--note", f"G3 wiring window {arm}"]
    for c in CAMS:
        cmd += ["--camera", c]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env={**os.environ, "PYTHONUTF8": "1"})
    if r.returncode != 0:
        raise SystemExit(f"anpr_eval failed for {arm}: {r.stderr[-400:]}")
    text = out.read_text(encoding="utf-8")
    # One confidence table per camera under "### <code> (...)", rows like | 0.7-0.9 | 12 | 83.3% (10/12) |
    # (band_label: "lo-hi" or ">= lo"); the two cameras' tables are summed.
    bands: dict[str, tuple[int, int]] = {}
    for code in CAMS:
        m = re.search(rf"^### {re.escape(code)} \(.*?(?=^### |\Z)", text, re.M | re.S)
        if not m:
            continue
        table = m.group(0).split("| OCR confidence |", 1)
        if len(table) < 2:
            continue
        for row in re.finditer(r"^\| (>= [\d.]+|[\d.]+-[\d.]+) \| (\d+) \| [\d.]+% \((\d+)/\d+\) \|$", table[1], re.M):
            n, k = bands.get(row.group(1), (0, 0))
            bands[row.group(1)] = (n + int(row.group(2)), k + int(row.group(3)))
    if not bands:
        raise SystemExit(f"no confidence table found in {out}")
    return bands


def exact_rate(text_md: Path) -> str | None:
    """The pooled precision cell of anpr_eval's summary table: | **All N ... pooled** | | | | | n | 97.9% (729/745) | ..."""
    for line in text_md.read_text(encoding="utf-8").splitlines():
        if "pooled**" in line:
            cells = [c.strip() for c in line.split("|")]
            return cells[7] if len(cells) > 7 else None
    return None


def api_rows(client: httpx.Client, headers: dict, since: datetime, until: datetime) -> list[dict]:
    rows = []
    for code in CAMS:
        r = client.get(f"{API}/sightings", headers=headers,
                       params={"camera": code, "since": since.isoformat(), "until": until.isoformat(), "limit": 2000})
        r.raise_for_status()
        rows += [s for s in r.json() if (s.get("track_id") or "").startswith(code + "-")
                 and datetime.fromisoformat(s["event_ts"]) < until]
    return rows


async def latency(since: datetime, until: datetime) -> list[float]:
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        rows = await conn.fetch(
            """SELECT (a.detail->>'latency_s')::float AS latency_s FROM alerts a JOIN cameras c ON c.id = a.camera_id
               WHERE a.triggered_at >= $1 AND a.triggered_at < $2 AND NOT a.retrospective AND a.detail ? 'latency_s'
                 AND NOT coalesce((a.detail->>'replayed')::boolean, false) AND c.camera_code = ANY($3::text[])""",
            since, until, CAMS)
    finally:
        await conn.close()
    return sorted(r["latency_s"] for r in rows)


def fps_from_log(path: Path | None, since: datetime, until: datetime) -> float | None:
    if not path or not path.exists():
        return None
    vals = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ .* analysed ([\d.]+) fps total", line)
        if m:
            t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
            if since <= t < until:
                vals.append(float(m.group(2)))
    return round(statistics.median(vals), 2) if vals else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="window A (marking off): since,until in IST")
    ap.add_argument("--b", required=True, help="window B (marking on): since,until in IST")
    ap.add_argument("--a-log", default="data/g3/worker_A.log")
    ap.add_argument("--b-log", default="data/g3/worker_B.log")
    ap.add_argument("--note", default="")
    ap.add_argument("--out", default=str(ROOT / "bench/results/g3_wiring.md"))
    a = ap.parse_args()
    windows = {"A": tuple(ist(x) for x in a.a.split(",")), "B": tuple(ist(x) for x in a.b.split(","))}
    client = httpx.Client(timeout=60)
    r = client.post(f"{API}/auth/login", json={"username": "admin", "password": os.environ.get("ADMIN_PASSWORD", "admin123")})
    r.raise_for_status()
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    res: dict = {"commit": commit, "generated": datetime.now(IST).isoformat(timespec="minutes"), "arms": {}}
    for arm, (since, until) in windows.items():
        bands = anpr_eval(arm, since, until)
        n = sum(v[0] for v in bands.values())
        below = sum(v[0] for k, v in bands.items() if not k.startswith(">="))   # every band under ">= 0.9"
        rows = api_rows(client, headers, since, until)
        marked = sum(1 for s in rows if s.get("needs_review") is True)
        unmarked_none = sum(1 for s in rows if s.get("needs_review") is None)
        lat = asyncio.run(latency(since, until))
        res["arms"][arm] = {
            "since": since.isoformat(), "until": until.isoformat(), "anpr_eval_rows": n, "anpr_eval_below_0_9": below,
            "anpr_eval_bands": bands, "api_rows": len(rows), "api_marked": marked, "api_unmarked_none": unmarked_none,
            "api_below_0_9_recomputed": sum(1 for s in rows if round(s["ocr_conf"], 3) < THRESHOLD),
            "exact": exact_rate(ROOT / "data" / "g3" / f"anpr_{arm}.md"),
            "alerts_with_latency": len(lat), "latency_median_s": round(statistics.median(lat), 3) if lat else None,
            "latency_p95_s": round(statistics.quantiles(lat, n=100)[94], 3) if len(lat) >= 2 else None,
            "analysed_fps_total_median": fps_from_log(ROOT / (a.a_log if arm == "A" else a.b_log), since, until),
        }
    A, B = res["arms"]["A"], res["arms"]["B"]
    # The marks are computed when a row is read, from the API's setting at that moment: window A's rows, fetched
    # now through the API in its B state, carry marks too. A's "no marks" property is the live T check run with
    # marking off (data/g3/check_off.json), not something a later query can show.
    checks = {
        "A: API rows equal anpr_eval's scored rows": A["api_rows"] == A["anpr_eval_rows"],
        "B: API rows equal anpr_eval's scored rows": B["api_rows"] == B["anpr_eval_rows"],
        "B: marked share equals anpr_eval's below-0.9 share (exact)": B["api_marked"] == B["anpr_eval_below_0_9"],
        "B: median latency <= A + 0.2 s": (A["latency_median_s"] is not None and B["latency_median_s"] is not None
                                           and B["latency_median_s"] <= A["latency_median_s"] + 0.2),
    }
    t: dict = {}
    for mode in ("off", "on"):
        p = ROOT / "data" / "g3" / f"check_{mode}.json"
        t[mode] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    if t["off"] and t["on"]:
        checks["T: alert count equal with marking off and on (same ingests)"] = t["off"]["alert_count"] == t["on"]["alert_count"]
        checks["T: live checks all passed, off and on"] = t["off"]["fails"] == 0 and t["on"]["fails"] == 0
    res["checks"] = checks
    res["t_block"] = {m: ({"alert_count": v["alert_count"], "fails": v["fails"], "at": v["at"]} if v else None)
                      for m, v in t.items()}
    ok = all(checks.values())
    res["verdict"] = "PASS" if ok else "FAIL"
    L = ["# G3 confidence marking: L wiring pair and live T checks", "",
         f"Generated {res['generated']} IST by `bench/g3_wiring.py` at commit `{commit}`. Gate: `bench/pipeline_gates.md` "
         "G3. Worker: AMD-TRAF-001, AMD-TRAF-002, AMD-POL-001, AMD-AMC-001; HW_DECODE=auto, object detection on, "
         "STATIC_TEXT_WINDOW_S=0, every other setting at its default; restarted between windows; the GTX 1650 Ti laptop "
         "on AC. A = API with CONFIDENCE_MARKING off (shipped), B = on. Scored: the two stock-footage cameras "
         "(synthetic plates), the worker's own tracks, as `scripts/anpr_eval.py` selects them."
         + (f" {a.note}" if a.note else ""), "",
         "| Arm | Window (IST) | Scored sightings (anpr_eval / API) | Below 0.9 (anpr_eval) | Marked by the API | "
         "Exact | Alerts with latency | Median s | p95 s | Analysed fps (total, median) |",
         "|---|---|---:|---:|---:|---|---:|---:|---:|---:|"]
    for arm, v in res["arms"].items():
        L.append(f"| {arm} | {v['since'][11:16]}–{v['until'][11:16]} | {v['anpr_eval_rows']} / {v['api_rows']} | "
                 f"{v['anpr_eval_below_0_9']} | {v['api_marked']}{' (read back with marking on)' if arm == 'A' else ''} | "
                 f"{v['exact'] or 'n/a'} | {v['alerts_with_latency']} | {v['latency_median_s']} | {v['latency_p95_s']} | "
                 f"{v['analysed_fps_total_median']} |")
    L += ["", "## Checks", ""]
    for k, v in checks.items():
        L.append(f"- [{'PASS' if v else 'FAIL'}] {k}")
    L += ["", f"**Verdict: {res['verdict']}.** The T block's pytest tests are in `services/api/tests/test_marking.py`; "
          "the live part (a 0.85 sighting marked, a 0.90 stored as REAL and read back not marked, a one-character alert "
          "marked, `reads` and `agreement` written, the alert count with marking off and on) is `bench/g3_check.py`, "
          f"run with marking off at {t['off']['at'] if t['off'] else 'n/a'} and on at {t['on']['at'] if t['on'] else 'n/a'} "
          "(synthetic plates on two simulator cameras, removed afterwards). The F leg (the fresh sandbox set, by band) "
          "is not run: `sandbox-fresh-v1` is not frozen, so no claim that confidence separates right from wrong reads "
          "is made beyond the 120 blind-checked plates already reported; the marking ships as a review aid."]
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(a.out).with_suffix(".json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print("\n".join(L))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

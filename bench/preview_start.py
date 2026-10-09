"""Does the relay's preview transcoder start on a lossy source? The shipped command against a candidate that waits
longer for a clean keyframe, on the same cameras in alternating order (same source, same minutes).

The preview (infra/mediamtx.yml, "~^(.+)_sub$") is what a browser plays for an H.265 camera and what the player falls
back to when a camera's own stream gives no picture. On a lossy source FFmpeg can give up before it has a picture
size ("Error opening output file ... Invalid argument"), and the relay stops trying after 20 s. Each run here reads
the camera through the relay and publishes to a scratch path on the same relay (loopback, nothing leaves the machine);
the result is the time until that path is ready, or "no start" after the window.

    uv run --no-sync python bench/preview_start.py --cams CAM07,CAM08,CAM10 --rounds 3
"""
from __future__ import annotations

import argparse
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RELAY, API = "127.0.0.1:8554", "http://127.0.0.1:9997"
ENCODE = ["-vf", "scale=640:-2,fps=8", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
          "-profile:v", "baseline", "-g", "16", "-bf", "0", "-an", "-f", "rtsp", "-rtsp_transport", "tcp"]
ARMS = {
    "shipped": [],
    # wait up to 20 s of stream for a picture size instead of FFmpeg's default ~5 s; drop corrupt packets; go on past
    # decode errors
    "candidate": ["-analyzeduration", "20000000", "-probesize", "20000000", "-fflags", "+discardcorrupt",
                  "-err_detect", "ignore_err"],
}


def ready(path: str) -> bool:
    try:
        r = httpx.get(f"{API}/v3/paths/get/{path}", timeout=3)
        return r.status_code == 200 and bool(r.json().get("ready"))
    except httpx.HTTPError:
        return False


def attempt(cam: str, arm: str, window: float) -> float | None:
    """Seconds until the scratch path is ready; the command is restarted when it exits, as the relay restarts it."""
    out = f"ZZPREV_{cam}_{arm}"
    t0, proc = time.monotonic(), None
    try:
        while time.monotonic() - t0 < window:
            if proc is None or proc.poll() is not None:
                proc = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp",
                                         *ARMS[arm], "-i", f"rtsp://{RELAY}/{cam}", *ENCODE, f"rtsp://{RELAY}/{out}"],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ready(out):
                return round(time.monotonic() - t0, 1)
            time.sleep(0.25)
        return None
    finally:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cams", required=True)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--window", type=float, default=30.0, help="seconds an attempt may take (the relay allows 20)")
    ap.add_argument("--rest", type=float, default=20.0, help="seconds between attempts")
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "preview_start.md"))
    a = ap.parse_args()
    cams = [c.strip().upper() for c in a.cams.split(",") if c.strip()]
    started = datetime.now().astimezone()
    rows = []
    for rnd in range(a.rounds):
        order = list(ARMS) if rnd % 2 == 0 else list(ARMS)[::-1]
        for cam in cams:
            for arm in order:
                s = attempt(cam, arm, a.window)
                rows.append({"round": rnd + 1, "cam": cam, "arm": arm, "seconds": s})
                print(rows[-1], flush=True)
                time.sleep(a.rest)
    ended = datetime.now().astimezone()

    def arm_line(arm: str, limit: float | None = None) -> str:
        xs = [r["seconds"] for r in rows if r["arm"] == arm]
        ok = [x for x in xs if x is not None and (limit is None or x <= limit)]
        med = f", median {statistics.median(ok):.1f} s" if ok else ""
        return f"{len(ok)} of {len(xs)}{med}"

    lines = [
        "# Preview transcoder start on lossy sources: shipped command against a candidate",
        "",
        f"Measured {started:%Y-%m-%d %H:%M}–{ended:%H:%M} (UTC{started:%z}) by `bench/preview_start.py` on cameras "
        f"{', '.join(cams)} of the organisers' sandbox, read through Sentinel's relay on one laptop; {a.rounds} rounds, "
        "the two commands in alternating order within each camera, an attempt's window "
        f"{a.window:.0f} s (the relay allows 20 s), {a.rest:.0f} s between attempts.",
        "",
        "Shipped: the preview command in `infra/mediamtx.yml`. Candidate: the same, with "
        f"`{' '.join(ARMS['candidate'])}` before the input.",
        "",
        "| Arm | Started within 20 s (the relay's limit) | Started within the window |",
        "|---|---|---|",
        f"| shipped | {arm_line('shipped', 20)} | {arm_line('shipped')} |",
        f"| candidate | {arm_line('candidate', 20)} | {arm_line('candidate')} |",
        "",
        "| Round | Camera | Arm | Seconds to a published preview |",
        "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['round']} | {r['cam']} | {r['arm']} | {r['seconds'] if r['seconds'] is not None else 'no start'} |")
    lines += ["", "The sandbox's feeds change through the day: the arms are compared within one session only.", ""]
    Path(a.out).write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("written", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

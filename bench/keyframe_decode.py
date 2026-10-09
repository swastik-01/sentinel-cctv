"""CPU cost of decoding every frame against keyframes only, on N relay streams at once: the measurement behind the
counts-only worker (services/analytics/sentinel_analytics/counts.py). Both modes convert only keyframes to BGR (the
frames a counts-only analyser uses), so the difference is decode alone. Each stream is its own RTSP session through
the local relay. Counts only; the simulator's plates are synthetic.

    uv run --no-sync python bench/keyframe_decode.py --seconds 25 [--cams A,B,...] [--out bench/results/keyframe_decode.md]
"""
from __future__ import annotations

import argparse
import json
import platform
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import av
import psutil

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
SIM = ["AMD-AMC-001", "AMD-AMC-002", "AMD-GSRTC-001", "AMD-HLTH-001", "AMD-POL-001", "AMD-TRAF-001", "AMD-TRAF-002",
       "GNR-GSRTC-001", "GNR-HLTH-001", "GNR-PNCHT-001", "GNR-PNCHT-002", "GNR-POL-001", "GNR-POL-002", "MHS-POL-001"]


def run(mode: str, cams: list[str], seconds: float) -> dict:
    stats: dict[str, dict] = {}
    start = threading.Barrier(len(cams) + 1)

    def one(code: str) -> None:
        try:
            c = av.open(f"rtsp://localhost:8554/{code}", options={"rtsp_transport": "tcp"}, timeout=(10, 15))
        except Exception as e:  # noqa: BLE001
            stats[code] = {"error": type(e).__name__}
            start.wait()
            return
        s = c.streams.video[0]
        if mode == "key":
            s.codec_context.skip_frame = "NONKEY"
        start.wait()
        decoded = keys = 0
        t0 = time.monotonic()
        try:
            for frame in c.decode(s):
                decoded += 1
                if frame.key_frame:
                    keys += 1
                    frame.to_ndarray(format="bgr24")
                if time.monotonic() - t0 > seconds:
                    break
        except Exception as e:  # noqa: BLE001
            stats[code] = {"error": type(e).__name__}
            return
        finally:
            c.close()
        wall = time.monotonic() - t0
        stats[code] = {"codec": s.codec_context.name, "w": s.codec_context.width, "h": s.codec_context.height,
                       "decoded_fps": round(decoded / wall, 1), "keyframes_fps": round(keys / wall, 2)}

    threads = [threading.Thread(target=one, args=(c,), daemon=True) for c in cams]
    for t in threads:
        t.start()
    start.wait()
    proc = psutil.Process()
    cpu0, w0 = sum(proc.cpu_times()[:2]), time.monotonic()
    for t in threads:
        t.join(seconds + 30)
    cpu, wall = sum(proc.cpu_times()[:2]) - cpu0, time.monotonic() - w0
    return {"mode": mode, "streams": len(cams), "wall_s": round(wall, 1), "cpu_s": round(cpu, 1),
            "cores": round(cpu / wall, 2), "per_stream": stats}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cams", default=",".join(SIM))
    ap.add_argument("--seconds", type=float, default=25)
    ap.add_argument("--out", default=str(ROOT / "bench/results/keyframe_decode.md"))
    a = ap.parse_args()
    cams = a.cams.split(",")
    key = run("key", cams, a.seconds)
    time.sleep(3)
    full = run("all", cams, a.seconds)
    now = datetime.now(IST)
    L = ["# Decoding every frame against keyframes only", "",
         f"Generated {now:%Y-%m-%d %H:%M} IST by `bench/keyframe_decode.py` on {platform.processor()}, "
         f"{psutil.cpu_count()} logical CPUs; PyAV {av.__version__}, software decode, RTSP over TCP through the local "
         f"relay; {len(cams)} simulator streams at once ({', '.join(cams)}), {a.seconds:g} s each mode. Only keyframes "
         "are converted to an image in both modes, so the difference is the decoder's work on the other frames. CPU is "
         "this process's user+system time over the wall time; the relay's own CPU is not included.", "",
         "| Mode | Streams | CPU cores used | Keyframes per stream per second (median) |", "|---|---:|---:|---:|"]
    for r in (full, key):
        kf = sorted(v["keyframes_fps"] for v in r["per_stream"].values() if "keyframes_fps" in v)
        med = kf[len(kf) // 2] if kf else float("nan")
        L.append(f"| {'every frame' if r['mode'] == 'all' else 'keyframes only'} | {r['streams']} | {r['cores']} | {med} |")
    L += ["", "| Stream | Codec | Size | Decoded/s (every frame) | Keyframes/s |", "|---|---|---|---:|---:|"]
    for c in cams:
        f, k = full["per_stream"].get(c, {}), key["per_stream"].get(c, {})
        L.append(f"| {c} | {f.get('codec', k.get('codec', '?'))} | {f.get('w', '?')}x{f.get('h', '?')} | "
                 f"{f.get('decoded_fps', 'err')} | {k.get('keyframes_fps', 'err')} |")
    L += ["", "The keyframe rate is set by each clip's encoder (one every 1-2 s here), so a counts-only analysis gets "
          "the same frames either way; what changes is the cost of getting them."]
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(a.out).with_suffix(".json").write_text(json.dumps({"generated": now.isoformat(timespec="minutes"),
                                                             "every_frame": full, "keyframes_only": key}, indent=2),
                                                 encoding="utf-8")
    print("\n".join(L[:8]))


if __name__ == "__main__":
    main()

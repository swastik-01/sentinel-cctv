"""How many cameras the counts-only worker (services/analytics/sentinel_analytics/counts.py) can count at once here.

Each stream is its own RTSP session through the local relay, cycling over the given simulator cameras, so N can exceed
the number of cameras while the decode and network load stay real. The loop mirrors counts.run: keyframe sources,
keyframes gathered up to a batch or GATHER_S, one detector call per batch. Nothing is sent to the API. For each N:
frames counted per stream per second, streams that delivered nothing, CPU cores used by this process (decode,
conversion, detector pre- and post-processing), GPU busy share and detector time per frame. The relay's own CPU
(MediaMTX in Docker) is not included.

    uv run --no-sync python bench/counts_capacity.py --streams 10 20 30 40 50 --seconds 60
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psutil

from sentinel_analytics.config import get_settings
from sentinel_analytics.counts import GATHER_S, KeyframeSource
from sentinel_analytics.objects import ObjectDetector

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
SIM = ["AMD-AMC-001", "AMD-AMC-002", "AMD-GSRTC-001", "AMD-HLTH-001", "AMD-POL-001", "AMD-TRAF-001", "AMD-TRAF-002",
       "GNR-GSRTC-001", "GNR-HLTH-001", "GNR-PNCHT-001", "GNR-PNCHT-002", "GNR-POL-001", "GNR-POL-002", "MHS-POL-001"]


def gpu_sampler(stop: threading.Event, out: list[int]) -> None:
    while not stop.is_set():
        try:
            out.append(int(subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                                          capture_output=True, text=True, timeout=5).stdout.strip()))
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        stop.wait(2)


def measure(n: int, cams: list[str], seconds: float, warm: float, det: ObjectDetector, batch: int, fps: float) -> dict:
    sources = [KeyframeSource(f"{cams[i % len(cams)]}#{i}", f"rtsp://localhost:8554/{cams[i % len(cams)]}", 1.0 / fps)
               for i in range(n)]
    for s in sources:
        s.start()
    proc = psutil.Process()
    counted = [0] * n
    det_ms, batches = 0.0, []
    pending: dict[int, object] = {}
    since = 0.0
    t_end_warm = time.time() + warm
    t_start = cpu0 = None
    gpu: list[int] = []
    stop_gpu = threading.Event()
    while True:
        now = time.time()
        if t_start is None and now >= t_end_warm:
            t_start, cpu0 = now, sum(proc.cpu_times()[:2])
            counted = [0] * n
            det_ms, batches = 0.0, []
            threading.Thread(target=gpu_sampler, args=(stop_gpu, gpu), daemon=True).start()
        if t_start is not None and now - t_start >= seconds:
            break
        for i, s in enumerate(sources):
            if (f := s.latest()) is not None:
                if not pending:
                    since = now
                pending[i] = f
        if pending and (len(pending) >= batch or now - since >= GATHER_S):
            items, pending = list(pending.items()), {}
            for k in range(0, len(items), batch):
                chunk = items[k: k + batch]
                t0 = time.perf_counter()
                det.detect_batch([f.image for _, f in chunk])
                det_ms += (time.perf_counter() - t0) * 1000
                batches.append(len(chunk))
                for i, _ in chunk:
                    counted[i] += 1
        else:
            time.sleep(0.02)
    wall = time.time() - t_start
    cpu = sum(proc.cpu_times()[:2]) - cpu0
    stop_gpu.set()
    for s in sources:
        s.stop()
    frames = sum(counted)
    per = [c / wall for c in counted]
    return {"streams": n, "seconds": round(wall, 1), "frames": frames,
            "per_stream_fps_median": round(statistics.median(per), 2), "per_stream_fps_min": round(min(per), 2),
            "silent_streams": sum(1 for c in counted if c == 0), "cpu_cores": round(cpu / wall, 2),
            "gpu_util_mean": round(statistics.mean(gpu), 1) if gpu else None,
            "det_ms_per_frame": round(det_ms / max(1, frames), 1),
            "batch_mean": round(statistics.mean(batches), 1) if batches else 0,
            "errors": sum(s.errors for s in sources)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--streams", type=int, nargs="+", default=[10, 20, 30, 40, 50])
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--warm", type=float, default=15, help="seconds to connect before measuring")
    ap.add_argument("--cams", default=",".join(SIM))
    ap.add_argument("--note", default="")
    ap.add_argument("--out", default=str(ROOT / "bench/results/counts_capacity.md"))
    a = ap.parse_args()
    s = get_settings()
    cams = a.cams.split(",")
    det = ObjectDetector()
    if not det.ready:
        raise SystemExit("object detector unavailable")
    gpu_name = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True,
                              text=True).stdout.strip() or "none"
    rows = []
    for n in a.streams:
        r = measure(n, cams, a.seconds, a.warm, det, s.counts_batch, s.counts_fps)
        rows.append(r)
        print(json.dumps(r), flush=True)
        time.sleep(3)
    now = datetime.now(IST)
    lines = [
        "# Counts-only worker: cameras counted at once on one laptop", "",
        f"Generated {now:%Y-%m-%d %H:%M} IST by `bench/counts_capacity.py`. Machine: {platform.processor()}, "
        f"{psutil.cpu_count()} logical CPUs, GPU {gpu_name}; detector {det.name} on {det.device} (fp16={det.half}, "
        f"imgsz {s.object_imgsz}), batch up to {s.counts_batch}, gathered for up to {GATHER_S} s; at most "
        f"{s.counts_fps:g} frame/s per stream, keyframes only. Streams: RTSP sessions through the local relay, cycling "
        f"over {len(cams)} simulator cameras ({', '.join(cams)}): H.264 and H.265, 704x576 to 1920x1080, 12-25 fps, "
        f"keyframes every 1-2 s. {a.warm:g} s to connect, then {a.seconds:g} s measured per row. The relay's own CPU "
        "is not included; no plate worker ran at the same time." + (f" {a.note}" if a.note else ""), "",
        "| Streams | Frames/s per stream (median, min) | Silent streams | CPU cores | GPU busy | Detector ms/frame | "
        "Mean batch | Reconnects/errors |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(f"| {r['streams']} | {r['per_stream_fps_median']}, {r['per_stream_fps_min']} | "
                     f"{r['silent_streams']} | {r['cpu_cores']} | {r['gpu_util_mean']}% | {r['det_ms_per_frame']} | "
                     f"{r['batch_mean']} | {r['errors']} |")
    lines += ["", "A stream's rate is capped by its keyframe interval: these cameras send a keyframe every 1-2 s, so "
              "0.5-1 frame/s per stream is the most this profile can count. Counts are per minute, so that is "
              "enough; a camera whose keyframes are further apart is counted less often."]
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path(a.out).with_suffix(".json").write_text(json.dumps({"generated": now.isoformat(timespec="minutes"),
                                                             "rows": rows}, indent=2), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

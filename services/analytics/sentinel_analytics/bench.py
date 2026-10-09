"""Per-stream cost benchmark → the numbers behind the 80,000-camera capacity model.

For each stream count N: connect N RTSP sources, run the full pipeline (decode →
detect → OCR) for a fixed duration, and record achieved analysis fps, GPU utilisation
and memory, CPU load and RSS. Writes bench/results/<timestamp>.json.

    uv run --package sentinel-analytics sentinel-bench --streams 1,2,4,8 --seconds 30
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import get_settings
from .detect import PlateDetector
from .ocr import PlateOCR
from .sink import ApiSink
from .stream import RtspSource

logging.basicConfig(level=logging.WARNING)


def gpu_sample() -> dict:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,power.draw",
             "--format=csv,noheader,nounits"], text=True, timeout=5).strip().split(", ")
        return {"name": out[0], "util_pct": float(out[1]), "mem_used_mb": float(out[2]),
                "mem_total_mb": float(out[3]), "power_w": float(out[4]) if out[4] != "[N/A]" else None}
    except Exception:  # noqa: BLE001
        return {}


try:
    import psutil  # optional
    _PROC = psutil.Process()   # must persist: cpu_percent() measures since the previous call on this object
except ImportError:
    psutil = None
    _PROC = None


def cpu_sample() -> dict:
    """Process CPU is normalised to a share of all logical cores (100 = the whole machine)."""
    if _PROC is None:
        return {"rss_mb": None}
    return {"proc_cpu_pct": round(_PROC.cpu_percent(interval=None) / psutil.cpu_count(), 1),
            "sys_cpu_pct": psutil.cpu_percent(interval=None),
            "rss_mb": round(_PROC.memory_info().rss / 2**20)}


def run_case(cams: list[dict], seconds: float, detector: PlateDetector, ocr: PlateOCR) -> dict:
    s = get_settings()
    sources = [RtspSource(c["camera_code"], c["rtsp_url"], s.detect_fps * 1.5, s.hw_decode).start() for c in cams]
    time.sleep(4)  # let streams connect
    interval = 1.0 / s.detect_fps
    due = {src.code: 0.0 for src in sources}
    analysed = plates = 0
    det_ms: list[float] = []
    gpu_util: list[float] = []
    t_end = time.time() + seconds
    cpu_sample()
    while time.time() < t_end:
        now = time.time()
        frames, codes = [], []
        for src in sources:
            if now >= due[src.code]:
                f = src.latest()
                if f is not None:
                    due[src.code] = now + interval
                    frames.append(f.image); codes.append(src.code)
        if frames:
            t0 = time.perf_counter()
            boxes = detector.detect_batch(frames)
            crops = [img[y:y + h, x:x + w] for img, bx in zip(frames, boxes) for (x, y, w, h, _) in bx]
            plates += sum(bool(t and c >= s.min_ocr_conf) for t, c in ocr.read_many(crops))
            det_ms.append((time.perf_counter() - t0) * 1000)
            analysed += len(frames)
            if len(det_ms) % 10 == 0:
                g = gpu_sample()
                if g:
                    gpu_util.append(g["util_pct"])
        else:
            time.sleep(0.005)
    for src in sources:
        src.stop()
    decoded = sum(src.stats.decoded for src in sources)
    g = gpu_sample()
    return {
        "streams": len(sources), "seconds": seconds,
        "cameras": [src.code for src in sources],
        "resolutions": sorted({f"{src.stats.width}x{src.stats.height}" for src in sources}),
        "decoders": sorted({src.stats.decoder for src in sources}),
        "decoded_fps_total": round(decoded / seconds, 1),
        "analysed_fps_total": round(analysed / seconds, 2),
        "analysed_fps_per_stream": round(analysed / seconds / max(1, len(sources)), 2),
        "target_fps_per_stream": s.detect_fps,
        "batch_ms_avg": round(sum(det_ms) / len(det_ms), 1) if det_ms else None,
        "batch_ms_p95": round(sorted(det_ms)[int(len(det_ms) * 0.95)], 1) if det_ms else None,
        "plates_read": plates,
        "gpu_util_avg_pct": round(sum(gpu_util) / len(gpu_util), 1) if gpu_util else None,
        "gpu_mem_used_mb": g.get("mem_used_mb"),
        **cpu_sample(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--streams", default="1,2,4,8")
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--out", default="bench/results")
    a = ap.parse_args()
    sink = ApiSink()
    cams = sorted(sink.cameras(), key=lambda c: c["camera_code"])
    if not cams:
        raise SystemExit("no analytics-enabled cameras in the registry")
    detector, ocr = PlateDetector(), PlateOCR()
    results = []
    for n in (int(x) for x in a.streams.split(",")):
        chosen = (cams * ((n // len(cams)) + 1))[:n]  # reuse streams if n > registry size
        print(f"== {n} stream(s) for {a.seconds:.0f}s ==", flush=True)
        r = run_case(chosen, a.seconds, detector, ocr)
        print(json.dumps(r, indent=1), flush=True)
        results.append(r)
    report = {
        "at": datetime.now(timezone.utc).isoformat(), "host": platform.node(),
        "cpu": platform.processor(), "os": platform.platform(), "gpu": gpu_sample(),
        "device": detector.device, "detector_mode": get_settings().detector,
        "yolo_loaded": bool(detector.model), "fp16": detector.half,
        "detect_fps_target": get_settings().detect_fps, "hw_decode": get_settings().hw_decode, "cases": results,
    }
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    path = out / f"bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()

"""NVDEC (the NVIDIA GPU's video decoder) against software decoding, with FFmpeg, on this machine.

decode.md measured OpenCV's D3D11 path, which on a laptop with an Intel iGPU decodes on the iGPU, not the NVIDIA card,
so a server node's NVDEC stayed design. This measures the NVIDIA decoder itself, decode only (no detector, no OCR):

- throughput: N decoders at full speed on one clip each (looped) for a fixed wall time, total frames decoded per second;
- real-time load: N streams paced at their own frame rate (-re), whether each keeps up, and the system CPU it costs.

Modes: software (CPU decode); software-640 (CPU decode, then each frame resized to 640x360 on the CPU); nvdec-copy
(NVDEC decode, full frames copied back to system memory, what today's CPU-side worker would need); nvdec-640 (NVDEC
decode and the resize on the GPU, only the small frame copied back, as a GPU pipeline feeding a 640-px detector).
Two rounds in alternating order, software first then hardware first, to spread thermal throttling over both.

    uv run --no-sync python bench/nvdec_decode.py --media <folder with the simulator's .mp4 clips>
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
# (options before the input, options after it). The -640 modes also resize each frame to 640x360, the size class the
# detectors take: on the CPU for software, on the GPU for NVDEC (only the small frame is copied back).
MODES = {"software": ([], []),
         "software-640": ([], ["-vf", "scale=640:360"]),
         "nvdec-copy": (["-hwaccel", "cuda"], []),
         "nvdec-640": (["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"], ["-vf", "scale_cuda=640:360,hwdownload,format=nv12"])}


def probe(clip: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=codec_name,width,height,avg_frame_rate,has_b_frames", "-of", "json", str(clip)],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = (int(x) for x in s["avg_frame_rate"].split("/"))
    return {"codec": s["codec_name"], "size": f"{s['width']}x{s['height']}", "fps": num / den,
            "b_frames": s.get("has_b_frames", 0)}


def decoder(clip: Path, mode: str, realtime: bool) -> subprocess.Popen:
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-progress", "pipe:1", "-stats_period", "0.5",
           *MODES[mode][0], *(["-re"] if realtime else []), "-stream_loop", "-1", "-i", str(clip), *MODES[mode][1],
           "-an", "-f", "null", "-"]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)


def frames_read(p: subprocess.Popen, store: dict, key: int) -> None:
    for line in p.stdout:
        if line.startswith("frame="):
            try:
                store[key] = int(line.split("=", 1)[1])
            except ValueError:
                pass


def gpu_sampler(samples: list, stop: threading.Event) -> None:
    while not stop.is_set():
        r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.decoder,utilization.gpu", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True)
        try:
            dec, gpu = (float(x) for x in r.stdout.strip().split(","))
            samples.append((dec, gpu))
        except ValueError:
            pass
        stop.wait(1.0)


def run(clip: Path, mode: str, n: int, seconds: float, realtime: bool) -> dict:
    procs = [decoder(clip, mode, realtime) for _ in range(n)]
    frames: dict[int, int] = {}
    readers = [threading.Thread(target=frames_read, args=(p, frames, i), daemon=True) for i, p in enumerate(procs)]
    for r in readers:
        r.start()
    time.sleep(2.0)                                   # start-up (decoder open, first keyframe) is not counted
    start = dict(frames)
    stop, gpu = threading.Event(), []
    g = threading.Thread(target=gpu_sampler, args=(gpu, stop), daemon=True)
    g.start()
    psutil.cpu_percent(None)
    cpu, t0 = [], time.monotonic()
    while time.monotonic() - t0 < seconds:
        time.sleep(1.0)
        cpu.append(psutil.cpu_percent(None))
    wall = time.monotonic() - t0
    end = dict(frames)
    stop.set()
    for p in procs:
        p.kill()
    for p in procs:
        p.wait()
    per = [(end.get(i, 0) - start.get(i, 0)) / wall for i in range(n)]
    errors = sum(1 for p in procs if p.returncode not in (0, 1, -9, 15, -15) and p.stderr and p.stderr.read().strip())
    return {"mode": mode, "streams": n, "realtime": realtime, "fps_total": round(sum(per), 1),
            "fps_min": round(min(per), 2) if per else 0.0, "cpu": round(statistics.mean(cpu), 1) if cpu else None,
            "nvdec": round(statistics.mean(d for d, _ in gpu), 1) if gpu else None,
            "gpu": round(statistics.mean(x for _, x in gpu), 1) if gpu else None, "errors": errors}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", required=True, help="folder with the simulator clips")
    ap.add_argument("--clips", default="GNR-POL-001.mp4,AMD-AMC-002.mp4", help="H.264 and H.265 at 1080p by default")
    ap.add_argument("--seconds", type=float, default=15.0)
    ap.add_argument("--throughput", default="1,4")
    ap.add_argument("--realtime", default="8,16")
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "nvdec_decode.md"))
    a = ap.parse_args()

    media = Path(a.media)
    clips = [media / c for c in a.clips.split(",")]
    info = {c.name: probe(c) for c in clips}
    gpu_name = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
                              capture_output=True, text=True).stdout.strip()
    ff = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    started = datetime.now(timezone.utc)
    rows = []
    orders = [list(MODES), list(MODES)[::-1]]                 # round 1 software first, round 2 hardware first
    for rnd, order in enumerate(orders, 1):
        for clip in clips:
            for n in (int(x) for x in a.throughput.split(",")):
                for mode in order:
                    r = run(clip, mode, n, a.seconds, realtime=False)
                    rows.append({"round": rnd, "clip": clip.name, **r})
                    print(rows[-1], flush=True)
            for n in (int(x) for x in a.realtime.split(",")):
                for mode in order:
                    r = run(clip, mode, n, a.seconds, realtime=True)
                    rows.append({"round": rnd, "clip": clip.name, **r})
                    print(rows[-1], flush=True)

    def pooled(clip, mode, n, rt, key):
        xs = [r[key] for r in rows if r["clip"] == clip and r["mode"] == mode and r["streams"] == n
              and r["realtime"] == rt and r[key] is not None]
        return round(statistics.mean(xs), 1) if xs else None

    def rounds(clip, mode, n, rt, key):
        return " / ".join(str(r[key]) for r in rows if r["clip"] == clip and r["mode"] == mode
                          and r["streams"] == n and r["realtime"] == rt)

    lines = [
        "# Video decode: NVDEC (NVIDIA hardware decoder) against software",
        "",
        f"Measured {started:%Y-%m-%d %H:%M} UTC on {platform.node()} ({gpu_name}; {platform.processor()}), "
        f"{platform.platform()}, by `bench/nvdec_decode.py` with {ff.split(' Copyright')[0]}.",
        f"Decode only (FFmpeg to a null output: no detector, no OCR), {a.seconds:.0f} s per case after a 2 s start-up, two rounds "
        "in alternating order (software first, then hardware first). The simulator's other services ran as usual "
        "(publishers copying their clips into the relay, the API, the database); no analytics worker ran.",
        "",
        "Clips: " + "; ".join(f"`{k}` {v['codec']} {v['size']} at {v['fps']:g} fps, B-frames {v['b_frames']}"
                              for k, v in info.items()) + ".",
        "",
        "Modes: **software** (CPU decode); **software-640** (CPU decode, each frame then resized to 640x360 on the CPU, "
        "the size class the detectors take); **nvdec-copy** (NVDEC decode, full frames copied back to system memory, "
        "what today's CPU-side worker would need); **nvdec-640** (NVDEC decode and the resize on the GPU, only the "
        "small frame copied back, as a GPU pipeline feeding a 640-px detector).",
        "",
        "## Throughput: decoders at full speed",
        "",
        "Frames decoded per second, all decoders together (mean of the two rounds; each round in the last column). "
        "Divide by 25 for 1080p25 streams' worth of decoding.",
        "",
        "| Clip | Decoders | Mode | Frames/s total | System CPU | NVDEC busy | Per round (frames/s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for clip in info:
        for n in (int(x) for x in a.throughput.split(",")):
            for mode in MODES:
                lines.append(f"| {clip} | {n} | {mode} | {pooled(clip, mode, n, False, 'fps_total')} | "
                             f"{pooled(clip, mode, n, False, 'cpu')}% | {pooled(clip, mode, n, False, 'nvdec')}% | "
                             f"{rounds(clip, mode, n, False, 'fps_total')} |")
    lines += [
        "",
        "## Real-time load: streams paced at their frame rate",
        "",
        "Each decoder reads at the clip's own rate (`-re`), as a live camera arrives. *Slowest stream* is the lowest "
        "decode rate of any one stream (it keeps up at the clip's rate).",
        "",
        "| Clip | Streams | Mode | Slowest stream (frames/s) | System CPU | NVDEC busy | Per round (CPU %) |",
        "|---|---|---|---|---|---|---|",
    ]
    for clip in info:
        for n in (int(x) for x in a.realtime.split(",")):
            for mode in MODES:
                lines.append(f"| {clip} | {n} | {mode} | {pooled(clip, mode, n, True, 'fps_min')} | "
                             f"{pooled(clip, mode, n, True, 'cpu')}% | {pooled(clip, mode, n, True, 'nvdec')}% | "
                             f"{rounds(clip, mode, n, True, 'cpu')} |")
    lines += [
        "",
        "What this is and is not: one laptop GPU (a GTX 1650, one NVDEC engine), FFmpeg's decoder, our simulator's clips, "
        "one day. It shows what the NVIDIA decoder takes off the CPU here, not a server node's streams: the Plan for "
        "Scale's per-node figures stay assumptions until measured on that hardware. The analytics worker does not use "
        "NVDEC today (`HW_DECODE=auto` is OpenCV's D3D11 path, `decode.md`).",
        "",
        "Raw rows:",
        "",
        "```json",
        json.dumps(rows, indent=None),
        "```",
        "",
    ]
    Path(a.out).write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("written", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

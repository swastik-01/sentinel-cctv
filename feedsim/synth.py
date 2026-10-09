"""Generate synthetic CCTV clips with legible (or deliberately illegible) number plates.

Purpose: unblock the whole ANPR pipeline before real footage exists. Each camera in
cameras.yaml gets a looping clip whose codec, resolution and "scene" match its
registry entry, so the simulator can stream it with `-c copy` at near-zero CPU.

Each vehicle is rendered as a small static canvas (body + plate + text) and then
animated across the road with `overlay`, whose x/y expressions support time (`t`).
(`drawbox` cannot animate: its `t` constant is line thickness, not time.)

Scenes:
  close  - plate ~220px wide, clearly OCR-able (checkpost / gate cameras)
  mid    - plate ~120px wide, OCR works most of the time
  wide   - plate ~40px wide, NOT OCR-able. Models the wide-angle reality.
  analog - 704x576 D1, soft, plate ~90px. Marginal.

Run inside the feedsim container:  docker compose run --rm feedsim-synth
"""
from __future__ import annotations

import os
import random
import subprocess
import sys
from pathlib import Path

import yaml

MEDIA = Path(os.environ.get("MEDIA_DIR", "media"))
CAMERAS = Path(os.environ.get("CAMERAS_FILE", "cameras.yaml"))
FONT = os.environ.get("FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
DURATION = int(os.environ.get("CLIP_SECONDS", "60"))

SCENE = {
    #           font  car_w  car_h  speed(px/s)  blur      (plate size derives from font)
    "close":  (46,   520,   200,   170,         0.0),
    "mid":    (25,   300,   115,   210,         0.4),
    "wide":   (9,    110,   42,    260,         0.8),
    "analog": (19,   230,   90,    150,         1.2),
}


def plate_box(font: int, n_chars: int) -> tuple[int, int]:
    """Plate width/height for DejaVuSans-Bold at this size (~0.74em per glyph)."""
    return int(n_chars * font * 0.74 + font * 0.6), int(font * 1.4)

CAR_COLOURS = ["0x2d4a8a", "0x8a2d2d", "0x3a3a3a", "0xd8d8d8", "0x6b8e23", "0x8b5a2b", "0xb0b0b0"]


def vehicle_source(plate: str, scene: str, colour: str, fps: int) -> str:
    """A static canvas: car body with a white plate and black plate text, centred low."""
    font, car_w, car_h, _, _ = SCENE[scene]
    plate_w, plate_h = plate_box(font, len(plate))
    px = (car_w - plate_w) // 2
    py = car_h - plate_h - max(4, car_h // 25)
    return (
        f"color=c={colour}:s={car_w}x{car_h}:r={fps}:d={DURATION},"
        f"drawbox=x={px}:y={py}:w={plate_w}:h={plate_h}:color=white:t=fill,"
        f"drawbox=x={px}:y={py}:w={plate_w}:h={plate_h}:color=black:t=2,"
        f"drawtext=fontfile={FONT}:text='{plate}':fontsize={font}:fontcolor=black"
        f":x={px}+({plate_w}-text_w)/2:y={py}+({plate_h}-text_h)/2"
    )


def build_graph(cam: dict, width: int, height: int, fps: int) -> str:
    scene = cam.get("scene", "mid")
    _, car_w, car_h, speed, blur = SCENE[scene]
    plates = cam.get("plates") or ["GJ01XX0000"]
    road_top = int(height * 0.52)
    bg = "0x8fa8c8" if scene != "analog" else "0x7f8f9f"
    rng = random.Random(cam["code"])

    parts = [
        f"color=c={bg}:s={width}x{height}:r={fps}:d={DURATION},"
        f"drawbox=x=0:y={road_top}:w={width}:h={height - road_top}:color=0x3c3c3c:t=fill,"
        f"drawbox=x=0:y={road_top}:w={width}:h=4:color=0xb5b5b5:t=fill[bg0]"
    ]
    period = (width + car_w + 200) / speed
    # Vehicles share one speed, so evenly spaced start offsets guarantee they never overlap
    # horizontally — otherwise a car in the next lane can hide a plate for the whole loop.
    slot = period / len(plates)
    lane_step = max(0, min(int(height * 0.10), (height - road_top - car_h - 12) // 2))
    for i, plate in enumerate(plates):
        colour = CAR_COLOURS[(i * 7 + len(plate)) % len(CAR_COLOURS)]
        lane_y = road_top + 10 + (i % 3) * lane_step
        offset = i * slot + rng.uniform(0, max(0.0, slot - (car_w + 40) / speed))
        x_expr = f"(mod(t+{offset:.2f}\\,{period:.3f})*{speed})-{car_w + 100}"
        parts.append(f"{vehicle_source(plate, scene, colour, fps)}[v{i}]")
        parts.append(f"[bg{i}][v{i}]overlay=x='{x_expr}':y={lane_y}:eval=frame:shortest=1[bg{i + 1}]")

    tail = [
        f"drawtext=fontfile={FONT}:text='{cam['code']}':fontsize={max(14, height // 40)}"
        f":fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=6:x=12:y=12",
        "noise=alls=6:allf=t",
    ]
    if blur:
        tail.append(f"gblur=sigma={blur}")
    tail.append("format=yuv420p")
    parts.append(f"[bg{len(plates)}]{','.join(tail)}[out]")
    return ";".join(parts)


def encode_args(codec: str) -> list[str]:
    if codec == "h265":
        return ["-c:v", "libx265", "-preset", "ultrafast", "-tag:v", "hvc1",
                "-x265-params", "keyint=30:min-keyint=30:log-level=error"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-profile:v", "main", "-g", "30", "-keyint_min", "30", "-sc_threshold", "0"]


def render(cam: dict) -> Path:
    width, height = (int(v) for v in cam["resolution"].lower().split("x"))
    fps = int(cam.get("fps", 25))
    out = MEDIA / f"{cam['code']}.mp4"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-filter_complex", build_graph(cam, width, height, fps), "-map", "[out]",
        *encode_args(cam.get("codec", "h264")),
        "-t", str(DURATION), "-an", "-movflags", "+faststart", str(out),
    ]
    print(f"[synth] {cam['code']}: {cam['codec']} {cam['resolution']}@{fps} scene={cam.get('scene')} "
          f"plates={len(cam.get('plates', []))}", flush=True)
    subprocess.run(cmd, check=True)
    return out


def main() -> int:
    MEDIA.mkdir(parents=True, exist_ok=True)
    cams = yaml.safe_load(CAMERAS.read_text())["cameras"]
    only = set(sys.argv[1:])
    for cam in cams:
        if only and cam["code"] not in only:
            continue
        target = MEDIA / f"{cam['code']}.mp4"
        if cam.get("real"):
            print(f"[synth] {cam['code']}: real footage, prepared by realclip.py on the host")
            continue
        if target.exists() and not os.environ.get("FORCE"):
            print(f"[synth] {cam['code']}: exists, skipping (FORCE=1 to regenerate)")
            continue
        render(cam)
    print("[synth] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

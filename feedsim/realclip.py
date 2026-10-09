"""Turn a real traffic clip into a simulated camera, with every number plate replaced.

synth.py draws vehicles as coloured rectangles: fine for exercising ANPR, useless for a
general object detector, which finds nothing in them. Stock footage has real vehicles and
people, and real registration numbers, which the simulator must not carry. This script:

  1. fetches the source clip once (Pexels, free-use licence) into media/_real/
  2. crops and scales it to the camera's view, resolution and frame rate
  3. finds the number plates in every frame with the same plate detector the worker uses,
     follows each one across frames, and paints a synthetic Gujarat registration over it:
     one fixed number per vehicle, so the ANPR ground truth is known (media/<CODE>.plates.json)
     and no real registration reaches a sighting
  4. encodes with the camera's codec using the simulator image's FFmpeg (same settings as
     synth.py), so the publisher streams it with `-c copy` like every other clip

Only plates on a vehicle are painted: a plate box must sit inside a car, motorcycle, bus or
truck box from the COCO detector, or be a confident detection. Without that gate, signboards
and road texture the plate detector half-believes get "registrations" painted on them.
A plate the detector misses in a frame keeps its paint for HOLD frames, moved along with the
vehicle's last velocity; a plate it never finds is left as it is. That is good enough for a
simulator, and it is not an anonymisation guarantee.

Runs on the host, because it needs the GPU plate model:
  uv run --no-sync python feedsim/realclip.py AMD-TRAF-001 AMD-TRAF-002
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MEDIA = HERE / "media"
REAL = MEDIA / "_real"
HOLD = 8                      # frames a lost plate keeps its paint
MEMORY = 25                   # frames a lost plate keeps its registration, if it reappears nearby
RTO = ["01", "27", "38", "18", "05", "06", "03", "13", "16", "23"]
SERIES = "ABCDEFGHJKLMNPRSTUVWXYZ"   # no I or O, as issued
# Real footage is far busier than synth.py's flat scenes; left uncapped, x264 spends ~9 Mbps on a
# 1080p street and a browser wall cannot keep up. 4 Mbps is a typical CCTV main-stream setting.
RATE = ["-maxrate", "4M", "-bufsize", "8M"]


def font_path() -> str:
    import matplotlib
    return str(Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans-Bold.ttf")


FONT = font_path()


def fetch(pexels_id: int) -> Path:
    # Downloaded by hand: Pexels' terms (section 8) forbid automated collection, so this never fetches it.
    dest = REAL / f"pexels-{pexels_id}.mp4"
    if not dest.exists():
        raise SystemExit(f"[realclip] missing {dest}: download https://www.pexels.com/video/{pexels_id}/ by hand "
                         f"from the website and save it there")
    return dest


@lru_cache(maxsize=None)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size)


@lru_cache(maxsize=4096)
def _plate_master(text: str, two_rows: bool) -> np.ndarray:
    """One high-resolution rendering per registration: white plate, black border and text."""
    W, H = (360, 220) if two_rows else (520, 112)
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W - 1, H - 1], outline="black", width=7)
    lines = [text[:-4], text[-4:]] if two_rows else [text]
    size = H
    while size > 8:
        boxes = [d.textbbox((0, 0), line, font=_font(size)) for line in lines]
        tw = max(b[2] - b[0] for b in boxes)
        th = sum(b[3] - b[1] for b in boxes) * 1.25
        if tw <= W * 0.9 and th <= H * 0.86:
            break
        size -= 4
    y = (H - th) / 2
    for line, b in zip(lines, boxes):
        d.text(((W - (b[2] - b[0])) / 2 - b[0], y - b[1]), line, font=_font(size), fill="black")
        y += (b[3] - b[1]) * 1.25
    return np.asarray(im)[:, :, ::-1].copy()


def plate_image(text: str, w: int, h: int) -> np.ndarray:
    """The registration scaled to the plate's box in this frame (anti-aliased)."""
    return cv2.resize(_plate_master(text, w / max(1, h) < 2.6), (w, h), interpolation=cv2.INTER_AREA)


class Plates:
    """Follows plate boxes across frames and gives each vehicle one synthetic registration."""

    def __init__(self, code: str, avoid: set[str]):
        self.rng = random.Random(code)
        self.used = set(avoid)
        self.tracks: list[dict] = []
        self.log: list[dict] = []

    def _new_plate(self) -> str:
        while True:
            p = (f"GJ{self.rng.choice(RTO)}{self.rng.choice(SERIES)}{self.rng.choice(SERIES)}"
                 f"{self.rng.randint(1000, 9999)}")
            if p not in self.used:
                self.used.add(p)
                return p

    def update(self, boxes: list[tuple[float, float, float, float]], idx: int) -> list[dict]:
        for t in self.tracks:
            t["matched"] = False
        for x, y, w, h in sorted(boxes, key=lambda b: -b[2] * b[3]):
            cx, cy = x + w / 2, y + h / 2
            best, dist = None, 1e9
            for t in self.tracks:
                if t["matched"]:
                    continue
                tx, ty, tw, th = t["box"]
                d = np.hypot(cx - (tx + tw / 2), cy - (ty + th / 2))
                if d < max(tw, w) * min(3.0, 1.2 + 0.25 * (idx - t["last"])) and d < dist:
                    best, dist = t, d
            if best is None:
                best = {"plate": self._new_plate(), "first": idx}
                self.tracks.append(best)
                self.log.append(best)
            if "box" in best and idx > best["last"]:
                gap = idx - best["last"]
                best["v"] = ((x - best["box"][0]) / gap, (y - best["box"][1]) / gap)
            best.update(box=(x, y, w, h), last=idx, matched=True)
        self.tracks = [t for t in self.tracks if idx - t["last"] <= MEMORY]
        live = [t for t in self.tracks if t["matched"]]
        held = []
        for t in self.tracks:
            if t["matched"] or idx - t["last"] > HOLD:
                continue
            vx, vy = t.get("v", (0.0, 0.0))
            gap = idx - t["last"]
            moved = dict(t, box=(t["box"][0] + vx * gap, t["box"][1] + vy * gap, t["box"][2], t["box"][3]))
            if not any(_overlap(moved["box"], m["box"]) > 0.1 for m in live):
                held.append(moved)
        return held + live            # a held box never paints over a plate seen this frame


def _overlap(a, b) -> float:
    iw = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return iw * ih / max(1e-6, min(a[2] * a[3], b[2] * b[3]))


def detect_plates(model, img: np.ndarray, conf: float,
                  max_frac: float = 0.15) -> list[tuple[float, float, float, float, float]]:
    """Plate boxes at native resolution: large frames are tiled so small plates are found.
    Boxes wider than `max_frac` of the view are dropped: on a wide camera those are signboards
    the detector mistook for plates, and painting a registration on a hoarding is worse than useless."""
    H, W = img.shape[:2]
    tiles = [(0, 0, W, H)] if W <= 1920 else [
        (x, y, min(1920, W - x), min(1080 + 120, H - y))
        for y in range(0, H - 120, 1080) for x in range(0, W, 1920 - 160)]
    out = []
    for x0, y0, tw, th in tiles:
        r = model.predict([img[y0:y0 + th, x0:x0 + tw]], conf=conf, imgsz=1280, verbose=False,
                          device="cuda")[0]
        for b in r.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            box = (x1 + x0, y1 + y0, x2 - x1, y2 - y1, float(b.conf[0]))
            if box[2] > max_frac * W:
                continue
            if not any(abs(box[0] - o[0]) < 6 and abs(box[1] - o[1]) < 6 for o in out):
                out.append(box)
    return out


VEHICLE_CLASSES = [2, 3, 5, 7]        # COCO car, motorcycle, bus, truck


def on_vehicle(plate, vehicles, sure: float) -> bool:
    """A plate is painted when it sits inside a vehicle box, or the detector is sure of it."""
    x, y, w, h, conf = plate
    if conf >= sure:
        return True
    for vx, vy, vw, vh in vehicles:
        ix = max(0.0, min(x + w, vx + vw) - max(x, vx))
        iy = max(0.0, min(y + h, vy + vh) - max(y, vy))
        if ix * iy >= 0.6 * w * h:
            return True
    return False


def render(cam: dict, avoid: set[str]) -> None:
    sys.path.insert(0, str(HERE))
    from synth import encode_args
    from ultralytics import YOLO

    spec = cam["real"]
    code = cam["code"]
    out_w, out_h = (int(v) for v in cam["resolution"].lower().split("x"))
    fps = int(cam.get("fps", 25))
    src = fetch(spec["pexels_id"])
    cap = cv2.VideoCapture(str(src))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cx, cy, cw, ch = spec.get("crop") or (0, 0, int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                                          int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    sx, sy = out_w / cw, out_h / ch
    start, seconds = float(spec.get("start", 0)), float(spec.get("seconds", 60))
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)

    model = YOLO(str(ROOT / "models/plate-yolov11n.pt"))
    model.to("cuda")
    coco = YOLO(str(ROOT / "models/yolo11n.pt"))
    coco.to("cuda")
    sure = spec.get("sure_conf", 0.6)
    painted: dict[str, int] = {}
    plates = Plates(code, avoid)
    work = REAL / f"{code}.work.avi"
    writer = cv2.VideoWriter(str(work), cv2.VideoWriter_fourcc(*"MJPG"), fps, (out_w, out_h))
    writer.set(cv2.VIDEOWRITER_PROP_QUALITY, 97)
    n_out = int(seconds * fps)
    src_idx, frame = -1, None
    print(f"[realclip] {code}: pexels {spec['pexels_id']} crop {cw}x{ch}@({cx},{cy}) -> {out_w}x{out_h}"
          f"@{fps} {seconds:.0f}s", flush=True)
    for k in range(n_out):
        want = int(round(k / fps * src_fps))
        while src_idx < want:
            ok, frame = cap.read()
            if not ok:
                break
            src_idx += 1
        if frame is None:
            break
        view = frame[cy:cy + ch, cx:cx + cw]
        boxes = detect_plates(model, view, spec.get("plate_conf", 0.25), spec.get("max_plate_frac", 0.15))
        img = cv2.resize(view, (out_w, out_h), interpolation=cv2.INTER_AREA if sx < 1 else cv2.INTER_CUBIC)
        r = coco.predict([img], conf=0.3, classes=VEHICLE_CLASSES, imgsz=1280, verbose=False, device="cuda")[0]
        vehicles = [(x1 / sx, y1 / sy, (x2 - x1) / sx, (y2 - y1) / sy)          # back to view coordinates
                    for x1, y1, x2, y2 in (b.xyxy[0].tolist() for b in r.boxes)]
        boxes = [b[:4] for b in boxes if on_vehicle(b, vehicles, sure)]
        for t in plates.update(boxes, k):
            x, y, w, h = t["box"]
            px, py = int(x * sx - w * sx * 0.08), int(y * sy - h * sy * 0.12)      # cover the edges too
            pw, ph = int(w * sx * 1.16), int(h * sy * 1.24)
            px, py = max(0, px), max(0, py)
            pw, ph = min(pw, out_w - px), min(ph, out_h - py)
            if pw >= 6 and ph >= 3:
                img[py:py + ph, px:px + pw] = plate_image(t["plate"], pw, ph)
                painted[t["plate"]] = painted.get(t["plate"], 0) + 1
        writer.write(img)
        if k % (fps * 10) == 0:
            print(f"[realclip] {code}: {k / fps:4.0f}s, {len(plates.log)} plates so far", flush=True)
    writer.release()
    cap.release()

    target = MEDIA / f"{code}.mp4"
    subprocess.run(["docker", "compose", "run", "--rm", "-T", "--entrypoint", "ffmpeg", "feedsim-synth",
                    "-y", "-hide_banner", "-loglevel", "error", "-i", f"/app/media/_real/{work.name}",
                    *encode_args(cam.get("codec", "h264")), *RATE, "-pix_fmt", "yuv420p", "-an",
                    "-movflags", "+faststart", f"/app/media/{target.name}"], check=True, cwd=ROOT)
    work.unlink()
    truth = [{"plate": t["plate"], "first_frame": t["first"], "last_frame": t["last"],
              "frames_painted": painted.get(t["plate"], 0)} for t in plates.log]
    (MEDIA / f"{code}.plates.json").write_text(json.dumps(
        {"camera": code, "source": f"https://www.pexels.com/video/{spec['pexels_id']}/",
         "licence": "Pexels licence (free to use and modify)", "fps": fps, "plates": truth}, indent=1),
        encoding="utf-8")
    print(f"[realclip] {code}: wrote {target.name}, {len(truth)} synthetic plates "
          f"({sum(1 for t in truth if t['frames_painted'] >= fps)} visible for 1 s or more)", flush=True)


def main() -> int:
    cams = yaml.safe_load((HERE / "cameras.yaml").read_text(encoding="utf-8"))["cameras"]
    avoid = {p for c in cams for p in c.get("plates") or []}
    only = set(sys.argv[1:])
    todo = [c for c in cams if c.get("real") and (not only or c["code"] in only)]
    if not todo:
        print("[realclip] no cameras with a `real:` source" + (f" among {sorted(only)}" if only else ""))
        return 1
    for cam in todo:
        render(cam, avoid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

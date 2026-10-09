"""Check intrusion events by eye: replay a clip through the worker's object detector and
zone logic, and save the frame at every event with the zone and the triggering boxes drawn.

Verification tooling, not product: the product never stores these images (zones.py).

    uv run --no-sync python bench/zone_check.py --camera AMD-TRAF-001 --clip feedsim/media/AMD-TRAF-001.mp4 --out <folder>
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import cv2
import httpx
import numpy as np

import sentinel_analytics  # noqa: F401  (OpenCV/FFmpeg environment)
from sentinel_analytics.objects import ObjectDetector
from sentinel_analytics.zones import ZoneWatch, inside, zones_for


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", required=True)
    ap.add_argument("--clip", required=True)
    ap.add_argument("--fps", type=float, default=5.0, help="frames analysed per second of clip, as the worker")
    ap.add_argument("--loops", type=int, default=1)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    api = os.environ.get("API", "http://localhost:8000")
    tok = httpx.post(f"{api}/auth/login", json={"username": "admin", "password": os.environ.get("ADMIN_PASSWORD", "admin123")}).json()["access_token"]
    zones = zones_for({"camera_code": a.camera, "zones": httpx.get(f"{api}/cameras/{a.camera}/zones",
                                                                  headers={"Authorization": f"Bearer {tok}"}).json()})
    if not zones:
        raise SystemExit(f"{a.camera} has no zones")
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    det = ObjectDetector()
    watch = ZoneWatch(a.camera, zones)
    cap = cv2.VideoCapture(a.clip)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, round(src_fps / a.fps))
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    events, occupied_frames, analysed = 0, 0, 0
    for loop in range(a.loops):
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        for i in range(0, n_frames, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, img = cap.read()
            if not ok:
                break
            t = loop * n_frames / src_fps + i / src_fps
            h, w = img.shape[:2]
            objs = det.detect_batch([img])[0]
            analysed += 1
            in_zone = [o for o in objs for z in zones if o.label in z.classes
                       and inside(z.polygon, (o.box[0] + o.box[2] / 2) / w, (o.box[1] + o.box[3]) / h)]
            occupied_frames += bool(in_zone)
            for e in watch.update(objs, 1_790_000_000 + t, w, h, 1.0 / a.fps):
                events += 1
                vis = img.copy()
                for z in zones:
                    pts = np.array([[int(x * w), int(y * h)] for x, y in z.polygon], np.int32)
                    cv2.polylines(vis, [pts], True, (0, 200, 255), 3)
                for o in in_zone:
                    x, y, bw, bh = o.box
                    cv2.rectangle(vis, (x, y), (x + bw, y + bh), (0, 0, 255), 3)
                name = out / f"event{events:02d}_loop{loop}_t{t:05.1f}s.jpg"
                cv2.imwrite(str(name), cv2.resize(vis, (960, int(960 * h / w))))
                print(f"event {events}: t={t:.1f}s count={e['value']} dwell={e['detail']['dwell_s']}s -> {name.name}")
    print(f"{analysed} frames analysed at {a.fps} fps over {a.loops} loop(s); {occupied_frames} with a person in a zone; {events} events")


if __name__ == "__main__":
    main()

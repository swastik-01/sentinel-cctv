"""What the analytics worker sees in one frame, drawn for the deck and HLD.

Runs the worker's own detectors, OCR and attribution on a frame of a simulated camera and
draws the result: vehicle and person boxes, plate boxes, and the plate read with the type and
colour the worker would attach. The default camera replays stock traffic footage in which
every plate has been replaced by a synthetic registration (feedsim/realclip.py).

    uv run --no-sync python submission/build/objects_frame.py --camera AMD-TRAF-002 --at 5 10 15 20

With several --at values it keeps the frame with the most plates read and attributed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from sentinel_analytics.attribute import bind_parent, frame_has_colour, vehicle_colour
from sentinel_analytics.detect import PlateDetector
from sentinel_analytics.objects import ObjectDetector
from sentinel_analytics.ocr import PlateOCR
from sentinel_common import looks_like_indian_plate, normalise_plate

ROOT = Path(__file__).resolve().parents[2]
COL = {"person": (246, 130, 59), "car": (255, 255, 255), "motorcycle": (80, 220, 255), "bus": (180, 105, 255),
       "truck": (60, 200, 250), "bicycle": (200, 200, 200)}


def label(img, text, x, y, colour, scale=0.62):
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    y = max(h + 6, y)
    cv2.rectangle(img, (x, y - h - 6), (x + w + 8, y + 2), (15, 23, 42), -1)
    cv2.putText(img, text, (x + 4, y - 3), cv2.FONT_HERSHEY_SIMPLEX, scale, colour, 2, cv2.LINE_AA)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", default="AMD-TRAF-002")
    ap.add_argument("--at", type=float, nargs="+", default=[21.0], help="seconds into the clip")
    ap.add_argument("--out", default=str(ROOT / "submission/out/screens"))
    a = ap.parse_args()

    cap = cv2.VideoCapture(str(ROOT / "feedsim/media" / f"{a.camera}.mp4"))
    od, pd, ocr = ObjectDetector(), PlateDetector(), PlateOCR()
    best = None
    for at in a.at:
        cap.set(cv2.CAP_PROP_POS_MSEC, at * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        result = draw(frame, od, pd, ocr, a.camera)
        print(f"  {at:5.1f}s: {result[1]} objects, {result[2]} plates read, {result[3]} attributed")
        if best is None or result[3:1:-1] > best[3:1:-1]:
            best = result
    if best is None:
        raise SystemExit(f"cannot read {a.camera}")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"objects-{a.camera}.png"
    cv2.imwrite(str(dest), best[0])
    print(f"wrote {dest}: {best[1]} objects, {best[2]} plates read, {best[3]} attributed")
    return 0


def draw(frame, od, pd, ocr, camera):
    objs = od.detect_batch([frame])[0]
    plates = pd.detect_batch([frame])[0]
    vis = frame.copy()
    for o in objs:
        x, y, w, h = o.box
        cv2.rectangle(vis, (x, y), (x + w, y + h), COL[o.label], 2)
        label(vis, f"{o.label} {o.conf:.2f}", x, y - 2, COL[o.label], 0.5)
    shown = attributed = 0
    colour_ok = frame_has_colour(frame)
    for (x, y, w, h, _conf) in plates:
        pad = int(h * 0.15)
        text, oconf = ocr.read_many([frame[max(0, y - pad): y + h + pad, max(0, x - pad): x + w + pad]])[0]
        norm = normalise_plate(text or "")
        if not looks_like_indian_plate(norm):
            continue
        parent = bind_parent((x, y, w, h), objs)
        col = vehicle_colour(frame, parent, (x, y, w, h)) if parent and colour_ok else None
        what = " ".join(v for v in ((col[0] if col else None), (parent.label if parent else None)) if v)
        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 230, 255), 2)
        label(vis, f"{norm}" + (f" · {what}" if what else ""), x, y + h + 26, (0, 230, 255), 0.62)
        shown += 1
        attributed += bool(parent)
    label(vis, f"{camera} · worker view: {sum(o.label == 'person' for o in objs)} people, "
               f"{sum(o.label != 'person' for o in objs)} vehicles, {shown} plates read", 12, 34, (255, 255, 255), 0.8)
    return vis, len(objs), shown, attributed


if __name__ == "__main__":
    raise SystemExit(main())

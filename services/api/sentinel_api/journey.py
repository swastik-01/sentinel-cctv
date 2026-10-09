"""A vehicle's movement history as a journey: plate reads grouped into visits (stops), and
the hop between consecutive stops.

A camera reads a passing vehicle several times; a parked one, for minutes. Reads at the
same camera less than VISIT_GAP_S apart are one visit. Between visits read exactly, the
hop gets a distance (camera to camera, straight line), a travel time and the implied
speed; a speed no road vehicle manages flags the hop, because two cars carrying the same
plate (a cloned plate) or an OCR confusion are more likely than a 400 km/h car.
Visits made only of near-miss reads are kept, marked as possible misreads, and never
used for a speed.
"""
from __future__ import annotations

import math
from collections import Counter

VISIT_GAP_S = 300
IMPLAUSIBLE_KMH = 150.0
MIN_HOP_M = 1000.0          # below this, camera placement error dominates any speed


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def _mode(values: list) -> str | None:
    values = [v for v in values if v]
    return Counter(values).most_common(1)[0][0] if values else None


def visits(timeline: list[dict], plate_norm: str) -> list[dict]:
    """`timeline`: sightings in ascending time, as returned by the movement query."""
    out: list[dict] = []
    for s in timeline:
        v = out[-1] if out else None
        if v and v["camera_code"] == s["camera_code"] \
                and (s["event_ts"] - v["last_ts"]).total_seconds() <= VISIT_GAP_S:
            v["last_ts"] = s["event_ts"]
            v["reads"] += 1
            v["_rows"].append(s)
            continue
        out.append({"camera_code": s["camera_code"], "camera_name": s["camera_name"],
                    "district": s.get("district"), "department": s.get("department"),
                    "lat": s.get("lat"), "lon": s.get("lon"),
                    "first_ts": s["event_ts"], "last_ts": s["event_ts"], "reads": 1, "_rows": [s]})

    last_exact: dict | None = None
    for n, v in enumerate(out, 1):
        rows = v.pop("_rows")
        best = max(rows, key=lambda r: r.get("ocr_conf") or 0)
        v.update(n=n, plates=sorted({r["plate_norm"] for r in rows}),
                 exact=any(r["plate_norm"] == plate_norm for r in rows),
                 crop_path=best.get("crop_path"), best_read=best["plate_norm"],
                 vehicle_type=_mode([r.get("vehicle_type") for r in rows]),
                 vehicle_color=_mode([r.get("vehicle_color") for r in rows]),
                 dwell_s=round((v["last_ts"] - v["first_ts"]).total_seconds()), hop=None, hop_note=None,
                 # G3: a stop rests on reads an operator should look at (marking.py); None when marking is off
                 needs_review=(any(bool(r.get("needs_review")) for r in rows)
                               if any(r.get("needs_review") is not None for r in rows) else None))
        v["possible_misread"] = not v["exact"]
        # Why a stop has no leg, said plainly rather than left for the reader to guess.
        if not v["exact"]:
            v["hop_note"] = "possible misread: not used for speed"
            continue
        if last_exact is None:
            v["hop_note"] = "first sighting" if n == 1 else "first exact read"
        elif last_exact["camera_code"] == v["camera_code"]:
            v["hop_note"] = f"same camera as stop {last_exact['n']}"
        elif None in (last_exact["lat"], last_exact["lon"], v["lat"], v["lon"]):
            v["hop_note"] = "no camera position"
        else:
            d = haversine_m(last_exact["lat"], last_exact["lon"], v["lat"], v["lon"])
            t = (v["first_ts"] - last_exact["last_ts"]).total_seconds()
            kmh = d / t * 3.6 if t > 0 else None
            v["hop"] = {"from_n": last_exact["n"], "distance_m": round(d), "travel_s": round(t),
                        "speed_kmh": round(kmh, 1) if kmh is not None else None,
                        "implausible": d >= MIN_HOP_M and (kmh is None or kmh > IMPLAUSIBLE_KMH)}
        last_exact = v
    return out

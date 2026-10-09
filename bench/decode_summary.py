"""Summarise a software-vs-hardware decode A/B (sentinel-bench JSON files) as markdown.

    uv run --no-sync python bench/decode_summary.py <folder with r<round>_<hw>_<n>/bench_*.json> [--out bench/results/decode.md]
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--out", default="bench/results/decode.md")
    a = ap.parse_args()
    runs = defaultdict(list)            # (hw, streams) -> [case]
    meta = None
    for f in sorted(Path(a.folder).glob("r*_*_*/bench_*.json")):
        m = re.match(r"r(\d+)_(\w+)_(\d+)", f.parent.name)
        rep = json.loads(f.read_text())
        meta = meta or rep
        for case in rep["cases"]:
            runs[(m.group(2), case["streams"])].append({**case, "round": int(m.group(1))})
    rows = []
    for n in sorted({k[1] for k in runs}):
        sw, hw = runs.get(("off", n), []), runs.get(("auto", n), [])
        if not sw or not hw:
            continue
        f = lambda cs, k: statistics.mean(c[k] for c in cs)                     # noqa: E731
        rows.append(f"| {n} | {f(sw, 'analysed_fps_per_stream'):.2f} | {f(hw, 'analysed_fps_per_stream'):.2f} | "
                    f"{(f(hw, 'analysed_fps_per_stream') / f(sw, 'analysed_fps_per_stream') - 1) * 100:+.0f}% | "
                    f"{f(sw, 'sys_cpu_pct'):.0f}% | {f(hw, 'sys_cpu_pct'):.0f}% | "
                    f"{', '.join(str(c['analysed_fps_per_stream']) for c in sw)} / {', '.join(str(c['analysed_fps_per_stream']) for c in hw)} |")
    lines = [
        "# Video decode: software vs hardware (D3D11)",
        "",
        f"Measured {meta['at'][:16].replace('T', ' ')} UTC on {meta['host']} ({meta['gpu'].get('name', 'GPU?')}, {meta['cpu']}),",
        f"{meta['os']}, by `sentinel-bench` with `HW_DECODE=off` and `HW_DECODE=auto`, {runs[next(iter(runs))][0]['seconds']:.0f} s per case,",
        "two rounds in alternating order (software first, then hardware first) to spread thermal throttling across both.",
        f"Pipeline as in production: DETECTOR={meta['detector_mode']}, DETECT_FPS={meta['detect_fps_target']}, plate detector on {meta['device']}, "
        "OCR on CPU. Streams are the simulator's cameras (H.264 and H.265, 720p and 1080p), reused when more are asked for than exist.",
        "",
        "| Streams | Analysed fps per stream, software | Hardware | Change | System CPU, software | Hardware | Per round (sw / hw) |",
        "|---|---|---|---|---|---|---|",
        *rows,
        "",
        "Analysed fps per stream is what reaches the plate detector (target 5). System CPU includes everything running on the",
        "laptop (the API, database and simulator containers too). One laptop, one day: a direction and a size, not a node figure;",
        "the Plan for Scale's streams-per-node for a server GPU stays an assumption until measured on that hardware.",
    ]
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

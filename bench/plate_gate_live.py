"""The not-a-plate rule live (bench/plate_gate_gates.md, gate A5): what a worker log says about reads dropped as not a
plate on real cameras, counts only. The worker logs the drops per camera every 30 s only when there are any, so a
run with none shows no such line; the sightings it stored are counted from its per-sighting lines (never printed).

    uv run --no-sync python bench/plate_gate_live.py data/rotation-capture/worker_001_CAM06-CAM07.log
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TS = r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--out", default=str(ROOT / "bench/results/plate_gate_live.md"))
    a = ap.parse_args()
    lines = Path(a.log).read_text(encoding="utf-8", errors="replace").splitlines()
    stamps = [m.group(1) for line in lines if (m := re.match(TS, line))]
    first, last = datetime.fromisoformat(stamps[0]), datetime.fromisoformat(stamps[-1])
    status = [line for line in lines if "streams up |" in line]
    dropped: dict[str, tuple[int, int]] = {}
    for line in lines:
        if "reads dropped as not a plate" in line:
            for code, n, m in re.findall(r"([A-Z0-9-]+) (\d+)/(\d+)", line.split("gate:")[-1]):
                dropped[code] = (int(n), int(m))            # cumulative over the run: the last line is the total
    sightings = Counter(m.group(1) for line in lines
                        if (m := re.search(r"sentinel\.worker: ([A-Z0-9-]+): [A-Z0-9]+ \(ocr [\d.]+, \d+ reads?\)", line)))
    single = max((int(m.group(1)) for line in lines
                  if (m := re.search(r"single confident reads accepted \((\d+) so far\)", line))), default=0)
    fixed: dict[str, int] = {}
    for line in lines:
        if "fixed text not stored" in line:
            for code, n in re.findall(r"([A-Z0-9-]+) (\d+)", line.split("place):")[-1]):
                fixed[code] = int(n)
    up = [re.search(r"(\d+)/(\d+) streams up", s) for s in status]
    both_up = sum(1 for m in up if m and m.group(1) == m.group(2))
    cams = sorted(set(sightings) | set(dropped) | set(fixed))
    minutes = (last - first).total_seconds() / 60
    L = ["# Not-a-plate rule on real cameras: reads dropped live", "",
         f"Generated {datetime.now():%Y-%m-%d %H:%M} IST by `bench/plate_gate_live.py` from `{a.log}` "
         f"({first:%d %b %H:%M}–{last:%H:%M} IST, {minutes:.0f} min, {len(status)} status lines, every stream up on "
         f"{both_up} of them). Counts only. The rule: a read that fits a plate layout only after more than one digit "
         "was turned into a letter is dropped (`MAX_LETTERS_FROM_DIGITS=1`, `worker.check_read`).", "",
         "| Camera | Sightings stored | Reads dropped as not a plate (of reads passing the gate) | Fixed-text drops |",
         "|---|---:|---|---:|"]
    for c in cams:
        d = dropped.get(c)
        L.append(f"| {c} | {sightings.get(c, 0)} | {f'{d[0]} of {d[1]}' if d else '0 (no drop logged)'} | {fixed.get(c, 0)} |")
    L += ["", f"Single confident reads accepted on slow cameras: {single}. "
          "The worker logs the per-camera drop count only when it is above zero, so '0 (no drop logged)' means no read "
          "was dropped as not a plate in the whole run; how many reads passed the gate is then not in the log.", "",
          "Limits: one run on the two sandbox cameras that read plates; the hoarding whose phone number the rule was "
          "written for is in CAM06's view, so a zero here is the rule holding against it, not a general false-positive "
          "rate on text; letter-only signage is not covered by the rule."]
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()

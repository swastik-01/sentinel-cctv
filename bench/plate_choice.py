"""Which plate should a track report: the character vote across its reads, or its single
most confident read? Scored on the same tracks against the simulator's ground truth.

The worker writes every harvested track, with all its reads, when TRACK_LOG is set:
    TRACK_LOG=tracks.jsonl CAMERAS=... uv run --no-sync sentinel-worker
    uv run --no-sync python bench/plate_choice.py tracks.jsonl [more.jsonl] [--out bench/results/plate_choice.md]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import yaml
from sentinel_common import looks_like_indian_plate, normalise_plate

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("anpr_eval", ROOT / "scripts" / "anpr_eval.py")
anpr_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(anpr_eval)


def rules(t: dict) -> dict[str, str]:
    best, voted = t["best"], t["voted"]
    valid_vote = voted if looks_like_indian_plate(voted) else best
    return {
        "vote": valid_vote,                                       # what the 24 Sep worker stores
        "best read": best,                                        # what the 23 Sep worker stored
        # A confident single read beats a vote the reads do not agree on.
        "best if confident, else vote": best if t["best_conf"] >= 0.9 or t["agreement"] < 0.99 else valid_vote,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    cams = {c["code"]: c for c in yaml.safe_load((ROOT / "feedsim" / "cameras.yaml").read_text(encoding="utf-8"))["cameras"]}
    lines = ["# Plate choice per track: vote or best single read", ""]
    for log in a.logs:
        tracks = [json.loads(x) for x in Path(log).read_text(encoding="utf-8").splitlines() if x.strip()]
        score = defaultdict(lambda: defaultdict(lambda: [0, 0]))      # camera -> rule -> [exact, n]
        for t in tracks:
            truth = anpr_eval.load_truth(cams[t["camera"]]) if t["camera"] in cams else None
            if not truth:
                continue
            for name, plate in rules(t).items():
                s = score[t["camera"]][name]
                s[0] += normalise_plate(plate) in truth["plates"]
                s[1] += 1
        lines += [f"## {Path(log).name} ({len(tracks)} tracks)", "",
                  "| Camera | Tracks | " + " | ".join(rules({"best": "", "voted": "", "best_conf": 0, "agreement": 0})) + " |",
                  "|---|---|" + "---|" * 3]
        tot = defaultdict(lambda: [0, 0])
        for cam, by_rule in sorted(score.items()):
            n = next(iter(by_rule.values()))[1]
            cells = []
            for name, (ok, m) in by_rule.items():
                cells.append(f"{ok / m:.1%} ({ok}/{m})")
                tot[name][0] += ok; tot[name][1] += m
            lines.append(f"| {cam} | {n} | " + " | ".join(cells) + " |")
        lines.append("| **all** | | " + " | ".join(f"**{ok / m:.1%}** ({ok}/{m})" for ok, m in tot.values()) + " |")
        lines.append("")
    lines += ["Exact = the track's reported plate is one of that camera's ground-truth plates (synthetic registrations",
              "painted on stock footage, or drawn by the simulator). Same tracks for every rule; only the choice differs."]
    text = "\n".join(lines) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()

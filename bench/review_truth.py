"""How right are the reviewers themselves? On our own cameras the true plates are known (feedsim/cameras.yaml for the
synthetic clips, feedsim/media/<CODE>.plates.json for the painted stock clips), so each review on those cameras can be
scored twice: the reviewer's reading against the truth, and Sentinel's stored read against the truth. This checks the
blind-review method before its figures on real plates (the sandbox, no ground truth) are trusted. Read-only.

    uv run --no-sync python bench/review_truth.py [--mode blind]   # -> bench/results/review_truth.md
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import yaml

from sentinel_api.config import get_settings
from sentinel_common import normalise_plate

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))


def truth() -> dict[str, set[str]]:
    """Known plates per camera. Stock clips: only the plates we painted; any other plate in view is unknown."""
    out: dict[str, set[str]] = {}
    for cam in yaml.safe_load((ROOT / "feedsim" / "cameras.yaml").read_text(encoding="utf-8"))["cameras"]:
        if cam.get("plates"):
            out[cam["code"]] = {normalise_plate(p) for p in cam["plates"]}
    for f in (ROOT / "feedsim" / "media").glob("*.plates.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        out[d["camera"]] = {normalise_plate(p["plate"]) for p in d["plates"]}
    return out


def edits(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def nearest(p: str, known: set[str]) -> int:
    return min(edits(p, k) for k in known)


async def reviews(mode: str):
    conn = await asyncpg.connect(get_settings().pg_dsn)
    try:
        return await conn.fetch(
            """SELECT c.camera_code, u.username, r.seen, r.stored_plate, r.verdict FROM plate_reviews r
               JOIN cameras c ON c.id = r.camera_id JOIN users u ON u.id = r.reviewer_id WHERE r.mode = $1""", mode)
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="blind", choices=["blind", "verify"])
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "review_truth.md"))
    a = ap.parse_args()
    known = truth()
    rows = [r for r in asyncio.run(reviews(a.mode)) if r["camera_code"] in known]
    per: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        k, c = known[r["camera_code"]], per[r["camera_code"]]
        c["n"] += 1
        seen = normalise_plate(r["seen"] or "") if r["seen"] not in ("?", "-", None) else None
        stored = normalise_plate(r["stored_plate"])
        if seen is None:
            c["reviewer_skipped"] += 1                       # typed unreadable / not a plate
        else:
            d = nearest(seen, k)
            c["reviewer_right" if d == 0 else "reviewer_one_off" if d == 1 else "reviewer_far"] += 1
        d = nearest(stored, k)
        c["sentinel_right" if d == 0 else "sentinel_one_off" if d == 1 else "sentinel_far"] += 1
        # where the page's verdict and the truth disagree, who was wrong?
        if seen is not None and r["verdict"] in ("one_off", "wrong"):
            c["disagree"] += 1
            if nearest(stored, k) == 0 and nearest(seen, k) > 0:
                c["disagree_reviewer_wrong"] += 1
            elif nearest(seen, k) == 0 and nearest(stored, k) > 0:
                c["disagree_sentinel_wrong"] += 1
            else:
                c["disagree_both_or_unknown"] += 1
    pct = lambda x, n: f"{x} ({100 * x / n:.1f}%)" if n else "—"
    who = Counter(r["username"] for r in rows)
    L = [f"# Blind review checked against known plates ({a.mode} mode)", "",
         f"Generated {datetime.now(IST):%Y-%m-%d %H:%M} IST by `bench/review_truth.py` (read-only). Reviews on our own "
         "cameras, where the true plates are known: the synthetic clips' plates (`feedsim/cameras.yaml`) and the plates "
         "painted on the two stock clips (`feedsim/media/*.plates.json`; other vehicles there carry real, unlabelled "
         "plates, so a read matching none of the painted ones counts as 'far'). Reviewers: "
         + ", ".join(f"{u} {n}" for u, n in who.most_common()) + ".", "",
         "Each review is scored twice. *Reviewer*: the plate the person typed against the known plates. *Sentinel*: "
         "the stored read against the known plates. *Disagreements*: reviews the page graded one-off or wrong; the "
         "truth says whose reading was wrong.", "",
         "| Camera | Reviews | Reviewer right | Reviewer one off | Sentinel right | Sentinel one off | "
         "Disagreements | …reviewer wrong | …Sentinel wrong | …both or unknown |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    tot = Counter()
    for cam in sorted(per):
        c = per[cam]
        tot.update(c)
        typed = c["n"] - c["reviewer_skipped"]
        L.append(f"| {cam} | {c['n']} | {pct(c['reviewer_right'], typed)} | {c['reviewer_one_off']} | "
                 f"{pct(c['sentinel_right'], c['n'])} | {c['sentinel_one_off']} | {c['disagree']} | "
                 f"{c['disagree_reviewer_wrong']} | {c['disagree_sentinel_wrong']} | {c['disagree_both_or_unknown']} |")
    typed = tot["n"] - tot["reviewer_skipped"]
    L.append(f"| **All** | {tot['n']} | {pct(tot['reviewer_right'], typed)} | {tot['reviewer_one_off']} | "
             f"{pct(tot['sentinel_right'], tot['n'])} | {tot['sentinel_one_off']} | {tot['disagree']} | "
             f"{tot['disagree_reviewer_wrong']} | {tot['disagree_sentinel_wrong']} | {tot['disagree_both_or_unknown']} |")
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[6:]))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

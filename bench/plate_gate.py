"""How well would a rule on the OCR read tell a plate from other text? Measured on the frozen OCR test sets
(bench/ocr_sets.py) and on the stored sandbox sightings our AI coding assistant labelled (with the stored read in view:
not a person, not blind), reading every crop exactly as bench/ocr_ab.py does (the product's PlateOCR.read_many,
weakest-character confidence, normalise_plate, the worker gate).

    PYTHONUTF8=1 uv run --no-sync python bench/plate_gate.py [--out bench/results/plate_gate.md]

Each rule is applied on top of the current worker gate (confidence >= min_ocr_conf and looks_like_indian_plate), so
it can only remove reads. Digits turned into letters are counted by the product's letters_from_digits, the count
the worker's rule uses (1e-k2 here). For the other rules, normalise_plate is replayed step by step to count how each
character was repaired; on every read the replay is checked against normalise_plate and against the product helper
(bench/plate_gate_gates.md A0), and the mismatch counts are written to the results:
  - digit -> letter in the state code (positions 1-2), in the series letters, or in a BH plate's letters;
  - letter -> digit anywhere; a look-alike letter swap that made the state code valid (_fix_state).
The stored sightings keep only the normalised text (sink.py stores plate_norm as plate_text), so the raw read is
recovered by re-reading the stored evidence crop.

Test only: nothing here is trained on. Counts only in the output; no plate text or crop path is printed or written.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocr_ab import BATCH, load_model, load_set  # noqa: E402  (sets the CPU-only environment first)

import argparse  # noqa: E402
import csv  # noqa: E402
import json  # noqa: E402
from collections import Counter  # noqa: E402
from datetime import datetime  # noqa: E402
from importlib.metadata import version  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from sentinel_analytics.config import get_settings  # noqa: E402
from sentinel_common import letters_from_digits, looks_like_indian_plate, normalise_plate  # noqa: E402
from sentinel_common.plates import _BH, _STD, STATE_CODES, _clean, _fix_state, _repair_bh, _repair_standard  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "ocr-eval"
LABELS = ROOT / "data" / "gov-sandbox" / "eye" / "labels.csv"
SETS = ("reject-v1", "sandbox-v1", "ownfeed-v1")
VERDICTS = ("not_a_plate", "exact", "one_off", "wrong", "unreadable")


def trace(raw: str) -> dict:
    """Replay normalise_plate, counting each repair by the role of the position it touched."""
    s = _clean(raw)
    t = {"clean_len": len(s), "letters": sum(c.isalpha() for c in s), "digits_only": bool(s) and s.isdigit(),
         "state_as_read": s[:2] in STATE_CODES, "lead_digits": len(s) >= 2 and s[:2].isdigit(), "path": "empty",
         "d2l_state": 0, "d2l_series": 0, "d2l_bh": 0, "l2d": 0, "lookalike": 0}
    if not s:
        t["norm"] = ""
        return t
    if _BH.match(s):
        t.update(path="bh", norm=s)
        return t
    cur = s
    if _STD.match(s):
        t["path"] = "std"
    else:
        rep, roles = _repair_standard(s), None
        if rep:
            t["path"], roles = "std-repaired", ["state"] * 2 + ["rto"] * 2 + ["series"] * (len(s) - 8) + ["num"] * 4
        else:
            rep = _repair_bh(s)
            if rep:
                t["path"], roles = "bh-repaired", ["yy"] * 2 + ["bh"] * 2 + ["num"] * 4 + ["bh"] * (len(s) - 8)
        if rep:
            for a, b, role in zip(s, rep, roles):
                if a.isdigit() and b.isalpha():
                    t["d2l_" + ("series" if role == "series" else "state" if role == "state" else "bh")] += 1
                elif a.isalpha() and b.isdigit():
                    t["l2d"] += 1
            cur = rep
        else:
            t["path"] = "fallback"
    m = _STD.match(cur)
    if m and m.group(1) not in STATE_CODES:
        fixed = _fix_state(m.group(1))
        t["lookalike"] = sum(a != b for a, b in zip(fixed, m.group(1)))
        cur = fixed + cur[2:]
    t["norm"] = cur
    return t


def d2l(t: dict) -> int:
    return t["from_digits"]          # the product helper, set by judge()


def replay_d2l(t: dict) -> int:
    return t["d2l_state"] + t["d2l_series"] + t["d2l_bh"]


# source -> reads checked, and where the product helper or normalise_plate disagreed with the replay (want 0, 0)
PARITY: dict[str, Counter] = {}


# name -> (family, description, keep(trace, conf) -> bool). Each is applied on top of the current gate.
RULES = {
    "conf-0.50": ("confidence", "weakest character >= 0.50 (now 0.35)", lambda t, c: c >= 0.50),
    "conf-0.70": ("confidence", "weakest character >= 0.70", lambda t, c: c >= 0.70),
    "conf-0.90": ("confidence", "weakest character >= 0.90", lambda t, c: c >= 0.90),
    "1a-state-any": ("repair budget", "reject if a state-code letter was made from a digit",
                     lambda t, c: t["d2l_state"] == 0),
    "1b-state-both": ("repair budget", "reject if both state-code letters were made from digits",
                      lambda t, c: t["d2l_state"] < 2),
    "1b-simple": ("repair budget", "1b as a one-line check: the raw read starts with two digits and is not a BH plate",
                  lambda t, c: not (t["lead_digits"] and not _BH.match(t["norm"]))),
    "1c-series": ("repair budget", "reject if a series letter was made from a digit", lambda t, c: t["d2l_series"] == 0),
    "1d-k1": ("repair budget", "reject if any letter was made from a digit (k >= 1)", lambda t, c: d2l(t) < 1),
    "1e-k2": ("repair budget", "reject if 2 or more letters were made from digits", lambda t, c: d2l(t) < 2),
    "1f-k3": ("repair budget", "reject if 3 or more letters were made from digits", lambda t, c: d2l(t) < 3),
    "1g-all-digits": ("repair budget", "reject if the raw read has no letters at all", lambda t, c: not t["digits_only"]),
    "1h-state-touched": ("repair budget", "reject if the state code was changed at all (digit or look-alike)",
                         lambda t, c: t["d2l_state"] == 0 and t["lookalike"] == 0),
    "1i-any-repair": ("repair budget", "reject if any character was repaired (reference: the strictest rule)",
                      lambda t, c: d2l(t) + t["l2d"] + t["lookalike"] == 0),
    "2a-state-as-read": ("state code", "raw read starts with a real state/UT code, or is a BH plate as read",
                         lambda t, c: t["state_as_read"] or t["path"] == "bh"),
    "2b-state-or-bh": ("state code", "raw read starts with a real state/UT code, or normalises to a BH plate",
                       lambda t, c: t["state_as_read"] or bool(_BH.match(t["norm"]))),
    "2c-no-lookalike": ("state code", "state code valid after the digit repair, without the look-alike swap",
                        lambda t, c: t["lookalike"] == 0),
    "2b+1c": ("combined", "2b, and no series letter made from a digit",
              lambda t, c: (t["state_as_read"] or bool(_BH.match(t["norm"]))) and t["d2l_series"] == 0),
}


def read_all(ocr, imgs: list) -> list[tuple[str, float]]:
    ocr.read_many([i for i in imgs[:BATCH] if i is not None])   # warm-up, as ocr_ab.score does
    out = []
    for i in range(0, len(imgs), BATCH):
        out += ocr.read_many(imgs[i:i + BATCH])
    return out


def judge(text: str, conf: float, min_conf: float, source: str) -> tuple[dict, bool, dict]:
    t = trace(text)
    norm = normalise_plate(text)
    t["from_digits"] = letters_from_digits(text)
    par = PARITY.setdefault(source, Counter())
    par["reads"] += 1
    par["helper_vs_replay"] += t["from_digits"] != replay_d2l(t)
    par["normalise_vs_replay"] += t["norm"] != norm
    gate = bool(text) and conf >= min_conf and looks_like_indian_plate(norm)
    return t, gate, {r: gate and keep(t, conf) for r, (_, _, keep) in RULES.items()}


def quantiles(xs: list[float]) -> dict:
    if not xs:
        return {}
    q = np.percentile(xs, [10, 50, 90])
    return {"p10": round(float(q[0]), 3), "median": round(float(q[1]), 3), "p90": round(float(q[2]), 3)}


def score_set(ocr, name: str, min_conf: float) -> dict:
    rows, imgs = load_set(EVAL / name / "manifest.csv")
    reads = read_all(ocr, imgs)
    labelled = any(r["true_plate"] for r in rows)
    prev = EVAL / "runs" / f"ocr_baseline__{name}__{get_settings().ocr_model}.csv"
    same = None
    if prev.exists():   # the reads must be the product's: compare with the stored ocr_ab baseline run
        with open(prev, encoding="utf-8") as f:
            old = {r["id"]: r["read"] for r in csv.DictReader(f)}
        same = sum(old.get(r["id"]) == text for r, (text, _) in zip(rows, reads))
    groups = sorted({r["group"] for r in rows})
    res = {"n": len(rows), "groups": len(groups), "labelled": labelled, "reads_same_as_ocr_baseline": same,
           "paths": Counter(), "gate": 0, "gate_exact": 0, "gate_wrong": 0, "conf_all": [], "rules": {}}
    per_rule = {r: {"kept": 0, "exact_lost": 0, "wrong_removed": 0, "grp_kept": Counter()} for r in RULES}
    grp_gate = Counter()
    for r, (text, conf) in zip(rows, reads):
        t, gate, keep = judge(text, conf, min_conf, name)
        res["paths"][t["path"]] += 1
        res["conf_all"].append(conf)
        exact = labelled and normalise_plate(text) == r["true_plate"]
        res["gate"] += gate
        res["gate_exact"] += gate and exact
        res["gate_wrong"] += gate and not exact
        grp_gate[r["group"]] += gate
        for rule, k in keep.items():
            p = per_rule[rule]
            p["kept"] += k
            p["grp_kept"][r["group"]] += k
            if gate and not k:
                p["exact_lost" if exact else "wrong_removed"] += 1
    for rule, p in per_rule.items():
        live = [g for g in groups if grp_gate[g]]
        res["rules"][rule] = {"kept": p["kept"], "rejected": res["gate"] - p["kept"],
                              "exact_lost": p["exact_lost"], "wrong_removed": p["wrong_removed"],
                              "groups_all_rejected": sum(1 for g in live if not p["grp_kept"][g]),
                              "groups_with_gate": len(live)}
    res["paths"] = dict(res["paths"])
    res["conf"] = quantiles(res.pop("conf_all"))
    return res


def score_labels(ocr, min_conf: float) -> dict:
    with open(LABELS, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    imgs = []
    for r in rows:
        p = ROOT / "data" / r["crop"].lstrip("/")
        imgs.append(cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR) if p.exists() else None)
    reads = read_all(ocr, imgs)
    res = {"n": len(rows), "missing_crops": sum(i is None for i in imgs), "verdicts": Counter(),
           "gate": Counter(), "reread_matches_stored": Counter(), "cameras": Counter(),
           "rules": {rule: Counter() for rule in RULES}, "conf": {}}
    confs: dict[str, list[float]] = {}
    for r, (text, conf) in zip(rows, reads):
        v = r["verdict"]
        t, gate, keep = judge(text, conf, min_conf, "stored sightings")
        res["verdicts"][v] += 1
        res["cameras"][r["camera"]] += 1
        res["gate"][v] += gate
        res["reread_matches_stored"][v] += normalise_plate(text) == r["stored"]
        confs.setdefault(v, []).append(conf)
        for rule, k in keep.items():
            res["rules"][rule][v] += gate and not k
    res["conf"] = {v: quantiles(x) for v, x in confs.items()}
    for k in ("verdicts", "gate", "reread_matches_stored", "cameras"):
        res[k] = dict(res[k])
    res["rules"] = {k: dict(v) for k, v in res["rules"].items()}
    return res


def score_synth_plates(ocr, min_conf: float) -> dict:
    """The held-out synthetic split (bench/plategen.py test, never trained on): unlike ownfeed-v1 it has other
    states' plates and BH plates, the layouts a digit-led rule could hurt."""
    base = ROOT / "data" / "ocr-train"
    with open(base / "test.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with open(base / "test_meta.csv", encoding="utf-8") as f:
        kind = {r["image_path"]: r["kind"] for r in csv.DictReader(f)}
    imgs = [cv2.imdecode(np.fromfile(str(base / r["image_path"]), np.uint8), cv2.IMREAD_COLOR) for r in rows]
    reads = read_all(ocr, imgs)
    res = {"n": Counter(), "gate": Counter(), "gate_exact": Counter(), "rules": {r: Counter() for r in RULES}}
    for r, (text, conf) in zip(rows, reads):
        k = kind.get(r["image_path"], "?")
        _, gate, keep = judge(text, conf, min_conf, "synthetic plates")
        exact = normalise_plate(text) == r["plate_text"]
        res["n"][k] += 1
        res["gate"][k] += gate
        res["gate_exact"][k] += gate and exact
        for rule, kept in keep.items():
            res["rules"][rule][k] += gate and exact and not kept      # exact reads lost
    return {k: (dict(v) if isinstance(v, Counter) else {r: dict(c) for r, c in v.items()}) for k, v in res.items()}


# Synthetic non-plate text of the kinds a plate detector fires on near a road: rendered here, never saved, test only.
SHOP = ["SHREE", "GANESH", "MEDICAL", "STORE", "SALE", "OFF", "HOTEL", "PAN", "CENTRE", "MOBILE", "BANK", "ATM",
        "SCHOOL", "HOSPITAL", "TRADERS", "JEWELLERS", "OPEN", "PARKING", "NO", "ENTRY", "TEA", "STALL", "KIRANA",
        "AUTO", "PARTS", "TYRES", "SWEETS", "FARSAN", "CLINIC", "XEROX"]
TRUCK = ["HORN OK PLEASE", "USE DIPPER AT NIGHT", "ON GOVT DUTY", "POLICE", "TAXI", "SCHOOL BUS", "TATA",
         "ASHOK LEYLAND", "GSRTC", "AMTS", "BRTS", "PRESS", "DOCTOR", "IND", "OK TATA", "AMBULANCE", "108"]


def probe_text(kind: str, rng) -> str:
    d = lambda n: "".join(rng.choice("0123456789") for _ in range(n))   # noqa: E731
    if kind == "mobile":
        num = rng.choice("6789") + d(9)
        return rng.choice([num, f"{num[:5]} {num[5:]}", f"+91 {num[:5]} {num[5:]}", f"MO. {num}", f"CALL {num}"])
    if kind == "landline":
        return rng.choice([f"079-{d(8)}", f"(0{d(2)}) {d(8)}", f"0{d(2)} {d(4)} {d(4)}", f"TEL {d(4)}{d(4)}"])
    if kind == "timestamp":
        dd, mm, hh, mi, ss = rng.randint(1, 28), rng.randint(1, 12), rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59)
        return rng.choice([f"{dd:02d}-{mm:02d}-2026 {hh:02d}:{mi:02d}:{ss:02d}", f"2026-{mm:02d}-{dd:02d} {hh:02d}:{mi:02d}:{ss:02d}",
                           f"{dd:02d}/{mm:02d}/2026", f"{hh:02d}:{mi:02d}:{ss:02d}"])
    if kind == "overlay":
        return rng.choice([f"CAM{d(2)}", f"CAM {rng.randint(1, 16)}", f"CH{d(2)}", f"GATE {rng.randint(1, 9)}",
                           f"{rng.choice(['AMD', 'GNR', 'SRT', 'RJK'])}-{rng.choice(['POL', 'AMC', 'TRAF'])}-{d(3)}"])
    if kind == "shop":
        return " ".join(rng.sample(SHOP, rng.randint(1, 3)))
    if kind == "shop-number":
        return rng.choice([f"SHOP NO {rng.randint(1, 99)}", f"PLOT {rng.randint(1, 999)}", f"PIN 3{d(5)}",
                           f"ROUTE {rng.randint(1, 200)}", f"BUS {d(3)}", f"SINCE 19{d(2)}", f"ROOM {d(3)}",
                           "GST 24" + "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(5)) + d(4) + "A1Z" + d(1)])
    if kind == "vehicle-text":
        return rng.choice(TRUCK)
    if kind == "fleet-number":
        return rng.choice([f"AMTS {d(4)}", f"BRTS {d(3)}", f"P {d(5)}", f"DEPOT {d(2)}", f"NO. {d(4)}", d(4), d(6)])
    raise ValueError(kind)


PROBE_RULES = ("conf-0.70", "1b-state-both", "1e-k2", "1g-all-digits", "2a-state-as-read", "2b+1c")
PROBE_KINDS = ("mobile", "landline", "timestamp", "overlay", "shop", "shop-number", "vehicle-text", "fleet-number")
PROBE_FONTS = [str(Path(__import__("matplotlib").get_data_path()) / "fonts/ttf/DejaVuSans-Bold.ttf"),
               str(Path("C:/Windows/Fonts/arialbd.ttf")), str(Path("C:/Windows/Fonts/bahnschrift.ttf"))]
SIGN = [((255, 255, 255), (0, 0, 0)), ((255, 220, 0), (0, 0, 0)), ((200, 20, 20), (255, 255, 255)),
        ((20, 60, 160), (255, 255, 255)), ((0, 0, 0), (255, 255, 255)), ((20, 120, 50), (255, 255, 255)),
        ((0, 0, 0), (255, 220, 0))]   # (background, text) in RGB


def render_probe(text: str, rng) -> np.ndarray:
    """Text on a sign colour, cropped as the worker crops a detected box (15% of its height as padding), shrunk to a
    CCTV-sized crop, blurred, noised and JPEG-coded like a stored evidence crop."""
    from PIL import Image, ImageDraw, ImageFont
    fonts = [p for p in PROBE_FONTS if Path(p).exists()]
    f = ImageFont.truetype(rng.choice(fonts), 64)
    lines = text.split(" ", 1) if (len(text) > 12 and rng.random() < 0.3) else [text]
    boxes = [ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), ln, font=f) for ln in lines]
    tw, th = max(b[2] - b[0] for b in boxes), sum(b[3] - b[1] for b in boxes) + 12 * (len(lines) - 1)
    bg, fg = rng.choice(SIGN)
    mx, my = rng.randint(8, 30), rng.randint(6, 20)
    img = Image.new("RGB", (tw + 2 * mx, th + 2 * my), bg)
    dr, y = ImageDraw.Draw(img), my
    for ln, b in zip(lines, boxes):
        dr.text((mx + (tw - (b[2] - b[0])) // 2 - b[0], y - b[1]), ln, font=f, fill=fg)
        y += b[3] - b[1] + 12
    a = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    pad = int(a.shape[0] * 0.15)
    surround = rng.randint(40, 200)
    a = cv2.copyMakeBorder(a, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(surround,) * 3)
    w = rng.randint(60, 200)
    a = cv2.resize(a, (w, max(14, int(a.shape[0] * w / a.shape[1]))), interpolation=cv2.INTER_AREA)
    if rng.random() < 0.6:
        a = cv2.GaussianBlur(a, (3, 3), rng.uniform(0.3, 1.2))
    a = np.clip(a.astype(np.float32) + np.random.default_rng(rng.randint(0, 2**31)).normal(0, rng.uniform(0, 8), a.shape),
                0, 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", a, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return cv2.imdecode(enc, cv2.IMREAD_COLOR)


def score_probe(ocr, min_conf: float, per_kind: int, seed: int) -> dict:
    import random
    rng = random.Random(seed)
    kinds, imgs = [], []
    for k in PROBE_KINDS:
        for _ in range(per_kind):
            kinds.append(k)
            imgs.append(render_probe(probe_text(k, rng), rng))
    reads = read_all(ocr, imgs)
    res = {"per_kind": per_kind, "seed": seed, "n": Counter(), "gate": Counter(), "rules": {r: Counter() for r in RULES}}
    for k, (text, conf) in zip(kinds, reads):
        _, gate, keep = judge(text, conf, min_conf, f"probe seed {seed}")
        res["n"][k] += 1
        res["gate"][k] += gate
        for rule, kept in keep.items():
            res["rules"][rule][k] += kept          # still passes with the rule
    return {k: (dict(v) if isinstance(v, Counter) else {r: dict(c) for r, c in v.items()} if isinstance(v, dict) else v)
            for k, v in res.items()}


def markdown(res: dict) -> str:
    c, sets, lab = res["conditions"], res["sets"], res["labels"]
    rj, sb, ow = sets["reject-v1"], sets["sandbox-v1"], sets["ownfeed-v1"]
    out = [
        "# Not-a-plate gate: rules on the OCR read", "",
        f"Generated {res['generated']} by `bench/plate_gate.py`. OCR `{c['ocr_model']}` (fast-plate-ocr "
        f"{c['fast_plate_ocr']}, onnxruntime {c['onnxruntime']}, CPU, {c['threads']} threads, batches of {c['batch']}), "
        "read through the product's `PlateOCR.read_many`, `normalise_plate` and the worker gate (weakest character "
        f">= {c['min_ocr_conf']} and `looks_like_indian_plate`). Each rule is applied on top of that gate, so it can "
        "only remove reads. Digits turned into letters are counted by the product helper `letters_from_digits` "
        "(the count the worker's rule uses); the per-role counts the other rules need come from a step-by-step "
        "replay of `normalise_plate`, checked on every read against `normalise_plate` and against the helper "
        "(below). Counts only: no plate text is written here.", "",
        "Implementation parity (`bench/plate_gate_gates.md` A0), reads where the product helper's count differs "
        "from the replay's / where `normalise_plate` differs from the replay: " + "; ".join(
            f"{k} {v['helper_vs_replay']} / {v['normalise_vs_replay']} of {v['reads']:,}"
            for k, v in res["parity"].items()) + ".", "",
        "Reads identical to the stored `ocr_ab.py` baseline run: " + "; ".join(
            f"{k} {v['reads_same_as_ocr_baseline']}/{v['n']}" for k, v in sets.items()
            if v["reads_same_as_ocr_baseline"] is not None) + ".", "",
        "## Frozen test sets", "",
        f"- **reject-v1**: {rj['n']} real sandbox crops our AI coding assistant labelled not a plate (with the "
        f"stored read in view: not a person, not blind), {rj['groups']} groups (one group "
        f"= one piece of fixed text, so the set is really {rj['groups']} texts, all on one camera). "
        f"{rj['gate']} pass the current gate.",
        f"- **sandbox-v1**: {sb['n']} real plate crops, labelled the same way (one camera, {sb['groups']} groups). "
        f"{sb['gate']} pass the gate: "
        f"{sb['gate_exact']} exact, {sb['gate_wrong']} wrong.",
        f"- **ownfeed-v1**: {ow['n']:,} crops of synthetic plates painted on stock footage ({ow['groups']} vehicles). "
        f"{ow['gate']:,} pass the gate: {ow['gate_exact']:,} exact, {ow['gate_wrong']} wrong.", "",
        "Columns: *caught* = reads of non-plates the rule removes (want all); *exact lost* = correct plate reads it "
        "removes (want none); *wrong removed* = misread plates it removes (a side benefit); *vehicles gone* = groups "
        "whose every passing crop is removed.", "",
        f"| Rule | reject-v1 caught (of {rj['gate']}) | texts fully caught (of {rj['groups']}) | sandbox-v1 exact lost "
        f"(of {sb['gate_exact']}) | sandbox-v1 wrong removed (of {sb['gate_wrong']}) | ownfeed-v1 exact lost "
        f"(of {ow['gate_exact']:,}) | ownfeed-v1 wrong removed (of {ow['gate_wrong']}) | ownfeed-v1 vehicles gone "
        f"(of {ow['rules']['1a-state-any']['groups_with_gate']}) |",
        "|---|---|---|---|---|---|---|---|"]
    for rule, (fam, desc, _) in RULES.items():
        a, b, o = rj["rules"][rule], sb["rules"][rule], ow["rules"][rule]
        out.append(f"| `{rule}` {desc} | {a['rejected']} | {a['groups_all_rejected']} | {b['exact_lost']} | "
                   f"{b['wrong_removed']} | {o['exact_lost']} | {o['wrong_removed']} | {o['groups_all_rejected']} |")
    out += ["", "How the reads reached a valid layout (path through `normalise_plate`): " + "; ".join(
        f"{k} {v['paths']}" for k, v in sets.items()) + ".", "",
        "Weakest-character confidence (p10 / median / p90): " + "; ".join(
            f"{k} {v['conf']['p10']} / {v['conf']['median']} / {v['conf']['p90']}" for k, v in sets.items()) + ".", ""]
    n, g = lab["verdicts"], lab["gate"]
    out += [
        "## Stored sandbox sightings, labelled by our AI coding assistant", "",
        f"{lab['n']} stored sightings from the organisers' sandbox ({', '.join(f'{k} {v}' for k, v in sorted(lab['cameras'].items()))}), "
        "each labelled by our AI coding assistant from its own evidence crop with the stored read in view "
        "(`data/gov-sandbox/eye/labels.csv`): not by a person and not blind, so a label may lean towards the stored "
        "read. The team's blind check is separate (`bench/plate_gate_gates.md` A5). The stored text is the "
        "track's vote and the raw read was not kept, so each evidence crop (the track's best read) is read again with "
        "the product OCR. This set includes the crops frozen into sandbox-v1 and reject-v1, plus sightings labelled "
        f"after those sets were frozen. Missing crops: {lab['missing_crops']}.", "",
        "Re-read agrees with the stored text after normalising: " + "; ".join(
            f"{v} {lab['reread_matches_stored'].get(v, 0)}/{n.get(v, 0)}" for v in VERDICTS if n.get(v)) + ". "
        "Re-read passes the current gate: " + "; ".join(f"{v} {g.get(v, 0)}/{n.get(v, 0)}" for v in VERDICTS if n.get(v))
        + ".", "",
        "Dropped by each rule (of the sightings whose re-read passes the current gate):", "",
        "| Rule | " + " | ".join(f"{v} (of {g.get(v, 0)})" for v in VERDICTS if n.get(v)) + " |",
        "|---|" + "---|" * sum(1 for v in VERDICTS if n.get(v))]
    for rule, (_, desc, _) in RULES.items():
        out.append(f"| `{rule}` | " + " | ".join(str(lab["rules"][rule].get(v, 0)) for v in VERDICTS if n.get(v)) + " |")
    out += ["", "Weakest-character confidence by verdict (p10 / median / p90): " + "; ".join(
        f"{v} {q['p10']} / {q['median']} / {q['p90']}" for v, q in lab["conf"].items() if q) + ".", ""]
    sp = res["synth_plates"]
    kinds = [k for k in ("GJ", "other", "BH") if sp["n"].get(k)]
    out += [
        "## Synthetic held-out plates (other states and BH)", "",
        f"`data/ocr-train/test.csv` from `bench/plategen.py`, never trained on: {sum(sp['n'].values()):,} synthetic plates ("
        + ", ".join(f"{k} {sp['n'][k]}" for k in kinds) + "). ownfeed-v1 is all GJ, so this is where a rule would show a "
        "cost on other states' plates and on BH plates, which start with digits. Exact reads that pass the current gate: "
        + ", ".join(f"{k} {sp['gate_exact'].get(k, 0)}" for k in kinds) + ".", "",
        "| Rule | " + " | ".join(f"{k} exact lost (of {sp['gate_exact'].get(k, 0)})" for k in kinds) + " |",
        "|---|" + "---|" * len(kinds)]
    for rule in RULES:
        out.append(f"| `{rule}` | " + " | ".join(str(sp["rules"][rule].get(k, 0)) for k in kinds) + " |")
    tot = lambda d: sum(d.values())   # noqa: E731
    out += ["", "## Synthetic non-plate text (probe)", "",
            "Rendered in memory and never saved: text on a sign colour in DejaVu Sans Bold, Arial Bold or Bahnschrift, "
            "padded like a worker crop, shrunk to 60-200 px wide, blurred, noised and JPEG-coded. It assumes the plate "
            "detector has already fired on the text (as it did on the sandbox hoarding); it measures only what the OCR, "
            "the gate and each rule then do. Cells: crops that still pass. The first probe run was seed 7 at 150 crops per "
            "kind, and `1e-k2` was singled out after it; seed 11 was first run after that choice, as a check.", ""]
    for pr in res["probe"]:
        out += [f"Seed {pr['seed']}, {pr['per_kind']} crops per kind:", "",
                "| Kind | n | current gate | " + " | ".join(f"`{r}`" for r in PROBE_RULES) + " |",
                "|---|---|---|" + "---|" * len(PROBE_RULES)]
        for k in PROBE_KINDS:
            out.append(f"| {k} | {pr['n'][k]} | {pr['gate'].get(k, 0)} | "
                       + " | ".join(str(pr["rules"][r].get(k, 0)) for r in PROBE_RULES) + " |")
        out += [f"| all | {tot(pr['n'])} | {tot(pr['gate'])} | "
                + " | ".join(str(tot(pr["rules"][r])) for r in PROBE_RULES) + " |", ""]
    out += ["", "## Caveats", "",
        "- One read per crop. The worker applies the gate per read before the tracker votes, and a sighting needs "
        "several reads, so a rule that removes one read of a vehicle does not always lose the vehicle; *vehicles gone* "
        "is the stricter view on ownfeed-v1.",
        "- The crops are the stored JPEG evidence crops (quality 85); the worker read the raw frame crop.",
        "- The non-plate text is from one sandbox camera and a handful of distinct texts: a rule that catches it may "
        "be fitted to those texts, not to hoardings in general. The sandbox crops are test-only and never trained on.",
        "- The sandbox labels (reject-v1, sandbox-v1, the stored sightings) were made by our AI coding assistant with "
        "the stored read in view, not by a person and not blind.",
        "- ownfeed-v1 plates are synthetic (all GJ), painted on Pexels stock footage: real out-of-state plates, "
        "damaged plates and non-standard fonts are not in it.",
        "- The hoarding sightings were stored before `static_text.py` existed. That filter mutes fixed text read again "
        "in the same place, but it still stores the first sighting; a rule on the read stops the first one too.", ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "bench" / "results" / "plate_gate.md"))
    ap.add_argument("--threads", type=int, default=2, choices=(1, 2))
    ap.add_argument("--probe-per-kind", type=int, default=300)
    ap.add_argument("--seeds", type=int, nargs="+", default=[7, 11])
    a = ap.parse_args()
    cv2.setNumThreads(1)
    s = get_settings()
    ocr, label = load_model(s.ocr_model, None, a.threads)
    res = {"generated": datetime.now().astimezone().isoformat(timespec="seconds"),
           "conditions": {"ocr_model": label, "fast_plate_ocr": version("fast-plate-ocr"),
                          "onnxruntime": version("onnxruntime"), "threads": a.threads, "batch": BATCH,
                          "min_ocr_conf": s.min_ocr_conf},
           "rules": {k: {"family": f, "description": d} for k, (f, d, _) in RULES.items()}, "sets": {}}
    for name in SETS:
        res["sets"][name] = score_set(ocr, name, s.min_ocr_conf)
        r = res["sets"][name]
        print(f"{name}: {r['n']} crops, {r['gate']} pass the gate; reads same as baseline run "
              f"{r['reads_same_as_ocr_baseline']}")
    res["labels"] = score_labels(ocr, s.min_ocr_conf)
    print(f"labels: {res['labels']['n']} sightings, gate passes by verdict {res['labels']['gate']}")
    res["synth_plates"] = score_synth_plates(ocr, s.min_ocr_conf)
    print(f"synthetic plates: n {res['synth_plates']['n']}, exact passing {res['synth_plates']['gate_exact']}")
    res["probe"] = [score_probe(ocr, s.min_ocr_conf, a.probe_per_kind, seed) for seed in a.seeds]
    for pr in res["probe"]:
        print(f"probe seed {pr['seed']}: gate passes {sum(pr['gate'].values())} of {sum(pr['n'].values())}")
    res["parity"] = {k: dict(v) for k, v in PARITY.items()}
    bad = sum(v["helper_vs_replay"] + v["normalise_vs_replay"] for v in PARITY.values())
    print(f"parity: {sum(v['reads'] for v in PARITY.values())} reads, {bad} mismatches", res["parity"])
    for rule in RULES:
        rj, sb, ow, lb = (res["sets"]["reject-v1"]["rules"][rule], res["sets"]["sandbox-v1"]["rules"][rule],
                          res["sets"]["ownfeed-v1"]["rules"][rule], res["labels"]["rules"][rule])
        print(f"{rule:18s} reject caught {rj['rejected']:>2} | sandbox exact lost {sb['exact_lost']:>2} | "
              f"ownfeed exact lost {ow['exact_lost']:>4} wrong removed {ow['wrong_removed']:>3} "
              f"vehicles gone {ow['groups_all_rejected']:>3} | labels {lb} | synth lost {res['synth_plates']['rules'][rule]} "
              f"| probe still passing {[sum(pr['rules'][rule].values()) for pr in res['probe']]}")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    out.with_suffix(".md").write_text(markdown(res), encoding="utf-8")
    print("wrote", out.with_suffix(".md"), "and .json")
    if bad:
        print("the product helper or normalise_plate no longer matches the replay: see the parity line")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

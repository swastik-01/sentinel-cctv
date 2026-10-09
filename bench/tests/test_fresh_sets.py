"""sandbox-fresh-v1 and sandbox-blind-v2 (bench/ocr_sets.py) and their report (bench/sandbox_fresh.py), end to end on
synthetic plates (GJ99..., never a real registration), a temporary data folder and a stubbed database fetch."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timedelta

import cv2
import numpy as np
import pytest

import ocr_sets
import sandbox_fresh
from ocr_sets import IST

PLATE_SHAPE = re.compile(r"[A-Z]{2}\s?[0-9]{1,2}\s?[A-Z]{0,3}\s?[0-9]{3,4}")
NOW = datetime(2026, 9, 26, 21, 0, tzinfo=IST)


def at(h, m, s=0, day=26, us=0):
    return datetime(2026, 9, day, h, m, s, us, tzinfo=IST)


class DB:
    """The live state the builders would fetch: reviews of sandbox sightings, and crops on disk."""

    def __init__(self, root):
        self.root, self.revs, self.window, self.n = root, [], [], 0

    def sighting(self, sid, ts, stored, cam="CAM06", conf=0.95, crop=True):
        path = f"/crops/{cam}/{sid}_{stored}.jpg"    # the worker names a crop after its plate
        if crop:
            img = np.random.default_rng(sid).integers(0, 255, (40, 160, 3), dtype=np.uint8)
            dst = self.root / "data" / path.lstrip("/")
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(cv2.imencode(".jpg", img)[1].tobytes())
        self.window.append((sid, ts))
        return {"sighting_id": sid, "sighting_ts": ts, "camera_code": cam, "stored_plate": stored, "ocr_conf": conf,
                "crop_path": path, "plate_norm": stored}

    def review(self, s, user, seen, created, mode="blind"):
        self.n += 1
        self.revs.append(s | {"id": self.n, "username": user, "seen": seen, "created_at": created, "mode": mode})

    def fetch(self, since, until):
        """As ocr_sets.fetch: every review, and the sightings with a crop after `since` (up to `until`)."""
        return [dict(r) for r in self.revs], [i for i, ts in self.window if ts > since and (until is None or ts <= until)]


@pytest.fixture
def env(tmp_path, monkeypatch):
    out = tmp_path / "data" / "ocr-eval"
    monkeypatch.setattr(ocr_sets, "ROOT", tmp_path)
    monkeypatch.setattr(ocr_sets, "OUT", out)
    monkeypatch.setattr(ocr_sets, "now", lambda: NOW)
    monkeypatch.setattr(ocr_sets, "git_head", lambda: ("abc1234", 0))
    db = DB(tmp_path)
    monkeypatch.setattr(ocr_sets, "fetch", db.fetch)
    v1 = out / "sandbox-blind-v1"
    v1.mkdir(parents=True)
    rows = [("1", "CAM06", "2026-09-25 22:00:00", "GJ99ZZ9999", "GJ99ZZ9999", "exact"),
            ("2", "CAM07", "2026-09-26 07:00:00", "GJ99YY8888", "GJ99YY8880", "one_off"),
            ("3", "CAM06", "2026-09-26 07:30:00", "GJ99XX7777", "GJ99XX7777", "exact")]
    with open(v1 / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "camera", "event_ist", "true_plate", "stored", "verdict", "ocr_conf", "group", "layout",
                    "width_px", "height_px", "sha256"])
        for i, (sid, cam, t, truth, stored, v) in enumerate(rows):
            w.writerow([sid, cam, t, truth, stored, v, "0.950", f"g{i + 1:03d}", "one-line", 160, 40, "x"])
    return db


def v1_source(db):
    """v1's sightings, read by reader 1 before v1 froze; the last one sits inside the second the fresh set starts at."""
    s = [db.sighting(1, at(22, 0, day=25), "GJ99ZZ9999"), db.sighting(2, at(7, 0), "GJ99YY8880", cam="CAM07"),
         db.sighting(3, at(7, 30), "GJ99XX7777"), db.sighting(4, at(7, 55, 27, us=550049), "GJ99HH4444")]
    for x, seen in zip(s, ("GJ99ZZ9999", "GJ99YY8888", "GJ99XX7777", "-")):
        db.review(x, "admin", seen, at(12, 30))
    return s


def fresh_rows(db):
    t = lambda i: at(9, 0) + timedelta(minutes=i)   # noqa: E731
    s = {sid: db.sighting(sid, t(sid - 100), stored, conf=conf, crop=sid != 113) for sid, stored, conf in (
        (101, "GJ99AB1234", 0.95), (102, "GJ99KL5078", 0.9), (103, "GJ99CD4821", 0.62), (104, "GJ99MN1117", 0.8),
        (105, "GJ99EF2222", 0.95), (106, "GJ99GH3333", 0.95), (107, "GJ99JK4444", 0.95), (108, "GJ99ZZ9998", 0.99),
        (109, "GJ99PP5555", 0.95), (110, "GJ99RR6666", 0.95), (111, "GJ99QQ1000", 0.95), (112, "GJ99SS7777", 0.95),
        (113, "GJ99TT8888", 0.95))}
    r = lambda sid, user, seen, m=0, mode="blind": db.review(s[sid], user, seen, at(19, 0) + timedelta(minutes=m), mode)  # noqa: E731
    r(101, "admin", "GJ99AB1234")
    r(102, "admin", "GJ99KL5678"), r(102, "auditor", "gj99 kl-5678", 5)
    r(103, "admin", "GJ99CD4321"), r(103, "auditor", "GJ99CD4327", 5)
    r(104, "admin", "GJ99MN1111"), r(104, "auditor", "GJ99MN7777", 5)
    r(105, "admin", "-"), r(105, "auditor", "GJ99EF2222", 5)
    r(106, "auditor", "?")
    r(107, "auditor", "12345")
    r(108, "admin", "GJ99ZZ9998")
    r(109, "supervisor", "GJ99PP5555")
    r(110, "admin", "GJ99RR6666", mode="verify")
    r(111, "admin", "GJ99QQ1000"), r(111, "admin", "GJ99QQ2000", 30)
    r(112, "auditor", "GJ99SS7777", 150)     # 21:30, after the freeze time
    r(113, "admin", "GJ99TT8888")
    db.sighting(150, at(9, 50), "GJ99WW1515")    # stored, never reviewed
    return s


def adjudicate(name, answers):
    d = ocr_sets.OUT / name
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "adjudication.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["sighting_id", "answer", "note"])
        w.writerows([sid, a, ""] for sid, a in answers.items())


def tree(path):
    return {p.relative_to(path): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
            for p in path.rglob("*")}


def manifest(name):
    with open(ocr_sets.OUT / name / "manifest.csv", encoding="utf-8") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def test_answer_rules():
    assert ocr_sets.settle("GJ99AB1234", None, None) == ("single", "GJ99AB1234")
    assert ocr_sets.settle(None, "gj99 ab-1234", None) == ("single", "GJ99AB1234")
    assert ocr_sets.settle("GJ99AB1234", "gj 99 ab 1234", None) == ("agreed", "GJ99AB1234")
    assert ocr_sets.settle("GJ99AB1234", "GJ99AB1284", None) == ("unsettled disagreement", "")
    assert ocr_sets.settle("GJ99AB1234", "GJ99AB1284", "") == ("unsettled disagreement", "")
    assert ocr_sets.settle("GJ99AB1234", "GJ99AB1284", "gj99ab1284") == ("settled", "GJ99AB1284")
    assert ocr_sets.settle("GJ99AB1234", "GJ99AB1284", "?") == ("settled as not a plate or unreadable", "")
    assert ocr_sets.settle("-", "GJ99AB1234", None) == ("not a plate", "")
    assert ocr_sets.settle("GJ99AB1234", "98250", None) == ("not a plate", "")     # digits only: a phone number
    assert ocr_sets.settle("?", None, None) == ("unreadable", "")
    assert ocr_sets.settle("GJ99AB1234", "?", None) == ("unreadable", "")


def test_band_as_the_review_page():
    stored = float(np.float32(0.9))          # a REAL 0.9 read back: 0.8999999761...
    assert ocr_sets.band(stored) == ">=0.9" and ocr_sets.band(0.8995) == "<0.9" and ocr_sets.band(None) == ""


def test_fresh_freeze(env, capsys):
    v1_source(env)
    fresh_rows(env)
    adjudicate("sandbox-fresh-v1", {103: "GJ99CD4321", 104: ""})
    ocr_sets.freeze("fresh")
    m = manifest("sandbox-fresh-v1")
    assert sorted(m) == ["101", "102", "103", "108", "111"]     # 4 (v1's last sighting) is not fresh
    assert {k: (r["answer_by"], r["readers"], r["verdict"]) for k, r in m.items()} == {
        "101": ("single", "1", "exact"), "102": ("agreed", "both", "one_off"), "103": ("settled", "both", "one_off"),
        "108": ("single", "1", "exact"), "111": ("single", "1", "exact")}
    assert m["102"]["true_plate"] == "GJ99KL5678" and m["111"]["reading_1"] == "GJ99QQ1000"   # the earliest review
    assert m["108"]["vehicle"] == "seen" and {m[k]["vehicle"] for k in ("101", "102", "103", "111")} == {"new"}
    assert m["102"]["conf_band"] == ">=0.9" and m["103"]["conf_band"] == "<0.9"
    assert all((ocr_sets.OUT / "sandbox-fresh-v1" / f"{k}.jpg").is_file() for k in m)
    with open(ocr_sets.OUT / "sandbox-fresh-v1" / "left_out.csv", encoding="utf-8") as f:
        left = {r["id"]: r for r in csv.DictReader(f)}
    assert {k: r["reason"] for k, r in left.items()} == {"104": "unsettled disagreement", "105": "not a plate",
                                                         "106": "unreadable", "107": "not a plate", "113": "crop missing"}
    assert left["104"]["vehicle"] == "new" and left["104"]["group"]
    assert {k: bool(r["group"]) for k, r in left.items()} == {"104": True, "105": True, "106": False, "107": False,
                                                              "113": True}    # no group where nobody typed a plate
    info = json.loads((ocr_sets.OUT / "sandbox-fresh-v1" / "freeze.json").read_text(encoding="utf-8"))
    assert info["git_head"] == "abc1234" and "e18331a" in info["capture_build"] and info["frozen_by_deadline"]
    assert info["window"]["v1_sightings_left_to_v1"] == 1 and "sandbox-fresh-v2" in info["later_reviews"]
    assert info["ignored_reviews"] == {"review by another account": 1, "verify-mode review by a reader": 1,
                                       "later blind review by the same reader": 1, "made after the freeze time": 1}
    c = info["counts"]
    assert (c["rows"], c["disagreements"], c["settled"], c["unsettled"], c["both_typed_a_plate"], c["same_reading"]) == \
        (5, 2, 1, 1, 3, 1)
    assert (c["readers_split_plate_or_not"], c["neither_typed_a_plate"], c["left_out_no_plate_typed"]) == (1, 0, 2)
    assert c["sightings_in_window_with_crop"] == 14 and c["vehicles"] == {"new": 4, "seen": 1}
    n = c["new_vehicles"]
    assert (n["rows"], n["both_typed_a_plate"], n["disagreements"], n["unsettled"], n["readers_split_plate_or_not"]) == \
        (4, 3, 2, 1, 1)
    assert n["left_out"] == {"unsettled disagreement": 1, "not a plate": 1, "crop missing": 1}
    assert not PLATE_SHAPE.search(capsys.readouterr().out)


def row(sid, cam, ts, how, truth="", one="", two=""):
    return {"id": sid, "camera": cam, "_ts": ts, "answer_by": how, "true_plate": truth, "reading_1": one,
            "reading_2": two, "group": "", "vehicle": ""}


def test_a_left_out_row_never_joins_two_groups():
    v1 = [{"true_plate": "GJ99XX7777", "camera": "CAM07", "event_ist": "2026-09-26 07:00:00"}]
    alone = row("1", "CAM06", at(9, 0), "single", "GJ99AB1234", "GJ99AB1234")
    ocr_sets.group_rows([alone], v1)
    assert alone["vehicle"] == "new"
    rows = [row("1", "CAM06", at(9, 0), "single", "GJ99AB1234", "GJ99AB1234"),
            row("2", "CAM06", at(9, 30), ocr_sets.UNSETTLED, one="GJ99AB1234", two="GJ99XX7777"),   # links both
            row("3", "CAM07", at(11, 0), ocr_sets.UNSETTLED, one="GJ99QQ1111", two="GJ99QQ1117"),
            row("4", "CAM07", at(11, 0, 5), "not a plate", one="-", two="GJ99QQ1111"),
            row("5", "CAM05", at(12, 0), "not a plate", one="-", two="-")]
    ocr_sets.group_rows(rows, v1)
    assert rows[0]["vehicle"] == "new" and rows[1]["group"] == rows[0]["group"] and rows[1]["vehicle"] == "new"
    assert rows[2]["group"] not in (rows[0]["group"], "") and rows[3]["group"] == rows[2]["group"]
    assert (rows[4]["group"], rows[4]["vehicle"]) == ("", "")
    seen = row("6", "CAM06", at(9, 0), "single", "GJ99XX7771", "GJ99XX7771")
    ocr_sets.group_rows([seen], v1)
    assert seen["vehicle"] == "seen"


def adjudication_file(text):
    d = ocr_sets.OUT / "sandbox-fresh-v1"
    d.mkdir(parents=True, exist_ok=True)
    (d / "adjudication.csv").write_text(text, encoding="utf-8")


def test_adjudication_refuses_a_file_it_cannot_read(env):
    adjudication_file("﻿ sighting_id , answer ,note\n103,gj99 cd 4321,\n104,,\n,,\n")
    assert ocr_sets.adjudication("sandbox-fresh-v1") == {103: "gj99 cd 4321", 104: ""}
    for text in ("sighting_id;answer;note\n103;GJ99CD4321;\n",     # a semicolon export
                 "Sighting ID,Answer,note\n103,GJ99CD4321,\n",     # renamed columns
                 "sighting_id,answer,note\nGJ99CD4321,,\n",        # columns shifted: a plate where the id goes
                 "sighting_id,answer,note\n,GJ99CD4321,\n",        # an answer without an id
                 "sighting_id,answer,note\n103,GJ99CD,4321,x\n",   # an unquoted comma
                 "sighting_id,answer,note\n103,GJ99CD4321,\n103,,\n"):
        adjudication_file(text)
        with pytest.raises(SystemExit) as e:
            ocr_sets.adjudication("sandbox-fresh-v1")
        assert "GJ99" not in str(e.value) and "CD" not in str(e.value)


def test_a_crop_that_cannot_be_copied_names_no_plate(env, monkeypatch):
    v1_source(env)
    fresh_rows(env)

    def gone(src, dst):
        raise FileNotFoundError(2, "No such file or directory", str(src))
    monkeypatch.setattr(ocr_sets, "copy", gone)
    with pytest.raises(SystemExit) as e:
        ocr_sets.freeze("fresh")
    assert "GJ99" not in str(e.value) and "crops" not in str(e.value)
    assert not (ocr_sets.OUT / "sandbox-fresh-v1" / "manifest.csv").exists()


def test_refuses_to_overwrite(env, capsys):
    v1_source(env)
    fresh_rows(env)
    ocr_sets.freeze("fresh")
    before = tree(ocr_sets.OUT)
    env.review(env.sighting(120, at(9, 30), "GJ99UU1212"), "admin", "GJ99UU1212", at(20, 0))
    ocr_sets.freeze("fresh")
    ocr_sets.freeze("fresh", dry_run=True)
    assert tree(ocr_sets.OUT) == before
    assert capsys.readouterr().out.count("already frozen") == 2


def test_dry_run_writes_nothing(env, capsys):
    v1_source(env)
    fresh_rows(env)
    before = tree(env.root)
    ocr_sets.main(["fresh", "--dry-run"])
    ocr_sets.main(["blindv2", "--dry-run"])
    assert tree(env.root) == before and not (ocr_sets.OUT / "sandbox-fresh-v1").exists()
    out = capsys.readouterr().out
    assert "dry run" in out and "exact" not in out and "one_off" not in out and not PLATE_SHAPE.search(out)


def test_empty_set_is_not_frozen(env, capsys):
    v1_source(env)
    ocr_sets.freeze("fresh")
    assert not (ocr_sets.OUT / "sandbox-fresh-v1").exists() and "nothing frozen" in capsys.readouterr().out


def test_default_invocation_leaves_the_new_sets_alone(env, monkeypatch):
    monkeypatch.setattr(ocr_sets, "fetch", lambda *a: pytest.fail("dispatch reached the database"))
    called = []
    for key in ocr_sets.BUILDERS:
        monkeypatch.setitem(ocr_sets.BUILDERS, key, lambda key=key: called.append(key))
    monkeypatch.setattr(ocr_sets, "freeze", lambda key, dry_run=False: called.append((key, dry_run)))
    monkeypatch.setattr(ocr_sets, "sheet", lambda key: called.append(("sheet", key)))
    ocr_sets.main([])
    assert called == ["sandbox", "ownfeed", "blind"]
    called.clear()
    ocr_sets.main(["fresh", "--dry-run"])
    ocr_sets.main(["blindv2"])
    ocr_sets.main(["sheet", "fresh"])
    assert called == [("fresh", True), ("blindv2", False), ("sheet", "fresh")]
    for bad in (["--dry-run"], ["blind", "--dry-run"], ["sheet"], ["sheet", "blind"]):
        with pytest.raises(SystemExit):
            ocr_sets.main(bad)


def test_sheet_never_shows_sentinels_read(env, capsys):
    v1_source(env)
    s = fresh_rows(env)
    ocr_sets.main(["sheet", "fresh"])
    d = ocr_sets.OUT / "sandbox-fresh-v1"
    page = (d / "sheet.html").read_text(encoding="utf-8")
    assert all(x in page for x in ("GJ99CD4321", "GJ99CD4327", "GJ99MN1111", "GJ99MN7777", "data:image/jpeg;base64"))
    assert not any(x["stored_plate"] in page for x in s.values()) and "crops/" not in page
    assert "0.62" not in page and "0.8" not in page and "Sighting 102" not in page     # agreed rows are not on it
    with open(d / "adjudication.csv", encoding="utf-8") as f:
        assert [r["sighting_id"] for r in csv.DictReader(f)] == ["103", "104"]
    adjudicate("sandbox-fresh-v1", {103: "GJ99CD4321", 104: ""})
    kept = (d / "adjudication.csv").read_bytes()
    ocr_sets.main(["sheet", "fresh"])
    assert (d / "adjudication.csv").read_bytes() == kept and not (d / "manifest.csv").exists()
    assert not PLATE_SHAPE.search(capsys.readouterr().out)


def test_blindv2_leaves_v1_alone(env):
    v1_source(env)
    x = {r["sighting_id"]: r for r in env.revs}
    env.review(x[1], "auditor", "GJ99ZZ9999", at(20, 0))
    env.review(x[2], "auditor", "GJ99YY8880", at(20, 1))
    env.review(x[3], "auditor", "GJ99XX7771", at(20, 2))
    env.review(x[4], "auditor", "-", at(20, 3))
    env.review(env.sighting(5, at(23, 0, day=25), "GJ99VV5050"), "auditor", "GJ99VV5050", at(20, 4))   # not v1's
    adjudicate("sandbox-blind-v2", {2: "GJ99YY8880"})
    v1 = tree(ocr_sets.OUT / "sandbox-blind-v1")
    ocr_sets.freeze("blindv2")
    assert tree(ocr_sets.OUT / "sandbox-blind-v1") == v1
    m = manifest("sandbox-blind-v2")
    assert {k: (r["answer_by"], r["verdict"]) for k, r in m.items()} == {"1": ("agreed", "exact"),
                                                                          "2": ("settled", "exact")}
    info = json.loads((ocr_sets.OUT / "sandbox-blind-v2" / "freeze.json").read_text(encoding="utf-8"))
    h = info["headline"]
    assert info["counts"]["v1_source_sightings"] == 4 and info["counts"]["reader2_read_all"]
    assert h["frozen_by_deadline"] and not h["all_disagreements_settled"] and not h["holds_as_far_as_checkable"]
    assert info["ignored_reviews"]["reader 2 review in v1's window but not of its 144"] == 1
    c = info["counts"]     # sighting 4: both readers typed '-', which is agreement, not a split
    assert (c["readers_split_plate_or_not"], c["neither_typed_a_plate"], c["disagreements"]) == (0, 1, 2)


def report(env, key, tmp_path):
    logs = tmp_path / "data" / "rotation-capture"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "rotation.csv").write_text("run,cameras,start_ist,end_ist,minutes,log\n"
                                       '1,"CAM06,CAM07",2026-09-26T08:30:00,2026-09-26T09:05:00,35.0,w.log\n',
                                       encoding="utf-8")
    out = tmp_path / "res" / f"{key}.md"
    out.parent.mkdir(exist_ok=True)
    sandbox_fresh.main([key, "--manifest-root", str(ocr_sets.OUT), "--logs-root", str(tmp_path / "data"),
                        "--out", str(out)])
    return out.read_text(encoding="utf-8"), json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))


def test_report_refuses_before_the_freeze(env, tmp_path):
    with pytest.raises(SystemExit, match="not frozen"):
        report(env, "fresh", tmp_path)


def test_fresh_report(env, tmp_path, monkeypatch):
    v1_source(env)
    fresh_rows(env)
    adjudicate("sandbox-fresh-v1", {103: "GJ99CD4321"})
    ocr_sets.freeze("fresh")
    monkeypatch.setattr(ocr_sets, "fetch", lambda *a: pytest.fail("the report must not read the database"))
    md, res = report(env, "fresh", tmp_path)
    everything, new = res["results"]["All rows"], res["results"]["New vehicles"]
    assert (everything["exact"]["k"], everything["exact"]["n"]) == (3, 5)
    assert everything["exact"]["wilson95"] == sandbox_fresh.wilson(3, 5)
    assert (everything["within1"]["k"], everything["norm"]["k"]) == (5, 3)
    assert (everything["exact_unsettled_as_misses"]["k"], everything["exact_unsettled_as_misses"]["n"]) == (3, 6)
    assert (new["exact"]["k"], new["exact"]["n"], new["exact_unsettled_as_misses"]["n"]) == (2, 4, 5)
    assert everything["bands"][">=0.9"]["exact"]["n"] == 4 and everything["bands"]["<0.9"]["exact"]["n"] == 1
    assert res["rows_outside_logged_windows"] == 4 and res["vehicles"] == {"seen": 1, "new": 4}
    assert res["unlogged_spans"] == [{"first_row": "2026-09-26T09:07:00+05:30", "last_row": "2026-09-26T09:13:00+05:30",
                                      "rows": {"CAM06": 4}}] and "26 Sep 09:07–09:13 (CAM06 4)" in md
    for split in ("bands", "cameras", "layouts"):
        assert all(set(x) == set(sandbox_fresh.MEASURES) for x in everything[split].values())
    assert set(everything["band_gap"]) == set(sandbox_fresh.MEASURES)
    assert "| | All rows | New vehicles |" in md and "| Disagreements | 2 | 2 |" in md
    assert "| Both called it not a plate or unreadable (left out) | 0 | 0 |" in md
    assert "New vehicles" in md and "looping footage" in md and "e18331a" in md and "sandbox-fresh-v2" in md
    for text in (md, json.dumps(res)):
        assert not PLATE_SHAPE.search(text) and "GJ99" not in text


def test_v2_report(env, tmp_path):
    v1_source(env)
    x = {r["sighting_id"]: r for r in env.revs}
    for sid, seen in ((1, "GJ99ZZ9999"), (2, "GJ99YY8880"), (3, "GJ99XX7771"), (4, "-")):
        env.review(x[sid], "auditor", seen, at(20, sid))
    adjudicate("sandbox-blind-v2", {2: "GJ99YY8880", 3: "GJ99XX7777"})
    ocr_sets.freeze("blindv2")
    md, res = report(env, "v2", tmp_path)
    assert (res["results"]["v2"]["exact"]["k"], res["results"]["v2"]["exact"]["n"]) == (3, 3)
    assert (res["v1"]["exact"]["k"], res["v1"]["exact"]["n"]) == (2, 3)
    assert res["changes_from_v1"] == {"hits": {"n": 2, "read by reader 2": 2, "exact in v2": 2, "answer changed": 0},
                                      "misses": {"n": 1, "read by reader 2": 1, "exact in v2": 1, "answer changed": 1}}
    assert "v2 (3 of 3 rows read by both readers)" in md and "| Both called it not a plate or unreadable (left out) | 1 |" in md
    assert res["freeze"]["headline"]["holds_as_far_as_checkable"] and "Holds as far as the script can check: yes" in md
    assert "saw Sentinel's read after typing" in md
    for text in (md, json.dumps(res)):
        assert not PLATE_SHAPE.search(text) and "GJ99" not in text


def test_v2_report_shows_a_partial_second_reading(env, tmp_path):
    v1_source(env)
    x = {r["sighting_id"]: r for r in env.revs}
    env.review(x[2], "auditor", "GJ99YY8888", at(20, 0))     # reader 2 has read one of the four
    ocr_sets.freeze("blindv2")
    md, res = report(env, "v2", tmp_path)
    assert res["rows_read_by_both"] == 1 and "v2 (1 of 3 rows read by both readers)" in md
    assert res["changes_from_v1"]["hits"] == {"n": 2, "read by reader 2": 0, "exact in v2": 2, "answer changed": 0}
    assert res["changes_from_v1"]["misses"] == {"n": 1, "read by reader 2": 1, "a miss in v2": 1, "answer changed": 0}
    assert not res["freeze"]["headline"]["holds_as_far_as_checkable"] and "stays the quoted figure" in md


def test_wilson_known_values():
    assert sandbox_fresh.wilson(5, 10) == [0.2366, 0.7634]
    assert sandbox_fresh.wilson(0, 10) == [0.0, 0.2775]
    assert sandbox_fresh.wilson(0, 0) is None

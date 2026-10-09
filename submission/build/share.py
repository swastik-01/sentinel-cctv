"""Assemble the folder the team shares to fill the submission form: one numbered subfolder per
upload field of the Google Form, files named as they should appear on Drive, the form-answers
document (Word, and PDF when Word is installed) and a README for whoever fills the form.

    uv run --no-sync python submission/build/share.py                 # -> D:\\GitHub\\Sentinel-Submission (beside the repo)
    uv run --no-sync python submission/build/share.py --out <folder>

The folder is rebuilt from scratch (an existing one is removed first, if it was made by this
script), so it never holds a stale file. Run it after any deliverable or the form answers change.
"""
from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "submission" / "out"
DOCX = ROOT / "submission" / "Sentinel-Form-Answers.docx"
MARK = ".sentinel-share"
IST = timezone(timedelta(hours=5, minutes=30))

# The text behind every shipped document: a bench/results file is shipped only if one of these (or a gates file, or a
# results file already shipped) names it. The PDFs are built from the Markdown; the deck and diagram captions from
# their scripts.
SHIPPED_SOURCES = [ROOT / "docs" / "hld.md", ROOT / "docs" / "plan-for-scale.md", ROOT / "docs" / "privacy-dpdp.md",
                   ROOT / "submission" / "build" / "deck.cjs", ROOT / "submission" / "build" / "diagrams.mjs",
                   ROOT / "submission" / "build" / "diagrams_pdf.mjs", OUT / "README-for-reviewers.txt",
                   OUT / "sandbox-readiness.md", OUT / "registry-api.md"]

FOLDERS = [
    ("1 - Solution Presentation", "Solution Presentation Link", "file link of Sentinel-Solution.pdf"),
    ("2 - High-Level Design", "High-Level Design / Architecture Document Link", "file link of Sentinel-HLD.pdf"),
    ("3 - Workflow Diagrams", "Workflow / Integration Diagram Link", "file link of Sentinel-Workflow-Diagrams.pdf"),
    ("4 - Screenshots", "Screenshots Folder Link", "link to the folder"),
    ("5 - Video and detection report", "Submit your solution (Video)", "link to the folder"),
    ("6 - Supporting documents", "Any other document or video submission", "link to the folder"),
]


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        return html.unescape(re.sub(r"<[^>]+>", " ", z.read("word/document.xml").decode("utf-8")))


def cited_results() -> tuple[list[Path], list[Path]]:
    """(shipped, skipped) bench/results/*.md: shipped when a shipped document, the form answers, a gates file or an
    already shipped result names it (as .md, or as the .json beside it), followed to closure. A result kept only as
    JSON (no .md beside it, e.g. a sentinel-bench run) ships as the JSON when named."""
    res = ROOT / "bench" / "results"
    results = sorted(list(res.glob("*.md")) + [j for j in res.glob("*.json") if not j.with_suffix(".md").exists()])
    pattern = {r: re.compile(rf"(?<![\w.-]){re.escape(r.stem)}\.(?:md|json)\b") for r in results}
    texts = [s.read_text(encoding="utf-8") for s in SHIPPED_SOURCES if s.exists()]
    texts += [g.read_text(encoding="utf-8") for g in sorted((ROOT / "bench").glob("*_gates.md"))]
    if DOCX.exists():
        texts.append(docx_text(DOCX))
    shipped: set[Path] = set()
    while texts:
        text = texts.pop()
        for r, pat in pattern.items():
            if r not in shipped and pat.search(text):
                shipped.add(r)
                texts.append(r.read_text(encoding="utf-8"))
    return [r for r in results if r in shipped], [r for r in results if r not in shipped]


def plan() -> dict[str, list[tuple[Path, str]]]:
    reports = sorted(OUT.glob("detections_*.pdf"))
    if len(reports) != 1:
        sys.exit(f"expected exactly one own-feed report in {OUT}, found {[r.name for r in reports]}")
    rep = reports[0].stem
    reviewers = OUT / "README-for-reviewers.txt"
    screens = sorted((OUT / "screens").glob("*.png"))
    if not screens:
        sys.exit("no screenshots in submission/out/screens (run screens.mjs)")
    # the results a shipped document cites, plus the adoption gates written before each measurement
    measurements = cited_results()[0] + sorted((ROOT / "bench").glob("*_gates.md"))
    gov = []                             # the government-feed run, once it exists
    gov_reports = sorted(OUT.glob("gov_detections_*.pdf"))
    if len(gov_reports) > 1:
        sys.exit(f"expected at most one government-feed report, found {[r.name for r in gov_reports]}")
    if (OUT / "Sentinel-Gov-Demo.mp4").exists():
        gov += [(OUT / "Sentinel-Gov-Demo.mp4", "2 - Government feed demo.mp4"),
                (OUT / "Sentinel-Gov-Demo-chapters.txt", "2 - Government feed demo - chapters.txt")]
    if gov_reports:
        g = gov_reports[0].stem
        gov += [(OUT / f"{g}.pdf", "2 - Government feed detection report.pdf"),
                (OUT / f"{g}.csv", "2 - Government feed detection report - plate reads.csv"),
                (OUT / f"{g}_vehicles.csv", "2 - Government feed detection report - vehicles.csv"),
                (OUT / f"{g}_counts.csv", "2 - Government feed detection report - counts.csv"),
                (OUT / f"{g}_intrusions.csv", "2 - Government feed detection report - intrusion alerts.csv")]
    return {
        "1 - Solution Presentation": [(OUT / "Sentinel-Solution.pdf", "Sentinel-Solution.pdf")],
        "2 - High-Level Design": [(OUT / "Sentinel-HLD.pdf", "Sentinel-HLD.pdf")],
        "3 - Workflow Diagrams": [(OUT / "Sentinel-Workflow-Diagrams.pdf", "Sentinel-Workflow-Diagrams.pdf")],
        # gov-*.png come from the organisers' sandbox: named like the other government-feed files
        "4 - Screenshots": [(p, f"2 - Government feed - {p.stem[4:]}{p.suffix}" if p.name.startswith("gov-") else p.name)
                            for p in screens] + [(reviewers, reviewers.name)],
        "5 - Video and detection report": [
            (OUT / "Sentinel-Demo.mp4", "1 - Own feed demo.mp4"),
            (OUT / "Sentinel-Demo-chapters.txt", "1 - Own feed demo - chapters.txt"),
            (OUT / f"{rep}.pdf", "1 - Own feed detection report.pdf"),
            (OUT / f"{rep}.csv", "1 - Own feed detection report - plate reads.csv"),
            (OUT / f"{rep}_vehicles.csv", "1 - Own feed detection report - vehicles.csv"),
            (OUT / f"{rep}_counts.csv", "1 - Own feed detection report - counts.csv"),
            (OUT / f"{rep}_intrusions.csv", "1 - Own feed detection report - intrusion alerts.csv"),
            (reviewers, reviewers.name),
        ] + gov,
        "6 - Supporting documents": [
            (OUT / "Sentinel-Plan-for-Scale.pdf", "Sentinel-Plan-for-Scale.pdf"),
            (OUT / "Sentinel-Privacy-DPDP.pdf", "Sentinel-Privacy-DPDP.pdf"),
            (OUT / "Sentinel-Solution.pptx", "Sentinel-Solution.pptx"),
            (OUT / "registry-cameras.csv", "registry-cameras.csv"),
            (OUT / "registry-gap-analysis.pdf", "registry-gap-analysis.pdf"),
            (OUT / "registry-api.md", "registry-api.md"),
            (OUT / "registry-api.json", "registry-api.json"),
            (OUT / "sandbox-readiness.md", "sandbox-readiness.md"),
            (OUT / "Sentinel-Demo-chapters.txt", "Sentinel-Demo-chapters.txt"),
            (reviewers, reviewers.name),
        ] + [(p, f"measurements/{p.name}") for p in measurements],
    }


def readme(built: str, docx_pdf: bool, gov_video: bool, gov_report: bool) -> str:
    rows = "\n".join(f"  {name:<32} -> \"{field}\": {how}" for name, field, how in FOLDERS)
    doc = "\"Form answers - what to enter.docx\"" + (" (or the .pdf beside it)" if docx_pdf else "")
    return f"""Sentinel - submission folder for the Gujarat Police Innovation Challenge 2026
Built {built} from the Sentinel repository (submission/build/share.py). Use only this folder:
earlier copies of the form-answers document said "Hybrid"; the solution model is Model 2, with
Model 1 confirmed as the foundation, and every document here says so.

Start with {doc}: it lists every question of the Google Form in
order, with the exact answer to pick or paste, and names the file behind each link.

Which folder goes to which form field
{rows}

How to share
  Upload the six numbered folders to Google Drive exactly as they are (folder and file names too).
  Set every folder and file to "Anyone with the link -> Viewer", then open each link in a private
  browser window before pasting it into the form. Upload nothing else.

{gov_text(gov_video, gov_report)}

Submit from the portal account's Google login, once, after every field is filled. The answers
document marks the choices that are the team's to make (participant category and sub-type).
"""


def gov_text(video: bool, report: bool) -> str:
    if video and report:
        return ("Government-provided feeds\n"
                '  Folder 5 holds both demonstrations: "1 - ..." on our own feeds and "2 - ..." on the\n'
                "  organisers' sandbox cameras, each with its detection report.")
    missing = " and ".join(x for x, ok in (("the screen recording", video), ("the detection report", report)) if not ok)
    return ("Not in this folder yet\n"
            "  From the demonstration on the government-provided feeds: " + missing + ". It goes into\n"
            '  folder 5 once made; the form asks for it ("you will have to submit solution with our provided data").')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT.parent / "Sentinel-Submission"))
    a = ap.parse_args()
    dest = Path(a.out)
    if dest.exists():
        if not (dest / MARK).exists() and any(dest.iterdir()):
            sys.exit(f"{dest} exists and was not made by this script; choose another --out or empty it")
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    (dest / MARK).write_text("made by submission/build/share.py; safe to delete\n", encoding="utf-8")

    n = 0
    for folder, files in plan().items():
        for src, name in files:
            if not src.exists():
                sys.exit(f"missing: {src}")
            target = dest / folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            n += 1
    if not DOCX.exists():
        sys.exit(f"missing: {DOCX}")
    shutil.copy2(DOCX, dest / "Form answers - what to enter.docx")
    pdf = dest / "Form answers - what to enter.pdf"
    r = subprocess.run(["powershell", "-NoProfile", "-File", str(ROOT / "submission/build/docx_pdf.ps1"),
                        "-In", str(dest / "Form answers - what to enter.docx"), "-Out", str(pdf)],
                       capture_output=True, text=True)
    docx_pdf = r.returncode == 0 and pdf.exists()
    if not docx_pdf:
        print("  (no PDF of the answers: Word not available)", file=sys.stderr)
    built = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
    gov_video = (dest / "5 - Video and detection report" / "2 - Government feed demo.mp4").exists()
    gov_report = (dest / "5 - Video and detection report" / "2 - Government feed detection report.pdf").exists()
    (dest / "README.txt").write_text(readme(built, docx_pdf, gov_video, gov_report), encoding="utf-8")

    shipped, skipped = cited_results()
    print(f"measurements: {len(shipped)} results files cited by a shipped document or gates file, and the gates files; "
          f"left out, cited by none: {', '.join(p.name for p in skipped) or 'none'}")
    total = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
    print(f"{dest}: {n} deliverable files in 6 folders, README and form answers; {total / 1e6:.1f} MB")
    for folder, _, _ in FOLDERS:
        items = [p for p in (dest / folder).rglob("*") if p.is_file()]
        print(f"  {folder}: {len(items)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

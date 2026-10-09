"""Render PDF pages to PNG for visual QA:  python pdfpages.py file.pdf outdir [first-last] [zoom]"""
import sys
from pathlib import Path

import fitz

pdf, out = Path(sys.argv[1]), Path(sys.argv[2])
rng = sys.argv[3] if len(sys.argv) > 3 else None
zoom = float(sys.argv[4]) if len(sys.argv) > 4 else 1.3
out.mkdir(parents=True, exist_ok=True)
doc = fitz.open(pdf)
a, b = (int(x) for x in rng.split("-")) if rng else (1, doc.page_count)
for i in range(a - 1, min(b, doc.page_count)):
    pix = doc[i].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    p = out / f"{pdf.stem}-p{i + 1:02d}.png"
    pix.save(p)
    print(p)
print("pages:", doc.page_count)

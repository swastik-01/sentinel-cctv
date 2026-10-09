"""Tile page PNGs into contact sheets:  python sheet.py outprefix cols img1 img2 ..."""
import sys
from PIL import Image

prefix, cols, files = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
per = cols * 2
for s in range(0, len(files), per):
    imgs = [Image.open(f) for f in files[s:s + per]]
    w, h = imgs[0].size
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w + (cols - 1) * 12, rows * h + (rows - 1) * 12), "#94a3b8")
    for i, im in enumerate(imgs):
        sheet.paste(im, ((i % cols) * (w + 12), (i // cols) * (h + 12)))
    path = f"{prefix}-{s // per + 1}.png"
    sheet.save(path)
    print(path)

"""Render the MV portion of the NOAA custom chart to a WebP for the app.

Usage: python tools/make_chart.py app/static/chart.pdf app/static/chart.webp
Writes the image plus app/static/chart.json with its exact lat/lon bounds.
"""
import json
import sys
from pathlib import Path

import fitz  # pymupdf
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from geo import PAGE_H, ll2pdf, pdf2ll  # noqa: E402

SOUTH, WEST, NORTH, EAST = 41.315, -70.89, 41.585, -70.385
DPI = 230

src, out = sys.argv[1], Path(sys.argv[2])
xa, ya = ll2pdf(SOUTH, WEST)
xb, yb = ll2pdf(NORTH, EAST)
clip = fitz.Rect(xa, PAGE_H - yb, xb, PAGE_H - ya)  # fitz uses top-left origin

doc = fitz.open(src)
pix = doc[0].get_pixmap(clip=clip, dpi=DPI, alpha=False)
img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
img.save(out, "WEBP", quality=78, method=6)

s_lat, w_lon = pdf2ll(xa, ya)
n_lat, e_lon = pdf2ll(xb, yb)
meta = {"south": s_lat, "west": w_lon, "north": n_lat, "east": e_lon,
        "width": img.width, "height": img.height,
        "source": "NOAA Custom Chart 'MV - 2026', generated 2026-09-08"}
out.with_suffix(".json").write_text(json.dumps(meta, indent=2))
print(meta, f"{out.stat().st_size/1e6:.1f} MB")

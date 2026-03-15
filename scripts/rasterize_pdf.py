#!/usr/bin/env python3

import argparse
from pathlib import Path

import fitz
from PIL import Image


parser = argparse.ArgumentParser()
parser.add_argument("input_pdf")
parser.add_argument("output_pdf")
parser.add_argument("--dpi", type=int, default=300)
args = parser.parse_args()

input_pdf = Path(args.input_pdf)
output_pdf = Path(args.output_pdf)
output_pdf.parent.mkdir(parents=True, exist_ok=True)

zoom = args.dpi / 72.0
matrix = fitz.Matrix(zoom, zoom)
images = []

with fitz.open(input_pdf) as doc:
    for page in doc:
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        if pix.n >= 3:
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        else:
            image = Image.frombytes("L", [pix.width, pix.height], pix.samples).convert("RGB")
        images.append(image)

if not images:
    raise ValueError(f"No pages found in {input_pdf}")

images[0].save(
    output_pdf,
    save_all=True,
    append_images=images[1:],
    resolution=args.dpi,
)

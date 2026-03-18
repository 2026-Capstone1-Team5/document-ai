#!/usr/bin/env python3

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

from rasterize_pdf import rasterize_pdf


BAD_CHAR_RE = re.compile(r"[^\x09\x0A\x0D\x20-\x7EÀ-ÿ]")
REPO_ROOT = Path(__file__).resolve().parent.parent


def inspect_pdf(pdf_path):
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "parse_document requires PyMuPDF for PDF inspection. Install it with: pip install pymupdf"
        ) from exc

    pdf_path = Path(pdf_path)

    with fitz.open(pdf_path) as doc:
        text_chars = 0
        image_pages = 0
        page_count = len(doc)
        sample_text = []

        for page in doc:
            text = page.get_text("text")
            text_chars += len(text.strip())
            if text.strip():
                sample_text.append(text.strip())
            if page.get_images(full=True):
                image_pages += 1

    joined_text = "\n".join(sample_text[:3])
    bad_chars = len(BAD_CHAR_RE.findall(joined_text))
    total_chars = max(len(joined_text), 1)
    bad_ratio = bad_chars / total_chars

    suspicious_reasons = []

    if text_chars == 0 and image_pages > 0:
        suspicious_reasons.append("image_only_pdf")

    if image_pages == page_count and 0 < text_chars < 3000 and page_count <= 3:
        suspicious_reasons.append("image_pages_with_text_layer")

    if bad_ratio > 0.02:
        suspicious_reasons.append("noisy_text_layer")

    return {
        "page_count": page_count,
        "text_chars": text_chars,
        "image_pages": image_pages,
        "bad_char_ratio": round(bad_ratio, 4),
        "suspicious": bool(suspicious_reasons),
        "reasons": suspicious_reasons,
    }


def run_mineru(pdf_path, output_dir, language):
    if shutil.which("docker") is None:
        raise RuntimeError("docker command not found in PATH")

    input_dir = Path(pdf_path).resolve().parent
    output_dir = Path(output_dir).resolve()
    input_name = Path(pdf_path).name

    command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "-T",
        "-v",
        f"{input_dir}:/input:ro",
        "-v",
        f"{output_dir}:/output",
        "mineru-cpu",
        (
            f'mineru -p "/input/{input_name}" '
            f'-o /output -b pipeline -m txt -l "{language}" -d cpu'
        ),
    ]
    subprocess.run(command, check=True, cwd=REPO_ROOT)


def find_output_stem(result_root, preferred_stem):
    preferred_txt = Path(result_root) / preferred_stem / "txt"
    if preferred_txt.exists():
        return preferred_stem

    candidates = sorted(p.name for p in Path(result_root).iterdir() if p.is_dir())
    if len(candidates) == 1:
        return candidates[0]

    raise FileNotFoundError(
        f"Could not determine MinerU output directory under {result_root}"
    )


def find_txt_dir(output_dir, stem):
    txt_dir = Path(output_dir) / stem / "txt"
    if not txt_dir.exists():
        raise FileNotFoundError(f"MinerU output not found at {txt_dir}")
    return txt_dir


def build_output_map(txt_dir, stem):
    files = {
        "markdown": txt_dir / f"{stem}.md",
        "content_list": txt_dir / f"{stem}_content_list.json",
        "middle_json": txt_dir / f"{stem}_middle.json",
        "model_json": txt_dir / f"{stem}_model.json",
        "layout_pdf": txt_dir / f"{stem}_layout.pdf",
        "origin_pdf": txt_dir / f"{stem}_origin.pdf",
        "span_pdf": txt_dir / f"{stem}_span.pdf",
        "images_dir": txt_dir / "images",
    }

    output_map = {}
    for key, path in files.items():
        if path.exists():
            output_map[key] = str(path)

    return output_map


def main():
    parser = argparse.ArgumentParser(
        description="Parse a PDF with MinerU and optionally rasterize first if the text layer looks suspicious."
    )
    parser.add_argument("input_pdf")
    parser.add_argument("output_dir")
    parser.add_argument("--language", default="en")
    parser.add_argument("--force-rasterize", action="store_true")
    parser.add_argument("--force-normal", action="store_true")
    parser.add_argument("--dpi", type=int, default=300)
    args = parser.parse_args()

    if args.force_rasterize and args.force_normal:
        raise ValueError("Choose only one of --force-rasterize or --force-normal")

    input_pdf = Path(args.input_pdf).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if shutil.which("docker") is None:
        raise RuntimeError("docker command not found in PATH")

    inspection = inspect_pdf(input_pdf)

    parse_mode = "normal"
    parse_input = input_pdf
    rasterized_pdf = None

    if args.force_rasterize:
        parse_mode = "rasterized"
    elif args.force_normal:
        parse_mode = "normal"
    elif inspection["suspicious"]:
        parse_mode = "rasterized"

    if parse_mode == "rasterized":
        rasterized_dir = output_dir / "intermediate"
        rasterized_dir.mkdir(parents=True, exist_ok=True)
        rasterized_pdf = rasterized_dir / f"{input_pdf.stem}_rasterized.pdf"
        rasterize_pdf(input_pdf, rasterized_pdf, dpi=args.dpi)
        parse_input = rasterized_pdf

    result_root = output_dir / "mineru_output"
    result_root.mkdir(parents=True, exist_ok=True)
    run_mineru(parse_input, result_root, args.language)

    output_stem = find_output_stem(result_root, parse_input.stem)
    txt_dir = find_txt_dir(result_root, output_stem)
    outputs = build_output_map(txt_dir, output_stem)

    metadata = {
        "input_pdf": str(input_pdf),
        "parse_input": str(parse_input),
        "parse_mode": parse_mode,
        "language": args.language,
        "inspection": inspection,
        "outputs": outputs,
    }

    if rasterized_pdf is not None:
        metadata["rasterized_pdf"] = str(rasterized_pdf)

    metadata_path = output_dir / "meta.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))

    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()

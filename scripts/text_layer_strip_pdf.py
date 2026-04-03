#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from typing import Any


def _require_fitz():
    try:
        import fitz  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "text_layer_strip_pdf requires PyMuPDF. Install it with: pip install pymupdf"
        ) from exc
    return fitz


def pdf_page_sizes(pdf_path: Path) -> list[dict[str, float]]:
    fitz = _require_fitz()
    sizes: list[dict[str, float]] = []
    with fitz.open(pdf_path) as doc:
        for index, page in enumerate(doc, start=1):
            sizes.append(
                {
                    "page_number": index,
                    "width": round(float(page.rect.width), 3),
                    "height": round(float(page.rect.height), 3),
                }
            )
    return sizes


def extracted_text_chars(pdf_path: Path) -> int:
    fitz = _require_fitz()
    chars = 0
    with fitz.open(pdf_path) as doc:
        for page in doc:
            chars += len(page.get_text("text").strip())
    return chars


def render_diff_ratios(
    input_pdf: Path,
    output_pdf: Path,
    *,
    dpi: int = 72,
) -> list[float]:
    fitz = _require_fitz()
    ratios: list[float] = []
    with fitz.open(input_pdf) as input_doc, fitz.open(output_pdf) as output_doc:
        if len(input_doc) != len(output_doc):
            return [1.0]
        for input_page, output_page in zip(input_doc, output_doc):
            input_pix = input_page.get_pixmap(dpi=dpi, alpha=False)
            output_pix = output_page.get_pixmap(dpi=dpi, alpha=False)
            if (
                input_pix.width != output_pix.width
                or input_pix.height != output_pix.height
                or len(input_pix.samples) != len(output_pix.samples)
            ):
                ratios.append(1.0)
                continue
            diff_total = sum(
                abs(src - dst)
                for src, dst in zip(input_pix.samples, output_pix.samples)
            )
            ratios.append(diff_total / (255 * len(input_pix.samples)))
    return ratios


def strip_text_layer(input_pdf: Path, output_pdf: Path, dpi: int = 300) -> dict[str, Any]:
    fitz = _require_fitz()
    input_pdf = Path(input_pdf).resolve()
    output_pdf = Path(output_pdf).resolve()
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    input_sizes = pdf_page_sizes(input_pdf)
    output_doc = fitz.open()
    with fitz.open(input_pdf) as source_doc:
        for page in source_doc:
            pixmap = page.get_pixmap(dpi=dpi, alpha=False)
            new_page = output_doc.new_page(
                width=float(page.rect.width),
                height=float(page.rect.height),
            )
            new_page.insert_image(new_page.rect, stream=pixmap.tobytes("png"))

    output_doc.save(output_pdf, garbage=4, deflate=True)
    output_doc.close()

    return {
        "input_pdf": str(input_pdf),
        "output_pdf": str(output_pdf),
        "dpi": dpi,
        "method": "render_page_to_image_pdf",
        "input_page_count": len(input_sizes),
        "input_page_sizes": input_sizes,
    }


def validate_text_layer_stripped(
    input_pdf: Path,
    output_pdf: Path,
    *,
    max_text_chars: int = 0,
    page_size_tolerance: float = 0.01,
    render_diff_dpi: int = 72,
    render_diff_tolerance: float = 0.01,
) -> dict[str, Any]:
    input_pdf = Path(input_pdf).resolve()
    output_pdf = Path(output_pdf).resolve()

    input_sizes = pdf_page_sizes(input_pdf)
    output_sizes = pdf_page_sizes(output_pdf)
    page_count_equal = len(input_sizes) == len(output_sizes)
    page_size_equal = page_count_equal and all(
        abs(src["width"] - dst["width"]) <= page_size_tolerance
        and abs(src["height"] - dst["height"]) <= page_size_tolerance
        for src, dst in zip(input_sizes, output_sizes)
    )
    text_chars = extracted_text_chars(output_pdf)
    text_layer_removed = text_chars <= max_text_chars
    diff_ratios = render_diff_ratios(input_pdf, output_pdf, dpi=render_diff_dpi)
    diff_ratio_max = max(diff_ratios) if diff_ratios else None
    render_fidelity_ok = diff_ratio_max is not None and diff_ratio_max <= render_diff_tolerance
    return {
        "input_pdf": str(input_pdf),
        "output_pdf": str(output_pdf),
        "input_page_count": len(input_sizes),
        "output_page_count": len(output_sizes),
        "input_page_sizes": input_sizes,
        "output_page_sizes": output_sizes,
        "page_count_equal": page_count_equal,
        "page_size_equal": page_size_equal,
        "max_text_chars": max_text_chars,
        "extracted_text_chars": text_chars,
        "text_layer_removed": text_layer_removed,
        "render_diff_dpi": render_diff_dpi,
        "render_diff_tolerance": render_diff_tolerance,
        "render_diff_ratios": diff_ratios,
        "render_diff_ratio_max": diff_ratio_max,
        "render_fidelity_ok": render_fidelity_ok,
    }


def build_provenance_payload(
    input_pdf: Path,
    output_pdf: Path,
    *,
    dpi: int,
    max_text_chars: int,
    page_size_tolerance: float,
    render_diff_dpi: int,
    render_diff_tolerance: float,
) -> dict[str, Any]:
    generation = strip_text_layer(input_pdf, output_pdf, dpi=dpi)
    validation = validate_text_layer_stripped(
        input_pdf,
        output_pdf,
        max_text_chars=max_text_chars,
        page_size_tolerance=page_size_tolerance,
        render_diff_dpi=render_diff_dpi,
        render_diff_tolerance=render_diff_tolerance,
    )
    return {
        "generator": "text_layer_strip_pdf",
        "generator_version": 1,
        "generation": generation,
        "validation": validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a text-layer stripped PDF by rendering each page to an image-only PDF and emit validation provenance."
    )
    parser.add_argument("input_pdf")
    parser.add_argument("output_pdf")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--max-text-chars", type=int, default=0)
    parser.add_argument("--page-size-tolerance", type=float, default=0.01)
    parser.add_argument("--render-diff-dpi", type=int, default=72)
    parser.add_argument("--render-diff-tolerance", type=float, default=0.01)
    parser.add_argument(
        "--provenance-json",
        default=None,
        help="Optional path for provenance/validation JSON. Defaults to <output>.provenance.json",
    )
    args = parser.parse_args()

    input_pdf = Path(args.input_pdf)
    output_pdf = Path(args.output_pdf)
    provenance_json = (
        Path(args.provenance_json)
        if args.provenance_json
        else output_pdf.with_suffix(output_pdf.suffix + ".provenance.json")
    )

    payload = build_provenance_payload(
        input_pdf,
        output_pdf,
        dpi=args.dpi,
        max_text_chars=args.max_text_chars,
        page_size_tolerance=args.page_size_tolerance,
        render_diff_dpi=args.render_diff_dpi,
        render_diff_tolerance=args.render_diff_tolerance,
    )
    provenance_json.parent.mkdir(parents=True, exist_ok=True)
    provenance_json.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

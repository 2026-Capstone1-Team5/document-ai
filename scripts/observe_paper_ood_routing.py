#!/usr/bin/env python3

import argparse
import json
import re
from collections import Counter, defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from mineru.utils.pdf_classify import (
    classify,
    extract_pages,
    get_avg_cleaned_chars_per_page,
    get_high_image_coverage_ratio,
)
from pdfminer.high_level import extract_text
from pdfminer.layout import LAParams


REPO_ROOT = Path(__file__).resolve().parent.parent
CID_PATTERN = re.compile(r"\(cid:\d+\)")
CHARS_THRESHOLD = 50
INVALID_CHAR_RATIO_THRESHOLD = 0.05
IMAGE_COVERAGE_RATIO_THRESHOLD = 0.8


def resolve_repo_path(raw_path: str | Path) -> Path:
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def load_manifest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"Manifest row {line_number} must be a JSON object")
        rows.append(row)
    return rows


def invalid_char_ratio(sample_pdf_bytes: bytes) -> float:
    laparams = LAParams(
        line_overlap=0.5,
        char_margin=2.0,
        line_margin=0.5,
        word_margin=0.1,
        boxes_flow=None,
        detect_vertical=False,
        all_texts=False,
    )
    text = extract_text(pdf_file=BytesIO(sample_pdf_bytes), laparams=laparams).replace("\n", "")
    matches = CID_PATTERN.findall(text)
    cid_count = len(matches)
    cid_len = sum(len(match) for match in matches)
    text_len = len(text)
    if text_len == 0:
        return 0.0
    return cid_count / (cid_count + text_len - cid_len)


def cid_char_ratio(sample_pdf_bytes: bytes) -> float:
    """Backward-compatible alias for the current MinerU invalid-character ratio."""
    return invalid_char_ratio(sample_pdf_bytes)


def observe_pdf(pdf_path: Path) -> dict[str, Any]:
    pdf_bytes = pdf_path.read_bytes()
    sample_pdf_bytes = extract_pages(pdf_bytes)
    pdf = pdfium.PdfDocument(sample_pdf_bytes)
    try:
        page_count = len(pdf)
        pages_to_check = min(page_count, 10) if page_count else 0
        avg_cleaned_chars_per_page = (
            get_avg_cleaned_chars_per_page(pdf, pages_to_check) if pages_to_check else 0.0
        )
    finally:
        pdf.close()

    cid_ratio = invalid_char_ratio(sample_pdf_bytes)
    classification = classify(pdf_bytes)
    high_image_coverage_ratio = (
        get_high_image_coverage_ratio(sample_pdf_bytes, min(page_count, 10)) if page_count else 0.0
    )
    chars_threshold_passed = avg_cleaned_chars_per_page >= CHARS_THRESHOLD
    invalid_ratio_threshold_passed = cid_ratio <= INVALID_CHAR_RATIO_THRESHOLD
    image_coverage_threshold_passed = high_image_coverage_ratio < IMAGE_COVERAGE_RATIO_THRESHOLD
    return {
        "classify_result": classification,
        "page_count": page_count,
        "pages_checked": min(page_count, 10),
        "avg_cleaned_chars_per_page": avg_cleaned_chars_per_page,
        "invalid_char_ratio": cid_ratio,
        "cid_char_ratio": cid_ratio,
        "invalid_chars_detected": cid_ratio > 0.05,
        "high_image_coverage_ratio": high_image_coverage_ratio,
        "classifier_signal_thresholds": {
            "chars_per_page_min": CHARS_THRESHOLD,
            "invalid_char_ratio_max": INVALID_CHAR_RATIO_THRESHOLD,
            "image_coverage_ratio_max": IMAGE_COVERAGE_RATIO_THRESHOLD,
        },
        "classifier_signal_status": {
            "chars_threshold_passed": chars_threshold_passed,
            "invalid_ratio_threshold_passed": invalid_ratio_threshold_passed,
            "image_coverage_threshold_passed": image_coverage_threshold_passed,
        },
        "classifier_signal_accepts_text_path": (
            chars_threshold_passed
            and invalid_ratio_threshold_passed
            and image_coverage_threshold_passed
        ),
    }


def build_scored_index(scored_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not scored_payload:
        return {}
    comparisons = {
        str(item["doc_id"]): item for item in scored_payload.get("doc_comparisons", [])
    }
    scores_by_doc: dict[str, dict[str, Any]] = defaultdict(dict)
    for item in scored_payload.get("doc_scores", []):
        doc_id = item.get("doc_id")
        variant = item.get("variant")
        if doc_id and variant:
            scores_by_doc[str(doc_id)][str(variant)] = item
    result: dict[str, dict[str, Any]] = {}
    for doc_id, comparison in comparisons.items():
        result[doc_id] = {
            "comparison": comparison,
            "scores": scores_by_doc.get(doc_id, {}),
        }
    return result


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    subgroup_counts = Counter()
    subgroup_txt_counts = Counter()
    cid_by_subgroup: dict[str, list[float]] = defaultdict(list)
    auto_cer_when_txt: list[float] = []
    original_cer_when_txt: list[float] = []
    for row in rows:
        subgroup = str(row.get("subgroup") or "unknown")
        subgroup_counts[subgroup] += 1
        observation = row["observation"]
        if observation["classify_result"] == "txt":
            subgroup_txt_counts[subgroup] += 1
            scored = row.get("scored") or {}
            auto_cer = scored.get("scores", {}).get("auto", {}).get("auxiliary_metrics", {}).get("cer")
            original_cer = scored.get("scores", {}).get("original", {}).get("auxiliary_metrics", {}).get("cer")
            if auto_cer is not None:
                auto_cer_when_txt.append(auto_cer)
            if original_cer is not None:
                original_cer_when_txt.append(original_cer)
        cid_by_subgroup[subgroup].append(observation["cid_char_ratio"])

    return {
        "documents": len(rows),
        "subgroup_counts": dict(subgroup_counts),
        "subgroup_txt_counts": dict(subgroup_txt_counts),
        "subgroup_txt_rates": {
            subgroup: (subgroup_txt_counts[subgroup] / count if count else None)
            for subgroup, count in subgroup_counts.items()
        },
        "mean_cid_ratio_by_subgroup": {
            subgroup: (sum(values) / len(values) if values else None)
            for subgroup, values in cid_by_subgroup.items()
        },
        "mean_original_cer_when_classified_txt": (
            sum(original_cer_when_txt) / len(original_cer_when_txt) if original_cer_when_txt else None
        ),
        "mean_auto_cer_when_classified_txt": (
            sum(auto_cer_when_txt) / len(auto_cer_when_txt) if auto_cer_when_txt else None
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Directly observe MinerU classify() outputs and routing-related proxies for a paper OOD manifest."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--scored-json")
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    manifest_rows = load_manifest(resolve_repo_path(args.manifest))
    scored_index = (
        build_scored_index(json.loads(resolve_repo_path(args.scored_json).read_text(encoding="utf-8")))
        if args.scored_json
        else {}
    )

    observed_rows = []
    for row in manifest_rows:
        doc_id = str(row["doc_id"])
        pdf_path = resolve_repo_path(row["input_pdf"])
        observed_rows.append(
            {
                "doc_id": doc_id,
                "subgroup": row.get("subgroup"),
                "source_bucket": row.get("source_bucket"),
                "input_pdf": str(pdf_path.relative_to(REPO_ROOT)),
                "observation": observe_pdf(pdf_path),
                "scored": scored_index.get(doc_id),
            }
        )

    payload = {
        "manifest": str(resolve_repo_path(args.manifest).relative_to(REPO_ROOT)),
        "scored_json": (
            str(resolve_repo_path(args.scored_json).relative_to(REPO_ROOT))
            if args.scored_json
            else None
        ),
        "summary": summarize(observed_rows),
        "rows": observed_rows,
    }
    output_path = resolve_repo_path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import argparse
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import fitz


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_BENCHMARK_CSV = REPO_ROOT / "benchmark/manifest.csv"
DEFAULT_OUTPUT_MANIFEST = REPO_ROOT / "output/benchmark_reports/paper_routing_evidence_manifest.jsonl"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "benchmark/paper_ood/derived/routing_evidence"
DEFAULT_METADATA_DIR = REPO_ROOT / "benchmark/paper_ood/metadata/routing_evidence"
TARGET_SUBGROUPS = {"receipt", "invoice"}
DEFAULT_PAGE_WIDTH = 595.0
DEFAULT_PAGE_HEIGHT = 842.0
TARGET_TEXT_CHAR_BUDGET = 1800
TARGET_TEXT_FONT_SIZE = 8.0
IMAGE_SCALE_CANDIDATES = (0.72, 0.68, 0.64)
SUBSTITUTION_MAP = str.maketrans(
    {
        "0": "7",
        "1": "8",
        "2": "9",
        "3": "0",
        "4": "1",
        "5": "2",
        "6": "3",
        "7": "4",
        "8": "5",
        "9": "6",
        "a": "m",
        "e": "q",
        "i": "u",
        "o": "y",
        "u": "a",
        "A": "M",
        "E": "Q",
        "I": "U",
        "O": "Y",
        "U": "A",
    }
)


def load_sibling_module(name: str):
    module_path = SCRIPT_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load sibling module: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


observe_module = load_sibling_module("observe_paper_ood_routing")
observe_pdf = observe_module.observe_pdf
load_benchmark_manifest_csv = load_sibling_module("benchmark_manifest_utils").load_benchmark_manifest_csv


def resolve_repo_path(raw_path: str | Path) -> Path:
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def stringify_repo_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_manifest(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        rows.append(json.loads(stripped))
    return rows


def subgroup_for_doc_id(doc_id: str) -> str | None:
    if doc_id.startswith("receipt-"):
        return "receipt"
    if doc_id.startswith("invoice-"):
        return "invoice"
    return None


def source_bucket_for_doc_id(doc_id: str, metadata: dict[str, Any]) -> str:
    dataset = metadata.get("dataset")
    if dataset:
        return f"hf:{dataset}"
    return f"local:{doc_id}"


def build_source_rows_from_benchmark_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in load_benchmark_manifest_csv(path):
        doc_id = str(row["doc_id"])
        subgroup = subgroup_for_doc_id(doc_id)
        if subgroup not in TARGET_SUBGROUPS:
            continue
        metadata_path = REPO_ROOT / "benchmark/paper_ood/metadata" / f"{doc_id}.source.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Missing source metadata for {doc_id}: {metadata_path}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        gold_path = REPO_ROOT / "benchmark/paper_ood/gold" / f"{doc_id}.json"
        if not gold_path.exists():
            raise FileNotFoundError(f"Missing gold artifact for {doc_id}: {gold_path}")
        image_path = REPO_ROOT / str(metadata.get("image_path") or "")
        if not image_path.exists():
            raise FileNotFoundError(f"Missing source image for {doc_id}: {image_path}")
        rows.append({
            "doc_id": doc_id,
            "subgroup": subgroup,
            "input_pdf": row["filename"],
            "image_path": str(image_path.relative_to(REPO_ROOT)),
            "gold_path": str(gold_path.relative_to(REPO_ROOT)),
            "gold_format": "fields_json",
            "metric_family": "token_f1",
            "annotation_source": "manual_from_source_annotation",
            "canonicalization_version": "v1",
            "source_bucket": source_bucket_for_doc_id(doc_id, metadata),
            "freeze_revision": metadata.get("freeze_revision", "paper-routing-evidence-v1"),
            "source_dataset_revision": metadata.get("dataset_revision"),
        })
    return rows


def flatten_field_values(payload: Any) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        if "fields" in payload:
            return flatten_field_values(payload["fields"])
        for value in payload.values():
            values.extend(flatten_field_values(value))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(flatten_field_values(item))
    elif payload is not None:
        text = str(payload).strip()
        if text:
            values.append(text)
    return values


def load_gold_text(gold_path: Path, gold_format: str) -> str:
    if gold_format == "transcript_txt":
        return gold_path.read_text(encoding="utf-8")

    payload = json.loads(gold_path.read_text(encoding="utf-8"))
    if gold_format == "transcript_json":
        if isinstance(payload, dict):
            for key in ("text", "transcript", "content"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        raise ValueError(f"Unsupported transcript_json payload shape: {gold_path}")

    if gold_format == "fields_json":
        return "\n".join(flatten_field_values(payload))

    raise ValueError(f"Unsupported gold_format: {gold_format}")


def build_harmful_text(text: str, *, target_chars: int = TARGET_TEXT_CHAR_BUDGET) -> str:
    normalized_lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    if not normalized_lines:
        normalized_lines = ["fallback receipt line item total subtotal tax payment card visa"]
    corrupted_lines = [line.translate(SUBSTITUTION_MAP) for line in normalized_lines]
    if not corrupted_lines:
        corrupted_lines = ["fallback receipt line item total subtotal tax payment card visa".translate(SUBSTITUTION_MAP)]

    parts: list[str] = []
    index = 0
    while sum(len(part) for part in parts) < target_chars:
        parts.append(corrupted_lines[index % len(corrupted_lines)])
        index += 1
    return "\n".join(parts)


def image_rect_for_scale(page_width: float, page_height: float, scale: float) -> fitz.Rect:
    width = page_width * scale
    height = page_height * scale
    x0 = (page_width - width) / 2.0
    y0 = (page_height - height) / 2.0
    return fitz.Rect(x0, y0, x0 + width, y0 + height)


def _wrapped_text(text: str, usable_width: float, fontsize: float) -> str:
    chars_per_line = max(40, math.floor(usable_width / (fontsize * 0.55)))
    lines = []
    source = text.replace("\r", "\n")
    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        while len(line) > chars_per_line:
            lines.append(line[:chars_per_line])
            line = line[chars_per_line:]
        if line:
            lines.append(line)
    return "\n".join(lines)


def add_invisible_text(page: fitz.Page, text: str, page_width: float, page_height: float) -> None:
    usable_width = page_width - 60.0
    rect = fitz.Rect(30, 30, page_width - 30, page_height - 30)
    for trim_ratio in (1.0, 0.9, 0.8, 0.7, 0.6):
        candidate_text = text[: max(200, int(len(text) * trim_ratio))]
        for fontsize in (TARGET_TEXT_FONT_SIZE, 7.0, 6.0, 5.5):
            text_block = _wrapped_text(candidate_text, usable_width, fontsize)
            inserted = page.insert_textbox(rect, text_block, fontsize=fontsize, render_mode=3)
            if inserted >= 0:
                return
    raise RuntimeError("Invisible text insertion failed to fit on the page")


def materialize_pdf(
    *,
    image_path: Path,
    harmful_text: str,
    output_pdf: Path,
    page_width: float = DEFAULT_PAGE_WIDTH,
    page_height: float = DEFAULT_PAGE_HEIGHT,
) -> dict[str, Any]:
    last_observation: dict[str, Any] | None = None
    for scale in IMAGE_SCALE_CANDIDATES:
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        doc = fitz.open()
        page = doc.new_page(width=page_width, height=page_height)
        page.insert_image(image_rect_for_scale(page_width, page_height, scale), filename=str(image_path))
        add_invisible_text(page, harmful_text, page_width, page_height)
        doc.save(output_pdf)
        doc.close()

        observation = observe_pdf(output_pdf)
        last_observation = observation
        if observation["classify_result"] == "txt" and observation["classifier_signal_accepts_text_path"]:
            return {
                "selected_image_scale": scale,
                "observation": observation,
            }

    raise RuntimeError(
        f"Failed to materialize a txt-classified routing-evidence PDF for {image_path.name}: {last_observation}"
    )


def build_manifest_row(
    *,
    source_row: dict[str, Any],
    donor_row: dict[str, Any],
    output_pdf: Path,
) -> dict[str, Any]:
    doc_id = f"{source_row['doc_id']}-routingtrap"
    row = dict(source_row)
    row["doc_id"] = doc_id
    row["input_pdf"] = stringify_repo_path(output_pdf)
    row["source_bucket"] = f"synthetic:routing-evidence:{source_row.get('source_bucket', 'unknown')}"
    row["suspected_issue"] = "controlled_harmful_text_layer"
    row["inclusion_reason"] = "direct_classifier_reliability_probe"
    row["freeze_revision"] = "paper-routing-evidence-v1"
    row["base_doc_id"] = source_row["doc_id"]
    row["donor_doc_id"] = donor_row["doc_id"]
    return row


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Materialize a controlled routing-evidence dataset with harmful text layers over receipt/invoice images."
    )
    parser.add_argument("--benchmark-csv", default=str(DEFAULT_BENCHMARK_CSV))
    parser.add_argument("--output-manifest", default=str(DEFAULT_OUTPUT_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--metadata-dir", default=str(DEFAULT_METADATA_DIR))
    parser.add_argument("--max-docs", type=int)
    parser.add_argument("--subgroup", action="append", dest="subgroups")
    args = parser.parse_args()

    benchmark_csv = resolve_repo_path(args.benchmark_csv)
    output_manifest = resolve_repo_path(args.output_manifest)
    output_dir = resolve_repo_path(args.output_dir)
    metadata_dir = resolve_repo_path(args.metadata_dir)
    subgroups = set(args.subgroups or TARGET_SUBGROUPS)

    source_rows = [
        row
        for row in build_source_rows_from_benchmark_csv(benchmark_csv)
        if row.get("subgroup") in subgroups
    ]
    if args.max_docs is not None:
        source_rows = source_rows[: args.max_docs]
    if not source_rows:
        raise ValueError(f"No source rows found in {benchmark_csv} for subgroups={sorted(subgroups)}")

    materialized_rows: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []

    for index, source_row in enumerate(source_rows):
        donor_row = source_rows[(index + 1) % len(source_rows)]
        image_path = resolve_repo_path(source_row["image_path"])
        if not image_path.exists():
            raise FileNotFoundError(f"Missing PNG backing image for {source_row['doc_id']}: {image_path}")
        donor_gold_path = resolve_repo_path(donor_row["gold_path"])
        harmful_text = build_harmful_text(load_gold_text(donor_gold_path, donor_row["gold_format"]))

        output_pdf = output_dir / f"{source_row['doc_id']}-routingtrap.pdf"
        materialized = materialize_pdf(image_path=image_path, harmful_text=harmful_text, output_pdf=output_pdf)
        manifest_row = build_manifest_row(source_row=source_row, donor_row=donor_row, output_pdf=output_pdf)
        materialized_rows.append(manifest_row)

        metadata = {
            "doc_id": manifest_row["doc_id"],
            "base_doc_id": source_row["doc_id"],
            "donor_doc_id": donor_row["doc_id"],
            "image_path": str(image_path.relative_to(REPO_ROOT)),
            "output_pdf": stringify_repo_path(output_pdf),
            "selected_image_scale": materialized["selected_image_scale"],
            "harmful_text_preview": harmful_text[:400],
            "harmful_text_chars": len(harmful_text),
            "observation": materialized["observation"],
        }
        metadata_path = metadata_dir / f"{manifest_row['doc_id']}.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report_rows.append(metadata)

    write_jsonl(output_manifest, materialized_rows)
    report = {
        "benchmark_csv": str(benchmark_csv.relative_to(REPO_ROOT)),
        "output_manifest": str(output_manifest.relative_to(REPO_ROOT)),
        "documents": len(materialized_rows),
        "subgroups": sorted(subgroups),
        "rows": report_rows,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

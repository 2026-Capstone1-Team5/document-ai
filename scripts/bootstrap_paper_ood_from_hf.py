#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FREEZE_REVISION = "paper-ood-v1"
SUPPORTED_DATASETS = {
    "jsdnrs/ICDAR2019-SROIE",
    "naver-clova-ix/cord-v2",
    "davidle7/funsd-json",
    "philschmid/ocr-invoice-data",
}


def _require_dependencies():
    try:
        from datasets import load_dataset  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError as exc:  # pragma: no cover - runtime guard
        raise SystemExit(
            "bootstrap_paper_ood_from_hf requires datasets and pillow. "
            "Example: uv run --with datasets --with pillow python scripts/bootstrap_paper_ood_from_hf.py ..."
        ) from exc
    return load_dataset, Image


def resolve_repo_path(raw_path: str | Path) -> Path:
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze one HF dataset row into the repo-local paper OOD layout and bootstrap a gold artifact when possible."
    )
    parser.add_argument("--dataset", required=True, choices=sorted(SUPPORTED_DATASETS))
    parser.add_argument("--split", required=True)
    parser.add_argument("--index", required=True, type=int)
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--subgroup", required=True)
    parser.add_argument("--source-shortname", required=True)
    parser.add_argument("--output-dir", default="benchmark/paper_ood/raw")
    parser.add_argument("--gold-dir", default="benchmark/paper_ood/gold")
    parser.add_argument("--derived-dir", default="benchmark/paper_ood/derived")
    parser.add_argument("--metadata-dir", default="benchmark/paper_ood/metadata")
    parser.add_argument("--manifest-row-output", type=Path)
    parser.add_argument("--metadata-output", type=Path)
    parser.add_argument("--freeze-revision", default=DEFAULT_FREEZE_REVISION)
    parser.add_argument("--annotation-source", default="manual_from_source_annotation")
    parser.add_argument("--language", default="en")
    parser.add_argument("--gold-format", default="fields_json")
    parser.add_argument("--metric-family", default="token_f1")
    parser.add_argument("--source-bucket")
    parser.add_argument("--suspected-issue")
    parser.add_argument("--inclusion-reason")
    parser.add_argument("--skip-gold-bootstrap", action="store_true")
    return parser.parse_args()


def flatten_scalar_map(payload: Any, *, prefix: str = "") -> dict[str, str]:
    results: dict[str, str] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            results.update(flatten_scalar_map(value, prefix=child_prefix))
        return results
    if isinstance(payload, list):
        parts: list[str] = []
        for item in payload:
            if isinstance(item, (str, int, float)):
                text = str(item).strip()
                if text:
                    parts.append(text)
            elif isinstance(item, dict):
                text_candidates = []
                for candidate_key in ("text", "value", "word", "nm", "price", "key", "content"):
                    candidate = item.get(candidate_key)
                    if isinstance(candidate, str) and candidate.strip():
                        text_candidates.append(candidate.strip())
                if not text_candidates:
                    nested = flatten_scalar_map(item)
                    if nested:
                        text_candidates.extend(value for value in nested.values() if value.strip())
                if text_candidates:
                    parts.append(" ".join(text_candidates))
        if parts and prefix:
            results[prefix] = " ".join(parts)
        return results
    if isinstance(payload, (str, int, float)):
        text = str(payload).strip()
        if text and prefix:
            results[prefix] = text
    return results


def bootstrap_sroie_fields(row: dict[str, Any]) -> dict[str, str]:
    entities = row.get("entities") or {}
    if not isinstance(entities, dict):
        return {}
    return {str(k): str(v).strip() for k, v in entities.items() if str(v).strip()}


def bootstrap_cord_fields(row: dict[str, Any]) -> dict[str, str]:
    raw = row.get("ground_truth") or ""
    if not isinstance(raw, str) or not raw.strip():
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        return {}
    if "gt_parse" in payload:
        return flatten_scalar_map(payload["gt_parse"])
    return flatten_scalar_map(payload)


def bootstrap_funsd_fields(row: dict[str, Any]) -> dict[str, str]:
    raw = row.get("text_output") or ""
    if not isinstance(raw, str) or not raw.strip():
        return {}
    payload = json.loads(raw)
    if isinstance(payload, dict) and "form" in payload:
        form = payload["form"]
        if isinstance(form, list):
            results: dict[str, str] = {}
            counters: dict[str, int] = {}
            for item in form:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or "field").strip().lower().replace(" ", "_")
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                counters[label] = counters.get(label, 0) + 1
                results[f"{label}_{counters[label]:02d}"] = text
            if results:
                return results
    return flatten_scalar_map(payload)


def bootstrap_invoice_fields(row: dict[str, Any]) -> dict[str, str]:
    raw = row.get("parsed_data") or ""
    if not isinstance(raw, str) or not raw.strip():
        return {}
    payload = json.loads(raw)
    return flatten_scalar_map(payload)


def bootstrap_gold_fields(dataset_name: str, row: dict[str, Any]) -> dict[str, str]:
    if dataset_name == "jsdnrs/ICDAR2019-SROIE":
        return bootstrap_sroie_fields(row)
    if dataset_name == "naver-clova-ix/cord-v2":
        return bootstrap_cord_fields(row)
    if dataset_name == "davidle7/funsd-json":
        return bootstrap_funsd_fields(row)
    if dataset_name == "philschmid/ocr-invoice-data":
        return bootstrap_invoice_fields(row)
    raise ValueError(f"Unsupported dataset for bootstrap: {dataset_name}")


def save_image_and_pdf(image: Any, image_path: Path, pdf_path: Path) -> None:
    image_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    rgb = image.convert("RGB")
    rgb.save(image_path)
    rgb.save(pdf_path, "PDF", resolution=100.0)


def build_manifest_row(args: argparse.Namespace, pdf_path: Path, gold_path: Path) -> dict[str, Any]:
    return {
        "doc_id": args.doc_id,
        "input_pdf": str(pdf_path.relative_to(REPO_ROOT)),
        "subgroup": args.subgroup,
        "source_bucket": args.source_bucket or f"hf:{args.dataset}",
        "gold_path": str(gold_path.relative_to(REPO_ROOT)),
        "gold_format": args.gold_format,
        "metric_family": args.metric_family,
        "annotation_source": args.annotation_source,
        "canonicalization_version": "v1",
        "language": args.language,
        "suspected_issue": args.suspected_issue or "needs_review",
        "inclusion_reason": args.inclusion_reason or "hf_bootstrap_import",
        "freeze_revision": args.freeze_revision,
    }


def main() -> int:
    args = parse_args()
    load_dataset, _ = _require_dependencies()

    dataset = load_dataset(args.dataset, split=f"{args.split}[{args.index}:{args.index + 1}]")
    if len(dataset) != 1:
        raise SystemExit(f"Unable to load exactly one row for {args.dataset}:{args.split}[{args.index}]")
    row = dataset[0]
    image = row.get("image")
    if image is None:
        raise SystemExit(f"Dataset row has no image field: {args.dataset}")

    output_dir = resolve_repo_path(args.output_dir)
    gold_dir = resolve_repo_path(args.gold_dir)
    metadata_dir = resolve_repo_path(args.metadata_dir)
    image_path = output_dir / f"{args.doc_id}.png"
    pdf_path = output_dir / f"{args.doc_id}.pdf"
    gold_path = gold_dir / (
        f"{args.doc_id}.json" if args.gold_format in {"fields_json", "transcript_json"} else f"{args.doc_id}.txt"
    )
    metadata_path = resolve_repo_path(args.metadata_output) if args.metadata_output else metadata_dir / f"{args.doc_id}.source.json"

    save_image_and_pdf(image, image_path, pdf_path)

    bootstrapped_gold: dict[str, Any] | None = None
    if not args.skip_gold_bootstrap and args.gold_format == "fields_json":
        bootstrapped_gold = bootstrap_gold_fields(args.dataset, row)
        gold_path.parent.mkdir(parents=True, exist_ok=True)
        gold_path.write_text(json.dumps(bootstrapped_gold, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    metadata = {
        "doc_id": args.doc_id,
        "dataset": args.dataset,
        "split": args.split,
        "index": args.index,
        "source_shortname": args.source_shortname,
        "image_path": str(image_path.relative_to(REPO_ROOT)),
        "pdf_path": str(pdf_path.relative_to(REPO_ROOT)),
        "gold_path": str(gold_path.relative_to(REPO_ROOT)),
        "row_keys": sorted(row.keys()),
        "bootstrapped_gold_keys": sorted(bootstrapped_gold.keys()) if isinstance(bootstrapped_gold, dict) else [],
        "freeze_revision": args.freeze_revision,
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest_row = build_manifest_row(args, pdf_path, gold_path)
    if args.manifest_row_output:
        out = resolve_repo_path(args.manifest_row_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest_row, ensure_ascii=False) + "\n", encoding="utf-8")

    payload = {
        "image_path": str(image_path.relative_to(REPO_ROOT)),
        "pdf_path": str(pdf_path.relative_to(REPO_ROOT)),
        "gold_path": str(gold_path.relative_to(REPO_ROOT)),
        "metadata_path": str(metadata_path.relative_to(REPO_ROOT)),
        "manifest_row": manifest_row,
        "bootstrapped_gold": bootstrapped_gold,
    }
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

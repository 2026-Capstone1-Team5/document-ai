#!/usr/bin/env python3

import argparse
import json
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = Path(__file__).resolve().parent / "parse_document.py"
SUPPORTED_METRIC_FAMILIES = {"exact_match", "token_f1", "cer", "wer", "ned"}
SUPPORTED_GOLD_FORMATS = {"fields_json", "transcript_txt", "transcript_json"}
VARIANT_SPECS = {
    "original": {
        "requested_mode": "normal",
        "flags": ["--force-normal"],
        "input_field": "input_pdf",
    },
    "rasterized": {
        "requested_mode": "rasterized",
        "flags": ["--force-rasterize"],
        "input_field": "input_pdf",
    },
    "auto": {
        "requested_mode": "auto",
        "flags": [],
        "input_field": "input_pdf",
    },
    "text_layer_stripped": {
        "requested_mode": "normal",
        "flags": ["--force-normal"],
        "input_field": "stripped_pdf",
    },
}
REQUIRED_MANIFEST_FIELDS = {
    "doc_id",
    "input_pdf",
    "subgroup",
    "gold_path",
    "gold_format",
    "metric_family",
    "annotation_source",
    "canonicalization_version",
}


def resolve_repo_path(raw_path: str | Path) -> Path:
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_doc_ids: set[str] = set()
    for line_number, raw_line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"Manifest row {line_number} must be a JSON object")
        missing = sorted(field for field in REQUIRED_MANIFEST_FIELDS if not row.get(field))
        if missing:
            raise ValueError(
                f"Manifest row {line_number} missing required fields: {', '.join(missing)}"
            )
        doc_id = str(row["doc_id"])
        if doc_id in seen_doc_ids:
            raise ValueError(f"Duplicate doc_id in manifest: {doc_id}")
        seen_doc_ids.add(doc_id)
        metric_family = str(row["metric_family"])
        if metric_family not in SUPPORTED_METRIC_FAMILIES:
            raise ValueError(
                f"Unsupported metric_family for doc_id={doc_id}: {metric_family}"
            )
        gold_format = str(row["gold_format"])
        if gold_format not in SUPPORTED_GOLD_FORMATS:
            raise ValueError(
                f"Unsupported gold_format for doc_id={doc_id}: {gold_format}"
            )
        normalized = {key: value for key, value in row.items()}
        normalized["doc_id"] = doc_id
        normalized["language"] = str(row.get("language") or "en")
        normalized["input_pdf"] = str(resolve_repo_path(row["input_pdf"]))
        normalized["gold_path"] = str(resolve_repo_path(row["gold_path"]))
        if row.get("stripped_pdf"):
            normalized["stripped_pdf"] = str(resolve_repo_path(row["stripped_pdf"]))
        if not Path(normalized["gold_path"]).exists():
            raise ValueError(
                f"Missing gold artifact for doc_id={doc_id}: {normalized['gold_path']}"
            )
        rows.append(normalized)
    return rows


def resolve_markdown_output(meta: dict[str, Any]) -> tuple[Path | None, str | None]:
    outputs = meta.get("outputs", {}) if isinstance(meta.get("outputs"), dict) else {}
    for key in ("selected_markdown", "markdown"):
        raw_path = outputs.get(key)
        if not raw_path:
            continue
        path = Path(raw_path)
        if path.exists():
            return path, key
    for key in ("selected_markdown", "markdown"):
        raw_path = outputs.get(key)
        if raw_path:
            return Path(raw_path), key
    return None, None


def canonicalize_variant_name(raw: str) -> str:
    normalized = raw.strip().lower().replace("-", "_")
    if normalized == "normal":
        normalized = "original"
    if normalized == "stripped":
        normalized = "text_layer_stripped"
    if normalized not in VARIANT_SPECS:
        raise ValueError(f"Unsupported variant: {raw}")
    return normalized


def resolve_input_path(row: dict[str, Any], variant: str) -> Path:
    spec = VARIANT_SPECS[variant]
    input_field = spec["input_field"]
    raw_path = row.get(input_field)
    if not raw_path:
        raise ValueError(f"doc_id={row['doc_id']} missing required field for {variant}: {input_field}")
    return resolve_repo_path(raw_path)


def run_variant(
    *,
    row: dict[str, Any],
    variant: str,
    output_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    spec = VARIANT_SPECS[variant]
    input_pdf = resolve_input_path(row, variant)
    started_at = time.monotonic()
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(SCRIPT_PATH),
        str(input_pdf),
        str(output_dir),
        "--language",
        row["language"],
        *spec["flags"],
    ]
    if not input_pdf.exists():
        return {
            "variant": variant,
            "requested_mode": spec["requested_mode"],
            "status": "failed",
            "failure_reason": f"missing_input_pdf:{input_pdf}",
            "source_pdf": str(input_pdf),
            "elapsed_seconds": round(time.monotonic() - started_at, 3),
            "command": command,
        }

    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "variant": variant,
            "requested_mode": spec["requested_mode"],
            "status": "failed",
            "failure_reason": "timeout",
            "source_pdf": str(input_pdf),
            "elapsed_seconds": round(time.monotonic() - started_at, 3),
            "command": command,
        }

    elapsed_seconds = round(time.monotonic() - started_at, 3)
    meta_path = output_dir / "meta.json"
    if completed.returncode != 0:
        stderr_lines = [line for line in (completed.stderr or "").splitlines() if line.strip()]
        return {
            "variant": variant,
            "requested_mode": spec["requested_mode"],
            "status": "failed",
            "failure_reason": stderr_lines[-1] if stderr_lines else f"returncode_{completed.returncode}",
            "source_pdf": str(input_pdf),
            "elapsed_seconds": elapsed_seconds,
            "command": command,
        }
    if not meta_path.exists():
        return {
            "variant": variant,
            "requested_mode": spec["requested_mode"],
            "status": "failed",
            "failure_reason": "missing_meta_json",
            "source_pdf": str(input_pdf),
            "elapsed_seconds": elapsed_seconds,
            "command": command,
        }

    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, JSONDecodeError):
        return {
            "variant": variant,
            "requested_mode": spec["requested_mode"],
            "status": "failed",
            "failure_reason": "invalid_meta_json",
            "source_pdf": str(input_pdf),
            "elapsed_seconds": elapsed_seconds,
            "meta_path": str(meta_path),
            "command": command,
        }

    markdown_path, markdown_output_key = resolve_markdown_output(meta)
    return {
        "variant": variant,
        "requested_mode": spec["requested_mode"],
        "status": "succeeded",
        "failure_reason": None,
        "source_pdf": str(input_pdf),
        "elapsed_seconds": elapsed_seconds,
        "meta_path": str(meta_path),
        "parse_mode": meta.get("parse_mode"),
        "inspection": meta.get("inspection"),
        "outputs": meta.get("outputs"),
        "markdown_path": str(markdown_path) if markdown_path else None,
        "markdown_output_key": markdown_output_key,
        "command": command,
    }


def benchmark_document(
    *,
    row: dict[str, Any],
    run_root: Path,
    variants: list[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    doc_output_dir = run_root / row["doc_id"]
    results: dict[str, Any] = {}
    for variant in variants:
        results[variant] = run_variant(
            row=row,
            variant=variant,
            output_dir=doc_output_dir / variant,
            timeout_seconds=timeout_seconds,
        )
    completed_variants = [
        variant for variant, payload in results.items() if payload["status"] == "succeeded"
    ]
    return {
        "doc_id": row["doc_id"],
        "input_pdf": str(resolve_input_path(row, "original")),
        "language": row["language"],
        "subgroup": row["subgroup"],
        "source_bucket": row.get("source_bucket"),
        "gold": {
            "gold_path": row["gold_path"],
            "gold_format": row["gold_format"],
            "metric_family": row["metric_family"],
            "annotation_source": row["annotation_source"],
            "canonicalization_version": row["canonicalization_version"],
        },
        "manifest_row": row,
        "variants": results,
        "paired_complete": len(completed_variants) == len(variants),
        "completed_variants": completed_variants,
    }


def summarize(results: list[dict[str, Any]], variants: list[str]) -> dict[str, Any]:
    attempted = len(results)
    fully_completed = sum(1 for row in results if row["paired_complete"])
    variant_success_counts = {
        variant: sum(
            1
            for row in results
            if row["variants"].get(variant, {}).get("status") == "succeeded"
        )
        for variant in variants
    }
    variant_elapsed: dict[str, list[float]] = defaultdict(list)
    failure_counter: Counter[str] = Counter()
    subgroup_counts: Counter[str] = Counter()
    subgroup_complete_counts: Counter[str] = Counter()
    for row in results:
        subgroup = str(row.get("subgroup") or "unknown")
        subgroup_counts[subgroup] += 1
        if row["paired_complete"]:
            subgroup_complete_counts[subgroup] += 1
        for variant in variants:
            payload = row["variants"].get(variant, {})
            if payload.get("status") == "succeeded" and payload.get("elapsed_seconds") is not None:
                variant_elapsed[variant].append(payload["elapsed_seconds"])
            elif payload.get("failure_reason"):
                failure_counter[f"{variant}:{payload['failure_reason']}"] += 1
    runtime = {}
    for variant in variants:
        timings = variant_elapsed[variant]
        runtime[variant] = {
            "median_elapsed_seconds": statistics.median(timings) if timings else None,
            "avg_elapsed_seconds": statistics.fmean(timings) if timings else None,
            "p95_elapsed_seconds": (
                sorted(timings)[max(0, min(len(timings) - 1, int(round((len(timings) - 1) * 0.95))))]
                if timings
                else None
            ),
        }
    return {
        "attempted_documents": attempted,
        "fully_completed_documents": fully_completed,
        "paired_completeness_rate": fully_completed / attempted if attempted else None,
        "variant_success_counts": variant_success_counts,
        "variant_success_rates": {
            variant: (variant_success_counts[variant] / attempted if attempted else None)
            for variant in variants
        },
        "subgroup_counts": dict(subgroup_counts),
        "subgroup_paired_complete_counts": dict(subgroup_complete_counts),
        "runtime": runtime,
        "failure_reasons": dict(failure_counter),
    }


def write_report(report: dict[str, Any], run_root: Path, report_dir: Path) -> tuple[Path, Path]:
    results_path = run_root / "results.json"
    results_path.write_text(json.dumps(report, indent=2))

    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")
    summary_path = report_dir / f"paper_ood_benchmark_{timestamp}.json"
    summary_payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": report["manifest"],
        "run_root": report["run_root"],
        "variants": report["variants"],
        "summary": report["summary"],
        "source_results_json": str(results_path.resolve()),
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2))
    latest_path = report_dir / "latest_paper_ood_benchmark_summary.json"
    latest_path.write_text(json.dumps(summary_payload, indent=2))
    return results_path, summary_path


def parse_variant_list(raw: str) -> list[str]:
    variants = [canonicalize_variant_name(item) for item in raw.split(",") if item.strip()]
    if not variants:
        raise ValueError("At least one variant is required")
    deduped: list[str] = []
    for variant in variants:
        if variant not in deduped:
            deduped.append(variant)
    return deduped


def validate_variant_requirements(rows: list[dict[str, Any]], variants: list[str]) -> None:
    if "text_layer_stripped" not in variants:
        return
    missing = [
        row["doc_id"]
        for row in rows
        if not row.get("stripped_pdf") or not Path(str(row["stripped_pdf"])).exists()
    ]
    if missing:
        preview = ", ".join(missing[:10])
        raise ValueError(
            "text_layer_stripped variant requires existing stripped_pdf entries for all rows; "
            f"missing for doc_ids: {preview}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the paper OOD paired benchmark from a JSONL manifest using parse_document variants."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-root", default="output/paper_ood_benchmark")
    parser.add_argument("--report-dir", default="output/benchmark_reports")
    parser.add_argument("--variants", default="original,rasterized,auto")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    run_root = (REPO_ROOT / args.run_root).resolve()
    report_dir = (REPO_ROOT / args.report_dir).resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    rows = load_manifest(manifest_path)
    if args.offset:
        rows = rows[args.offset :]
    if args.limit > 0:
        rows = rows[: args.limit]
    variants = parse_variant_list(args.variants)
    validate_variant_requirements(rows, variants)

    results = []
    for sample_index, row in enumerate(rows, start=1):
        result = benchmark_document(
            row=row,
            run_root=run_root,
            variants=variants,
            timeout_seconds=args.timeout_seconds,
        )
        results.append(result)
        print(
            f"[{sample_index}/{len(rows)}] doc_id={row['doc_id']} paired_complete={result['paired_complete']} completed={','.join(result['completed_variants']) or 'none'}"
        )

    report = {
        "manifest": str(manifest_path),
        "run_root": str(run_root),
        "variants": variants,
        "summary": summarize(results, variants),
        "results": results,
    }
    results_path, summary_path = write_report(report, run_root, report_dir)
    print(json.dumps(report["summary"], indent=2))
    print(f"Saved results: {results_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()

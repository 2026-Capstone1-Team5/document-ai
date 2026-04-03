#!/usr/bin/env python3

import argparse
import json
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from benchmark_manifest_utils import resolve_repo_path


REPO_ROOT = Path(__file__).resolve().parent.parent
PARSE_SCRIPT = SCRIPT_DIR / "parse_document.py"
VARIANT_SPECS = {
    "original": {"requested_mode": "normal", "flags": ["--force-normal"]},
    "rasterized": {"requested_mode": "rasterized", "flags": ["--force-rasterize"]},
    "auto": {"requested_mode": "auto", "flags": []},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run original/rasterized/auto parsing across the structured/unstructured benchmark manifest."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--variants", default="original,rasterized,auto")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--output-json")
    parser.add_argument("--output-summary")
    return parser.parse_args()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        row = json.loads(stripped)
        if not isinstance(row, dict):
            raise ValueError(f"Manifest row {line_number} must be a JSON object")
        if not row.get("doc_id") or not row.get("input_pdf") or not row.get("benchmark_group"):
            raise ValueError(f"Manifest row {line_number} missing required fields")
        rows.append(row)
    return rows


def resolve_markdown_output(meta: dict[str, Any]) -> tuple[str | None, str | None]:
    outputs = meta.get("outputs", {}) if isinstance(meta.get("outputs"), dict) else {}
    for key in ("selected_markdown", "markdown"):
        raw_path = outputs.get(key)
        if not raw_path:
            continue
        path = Path(raw_path)
        if path.exists():
            return str(path), key
    for key in ("selected_markdown", "markdown"):
        raw_path = outputs.get(key)
        if raw_path:
            return str(Path(raw_path)), key
    return None, None


def run_variant(row: dict[str, Any], variant: str, run_root: Path, timeout_seconds: int) -> dict[str, Any]:
    spec = VARIANT_SPECS[variant]
    source_pdf = resolve_repo_path(row["input_pdf"])
    started = time.monotonic()
    output_dir = run_root / row["doc_id"] / variant
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(PARSE_SCRIPT),
        str(source_pdf),
        str(output_dir),
        "--language",
        str(row.get("language") or "en"),
        *spec["flags"],
    ]
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
            "status": "failed",
            "failure_reason": "timeout",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "requested_mode": spec["requested_mode"],
        }
    elapsed = round(time.monotonic() - started, 3)
    meta_path = output_dir / "meta.json"
    if completed.returncode != 0 or not meta_path.exists():
        failure_reason = "missing_meta_json" if completed.returncode == 0 else f"returncode_{completed.returncode}"
        stderr_lines = [line for line in completed.stderr.splitlines() if line.strip()]
        if stderr_lines:
            failure_reason = stderr_lines[-1]
        return {
            "variant": variant,
            "status": "failed",
            "failure_reason": failure_reason,
            "elapsed_seconds": elapsed,
            "requested_mode": spec["requested_mode"],
        }
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    markdown_path, markdown_key = resolve_markdown_output(meta)
    markdown_chars = None
    if markdown_path and Path(markdown_path).exists():
        markdown_chars = len(Path(markdown_path).read_text(encoding="utf-8", errors="ignore"))
    return {
        "variant": variant,
        "status": "succeeded",
        "failure_reason": None,
        "elapsed_seconds": elapsed,
        "requested_mode": spec["requested_mode"],
        "parse_mode": meta.get("parse_mode"),
        "inspection": meta.get("inspection"),
        "markdown_path": markdown_path,
        "markdown_output_key": markdown_key,
        "markdown_chars": markdown_chars,
    }


def summarize(results: list[dict[str, Any]], variants: list[str]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total_documents": len(results),
        "variants": variants,
        "overall_variant_summary": {},
        "benchmark_group_summary": {},
    }
    for variant in variants:
        variant_rows = [row["variants"][variant] for row in results]
        success_rows = [row for row in variant_rows if row["status"] == "succeeded"]
        summary["overall_variant_summary"][variant] = {
            "attempted": len(variant_rows),
            "succeeded": len(success_rows),
            "success_rate": (len(success_rows) / len(variant_rows)) if variant_rows else None,
            "mean_elapsed_seconds": statistics.fmean([row["elapsed_seconds"] for row in success_rows]) if success_rows else None,
            "mean_markdown_chars": statistics.fmean([row["markdown_chars"] for row in success_rows if row.get("markdown_chars") is not None]) if success_rows and any(row.get("markdown_chars") is not None for row in success_rows) else None,
        }

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        grouped[str(row["benchmark_group"])].append(row)

    for group_name, group_rows in grouped.items():
        per_variant = {}
        for variant in variants:
            variant_rows = [row["variants"][variant] for row in group_rows]
            success_rows = [row for row in variant_rows if row["status"] == "succeeded"]
            per_variant[variant] = {
                "attempted": len(variant_rows),
                "succeeded": len(success_rows),
                "success_rate": (len(success_rows) / len(variant_rows)) if variant_rows else None,
                "mean_elapsed_seconds": statistics.fmean([row["elapsed_seconds"] for row in success_rows]) if success_rows else None,
                "mean_markdown_chars": statistics.fmean([row["markdown_chars"] for row in success_rows if row.get("markdown_chars") is not None]) if success_rows and any(row.get("markdown_chars") is not None for row in success_rows) else None,
            }
        summary["benchmark_group_summary"][group_name] = {
            "documents": len(group_rows),
            "variants": per_variant,
        }
    return summary


def main() -> int:
    args = parse_args()
    variants = [variant.strip() for variant in args.variants.split(",") if variant.strip()]
    unsupported = [variant for variant in variants if variant not in VARIANT_SPECS]
    if unsupported:
        raise SystemExit(f"Unsupported variants: {unsupported}")
    manifest_path = resolve_repo_path(args.manifest)
    run_root = resolve_repo_path(args.run_root)
    rows = load_manifest(manifest_path)
    results: list[dict[str, Any]] = []
    for row in rows:
        rendered = dict(row)
        rendered["variants"] = {}
        for variant in variants:
            rendered["variants"][variant] = run_variant(row, variant, run_root, args.timeout_seconds)
        results.append(rendered)
    summary = summarize(results, variants)
    if args.output_json:
        output_json = resolve_repo_path(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.output_summary:
        output_summary = resolve_repo_path(args.output_summary)
        output_summary.parent.mkdir(parents=True, exist_ok=True)
        output_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

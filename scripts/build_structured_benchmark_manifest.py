#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from benchmark_manifest_utils import dump_jsonl_rows, load_benchmark_manifest_csv, resolve_repo_path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO_ROOT / "benchmark" / "manifest.csv"
DEFAULT_OUTPUT = REPO_ROOT / "benchmark" / "manifests" / "structured_unstructured_benchmark_manifest.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a benchmark manifest from benchmark/manifest.csv for structured/unstructured experiments."
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = load_benchmark_manifest_csv(resolve_repo_path(args.csv))
    export_rows = [
        {
            "doc_id": row["doc_id"],
            "input_pdf": row["filename"],
            "benchmark_group": row["benchmark_group"],
            "language": row["language"],
            "digital_type": row["digital_type"],
            "contains_tables": row["contains_tables"],
            "contains_formulas": row["contains_formulas"],
            "contains_figures": row["contains_figures"],
            "notes": row["notes"],
        }
        for row in rows
    ]
    output_path = resolve_repo_path(args.output)
    dump_jsonl_rows(output_path, export_rows)
    summary = {
        "csv_path": str(resolve_repo_path(args.csv).relative_to(REPO_ROOT)),
        "output_path": str(output_path.relative_to(REPO_ROOT)),
        "total_rows": len(export_rows),
        "structured_rows": sum(1 for row in export_rows if row["benchmark_group"] == "structured"),
        "unstructured_rows": sum(1 for row in export_rows if row["benchmark_group"] == "unstructured"),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

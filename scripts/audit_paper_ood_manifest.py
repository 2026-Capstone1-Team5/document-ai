#!/usr/bin/env python3

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIRED_FIELDS = {
    "doc_id",
    "input_pdf",
    "subgroup",
    "gold_path",
    "gold_format",
    "metric_family",
    "annotation_source",
    "canonicalization_version",
}
SUPPORTED_GOLD_FORMATS = {"fields_json", "transcript_txt", "transcript_json"}
SUPPORTED_METRIC_FAMILIES = {"exact_match", "token_f1", "cer", "wer", "ned"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit a paper OOD manifest for schema completeness and curation readiness."
    )
    parser.add_argument("manifest", type=Path, help="Path to a JSONL manifest")
    parser.add_argument(
        "--require-stripped",
        action="store_true",
        help="Require every row to provide an existing stripped_pdf path",
    )
    parser.add_argument(
        "--min-total",
        type=int,
        default=0,
        help="Fail if the manifest has fewer than this many rows",
    )
    parser.add_argument(
        "--min-subgroup",
        action="append",
        default=[],
        metavar="SUBGROUP=COUNT",
        help="Fail if a subgroup has fewer than COUNT rows; repeatable",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path to write the audit summary JSON",
    )
    return parser.parse_args()


def resolve_repo_path(raw_path: str | Path) -> Path:
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def load_rows(manifest_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"Manifest row {line_number} must be a JSON object")
        row["_line_number"] = line_number
        rows.append(row)
    return rows


def parse_thresholds(raw_thresholds: list[str]) -> dict[str, int]:
    thresholds: dict[str, int] = {}
    for raw in raw_thresholds:
        subgroup, sep, count = raw.partition("=")
        if not sep or not subgroup.strip() or not count.strip():
            raise ValueError(f"Invalid --min-subgroup value: {raw}")
        thresholds[subgroup.strip()] = int(count)
    return thresholds


def audit_rows(
    rows: list[dict[str, Any]], *, require_stripped: bool, min_total: int, min_subgroup: dict[str, int]
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    subgroup_counts: Counter[str] = Counter()
    source_bucket_counts: Counter[str] = Counter()
    metric_family_counts: Counter[str] = Counter()
    gold_format_counts: Counter[str] = Counter()
    duplicate_doc_ids: Counter[str] = Counter()
    seen_doc_ids: set[str] = set()

    for row in rows:
        line_number = row["_line_number"]
        doc_id = str(row.get("doc_id") or "")
        missing = sorted(field for field in REQUIRED_FIELDS if not row.get(field))
        if missing:
            errors.append(
                f"row {line_number}: missing required fields: {', '.join(missing)}"
            )
            continue
        if doc_id in seen_doc_ids:
            duplicate_doc_ids[doc_id] += 1
        seen_doc_ids.add(doc_id)
        subgroup = str(row["subgroup"])
        subgroup_counts[subgroup] += 1
        source_bucket = str(row.get("source_bucket") or "unknown")
        source_bucket_counts[source_bucket] += 1
        metric_family = str(row["metric_family"])
        gold_format = str(row["gold_format"])
        metric_family_counts[metric_family] += 1
        gold_format_counts[gold_format] += 1

        if metric_family not in SUPPORTED_METRIC_FAMILIES:
            errors.append(
                f"row {line_number} doc_id={doc_id}: unsupported metric_family={metric_family}"
            )
        if gold_format not in SUPPORTED_GOLD_FORMATS:
            errors.append(
                f"row {line_number} doc_id={doc_id}: unsupported gold_format={gold_format}"
            )

        input_pdf = resolve_repo_path(row["input_pdf"])
        if not input_pdf.exists():
            errors.append(
                f"row {line_number} doc_id={doc_id}: missing input_pdf={input_pdf}"
            )
        gold_path = resolve_repo_path(row["gold_path"])
        if not gold_path.exists():
            errors.append(
                f"row {line_number} doc_id={doc_id}: missing gold_path={gold_path}"
            )

        stripped_raw = row.get("stripped_pdf")
        if require_stripped and not stripped_raw:
            errors.append(
                f"row {line_number} doc_id={doc_id}: missing stripped_pdf while --require-stripped is set"
            )
        if stripped_raw:
            stripped_path = resolve_repo_path(stripped_raw)
            if not stripped_path.exists():
                errors.append(
                    f"row {line_number} doc_id={doc_id}: missing stripped_pdf={stripped_path}"
                )

        if not row.get("source_bucket"):
            warnings.append(f"row {line_number} doc_id={doc_id}: source_bucket missing")
        if not row.get("freeze_revision"):
            warnings.append(f"row {line_number} doc_id={doc_id}: freeze_revision missing")
        if not row.get("inclusion_reason"):
            warnings.append(f"row {line_number} doc_id={doc_id}: inclusion_reason missing")

    for doc_id, count in sorted(duplicate_doc_ids.items()):
        errors.append(f"duplicate doc_id={doc_id} seen {count + 1} times")

    total_rows = len(rows)
    if total_rows < min_total:
        errors.append(f"manifest has {total_rows} rows, below required minimum {min_total}")
    for subgroup, minimum in sorted(min_subgroup.items()):
        actual = subgroup_counts.get(subgroup, 0)
        if actual < minimum:
            errors.append(
                f"subgroup {subgroup} has {actual} rows, below required minimum {minimum}"
            )

    return {
        "total_rows": total_rows,
        "subgroup_counts": dict(sorted(subgroup_counts.items())),
        "source_bucket_counts": dict(sorted(source_bucket_counts.items())),
        "metric_family_counts": dict(sorted(metric_family_counts.items())),
        "gold_format_counts": dict(sorted(gold_format_counts.items())),
        "errors": errors,
        "warnings": warnings,
        "passed": not errors,
    }


def main() -> int:
    args = parse_args()
    thresholds = parse_thresholds(args.min_subgroup)
    rows = load_rows(args.manifest)
    report = audit_rows(
        rows,
        require_stripped=args.require_stripped,
        min_total=args.min_total,
        min_subgroup=thresholds,
    )
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

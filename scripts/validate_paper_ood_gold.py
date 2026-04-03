#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
SUPPORTED_GOLD_FORMATS = {"fields_json", "transcript_txt", "transcript_json"}
TRANSCRIPT_JSON_KEYS = ("text", "transcript", "content")


def resolve_repo_path(raw_path: str | Path) -> Path:
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate paper OOD gold artifacts for a manifest or a single file."
    )
    parser.add_argument("manifest", nargs="?", type=Path, help="Optional JSONL manifest to validate")
    parser.add_argument("--gold-path", type=Path, help="Validate a single gold file")
    parser.add_argument("--gold-format", choices=sorted(SUPPORTED_GOLD_FORMATS), help="Gold format for --gold-path")
    parser.add_argument("--json-output", type=Path, help="Optional path to write the validation report")
    return parser.parse_args()


def load_manifest_rows(manifest_path: Path) -> list[dict[str, Any]]:
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


def validate_fields_json(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid JSON: {exc}"]
    if not isinstance(payload, dict):
        return ["fields_json must be a JSON object"]
    if not payload:
        return ["fields_json must not be empty"]
    for key, value in payload.items():
        if not isinstance(key, str) or not key.strip():
            errors.append("fields_json keys must be non-empty strings")
            break
        if isinstance(value, (dict, list)):
            errors.append(f"field '{key}' must be a scalar or flat string value")
            break
    return errors


def validate_transcript_txt(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return ["transcript_txt must contain non-whitespace text"]
    return []


def validate_transcript_json(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid JSON: {exc}"]
    if isinstance(payload, str):
        if not payload.strip():
            return ["transcript_json string payload must not be empty"]
        return []
    if not isinstance(payload, dict):
        return ["transcript_json must be a JSON object or string"]
    for key in TRANSCRIPT_JSON_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return []
    return [
        "transcript_json must contain a non-empty text field under one of: "
        + ", ".join(TRANSCRIPT_JSON_KEYS)
    ]


def validate_gold_file(path: Path, gold_format: str) -> list[str]:
    if gold_format not in SUPPORTED_GOLD_FORMATS:
        return [f"unsupported gold_format={gold_format}"]
    if not path.exists():
        return [f"missing gold file: {path}"]
    if gold_format == "fields_json":
        return validate_fields_json(path)
    if gold_format == "transcript_txt":
        return validate_transcript_txt(path)
    return validate_transcript_json(path)


def build_report_for_manifest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    passed = True
    for row in rows:
        doc_id = str(row.get("doc_id") or f"line-{row['_line_number']}")
        gold_format = str(row.get("gold_format") or "")
        gold_path_raw = row.get("gold_path")
        if not gold_path_raw:
            errors = ["missing gold_path"]
            gold_path = None
        else:
            gold_path = resolve_repo_path(gold_path_raw)
            errors = validate_gold_file(gold_path, gold_format)
        item = {
            "doc_id": doc_id,
            "gold_format": gold_format,
            "gold_path": str(gold_path) if gold_path else None,
            "passed": not errors,
            "errors": errors,
        }
        items.append(item)
        if errors:
            passed = False
    return {
        "mode": "manifest",
        "checked": len(items),
        "passed": passed,
        "items": items,
    }


def build_report_for_single(path: Path, gold_format: str) -> dict[str, Any]:
    resolved = resolve_repo_path(path)
    errors = validate_gold_file(resolved, gold_format)
    return {
        "mode": "single",
        "checked": 1,
        "passed": not errors,
        "items": [
            {
                "doc_id": None,
                "gold_format": gold_format,
                "gold_path": str(resolved),
                "passed": not errors,
                "errors": errors,
            }
        ],
    }


def main() -> int:
    args = parse_args()
    if bool(args.manifest) == bool(args.gold_path):
        raise SystemExit("Provide exactly one of: manifest path OR --gold-path with --gold-format")
    if args.gold_path and not args.gold_format:
        raise SystemExit("--gold-format is required with --gold-path")

    if args.manifest:
        report = build_report_for_manifest(load_manifest_rows(args.manifest))
    else:
        report = build_report_for_single(args.gold_path, args.gold_format)

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

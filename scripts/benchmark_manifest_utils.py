#!/usr/bin/env python3

import csv
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_GROUPS = {"structured", "unstructured"}
BOOLEAN_COLUMNS = ("contains_tables", "contains_formulas", "contains_figures")


def resolve_repo_path(raw_path: str | Path) -> Path:
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def _parse_yes_no(raw: str) -> bool:
    normalized = (raw or "").strip().lower()
    if normalized not in {"yes", "no"}:
        raise ValueError(f"Expected yes/no value, got: {raw!r}")
    return normalized == "yes"


def benchmark_group_for_digital_type(digital_type: str) -> str:
    normalized = (digital_type or "").strip().lower()
    if normalized == "digital":
        return "structured"
    if normalized == "scanned":
        return "unstructured"
    raise ValueError(f"Unsupported digital_type: {digital_type!r}")


def load_benchmark_manifest_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "filename",
            "language",
            "digital_type",
            "contains_tables",
            "contains_formulas",
            "contains_figures",
            "notes",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required CSV columns: {sorted(missing)}")
        for index, row in enumerate(reader, start=2):
            filename = (row.get("filename") or "").strip()
            if not filename:
                raise ValueError(f"Row {index} missing filename")
            input_pdf = resolve_repo_path(filename)
            if not input_pdf.exists():
                raise ValueError(f"Row {index} references missing PDF: {filename}")
            digital_type = (row.get("digital_type") or "").strip().lower()
            benchmark_group = benchmark_group_for_digital_type(digital_type)
            normalized: dict[str, Any] = {
                "doc_id": input_pdf.stem,
                "input_pdf": str(input_pdf),
                "filename": filename,
                "language": (row.get("language") or "").strip(),
                "digital_type": digital_type,
                "benchmark_group": benchmark_group,
                "notes": (row.get("notes") or "").strip(),
            }
            for column in BOOLEAN_COLUMNS:
                normalized[column] = _parse_yes_no(row.get(column) or "")
            rows.append(normalized)
    return rows


def dump_jsonl_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(__import__("json").dumps(row, ensure_ascii=False) + "\n")

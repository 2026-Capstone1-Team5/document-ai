#!/usr/bin/env python3

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_SCRIPT = REPO_ROOT / "scripts" / "bootstrap_paper_ood_from_hf.py"
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_paper_ood_manifest.py"
VALIDATE_GOLD_SCRIPT = REPO_ROOT / "scripts" / "validate_paper_ood_gold.py"
DEFAULT_PLAN = REPO_ROOT / "benchmark" / "manifests" / "paper_ood_batch1_import_plan.json"
DEFAULT_MAIN_MANIFEST = REPO_ROOT / "benchmark" / "manifests" / "paper_ood_main_manifest.jsonl"
DEFAULT_CONTROL_MANIFEST = REPO_ROOT / "benchmark" / "manifests" / "paper_structured_control_manifest.jsonl"
DEFAULT_TRACKER = REPO_ROOT / "benchmark" / "manifests" / "paper_ood_collection_tracker.csv"
DEFAULT_REPORT = REPO_ROOT / "benchmark" / "paper_ood" / "reports" / "paper_ood_batch_materialization_report.json"
GENERATED_ROW_DIR = REPO_ROOT / "benchmark" / "manifests" / "generated"
TRACKER_FIELDS = [
    "doc_id",
    "role",
    "subgroup",
    "source_bucket",
    "input_pdf_frozen",
    "gold_created",
    "manifest_row_written",
    "audit_passed",
    "notes",
]


def resolve_repo_path(raw_path: str | Path) -> Path:
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize a curated paper OOD batch from an import plan, writing ready manifests and tracker status."
    )
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--main-manifest-output", type=Path, default=DEFAULT_MAIN_MANIFEST)
    parser.add_argument("--control-manifest-output", type=Path, default=DEFAULT_CONTROL_MANIFEST)
    parser.add_argument("--tracker-output", type=Path, default=DEFAULT_TRACKER)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def load_plan(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Import plan must be a JSON array")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Import plan item {index} must be a JSON object")
        rows.append(item)
    return rows


def generated_row_path(doc_id: str) -> Path:
    return GENERATED_ROW_DIR / f"{doc_id}.jsonl"


def run_bootstrap(item: dict[str, Any]) -> dict[str, Any]:
    doc_id = str(item["doc_id"])
    manifest_output = generated_row_path(doc_id)
    command = [
        sys.executable,
        str(BOOTSTRAP_SCRIPT),
        "--dataset",
        str(item["dataset"]),
        "--dataset-revision",
        str(item["dataset_revision"]),
        "--split",
        str(item["split"]),
        "--index",
        str(item["index"]),
        "--doc-id",
        doc_id,
        "--subgroup",
        str(item["subgroup"]),
        "--source-shortname",
        str(item["source_shortname"]),
        "--gold-format",
        str(item["gold_format"]),
        "--metric-family",
        str(item["metric_family"]),
        "--annotation-source",
        str(item["annotation_source"]),
        "--language",
        str(item["language"]),
        "--source-bucket",
        str(item["source_bucket"]),
        "--suspected-issue",
        str(item["suspected_issue"]),
        "--inclusion-reason",
        str(item["inclusion_reason"]),
        "--freeze-revision",
        str(item["freeze_revision"]),
        "--manifest-row-output",
        str(manifest_output),
    ]
    if item.get("skip_gold_bootstrap"):
        command.append("--skip-gold-bootstrap")
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_json_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def validate_manifest(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    subgroup_counts = Counter(str(row["subgroup"]) for row in rows)
    command = [
        sys.executable,
        str(VALIDATE_GOLD_SCRIPT),
        str(path),
    ]
    gold_report = run_json_command(command)
    command = [
        sys.executable,
        str(AUDIT_SCRIPT),
        str(path),
        "--min-total",
        str(len(rows)),
    ]
    for subgroup, count in sorted(subgroup_counts.items()):
        command.extend(["--min-subgroup", f"{subgroup}={count}"])
    audit_report = run_json_command(command)
    return {
        "gold_validation": gold_report,
        "manifest_audit": audit_report,
        "passed": bool(gold_report["passed"]) and bool(audit_report["passed"]),
    }


def build_tracker_row(
    item: dict[str, Any],
    *,
    imported: bool,
    gold_created: bool,
    manifest_written: bool,
    audit_passed: bool,
    notes: str,
) -> dict[str, str]:
    return {
        "doc_id": str(item["doc_id"]),
        "role": str(item["role"]),
        "subgroup": str(item["subgroup"]),
        "source_bucket": str(item["source_bucket"]),
        "input_pdf_frozen": "yes" if imported else "no",
        "gold_created": "yes" if gold_created else "no",
        "manifest_row_written": "yes" if manifest_written else "no",
        "audit_passed": "yes" if audit_passed else "no",
        "notes": notes,
    }


def write_tracker(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRACKER_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    plan = load_plan(resolve_repo_path(args.plan))

    main_ready_rows: list[dict[str, Any]] = []
    control_ready_rows: list[dict[str, Any]] = []
    tracker_rows: list[dict[str, str]] = []
    import_results: list[dict[str, Any]] = []

    for item in plan:
        strategy = str(item["strategy"])
        doc_id = str(item["doc_id"])
        role = str(item["role"])
        if strategy == "bootstrap_hf":
            payload = run_bootstrap(item)
            manifest_row = payload["manifest_row"]
            gold_path = resolve_repo_path(payload["gold_path"])
            gold_created = gold_path.exists()
            if gold_created:
                if role == "main":
                    main_ready_rows.append(manifest_row)
                elif role == "control":
                    control_ready_rows.append(manifest_row)
                else:
                    raise ValueError(f"Unsupported role={role} for doc_id={doc_id}")
            tracker_rows.append(
                build_tracker_row(
                    item,
                    imported=True,
                    gold_created=gold_created,
                    manifest_written=gold_created,
                    audit_passed=False,
                    notes="imported_from_hf",
                )
            )
            import_results.append(
                {
                    "doc_id": doc_id,
                    "strategy": strategy,
                    "role": role,
                    "imported": True,
                    "gold_created": gold_created,
                    "generated_manifest_row": str(generated_row_path(doc_id).relative_to(REPO_ROOT)),
                }
            )
            continue
        if strategy == "manual_pending":
            tracker_rows.append(
                build_tracker_row(
                    item,
                    imported=False,
                    gold_created=False,
                    manifest_written=False,
                    audit_passed=False,
                    notes=str(item.get("notes") or "manual_step_pending"),
                )
            )
            import_results.append(
                {
                    "doc_id": doc_id,
                    "strategy": strategy,
                    "role": role,
                    "imported": False,
                    "gold_created": False,
                }
            )
            continue
        raise ValueError(f"Unsupported strategy={strategy} for doc_id={doc_id}")

    main_manifest_path = resolve_repo_path(args.main_manifest_output)
    control_manifest_path = resolve_repo_path(args.control_manifest_output)
    append_jsonl(main_manifest_path, main_ready_rows)
    append_jsonl(control_manifest_path, control_ready_rows)

    main_validation = validate_manifest(main_manifest_path, main_ready_rows)
    control_validation = validate_manifest(control_manifest_path, control_ready_rows)

    audit_status_by_doc_id: dict[str, bool] = {}
    for rows, validation in (
        (main_ready_rows, main_validation),
        (control_ready_rows, control_validation),
    ):
        passed = bool(validation and validation["passed"])
        for row in rows:
            audit_status_by_doc_id[str(row["doc_id"])] = passed

    for tracker_row in tracker_rows:
        doc_id = tracker_row["doc_id"]
        if doc_id in audit_status_by_doc_id:
            tracker_row["audit_passed"] = "yes" if audit_status_by_doc_id[doc_id] else "no"

    tracker_path = resolve_repo_path(args.tracker_output)
    write_tracker(tracker_path, tracker_rows)

    report = {
        "plan_path": str(resolve_repo_path(args.plan).relative_to(REPO_ROOT)),
        "main_manifest": str(main_manifest_path.relative_to(REPO_ROOT)),
        "control_manifest": str(control_manifest_path.relative_to(REPO_ROOT)),
        "tracker_path": str(tracker_path.relative_to(REPO_ROOT)),
        "main_ready_count": len(main_ready_rows),
        "control_ready_count": len(control_ready_rows),
        "pending_manual_count": sum(1 for item in plan if item["strategy"] == "manual_pending"),
        "main_validation": main_validation,
        "control_validation": control_validation,
        "imports": import_results,
    }
    report_path = resolve_repo_path(args.report_output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    passed = True
    for validation in (main_validation, control_validation):
        if validation is not None and not validation["passed"]:
            passed = False
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import json
from pathlib import Path


def load_summary(path: Path) -> dict:
    return json.loads(path.read_text())


def parse_summary_arg(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise ValueError(
            f"Invalid --summary value {raw!r}; expected <row>=<summary-json-path>"
        )
    row, path_str = raw.split("=", 1)
    row = row.strip()
    if not row:
        raise ValueError(f"Invalid --summary value {raw!r}; row name is empty")
    path = Path(path_str).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Summary JSON not found for row {row!r}: {path}")
    return row, path


def build_row_entry(row: str, summary: dict) -> dict:
    parse_summary = summary.get("parse_summary", {})
    source_parse_results_json = summary.get("source_parse_results_json")
    run_root = (
        str(Path(source_parse_results_json).resolve().parent)
        if source_parse_results_json
        else None
    )
    requested_mode = summary.get("requested_mode", row)
    command_parse = None
    if run_root:
        command_parse = (
            "python scripts/omnidocbench/benchmark_omnidocbench.py "
            f"--mode {requested_mode} "
            f"--run-root {run_root}"
        )
    command_eval = (
        "python scripts/omnidocbench/run_omnidocbench_full_eval.py "
        f"--skip-parse --mode {requested_mode} "
        f"--run-root {run_root} "
        f"--run-label {summary.get('run_label')}"
        if run_root and summary.get("run_label")
        else None
    )
    return {
        "row": row,
        "requested_mode": requested_mode,
        "run_label": summary.get("run_label"),
        "summary_json": str(summary.get("_source_summary_json", "")),
        "source_parse_results_json": source_parse_results_json,
        "official_metric_json": summary.get("official_metric_json"),
        "official_prediction_dir": summary.get("official_prediction_dir"),
        "official_gt_subset_json": summary.get("official_gt_subset_json"),
        "official_config_yaml": summary.get("official_config_yaml"),
        "official_evaluator_ref": summary.get("official_evaluator_ref"),
        "dataset_revision": summary.get("dataset_revision"),
        "dataset_source": summary.get("dataset_source"),
        "command_parse": command_parse,
        "command_eval": command_eval,
        "metrics": summary.get("table_metrics", {}),
        "runtime": {
            "elapsed_seconds_avg_success": parse_summary.get(
                "elapsed_seconds_avg_success"
            ),
            "elapsed_seconds_median_success": parse_summary.get(
                "elapsed_seconds_median_success"
            ),
            "elapsed_seconds_p95_success": parse_summary.get(
                "elapsed_seconds_p95_success"
            ),
            "success_rate": parse_summary.get("success_rate"),
            "attempted_pages": parse_summary.get("attempted_pages"),
            "parse_succeeded_pages": parse_summary.get("parse_succeeded_pages"),
            "parse_failed_pages": parse_summary.get("parse_failed_pages"),
        },
    }


def build_main_table_rows(
    row_summaries: dict[str, dict], shipped_rows: list[str] | None = None
) -> dict:
    shipped = shipped_rows or list(row_summaries.keys())
    return {
        "rows": [build_row_entry(row, row_summaries[row]) for row in shipped],
    }


def build_runtime_summary(
    row_summaries: dict[str, dict], shipped_rows: list[str] | None = None
) -> dict:
    shipped = shipped_rows or list(row_summaries.keys())
    rows = []
    for row in shipped:
        row_entry = build_row_entry(row, row_summaries[row])
        parse_summary = row_summaries[row].get("parse_summary", {})
        rows.append({
            "row": row,
            "requested_mode": row_entry["requested_mode"],
            "command_parse": row_entry["command_parse"],
            "command_eval": row_entry["command_eval"],
            "elapsed_seconds_avg_success": parse_summary.get(
                "elapsed_seconds_avg_success"
            ),
            "elapsed_seconds_median_success": parse_summary.get(
                "elapsed_seconds_median_success"
            ),
            "elapsed_seconds_p95_success": parse_summary.get(
                "elapsed_seconds_p95_success"
            ),
            "success_rate": parse_summary.get("success_rate"),
            "attempted_pages": parse_summary.get("attempted_pages"),
            "parse_succeeded_pages": parse_summary.get("parse_succeeded_pages"),
            "parse_failed_pages": parse_summary.get("parse_failed_pages"),
        })
    return {"rows": rows}


def build_page_adaptive_gate(
    *,
    auto_payload: dict,
    page_adaptive_payload: dict,
    full_page_count: int,
    ratio_threshold: float = 2.5,
    max_hours: float = 24.0,
) -> dict:
    auto_parse = auto_payload.get("parse_summary", {})
    adaptive_parse = page_adaptive_payload.get("parse_summary", {})
    auto_eval = auto_payload.get("eval_accounting", {})
    adaptive_eval = page_adaptive_payload.get("eval_accounting", {})
    auto_median = auto_parse.get("elapsed_seconds_median_success")
    adaptive_median = adaptive_parse.get("elapsed_seconds_median_success")
    auto_attempted = auto_parse.get("attempted_pages", auto_eval.get("attempted_pages"))
    adaptive_attempted = adaptive_parse.get(
        "attempted_pages", adaptive_eval.get("attempted_pages")
    )
    adaptive_failed = adaptive_parse.get(
        "parse_failed_pages", adaptive_eval.get("parse_failed_pages")
    )
    adaptive_succeeded = adaptive_parse.get(
        "parse_succeeded_pages", adaptive_eval.get("parse_succeeded_pages")
    )

    smoke_success = bool(
        adaptive_attempted
        and adaptive_failed == 0
        and adaptive_succeeded == adaptive_attempted
    )
    runtime_ratio = (
        adaptive_median / auto_median
        if auto_median not in (None, 0) and adaptive_median is not None
        else None
    )
    projected_hours = (
        (adaptive_median * full_page_count) / 3600
        if adaptive_median is not None
        else None
    )

    threshold_checks = {
        "smoke_ok": smoke_success,
        "ratio_ok": runtime_ratio is not None and runtime_ratio <= ratio_threshold,
        "hours_ok": projected_hours is not None and projected_hours <= max_hours,
    }
    disposition = "main_row" if all(threshold_checks.values()) else "secondary_ablation"
    return {
        "auto_requested_mode": auto_payload.get("requested_mode"),
        "page_adaptive_requested_mode": page_adaptive_payload.get("requested_mode"),
        "full_page_count": full_page_count,
        "ratio_threshold": ratio_threshold,
        "max_hours": max_hours,
        "auto_median_seconds_per_page": auto_median,
        "page_adaptive_median_seconds_per_page": adaptive_median,
        "runtime_ratio_vs_auto": runtime_ratio,
        "projected_hours": projected_hours,
        "threshold_checks": threshold_checks,
        "disposition": disposition,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build paper-facing OmniDocBench main-table/runtime/gate artifacts from variant summary JSON files."
    )
    parser.add_argument(
        "--summary",
        action="append",
        default=[],
        help="Variant summary mapping in the form <row>=<summary-json-path>. Repeatable.",
    )
    parser.add_argument(
        "--main-rows",
        default=None,
        help="Comma-separated main table row order. Defaults to the order of --summary inputs.",
    )
    parser.add_argument(
        "--output-main-table",
        "--main-table-output",
        required=True,
        dest="output_main_table",
        help="Output path for paper_variant_main_table_rows.json",
    )
    parser.add_argument(
        "--output-runtime-summary",
        "--runtime-output",
        required=True,
        dest="output_runtime_summary",
        help="Output path for paper_variant_runtime_summary.json",
    )
    parser.add_argument(
        "--auto-smoke-summary",
        default=None,
        help="Optional summary JSON path for auto smoke gate input.",
    )
    parser.add_argument(
        "--page-adaptive-smoke-summary",
        default=None,
        help="Optional summary JSON path for page_adaptive smoke gate input.",
    )
    parser.add_argument(
        "--full-page-count",
        type=int,
        default=None,
        help="Full benchmark page count used for page_adaptive runtime projection.",
    )
    parser.add_argument(
        "--output-page-adaptive-gate",
        "--page-adaptive-gate-output",
        default=None,
        dest="output_page_adaptive_gate",
        help="Optional output path for paper_variant_page_adaptive_gate.json.",
    )
    parser.add_argument(
        "--page-adaptive-ablation-output",
        default=None,
        help="Optional output path for paper_variant_page_adaptive_ablation.json.",
    )
    parser.add_argument(
        "--runtime-multiplier-threshold",
        type=float,
        default=2.5,
    )
    parser.add_argument(
        "--max-projected-hours",
        type=float,
        default=24.0,
    )
    args = parser.parse_args()

    row_summaries: dict[str, dict] = {}
    ordered_rows: list[str] = []
    for raw in args.summary:
        row, path = parse_summary_arg(raw)
        payload = load_summary(path)
        payload["_source_summary_json"] = str(path)
        row_summaries[row] = payload
        ordered_rows.append(row)

    if not row_summaries:
        raise ValueError("At least one --summary row=<path> input is required")

    shipped_rows = (
        [row.strip() for row in args.main_rows.split(",") if row.strip()]
        if args.main_rows
        else ordered_rows
    )
    missing = [row for row in shipped_rows if row not in row_summaries]
    if missing:
        raise ValueError(f"Missing --summary inputs for rows: {missing}")

    gate = None
    if args.output_page_adaptive_gate:
        auto_payload = (
            load_summary(Path(args.auto_smoke_summary).resolve())
            if args.auto_smoke_summary
            else row_summaries.get("auto")
        )
        page_adaptive_payload = (
            load_summary(Path(args.page_adaptive_smoke_summary).resolve())
            if args.page_adaptive_smoke_summary
            else row_summaries.get("page_adaptive")
        )
        if not (auto_payload and page_adaptive_payload and args.full_page_count is not None):
            raise ValueError(
                "--page-adaptive-gate-output requires auto/page_adaptive summaries and --full-page-count"
            )
        gate = build_page_adaptive_gate(
            auto_payload=auto_payload,
            page_adaptive_payload=page_adaptive_payload,
            full_page_count=args.full_page_count,
            ratio_threshold=args.runtime_multiplier_threshold,
            max_hours=args.max_projected_hours,
        )
        write_json(Path(args.output_page_adaptive_gate).resolve(), gate)

    final_rows = list(shipped_rows)
    if gate and gate["disposition"] != "main_row" and "page_adaptive" in final_rows:
        final_rows = [row for row in final_rows if row != "page_adaptive"]
        if args.page_adaptive_ablation_output:
            write_json(
                Path(args.page_adaptive_ablation_output).resolve(),
                build_row_entry("page_adaptive", row_summaries["page_adaptive"]),
            )

    main_table = build_main_table_rows(row_summaries=row_summaries, shipped_rows=final_rows)
    runtime_summary = build_runtime_summary(
        row_summaries=row_summaries, shipped_rows=ordered_rows
    )
    write_json(Path(args.output_main_table).resolve(), main_table)
    write_json(Path(args.output_runtime_summary).resolve(), runtime_summary)


if __name__ == "__main__":
    main()

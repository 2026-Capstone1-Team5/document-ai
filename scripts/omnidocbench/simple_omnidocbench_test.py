import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def format_metric(value: float | None, digits: int) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def run_cmd(cmd: list[str]) -> None:
    print(f"[run] {' '.join(cmd)}")
    completed = subprocess.run(cmd, text=True)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simple OmniDocBench test: parse -> official eval -> print key metrics."
    )
    parser.add_argument(
        "--limit", type=int, default=20, help="Number of samples to test"
    )
    parser.add_argument(
        "--offset", type=int, default=0, help="Start index in the pinned manifest row set"
    )
    parser.add_argument(
        "--name",
        default="simple_run",
        help="Run name used for output folder and report file names",
    )
    parser.add_argument(
        "--official-repo",
        default=os.environ.get(
            "OMNIDOCBENCH_OFFICIAL_REPO", "benchmark_assets/OmniDocBench-official"
        ),
        help="Path to official OmniDocBench eval repo",
    )
    args = parser.parse_args()

    repo_root = repo_root_from_script()
    run_root = repo_root / "output" / f"omnidocbench_{args.name}"
    report_dir = repo_root / "output" / "benchmark_reports"
    summary_md = report_dir / f"omnidocbench_{args.name}_summary.md"
    temp_json = Path(tempfile.gettempdir()) / f"omnidocbench_{args.name}_summary.json"

    # Step 1) Parse samples with our pipeline
    run_cmd(
        [
            sys.executable,
            str(repo_root / "scripts" / "omnidocbench" / "benchmark_omnidocbench.py"),
            "--offset",
            str(args.offset),
            "--limit",
            str(args.limit),
            "--language",
            "en",
            "--run-root",
            str(run_root),
            "--report-dir",
            str(report_dir),
        ]
    )

    # Step 2) Run official OmniDocBench end-to-end evaluation on parsed results
    run_cmd(
        [
            sys.executable,
            str(
                repo_root / "scripts" / "omnidocbench" / "run_omnidocbench_full_eval.py"
            ),
            "--skip-parse",
            "--run-root",
            str(run_root),
            "--official-repo",
            str(Path(args.official_repo).resolve()),
            "--run-label",
            args.name,
            "--output-json",
            str(temp_json),
            "--output-md",
            str(summary_md),
        ]
    )

    # Step 3) Print only key metrics
    payload = json.loads(temp_json.read_text())
    metrics = payload["table_metrics"]
    print("\n=== Simple OmniDocBench Result ===")
    print(f"run_name: {args.name}")
    print(f"text_edit: {format_metric(metrics['text_edit_dist'], 6)}")
    print(f"formula_cdm: {format_metric(metrics['formula_cdm_pct'], 2)}")
    print(f"table_teds: {format_metric(metrics['table_teds_pct'], 2)}")
    print(f"read_order_edit: {format_metric(metrics['reading_order_edit_dist'], 6)}")
    print(f"overall: {format_metric(metrics['overall_pct'], 2)}")
    print(f"summary_md: {summary_md}")
    if temp_json.exists():
        temp_json.unlink()


if __name__ == "__main__":
    main()

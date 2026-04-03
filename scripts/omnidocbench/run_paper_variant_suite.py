import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_variants(raw: str) -> list[str]:
    variants = [item.strip() for item in raw.split(",") if item.strip()]
    valid = {"normal", "rasterized", "auto", "page_adaptive"}
    invalid = [item for item in variants if item not in valid]
    if invalid:
        raise ValueError(f"Invalid variants: {invalid}. valid={sorted(valid)}")
    if not variants:
        raise ValueError("At least one variant is required")
    return variants


def run_cmd(cmd: list[str]) -> None:
    print(f"[run] {' '.join(cmd)}")
    completed = subprocess.run(cmd, text=True)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def build_variant_paths(
    repo_root: Path, report_dir: Path, run_prefix: str, mode: str
) -> dict:
    run_name = f"{run_prefix}_{mode}"
    return {
        "mode": mode,
        "run_name": run_name,
        "run_root": repo_root / "output" / run_name,
        "summary_json": report_dir / f"{run_name}_summary.json",
        "summary_md": report_dir / f"{run_name}_summary.md",
    }


def run_variant(
    *,
    repo_root: Path,
    report_dir: Path,
    official_repo: Path,
    mode: str,
    run_prefix: str,
    indices_file: str | None,
    offset: int,
    limit: int,
    language: str,
    timeout_seconds: int,
    modules: str,
    skip_parse: bool,
) -> dict:
    paths = build_variant_paths(repo_root, report_dir, run_prefix, mode)

    if not skip_parse:
        benchmark_cmd = [
            sys.executable,
            str(repo_root / "scripts" / "omnidocbench" / "benchmark_omnidocbench.py"),
            "--mode",
            mode,
            "--language",
            language,
            "--timeout-seconds",
            str(timeout_seconds),
            "--run-root",
            str(paths["run_root"]),
            "--report-dir",
            str(report_dir),
        ]
        if indices_file:
            benchmark_cmd.extend(["--indices-file", indices_file])
        else:
            benchmark_cmd.extend(["--offset", str(offset), "--limit", str(limit)])
        run_cmd(benchmark_cmd)

    eval_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "omnidocbench" / "run_omnidocbench_full_eval.py"),
        "--mode",
        mode,
        "--run-root",
        str(paths["run_root"]),
        "--official-repo",
        str(official_repo.resolve()),
        "--run-label",
        paths["run_name"],
        "--output-json",
        str(paths["summary_json"]),
        "--output-md",
        str(paths["summary_md"]),
        "--modules",
        modules,
    ]
    if skip_parse:
        eval_cmd.insert(2, "--skip-parse")
    else:
        eval_cmd.extend(
            [
                "--language",
                language,
                "--timeout-seconds",
                str(timeout_seconds),
            ]
        )
        if not indices_file:
            eval_cmd.extend(["--offset", str(offset), "--limit", str(limit)])
    run_cmd(eval_cmd)

    return {
        "mode": mode,
        "run_name": paths["run_name"],
        "run_root": str(paths["run_root"]),
        "summary_json": str(paths["summary_json"]),
        "summary_md": str(paths["summary_md"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the paper benchmark variants sequentially and write a manifest of per-row summary artifacts."
    )
    parser.add_argument("--run-prefix", required=True)
    parser.add_argument(
        "--variants",
        default="normal,rasterized,auto,page_adaptive",
        help="Comma-separated variant list.",
    )
    parser.add_argument("--indices-file", default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=1355)
    parser.add_argument("--language", default="en")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--official-repo",
        default=os.environ.get(
            "OMNIDOCBENCH_OFFICIAL_REPO", "benchmark_assets/OmniDocBench-official"
        ),
    )
    parser.add_argument(
        "--report-dir",
        default="output/benchmark_reports",
    )
    parser.add_argument(
        "--modules",
        default="text,formula,table,reading_order",
    )
    parser.add_argument("--skip-parse", action="store_true")
    args = parser.parse_args()

    repo_root = repo_root_from_script()
    report_dir = (repo_root / args.report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    variants = parse_variants(args.variants)

    manifest = {
        "run_prefix": args.run_prefix,
        "variants": [],
    }
    for mode in variants:
        manifest["variants"].append(
            run_variant(
                repo_root=repo_root,
                report_dir=report_dir,
                official_repo=Path(args.official_repo),
                mode=mode,
                run_prefix=args.run_prefix,
                indices_file=args.indices_file,
                offset=args.offset,
                limit=args.limit,
                language=args.language,
                timeout_seconds=args.timeout_seconds,
                modules=args.modules,
                skip_parse=args.skip_parse,
            )
        )

    manifest_path = report_dir / f"{args.run_prefix}_suite_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Saved manifest: {manifest_path}")


if __name__ == "__main__":
    main()

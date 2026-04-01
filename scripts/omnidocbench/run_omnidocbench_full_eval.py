import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import hf_hub_download


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def benchmark_assets_root() -> Path:
    root = repo_root_from_script() / "benchmark_assets"
    root.mkdir(parents=True, exist_ok=True)
    return root


def configure_local_hf_cache() -> None:
    assets = benchmark_assets_root()
    hf_home = assets / "hf_home"
    hub_cache = hf_home / "hub"
    datasets_cache = hf_home / "datasets"
    for p in [hf_home, hub_cache, datasets_cache]:
        p.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(hf_home))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hub_cache))
    os.environ.setdefault("HF_DATASETS_CACHE", str(datasets_cache))


def resolve_official_repo_default() -> str:
    # Cross-platform default; users can override via CLI or env var.
    return os.environ.get(
        "OMNIDOCBENCH_OFFICIAL_REPO",
        str(benchmark_assets_root() / "OmniDocBench-official"),
    )


def run_cmd(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print(f"[cmd] {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=cwd, env=env, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(cmd)}")


def ensure_official_repo(official_repo: Path) -> None:
    marker = official_repo / "pdf_validation.py"
    if marker.exists():
        return
    if official_repo.exists() and any(official_repo.iterdir()):
        raise FileNotFoundError(
            f"{official_repo} exists but is not a valid OmniDocBench evaluator checkout"
        )
    official_repo.parent.mkdir(parents=True, exist_ok=True)
    run_cmd(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "https://github.com/opendatalab/OmniDocBench",
            str(official_repo),
        ]
    )
    if not marker.exists():
        raise FileNotFoundError(f"Failed to prepare official evaluator at {official_repo}")


def ensure_parse_results(
    scripts_dir: Path,
    split: str,
    offset: int,
    limit: int,
    language: str,
    timeout_seconds: int,
    run_root: Path,
    report_dir: Path,
    skip_parse: bool,
) -> Path:
    results_path = run_root / "results.json"
    if skip_parse:
        if not results_path.exists():
            raise FileNotFoundError(f"--skip-parse was set, but {results_path} does not exist")
        return results_path

    run_root.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    benchmark_script = scripts_dir / "benchmark_omnidocbench.py"

    cmd = [
        sys.executable,
        str(benchmark_script),
        "--split",
        split,
        "--offset",
        str(offset),
        "--limit",
        str(limit),
        "--language",
        language,
        "--timeout-seconds",
        str(timeout_seconds),
        "--run-root",
        str(run_root),
        "--report-dir",
        str(report_dir),
    ]
    run_cmd(cmd, cwd=scripts_dir.parent)
    if not results_path.exists():
        raise FileNotFoundError(f"Parse finished but no results found: {results_path}")
    return results_path


def build_official_eval_inputs(
    results_path: Path,
    official_repo: Path,
    run_label: str,
    modules: set[str],
) -> tuple[Path, Path, Path]:
    results = json.loads(results_path.read_text())
    pred_dir_name = f"end2end_{run_label}"
    pred_dir = official_repo / "demo_data" / pred_dir_name
    pred_dir.mkdir(parents=True, exist_ok=True)

    pred_basenames: set[str] = set()
    copied = 0
    for row in results.get("results", []):
        if row.get("status") != "succeeded":
            continue
        src = row.get("source_image_ref") or ""
        if "/images/" not in src:
            continue
        base = Path(src).name
        stem = Path(src).stem
        meta_path = Path(row.get("meta_path") or "")
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        md_path = Path(meta.get("outputs", {}).get("markdown", ""))
        if not md_path.exists():
            continue
        shutil.copy2(md_path, pred_dir / f"{stem}.md")
        pred_basenames.add(base)
        copied += 1

    if copied == 0:
        raise RuntimeError("No markdown predictions were copied for official evaluation")

    gt_json_path = Path(
        hf_hub_download(
            repo_id="opendatalab/OmniDocBench",
            repo_type="dataset",
            filename="OmniDocBench.json",
            local_dir=str(benchmark_assets_root() / "omnidocbench_hf"),
        )
    )
    gt_rows = json.loads(gt_json_path.read_text())
    subset = [
        row
        for row in gt_rows
        if Path(row.get("page_info", {}).get("image_path", "")).name in pred_basenames
    ]
    subset_path = official_repo / "demo_data" / f"OmniDocBench_subset_{run_label}.json"
    subset_path.write_text(json.dumps(subset, ensure_ascii=False, indent=2))

    config_path = official_repo / "configs" / f"end2end_{run_label}_cdm.yaml"
    lines = ["end2end_eval:", "  metrics:"]
    if "text" in modules:
        lines.extend(
            [
                "    text_block:",
                "      metric:",
                "        - Edit_dist",
            ]
        )
    if "formula" in modules:
        lines.extend(
            [
                "    display_formula:",
                "      metric:",
                "        - Edit_dist",
                "        - CDM",
            ]
        )
    if "table" in modules:
        lines.extend(
            [
                "    table:",
                "      metric:",
                "        - TEDS",
                "        - Edit_dist",
            ]
        )
    if "reading_order" in modules:
        lines.extend(
            [
                "    reading_order:",
                "      metric:",
                "        - Edit_dist",
            ]
        )
    lines.extend(
        [
            "  dataset:",
            "    dataset_name: end2end_dataset",
            "    ground_truth:",
            f"      data_path: ./demo_data/{subset_path.name}",
            "    prediction:",
            f"      data_path: ./demo_data/{pred_dir_name}",
            "    match_method: quick_match",
            "",
        ]
    )
    config_path.write_text("\n".join(lines))
    return pred_dir, subset_path, config_path


def run_official_eval(official_repo: Path, config_path: Path) -> Path:
    env = os.environ.copy()
    uv_cache = benchmark_assets_root() / "uv_cache"
    uv_cache.mkdir(parents=True, exist_ok=True)
    env.setdefault("UV_CACHE_DIR", str(uv_cache))

    cmd = [
        "uv",
        "run",
        "--python",
        "3.10",
        "--with",
        "scikit-image==0.20.0",
        "--with-requirements",
        str(official_repo / "requirements.txt"),
        "python",
        str(official_repo / "pdf_validation.py"),
        "--config",
        str(config_path),
    ]
    run_cmd(cmd, cwd=official_repo, env=env)

    config = json.loads(json.dumps({}))  # keep linter happy without yaml dep
    # save_name rule in pdf_validation.py:
    # basename(prediction.data_path) + "_" + match_method
    pred_dir_name = None
    match_method = "quick_match"
    for line in config_path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("data_path: ./demo_data/end2end_"):
            pred_dir_name = stripped.split("/")[-1]
        if stripped.startswith("match_method:"):
            match_method = stripped.split(":", 1)[1].strip()
    if not pred_dir_name:
        raise RuntimeError(f"Failed to infer prediction dir from config: {config_path}")

    metric_path = official_repo / "result" / f"{pred_dir_name}_{match_method}_metric_result.json"
    if not metric_path.exists():
        raise FileNotFoundError(f"Official metric result not found: {metric_path}")
    return metric_path


def compute_table_metrics(metric_path: Path) -> dict:
    metric = json.loads(metric_path.read_text())
    text_edit = metric.get("text_block", {}).get("all", {}).get("Edit_dist", {}).get("ALL_page_avg")
    table_teds_raw = metric.get("table", {}).get("all", {}).get("TEDS", {}).get("all")
    formula_cdm_raw = metric.get("display_formula", {}).get("all", {}).get("CDM", {}).get("all")
    reading_order_edit = (
        metric.get("reading_order", {}).get("all", {}).get("Edit_dist", {}).get("ALL_page_avg")
    )

    table_teds_pct = (
        (table_teds_raw * 100 if table_teds_raw <= 1 else table_teds_raw)
        if table_teds_raw is not None
        else None
    )
    formula_cdm_pct = (
        (formula_cdm_raw * 100 if formula_cdm_raw <= 1 else formula_cdm_raw)
        if formula_cdm_raw is not None
        else None
    )
    text_score_pct = ((1 - text_edit) * 100) if text_edit is not None else None
    overall_pct = None
    if text_score_pct is not None and table_teds_pct is not None and formula_cdm_pct is not None:
        overall_pct = (text_score_pct + table_teds_pct + formula_cdm_pct) / 3

    return {
        "text_edit_dist": text_edit,
        "text_score_pct": text_score_pct,
        "table_teds_raw": table_teds_raw,
        "table_teds_pct": table_teds_pct,
        "formula_cdm_raw": formula_cdm_raw,
        "formula_cdm_pct": formula_cdm_pct,
        "reading_order_edit_dist": reading_order_edit,
        "overall_pct": overall_pct,
    }


def write_outputs(
    output_json: Path,
    output_md: Path,
    run_label: str,
    parse_results_path: Path,
    metric_path: Path,
    pred_dir: Path,
    subset_path: Path,
    config_path: Path,
    table_metrics: dict,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "run_label": run_label,
        "created_at_utc": now,
        "source_parse_results_json": str(parse_results_path.resolve()),
        "official_metric_json": str(metric_path.resolve()),
        "official_prediction_dir": str(pred_dir.resolve()),
        "official_gt_subset_json": str(subset_path.resolve()),
        "official_config_yaml": str(config_path.resolve()),
        "table_metrics": table_metrics,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2))

    def fmt_num(v: float | None, digits: int) -> str:
        return "N/A" if v is None else f"{v:.{digits}f}"

    md = "\n".join(
        [
            f"# OmniDocBench End-to-End Summary ({run_label})",
            "",
            "| Text Edit↓ | Formula CDM↑ | Table TEDS↑ | Read Order Edit↓ | Overall↑ |",
            "|---:|---:|---:|---:|---:|",
            (
                f"| {fmt_num(table_metrics['text_edit_dist'], 6)} | "
                f"{fmt_num(table_metrics['formula_cdm_pct'], 2)} | "
                f"{fmt_num(table_metrics['table_teds_pct'], 2)} | "
                f"{fmt_num(table_metrics['reading_order_edit_dist'], 6)} | "
                f"{fmt_num(table_metrics['overall_pct'], 2)} |"
            ),
            "",
            f"- Parse results: `{parse_results_path}`",
            f"- Official metric: `{metric_path}`",
            f"- Prediction dir: `{pred_dir}`",
            f"- GT subset: `{subset_path}`",
            f"- Config: `{config_path}`",
            "",
        ]
    )
    output_md.write_text(md)


def main() -> None:
    configure_local_hf_cache()
    parser = argparse.ArgumentParser(
        description="Run OmniDocBench parse + official end2end(CDM) eval and emit table-ready metrics."
    )
    parser.add_argument("--split", default="train")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=1355)
    parser.add_argument("--language", default="en")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--run-root",
        default="output/omnidocbench_benchmark_full",
        help="Where parse artifacts/results.json are written by benchmark_omnidocbench.py",
    )
    parser.add_argument(
        "--report-dir",
        default="output/benchmark_reports",
        help="Managed report directory used by benchmark_omnidocbench.py",
    )
    parser.add_argument(
        "--official-repo",
        default=resolve_official_repo_default(),
        help="Path to the official OmniDocBench evaluation repository clone",
    )
    parser.add_argument(
        "--run-label",
        default="mineru_full",
        help="Label used in generated official prediction/config file names",
    )
    parser.add_argument(
        "--skip-parse",
        action="store_true",
        help="Skip parsing and reuse existing <run-root>/results.json",
    )
    parser.add_argument(
        "--output-json",
        default="output/benchmark_reports/omnidocbench_full_table_summary.json",
        help="Final JSON with table-ready metrics",
    )
    parser.add_argument(
        "--output-md",
        default="output/benchmark_reports/omnidocbench_full_table_summary.md",
        help="Final markdown table summary",
    )
    parser.add_argument(
        "--modules",
        default="text,formula,table,reading_order",
        help=(
            "Comma-separated modules to evaluate: "
            "text,formula,table,reading_order (e.g. text or text,table)"
        ),
    )
    args = parser.parse_args()

    scripts_dir = Path(__file__).resolve().parent
    run_root = Path(args.run_root).resolve()
    report_dir = Path(args.report_dir).resolve()
    official_repo = Path(args.official_repo).resolve()
    output_json = Path(args.output_json).resolve()
    output_md = Path(args.output_md).resolve()
    modules = {m.strip() for m in args.modules.split(",") if m.strip()}
    valid_modules = {"text", "formula", "table", "reading_order"}
    invalid = modules - valid_modules
    if invalid:
        raise ValueError(f"Invalid modules: {sorted(invalid)}. valid={sorted(valid_modules)}")
    if not modules:
        raise ValueError("No modules selected. Use --modules with at least one module.")

    ensure_official_repo(official_repo)

    parse_results_path = ensure_parse_results(
        scripts_dir=scripts_dir,
        split=args.split,
        offset=args.offset,
        limit=args.limit,
        language=args.language,
        timeout_seconds=args.timeout_seconds,
        run_root=run_root,
        report_dir=report_dir,
        skip_parse=args.skip_parse,
    )

    pred_dir, subset_path, config_path = build_official_eval_inputs(
        results_path=parse_results_path,
        official_repo=official_repo,
        run_label=args.run_label,
        modules=modules,
    )
    metric_path = run_official_eval(official_repo=official_repo, config_path=config_path)
    table_metrics = compute_table_metrics(metric_path=metric_path)

    write_outputs(
        output_json=output_json,
        output_md=output_md,
        run_label=args.run_label,
        parse_results_path=parse_results_path,
        metric_path=metric_path,
        pred_dir=pred_dir,
        subset_path=subset_path,
        config_path=config_path,
        table_metrics=table_metrics,
    )

    print("\n=== OmniDocBench Table Metrics ===")
    print(json.dumps(table_metrics, indent=2))
    print(f"\nSaved summary json: {output_json}")
    print(f"Saved summary md:   {output_md}")


if __name__ == "__main__":
    main()

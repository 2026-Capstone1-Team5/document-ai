# OmniDocBench Benchmark Guide

This directory contains scripts for MinerU parsing benchmark/evaluation on OmniDocBench.

## Scripts

- `benchmark_omnidocbench.py`: parse-only benchmark (creates per-sample outputs + `results.json`)
- `run_omnidocbench_full_eval.py`: parse + official end-to-end evaluation
- `simple_omnidocbench_test.py`: simple wrapper for parse -> official eval -> metric summary

## Prerequisites

1. Ensure external tools are available in `PATH`:
- `xelatex`
- `magick` (ImageMagick)
- `gs` (Ghostscript)

2. Use `uv` for Python execution.

Notes:
- The script auto-prepares the official evaluator on first run.
- Benchmark assets are stored under `benchmark_assets/` (no `/tmp` cache path needed).
- Official evaluation now uses the pinned dataset manifest (`OmniDocBench.json`) as the source of truth for page identity and records provenance in the summary artifacts.
- The default pinned dataset revision is `91fe284bbfacfa687959ae3eb00846ca852aa907` (override with `OMNIDOCBENCH_DATASET_REVISION` only if you intentionally want a different paper run).

## Quick Start (Recommended)

### macOS / Linux

```bash
uv run --with datasets --with pillow --with pymupdf --with huggingface_hub \
python scripts/omnidocbench/simple_omnidocbench_test.py \
  --limit 20 \
  --offset 0 \
  --name smoke20 \
  --official-repo benchmark_assets/OmniDocBench-official
```

### Windows (PowerShell)

```powershell
uv run --with datasets --with pillow --with pymupdf --with huggingface_hub python scripts/omnidocbench/simple_omnidocbench_test.py --limit 20 --offset 0 --name smoke20 --official-repo benchmark_assets/OmniDocBench-official
```

Main output:
- `output/benchmark_reports/omnidocbench_<name>_summary.md`

## Proven repo-local smoke recipe (all major modules covered)

Generate a deterministic metric-coverage smoke plan (one sample per text/formula/table bucket), then run parse + official eval from repo-local paths:

```bash
uv run --with huggingface_hub \
python scripts/omnidocbench/build_sample_indices.py \
  --per-group 1 \
  --output output/benchmark_reports/omnidocbench_metric_coverage_smoke_plan.json

uv run --with datasets --with pillow --with pymupdf --with huggingface_hub \
python scripts/omnidocbench/benchmark_omnidocbench.py \
  --indices-file output/benchmark_reports/omnidocbench_metric_coverage_smoke_plan.json \
  --run-root output/omnidocbench_metric_coverage_smoke \
  --report-dir output/benchmark_reports

uv run --with datasets --with pillow --with pymupdf --with huggingface_hub \
python scripts/omnidocbench/run_omnidocbench_full_eval.py \
  --skip-parse \
  --run-root output/omnidocbench_metric_coverage_smoke \
  --official-repo benchmark_assets/OmniDocBench-official \
  --run-label metric_coverage_smoke \
  --output-json output/benchmark_reports/omnidocbench_metric_coverage_smoke_summary.json \
  --output-md output/benchmark_reports/omnidocbench_metric_coverage_smoke_summary.md
```

This is the recommended smoke gate before any paper-facing full run because it:
- uses official GT-row indices (not imagefolder ordering),
- covers text/formula/table buckets deterministically,
- fails fast if GT subset generation is empty or requested official metrics are `NaN`.

## Full Control: Parse + Official Eval

### First run (do NOT use `--skip-parse`)

```bash
uv run --with datasets --with pillow --with pymupdf --with huggingface_hub \
python scripts/omnidocbench/run_omnidocbench_full_eval.py \
  --split train \
  --offset 0 \
  --limit 1355 \
  --run-root output/omnidocbench_benchmark_full \
  --official-repo benchmark_assets/OmniDocBench-official \
  --run-label mineru_full
```

### Re-evaluation only (use `--skip-parse`)

Use this only when `output/.../results.json` already exists.

```bash
uv run --with datasets --with pillow --with pymupdf --with huggingface_hub \
python scripts/omnidocbench/run_omnidocbench_full_eval.py \
  --skip-parse \
  --run-root output/omnidocbench_benchmark_full \
  --official-repo benchmark_assets/OmniDocBench-official \
  --run-label mineru_rerun
```

## Module-only Evaluation

Use `--modules` to evaluate specific parts only:
- `text`
- `formula`
- `table`
- `reading_order`

Examples:

```bash
# text only
uv run --with datasets --with pillow --with pymupdf --with huggingface_hub \
python scripts/omnidocbench/run_omnidocbench_full_eval.py \
  --skip-parse \
  --run-root output/omnidocbench_benchmark_full \
  --official-repo benchmark_assets/OmniDocBench-official \
  --run-label mineru_text_only \
  --modules text

# text + table
uv run --with datasets --with pillow --with pymupdf --with huggingface_hub \
python scripts/omnidocbench/run_omnidocbench_full_eval.py \
  --skip-parse \
  --run-root output/omnidocbench_benchmark_full \
  --official-repo benchmark_assets/OmniDocBench-official \
  --run-label mineru_text_table \
  --modules text,table
```

If a module is not selected, its metric is shown as `N/A` in summary output.

## Balanced Sampling (Human-selectable)

Build a balanced index plan (e.g., 20 per group), then edit `indices` manually if needed:

```bash
uv run --with datasets --with pillow --with huggingface_hub \
python scripts/omnidocbench/build_sample_indices.py \
  --per-group 20 \
  --output output/benchmark_reports/omnidocbench_sample_plan.json
```

Default grouping is `metric_coverage` (text/formula/table presence buckets).  
Use `--group-by` only if you explicitly want another grouping.

```bash
uv run --with datasets --with pillow --with huggingface_hub \
python scripts/omnidocbench/build_sample_indices.py \
  --per-group 20 \
  --output output/benchmark_reports/omnidocbench_metric_coverage_plan.json
```

Run parse benchmark only on selected indices:

```bash
uv run --with datasets --with pillow --with pymupdf --with huggingface_hub \
python scripts/omnidocbench/benchmark_omnidocbench.py \
  --indices-file output/benchmark_reports/omnidocbench_sample_plan.json \
  --run-root output/omnidocbench_balanced \
  --report-dir output/benchmark_reports
```

Important:
- `indices` now refer to **official `OmniDocBench.json` row indices**, not Hugging Face imagefolder order.
- This keeps sample selection stable and aligned with the official evaluator.

## Outputs

- parse artifacts: `output/omnidocbench_*`
- managed reports: `output/benchmark_reports/`
  - `*_summary.md`
  - `*_summary.json`
  - provenance fields include:
    - official evaluator git ref
    - dataset source
    - dataset revision
    - prediction dir / GT subset / config paths

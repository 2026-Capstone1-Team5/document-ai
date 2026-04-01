# OmniDocBench Benchmark Guide

This directory contains scripts for MinerU parsing benchmark/evaluation on OmniDocBench.

## Scripts

- `benchmark_omnidocbench.py`: parse-only benchmark (creates per-sample outputs + `results.json`)
- `run_omnidocbench_full_eval.py`: parse + official end-to-end evaluation
- `simple_omnidocbench_test.py`: simple wrapper for parse -> official eval -> metric summary

## Prerequisites

1. Clone official evaluator:

```bash
git clone https://github.com/opendatalab/OmniDocBench benchmark/OmniDocBench-official
```

2. Ensure external tools are available in `PATH`:
- `xelatex`
- `magick` (ImageMagick)
- `gs` (Ghostscript)

3. Use `uv` for Python execution.

## Quick Start (Recommended)

### macOS / Linux

```bash
uv run --with datasets --with pillow --with pymupdf --with huggingface_hub \
python scripts/omnidocbench/simple_omnidocbench_test.py \
  --limit 20 \
  --offset 0 \
  --name smoke20 \
  --official-repo benchmark/OmniDocBench-official
```

### Windows (PowerShell)

```powershell
uv run --with datasets --with pillow --with pymupdf --with huggingface_hub python scripts/omnidocbench/simple_omnidocbench_test.py --limit 20 --offset 0 --name smoke20 --official-repo benchmark/OmniDocBench-official
```

Main output:
- `output/benchmark_reports/omnidocbench_<name>_summary.md`

## Full Control: Parse + Official Eval

### First run (do NOT use `--skip-parse`)

```bash
uv run --with datasets --with pillow --with pymupdf --with huggingface_hub \
python scripts/omnidocbench/run_omnidocbench_full_eval.py \
  --split train \
  --offset 0 \
  --limit 1355 \
  --run-root output/omnidocbench_benchmark_full \
  --official-repo benchmark/OmniDocBench-official \
  --run-label mineru_full
```

### Re-evaluation only (use `--skip-parse`)

Use this only when `output/.../results.json` already exists.

```bash
uv run --with datasets --with pillow --with pymupdf --with huggingface_hub \
python scripts/omnidocbench/run_omnidocbench_full_eval.py \
  --skip-parse \
  --run-root output/omnidocbench_benchmark_full \
  --official-repo benchmark/OmniDocBench-official \
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
  --official-repo benchmark/OmniDocBench-official \
  --run-label mineru_text_only \
  --modules text

# text + table
uv run --with datasets --with pillow --with pymupdf --with huggingface_hub \
python scripts/omnidocbench/run_omnidocbench_full_eval.py \
  --skip-parse \
  --run-root output/omnidocbench_benchmark_full \
  --official-repo benchmark/OmniDocBench-official \
  --run-label mineru_text_table \
  --modules text,table
```

If a module is not selected, its metric is shown as `N/A` in summary output.

## Outputs

- parse artifacts: `output/omnidocbench_*`
- managed reports: `output/benchmark_reports/`
  - `*_summary.md`
  - `*_summary.json`

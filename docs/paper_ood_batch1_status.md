# Paper OOD Batch 1 Status

This note records the first **materialized** paper OOD batch in the repo after running:

```bash
uv run --with datasets --with pillow python scripts/materialize_paper_ood_batch.py
```

The batch import plan now pins each Hugging Face source row to a specific upstream
dataset revision so reruns preserve the same `(dataset, split, index)` mapping.

## Current ready counts

- main OOD ready rows: **16**
- structured control ready rows: **2**
- manual pending rows: **4**

## What is already frozen

### Main OOD manifest
- `benchmark/manifests/paper_ood_main_manifest.jsonl`
- subgroup mix:
  - `receipt=10`
  - `invoice=3`
  - `ocr_form=3`

### Structured control manifest
- `benchmark/manifests/paper_structured_control_manifest.jsonl`
- subgroup mix:
  - `structured_form=2`

### Tracker
- `benchmark/manifests/paper_ood_collection_tracker.csv`

### Report
- `benchmark/paper_ood/reports/paper_ood_batch_materialization_report.json`

## Why 4 rows are still pending

The remaining control rows (`control-rvl-0001` through `control-rvl-0004`) are still manual because
the current `datasets` runtime rejects the legacy dataset script used by `aharley/rvl_cdip`.

Observed failure during inspection:

> `RuntimeError: Dataset scripts are no longer supported, but found rvl_cdip.py`

That means the current automated HF importer cannot freeze those rows yet.

## Operational meaning

The repo now has a working, audited first-pass batch for:
- SROIE receipts
- CORD receipts
- invoice OCR rows
- FUNSD main/control rows

## Claim-strength caveat

Batch 1 is useful for **paired quality benchmarking** (`original / rasterized / auto`), but it is not by itself
strong evidence for a direct `txt`-path routing-failure claim.

Why:
- the imported Hugging Face rows are image-backed inputs that were wrapped into repo-local PDFs
- direct `classify()` observation on the current batch reports `ocr`, not `txt`

So Batch 1 currently supports:
- quantitative OOD parsing-quality comparisons
- conservative wording about threshold limitations / distribution mismatch

It does **not yet** support:
- categorical wording that a receipt-like document was directly observed as misrouted to the text path

Use `docs/paper_routing_claim_guardrails.md` together with the routing-observation outputs when writing the paper.

The remaining work is no longer infrastructure-heavy:
1. either manually curate the 4 RVL rows, or choose a replacement control source
2. review bootstrapped gold for the already imported rows
3. scale the same process beyond Batch 1 toward the paper target manifests

## Verification snapshot

At materialization time:
- `paper_ood_main_manifest.jsonl` passed gold validation
- `paper_ood_main_manifest.jsonl` passed manifest audit with:
  - `--min-total 16`
  - `--min-subgroup receipt=10`
  - `--min-subgroup invoice=3`
  - `--min-subgroup ocr_form=3`
- `paper_structured_control_manifest.jsonl` passed gold validation
- `paper_structured_control_manifest.jsonl` passed manifest audit with:
  - `--min-total 2`
  - `--min-subgroup structured_form=2`

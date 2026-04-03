# Paper OOD Curation Workflow

This workflow turns the **HF-first shortlist** into a reproducible paper benchmark.

## 1. Download and freeze candidate source documents

For each selected document:
- save the PDF under `benchmark/paper_ood/raw/`
- record the public source in the manifest via `source_bucket`
- record the frozen upstream revision in `freeze_revision`

Recommended naming:
- `receipt-sroie-0001.pdf`
- `invoice-ocr-0007.pdf`
- `ticket-manual-0003.pdf`
- `control-form-0004.pdf`

## 2. Create gold artifacts before benchmarking

Create one gold artifact per document under `benchmark/paper_ood/gold/`.

Recommended contracts:
- receipt / invoice / form-like docs: `gold_format=fields_json`
- free-text docs: `gold_format=transcript_txt` or `transcript_json`

Keep the contract stable per subgroup so pairwise comparisons remain interpretable.

## 3. Fill the manifests

Use the template JSONL files under `benchmark/manifests/` as the starting point:
- `paper_ood_main_manifest.template.jsonl`
- `paper_structured_control_manifest.template.jsonl`
- `paper_ood_causal_probe_manifest.template.jsonl`

Minimum fields are enforced by the runner, but curation should also fill:
- `source_bucket`
- `freeze_revision`
- `inclusion_reason`
- `suspected_issue`

## 4. Audit manifests before any expensive runs

Audit the main manifest:

```bash
python scripts/audit_paper_ood_manifest.py \
  benchmark/manifests/paper_ood_main_manifest.jsonl \
  --min-total 100 \
  --min-subgroup receipt=50 \
  --min-subgroup invoice=10
```

Audit the structured control manifest:

```bash
python scripts/audit_paper_ood_manifest.py \
  benchmark/manifests/paper_structured_control_manifest.jsonl \
  --min-total 15
```

Audit the causal subset and require stripped PDFs:

```bash
python scripts/audit_paper_ood_manifest.py \
  benchmark/manifests/paper_ood_causal_probe_manifest.jsonl \
  --require-stripped \
  --min-total 20
```

The audit command fails if:
- required fields are missing
- input PDFs or gold artifacts do not exist
- `stripped_pdf` is missing when required
- subgroup minimums are not met

## 5. Generate stripped PDFs for causal rows

For each causal row, generate a stripped version:

```bash
python scripts/text_layer_strip_pdf.py \
  benchmark/paper_ood/raw/receipt-sroie-0001.pdf \
  benchmark/paper_ood/derived/receipt-sroie-0001.stripped.pdf \
  --provenance-json benchmark/paper_ood/derived/receipt-sroie-0001.stripped.provenance.json
```

## 6. Run the paired benchmark

Main OOD:

```bash
python scripts/paper_ood_benchmark.py \
  benchmark/manifests/paper_ood_main_manifest.jsonl \
  --variants original,rasterized,auto
```

Structured control:

```bash
python scripts/paper_ood_benchmark.py \
  benchmark/manifests/paper_structured_control_manifest.jsonl \
  --variants original,rasterized,auto
```

Causal probe:

```bash
python scripts/paper_ood_benchmark.py \
  benchmark/manifests/paper_ood_causal_probe_manifest.jsonl \
  --variants original,rasterized,auto,text_layer_stripped
```

## 7. Score and export paper artifacts

Score each benchmark output with `score_paper_ood_results.py`, then build paper-facing JSON artifacts using `build_paper_ood_artifacts.py`.

The intended narrative is:
- **main set**: `original / rasterized / auto`
- **control set**: non-regression check
- **causal set**: harmful-text-layer intervention evidence

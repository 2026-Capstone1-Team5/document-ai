# Paper OOD HF Import Guide

The paper OOD benchmark uses **image-backed HF datasets** as source material.
Because the benchmark runner expects PDFs, the import flow is:

1. download one HF row
2. freeze the source image locally
3. wrap it into a single-page PDF
4. bootstrap a gold artifact when the source annotation allows it
5. write metadata + optional manifest row

## Supported source datasets

Current import automation supports:
- `jsdnrs/ICDAR2019-SROIE`
- `naver-clova-ix/cord-v2`
- `davidle7/funsd-json`
- `philschmid/ocr-invoice-data`

These are treated as **image-backed sources**, not native PDF sources.

## Example: import one SROIE row

```bash
uv run --with datasets --with pillow python scripts/bootstrap_paper_ood_from_hf.py \
  --dataset jsdnrs/ICDAR2019-SROIE \
  --dataset-revision bffe40c26759f3376ec2b3ae9031dbba54cd587c \
  --split train \
  --index 0 \
  --doc-id receipt-sroie-0001 \
  --subgroup receipt \
  --source-shortname sroie \
  --suspected-issue ocr_noise \
  --inclusion-reason starter_batch_scanned_receipt \
  --manifest-row-output benchmark/manifests/generated/receipt-sroie-0001.jsonl
```

Outputs:
- `benchmark/paper_ood/raw/receipt-sroie-0001.png`
- `benchmark/paper_ood/raw/receipt-sroie-0001.pdf`
- `benchmark/paper_ood/gold/receipt-sroie-0001.json`
- `benchmark/paper_ood/metadata/receipt-sroie-0001.source.json`

The pinned dataset revision is written to:
- `benchmark/paper_ood/metadata/<doc_id>.source.json` as `dataset_revision`
- generated manifest rows as `source_dataset_revision`

## Bootstrap behavior by dataset

### SROIE
- image → PDF wrapper
- gold bootstrap source: `entities`
- recommended subgroup: `receipt`

### CORD v2
- image → PDF wrapper
- gold bootstrap source: parsed `ground_truth` JSON
- recommended subgroup: `receipt`

### FUNSD JSON
- image → PDF wrapper
- gold bootstrap source: `text_output`
- recommended subgroup: `ocr_form` or `structured_form`

### OCR invoice
- image → PDF wrapper
- gold bootstrap source: parsed `parsed_data`
- recommended subgroup: `invoice`

## Important caution

Bootstrapped gold is a **starting point**, not automatically paper-ready truth.
After import:
1. review the generated gold file
2. normalize field naming if needed
3. run `validate_paper_ood_gold.py`
4. only then copy the row into the real manifest

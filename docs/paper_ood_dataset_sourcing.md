# Paper OOD Dataset Sourcing Guide

This benchmark is designed around a **paired OOD main set** plus a **small structured control set**.
The main paper claim is about harmful text layers and adaptive routing, so the sourcing priority is:

1. **unstructured / semi-structured commercial documents** for the main set
2. **clean structured documents** for non-regression control
3. a **causal probe subset** where a `text_layer_stripped` PDF can be generated from the same original PDF

## Recommended Hugging Face sourcing buckets

### A. Main OOD buckets

#### 1) Receipts / POS slips / small commercial documents
Use these as the backbone of the `paper_ood_main_manifest.jsonl` dataset.

- `naver-clova-ix/cord-v2`
  - https://huggingface.co/datasets/naver-clova-ix/cord-v2/viewer
  - Strong for receipt-style semi-structured layouts.
- `jsdnrs/ICDAR2019-SROIE`
  - https://huggingface.co/datasets/jsdnrs/ICDAR2019-SROIE
  - Real scanned receipts, useful for OCR-noisy settings.
- `mankind1023/receipt-dataset-standardized`
  - https://huggingface.co/datasets/mankind1023/receipt-dataset-standardized
  - Useful as a broader receipt pool curated from public sources.
- `philschmid/ocr-invoice-data`
  - https://huggingface.co/datasets/philschmid/ocr-invoice-data
  - Good for invoice-like semi-structured documents.
- `abdoelsayed/CORU`
  - https://huggingface.co/datasets/abdoelsayed/CORU
  - Receipt understanding / post-OCR style data.

**Recommendation:** build the first 100+ main set primarily from receipt / invoice style PDFs because Hugging Face coverage is strongest there.

#### 2) Ticket-like documents
Hugging Face has fewer clean ticket/PDF sources than receipt sources. Treat ticket data as a secondary bucket:

- first search HF for ticket/e-ticket style datasets
- if coverage is thin, supplement with manually collected public PDF tickets or synthetic-but-realistic ticket PDFs

#### 3) Brochure / flyer / poster / mixed-layout PDFs
HF coverage is much weaker here. Use these as a smaller OOD subgroup, not the majority bucket.

**Recommendation:** keep brochure/flyer/poster as a targeted subgroup rather than the backbone of the main set.

### B. Structured control candidates
Use these for `paper_structured_control_manifest.jsonl`.

- `aharley/rvl_cdip`
  - https://huggingface.co/datasets/aharley/rvl_cdip
  - Broad structured document categories; useful as a control sourcing pool.
- `davidle7/funsd-json`
  - https://huggingface.co/datasets/davidle7/funsd-json
  - Form-like scanned documents.
- `nielsr/FUNSD_layoutlmv2`
  - https://huggingface.co/datasets/nielsr/FUNSD_layoutlmv2
  - Another FUNSD packaging; useful when format compatibility differs.
- `eliolio/docvqa`
  - https://huggingface.co/datasets/eliolio/docvqa
  - More general document images; useful for selecting cleaner control examples.

**Recommendation:** structured control should be intentionally small (roughly 15--20 docs), curated for clean non-regression checks rather than representativeness.

## Practical sourcing strategy

### Main set (100+)
Recommended composition:
- 50--70: receipt / POS / invoice-like
- 15--25: OCR-noisy scans / mixed scan documents
- 10--20: ticket-like documents
- 10--20: brochure / flyer / mixed-layout PDFs

### Control set (15--20)
- digital-born reports/forms/docs
- easier OCR / cleaner text layer
- should not be selected for failure cases

### Causal probe subset (20--30)
Select from the main set after an initial pilot run:
- large `rasterized - original` improvement
- large `auto - original` improvement
- visually plausible harmful-text-layer cases

## Manifest contract reminder
All manifests should include at least:
- `doc_id`
- `input_pdf`
- `subgroup`
- `gold_path`
- `gold_format`
- `metric_family`
- `annotation_source`
- `canonicalization_version`

Optional / useful fields:
- `source_bucket`
- `language`
- `suspected_issue`
- `inclusion_reason`
- `freeze_revision`
- `stripped_pdf` (required for causal subset)

## Important caveat
Hugging Face is likely enough to source the **receipt/invoice-heavy main backbone**, but it is **not enough by itself** for all desired OOD subgroups.
In practice, use HF as the primary source for:
- receipts
- invoices
- form-like scanned docs

and expect to supplement:
- tickets
- brochures / flyers / posters
- especially weird low-quality PDFs

That still fits the paper goal: the paper needs a strong harmful-text-layer OOD benchmark, not a perfectly uniform public benchmark.

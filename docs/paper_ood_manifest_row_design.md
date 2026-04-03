# Paper OOD Manifest Row Design Rules

This note translates the HF-first sourcing plan into **manifest-ready row rules**.
Use it when converting a downloaded source sample into one JSONL row.

## Canonical row skeleton

```json
{
  "doc_id": "receipt-sroie-0001",
  "input_pdf": "benchmark/paper_ood/raw/receipt-sroie-0001.pdf",
  "subgroup": "receipt",
  "source_bucket": "hf:jsdnrs/ICDAR2019-SROIE",
  "gold_path": "benchmark/paper_ood/gold/receipt-sroie-0001.json",
  "gold_format": "fields_json",
  "metric_family": "token_f1",
  "annotation_source": "manual",
  "canonicalization_version": "v1",
  "language": "en",
  "suspected_issue": "ocr_noise",
  "inclusion_reason": "scanned_receipt_with_noisy_text_layer",
  "freeze_revision": "paper-ood-v1"
}
```

## Field-level rules

### `doc_id`
Use `<subgroup>-<source-shortname>-<zero-padded-id>`.

Recommended shortnames:
- `sroie`
- `cord`
- `receiptstd`
- `invoiceocr`
- `funsd`
- `rvl`
- `ticketman`
- `brochureman`

Examples:
- `receipt-sroie-0001`
- `receipt-cord-0017`
- `invoice-invoiceocr-0003`
- `structured-funsd-0004`
- `control-rvl-0009`

### `subgroup`
Use only stable paper-facing labels:
- `receipt`
- `invoice`
- `ocr_form`
- `ticket`
- `brochure`
- `mixed_layout`
- `structured_form`
- `structured_control`

Do **not** encode the source name inside `subgroup`.
Source belongs in `source_bucket`.

### `source_bucket`
Always prefix by origin:
- HF sources: `hf:<dataset-name>`
- manual sources: `manual:<collector-or-site>`

Examples:
- `hf:jsdnrs/ICDAR2019-SROIE`
- `hf:naver-clova-ix/cord-v2`
- `manual:public-ticket-samples`

### `gold_format`
Use the most stable contract for the subgroup:
- receipts / invoices / forms → `fields_json`
- clean control text docs → `transcript_txt` or `transcript_json`

### `metric_family`
Recommended defaults:
- `fields_json` → `token_f1`
- clean exact form extraction control → `exact_match` if field schema is strict
- transcript-based control → `cer` or `wer`

### `annotation_source`
Allowed practical values:
- `manual`
- `manual_from_source_annotation`
- `manual_normalized`

Avoid vague labels like `auto` unless the row was truly not manually verified.

### `suspected_issue`
Use a small vocabulary so subgroup summaries stay clean:
- `ocr_noise`
- `noisy_text_layer`
- `layout_fragmentation`
- `dense_small_text`
- `mixed_language_or_symbols`
- `folded_scan`
- `clean_control`

### `freeze_revision`
This is the dataset-freeze tag used by the paper benchmark, not necessarily the HF git SHA.
Recommended pattern:
- `paper-ood-v1`
- `paper-ood-v1-r2`

If you also need the upstream revision, add it inside curation notes or a sidecar CSV, but keep `freeze_revision` paper-centric.

## Source-specific mapping rules

## 1. `jsdnrs/ICDAR2019-SROIE`
Use for the **receipt** backbone.

Recommended mapping:
- `subgroup`: `receipt`
- `gold_format`: `fields_json`
- `metric_family`: `token_f1`
- `suspected_issue`: usually `ocr_noise` or `noisy_text_layer`
- `inclusion_reason`: scanned receipt with semi-structured key fields

Doc ID pattern:
- `receipt-sroie-0001`

## 2. `naver-clova-ix/cord-v2`
Use for receipt layout diversity.

Recommended mapping:
- `subgroup`: `receipt`
- `gold_format`: `fields_json`
- `metric_family`: `token_f1`
- `suspected_issue`: `layout_fragmentation` or `dense_small_text`
- `inclusion_reason`: receipt layout diversity with dense field structure

Doc ID pattern:
- `receipt-cord-0001`

## 3. `mankind1023/receipt-dataset-standardized`
Use as an efficient filler pool once SROIE/CORD are partially exhausted.

Recommended mapping:
- `subgroup`: `receipt`
- `gold_format`: `fields_json`
- `metric_family`: `token_f1`
- `suspected_issue`: inherited from visual review, not assumed from source
- `inclusion_reason`: standardized receipt row selected to fill receipt bucket

Doc ID pattern:
- `receipt-receiptstd-0001`

## 4. `philschmid/ocr-invoice-data`
Use for the invoice subgroup.

Recommended mapping:
- `subgroup`: `invoice`
- `gold_format`: `fields_json`
- `metric_family`: `token_f1`
- `suspected_issue`: `ocr_noise` or `dense_small_text`
- `inclusion_reason`: invoice-like semi-structured commercial document

Doc ID pattern:
- `invoice-invoiceocr-0001`

## 5. `davidle7/funsd-json`
Use in two ways:
- OOD noisy-form rows in main set
- cleaner form rows in structured control

Main-set FUNSD mapping:
- `subgroup`: `ocr_form`
- `gold_format`: `fields_json`
- `metric_family`: `token_f1`
- `suspected_issue`: `layout_fragmentation` or `ocr_noise`
- `inclusion_reason`: scanned form with noisy OCR-like layout behavior

Control-set FUNSD mapping:
- `subgroup`: `structured_form`
- `gold_format`: `fields_json`
- `metric_family`: `exact_match`
- `suspected_issue`: `clean_control`
- `inclusion_reason`: cleaner form selected as non-regression control

Doc ID patterns:
- `ocrform-funsd-0001`
- `structured-funsd-0001`

## 6. `aharley/rvl_cdip`
Use only for structured control.

Recommended mapping:
- `subgroup`: `structured_control`
- `gold_format`: `transcript_txt` or `transcript_json`
- `metric_family`: `cer` or `wer`
- `suspected_issue`: `clean_control`
- `inclusion_reason`: clean digital-born or easier structured control document

Doc ID pattern:
- `control-rvl-0001`

## Causal subset row rule
When promoting a row into the causal probe manifest:
- keep the same `doc_id`
- copy all main-row metadata
- add `stripped_pdf`
- update `suspected_issue` if needed to a stronger causal label like `harmful_text_layer`
- set `inclusion_reason` to a pilot-run-based criterion, e.g. `large_rasterized_gain_pilot`

## Promotion checklist
Before a row enters a real manifest:
1. local PDF exists
2. local gold exists
3. row follows canonical subgroup labels
4. row uses the correct source bucket
5. row has a concrete inclusion reason
6. row passes `audit_paper_ood_manifest.py`

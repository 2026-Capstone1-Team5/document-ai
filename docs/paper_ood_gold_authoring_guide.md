# Paper OOD Gold Authoring Guide

This guide defines how to write **gold artifacts** for the paper OOD benchmark.

## Why gold discipline matters

The benchmark compares `original`, `rasterized`, and `auto` on the **same frozen document**.
If gold artifacts drift in shape or completeness across subgroups, the paper loses interpretability.

## Supported gold contracts

### 1. `fields_json`
Use for:
- receipts
- invoices
- forms with stable key-value extraction goals

Rules:
- must be a non-empty JSON object
- keys must be non-empty strings
- values should be flat scalar values or strings
- do not nest arbitrary lists/dicts unless the whole subgroup contract explicitly changes later

Recommended examples:
- `vendor_name`
- `document_date`
- `total_amount`
- `currency`
- `document_id`

Template:
- `benchmark/paper_ood/gold_templates/fields_json.template.json`

### 2. `transcript_txt`
Use for:
- clean control documents
- transcript-style scoring where canonical text is enough

Rules:
- plain UTF-8 text file
- must not be empty
- normalize obvious copy artefacts before saving
- keep only the text intended for scoring

Template:
- `benchmark/paper_ood/gold_templates/transcript_txt.template.txt`

### 3. `transcript_json`
Use when transcript metadata is useful but the scoring still depends on one canonical text field.

Rules:
- JSON object or JSON string
- if object, it must contain one non-empty text field under:
  - `text`
  - `transcript`
  - `content`

Template:
- `benchmark/paper_ood/gold_templates/transcript_json.template.json`

## Recommended subgroup mapping

- `receipt` → `fields_json` + `token_f1`
- `invoice` → `fields_json` + `token_f1`
- `ocr_form` → `fields_json` + `token_f1`
- `structured_form` → `fields_json` + `exact_match`
- `structured_control` → `transcript_txt` or `transcript_json` + `cer`/`wer`

## Authoring checklist per document

1. Confirm the subgroup.
2. Pick the correct gold contract.
3. Save the gold under `benchmark/paper_ood/gold/`.
4. Run validation before touching the manifest.
5. Only then mark the row as `gold_created=yes` in the tracker.

## Validation commands

Validate a single gold file:

```bash
python scripts/validate_paper_ood_gold.py \
  --gold-path benchmark/paper_ood/gold/receipt-sroie-0001.json \
  --gold-format fields_json
```

Validate all gold files referenced by a manifest:

```bash
python scripts/validate_paper_ood_gold.py \
  benchmark/manifests/paper_ood_main_batch1.template.jsonl
```

The validator fails when:
- the gold file is missing
- the JSON is malformed
- `fields_json` is empty or wrongly typed
- transcript contracts have no usable text

## Practical rule of thumb

When in doubt:
- prefer **stable, smaller gold contracts** over ambitious nested structures
- keep subgroup contracts internally consistent
- do not change a subgroup contract mid-collection without updating the row-design docs

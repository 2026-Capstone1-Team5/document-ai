# Paper OOD First Batch Playbook

This playbook is for the **first real collection pass**.
The goal is not to finish the full paper benchmark in one shot, but to create a clean, auditable starting batch that proves the end-to-end curation workflow works.

## Batch 1 target

### Main OOD starter batch
- 6 SROIE receipt rows
- 4 CORD receipt rows
- 3 invoice rows
- 3 FUNSD noisy-form rows

Total: **16 main-set starter rows**

### Structured control starter batch
- 2 FUNSD cleaner-form control rows
- 4 RVL-CDIP control rows

Total: **6 control starter rows**

## Why this batch exists

Batch 1 is meant to validate:
1. file freezing and naming convention
2. gold artifact creation workflow
3. manifest authoring discipline
4. manifest audit CLI behavior
5. runner/scoring/artifact path before scaling to 100+

## Required deliverables for each row

Every row must end with:
- local PDF frozen under `benchmark/paper_ood/raw/`
- local gold frozen under `benchmark/paper_ood/gold/`
- one manifest row copied into the appropriate real manifest
- one tracker row updated in the collection tracker

## Source-specific batch allocation

### SROIE (6 rows)
Use for scanned receipt failures.

Suggested IDs:
- `receipt-sroie-0001`
- `receipt-sroie-0002`
- `receipt-sroie-0003`
- `receipt-sroie-0004`
- `receipt-sroie-0005`
- `receipt-sroie-0006`

### CORD (4 rows)
Use for dense field-layout receipts.

Suggested IDs:
- `receipt-cord-0001`
- `receipt-cord-0002`
- `receipt-cord-0003`
- `receipt-cord-0004`

### Invoice (3 rows)
Use for non-receipt semi-structured commercial docs.

Suggested IDs:
- `invoice-invoiceocr-0001`
- `invoice-invoiceocr-0002`
- `invoice-invoiceocr-0003`

### FUNSD main (3 rows)
Use for OCR-noisy form behavior.

Suggested IDs:
- `ocrform-funsd-0001`
- `ocrform-funsd-0002`
- `ocrform-funsd-0003`

### Structured control (6 rows)
- `structured-funsd-0001`
- `structured-funsd-0002`
- `control-rvl-0001`
- `control-rvl-0002`
- `control-rvl-0003`
- `control-rvl-0004`

## Operational sequence

1. Freeze the PDF locally.
2. Create the gold artifact.
3. Fill the tracker row.
4. Copy the matching seed JSONL row into the real manifest and adjust only the row-specific facts.
5. Run the audit command.
6. Do not benchmark until the audit passes.

## Audit commands

### Main starter batch
```bash
python scripts/audit_paper_ood_manifest.py \
  benchmark/manifests/paper_ood_main_batch1.template.jsonl \
  --min-total 16 \
  --min-subgroup receipt=10 \
  --min-subgroup invoice=3 \
  --min-subgroup ocr_form=3
```

### Control starter batch
```bash
python scripts/audit_paper_ood_manifest.py \
  benchmark/manifests/paper_structured_control_batch1.template.jsonl \
  --min-total 6 \
  --min-subgroup structured_control=4 \
  --min-subgroup structured_form=2
```

These starter manifests are expected to fail until the PDFs and gold files are truly present. That is intentional.

## Done criteria for Batch 1

Batch 1 is complete when:
- all 22 rows have frozen local files
- both starter manifests pass audit
- the team has validated the naming and row-writing discipline
- at least one end-to-end benchmark dry run is performed on the starter batch

## After Batch 1

Once Batch 1 is stable, scale by repeating the same pattern until the real target manifests reach:
- main OOD: 100+
- control: 15--20
- causal: selected later from pilot results

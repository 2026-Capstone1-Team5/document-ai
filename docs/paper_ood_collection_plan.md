# Paper OOD First-Pass Collection Plan

This is the **operational collection plan** for building the paper benchmark from a
HF-first sourcing strategy.

## Goal

Build a benchmark with three layers:

1. **Main OOD paired set**: 100--125 documents
2. **Structured control set**: 15--20 documents
3. **Causal probe subset**: 20--30 documents sampled from the main set after a pilot run

Primary comparison for the paper:
- `original`
- `rasterized`
- `auto`

Causal probe only:
- `text_layer_stripped`

## Source allocation (pass 1)

| Bucket | Source | Role | Target docs | Current source signal | Gold contract | Metric family | Notes |
|---|---|---:|---:|---|---|---|---|
| Receipt scan / OCR-noisy | `jsdnrs/ICDAR2019-SROIE` | Main | 35--40 | HF card reports **987 rows** and **CC-BY-4.0** | `fields_json` | `token_f1` | Best first pull for real scanned receipt failures |
| Receipt layout / semi-structured | `naver-clova-ix/cord-v2` | Main | 25--30 | HF metadata shows **800/100/100 train/val/test** and page license **CC-BY-4.0** | `fields_json` | `token_f1` | Strong receipt layouts; verify export path per sample |
| Aggregated receipt pool | `mankind1023/receipt-dataset-standardized` | Main | 20--25 | HF page describes **2800 receipt images with paired JSON**, with upstream-license redistribution notice | `fields_json` | `token_f1` | Efficient filler pool; keep provenance strict per row |
| Invoice / commercial docs | `philschmid/ocr-invoice-data` | Main | 10--15 | HF invoice-style source; exact row count/license must be frozen during pull | `fields_json` | `token_f1` | Use to avoid overfitting benchmark to only receipts |
| Noisy forms | `davidle7/funsd-json` | Main + Control | 10 main + 5 control | HF card reports **199 rows**, **Apache-2.0** | `fields_json` | `exact_match` or `token_f1` | Good bridge between OOD failures and structured control |
| Clean control docs | `aharley/rvl_cdip` | Control | 10--12 | HF card reports **320k/40k/40k** split counts; license traces to Legacy Tobacco archive | `transcript_txt` or `transcript_json` | `cer` or `wer` | Use only carefully selected clean digital-born controls |
| Extra control backup | `eliolio/docvqa` | Control backup | 0--5 | HF page points to challenge data; dataset page itself is not a direct PDF pool | `transcript_txt` | `cer` | Optional backup, not primary source |
| Tickets / brochures / mixed weird PDFs | Manual supplementation | Main | 10--15 | HF coverage weaker | subgroup-specific | subgroup-specific | Needed to preserve the OOD story beyond receipts |

## Target composition

### Main OOD paired set (100--125)
- 60--75 receipt / POS / invoice-like docs
- 10--15 OCR-noisy forms
- 10--15 ticket-like docs
- 10--15 brochure / flyer / mixed-layout docs

### Structured control set (15--20)
- 5 FUNSD-derived cleaner forms
- 10--12 RVL-CDIP-derived clean controls
- 0--5 optional DocVQA-like backups

### Causal probe subset (20--30)
Do **not** curate this upfront.

Select it from the main set **after a pilot run** using these rules:
- large `rasterized - original` gain, or
- large `auto - original` gain, and
- visually plausible harmful-text-layer behavior, and
- stripped-PDF generation passes validation

## Collection order

1. Pull **SROIE** first
2. Pull **CORD v2** second
3. Pull **receipt-dataset-standardized** third
4. Add **invoice-like** rows from `ocr-invoice-data`
5. Add **FUNSD** rows for the noisy-form subgroup
6. Fill the final OOD gap with **manual ticket/brochure supplementation**
7. Curate the structured control set from **FUNSD + RVL-CDIP**

This order is intentional: it gets the receipt-heavy main benchmark to 80% completion quickly,
then adds subgroup diversity.

## Row-level curation rules

Every accepted row should have:
- `source_bucket`
- `freeze_revision`
- `inclusion_reason`
- `suspected_issue`
- stable `doc_id`
- local frozen `input_pdf`
- local frozen `gold_path`

Recommended `suspected_issue` vocabulary:
- `noisy_text_layer`
- `ocr_noise`
- `layout_fragmentation`
- `dense_small_text`
- `mixed_language_or_symbols`
- `folded_scan`
- `clean_control`

## Audit gates before execution

### Main set
```bash
python scripts/audit_paper_ood_manifest.py \
  benchmark/manifests/paper_ood_main_manifest.jsonl \
  --min-total 100 \
  --min-subgroup receipt=50 \
  --min-subgroup invoice=10 \
  --min-subgroup ticket=10
```

### Structured control
```bash
python scripts/audit_paper_ood_manifest.py \
  benchmark/manifests/paper_structured_control_manifest.jsonl \
  --min-total 15
```

### Causal probe
```bash
python scripts/audit_paper_ood_manifest.py \
  benchmark/manifests/paper_ood_causal_probe_manifest.jsonl \
  --require-stripped \
  --min-total 20
```

## Evidence use in the paper

- **Main table**: main OOD paired set
- **Non-regression check**: structured control set
- **Mechanism / harmful-text-layer evidence**: causal probe subset
- **External anchor**: OmniDocBench appendix / supporting benchmark

## Source references

- SROIE: https://huggingface.co/datasets/jsdnrs/ICDAR2019-SROIE
- CORD v2: https://huggingface.co/datasets/naver-clova-ix/cord-v2
- receipt-dataset-standardized: https://huggingface.co/datasets/mankind1023/receipt-dataset-standardized
- ocr-invoice-data: https://huggingface.co/datasets/philschmid/ocr-invoice-data
- FUNSD JSON: https://huggingface.co/datasets/davidle7/funsd-json
- RVL-CDIP: https://huggingface.co/datasets/aharley/rvl_cdip
- DocVQA: https://huggingface.co/datasets/eliolio/docvqa

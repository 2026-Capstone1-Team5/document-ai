# Paper OOD Dataset Shortlist (HF-first)

This is the **first-pass shortlist** for curating the paper OOD paired benchmark.
It is intentionally pragmatic: start with the strongest public sources for receipt/invoice/form-like documents, then fill weaker subgroups manually.

## Tier 1 — pull first
These should be the first sources used when building the main set.

### 1) `jsdnrs/ICDAR2019-SROIE`
- Link: https://huggingface.co/datasets/jsdnrs/ICDAR2019-SROIE
- Why: real scanned English receipts, OCR noise, semi-structured fields.
- Fit:
  - main OOD receipt bucket
  - causal subset candidate pool
- Notes:
  - HF card says **987 receipt images**.
  - HF card says license is **CC-BY-4.0**.

### 2) `naver-clova-ix/cord-v2`
- Link: https://huggingface.co/datasets/naver-clova-ix/cord-v2
- Why: strong receipt-style structured annotations and varied layout fields.
- Fit:
  - main OOD receipt bucket
  - good for `fields_json` gold design
- Notes:
  - HF page exposes receipt parsing structure and split metadata.
  - Check upstream license/redistribution terms before final paper release packaging.

### 3) `mankind1023/receipt-dataset-standardized`
- Link: https://huggingface.co/datasets/mankind1023/receipt-dataset-standardized
- Why: already aggregates multiple public receipt sources into one standardized pool.
- Fit:
  - efficient bulk sourcing for the 100+ main set
- Notes:
  - HF page says **2800 receipt images with paired JSON annotations**.
  - HF page says it redistributes upstream datasets under their original licenses; use `NOTICE.md` and `licenses/` for exact provenance.

## Tier 2 — pull for specific subgroups
These are useful, but should not dominate the main set.

### 4) `philschmid/ocr-invoice-data`
- Link: https://huggingface.co/datasets/philschmid/ocr-invoice-data
- Why: invoice-like semi-structured commercial docs.
- Fit:
  - invoice subgroup inside main OOD

### 5) `davidle7/funsd-json`
- Link: https://huggingface.co/datasets/davidle7/funsd-json
- Why: noisy scanned forms; good control/control-adjacent material.
- Fit:
  - structured control
  - OCR-noisy scanned form subgroup
- Notes:
  - HF card says **Apache-2.0** from original FUNSD.

### 6) `nielsr/FUNSD_layoutlmv2`
- Link: https://huggingface.co/datasets/nielsr/FUNSD_layoutlmv2
- Why: alternate FUNSD packaging if tooling compatibility is better.
- Fit:
  - structured control backup source

### 7) `aharley/rvl_cdip`
- Link: https://huggingface.co/datasets/aharley/rvl_cdip
- Why: broad structured document pool for selecting clean control examples.
- Fit:
  - structured control only
- Notes:
  - HF card points to IIT-CDIP / Legacy Tobacco Document Library licensing.
  - Use carefully; do a license review before final redistribution decisions.

## Tier 3 — likely manual supplementation needed
These subgroups are part of the paper story, but HF alone probably won't cover them well enough.

### 8) Ticket / e-ticket PDFs
- Current view: HF coverage appears thinner than receipts.
- Recommendation:
  - use HF if a clean ticket dataset is found later,
  - otherwise supplement with public sample ticket PDFs or curated synthetic-but-realistic ticket PDFs.

### 9) Brochure / flyer / poster / mixed-layout PDFs
- Current view: HF coverage is weaker and more heterogeneous.
- Recommendation:
  - keep as a **small targeted subgroup**,
  - likely supplement manually.

## Recommended first curation pass
Use this order:
1. `jsdnrs/ICDAR2019-SROIE`
2. `naver-clova-ix/cord-v2`
3. `mankind1023/receipt-dataset-standardized`
4. `philschmid/ocr-invoice-data`
5. `davidle7/funsd-json`
6. `aharley/rvl_cdip`

## Suggested target counts for pass 1
- 40 from SROIE / scanned receipt-like docs
- 30 from CORD v2 / receipt layouts
- 20 from standardized receipt aggregate
- 10--15 from invoice-like sources
- 10--15 from FUNSD / structured scanned forms
- 10--20 manually supplemented ticket/brochure/mixed-layout docs

This is enough to build a realistic **100+ main set**, then carve out:
- 15--20 structured control
- 20--30 causal probe subset

## Manifest filling rule
When adding a row, always fill:
- `source_bucket` as `hf:<dataset-name>` or `manual:<source>`
- `inclusion_reason`
- `suspected_issue`
- `freeze_revision`

That keeps the curation auditable later.

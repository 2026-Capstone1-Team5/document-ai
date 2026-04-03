# Final Routing Evidence Dataset

This document records the **final controlled dataset** used to directly support the paper's classifier-reliability claim.

## Contribution this dataset supports

This dataset is designed to support the following paper-safe contribution statement:

> We empirically demonstrate that MinerU's preprocessing classifier can make unreliable routing decisions under specific harmful-text-layer conditions. In the final controlled receipt/invoice set, `classify()` directly returns `txt` while all observed classifier-side signals remain on the text-acceptable side of their thresholds, yet downstream parsing quality under the original path remains poor. Rasterization and our adaptive fallback mitigate that failure mode.

This wording is intentionally narrower than a universal training-mismatch claim.
It states a **directly observed classifier unreliability phenomenon** under a reproducible controlled condition.

## Dataset design

### Source population
The dataset is derived from the already frozen receipt/invoice rows in:
- `benchmark/manifests/paper_ood_main_manifest.jsonl`

### Final routing-evidence manifest
- `benchmark/manifests/paper_routing_evidence_manifest.jsonl`

### Size and composition
- total documents: **13**
- subgroup mix:
  - `receipt = 10`
  - `invoice = 3`

### Source breakdown
- `jsdnrs/ICDAR2019-SROIE` (HF): **6**
- `naver-clova-ix/cord-v2` (HF): **4**
- `philschmid/ocr-invoice-data` (HF): **3**

### Construction rule
Each routing-evidence PDF is constructed from an existing receipt/invoice image-backed row by:
1. placing the original receipt/invoice image on a larger page so the image coverage ratio stays below MinerU's high-image threshold,
2. overlaying an invisible but extractable harmful text layer derived from another document's gold text,
3. preserving the original gold target for evaluation.

The generator is:
- `scripts/materialize_paper_routing_evidence_dataset.py`

## Reproduction commands

### 1) Materialize the controlled dataset
```bash
python3 scripts/materialize_paper_routing_evidence_dataset.py --max-docs 13 \
  > output/benchmark_reports/paper_routing_evidence_materialization_report.json
```

### 2) Benchmark run
```bash
python3 scripts/paper_ood_benchmark.py \
  --manifest benchmark/manifests/paper_routing_evidence_manifest.jsonl \
  --run-root output/paper_routing_evidence_full \
  --report-dir output/benchmark_reports \
  --variants original,rasterized,auto \
  --timeout-seconds 900
```

### 3) Score the run
```bash
python3 scripts/score_paper_ood_results.py \
  --results-json output/paper_routing_evidence_full/results.json \
  --output-json output/benchmark_reports/paper_routing_evidence_full_scored.json
```

### 4) Direct routing observation
```bash
python3 scripts/observe_paper_ood_routing.py \
  --manifest benchmark/manifests/paper_routing_evidence_manifest.jsonl \
  --scored-json output/benchmark_reports/paper_routing_evidence_full_scored.json \
  --output-json output/benchmark_reports/paper_routing_evidence_observation_scored.json
```

### 5) Build the paper-facing claim bundle
```bash
python3 scripts/build_paper_claim_evidence.py \
  --routing-json output/benchmark_reports/paper_routing_evidence_observation_scored.json \
  --scored-json output/benchmark_reports/paper_routing_evidence_full_scored.json \
  --output-json output/benchmark_reports/paper_routing_evidence_claim_evidence.json \
  --output-md output/benchmark_reports/paper_routing_evidence_claim_evidence.md
```

## Direct classifier observation

Source:
- `output/benchmark_reports/paper_routing_evidence_observation_scored.json`

Observed across the full 13-document set:
- `classify() = txt`: **13 / 13**
- classifier signal accepts text path: **13 / 13**
- mean average cleaned chars/page: **1717.15**
- mean invalid-character ratio: **0.00**
- mean high-image-coverage ratio: **0.00**

Interpretation:
- by MinerU's own classifier-side checks, every document in this final set looks acceptable for the text path
- nevertheless, downstream quality under the original path remains poor

### Current MinerU threshold mapping

In the currently installed MinerU version, `classify()` does **not** expose an `abnormal_ratio < 3%` metric.
Instead, the direct classifier checks are:

- `avg_cleaned_chars_per_page >= 50`
- `invalid_char_ratio <= 0.05`
- `high_image_coverage_ratio < 0.8`

The `invalid_char_ratio` reported here is the exact CID-pattern ratio used by `detect_invalid_chars(...)`
inside `mineru.utils.pdf_classify`, so the paper should refer to the **current invalid-character threshold**
rather than to an unavailable `abnormal_ratio` field.

## Quantitative result

Source:
- `output/benchmark_reports/paper_routing_evidence_full_scored.json`

| variant | n | mean primary score | mean token F1 | mean CER | mean WER | mean NED |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| original | 13 | 0.1266 | 0.1266 | 3.4215 | 1.6267 | 0.8377 |
| rasterized | 13 | 0.2089 | 0.2089 | 0.8887 | 0.9359 | 0.7863 |
| auto | 13 | 0.2009 | 0.2009 | 0.8963 | 0.9421 | 0.7916 |

### Pairwise comparison summary
- `rasterized - original`
  - mean delta in primary score: **+0.0823**
  - positive on **6 / 13**, tied on **7 / 13**, negative on **0 / 13**
  - sign-test p-value: **0.03125**
- `auto - original`
  - mean delta in primary score: **+0.0743**
  - positive on **5 / 13**, tied on **8 / 13**, negative on **0 / 13**
  - sign-test p-value: **0.0625**
- `auto - rasterized`
  - mean delta: **-0.0080**

Interpretation:
- the original text-path behavior is consistently weak on this final controlled set
- rasterization provides the strongest recovery
- the current adaptive route improves over the original path on mean score, but remains slightly below forced rasterization

## What this proves

This final dataset directly supports the following three-part observation:
1. **direct routing decision**: MinerU's `classify()` returns `txt`
2. **internal signals look acceptable**: chars/page is high, CID ratio is low, image coverage is low
3. **actual outcome is bad**: original-path parsing quality is poor, while rasterization improves it

That is enough to support the paper claim that the preprocessing classifier is **not reliable under this specific harmful-text-layer condition**.

## What this does not prove

This dataset does **not** prove:
- that every real-world receipt failure is caused by the same mechanism
- that training-distribution mismatch is the sole root cause
- that MinerU universally fails on all receipt PDFs

Those broader claims should still be avoided.

## Recommended paper wording

Recommended paragraph:

> On a controlled routing-evidence set of 13 receipt/invoice-like PDFs, MinerU's `classify()` returned `txt` for all documents, and all observed classifier-side signals remained on the text-acceptable side of their thresholds (mean cleaned characters per page 1717.15, mean invalid-character ratio 0.00, mean high-image-coverage ratio 0.00). Despite this, the original path yielded poor parsing quality (mean primary score 0.1266, mean CER 3.4215), while rasterization improved the same documents (mean primary score 0.2089, mean CER 0.8887). We therefore treat this as direct evidence that the preprocessing classifier can be unreliable under harmful-text-layer conditions, without claiming that this mechanism explains every receipt failure in the wild.

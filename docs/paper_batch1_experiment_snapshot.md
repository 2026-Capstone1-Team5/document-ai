# Paper Batch 1 Experiment Snapshot

This snapshot records the first **paper-facing** OOD experiment batch that is already runnable inside the repo.
It is intended to support writing, not to replace the larger 100+ document target set.

## Scope

### Main OOD batch
- manifest: `benchmark/manifests/paper_ood_main_manifest.jsonl`
- size: **16 documents**
- subgroup mix:
  - `receipt = 10`
  - `invoice = 3`
  - `ocr_form = 3`
- variants:
  - `original`
  - `rasterized`
  - `auto`

### Structured control batch
- manifest: `benchmark/manifests/paper_structured_control_manifest.jsonl`
- size: **2 documents**
- subgroup mix:
  - `structured_form = 2`
- variants:
  - `original`
  - `rasterized`
  - `auto`

### Routing probe batch
- manifest: `benchmark/manifests/paper_routing_probe_manifest.jsonl`
- purpose: direct `classify()` observation for claim-strength control

## Commands used

### Main OOD run
```bash
python3 scripts/paper_ood_benchmark.py \
  --manifest benchmark/manifests/paper_ood_main_manifest.jsonl \
  --run-root output/paper_ood_batch1_main_full \
  --report-dir output/benchmark_reports \
  --variants original,rasterized,auto \
  --timeout-seconds 900
```

### Main OOD scoring
```bash
python3 scripts/score_paper_ood_results.py \
  --results-json output/paper_ood_batch1_main_full/results.json \
  --output-json output/benchmark_reports/paper_ood_batch1_main_full_scored.json
```

### Structured control run
```bash
python3 scripts/paper_ood_benchmark.py \
  --manifest benchmark/manifests/paper_structured_control_manifest.jsonl \
  --run-root output/paper_ood_batch1_control_full \
  --report-dir output/benchmark_reports \
  --variants original,rasterized,auto \
  --timeout-seconds 900
```

### Structured control scoring
```bash
python3 scripts/score_paper_ood_results.py \
  --results-json output/paper_ood_batch1_control_full/results.json \
  --output-json output/benchmark_reports/paper_ood_batch1_control_full_scored.json
```

### Routing observation
```bash
python3 scripts/observe_paper_ood_routing.py \
  --manifest benchmark/manifests/paper_routing_probe_manifest.jsonl \
  --output-json output/benchmark_reports/paper_routing_probe_observation.json
```

### Claim evidence bundle
```bash
python3 scripts/build_paper_claim_evidence.py \
  --routing-json output/benchmark_reports/paper_routing_probe_observation.json \
  --scored-json output/benchmark_reports/paper_ood_batch1_main_full_scored.json \
  --control-scored-json output/benchmark_reports/paper_ood_batch1_control_full_scored.json \
  --output-json output/benchmark_reports/paper_ood_batch1_claim_evidence.json \
  --output-md output/benchmark_reports/paper_ood_batch1_claim_evidence.md
```

## Main OOD quantitative result

Source: `output/benchmark_reports/paper_ood_batch1_main_full_scored.json`

| variant | n | mean primary score | mean token F1 | mean CER | mean WER | mean NED |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| original | 16 | 0.3758 | 0.3758 | 3.1314 | 3.0580 | 0.6735 |
| rasterized | 16 | 0.4193 | 0.4193 | 1.1415 | 1.0704 | 0.6621 |
| auto | 16 | 0.4193 | 0.4193 | 1.1415 | 1.0704 | 0.6621 |

### Pairwise deltas on the main OOD batch
- `auto - original`
  - mean delta in primary score: **+0.0435**
  - bootstrap mean CI95: **[+0.0036, +0.1116]**
  - sign-test p-value: **0.0703**
- `rasterized - original`
  - mean delta in primary score: **+0.0435**
  - bootstrap mean CI95: **[+0.0036, +0.1116]**
  - sign-test p-value: **0.0703**
- `auto - rasterized`
  - mean delta: **0.0000**

Interpretation for writing:
- on this first OOD batch, **rasterized and auto outperform original on mean primary score**
- in this specific batch, `auto` and `rasterized` are numerically identical because every imported OOD row was directly observed as `classify() = ocr`

## Structured control quantitative result

Source: `output/benchmark_reports/paper_ood_batch1_control_full_scored.json`

| variant | n | mean primary score | mean token F1 | mean CER | mean WER | mean NED |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| original | 2 | 0.5036 | 0.3012 | 2.7825 | 1.1897 | 0.8528 |
| rasterized | 2 | 0.5035 | 0.3135 | 1.7504 | 0.8791 | 0.8241 |
| auto | 2 | 0.5035 | 0.3135 | 1.7504 | 0.8791 | 0.8241 |

Interpretation for writing:
- the current tiny control slice shows **no severe regression** in the primary score
- because `n = 2`, this is only a **non-regression sanity check**, not a strong standalone claim

## Direct routing observation result

Source: `output/benchmark_reports/paper_routing_probe_observation.json`

Directly observed local probe outputs:
- `sample1_researchpaper.pdf` -> `txt`
- `sample6_equations.pdf` -> `txt`
- `sample2_reciept.pdf` -> `ocr`
- `sample3_invoice.pdf` -> `ocr`
- `sample5_bankstatement.pdf` -> `ocr`

Also important:
- the current HF-imported OOD starter batch is image-backed and is directly observed as `ocr`
- therefore the current batch **does not** directly support the stronger claim that a noisy receipt-like PDF was misrouted to the text path

## Claim rule for the paper

Current claim mode from `output/benchmark_reports/paper_ood_batch1_claim_evidence.json`:
- **`conservative_inference_only`**

Recommended wording:
> No direct `classify() = txt` observation was found for the current OOD probes; use conservative wording about threshold limitations or distribution mismatch instead of a categorical routing-failure claim.

Practical paper-safe wording:
> On the first OOD batch, rasterized and auto variants improved mean primary score over the original path, while direct `classify()` observations on the current probes did not yet expose a receipt-like example classified as `txt`. Accordingly, we interpret the evidence as consistent with preprocessing-threshold limitations and/or training-distribution mismatch, rather than claiming a directly observed routing failure for every receipt-like document.

## Why CER is included and Spearman is not

- **CER is included** as an auxiliary quantitative metric because it directly addresses the criticism that the paper lacked text-level error evidence.
- **Spearman correlation is intentionally omitted** at this stage because the current batch is too small for a credible standalone correlation claim; forcing that analysis now would be weaker than stating the limitation explicitly.

## Limitation of this snapshot

This is a **starter batch**, not the final paper dataset.
It is useful because it already provides:
- reproducible OOD benchmarking
- direct `classify()` observation machinery
- CER-backed quantitative evidence
- explicit claim-strength guardrails

It is not yet the final target because:
- the main OOD set is still **16**, not **100+**
- the control set is still **2**, not **10+**
- the current imported OOD rows are image-backed, so they support quality comparisons better than strong causal routing-failure claims

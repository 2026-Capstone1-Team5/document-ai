# Paper Routing Claim Guardrails

This note exists to keep the paper claims aligned with what the repo has **directly observed**.

## Why this note exists

Team feedback correctly pointed out that:

- saying *routing failure* is a **causal claim**
- that claim should not be stated as a direct observation unless `mineru.utils.pdf_classify.classify(...)`
  is observed on the relevant PDF inputs

## Direct-observation path now available

Use:

```bash
python3 scripts/observe_paper_ood_routing.py \
  --manifest benchmark/manifests/paper_routing_probe_manifest.jsonl \
  --output-json output/benchmark_reports/paper_routing_probe_observation.json
```

or point the same script at any other manifest of candidate PDFs.

The script records:
- `classify_result` (`txt` / `ocr`)
- `avg_cleaned_chars_per_page`
- `invalid_char_ratio`
- `invalid_chars_detected`
- `high_image_coverage_ratio`

For the currently installed MinerU version, this is the exact observable threshold surface used by
`classify()`:
- `avg_cleaned_chars_per_page >= 50`
- `invalid_char_ratio <= 0.05`
- `high_image_coverage_ratio < 0.8`

Do **not** rewrite this as an `abnormal_ratio < 3%` result unless you separately extract that metric
from a different MinerU build. In this repo, the direct evidence is the current invalid-character
ratio heuristic plus the other two thresholds above.

## What is directly observed today

There are now **two different evidence lanes** in the repo:

1. **natural / imported batch evidence**
   - useful for OOD quality benchmarking
   - not strong enough by itself for a direct txt-path misrouting claim
2. **controlled routing-evidence dataset**
   - intentionally constructed to expose harmful-text-layer classifier unreliability
   - directly supports the stronger classifier-reliability claim

Keep these two lanes separate in the paper.

From `output/benchmark_reports/paper_routing_probe_observation.json`:

- `sample1_researchpaper.pdf` -> `txt`
- `sample6_equations.pdf` -> `txt`
- `sample2_reciept.pdf` -> `ocr`
- `sample3_invoice.pdf` -> `ocr`
- `sample5_bankstatement.pdf` -> `ocr`

Also, the current HF-imported paper OOD starter batch is image-backed and wrapped into single-page PDFs.
Those rows are all directly observed as `ocr`, not `txt`, which means they are **not suitable evidence for a
text-layer routing-failure claim by themselves**.

From `output/benchmark_reports/paper_routing_evidence_observation_scored.json`:

- controlled receipt/invoice routing-evidence rows are directly observed as `classify() = txt`
- the same rows also keep classifier-side signals on the text-acceptable side of the thresholds
- yet the original path still performs poorly on the paired benchmark

That controlled dataset is now the repo's **direct support** for the narrower claim:

> MinerU's preprocessing classifier can be unreliable under specific harmful-text-layer conditions.

## Claim rule for the paper

### Allowed wording
- “The evidence suggests a blind spot in preprocessing heuristics.”
- “The observed behavior is consistent with threshold limitations or distribution mismatch.”
- “We directly observed `classify()` outputs on representative local probes and did not always observe the stronger failure mode required for a categorical routing-failure claim.”
- “In the controlled routing-evidence dataset, `classify()` returned `txt` while classifier-side signals remained acceptable and the original path still failed.”
- “This directly demonstrates classifier unreliability under controlled harmful-text-layer conditions.”

### Disallowed wording unless a direct counterexample is observed
- “The receipt was misrouted to the text path.”
- “MinerU classified noisy receipts as `txt`.”
- “We proved routing failure.”

### Additional caution even after the controlled dataset exists

Do **not** automatically upgrade the claim to:
- “all receipt failures are caused by txt-path misrouting”
- “training-distribution mismatch is proven as the root cause”
- “the natural imported OOD batch already shows the same direct failure mode”

The controlled dataset proves a narrower but still strong statement:
- the classifier can be made to return `txt` under acceptable internal signals while downstream quality is poor
- therefore the classifier is not intrinsically reliable under harmful-text-layer conditions

## Practical implication

For the **natural imported batch**, the paper should still prefer the lower-strength interpretation:

> the results are consistent with preprocessing-threshold limitations and/or training-distribution mismatch,
> rather than claiming a directly observed misrouting event in every receipt-like example.

For the **controlled routing-evidence dataset**, the paper may now use the stronger but still scoped interpretation:

> under controlled harmful-text-layer conditions, MinerU's preprocessing classifier can route receipt/invoice-like PDFs to the text path even when classifier-side signals appear acceptable, and rasterization mitigates the resulting quality failure.

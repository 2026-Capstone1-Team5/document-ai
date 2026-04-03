# Document-AI
Document AI Technology Based on Document Parsing and Application of AI Agent Skills

## Current parser entrypoint

The current reusable parser entrypoint is:

```bash
python scripts/parse_document.py <input_pdf> <output_dir> --language en
```

It does three things:

1. inspects the PDF
2. chooses either the normal MinerU path or the rasterized path
3. runs MinerU through Docker

If you want the parser to compare original-vs-rasterized output per page and keep the cleaner result:

```bash
python scripts/parse_document.py <input_pdf> <output_dir> --language en --page-adaptive
```

## Requirements

- host Python with:
  - `pymupdf`
  - `pillow`
- one of:
  - local `mineru` CLI available in `PATH`
  - Docker + Docker Compose with a Compose file that defines the `mineru-cpu` service

The script tries these execution paths in order:

1. local `mineru`
2. `docker compose`
3. `docker-compose`

If `mineru` was installed with `pip install --user`, the script also checks the Python user script directory automatically.
The first local `mineru` run may download model files and can take longer than later runs.
When local MinerU hits process-pool permission limits, the parser retries with sequential PDF rendering automatically.

Example:

```bash
pip install pymupdf pillow
docker compose build mineru-cpu
python scripts/parse_document.py benchmark/pdfs/sample2_reciept.pdf output/ --language en
```

## Output

The parser writes:

- `output/meta.json`
- `output/mineru_output/...`
- `output/intermediate/...` only if rasterization was used

With `--page-adaptive`, it writes:

- `output/meta.json`
- `output/selected_markdown.md`
- `output/page_inputs/`
- `output/page_runs/`

`meta.json` includes:

- `input_pdf`
- `parse_input`
- `parse_mode`
- `language`
- `inspection`
- `outputs`

## Document access layer

After MinerU finishes, you can build a document map from the `txt` output folder:

```bash
python3 scripts/document_access.py build benchmark/results/mineru/sample1_researchpaper/txt output/document_map.json
```

This generates a `document_map.json` with:

- `outline`
- `sections`
- `pages`
- `visuals`

The idea is to let agents access the document progressively instead of loading the whole markdown at once.

Useful commands:

```bash
python3 scripts/document_access.py outline output/document_map.json
python3 scripts/document_access.py page output/document_map.json 1
python3 scripts/document_access.py section output/document_map.json section_001
python3 scripts/document_access.py visuals output/document_map.json
python3 scripts/document_access.py visual output/document_map.json image_003
```

`visuals` includes figures, tables, and equations with:

- page number
- bounding box
- image path
- caption text when available

## OmniDocBench benchmark

See the dedicated guide:

- `scripts/omnidocbench/README.md`

## Structured / unstructured benchmark

The main paper benchmark now uses a **flat PDF corpus** under `benchmark/pdfs/`, with document grouping driven by `benchmark/manifest.csv` metadata rather than directory names.

- source of truth: `benchmark/manifest.csv`
- derived manifest: `benchmark/manifests/structured_unstructured_benchmark_manifest.jsonl`
- grouping rule: `digital_type=digital -> structured`, `digital_type=scanned -> unstructured`

Build the manifest from the CSV:

```bash
python3 scripts/build_structured_benchmark_manifest.py \
  --output benchmark/manifests/structured_unstructured_benchmark_manifest.jsonl
```

Run the benchmark across `original`, `rasterized`, and `auto`:

```bash
python3 scripts/benchmark_structured_unstructured.py \
  --manifest benchmark/manifests/structured_unstructured_benchmark_manifest.jsonl \
  --run-root output/structured_unstructured_benchmark \
  --output-json output/benchmark_reports/structured_unstructured_results.json \
  --output-summary output/benchmark_reports/structured_unstructured_summary.json
```

This benchmark is observational: it compares parse success, runtime, and markdown availability/size across the structured and unstructured groups without requiring gold labels for every PDF.

## Paper routing-evidence experiment

For the current paper-ready classifier-reliability experiment, use the controlled routing-evidence set documented in:

- `docs/paper_final_routing_evidence_dataset.md`
- `docs/paper_routing_claim_guardrails.md`

### Dataset

- manifest: `benchmark/manifests/paper_routing_evidence_manifest.jsonl`
- size: **13 documents**
  - `receipt = 10`
  - `invoice = 3`
- source breakdown:
  - `jsdnrs/ICDAR2019-SROIE` (HF): 6
  - `naver-clova-ix/cord-v2` (HF): 4
  - `philschmid/ocr-invoice-data` (HF): 3
- role: this is a **controlled harmful-text-layer evidence set**, not a general-purpose benchmark

Each document is built from a frozen receipt/invoice example by keeping the original gold target,
placing the document image on a larger page, and overlaying an invisible but extractable harmful
text layer. The goal is to test whether MinerU's preprocessing classifier can still choose the text path
when its own observable thresholds look acceptable.

### Reproduction

Materialize the dataset:

```bash
python3 scripts/materialize_paper_routing_evidence_dataset.py --max-docs 13 \
  > output/benchmark_reports/paper_routing_evidence_materialization_report.json
```

Run the benchmark:

```bash
python3 scripts/paper_ood_benchmark.py \
  --manifest benchmark/manifests/paper_routing_evidence_manifest.jsonl \
  --run-root output/paper_routing_evidence_full \
  --report-dir output/benchmark_reports \
  --variants original,rasterized,auto \
  --timeout-seconds 900
```

Score the run:

```bash
python3 scripts/score_paper_ood_results.py \
  --results-json output/paper_routing_evidence_full/results.json \
  --output-json output/benchmark_reports/paper_routing_evidence_full_scored.json
```

Observe direct classifier behavior:

```bash
python3 scripts/observe_paper_ood_routing.py \
  --manifest benchmark/manifests/paper_routing_evidence_manifest.jsonl \
  --scored-json output/benchmark_reports/paper_routing_evidence_full_scored.json \
  --output-json output/benchmark_reports/paper_routing_evidence_observation_scored.json
```

Build the paper-facing claim bundle:

```bash
python3 scripts/build_paper_claim_evidence.py \
  --routing-json output/benchmark_reports/paper_routing_evidence_observation_scored.json \
  --scored-json output/benchmark_reports/paper_routing_evidence_full_scored.json \
  --output-json output/benchmark_reports/paper_routing_evidence_claim_evidence.json \
  --output-md output/benchmark_reports/paper_routing_evidence_claim_evidence.md
```

### Current result snapshot

From the current committed evidence bundle:

- `classify() = txt`: **13 / 13**
- classifier-side text-path acceptance: **13 / 13**
- `claim_mode`: `controlled_classifier_unreliability_supported`

Variant means:

| variant | mean primary score | mean CER |
| --- | ---: | ---: |
| original | 0.1266 | 3.4215 |
| rasterized | 0.2089 | 0.8887 |
| auto | 0.2009 | 0.8963 |

Interpretation:

- this README section documents a **controlled mechanism test**
- it is strong enough to support the narrow claim that MinerU's classifier can be unreliable under
  harmful-text-layer conditions
- it is **not** evidence that every real-world receipt failure shares the same cause

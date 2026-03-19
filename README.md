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

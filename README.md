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

## Requirements

- Docker + Docker Compose
- host Python with:
  - `pymupdf`
  - `pillow`

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

`meta.json` includes:

- `input_pdf`
- `parse_input`
- `parse_mode`
- `language`
- `inspection`
- `outputs`

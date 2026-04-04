#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def fmt(v: Any) -> str:
    if v is None:
        return 'NA'
    if isinstance(v, float):
        return f'{v:.3f}'
    return str(v)


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a single paper-facing report from the main benchmark and stronger-claim outputs.')
    parser.add_argument('--main-summary', required=True)
    parser.add_argument('--claim-json', required=True)
    parser.add_argument('--claim-md', required=True)
    parser.add_argument('--output-md', required=True)
    parser.add_argument('--output-json', required=True)
    args = parser.parse_args()

    main_summary = load_json(Path(args.main_summary))
    claim_json = load_json(Path(args.claim_json))
    claim_md = Path(args.claim_md).read_text(encoding='utf-8')

    payload = {
        'main_benchmark_summary': main_summary,
        'stronger_claim': claim_json,
    }
    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    lines = [
        '# Paper Benchmark Report',
        '',
        '## Main benchmark summary',
        '',
        f"- total_documents: {main_summary.get('total_documents')}",
        f"- variants: {', '.join(main_summary.get('variants', []))}",
        '',
        '### Overall variant summary',
        '',
        '| variant | attempted | succeeded | success_rate | mean_elapsed_seconds | mean_markdown_chars |',
        '| --- | ---: | ---: | ---: | ---: | ---: |',
    ]
    for variant, row in (main_summary.get('overall_variant_summary') or {}).items():
        lines.append(
            f"| {variant} | {fmt(row.get('attempted'))} | {fmt(row.get('succeeded'))} | {fmt(row.get('success_rate'))} | {fmt(row.get('mean_elapsed_seconds'))} | {fmt(row.get('mean_markdown_chars'))} |"
        )
    lines.extend([
        '',
        '### Structured / unstructured summary',
        '',
    ])
    for group, group_row in (main_summary.get('benchmark_group_summary') or {}).items():
        lines.extend([
            f'#### {group}',
            '',
            f"- documents: {group_row.get('documents')}",
            '',
            '| variant | attempted | succeeded | success_rate | mean_elapsed_seconds | mean_markdown_chars |',
            '| --- | ---: | ---: | ---: | ---: | ---: |',
        ])
        for variant, row in (group_row.get('variants') or {}).items():
            lines.append(
                f"| {variant} | {fmt(row.get('attempted'))} | {fmt(row.get('succeeded'))} | {fmt(row.get('success_rate'))} | {fmt(row.get('mean_elapsed_seconds'))} | {fmt(row.get('mean_markdown_chars'))} |"
            )
        lines.append('')

    lines.extend([
        '## Stronger-claim evidence',
        '',
        claim_md.strip(),
        '',
    ])

    out_md = Path(args.output_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'output_md': str(out_md), 'output_json': str(out_json)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

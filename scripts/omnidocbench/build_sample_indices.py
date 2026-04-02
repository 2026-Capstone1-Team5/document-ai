import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from manifest import configure_local_hf_cache, load_gt_rows, official_image_path


def load_gt_attr_map(rows: list[dict], group_by: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        page_info = row.get("page_info", {})
        basename = Path(official_image_path(row)).name
        attrs = page_info.get("page_attribute", {}) or {}
        value = attrs.get(group_by, "unknown")
        if value in (None, ""):
            value = "unknown"
        out[basename] = str(value)
    return out


def load_metric_coverage_map(rows: list[dict]) -> dict[str, str]:
    """
    Build bucket key from page content presence:
    - text (text_block/title/reference-like text categories)
    - formula (equation_isolated)
    - table (table)
    Example bucket: text1_formula0_table1
    """
    text_cats = {
        "text_block",
        "title",
        "reference",
        "header",
        "footer",
        "page_number",
        "page_footnote",
        "abandon",
    }
    out: dict[str, str] = {}
    for row in rows:
        page_info = row.get("page_info", {})
        basename = Path(official_image_path(row)).name
        cats = Counter(d.get("category_type") for d in row.get("layout_dets", []))
        has_text = any(cats.get(c, 0) > 0 for c in text_cats)
        has_formula = cats.get("equation_isolated", 0) > 0
        has_table = cats.get("table", 0) > 0
        bucket = (
            f"text{int(has_text)}_"
            f"formula{int(has_formula)}_"
            f"table{int(has_table)}"
        )
        out[basename] = bucket
    return out


def main() -> None:
    configure_local_hf_cache()
    parser = argparse.ArgumentParser(
        description=(
            "Build balanced OmniDocBench sample indices by group. "
            "Output JSON can be edited by human and used via --indices-file."
        )
    )
    parser.add_argument("--split", default="train")
    parser.add_argument(
        "--group-by",
        default="metric_coverage",
        choices=["data_source", "language", "layout", "metric_coverage"],
    )
    parser.add_argument("--per-group", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        default="output/benchmark_reports/omnidocbench_sample_plan.json",
    )
    args = parser.parse_args()

    random.seed(args.seed)
    rows = load_gt_rows()
    if args.group_by == "metric_coverage":
        attr_map = load_metric_coverage_map(rows)
    else:
        attr_map = load_gt_attr_map(rows, args.group_by)

    group_to_indices: dict[str, list[int]] = defaultdict(list)
    index_to_path: dict[int, str] = {}
    for idx, row in enumerate(rows):
        img_path = official_image_path(row)
        basename = Path(img_path).name
        group = attr_map.get(basename, "unknown")
        group_to_indices[group].append(idx)
        index_to_path[idx] = img_path

    groups = {}
    selected_all: list[int] = []
    for group, indices in sorted(group_to_indices.items()):
        picked = random.sample(indices, k=min(args.per_group, len(indices)))
        picked.sort()
        selected_all.extend(picked)
        groups[group] = {
            "available": len(indices),
            "selected_count": len(picked),
            "selected_indices": picked,
            "examples": [index_to_path[i] for i in picked[:3]],
        }

    selected_all = sorted(set(selected_all))
    payload = {
        "split": args.split,
        "group_by": args.group_by,
        "per_group": args.per_group,
        "seed": args.seed,
        "selected_total": len(selected_all),
        "groups": groups,
        # edit this list manually if you want custom human selection
        "indices": selected_all,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Saved sample plan: {out_path.resolve()}")
    print(f"Selected total: {len(selected_all)}")


if __name__ == "__main__":
    main()

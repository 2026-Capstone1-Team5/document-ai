import argparse
import json
import os
import random
from collections import defaultdict
from pathlib import Path

from datasets import Image, load_dataset
from huggingface_hub import hf_hub_download


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def benchmark_assets_root() -> Path:
    root = repo_root_from_script() / "benchmark_assets"
    root.mkdir(parents=True, exist_ok=True)
    return root


def configure_local_hf_cache() -> None:
    assets = benchmark_assets_root()
    hf_home = assets / "hf_home"
    hub_cache = hf_home / "hub"
    datasets_cache = hf_home / "datasets"
    for p in [hf_home, hub_cache, datasets_cache]:
        p.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(hf_home))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hub_cache))
    os.environ.setdefault("HF_DATASETS_CACHE", str(datasets_cache))


def load_gt_attr_map(group_by: str) -> dict[str, str]:
    gt_path = Path(
        hf_hub_download(
            repo_id="opendatalab/OmniDocBench",
            repo_type="dataset",
            filename="OmniDocBench.json",
            local_dir=str(benchmark_assets_root() / "omnidocbench_hf"),
        )
    )
    rows = json.loads(gt_path.read_text())
    out: dict[str, str] = {}
    for row in rows:
        page_info = row.get("page_info", {})
        img_path = page_info.get("image_path", "")
        basename = Path(img_path).name
        attrs = page_info.get("page_attribute", {}) or {}
        value = attrs.get(group_by, "unknown")
        if value in (None, ""):
            value = "unknown"
        out[basename] = str(value)
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
        default="data_source",
        choices=["data_source", "language", "layout"],
    )
    parser.add_argument("--per-group", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        default="output/benchmark_reports/omnidocbench_sample_plan.json",
    )
    args = parser.parse_args()

    random.seed(args.seed)
    attr_map = load_gt_attr_map(args.group_by)

    raw = load_dataset("opendatalab/OmniDocBench", split=args.split, streaming=True)
    raw = raw.cast_column("image", Image(decode=False))

    group_to_indices: dict[str, list[int]] = defaultdict(list)
    index_to_path: dict[int, str] = {}
    for idx, row in enumerate(raw):
        img_path = row.get("image", {}).get("path", "")
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

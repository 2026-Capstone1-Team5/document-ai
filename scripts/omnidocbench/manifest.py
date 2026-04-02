import json
import os
from pathlib import Path

from huggingface_hub import hf_hub_download


OMNIDOCBENCH_DATASET_REPO_ID = "opendatalab/OmniDocBench"
OMNIDOCBENCH_DATASET_REVISION = os.environ.get(
    "OMNIDOCBENCH_DATASET_REVISION",
    "91fe284bbfacfa687959ae3eb00846ca852aa907",
)
OMNIDOCBENCH_DATASET_SOURCE = f"hf://datasets/{OMNIDOCBENCH_DATASET_REPO_ID}"


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


def dataset_source_ref() -> str:
    return f"{OMNIDOCBENCH_DATASET_SOURCE}@{OMNIDOCBENCH_DATASET_REVISION}"


def load_gt_rows() -> list[dict]:
    gt_path = Path(
        hf_hub_download(
            repo_id=OMNIDOCBENCH_DATASET_REPO_ID,
            repo_type="dataset",
            revision=OMNIDOCBENCH_DATASET_REVISION,
            filename="OmniDocBench.json",
            local_dir=str(benchmark_assets_root() / "omnidocbench_hf"),
        )
    )
    return json.loads(gt_path.read_text())


def official_image_path(row: dict) -> str:
    return str(row.get("page_info", {}).get("image_path", "") or "")


def repo_image_candidates(image_path: str) -> list[str]:
    normalized = image_path.replace("\\", "/").strip()
    if not normalized:
        return []
    basename = Path(normalized).name
    candidates: list[str] = []
    if "/" not in normalized:
        candidates.append(f"images/{basename}")
    candidates.append(normalized)
    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def make_source_image_ref(repo_image_path: str) -> str:
    normalized = repo_image_path.replace("\\", "/").lstrip("/")
    return f"{dataset_source_ref()}/{normalized}"


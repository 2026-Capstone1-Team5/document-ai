import argparse
import json
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from difflib import SequenceMatcher
from json import JSONDecodeError

from PIL import Image
from huggingface_hub import hf_hub_download

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from manifest import (
    OMNIDOCBENCH_DATASET_REPO_ID,
    OMNIDOCBENCH_DATASET_REVISION,
    OMNIDOCBENCH_DATASET_SOURCE,
    benchmark_assets_root,
    configure_local_hf_cache,
    load_gt_rows,
    make_source_image_ref,
    official_image_path as gt_official_image_path,
    repo_image_candidates,
    repo_root_from_script,
)


load_dataset = None  # legacy compatibility for older tests/patches


MODE_FLAGS = {
    "auto": [],
    "normal": ["--force-normal"],
    "rasterized": ["--force-rasterize"],
    "page_adaptive": ["--page-adaptive"],
}


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    sorted_vals = sorted(values)
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (len(sorted_vals) - 1) * p
    low = int(rank)
    high = min(low + 1, len(sorted_vals) - 1)
    weight = rank - low
    return sorted_vals[low] * (1 - weight) + sorted_vals[high] * weight


def normalize_text(s: str) -> str:
    return " ".join((s or "").lower().split())


def levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def build_gt_text(row: dict) -> str:
    dets = row.get("layout_dets", [])
    ordered = sorted(
        [d for d in dets if d.get("text")],
        key=lambda d: (
            d.get("order") is None,
            d.get("order") if isinstance(d.get("order"), int) else 10**9,
        ),
    )
    return "\n".join(str(d.get("text", "")).strip() for d in ordered if d.get("text"))


def resolve_gt_repo_image_path(row: dict) -> str:
    image_path = gt_official_image_path(row)
    candidates = repo_image_candidates(image_path)
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            hf_hub_download(
                repo_id=OMNIDOCBENCH_DATASET_REPO_ID,
                repo_type="dataset",
                revision=OMNIDOCBENCH_DATASET_REVISION,
                filename=candidate,
                local_dir=str(benchmark_assets_root() / "omnidocbench_hf"),
            )
            return candidate
        except Exception as exc:  # pragma: no cover - networked fallback
            last_error = exc
            continue
    raise FileNotFoundError(
        f"Unable to resolve dataset image for GT path={image_path!r}"
    ) from last_error


def load_manifest_image(repo_image_path: str) -> Image.Image:
    local_path = hf_hub_download(
        repo_id=OMNIDOCBENCH_DATASET_REPO_ID,
        repo_type="dataset",
        revision=OMNIDOCBENCH_DATASET_REVISION,
        filename=repo_image_path,
        local_dir=str(benchmark_assets_root() / "omnidocbench_hf"),
    )
    return Image.open(local_path)


def resolve_markdown_output(meta: dict) -> tuple[Path | None, str | None]:
    outputs = meta.get("outputs", {})
    for key in ("selected_markdown", "markdown"):
        raw_path = outputs.get(key)
        if not raw_path:
            continue
        path = Path(raw_path)
        if path.exists():
            return path, key
    for key in ("selected_markdown", "markdown"):
        raw_path = outputs.get(key)
        if raw_path:
            return Path(raw_path), key
    return None, None


def parse_one_sample(
    sample: dict,
    sample_ref_path: str | None,
    gt_text: str | None,
    index: int,
    run_root: Path,
    language: str,
    timeout_seconds: int,
    requested_mode: str = "auto",
    official_image_path: str | None = None,
    repo_image_path: str | None = None,
) -> dict:
    sample_name = f"{index:05d}"
    sample_dir = run_root / sample_name
    sample_dir.mkdir(parents=True, exist_ok=True)

    image = sample["image"]
    image_path = sample_dir / "input.png"
    pdf_path = sample_dir / "input.pdf"
    image.save(image_path)
    image.convert("RGB").save(pdf_path, "PDF")

    parse_output_dir = sample_dir / "parse_output"
    parse_script = repo_root_from_script() / "scripts" / "parse_document.py"
    cmd = [
        sys.executable,
        str(parse_script),
        str(pdf_path),
        str(parse_output_dir),
        "--language",
        language,
        *MODE_FLAGS[requested_mode],
    ]

    start = time.perf_counter()
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        elapsed = time.perf_counter() - start
    except subprocess.TimeoutExpired:
        return {
            "index": index,
            "sample_name": sample_name,
            "status": "failed",
            "failure_reason": "timeout",
            "elapsed_seconds": timeout_seconds,
            "returncode": None,
            "requested_mode": requested_mode,
            "parse_mode": None,
            "markdown_chars": None,
            "meta_path": None,
        }

    meta_path = parse_output_dir / "meta.json"
    parse_mode = None
    markdown_chars = None
    markdown_similarity = None
    markdown_cer = None
    markdown_path = None
    markdown_output_key = None
    failure_reason = None
    has_markdown_output = False

    if completed.returncode == 0 and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, JSONDecodeError):
            status = "failed"
            failure_reason = "invalid_meta_json"
        else:
            parse_mode = meta.get("parse_mode")
            md_path, markdown_output_key = resolve_markdown_output(meta)
            markdown_path = str(md_path) if md_path else None
            if md_path and md_path.exists():
                has_markdown_output = True
                pred_text = md_path.read_text(errors="ignore")
                markdown_chars = len(pred_text)
                if gt_text:
                    gt_norm = normalize_text(gt_text)
                    pred_norm = normalize_text(pred_text)
                    markdown_similarity = SequenceMatcher(
                        None, gt_norm, pred_norm
                    ).ratio()
                    markdown_cer = levenshtein_distance(gt_norm, pred_norm) / max(
                        1, len(gt_norm)
                    )
            status = "succeeded"
    else:
        status = "failed"
        stderr = (completed.stderr or "").strip().splitlines()
        stdout = (completed.stdout or "").strip().splitlines()
        last_line = stderr[-1] if stderr else (stdout[-1] if stdout else "")
        failure_reason = last_line[:400] if last_line else "unknown_error"

    return {
        "index": index,
        "sample_name": sample_name,
        "source_image_ref": sample_ref_path,
        "official_image_path": official_image_path,
        "repo_image_path": repo_image_path,
        "status": status,
        "failure_reason": failure_reason,
        "elapsed_seconds": round(elapsed, 3),
        "returncode": completed.returncode,
        "requested_mode": requested_mode,
        "parse_mode": parse_mode,
        "markdown_path": markdown_path,
        "markdown_output_key": markdown_output_key,
        "has_markdown_output": has_markdown_output,
        "markdown_chars": markdown_chars,
        "markdown_similarity": markdown_similarity,
        "markdown_cer": markdown_cer,
        "has_gt": bool(gt_text),
        "meta_path": str(meta_path) if meta_path.exists() else None,
    }


def summarize(results: list[dict]) -> dict:
    total = len(results)
    succeeded = [r for r in results if r["status"] == "succeeded"]
    failed = [r for r in results if r["status"] == "failed"]
    markdown_available = [r for r in results if r.get("has_markdown_output")]
    gt_covered = [r for r in results if r.get("has_gt")]
    diagnostic_metric_rows = [
        r
        for r in results
        if r.get("has_gt")
        and r.get("has_markdown_output")
        and r.get("status") == "succeeded"
    ]

    times_all = [r["elapsed_seconds"] for r in results]
    times_success = [r["elapsed_seconds"] for r in succeeded]
    markdown_chars = [
        r["markdown_chars"] for r in succeeded if r["markdown_chars"] is not None
    ]
    markdown_similarity = [
        r["markdown_similarity"]
        for r in succeeded
        if r["markdown_similarity"] is not None
    ]
    markdown_cer = [
        r["markdown_cer"] for r in succeeded if r["markdown_cer"] is not None
    ]
    mode_counter = Counter(r["parse_mode"] for r in succeeded if r["parse_mode"])
    fail_counter = Counter(r["failure_reason"] for r in failed if r["failure_reason"])
    markdown_key_counter = Counter(
        r["markdown_output_key"]
        for r in markdown_available
        if r.get("markdown_output_key")
    )

    return {
        "total_samples": total,
        "attempted_pages": total,
        "succeeded_samples": len(succeeded),
        "parse_succeeded_pages": len(succeeded),
        "failed_samples": len(failed),
        "parse_failed_pages": len(failed),
        "success_rate": (len(succeeded) / total) if total else 0.0,
        "markdown_available_pages": len(markdown_available),
        "markdown_available_ratio": (len(markdown_available) / total) if total else 0.0,
        "elapsed_seconds_avg_all": (statistics.fmean(times_all) if times_all else None),
        "elapsed_seconds_avg_success": (
            statistics.fmean(times_success) if times_success else None
        ),
        "elapsed_seconds_median_success": (
            statistics.median(times_success) if times_success else None
        ),
        "elapsed_seconds_p95_success": percentile(times_success, 0.95),
        "parse_mode_distribution": dict(mode_counter),
        "markdown_output_key_distribution": dict(markdown_key_counter),
        "failure_reasons": dict(fail_counter),
        "markdown_chars_avg_success": (
            statistics.fmean(markdown_chars) if markdown_chars else None
        ),
        "gt_covered_pages": len(gt_covered),
        "gt_coverage_ratio": (len(gt_covered) / total) if total else 0.0,
        "diagnostic_metric_pages": len(diagnostic_metric_rows),
        "diagnostic_metric_ratio": (len(diagnostic_metric_rows) / total)
        if total
        else 0.0,
        "markdown_similarity_avg_success": (
            statistics.fmean(markdown_similarity) if markdown_similarity else None
        ),
        "markdown_cer_avg_success": (
            statistics.fmean(markdown_cer) if markdown_cer else None
        ),
    }


def write_report_artifacts(
    report: dict,
    results_path: Path,
    report_dir: str,
) -> tuple[Path, Path, Path]:
    results_path.write_text(json.dumps(report, indent=2))

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d-%H-%M-%S")
    run_id = (
        f"omnidocbench_limit{report['limit']}_offset{report['offset']}_{timestamp}"
    )

    managed_dir = Path(report_dir).resolve()
    managed_dir.mkdir(parents=True, exist_ok=True)

    managed_summary = {
        "run_id": run_id,
        "created_at_utc": now.isoformat(),
        "dataset": report["dataset"],
        "limit": report["limit"],
        "offset": report["offset"],
        "language": report["language"],
        "requested_mode": report.get("requested_mode"),
        "dataset_revision": report.get("dataset_revision"),
        "dataset_source": report.get("dataset_source"),
        "run_root": report["run_root"],
        "summary": report["summary"],
        "source_results_json": str(results_path.resolve()),
    }

    managed_summary_path = managed_dir / f"{timestamp}.json"
    managed_summary_path.write_text(json.dumps(managed_summary, indent=2))

    latest_path = managed_dir / "latest_omnidocbench_summary.json"
    latest_path.write_text(json.dumps(managed_summary, indent=2))

    registry_path = managed_dir / "registry_omnidocbench.json"
    if registry_path.exists():
        registry = json.loads(registry_path.read_text())
    else:
        registry = {"runs": []}

    registry["runs"].append(
        {
            "run_id": run_id,
            "created_at_utc": managed_summary["created_at_utc"],
            "dataset": managed_summary["dataset"],
            "limit": managed_summary["limit"],
            "offset": managed_summary["offset"],
            "requested_mode": managed_summary.get("requested_mode"),
            "success_rate": managed_summary["summary"].get("success_rate"),
            "avg_seconds": managed_summary["summary"].get(
                "elapsed_seconds_avg_success"
            ),
            "source_results_json": managed_summary["source_results_json"],
            "summary_json": str(managed_summary_path.resolve()),
        }
    )
    registry_path.write_text(json.dumps(registry, indent=2))

    return managed_summary_path, latest_path, registry_path


def main() -> None:
    configure_local_hf_cache()
    parser = argparse.ArgumentParser(
        description="Benchmark parser on OmniDocBench samples."
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--language", default="en")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--mode",
        default="auto",
        choices=sorted(MODE_FLAGS),
        help="Parser variant to benchmark: auto, normal, rasterized, page_adaptive.",
    )
    parser.add_argument(
        "--run-root",
        default="output/omnidocbench_benchmark",
        help="Directory for per-sample inputs/outputs and raw results.json.",
    )
    parser.add_argument(
        "--report-dir",
        default="output/benchmark_reports",
        help="Directory for managed benchmark summaries and registry.",
    )
    parser.add_argument(
        "--indices-file",
        default=None,
        help=(
            "Optional JSON file for explicit sample indices. "
            "Accepts either [1,2,3] or {'indices':[1,2,3]}."
        ),
    )
    args = parser.parse_args()

    run_root = Path(args.run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    results_path = run_root / "results.json"

    explicit_indices: list[int] | None = None
    if args.indices_file:
        payload = json.loads(Path(args.indices_file).read_text())
        if isinstance(payload, dict):
            payload_indices = payload.get("indices", [])
            explicit_indices = (
                list(payload_indices) if payload_indices is not None else []
            )
        else:
            explicit_indices = list(payload)
        explicit_indices = sorted({int(x) for x in explicit_indices})
        if not explicit_indices:
            raise ValueError(f"No indices found in {args.indices_file}")

    if explicit_indices is None and args.limit <= 0:
        summary = summarize([])
        report = {
            "dataset": "opendatalab/OmniDocBench",
            "limit": 0,
            "offset": args.offset,
            "language": args.language,
            "requested_mode": args.mode,
            "run_root": str(run_root),
            "indices_file": args.indices_file,
            "explicit_indices_count": None,
            "summary": summary,
            "results": [],
        }
        managed_summary_path, latest_path, registry_path = write_report_artifacts(
            report=report,
            results_path=results_path,
            report_dir=args.report_dir,
        )
        print("\n=== Benchmark Summary ===")
        print(json.dumps(summary, indent=2))
        print(f"\nSaved report: {results_path}")
        print(f"Managed summary: {managed_summary_path}")
        print(f"Managed latest:  {latest_path}")
        print(f"Managed registry:{registry_path}")
        return

    rows = load_gt_rows()

    results: list[dict] = []
    if explicit_indices is not None:
        max_index = len(rows) - 1
        missing_indices = [idx for idx in explicit_indices if idx < 0 or idx > max_index]
        if missing_indices:
            raise ValueError(
                f"Missing requested indices from {args.indices_file}: {missing_indices}"
            )
        selected_indices = explicit_indices
    else:
        wanted_end = min(args.offset + args.limit, len(rows))
        selected_indices = list(range(args.offset, wanted_end))

    wanted_total = len(selected_indices)
    for selected_count, idx in enumerate(selected_indices, start=1):
        row = rows[idx]
        official_image_path = gt_official_image_path(row)
        repo_image_path = resolve_gt_repo_image_path(row)
        gt_text = build_gt_text(row)
        sample_ref_path = make_source_image_ref(repo_image_path)
        image = load_manifest_image(repo_image_path)
        print(f"[{selected_count}/{wanted_total}] parsing sample index={idx}")
        result = parse_one_sample(
            sample={"image": image},
            sample_ref_path=sample_ref_path,
            gt_text=gt_text,
            index=idx,
            run_root=run_root,
            language=args.language,
            timeout_seconds=args.timeout_seconds,
            requested_mode=args.mode,
            official_image_path=official_image_path,
            repo_image_path=repo_image_path,
        )
        results.append(result)
        print(
            f"  -> status={result['status']} elapsed={result['elapsed_seconds']}s "
            f"mode={result['parse_mode']} sim={result['markdown_similarity']} "
            f"cer={result['markdown_cer']} reason={result['failure_reason']}"
        )
    summary = summarize(results)
    report = {
        "dataset": OMNIDOCBENCH_DATASET_REPO_ID,
        "dataset_source": OMNIDOCBENCH_DATASET_SOURCE,
        "dataset_revision": OMNIDOCBENCH_DATASET_REVISION,
        "limit": wanted_total,
        "offset": args.offset,
        "language": args.language,
        "requested_mode": args.mode,
        "run_root": str(run_root),
        "indices_file": args.indices_file,
        "explicit_indices_count": len(explicit_indices) if explicit_indices else None,
        "summary": summary,
        "results": results,
    }
    managed_summary_path, latest_path, registry_path = write_report_artifacts(
        report=report,
        results_path=results_path,
        report_dir=args.report_dir,
    )

    print("\n=== Benchmark Summary ===")
    print(json.dumps(summary, indent=2))
    print(f"\nSaved report: {results_path}")
    print(f"Managed summary: {managed_summary_path}")
    print(f"Managed latest:  {latest_path}")
    print(f"Managed registry:{registry_path}")


if __name__ == "__main__":
    main()

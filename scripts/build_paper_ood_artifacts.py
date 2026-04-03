#!/usr/bin/env python3

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


SEVERE_REGRESSION_THRESHOLD = -0.10


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def variant_rows(scored_payload: dict[str, Any], rows: list[str]) -> list[dict[str, Any]]:
    summary = scored_payload.get("variant_summary", {})
    return [
        {
            "row": row,
            **summary.get(row, {"n": 0, "mean_primary_score": None, "median_primary_score": None}),
        }
        for row in rows
    ]


def severe_regression_summary(scored_payload: dict[str, Any], variant: str) -> dict[str, Any]:
    deltas = [
        row.get(f"{variant}_vs_original")
        for row in scored_payload.get("doc_comparisons", [])
        if row.get(f"{variant}_vs_original") is not None
    ]
    severe = [delta for delta in deltas if delta <= SEVERE_REGRESSION_THRESHOLD]
    return {
        "variant": variant,
        "n": len(deltas),
        "severe_regression_threshold": SEVERE_REGRESSION_THRESHOLD,
        "severe_regression_count": len(severe),
        "severe_regression_rate": len(severe) / len(deltas) if deltas else None,
        "median_delta_vs_original": statistics.median(deltas) if deltas else None,
    }


def build_best_variant_summary(scored_payload: dict[str, Any]) -> dict[str, Any]:
    rows = scored_payload.get("doc_comparisons", [])
    best_counts: dict[str, int] = {}
    auto_regrets = [row.get("auto_regret") for row in rows if row.get("auto_regret") is not None]
    for row in rows:
        best_variant = row.get("best_variant")
        if not best_variant:
            continue
        best_counts[best_variant] = best_counts.get(best_variant, 0) + 1
    return {
        "best_variant_distribution": best_counts,
        "auto_best_rate": (
            best_counts.get("auto", 0) / len(rows) if rows else None
        ),
        "auto_regret_mean": statistics.fmean(auto_regrets) if auto_regrets else None,
        "auto_regret_median": statistics.median(auto_regrets) if auto_regrets else None,
    }


def build_main_table(scored_payload: dict[str, Any]) -> dict[str, Any]:
    pairwise = scored_payload.get("pairwise_summary", {})
    return {
        "rows": variant_rows(scored_payload, ["original", "rasterized", "auto"]),
        "pairwise": {
            key: pairwise.get(key)
            for key in [
                "auto_vs_original",
                "rasterized_vs_original",
                "auto_vs_rasterized",
            ]
            if key in pairwise
        },
        "best_variant": build_best_variant_summary(scored_payload),
    }


def build_control_table(scored_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "rows": variant_rows(scored_payload, ["original", "rasterized", "auto"]),
        "severe_regression": [
            severe_regression_summary(scored_payload, "rasterized"),
            severe_regression_summary(scored_payload, "auto"),
        ],
    }


def build_causal_table(scored_payload: dict[str, Any]) -> dict[str, Any]:
    pairwise = scored_payload.get("pairwise_summary", {})
    causal_keys = [
        "text_layer_stripped_vs_original",
        "rasterized_vs_text_layer_stripped",
        "auto_vs_text_layer_stripped",
        "auto_vs_original",
    ]
    return {
        "rows": variant_rows(
            scored_payload,
            ["original", "text_layer_stripped", "rasterized", "auto"],
        ),
        "pairwise": {key: pairwise.get(key) for key in causal_keys if key in pairwise},
    }


def build_methods_note(
    *,
    main_payload: dict[str, Any],
    control_payload: dict[str, Any] | None,
    causal_payload: dict[str, Any] | None,
    anchor_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "main_manifest": main_payload.get("manifest"),
        "main_run_root": main_payload.get("run_root"),
        "main_pairwise_keys": sorted(main_payload.get("pairwise_summary", {}).keys()),
        "control_manifest": control_payload.get("manifest") if control_payload else None,
        "causal_manifest": causal_payload.get("manifest") if causal_payload else None,
        "anchor_summary": anchor_payload,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build paper-facing OOD benchmark artifacts from scored benchmark outputs."
    )
    parser.add_argument("--main-scored-json", required=True)
    parser.add_argument("--control-scored-json", default=None)
    parser.add_argument("--causal-scored-json", default=None)
    parser.add_argument("--anchor-summary-json", default=None)
    parser.add_argument("--output-main-table", required=True)
    parser.add_argument("--output-control-table", default=None)
    parser.add_argument("--output-causal-table", default=None)
    parser.add_argument("--output-methods-note", required=True)
    args = parser.parse_args()

    main_payload = load_json(Path(args.main_scored_json).resolve())
    control_payload = (
        load_json(Path(args.control_scored_json).resolve())
        if args.control_scored_json
        else None
    )
    causal_payload = (
        load_json(Path(args.causal_scored_json).resolve())
        if args.causal_scored_json
        else None
    )
    anchor_payload = (
        load_json(Path(args.anchor_summary_json).resolve())
        if args.anchor_summary_json
        else None
    )

    write_json(Path(args.output_main_table).resolve(), build_main_table(main_payload))
    if args.output_control_table and control_payload:
        write_json(
            Path(args.output_control_table).resolve(),
            build_control_table(control_payload),
        )
    if args.output_causal_table and causal_payload:
        write_json(
            Path(args.output_causal_table).resolve(),
            build_causal_table(causal_payload),
        )
    write_json(
        Path(args.output_methods_note).resolve(),
        build_methods_note(
            main_payload=main_payload,
            control_payload=control_payload,
            causal_payload=causal_payload,
            anchor_payload=anchor_payload,
        ),
    )


if __name__ == "__main__":
    main()

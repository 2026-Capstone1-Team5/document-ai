#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from typing import Any


OOD_SUBGROUPS = {"receipt", "invoice", "ocr_form", "mixed_layout", "ticket", "brochure"}
MAIN_VARIANTS = ["original", "rasterized", "auto"]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def variant_rows(scored_payload: dict[str, Any], variants: list[str]) -> list[dict[str, Any]]:
    summary = scored_payload.get("variant_summary", {})
    return [
        {
            "variant": variant,
            **summary.get(
                variant,
                {
                    "n": 0,
                    "mean_primary_score": None,
                    "median_primary_score": None,
                    "mean_auxiliary_metrics": {},
                },
            ),
        }
        for variant in variants
    ]


def _format_score(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, (int, float)):
        return f"{value:.3f}"
    return str(value)


def _mitigation_improves(original: dict[str, Any], candidate: dict[str, Any]) -> bool:
    original_score = original.get("primary_score")
    candidate_score = candidate.get("primary_score")
    original_cer = original.get("auxiliary_metrics", {}).get("cer")
    candidate_cer = candidate.get("auxiliary_metrics", {}).get("cer")
    if None in {original_score, candidate_score, original_cer, candidate_cer}:
        return False
    return candidate_score > original_score and candidate_cer < original_cer


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Paper Claim Evidence",
        "",
        f"- claim_mode: `{payload['claim_mode']}`",
        f"- recommended_wording: {payload['recommended_wording']}",
        "",
        "## Main OOD quantitative rows",
        "",
        "| variant | n | mean_primary_score | mean_token_f1 | mean_cer | mean_wer | mean_ned |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload.get("quantitative_rows", []):
        aux = row.get("mean_auxiliary_metrics", {}) or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("variant")),
                    str(row.get("n", 0)),
                    _format_score(row.get("mean_primary_score")),
                    _format_score(aux.get("token_f1")),
                    _format_score(aux.get("cer")),
                    _format_score(aux.get("wer")),
                    _format_score(aux.get("ned")),
                ]
            )
            + " |"
        )

    control_rows = payload.get("control_quantitative_rows") or []
    if control_rows:
        lines.extend(
            [
                "",
                "## Structured control quantitative rows",
                "",
                "| variant | n | mean_primary_score | mean_token_f1 | mean_cer | mean_wer | mean_ned |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in control_rows:
            aux = row.get("mean_auxiliary_metrics", {}) or {}
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("variant")),
                        str(row.get("n", 0)),
                        _format_score(row.get("mean_primary_score")),
                        _format_score(aux.get("token_f1")),
                        _format_score(aux.get("cer")),
                        _format_score(aux.get("wer")),
                        _format_score(aux.get("ned")),
                    ]
                )
                + " |"
            )

    direct_rows = payload.get("direct_txt_observations_on_ood_docs") or []
    lines.extend(["", "## Direct classify() observations on OOD docs", ""])
    if direct_rows:
        lines.append("| doc_id | subgroup | classify_accepts_text | supports_claim | avg_chars | invalid_ratio | image_ratio | original_score | rasterized_score | auto_score | original_cer | rasterized_cer | auto_cer |")
        lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for row in direct_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("doc_id")),
                        str(row.get("subgroup")),
                        str(row.get("classifier_signal_accepts_text_path")),
                        str(row.get("supports_direct_failure_observation")),
                        _format_score(row.get("avg_cleaned_chars_per_page")),
                        _format_score(row.get("invalid_char_ratio")),
                        _format_score(row.get("high_image_coverage_ratio")),
                        _format_score(row.get("original_primary_score")),
                        _format_score(row.get("rasterized_primary_score")),
                        _format_score(row.get("auto_primary_score")),
                        _format_score(row.get("original_cer")),
                        _format_score(row.get("rasterized_cer")),
                        _format_score(row.get("auto_cer")),
                    ]
                )
                + " |"
            )
    else:
        lines.append(
            "No receipt/invoice-style OOD document in the current probe set was directly observed as `classify() = txt`."
        )

    lines.extend(
        [
            "",
            "## Pairwise summary",
            "",
            "```json",
            json.dumps(payload.get("pairwise_summary", {}), indent=2, ensure_ascii=False),
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def build_claim_evidence(
    *,
    routing_payload: dict[str, Any],
    scored_payload: dict[str, Any],
    control_scored_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    receipt_like_txt_rows = []
    supporting_rows = []
    for row in routing_payload.get("rows", []):
        subgroup = str(row.get("subgroup") or "unknown")
        classify_result = row.get("observation", {}).get("classify_result")
        if subgroup in OOD_SUBGROUPS and classify_result == "txt":
            scored = row.get("scored") or {}
            scores = scored.get("scores", {})
            original = scores.get("original", {})
            rasterized = scores.get("rasterized", {})
            auto = scores.get("auto", {})
            rendered_row = {
                "doc_id": row.get("doc_id"),
                "subgroup": subgroup,
                "source_bucket": row.get("source_bucket"),
                "avg_cleaned_chars_per_page": row.get("observation", {}).get("avg_cleaned_chars_per_page"),
                "invalid_char_ratio": row.get("observation", {}).get("invalid_char_ratio"),
                "cid_char_ratio": row.get("observation", {}).get("cid_char_ratio"),
                "high_image_coverage_ratio": row.get("observation", {}).get("high_image_coverage_ratio"),
                "classifier_signal_accepts_text_path": row.get("observation", {}).get("classifier_signal_accepts_text_path"),
                "original_primary_score": original.get("primary_score"),
                "rasterized_primary_score": rasterized.get("primary_score"),
                "auto_primary_score": auto.get("primary_score"),
                "original_cer": original.get("auxiliary_metrics", {}).get("cer"),
                "rasterized_cer": rasterized.get("auxiliary_metrics", {}).get("cer"),
                "auto_cer": auto.get("auxiliary_metrics", {}).get("cer"),
            }
            supports_direct_failure_observation = bool(
                rendered_row["classifier_signal_accepts_text_path"]
                and (
                    _mitigation_improves(original, rasterized)
                    or _mitigation_improves(original, auto)
                )
            )
            rendered_row["supports_direct_failure_observation"] = supports_direct_failure_observation
            receipt_like_txt_rows.append(rendered_row)
            if supports_direct_failure_observation:
                supporting_rows.append(rendered_row)

    pairwise_summary = scored_payload.get("pairwise_summary", {})
    rasterized_vs_original = pairwise_summary.get("rasterized_vs_original", {})
    claim_mode = "conservative_inference_only"
    if supporting_rows and (rasterized_vs_original.get("mean_delta") or 0) > 0:
        claim_mode = "controlled_classifier_unreliability_supported"
    return {
        "claim_mode": claim_mode,
        "direct_txt_observations_on_ood_docs": receipt_like_txt_rows,
        "supporting_direct_observations_on_ood_docs": supporting_rows,
        "routing_summary": routing_payload.get("summary"),
        "quantitative_rows": variant_rows(scored_payload, MAIN_VARIANTS),
        "control_quantitative_rows": (
            variant_rows(control_scored_payload, MAIN_VARIANTS) if control_scored_payload else []
        ),
        "pairwise_summary": pairwise_summary,
        "recommended_wording": (
            "The controlled dataset supports a narrow claim: under harmful-text-layer conditions, classify() can choose the text path while MinerU's own thresholds look acceptable and rasterization mitigates the aggregate failure."
            if claim_mode == "controlled_classifier_unreliability_supported"
            else "No direct controlled-support bundle was found for the current OOD probes; use conservative wording about threshold limitations or distribution mismatch instead of a categorical routing-failure claim."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combine routing observations and scored benchmark outputs into paper-facing claim evidence."
    )
    parser.add_argument("--routing-json", required=True)
    parser.add_argument("--scored-json", required=True)
    parser.add_argument("--control-scored-json")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md")
    args = parser.parse_args()

    payload = build_claim_evidence(
        routing_payload=load_json(Path(args.routing_json).resolve()),
        scored_payload=load_json(Path(args.scored_json).resolve()),
        control_scored_payload=(
            load_json(Path(args.control_scored_json).resolve()) if args.control_scored_json else None
        ),
    )
    output_path = Path(args.output_json).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.output_md:
        md_path = Path(args.output_md).resolve()
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({"claim_mode": payload["claim_mode"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import argparse
import json
import random
import statistics
from collections import defaultdict
from math import comb
from pathlib import Path
from typing import Any


SUPPORTED_METRIC_FAMILIES = {"exact_match", "token_f1", "cer", "wer", "ned"}
ERROR_RATE_FAMILIES = {"cer", "wer", "ned"}
AUXILIARY_METRICS = ("token_f1", "cer", "wer", "ned")
COMPARISON_PAIRS = [
    ("auto", "original"),
    ("rasterized", "original"),
    ("auto", "rasterized"),
    ("text_layer_stripped", "original"),
    ("rasterized", "text_layer_stripped"),
    ("auto", "text_layer_stripped"),
]


def normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    return normalized.split() if normalized else []


def levenshtein_distance(seq_a: list[str] | str, seq_b: list[str] | str) -> int:
    if seq_a == seq_b:
        return 0
    if len(seq_a) == 0:
        return len(seq_b)
    if len(seq_b) == 0:
        return len(seq_a)

    previous = list(range(len(seq_b) + 1))
    for index_a, token_a in enumerate(seq_a, start=1):
        current = [index_a]
        for index_b, token_b in enumerate(seq_b, start=1):
            insert_cost = current[index_b - 1] + 1
            delete_cost = previous[index_b] + 1
            substitute_cost = previous[index_b - 1] + (0 if token_a == token_b else 1)
            current.append(min(insert_cost, delete_cost, substitute_cost))
        previous = current
    return previous[-1]


def char_error_rate(gold: str, pred: str) -> float:
    gold_norm = normalize_text(gold)
    pred_norm = normalize_text(pred)
    if not gold_norm:
        return 0.0 if not pred_norm else 1.0
    distance = levenshtein_distance(gold_norm, pred_norm)
    return distance / len(gold_norm)


def word_error_rate(gold: str, pred: str) -> float:
    gold_tokens = tokenize(gold)
    pred_tokens = tokenize(pred)
    if not gold_tokens:
        return 0.0 if not pred_tokens else 1.0
    distance = levenshtein_distance(gold_tokens, pred_tokens)
    return distance / len(gold_tokens)


def normalized_edit_distance(gold: str, pred: str) -> float:
    gold_norm = normalize_text(gold)
    pred_norm = normalize_text(pred)
    max_len = max(len(gold_norm), len(pred_norm))
    if max_len == 0:
        return 0.0
    distance = levenshtein_distance(gold_norm, pred_norm)
    return distance / max_len


def token_f1(gold: str, pred: str) -> float:
    gold_tokens = tokenize(gold)
    pred_tokens = tokenize(pred)
    if not gold_tokens and not pred_tokens:
        return 1.0
    if not gold_tokens or not pred_tokens:
        return 0.0
    gold_counts: dict[str, int] = defaultdict(int)
    pred_counts: dict[str, int] = defaultdict(int)
    for token in gold_tokens:
        gold_counts[token] += 1
    for token in pred_tokens:
        pred_counts[token] += 1
    overlap = sum(min(gold_counts[token], pred_counts[token]) for token in gold_counts)
    precision = overlap / len(pred_tokens)
    recall = overlap / len(gold_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_field_values(payload: Any) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        if "fields" in payload:
            return flatten_field_values(payload["fields"])
        for value in payload.values():
            values.extend(flatten_field_values(value))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(flatten_field_values(item))
    elif payload is not None:
        text = str(payload).strip()
        if text:
            values.append(text)
    return values


def load_gold_text(gold_path: Path, gold_format: str) -> str:
    if gold_format == "transcript_txt":
        return gold_path.read_text(encoding="utf-8")
    payload = load_json(gold_path)
    if gold_format == "transcript_json":
        if isinstance(payload, dict):
            if isinstance(payload.get("text"), str):
                return payload["text"]
            if isinstance(payload.get("pages"), list):
                return "\n".join(
                    str(page.get("text", "")) for page in payload["pages"] if isinstance(page, dict)
                )
        raise ValueError(f"Unsupported transcript_json payload shape: {gold_path}")
    if gold_format == "fields_json":
        return "\n".join(flatten_field_values(payload))
    raise ValueError(f"Unsupported gold_format: {gold_format}")


def field_exact_match(gold_path: Path, pred_text: str) -> float:
    payload = load_json(gold_path)
    values = [normalize_text(value) for value in flatten_field_values(payload) if normalize_text(value)]
    if not values:
        return 1.0
    pred_norm = normalize_text(pred_text)
    matches = sum(1 for value in values if value in pred_norm)
    return matches / len(values)


def compute_metric(
    *,
    gold_path: Path,
    gold_format: str,
    metric_family: str,
    pred_text: str,
) -> float:
    if metric_family not in SUPPORTED_METRIC_FAMILIES:
        raise ValueError(f"Unsupported metric_family: {metric_family}")
    if metric_family == "exact_match" and gold_format == "fields_json":
        return field_exact_match(gold_path, pred_text)

    gold_text = load_gold_text(gold_path, gold_format)
    if metric_family == "exact_match":
        return 1.0 if normalize_text(gold_text) == normalize_text(pred_text) else 0.0
    if metric_family == "token_f1":
        return token_f1(gold_text, pred_text)
    if metric_family == "cer":
        return char_error_rate(gold_text, pred_text)
    if metric_family == "wer":
        return word_error_rate(gold_text, pred_text)
    if metric_family == "ned":
        return normalized_edit_distance(gold_text, pred_text)
    raise AssertionError("unreachable")


def compute_auxiliary_metrics(
    *,
    gold_path: Path,
    gold_format: str,
    pred_text: str,
) -> dict[str, float]:
    gold_text = load_gold_text(gold_path, gold_format)
    return {
        "token_f1": token_f1(gold_text, pred_text),
        "cer": char_error_rate(gold_text, pred_text),
        "wer": word_error_rate(gold_text, pred_text),
        "ned": normalized_edit_distance(gold_text, pred_text),
    }


def metric_to_primary_score(metric_family: str, raw_metric: float) -> float:
    if metric_family in ERROR_RATE_FAMILIES:
        return max(0.0, 1.0 - min(1.0, raw_metric))
    return raw_metric


def bootstrap_confidence_interval(
    values: list[float],
    *,
    statistic: str,
    iterations: int = 1000,
    seed: int = 0,
) -> list[float] | None:
    if not values:
        return None
    if len(values) == 1:
        return [values[0], values[0]]
    rng = random.Random(seed)
    sampled_stats: list[float] = []
    for _ in range(iterations):
        sample = [values[rng.randrange(len(values))] for _ in range(len(values))]
        if statistic == "mean":
            sampled_stats.append(statistics.fmean(sample))
        elif statistic == "median":
            sampled_stats.append(statistics.median(sample))
        else:  # pragma: no cover - guarded by caller
            raise ValueError(f"Unsupported bootstrap statistic: {statistic}")
    sampled_stats.sort()
    lower_index = max(0, int(iterations * 0.025))
    upper_index = min(iterations - 1, int(iterations * 0.975))
    return [sampled_stats[lower_index], sampled_stats[upper_index]]


def sign_test_p_value(deltas: list[float]) -> float | None:
    non_zero = [delta for delta in deltas if delta != 0]
    trials = len(non_zero)
    if trials == 0:
        return None
    positives = sum(1 for delta in non_zero if delta > 0)
    tail = sum(comb(trials, k) for k in range(positives, trials + 1)) / (2**trials)
    return min(1.0, 2 * min(tail, 1 - tail + comb(trials, positives) / (2**trials)))


def summarize_pairwise_deltas(deltas: list[float]) -> dict[str, Any]:
    if not deltas:
        return {
            "n": 0,
            "mean_delta": None,
            "median_delta": None,
            "bootstrap_mean_ci95": None,
            "bootstrap_median_ci95": None,
            "positive_rate": None,
            "sign_test_p_value": None,
        }
    positives = sum(1 for delta in deltas if delta > 0)
    return {
        "n": len(deltas),
        "mean_delta": statistics.fmean(deltas),
        "median_delta": statistics.median(deltas),
        "bootstrap_mean_ci95": bootstrap_confidence_interval(deltas, statistic="mean"),
        "bootstrap_median_ci95": bootstrap_confidence_interval(
            deltas, statistic="median"
        ),
        "positive_rate": positives / len(deltas),
        "sign_test_p_value": sign_test_p_value(deltas),
    }


def load_prediction_text(markdown_path: str | None) -> str:
    if not markdown_path:
        return ""
    path = Path(markdown_path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def score_results_payload(results_payload: dict[str, Any]) -> dict[str, Any]:
    doc_scores: list[dict[str, Any]] = []
    variant_scores: dict[str, list[float]] = defaultdict(list)
    subgroup_variant_scores: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    auxiliary_variant_scores: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    subgroup_auxiliary_variant_scores: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    pairwise_deltas: dict[str, list[float]] = defaultdict(list)
    subgroup_pairwise_deltas: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    doc_comparisons: list[dict[str, Any]] = []

    for row in results_payload.get("results", []):
        gold = row.get("gold", {})
        gold_path = Path(str(gold.get("gold_path", ""))).resolve()
        gold_format = str(gold.get("gold_format", ""))
        metric_family = str(gold.get("metric_family", ""))
        doc_variant_scores: dict[str, float] = {}
        for variant, payload in row.get("variants", {}).items():
            entry = {
                "doc_id": row.get("doc_id"),
                "subgroup": row.get("subgroup"),
                "variant": variant,
                "status": payload.get("status"),
                "metric_family": metric_family,
                "gold_format": gold_format,
            }
            if payload.get("status") != "succeeded":
                entry["raw_metric"] = None
                entry["primary_score"] = None
                entry["failure_reason"] = payload.get("failure_reason")
                doc_scores.append(entry)
                continue
            pred_text = load_prediction_text(payload.get("markdown_path"))
            raw_metric = compute_metric(
                gold_path=gold_path,
                gold_format=gold_format,
                metric_family=metric_family,
                pred_text=pred_text,
            )
            primary_score = metric_to_primary_score(metric_family, raw_metric)
            auxiliary_metrics = compute_auxiliary_metrics(
                gold_path=gold_path,
                gold_format=gold_format,
                pred_text=pred_text,
            )
            entry["raw_metric"] = raw_metric
            entry["primary_score"] = primary_score
            entry["auxiliary_metrics"] = auxiliary_metrics
            doc_scores.append(entry)
            doc_variant_scores[variant] = primary_score
            variant_scores[variant].append(primary_score)
            subgroup_variant_scores[str(row.get("subgroup") or "unknown")][variant].append(
                primary_score
            )
            for metric_name, metric_value in auxiliary_metrics.items():
                auxiliary_variant_scores[variant][metric_name].append(metric_value)
                subgroup_auxiliary_variant_scores[str(row.get("subgroup") or "unknown")][variant][
                    metric_name
                ].append(metric_value)

        subgroup = str(row.get("subgroup") or "unknown")
        sorted_scores = sorted(
            doc_variant_scores.items(), key=lambda item: item[1], reverse=True
        )
        best_variant = sorted_scores[0][0] if sorted_scores else None
        best_score = sorted_scores[0][1] if sorted_scores else None
        auto_score = doc_variant_scores.get("auto")
        original_score = doc_variant_scores.get("original")
        rasterized_score = doc_variant_scores.get("rasterized")
        comparisons = {}
        for left, right in COMPARISON_PAIRS:
            left_score = doc_variant_scores.get(left)
            right_score = doc_variant_scores.get(right)
            comparisons[f"{left}_vs_{right}"] = (
                left_score - right_score
                if left_score is not None and right_score is not None
                else None
            )
        doc_comparisons.append(
            {
                "doc_id": row.get("doc_id"),
                "subgroup": subgroup,
                "variant_scores": doc_variant_scores,
                "best_variant": best_variant,
                "best_score": best_score,
                "auto_regret": (
                    best_score - auto_score
                    if best_score is not None and auto_score is not None
                    else None
                ),
                **comparisons,
            }
        )
        for comparison_name, delta in comparisons.items():
            if delta is None:
                continue
            pairwise_deltas[comparison_name].append(delta)
            subgroup_pairwise_deltas[subgroup][comparison_name].append(delta)

    variant_summary = {}
    for variant, scores in variant_scores.items():
        variant_summary[variant] = {
            "n": len(scores),
            "mean_primary_score": statistics.fmean(scores) if scores else None,
            "median_primary_score": statistics.median(scores) if scores else None,
            "mean_auxiliary_metrics": {
                metric_name: (
                    statistics.fmean(auxiliary_variant_scores[variant][metric_name])
                    if auxiliary_variant_scores[variant][metric_name]
                    else None
                )
                for metric_name in AUXILIARY_METRICS
            },
        }

    subgroup_summary = {}
    for subgroup, variant_map in subgroup_variant_scores.items():
        subgroup_summary[subgroup] = {}
        for variant, scores in variant_map.items():
            subgroup_summary[subgroup][variant] = {
                "n": len(scores),
                "mean_primary_score": statistics.fmean(scores) if scores else None,
                "median_primary_score": statistics.median(scores) if scores else None,
                "mean_auxiliary_metrics": {
                    metric_name: (
                        statistics.fmean(
                            subgroup_auxiliary_variant_scores[subgroup][variant][metric_name]
                        )
                        if subgroup_auxiliary_variant_scores[subgroup][variant][metric_name]
                        else None
                    )
                    for metric_name in AUXILIARY_METRICS
                },
            }

    pairwise_summary = {
        comparison: summarize_pairwise_deltas(deltas)
        for comparison, deltas in pairwise_deltas.items()
    }
    subgroup_pairwise_summary = {}
    for subgroup, comparison_map in subgroup_pairwise_deltas.items():
        subgroup_pairwise_summary[subgroup] = {
            comparison: summarize_pairwise_deltas(deltas)
            for comparison, deltas in comparison_map.items()
        }

    return {
        "manifest": results_payload.get("manifest"),
        "run_root": results_payload.get("run_root"),
        "variants": results_payload.get("variants"),
        "doc_scores": doc_scores,
        "doc_comparisons": doc_comparisons,
        "variant_summary": variant_summary,
        "subgroup_summary": subgroup_summary,
        "pairwise_summary": pairwise_summary,
        "subgroup_pairwise_summary": subgroup_pairwise_summary,
    }


def write_outputs(payload: dict[str, Any], output_json: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score paper OOD benchmark results against frozen gold artifacts and emit canonical primary scores."
    )
    parser.add_argument("--results-json", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    results_payload = load_json(Path(args.results_json).resolve())
    scored = score_results_payload(results_payload)
    write_outputs(scored, Path(args.output_json).resolve())
    print(json.dumps(scored["variant_summary"], indent=2))


if __name__ == "__main__":
    main()

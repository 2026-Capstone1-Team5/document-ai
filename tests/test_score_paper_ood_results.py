import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


score_paper_ood_results = load_module(
    "score_paper_ood_results", SCRIPT_DIR / "score_paper_ood_results.py"
)


class MetricTests(unittest.TestCase):
    def test_error_rate_metrics_convert_to_primary_score(self):
        self.assertAlmostEqual(
            score_paper_ood_results.metric_to_primary_score("cer", 0.25), 0.75
        )
        self.assertEqual(
            score_paper_ood_results.metric_to_primary_score("ned", 2.0), 0.0
        )

    def test_field_exact_match_uses_field_presence_ratio(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gold = Path(tmpdir) / "gold.json"
            gold.write_text(json.dumps({"fields": {"merchant": "Cafe", "amount": "$10"}}))
            score = score_paper_ood_results.compute_metric(
                gold_path=gold,
                gold_format="fields_json",
                metric_family="exact_match",
                pred_text="Cafe receipt total $10",
            )

        self.assertEqual(score, 1.0)

    def test_score_results_payload_builds_pairwise_deltas(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            gold = tmp_path / "gold.txt"
            gold.write_text("alpha beta")
            original_md = tmp_path / "original.md"
            original_md.write_text("alpha beta")
            rasterized_md = tmp_path / "rasterized.md"
            rasterized_md.write_text("alpha")
            auto_md = tmp_path / "auto.md"
            auto_md.write_text("alpha beta gamma")

            results_payload = {
                "manifest": "manifest.jsonl",
                "run_root": str(tmp_path / "run"),
                "variants": ["original", "rasterized", "auto"],
                "results": [
                    {
                        "doc_id": "doc-1",
                        "subgroup": "receipt",
                        "gold": {
                            "gold_path": str(gold),
                            "gold_format": "transcript_txt",
                            "metric_family": "token_f1",
                        },
                        "variants": {
                            "original": {"status": "succeeded", "markdown_path": str(original_md)},
                            "rasterized": {"status": "succeeded", "markdown_path": str(rasterized_md)},
                            "auto": {"status": "succeeded", "markdown_path": str(auto_md)},
                        },
                    }
                ],
            }

            scored = score_paper_ood_results.score_results_payload(results_payload)

        self.assertIn("doc_comparisons", scored)
        self.assertIn("pairwise_summary", scored)
        self.assertEqual(scored["doc_comparisons"][0]["best_variant"], "original")
        self.assertIsNotNone(scored["doc_comparisons"][0]["auto_vs_original"])
        self.assertEqual(scored["pairwise_summary"]["auto_vs_original"]["n"], 1)


if __name__ == "__main__":
    unittest.main()

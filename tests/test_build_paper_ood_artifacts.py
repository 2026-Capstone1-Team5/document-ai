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


build_paper_ood_artifacts = load_module(
    "build_paper_ood_artifacts", SCRIPT_DIR / "build_paper_ood_artifacts.py"
)


class ArtifactBuilderTests(unittest.TestCase):
    def make_scored_payload(self) -> dict:
        return {
            "manifest": "manifest.jsonl",
            "run_root": "output/run",
            "variant_summary": {
                "original": {"n": 2, "mean_primary_score": 0.8, "median_primary_score": 0.8},
                "rasterized": {"n": 2, "mean_primary_score": 0.75, "median_primary_score": 0.75},
                "auto": {"n": 2, "mean_primary_score": 0.85, "median_primary_score": 0.85},
                "text_layer_stripped": {"n": 1, "mean_primary_score": 0.82, "median_primary_score": 0.82},
            },
            "pairwise_summary": {
                "auto_vs_original": {"n": 2, "mean_delta": 0.05},
                "rasterized_vs_original": {"n": 2, "mean_delta": -0.05},
                "auto_vs_rasterized": {"n": 2, "mean_delta": 0.1},
                "text_layer_stripped_vs_original": {"n": 1, "mean_delta": 0.02},
                "rasterized_vs_text_layer_stripped": {"n": 1, "mean_delta": -0.07},
            },
            "doc_comparisons": [
                {
                    "best_variant": "auto",
                    "auto_regret": 0.0,
                    "rasterized_vs_original": -0.2,
                    "auto_vs_original": 0.1,
                },
                {
                    "best_variant": "original",
                    "auto_regret": 0.05,
                    "rasterized_vs_original": -0.05,
                    "auto_vs_original": 0.0,
                },
            ],
        }

    def test_build_main_table_keeps_core_rows_and_pairwise(self):
        payload = self.make_scored_payload()
        main_table = build_paper_ood_artifacts.build_main_table(payload)

        self.assertEqual([row["row"] for row in main_table["rows"]], ["original", "rasterized", "auto"])
        self.assertIn("auto_vs_original", main_table["pairwise"])
        self.assertEqual(main_table["best_variant"]["best_variant_distribution"]["auto"], 1)

    def test_build_control_table_tracks_severe_regressions(self):
        payload = self.make_scored_payload()
        control = build_paper_ood_artifacts.build_control_table(payload)

        rasterized = control["severe_regression"][0]
        self.assertEqual(rasterized["variant"], "rasterized")
        self.assertEqual(rasterized["severe_regression_count"], 1)

    def test_build_causal_table_uses_stripped_pairwise_entries(self):
        payload = self.make_scored_payload()
        causal = build_paper_ood_artifacts.build_causal_table(payload)

        self.assertEqual(causal["rows"][1]["row"], "text_layer_stripped")
        self.assertIn("text_layer_stripped_vs_original", causal["pairwise"])

    def test_write_json_creates_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "artifact.json"
            build_paper_ood_artifacts.write_json(path, {"ok": True})
            payload = json.loads(path.read_text())

        self.assertEqual(payload["ok"], True)


if __name__ == "__main__":
    unittest.main()

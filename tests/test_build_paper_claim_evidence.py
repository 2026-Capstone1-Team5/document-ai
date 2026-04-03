import importlib.util
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


builder = load_module(
    "build_paper_claim_evidence", SCRIPT_DIR / "build_paper_claim_evidence.py"
)


class BuildPaperClaimEvidenceTests(unittest.TestCase):
    def test_claim_mode_is_conservative_without_txt_ood_observation(self):
        payload = builder.build_claim_evidence(
            routing_payload={
                "summary": {"documents": 1},
                "rows": [
                    {
                        "doc_id": "receipt-1",
                        "subgroup": "receipt",
                        "observation": {"classify_result": "ocr"},
                    }
                ],
            },
            scored_payload={
                "variant_summary": {
                    "original": {"n": 1, "mean_primary_score": 0.5, "mean_auxiliary_metrics": {"cer": 0.4}},
                    "rasterized": {"n": 1, "mean_primary_score": 0.7, "mean_auxiliary_metrics": {"cer": 0.2}},
                    "auto": {"n": 1, "mean_primary_score": 0.7, "mean_auxiliary_metrics": {"cer": 0.2}},
                },
                "pairwise_summary": {},
            },
        )
        self.assertEqual(payload["claim_mode"], "conservative_inference_only")
        self.assertEqual(len(payload["quantitative_rows"]), 3)

    def test_claim_mode_flips_only_for_supported_controlled_observation(self):
        payload = builder.build_claim_evidence(
            routing_payload={
                "summary": {"documents": 1},
                "rows": [
                    {
                        "doc_id": "receipt-1",
                        "subgroup": "receipt",
                        "source_bucket": "local:receipt",
                        "observation": {
                            "classify_result": "txt",
                            "avg_cleaned_chars_per_page": 120.0,
                            "invalid_char_ratio": 0.0,
                            "cid_char_ratio": 0.0,
                            "high_image_coverage_ratio": 0.2,
                            "classifier_signal_accepts_text_path": True,
                        },
                        "scored": {
                            "scores": {
                                "original": {"primary_score": 0.1, "auxiliary_metrics": {"cer": 0.8}},
                                "rasterized": {"primary_score": 0.7, "auxiliary_metrics": {"cer": 0.2}},
                                "auto": {"primary_score": 0.7, "auxiliary_metrics": {"cer": 0.2}},
                            }
                        },
                    }
                ],
            },
            scored_payload={
                "variant_summary": {},
                "pairwise_summary": {"rasterized_vs_original": {"mean_delta": 0.2}},
            },
        )
        self.assertEqual(payload["claim_mode"], "controlled_classifier_unreliability_supported")
        self.assertEqual(payload["direct_txt_observations_on_ood_docs"][0]["doc_id"], "receipt-1")
        self.assertEqual(payload["direct_txt_observations_on_ood_docs"][0]["original_primary_score"], 0.1)
        self.assertEqual(payload["direct_txt_observations_on_ood_docs"][0]["invalid_char_ratio"], 0.0)
        self.assertTrue(payload["direct_txt_observations_on_ood_docs"][0]["supports_direct_failure_observation"])

    def test_claim_mode_stays_conservative_when_txt_row_fails_classifier_signal_gate(self):
        payload = builder.build_claim_evidence(
            routing_payload={
                "summary": {"documents": 1},
                "rows": [
                    {
                        "doc_id": "receipt-1",
                        "subgroup": "receipt",
                        "observation": {
                            "classify_result": "txt",
                            "avg_cleaned_chars_per_page": 120.0,
                            "invalid_char_ratio": 0.4,
                            "high_image_coverage_ratio": 0.2,
                            "classifier_signal_accepts_text_path": False,
                        },
                        "scored": {
                            "scores": {
                                "original": {"primary_score": 0.1, "auxiliary_metrics": {"cer": 0.8}},
                                "rasterized": {"primary_score": 0.7, "auxiliary_metrics": {"cer": 0.2}},
                                "auto": {"primary_score": 0.7, "auxiliary_metrics": {"cer": 0.2}},
                            }
                        },
                    }
                ],
            },
            scored_payload={
                "variant_summary": {},
                "pairwise_summary": {"rasterized_vs_original": {"mean_delta": 0.2}},
            },
        )
        self.assertEqual(payload["claim_mode"], "conservative_inference_only")
        self.assertFalse(payload["direct_txt_observations_on_ood_docs"][0]["supports_direct_failure_observation"])

    def test_claim_mode_stays_conservative_when_txt_row_has_no_recovery_evidence(self):
        payload = builder.build_claim_evidence(
            routing_payload={
                "summary": {"documents": 1},
                "rows": [
                    {
                        "doc_id": "receipt-1",
                        "subgroup": "receipt",
                        "observation": {
                            "classify_result": "txt",
                            "avg_cleaned_chars_per_page": 120.0,
                            "invalid_char_ratio": 0.0,
                            "high_image_coverage_ratio": 0.2,
                            "classifier_signal_accepts_text_path": True,
                        },
                        "scored": {
                            "scores": {
                                "original": {"primary_score": 0.8, "auxiliary_metrics": {"cer": 0.2}},
                                "rasterized": {"primary_score": 0.7, "auxiliary_metrics": {"cer": 0.3}},
                                "auto": {"primary_score": 0.7, "auxiliary_metrics": {"cer": 0.3}},
                            }
                        },
                    }
                ],
            },
            scored_payload={
                "variant_summary": {},
                "pairwise_summary": {"rasterized_vs_original": {"mean_delta": -0.1}},
            },
        )
        self.assertEqual(payload["claim_mode"], "conservative_inference_only")
        self.assertFalse(payload["direct_txt_observations_on_ood_docs"][0]["supports_direct_failure_observation"])

    def test_render_markdown_includes_control_rows_and_fallback_message(self):
        payload = builder.build_claim_evidence(
            routing_payload={"summary": {}, "rows": []},
            scored_payload={
                "variant_summary": {
                    "original": {"n": 2, "mean_primary_score": 0.5, "mean_auxiliary_metrics": {"token_f1": 0.5, "cer": 0.7, "wer": 0.8, "ned": 0.6}},
                    "rasterized": {"n": 2, "mean_primary_score": 0.6, "mean_auxiliary_metrics": {"token_f1": 0.6, "cer": 0.5, "wer": 0.7, "ned": 0.5}},
                    "auto": {"n": 2, "mean_primary_score": 0.7, "mean_auxiliary_metrics": {"token_f1": 0.7, "cer": 0.4, "wer": 0.6, "ned": 0.4}},
                },
                "pairwise_summary": {"auto_minus_original": {"mean_delta": 0.2}},
            },
            control_scored_payload={
                "variant_summary": {
                    "original": {"n": 1, "mean_primary_score": 0.9, "mean_auxiliary_metrics": {"token_f1": 0.9, "cer": 0.1, "wer": 0.1, "ned": 0.1}},
                    "rasterized": {"n": 1, "mean_primary_score": 0.88, "mean_auxiliary_metrics": {"token_f1": 0.88, "cer": 0.12, "wer": 0.12, "ned": 0.12}},
                    "auto": {"n": 1, "mean_primary_score": 0.9, "mean_auxiliary_metrics": {"token_f1": 0.9, "cer": 0.1, "wer": 0.1, "ned": 0.1}},
                }
            },
        )
        rendered = builder.render_markdown(payload)
        self.assertIn("Structured control quantitative rows", rendered)
        self.assertIn("No receipt/invoice-style OOD document", rendered)
        self.assertIn("auto_minus_original", rendered)


if __name__ == "__main__":
    unittest.main()

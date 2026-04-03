import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


observe = load_module(
    "observe_paper_ood_routing", SCRIPT_DIR / "observe_paper_ood_routing.py"
)


class ObservePaperOODRoutingTests(unittest.TestCase):
    def test_cid_char_ratio_detects_cid_tokens(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf = Path(tmpdir) / "sample.pdf"
            pdf.write_bytes(b"%PDF-1.4 fake")
            with mock.patch.object(observe, "extract_text", return_value="abc(cid:12)(cid:34)"):
                ratio = observe.invalid_char_ratio(b"fake")
        self.assertGreater(ratio, 0.0)

    def test_build_scored_index_maps_doc_scores(self):
        payload = {
            "doc_comparisons": [{"doc_id": "doc-1", "best_variant": "auto"}],
            "doc_scores": [
                {
                    "doc_id": "doc-1",
                    "variant": "auto",
                    "auxiliary_metrics": {"cer": 0.1},
                }
            ],
        }
        index = observe.build_scored_index(payload)
        self.assertEqual(index["doc-1"]["comparison"]["best_variant"], "auto")
        self.assertEqual(index["doc-1"]["scores"]["auto"]["auxiliary_metrics"]["cer"], 0.1)

    def test_summarize_tracks_txt_rates_and_cer(self):
        rows = [
            {
                "subgroup": "receipt",
                "observation": {"classify_result": "txt", "cid_char_ratio": 0.2},
                "scored": {"scores": {"auto": {"auxiliary_metrics": {"cer": 0.3}}, "original": {"auxiliary_metrics": {"cer": 0.5}}}},
            },
            {
                "subgroup": "receipt",
                "observation": {"classify_result": "ocr", "cid_char_ratio": 0.0},
                "scored": None,
            },
        ]
        summary = observe.summarize(rows)
        self.assertEqual(summary["subgroup_counts"]["receipt"], 2)
        self.assertEqual(summary["subgroup_txt_counts"]["receipt"], 1)
        self.assertAlmostEqual(summary["mean_original_cer_when_classified_txt"], 0.5)


    def test_load_manifest_from_benchmark_csv_filters_doc_ids(self):
        rows = [
            {
                'doc_id': 'sample2_reciept',
                'filename': 'benchmark/pdfs/sample2_reciept.pdf',
                'benchmark_group': 'unstructured',
            },
            {
                'doc_id': 'sample1_researchpaper',
                'filename': 'benchmark/pdfs/sample1_researchpaper.pdf',
                'benchmark_group': 'structured',
            },
        ]
        with mock.patch.object(observe, 'load_benchmark_manifest_csv', return_value=rows):
            manifest_rows = observe.load_manifest_from_benchmark_csv(Path('benchmark/manifest.csv'), {'sample2_reciept'})
        self.assertEqual(len(manifest_rows), 1)
        self.assertEqual(manifest_rows[0]['doc_id'], 'sample2_reciept')
        self.assertEqual(manifest_rows[0]['subgroup'], 'receipt')

    def test_observe_pdf_reports_classifier_signal_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf = Path(tmpdir) / "sample.pdf"
            pdf.write_bytes(b"%PDF-1.4 fake")
            with (
                mock.patch.object(observe, "extract_pages", return_value=b"fake"),
                mock.patch.object(observe, "classify", return_value="txt"),
                mock.patch.object(observe, "get_avg_cleaned_chars_per_page", return_value=120.0),
                mock.patch.object(observe, "invalid_char_ratio", return_value=0.0),
                mock.patch.object(observe, "get_high_image_coverage_ratio", return_value=0.2),
                mock.patch.object(observe.pdfium, "PdfDocument") as pdf_document,
            ):
                pdf_document.return_value.__len__.return_value = 1
                result = observe.observe_pdf(pdf)
        self.assertTrue(result["classifier_signal_status"]["chars_threshold_passed"])
        self.assertTrue(result["classifier_signal_status"]["invalid_ratio_threshold_passed"])
        self.assertTrue(result["classifier_signal_status"]["image_coverage_threshold_passed"])
        self.assertTrue(result["classifier_signal_accepts_text_path"])
        self.assertEqual(result["invalid_char_ratio"], 0.0)


if __name__ == "__main__":
    unittest.main()

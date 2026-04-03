import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


materialize = load_module(
    "materialize_paper_routing_evidence_dataset",
    SCRIPT_DIR / "materialize_paper_routing_evidence_dataset.py",
)


def write_sample_png(path: Path) -> None:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 200), False)
    pix.clear_with(0xFFFFFF)
    pix.save(path)
    pix = None


class MaterializePaperRoutingEvidenceDatasetTests(unittest.TestCase):
    def test_build_harmful_text_is_non_empty_and_corrupted(self):
        text = materialize.build_harmful_text("TOTAL 1234\nVISA 9999", target_chars=120)
        self.assertGreaterEqual(len(text), 120)
        self.assertNotIn("TOTAL 1234", text)

    def test_materialize_pdf_produces_txt_classification(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            image_path = tmp / "source.png"
            write_sample_png(image_path)
            output_pdf = tmp / "trap.pdf"
            payload = materialize.materialize_pdf(
                image_path=image_path,
                harmful_text=materialize.build_harmful_text("receipt total subtotal visa 1234", target_chars=800),
                output_pdf=output_pdf,
            )
            self.assertEqual(payload["observation"]["classify_result"], "txt")
            self.assertGreater(payload["observation"]["avg_cleaned_chars_per_page"], 50)
            self.assertLess(payload["observation"]["high_image_coverage_ratio"], 0.8)
            self.assertTrue(payload["observation"]["classifier_signal_accepts_text_path"])

    def test_materialize_pdf_requires_text_path_acceptance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            image_path = tmp / "source.png"
            write_sample_png(image_path)
            output_pdf = tmp / "trap.pdf"
            observations = [
                {
                    "classify_result": "txt",
                    "classifier_signal_accepts_text_path": False,
                    "avg_cleaned_chars_per_page": 120.0,
                    "high_image_coverage_ratio": 0.2,
                },
                {
                    "classify_result": "txt",
                    "classifier_signal_accepts_text_path": True,
                    "avg_cleaned_chars_per_page": 120.0,
                    "high_image_coverage_ratio": 0.2,
                },
            ]
            with mock.patch.object(materialize, "observe_pdf", side_effect=observations):
                payload = materialize.materialize_pdf(
                    image_path=image_path,
                    harmful_text="receipt total subtotal visa",
                    output_pdf=output_pdf,
                )
            self.assertTrue(payload["observation"]["classifier_signal_accepts_text_path"])

    def test_build_manifest_row_marks_synthetic_source(self):
        source_row = {
            "doc_id": "receipt-sroie-0001",
            "input_pdf": "benchmark/pdfs/receipt-sroie-0001.pdf",
            "subgroup": "receipt",
            "source_bucket": "hf:jsdnrs/ICDAR2019-SROIE",
            "gold_path": "benchmark/paper_ood/gold/receipt-sroie-0001.json",
            "gold_format": "fields_json",
            "metric_family": "token_f1",
            "annotation_source": "manual_from_source_annotation",
            "canonicalization_version": "v1",
        }
        donor_row = {"doc_id": "receipt-sroie-0002"}
        row = materialize.build_manifest_row(
            source_row=source_row,
            donor_row=donor_row,
            output_pdf=Path("/repo/benchmark/paper_ood/derived/routing_evidence/receipt-sroie-0001-routingtrap.pdf"),
        )
        self.assertEqual(row["doc_id"], "receipt-sroie-0001-routingtrap")
        self.assertEqual(row["base_doc_id"], "receipt-sroie-0001")
        self.assertEqual(row["donor_doc_id"], "receipt-sroie-0002")
        self.assertIn("synthetic:routing-evidence", row["source_bucket"])


if __name__ == "__main__":
    unittest.main()

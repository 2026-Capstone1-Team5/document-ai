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


text_layer_strip_pdf = load_module(
    "text_layer_strip_pdf", SCRIPT_DIR / "text_layer_strip_pdf.py"
)


class TextLayerStripTests(unittest.TestCase):
    def test_strip_text_layer_preserves_page_count_and_removes_text(self):
        try:
            import fitz
        except ImportError as exc:
            self.skipTest(f"PyMuPDF unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_pdf = tmp_path / "input.pdf"
            output_pdf = tmp_path / "output.pdf"

            doc = fitz.open()
            page = doc.new_page(width=200, height=100)
            page.insert_text((24, 50), "hello world")
            doc.save(input_pdf)
            doc.close()

            generation = text_layer_strip_pdf.strip_text_layer(
                input_pdf, output_pdf, dpi=72
            )
            validation = text_layer_strip_pdf.validate_text_layer_stripped(
                input_pdf, output_pdf
            )
            output_exists = output_pdf.exists()

        self.assertTrue(output_exists)
        self.assertEqual(generation["input_page_count"], 1)
        self.assertTrue(validation["page_count_equal"])
        self.assertTrue(validation["page_size_equal"])
        self.assertTrue(validation["text_layer_removed"])
        self.assertTrue(validation["render_fidelity_ok"])
        self.assertEqual(validation["extracted_text_chars"], 0)

    def test_build_provenance_payload_includes_generation_and_validation(self):
        try:
            import fitz
        except ImportError as exc:
            self.skipTest(f"PyMuPDF unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_pdf = tmp_path / "input.pdf"
            output_pdf = tmp_path / "output.pdf"

            doc = fitz.open()
            page = doc.new_page(width=144, height=72)
            page.insert_text((12, 36), "provenance")
            doc.save(input_pdf)
            doc.close()

            payload = text_layer_strip_pdf.build_provenance_payload(
                input_pdf,
                output_pdf,
                dpi=72,
                max_text_chars=0,
                page_size_tolerance=0.01,
                render_diff_dpi=72,
                render_diff_tolerance=0.01,
            )
            sidecar = output_pdf.with_suffix(".pdf.provenance.json")
            sidecar.write_text(json.dumps(payload, indent=2))
            sidecar_exists = sidecar.exists()

        self.assertEqual(payload["generator"], "text_layer_strip_pdf")
        self.assertEqual(payload["generation"]["method"], "render_page_to_image_pdf")
        self.assertTrue(payload["validation"]["text_layer_removed"])
        self.assertIn("render_diff_ratio_max", payload["validation"])
        self.assertTrue(sidecar_exists)


if __name__ == "__main__":
    unittest.main()

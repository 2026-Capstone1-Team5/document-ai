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


bootstrap = load_module(
    "bootstrap_paper_ood_from_hf", SCRIPT_DIR / "bootstrap_paper_ood_from_hf.py"
)


class BootstrapPaperOODFromHFTests(unittest.TestCase):
    def test_bootstrap_sroie_fields_uses_entities(self):
        row = {
            "entities": {
                "company": "ACME",
                "date": "2026-01-01",
                "address": "",
                "total": "42.00",
            }
        }
        fields = bootstrap.bootstrap_sroie_fields(row)
        self.assertEqual(fields, {"company": "ACME", "date": "2026-01-01", "total": "42.00"})

    def test_bootstrap_cord_fields_flattens_gt_parse(self):
        row = {
            "ground_truth": json.dumps(
                {
                    "gt_parse": {
                        "menu": [
                            {"nm": "Americano", "price": "4.50"},
                            {"nm": "Bagel", "price": "3.00"},
                        ],
                        "total": {"total_price": "7.50"},
                    }
                }
            )
        }
        fields = bootstrap.bootstrap_cord_fields(row)
        self.assertIn("menu", fields)
        self.assertEqual(fields["total.total_price"], "7.50")

    def test_bootstrap_funsd_fields_prefers_form_entries(self):
        row = {
            "text_output": json.dumps(
                {
                    "form": [
                        {"label": "question", "text": "Name"},
                        {"label": "answer", "text": "Alice"},
                    ]
                }
            )
        }
        fields = bootstrap.bootstrap_funsd_fields(row)
        self.assertEqual(fields["question_01"], "Name")
        self.assertEqual(fields["answer_01"], "Alice")

    def test_bootstrap_invoice_fields_flattens_parsed_data(self):
        row = {
            "parsed_data": json.dumps(
                {
                    "seller": {"name": "Store"},
                    "totals": {"grand_total": "15.00"},
                }
            )
        }
        fields = bootstrap.bootstrap_invoice_fields(row)
        self.assertEqual(fields["seller.name"], "Store")
        self.assertEqual(fields["totals.grand_total"], "15.00")

    def test_build_manifest_row_uses_relative_repo_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(bootstrap.REPO_ROOT)
            pdf_path = repo_root / "benchmark/paper_ood/raw/doc-1.pdf"
            gold_path = repo_root / "benchmark/paper_ood/gold/doc-1.json"
            args = type(
                "Args",
                (),
                {
                    "doc_id": "doc-1",
                    "subgroup": "receipt",
                    "source_bucket": "hf:demo/source",
                    "gold_format": "fields_json",
                    "metric_family": "token_f1",
                    "annotation_source": "manual",
                    "language": "en",
                    "suspected_issue": "ocr_noise",
                    "inclusion_reason": "test",
                    "freeze_revision": "paper-ood-v1",
                },
            )
            row = bootstrap.build_manifest_row(args, pdf_path, gold_path)
        self.assertEqual(row["input_pdf"], "benchmark/paper_ood/raw/doc-1.pdf")
        self.assertEqual(row["gold_path"], "benchmark/paper_ood/gold/doc-1.json")


if __name__ == "__main__":
    unittest.main()

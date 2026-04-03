import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


materialize = load_module(
    "materialize_paper_ood_batch", SCRIPT_DIR / "materialize_paper_ood_batch.py"
)


class MaterializePaperOODBatchTests(unittest.TestCase):
    def test_load_plan_requires_array(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "plan.json"
            path.write_text('{"bad":true}', encoding="utf-8")
            with self.assertRaises(ValueError):
                materialize.load_plan(path)

    def test_validate_manifest_returns_none_for_empty_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.jsonl"
            self.assertIsNone(materialize.validate_manifest(path, []))

    def test_write_tracker_outputs_csv_header_and_rows(self):
        rows = [
            {
                "doc_id": "doc-1",
                "role": "main",
                "subgroup": "receipt",
                "source_bucket": "hf:test",
                "input_pdf_frozen": "yes",
                "gold_created": "yes",
                "manifest_row_written": "yes",
                "audit_passed": "yes",
                "notes": "ok",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tracker.csv"
            materialize.write_tracker(path, rows)
            with path.open("r", encoding="utf-8", newline="") as handle:
                parsed = list(csv.DictReader(handle))
        self.assertEqual(parsed[0]["doc_id"], "doc-1")

    @patch.object(materialize, "run_json_command")
    def test_validate_manifest_builds_exact_thresholds(self, mock_run_json_command):
        mock_run_json_command.side_effect = [
            {"passed": True, "checked": 2},
            {"passed": True, "total_rows": 2},
        ]
        rows = [
            {"doc_id": "a", "subgroup": "receipt"},
            {"doc_id": "b", "subgroup": "invoice"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "ready.jsonl"
            manifest_path.write_text("", encoding="utf-8")
            report = materialize.validate_manifest(manifest_path, rows)
        self.assertTrue(report["passed"])
        audit_command = mock_run_json_command.call_args_list[1].args[0]
        self.assertIn("--min-total", audit_command)
        self.assertIn("2", audit_command)
        self.assertIn("receipt=1", audit_command)
        self.assertIn("invoice=1", audit_command)

    @patch.object(materialize.subprocess, "run")
    def test_run_bootstrap_forwards_dataset_revision(self, mock_run):
        mock_run.return_value = type(
            "CompletedProcess",
            (),
            {
                "stdout": json.dumps(
                    {
                        "manifest_row": {"doc_id": "receipt-sroie-0001"},
                        "gold_path": "benchmark/paper_ood/gold/receipt-sroie-0001.json",
                    }
                ),
            },
        )()
        item = {
            "doc_id": "receipt-sroie-0001",
            "dataset": "jsdnrs/ICDAR2019-SROIE",
            "dataset_revision": "rev-xyz",
            "split": "train",
            "index": 0,
            "subgroup": "receipt",
            "source_shortname": "sroie",
            "gold_format": "fields_json",
            "metric_family": "token_f1",
            "annotation_source": "manual_from_source_annotation",
            "language": "en",
            "source_bucket": "hf:jsdnrs/ICDAR2019-SROIE",
            "suspected_issue": "ocr_noise",
            "inclusion_reason": "starter_batch_scanned_receipt",
            "freeze_revision": "paper-ood-v1",
        }
        materialize.run_bootstrap(item)
        command = mock_run.call_args.kwargs["args"] if "args" in mock_run.call_args.kwargs else mock_run.call_args.args[0]
        self.assertIn("--dataset-revision", command)
        self.assertIn("rev-xyz", command)


if __name__ == "__main__":
    unittest.main()

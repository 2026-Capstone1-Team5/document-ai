import importlib.util
import json
import subprocess
import sys
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


audit_manifest = load_module(
    "audit_paper_ood_manifest", SCRIPT_DIR / "audit_paper_ood_manifest.py"
)


class AuditPaperOODManifestTests(unittest.TestCase):
    def test_audit_rows_reports_missing_files_and_thresholds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            rows = [
                {
                    "_line_number": 1,
                    "doc_id": "doc-001",
                    "input_pdf": str(tmp_path / "missing.pdf"),
                    "subgroup": "receipt",
                    "gold_path": str(tmp_path / "missing.json"),
                    "gold_format": "fields_json",
                    "metric_family": "token_f1",
                    "annotation_source": "manual",
                    "canonicalization_version": "v1",
                }
            ]
            report = audit_manifest.audit_rows(
                rows,
                require_stripped=True,
                min_total=2,
                min_subgroup={"receipt": 2},
            )

        self.assertFalse(report["passed"])
        self.assertIn("manifest has 1 rows, below required minimum 2", report["errors"])
        self.assertTrue(any("missing input_pdf" in error for error in report["errors"]))
        self.assertTrue(any("missing stripped_pdf" in error for error in report["errors"]))
        self.assertTrue(any("source_bucket missing" in warning for warning in report["warnings"]))

    def test_cli_writes_json_and_passes_for_complete_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_pdf = tmp_path / "doc.pdf"
            gold_path = tmp_path / "gold.json"
            stripped_pdf = tmp_path / "doc.stripped.pdf"
            manifest = tmp_path / "manifest.jsonl"
            output = tmp_path / "audit.json"
            input_pdf.write_bytes(b"pdf")
            stripped_pdf.write_bytes(b"pdf")
            gold_path.write_text("{}", encoding="utf-8")
            manifest.write_text(
                json.dumps(
                    {
                        "doc_id": "doc-001",
                        "input_pdf": str(input_pdf),
                        "stripped_pdf": str(stripped_pdf),
                        "subgroup": "receipt",
                        "source_bucket": "hf:demo/receipts",
                        "gold_path": str(gold_path),
                        "gold_format": "fields_json",
                        "metric_family": "token_f1",
                        "annotation_source": "manual",
                        "canonicalization_version": "v1",
                        "freeze_revision": "paper-ood-v1",
                        "inclusion_reason": "pilot",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "audit_paper_ood_manifest.py"),
                    str(manifest),
                    "--require-stripped",
                    "--min-total",
                    "1",
                    "--min-subgroup",
                    "receipt=1",
                    "--json-output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(report["passed"])
        self.assertEqual(report["subgroup_counts"], {"receipt": 1})
        self.assertEqual(report["metric_family_counts"], {"token_f1": 1})


if __name__ == "__main__":
    unittest.main()

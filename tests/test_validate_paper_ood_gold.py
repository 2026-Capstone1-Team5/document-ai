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


validate_gold = load_module(
    "validate_paper_ood_gold", SCRIPT_DIR / "validate_paper_ood_gold.py"
)


class ValidatePaperOODGoldTests(unittest.TestCase):
    def test_fields_json_requires_non_empty_object(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "gold.json"
            path.write_text("{}", encoding="utf-8")
            errors = validate_gold.validate_gold_file(path, "fields_json")
        self.assertEqual(errors, ["fields_json must not be empty"])

    def test_transcript_json_accepts_text_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "gold.json"
            path.write_text(json.dumps({"text": "hello world"}), encoding="utf-8")
            errors = validate_gold.validate_gold_file(path, "transcript_json")
        self.assertEqual(errors, [])

    def test_manifest_report_marks_bad_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            good = tmp_path / "good.txt"
            bad = tmp_path / "bad.json"
            manifest = tmp_path / "manifest.jsonl"
            good.write_text("hello", encoding="utf-8")
            bad.write_text("{}", encoding="utf-8")
            manifest.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "doc_id": "doc-1",
                                "gold_path": str(good),
                                "gold_format": "transcript_txt",
                            }
                        ),
                        json.dumps(
                            {
                                "doc_id": "doc-2",
                                "gold_path": str(bad),
                                "gold_format": "fields_json",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            report = validate_gold.build_report_for_manifest(
                validate_gold.load_manifest_rows(manifest)
            )
        self.assertFalse(report["passed"])
        self.assertEqual(report["checked"], 2)
        self.assertTrue(report["items"][0]["passed"])
        self.assertEqual(report["items"][1]["errors"], ["fields_json must not be empty"])

    def test_cli_single_file_validation_writes_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            gold = tmp_path / "gold.txt"
            output = tmp_path / "report.json"
            gold.write_text("transcript", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "validate_paper_ood_gold.py"),
                    "--gold-path",
                    str(gold),
                    "--gold-format",
                    "transcript_txt",
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
        self.assertEqual(report["mode"], "single")


if __name__ == "__main__":
    unittest.main()
